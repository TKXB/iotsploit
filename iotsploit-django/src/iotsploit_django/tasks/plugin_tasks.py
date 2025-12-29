from __future__ import annotations

from celery import shared_task
from celery.utils.log import get_task_logger

from sat_toolkit.adapters.django.target_models import TargetManager
import asyncio

from iotsploit_django.composition_root.wiring import get_exploit_plugin_manager


logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def execute_plugin_task(self, plugin_name, target=None, parameters=None):
    try:
        # Celery worker runs the plugin in-process; do not enqueue another Celery task.
        plugin_manager = get_exploit_plugin_manager(use_celery=False)

        if target and isinstance(target, dict):
            target_manager = TargetManager.get_instance()
            target = target_manager.create_target_instance(target)

        plugin_instance = plugin_manager.get_plugin(plugin_name)

        raw_result = plugin_instance.execute_async(target, parameters)

        if asyncio.iscoroutine(raw_result):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            raw_result = loop.run_until_complete(raw_result)

        result = {
            "status": "success",
            "message": str(raw_result.message) if hasattr(raw_result, "message") else "Completed",
            "data": raw_result.data if hasattr(raw_result, "data") else None,
            "progress": raw_result.progress if hasattr(raw_result, "progress") else 100,
        }

        send_task_status(self.request.id, result)
        return result

    except Exception as e:
        error_result = {"status": "error", "message": str(e), "data": None}
        logger.error(f"Task failed: {str(e)}", exc_info=True)
        send_task_status(self.request.id, error_result)
        return error_result


def send_task_status(task_id, data):
    """Helper function to send task status updates to WebSocket clients"""
    try:
        from iotsploit_django.websocket.consumers import ExploitWebsocketConsumer

        for consumer in ExploitWebsocketConsumer.instances.get(task_id, []):
            consumer.send_update(data)
    except Exception as e:
        logger.error(f"Error sending task status: {str(e)}")


