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
        
        # Execute the plugin
        raw_result = plugin_manager.execute_plugin(plugin_name, target, parameters)
        
        result = {
            'status': 'success',
            'message': str(raw_result.message) if hasattr(raw_result, 'message') else 'Completed',
            'data': raw_result.data if hasattr(raw_result, 'data') else None
        }
        return result

    except Exception as e:
        error_result = {
            'status': 'error',
            'message': str(e),
            'data': None
        }
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