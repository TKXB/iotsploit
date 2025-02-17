from celery import shared_task
from celery.utils.log import get_task_logger
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from sat_toolkit.models.Target_Model import TargetManager
import asyncio
import json

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3)
def execute_plugin_task(self, plugin_name, target=None, parameters=None):
    try:
        plugin_manager = ExploitPluginManager()
        
        # Convert target dictionary back to Vehicle object if it exists
        if target and isinstance(target, dict):
            target_manager = TargetManager.get_instance()
            target = target_manager.create_target_instance(target)
        
        # Get plugin instance and execute
        plugin_instance = plugin_manager.get_plugin(plugin_name)
        
        # Execute the plugin
        raw_result = plugin_instance.execute_async(target, parameters)
        
        # Handle both async and sync results
        if asyncio.iscoroutine(raw_result):
            # Create event loop for async execution
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            raw_result = loop.run_until_complete(raw_result)
        
        # Format the result
        result = {
            'status': 'success',
            'message': str(raw_result.message) if hasattr(raw_result, 'message') else 'Completed',
            'data': raw_result.data if hasattr(raw_result, 'data') else None,
            'progress': raw_result.progress if hasattr(raw_result, 'progress') else 100
        }
        
        # Send status update through WebSocket
        send_task_status(self.request.id, result)
        return result

    except Exception as e:
        error_result = {
            'status': 'error',
            'message': str(e),
            'data': None
        }
        logger.error(f"Task failed: {str(e)}", exc_info=True)
        # Send error status through WebSocket
        send_task_status(self.request.id, error_result)
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