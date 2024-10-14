import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from sat_toolkit.tools.monitor_mgr import SystemMonitor
import asyncio

logger = logging.getLogger(__name__)

class CPUUsageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("WebSocket connection attempt received")
        await self.accept()
        logger.info("WebSocket connection accepted")
        self.monitor = SystemMonitor.create_monitor("linux")
        self.monitor.start_cpu_monitoring()
        asyncio.create_task(self.send_cpu_usage())

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected with code: {close_code}")
        self.monitor.stop_cpu_monitoring()

    async def send_cpu_usage(self):
        while True:
            try:
                cpu_usage = self.monitor.get_cpu_usage()
                await self.send(text_data=json.dumps({
                    'cpu_usage': cpu_usage
                }))
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in send_cpu_usage: {str(e)}")
                break
