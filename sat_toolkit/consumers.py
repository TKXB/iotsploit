import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from sat_toolkit.tools.monitor_mgr import SystemMonitor
import asyncio
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

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

class ExploitWebsocketConsumer(WebsocketConsumer):
    instances = {}  # Class variable to track all active consumers

    def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.accept()
        
        # Add this instance to the tracking dict
        if self.task_id not in self.instances:
            self.instances[self.task_id] = set()
        self.instances[self.task_id].add(self)
        
        logger.info(f"WebSocket connected for task: {self.task_id}")

    def disconnect(self, close_code):
        # Remove this instance from tracking
        if self.task_id in self.instances:
            self.instances[self.task_id].discard(self)
            if not self.instances[self.task_id]:
                del self.instances[self.task_id]
        
        logger.info(f"WebSocket disconnected for task: {self.task_id}")

    def receive(self, text_data):
        pass

    def send_update(self, data):
        self.send(text_data=json.dumps(data))
