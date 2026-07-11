from __future__ import annotations

from celery import shared_task
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from iotsploit_django.adapters.django.target_models import TargetManager
import asyncio

from iotsploit_django.composition_root.wiring import get_exploit_plugin_manager


logger = get_task_logger(__name__)


def _inject_context_in_worker(plugin_instance):
    """
    Inject backend context into plugin in Celery worker process.
    
    Since Celery worker is a separate process, we need to build the context
    here. Configuration is automatically read from environment variables by
    iotsploit_platforms.selector.build_context().
    """
    # Skip if already injected
    if getattr(plugin_instance, "_iots_ctx_injected", False):
        return
    
    try:
        from iotsploit_platforms.selector import build_context
        
        # build_context() reads all backend config from env vars automatically
        ctx = build_context()
        
        # Inject into plugin
        if hasattr(plugin_instance, "initialize"):
            # Never call initialize(None). Prefer initialize(ctx), fallback to initialize().
            try:
                plugin_instance.initialize(ctx)
            except TypeError:
                try:
                    plugin_instance.initialize()
                except TypeError:
                    logger.warning(
                        f"Plugin {plugin_instance.__class__.__name__} initialize() "
                        "signature mismatch, skipping initialization"
                    )
        
        plugin_instance._iots_ctx_injected = True
        logger.debug("Injected backend context into plugin in Celery worker")
        
    except Exception as e:
        logger.warning(
            f"Failed to inject backend context in Celery worker: {e}. "
            "Plugin may not have backend access."
        )


@shared_task(bind=True, max_retries=3)
def execute_plugin_task(self, plugin_name, target=None, parameters=None):
    try:
        # Celery worker runs the plugin in-process; do not enqueue another Celery task.
        plugin_manager = get_exploit_plugin_manager(use_celery=False)

        if target and isinstance(target, dict):
            target_manager = TargetManager.get_instance()
            target = target_manager.create_target_instance(target)

        plugin_instance = plugin_manager.get_plugin(plugin_name)
        
        # Inject backend context in worker process
        # (backends cannot be serialized across processes, must rebuild here)
        _inject_context_in_worker(plugin_instance)

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
    """Send task status updates to WebSocket clients via Channel Layers.
    
    Works across processes (Celery worker -> Django ASGI) using Redis-backed
    channel layers instead of in-memory consumer instances.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f"exploit_task_{task_id}"
            async_to_sync(channel_layer.group_send)(group_name, {
                'type': 'task_update',
                'data': data
            })
    except Exception as e:
        logger.error(f"Error sending task status: {str(e)}")


