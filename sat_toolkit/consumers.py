import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from sat_toolkit.tools.monitor_mgr import SystemMonitor
import asyncio

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
