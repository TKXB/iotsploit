import json
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from iotsploit_django.tools.monitor_mgr import SystemMonitor
import asyncio
# Import the configured Celery app to ensure result backend is available
from iotsploit_django.tasks.celery_app import app as celery_app
from iotsploit_core.core.stream_manager import StreamManager, StreamData, StreamType, StreamSource, StreamAction
from iotsploit_django.adapters.django.device_driver_manager_factory import get_device_driver_manager
import time
from iotsploit_core.core.device_spec import DeviceState
from collections import deque
import threading

logger = logging.getLogger(__name__)

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
    instances = {}  # Deprecated: use channel layers for cross-process messaging

    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f"exploit_task_{self.task_id}"
        
        # Join channel group for cross-process messaging from Celery worker
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        
        logger.info(f"WebSocket connected for task: {self.task_id}")
        await self.accept()
        
        self.is_polling = True
        asyncio.create_task(self.poll_task_status())

    async def disconnect(self, close_code):
        # Leave the channel group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"WebSocket disconnected for task: {self.task_id}")
        self.is_polling = False

    async def task_update(self, event):
        """Handle task_update messages from Celery worker via channel_layer.group_send()."""
        await self.send(text_data=json.dumps(event['data']))

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
            result = celery_app.AsyncResult(self.task_id)
            
            if result.ready():
                task_result = result.get()
                await self.send(text_data=json.dumps({
                    'status': 'complete',
                    'result': task_result
                }))
                self.is_polling = False
            else:
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
            self.is_polling = False

    async def poll_task_status(self):
        while self.is_polling:
            await self.send_task_status()
            await asyncio.sleep(1)

class PluginExecutionConsumer(AsyncWebsocketConsumer):
    """Live events for one plugin execution, keyed on its own id.

    Unlike the older exploit socket this does not poll Celery: the worker emits
    what happens, and a client that misses something refetches
    `/api/plugin-executions/<id>/`. On connect it replays the current state so a
    reload or a reconnect lands on the open prompt rather than an empty screen.
    """

    async def connect(self):
        self.execution_id = self.scope["url_route"]["kwargs"]["execution_id"]
        self.group_name = f"plugin_execution_{self.execution_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("WebSocket connected for execution: %s", self.execution_id)

        state = await self._state()
        if state is not None:
            await self.send(text_data=json.dumps({
                "execution_id": str(self.execution_id),
                "event": "state",
                "payload": state,
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info("WebSocket disconnected for execution: %s", self.execution_id)

    async def execution_event(self, event):
        """Forward one event emitted by the worker."""
        await self.send(text_data=json.dumps(event["message"]))

    async def receive(self, text_data):
        """Answering and cancelling go over authenticated HTTP, not this socket.

        Only a state refresh is accepted here, so there is one audited path for
        anything that changes a run.
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get("action") == "get_state":
            state = await self._state()
            await self.send(text_data=json.dumps({
                "execution_id": str(self.execution_id),
                "event": "state",
                "payload": state or {},
            }))

    @database_sync_to_async
    def _state(self):
        from iotsploit_django.view_handlers.interaction_views import execution_state
        return execution_state(self.execution_id)


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
        
        self.stream_manager = StreamManager()
        await self.stream_manager.register_stream(self.channel)
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.debug(f"Stream connection closed for channel: {self.channel}, channel_name: {self.channel_name}")
        
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

            device_manager = get_device_driver_manager()
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

            if stream_data.stream_type == StreamType.UART and stream_data.action == StreamAction.SEND:
                try:
                    uart_channel = stream_data.metadata.get('channel', 'A')
                    hex_data = stream_data.data.get('data')
                    if not hex_data:
                        raise ValueError("No data provided for UART transmission")
                    
                    data = bytes.fromhex(hex_data)
                    driver.send_uart_data(driver.device, uart_channel, data)
                    
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

            elif stream_data.stream_type == StreamType.CAN and stream_data.action == StreamAction.SEND:
                try:
                    can_id = int(stream_data.data['id'], 16)
                    can_data = bytes.fromhex(stream_data.data['data'])
                    # The client already states these; dropping them sent every
                    # frame as standard classic CAN regardless of what was asked.
                    metadata = stream_data.metadata or {}

                    driver.send_can_message(
                        driver.device,
                        can_id,
                        can_data,
                        is_extended_id=bool(metadata.get('is_extended_id', False)),
                        is_fd=bool(metadata.get('is_fd', False)),
                    )
                    
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
                stream_type=StreamType.CAN,
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
                stream_type=StreamType.CAN,
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
        
        self.group_name = "console_logs"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        try:
            with log_buffer_lock:
                existing_logs = list(console_log_buffer)
            
            if existing_logs:
                for log in existing_logs[-50:]:
                    await self.send(text_data=log)
            
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Connected to console log stream'
            }))
            
        except Exception as e:
            logger.error(f"Error sending existing logs: {e}")
    
    async def disconnect(self, close_code):
        """Disconnect from the WebSocket and leave the logs group"""
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def console_log(self, event):
        """Send a console log message to the WebSocket"""
        try:
            message = event['message']
            await self.send(text_data=message)
        except Exception as e:
            logger.error(f"Error sending console log: {e}")


class IoTFuzzerTestingConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for IoT Fuzzer testing page real-time updates"""
    
    async def connect(self):
        """Connect to the WebSocket and join the fuzzer group"""
        self.campaign_id = self.scope['url_route']['kwargs'].get('campaign_id')
        
        self.general_group = "iot_fuzzer_general"
        await self.channel_layer.group_add(
            self.general_group,
            self.channel_name
        )
        
        if self.campaign_id:
            self.campaign_group = f"iot_fuzzer_campaign_{self.campaign_id}"
            await self.channel_layer.group_add(
                self.campaign_group,
                self.channel_name
            )
        
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to IoT Fuzzer testing stream',
            'campaign_id': self.campaign_id
        }))
        
        if self.campaign_id:
            await self.send_initial_status()
    
    async def disconnect(self, close_code):
        """Disconnect from the WebSocket and leave the fuzzer groups"""
        await self.channel_layer.group_discard(
            self.general_group,
            self.channel_name
        )
        
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
            # Normalize statistics payload to AFL++ fixed schema before forwarding
            try:
                if event.get('event_type') == 'statistics_update' and isinstance(event.get('data'), dict):
                    data = event['data']
                    stats = data.get('statistics')
                    if not isinstance(stats, dict):
                        stats = {}

                    ui_stats = {
                        'execs_done': int(stats.get('execs_done', 0)),
                        'execs_per_sec': float(stats.get('execs_per_sec', 0.0)),
                        'execs_ps_last_min': float(stats.get('execs_ps_last_min', 0.0)),
                        'cycles_done': int(stats.get('cycles_done', 0)),
                        'cycles_wo_finds': int(stats.get('cycles_wo_finds', 0)),
                        'time_wo_finds': int(stats.get('time_wo_finds', 0)),
                        'corpus_count': int(stats.get('corpus_count', 0)),
                        'corpus_favored': int(stats.get('corpus_favored', 0)),
                        'corpus_found': int(stats.get('corpus_found', 0)),
                        'pending_total': int(stats.get('pending_total', 0)),
                        'pending_favs': int(stats.get('pending_favs', 0)),
                        'bitmap_cvg': float(stats.get('bitmap_cvg', 0.0)),
                        'stability': float(stats.get('stability', 0.0)),
                        'saved_crashes': int(stats.get('saved_crashes', 0)),
                        'saved_hangs': int(stats.get('saved_hangs', 0)),
                        'total_tmout': int(stats.get('total_tmout', 0)),
                        'run_time': int(stats.get('run_time', 0)),
                        'fuzz_time': int(stats.get('fuzz_time', 0)),
                        'last_update': int(stats.get('last_update', 0)),
                    }

                    missing = [k for k in ui_stats.keys() if k not in stats]
                    if missing:
                        logger.warning(f"[WS.normalize] Missing keys: {missing}")

                    data['statistics'] = ui_stats
            except Exception as e:
                logger.error(f"Error normalizing fuzzer_event statistics: {e}")

            await self.send(text_data=json.dumps(event))
        except Exception as e:
            logger.error(f"Error sending fuzzer event: {str(e)}")
    
    async def send_initial_status(self):
        """Send initial campaign status"""
        try:
            if self.campaign_id:
                from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
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
                from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
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
                from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
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
            await self.send(text_data=json.dumps({
                'type': 'logs_response',
                'campaign_id': campaign_id,
                'logs': []
            }))
        except Exception as e:
            logger.error(f"Error sending recent logs: {str(e)}")
    
    async def send_filtered_logs(self, filter_criteria):
        """Send filtered logs based on criteria"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'filtered_logs_response',
                'filter_criteria': filter_criteria,
                'logs': []
            }))
        except Exception as e:
            logger.error(f"Error sending filtered logs: {str(e)}")
    
    async def subscribe_to_logs(self, campaign_id):
        """Subscribe to logs for a specific campaign"""
        try:
            if campaign_id:
                await self.send(text_data=json.dumps({
                    'type': 'log_subscription_confirmed',
                    'campaign_id': campaign_id
                }))
        except Exception as e:
            logger.error(f"Error subscribing to logs: {str(e)}")
