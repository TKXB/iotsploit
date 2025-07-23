import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from sat_toolkit.tools.monitor_mgr import SystemMonitor
import asyncio
from asgiref.sync import async_to_sync
from celery.result import AsyncResult
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamType, StreamSource, StreamAction
from sat_toolkit.core.device_manager import DeviceDriverManager
import time
from sat_toolkit.core.device_spec import DeviceState
from collections import deque
import threading
# from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager  # Import locally to avoid circular imports

logger = logging.getLogger(__name__)

# Configure the log buffer for console logs
MAX_LOG_ENTRIES = 1000
console_log_buffer = deque(maxlen=MAX_LOG_ENTRIES)
log_buffer_lock = threading.Lock()

class SystemUsageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("WebSocket connection attempt received")
        await self.accept()
        logger.info("WebSocket connection accepted")
        self.monitor = SystemMonitor.create_monitor("linux")
        self.is_monitoring = True
        self.monitor.start_monitoring()
        asyncio.create_task(self.send_system_usage())

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected with code: {close_code}")
        self.is_monitoring = False

    async def send_system_usage(self):
        while self.is_monitoring:
            try:
                cpu_usage = self.monitor.get_cpu_usage()
                memory_usage = self.monitor.get_memory_usage()
                await self.send(text_data=json.dumps({
                    'cpu_usage': cpu_usage,
                    'memory_usage': memory_usage
                }))
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in send_system_usage: {str(e)}")
                break

class ExploitWebsocketConsumer(AsyncWebsocketConsumer):
    instances = {}  # Class variable to track all active consumers

    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        logger.info(f"WebSocket connected for task: {self.task_id}")
        await self.accept()
        
        # Flag to control polling
        self.is_polling = True
        # Start a periodic polling task for task status updates.
        asyncio.create_task(self.poll_task_status())

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected for task: {self.task_id}")
        # Stop polling on disconnect
        self.is_polling = False

    async def receive(self, text_data):
        """Handle incoming messages - could be used for requesting status updates"""
        try:
            data = json.loads(text_data)
            if data.get('action') == 'get_status':
                await self.send_task_status()
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")

    async def send_task_status(self):
        """Fetch and send task status from Celery/Redis"""
        try:
            # Get task result from Celery
            result = AsyncResult(self.task_id)
            
            if result.ready():
                # Task is complete
                task_result = result.get()
                await self.send(text_data=json.dumps({
                    'status': 'complete',
                    'result': task_result
                }))
                # Stop polling when task is complete
                self.is_polling = False
            else:
                # Task is still pending
                await self.send(text_data=json.dumps({
                    'status': 'pending',
                    'message': 'Task is still processing'
                }))

        except Exception as e:
            logger.error(f"Error fetching task status: {str(e)}")
            await self.send(text_data=json.dumps({
                'status': 'error',
                'message': f'Error fetching task status: {str(e)}'
            }))
            # Stop polling on error
            self.is_polling = False

    async def poll_task_status(self):
        # Poll for a status update every 1 second while is_polling is True
        while self.is_polling:
            await self.send_task_status()
            await asyncio.sleep(1)

class DeviceStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.channel = self.scope['url_route']['kwargs']['channel']
        self.group_name = f"stream_{self.channel}"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.debug(f"Stream connection established for channel: {self.channel}, channel_name: {self.channel_name}")
        
        # Register the channel with StreamManager
        self.stream_manager = StreamManager()
        await self.stream_manager.register_stream(self.channel)
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.debug(f"Stream connection closed for channel: {self.channel}, channel_name: {self.channel_name}")
        
        # Unregister the channel from StreamManager
        await self.stream_manager.unregister_stream(self.channel)
    
    async def stream_data(self, event):
        """Handle incoming stream data and forward it to the WebSocket"""
        logger.debug(f"Received stream data for channel {self.channel}, channel_name: {self.channel_name}: {event['data']}")
        await self.send(text_data=json.dumps(event['data']))

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            json_data = json.loads(text_data)
            stream_data = StreamData.from_dict(json_data)

            # 根据 stream_type 获取对应的驱动名称
            driver_name = None
            if stream_data.stream_type == StreamType.UART:
                driver_name = 'drv_ft2232'
            elif stream_data.stream_type == StreamType.CAN:
                driver_name = 'drv_socketcan'

            if not driver_name:
                error_data = StreamData(
                    stream_type=stream_data.stream_type,
                    channel=self.channel,
                    timestamp=time.time(),
                    source=StreamSource.SYSTEM,
                    action=StreamAction.ERROR,
                    data={'message': f'Unsupported stream type: {stream_data.stream_type.value}'},
                    metadata={'original_request': stream_data.to_dict()}
                )
                await self.send(text_data=json.dumps(error_data.to_dict()))
                return

            # Get the driver instance
            device_manager = DeviceDriverManager()
            driver = device_manager.get_driver_instance(driver_name)
            logger.info(f"Driver instance details: {driver}")
            
            if not driver:
                error_data = StreamData(
                    stream_type=stream_data.stream_type,
                    channel=self.channel,
                    timestamp=time.time(),
                    source=StreamSource.SYSTEM,
                    action=StreamAction.ERROR,
                    data={'message': f'{stream_data.stream_type.value} driver not found'},
                    metadata={'original_request': stream_data.to_dict()}
                )
                await self.send(text_data=json.dumps(error_data.to_dict()))
                return

            # 检查设备状态
            device_state = device_manager.get_device_state(driver_name, self.channel)
            if device_state != DeviceState.CONNECTED:
                logger.info("Device not connected, attempting to scan and connect...")
                devices = driver.scan()
                logger.info(f"Scan results: {devices}")
                
                if devices:
                    device = devices[0]
                    init_result = device_manager.initialize_device(driver_name, device)
                    connect_result = device_manager.connect_device(driver_name, device)
                    
                    if not (init_result.get('status') == 'success' and connect_result.get('status') == 'success'):
                        error_data = StreamData(
                            stream_type=stream_data.stream_type,
                            channel=self.channel,
                            timestamp=time.time(),
                            source=StreamSource.SYSTEM,
                            action=StreamAction.ERROR,
                            data={'message': f'Failed to initialize/connect {stream_data.stream_type.value} device'},
                            metadata={'original_request': stream_data.to_dict()}
                        )
                        await self.send(text_data=json.dumps(error_data.to_dict()))
                        return
                else:
                    error_data = StreamData(
                        stream_type=stream_data.stream_type,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SYSTEM,
                        action=StreamAction.ERROR,
                        data={'message': f'No {stream_data.stream_type.value} devices found'},
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(error_data.to_dict()))
                    return

            # Handle UART-specific actions
            if stream_data.stream_type == StreamType.UART and stream_data.action == StreamAction.SEND:
                try:
                    uart_channel = stream_data.metadata.get('channel', 'A')  # Default to channel A if not specified
                    hex_data = stream_data.data.get('data')
                    if not hex_data:
                        raise ValueError("No data provided for UART transmission")
                    
                    data = bytes.fromhex(hex_data)
                    driver.send_uart_data(driver.device, uart_channel, data)
                    
                    # Send success response
                    response_data = StreamData(
                        stream_type=StreamType.UART,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SERVER,
                        action=StreamAction.STATUS,
                        data={
                            'status': 'success',
                            'message': f'Sent UART data on channel {uart_channel}: {hex_data}'
                        },
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(response_data.to_dict()))
                    
                except (ValueError, KeyError) as e:
                    error_data = StreamData(
                        stream_type=StreamType.UART,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SYSTEM,
                        action=StreamAction.ERROR,
                        data={'message': f'Invalid UART message format: {str(e)}'},
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(error_data.to_dict()))
                    
                except Exception as e:
                    error_data = StreamData(
                        stream_type=StreamType.UART,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SYSTEM,
                        action=StreamAction.ERROR,
                        data={'message': f'Failed to send UART data: {str(e)}'},
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(error_data.to_dict()))

            # Handle CAN-specific actions
            elif stream_data.stream_type == StreamType.CAN and stream_data.action == StreamAction.SEND:
                try:
                    can_id = int(stream_data.data['id'], 16)
                    can_data = bytes.fromhex(stream_data.data['data'])
                    
                    driver.send_can_message(driver.device, can_id, can_data)
                    
                    # Send success response
                    response_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SERVER,
                        action=StreamAction.STATUS,
                        data={
                            'status': 'success',
                            'message': f'Sent CAN message - ID: {hex(can_id)}, Data: {can_data.hex()}'
                        },
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(response_data.to_dict()))
                    
                except (ValueError, KeyError) as e:
                    error_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SYSTEM,
                        action=StreamAction.ERROR,
                        data={'message': f'Invalid CAN message format: {str(e)}'},
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(error_data.to_dict()))
                    
                except Exception as e:
                    error_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=self.channel,
                        timestamp=time.time(),
                        source=StreamSource.SYSTEM,
                        action=StreamAction.ERROR,
                        data={'message': f'Failed to send CAN message: {str(e)}'},
                        metadata={'original_request': stream_data.to_dict()}
                    )
                    await self.send(text_data=json.dumps(error_data.to_dict()))
                    
        except json.JSONDecodeError as e:
            error_data = StreamData(
                stream_type=StreamType.CAN,  # Default to CAN for backward compatibility
                channel=self.channel,
                timestamp=time.time(),
                source=StreamSource.SYSTEM,
                action=StreamAction.ERROR,
                data={'message': 'Invalid JSON format'},
                metadata={'error': str(e)}
            )
            await self.send(text_data=json.dumps(error_data.to_dict()))
        except Exception as e:
            error_data = StreamData(
                stream_type=StreamType.CAN,  # Default to CAN for backward compatibility
                channel=self.channel,
                timestamp=time.time(),
                source=StreamSource.SYSTEM,
                action=StreamAction.ERROR,
                data={'message': str(e)},
                metadata={'error': str(e)}
            )
            await self.send(text_data=json.dumps(error_data.to_dict()))

class ConsoleLogsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for streaming console log output"""
    
    async def connect(self):
        """Connect to the WebSocket and join the logs group"""
        await self.accept()
        
        # Join the logs group
        self.group_name = "console_logs"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Send any existing logs from the buffer
        try:
            with log_buffer_lock:
                existing_logs = list(console_log_buffer)
            
            if existing_logs:
                for log in existing_logs[-50:]:  # Send the most recent 50 logs
                    await self.send(text_data=log)
            
            # Send a connection confirmation message
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Connected to console log stream'
            }))
            
        except Exception as e:
            logger.error(f"Error sending existing logs: {e}")
    
    async def disconnect(self, close_code):
        """Disconnect from the WebSocket and leave the logs group"""
        # Leave the logs group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def console_log(self, event):
        """Send a console log message to the WebSocket"""
        try:
            # Extract the message from the event
            message = event['message']
            # Send the message to the WebSocket
            await self.send(text_data=message)
        except Exception as e:
            logger.error(f"Error sending console log: {e}")


class IoTFuzzerTestingConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for IoT Fuzzer testing page real-time updates"""
    
    async def connect(self):
        """Connect to the WebSocket and join the fuzzer group"""
        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id')
        
        # Join the IoT fuzzer groups
        self.general_group = "iot_fuzzer_general"
        await self.channel_layer.group_add(
            self.general_group,
            self.channel_name
        )
        
        # Join campaign-specific group if campaign_id is provided
        if self.campaign_id:
            self.campaign_group = f"iot_fuzzer_campaign_{self.campaign_id}"
            await self.channel_layer.group_add(
                self.campaign_group,
                self.channel_name
            )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to IoT Fuzzer testing stream',
            'campaign_id': self.campaign_id
        }))
        
        # Send initial status if campaign exists
        if self.campaign_id:
            await self.send_initial_status()
    
    async def disconnect(self, close_code):
        """Disconnect from the WebSocket and leave the fuzzer groups"""
        # Leave the general group
        await self.channel_layer.group_discard(
            self.general_group,
            self.channel_name
        )
        
        # Leave campaign-specific group if exists
        if hasattr(self, 'campaign_group'):
            await self.channel_layer.group_discard(
                self.campaign_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_status':
                await self.send_current_status(data.get('campaign_id'))
            elif message_type == 'get_statistics':
                await self.send_current_statistics(data.get('campaign_id'))
            elif message_type == 'subscribe_campaign':
                await self.subscribe_to_campaign(data.get('campaign_id'))
            elif message_type == 'unsubscribe_campaign':
                await self.unsubscribe_from_campaign(data.get('campaign_id'))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))
    
    async def fuzzer_event(self, event):
        """Handle fuzzer events from the bridge"""
        try:
            # Forward the event to the WebSocket client
            await self.send(text_data=json.dumps(event))
        except Exception as e:
            logger.error(f"Error sending fuzzer event: {str(e)}")
    
    async def send_initial_status(self):
        """Send initial campaign status"""
        try:
            if self.campaign_id:
                from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
                fuzzer_manager = IoTFuzzerManager.get_instance()
                status = fuzzer_manager.get_campaign_status(self.campaign_id)
                
                await self.send(text_data=json.dumps({
                    'type': 'initial_status',
                    'campaign_id': self.campaign_id,
                    'status': status
                }))
        except Exception as e:
            logger.error(f"Error sending initial status: {str(e)}")
    
    async def send_current_status(self, campaign_id):
        """Send current campaign status"""
        try:
            if campaign_id:
                from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
                fuzzer_manager = IoTFuzzerManager.get_instance()
                status = fuzzer_manager.get_campaign_status(campaign_id)
                
                await self.send(text_data=json.dumps({
                    'type': 'status_response',
                    'campaign_id': campaign_id,
                    'status': status
                }))
        except Exception as e:
            logger.error(f"Error sending current status: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error getting campaign status: {str(e)}'
            }))
    
    async def send_current_statistics(self, campaign_id):
        """Send current campaign statistics"""
        try:
            if campaign_id:
                from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
                fuzzer_manager = IoTFuzzerManager.get_instance()
                statistics = fuzzer_manager.get_campaign_statistics(campaign_id)
                
                await self.send(text_data=json.dumps({
                    'type': 'statistics_response',
                    'campaign_id': campaign_id,
                    'statistics': statistics
                }))
        except Exception as e:
            logger.error(f"Error sending current statistics: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error getting campaign statistics: {str(e)}'
            }))
    
    async def subscribe_to_campaign(self, campaign_id):
        """Subscribe to a specific campaign"""
        try:
            if campaign_id:
                # Leave old campaign group if exists
                if hasattr(self, 'campaign_group'):
                    await self.channel_layer.group_discard(
                        self.campaign_group,
                        self.channel_name
                    )
                
                # Join new campaign group
                self.campaign_id = campaign_id
                self.campaign_group = f"iot_fuzzer_campaign_{campaign_id}"
                await self.channel_layer.group_add(
                    self.campaign_group,
                    self.channel_name
                )
                
                await self.send(text_data=json.dumps({
                    'type': 'subscription_confirmed',
                    'campaign_id': campaign_id
                }))
                
                # Send initial status for new campaign
                await self.send_initial_status()
                
        except Exception as e:
            logger.error(f"Error subscribing to campaign: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error subscribing to campaign: {str(e)}'
            }))
    
    async def unsubscribe_from_campaign(self, campaign_id):
        """Unsubscribe from a specific campaign"""
        try:
            if hasattr(self, 'campaign_group') and campaign_id:
                await self.channel_layer.group_discard(
                    self.campaign_group,
                    self.channel_name
                )
                
                self.campaign_id = None
                delattr(self, 'campaign_group')
                
                await self.send(text_data=json.dumps({
                    'type': 'unsubscription_confirmed',
                    'campaign_id': campaign_id
                }))
                
        except Exception as e:
            logger.error(f"Error unsubscribing from campaign: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error unsubscribing from campaign: {str(e)}'
            }))


class IoTFuzzerResultsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for IoT Fuzzer results page real-time updates"""
    
    async def connect(self):
        """Connect to the WebSocket and join the results group"""
        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id')
        
        # Join the results group
        self.results_group = "iot_fuzzer_results"
        await self.channel_layer.group_add(
            self.results_group,
            self.channel_name
        )
        
        # Join campaign-specific group if campaign_id is provided
        if self.campaign_id:
            self.campaign_group = f"iot_fuzzer_campaign_{self.campaign_id}"
            await self.channel_layer.group_add(
                self.campaign_group,
                self.channel_name
            )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to IoT Fuzzer results stream',
            'campaign_id': self.campaign_id
        }))
    
    async def disconnect(self, close_code):
        """Disconnect from the WebSocket and leave the results groups"""
        # Leave the results group
        await self.channel_layer.group_discard(
            self.results_group,
            self.channel_name
        )
        
        # Leave campaign-specific group if exists
        if hasattr(self, 'campaign_group'):
            await self.channel_layer.group_discard(
                self.campaign_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_logs':
                await self.send_recent_logs(data.get('campaign_id'))
            elif message_type == 'filter_logs':
                await self.send_filtered_logs(data.get('filter_criteria'))
            elif message_type == 'subscribe_logs':
                await self.subscribe_to_logs(data.get('campaign_id'))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))
    
    async def fuzzer_event(self, event):
        """Handle fuzzer events from the bridge"""
        try:
            # Only forward log and result events to results consumer
            event_type = event.get('event_type')
            if event_type in ['log_message', 'test_result', 'crash_detected']:
                await self.send(text_data=json.dumps(event))
        except Exception as e:
            logger.error(f"Error sending fuzzer event: {str(e)}")
    
    async def send_recent_logs(self, campaign_id):
        """Send recent logs for a campaign"""
        try:
            # This would typically get logs from the database or log buffer
            # For now, we'll send a placeholder response
            await self.send(text_data=json.dumps({
                'type': 'logs_response',
                'campaign_id': campaign_id,
                'logs': []  # TODO: Implement actual log retrieval
            }))
        except Exception as e:
            logger.error(f"Error sending recent logs: {str(e)}")
    
    async def send_filtered_logs(self, filter_criteria):
        """Send filtered logs based on criteria"""
        try:
            # This would typically filter logs based on criteria
            # For now, we'll send a placeholder response
            await self.send(text_data=json.dumps({
                'type': 'filtered_logs_response',
                'filter_criteria': filter_criteria,
                'logs': []  # TODO: Implement actual log filtering
            }))
        except Exception as e:
            logger.error(f"Error sending filtered logs: {str(e)}")
    
    async def subscribe_to_logs(self, campaign_id):
        """Subscribe to logs for a specific campaign"""
        try:
            if campaign_id:
                # Subscribe to campaign-specific logs
                await self.send(text_data=json.dumps({
                    'type': 'log_subscription_confirmed',
                    'campaign_id': campaign_id
                }))
        except Exception as e:
            logger.error(f"Error subscribing to logs: {str(e)}")
