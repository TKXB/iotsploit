import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from sat_toolkit.tools.monitor_mgr import SystemMonitor
import asyncio
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from celery.result import AsyncResult
import redis
from django.conf import settings
from sat_toolkit.core.stream_manager import StreamManager

logger = logging.getLogger(__name__)

class SystemUsageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("WebSocket connection attempt received")
        await self.accept()
        logger.info("WebSocket connection accepted")
        self.monitor = SystemMonitor.create_monitor("linux")
        self.monitor.start_monitoring()
        asyncio.create_task(self.send_system_usage())

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected with code: {close_code}")
        self.monitor.stop_monitoring()

    async def send_system_usage(self):
        while True:
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
        
        # Fetch initial task status
        await self.send_task_status()

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected for task: {self.task_id}")

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

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.debug(f"Stream connection closed for channel: {self.channel}, channel_name: {self.channel_name}")

    async def stream_data(self, event):
        """Handle incoming stream data and forward it to the WebSocket"""
        logger.debug(f"Received stream data for channel {self.channel}, channel_name: {self.channel_name}: {event['data']}")
        await self.send(text_data=json.dumps(event['data']))
