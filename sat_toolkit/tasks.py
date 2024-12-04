from celery import shared_task
from celery.utils.log import get_task_logger
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import asyncio
import json

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3)
def execute_plugin_task(self, plugin_name, target=None, parameters=None):
    try:
        # Get the WebSocket consumer for this task
        plugin_manager = ExploitPluginManager()
        
        # Send initial status
        send_task_status(self.request.id, {
            'status': 'started',
            'message': f'Starting execution of plugin {plugin_name}'
        })

        # Run the async function in an event loop
        raw_result = asyncio.run(plugin_manager.execute_plugin_async(plugin_name, target, parameters))
        
        result = {
            'status': 'success',
            'message': str(raw_result.message) if hasattr(raw_result, 'message') else 'Completed',
            'data': raw_result.data if hasattr(raw_result, 'data') else None
        }

        # Send final status
        send_task_status(self.request.id, result)
        return result

    except Exception as e:
        error_result = {
            'status': 'error',
            'message': str(e),
            'data': None
        }
        # Send error status
        send_task_status(self.request.id, error_result)
        logger.error(f"Task failed: {str(e)}", exc_info=True)
        return error_result

def send_task_status(task_id, data):
    """Helper function to send task status updates to WebSocket clients"""
    try:
        # Import here to avoid circular imports
        from sat_toolkit.consumers import ExploitWebsocketConsumer
        
        # Find all WebSocket consumers for this task
        for consumer in ExploitWebsocketConsumer.instances.get(task_id, []):
            consumer.send_update(data)
    except Exception as e:
        logger.error(f"Error sending task status: {str(e)}")