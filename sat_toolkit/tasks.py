from celery import shared_task
from celery.utils.log import get_task_logger
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from sat_toolkit.models.Target_Model import TargetManager
# from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager  # Import locally to avoid circular imports
import asyncio
import json
import time
from datetime import datetime

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


@shared_task(bind=True, max_retries=3)
def run_fuzzing_campaign(self, campaign_id, campaign_config):
    """
    Background task for running an IoT fuzzing campaign
    Uses Redis for cross-process state sharing
    
    Args:
        campaign_id: Campaign ID
        campaign_config: Campaign configuration
    """
    try:
        logger.info(f"Starting fuzzing campaign task: {campaign_id}")
        
        # Get fuzzer manager instance
        from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
        fuzzer_manager = IoTFuzzerManager.get_instance()
        
        # Get campaign state from Redis
        campaign_state = fuzzer_manager._get_campaign_state(campaign_id)
        if not campaign_state:
            raise Exception(f"Campaign {campaign_id} not found in Redis")
        
        # Create/initialize adapters for this worker process
        protocol_adapter = fuzzer_manager._get_protocol_adapter()
        orchestrator_adapter = protocol_adapter.create_orchestrator_adapter(campaign_config)
        monitor_adapter = protocol_adapter.create_monitor_adapter(campaign_config, orchestrator_adapter)
        
        # Store adapters in this worker process
        fuzzer_manager.orchestrator_adapters[campaign_id] = orchestrator_adapter
        fuzzer_manager.monitor_adapters[campaign_id] = monitor_adapter
        
        # Start the actual fuzzing process
        orchestrator_adapter.start()
        
        # Update campaign to running status in Redis
        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': 'running'
        })
        
        # Main fuzzing loop - monitor the real fuzzer progress
        iterations_total = campaign_config.get('iterations_total', 1000)
        iterations_completed = 0
        last_reported_iterations = 0
        
        while orchestrator_adapter.is_running and iterations_completed < iterations_total:
            # Get current campaign state from Redis to check for status changes
            current_state = fuzzer_manager._get_campaign_state(campaign_id)
            if not current_state or current_state.get('status') != 'running':
                logger.info(f"Campaign {campaign_id} status changed to {current_state.get('status') if current_state else 'not found'}, stopping")
                orchestrator_adapter.stop()
                break
            
            # Get real fuzzer progress from monitor
            monitor_stats = monitor_adapter.get_status()
            current_iterations = monitor_stats.get('current_iteration', 0)
            
            # Use the real fuzzer's progress
            if current_iterations > iterations_completed:
                iterations_completed = current_iterations
            
            # Update Redis state if progress changed significantly
            if iterations_completed - last_reported_iterations >= 10:
                fuzzer_manager._update_campaign_state(campaign_id, {
                    'iterations_completed': iterations_completed
                })
                
                send_campaign_progress_update(campaign_id, {
                    'iterations_completed': iterations_completed,
                    'iterations_total': iterations_total,
                    'progress_percentage': (iterations_completed / iterations_total) * 100
                })
                
                last_reported_iterations = iterations_completed
            
            # Check every 100ms
            time.sleep(0.1)
        
        # Ensure orchestrator is stopped
        orchestrator_adapter.stop()
        
        # Update final state in Redis
        final_status = 'completed' if iterations_completed >= iterations_total else 'stopped'
        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': final_status,
            'completed_at': datetime.now().isoformat(),
            'iterations_completed': iterations_completed
        })
        
        # Get final state for response
        final_state = fuzzer_manager._get_campaign_state(campaign_id)
        
        # Send final status update
        send_campaign_status_update(campaign_id, final_state)
        
        logger.info(f"Fuzzing campaign task completed: {campaign_id}")
        
        return {
            'status': 'success',
            'campaign_id': campaign_id,
            'iterations_completed': iterations_completed,
            'final_status': final_status
        }
        
    except Exception as e:
        logger.error(f"Error in fuzzing campaign task: {str(e)}")
        
        # Update campaign state on error in Redis
        try:
            from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
            fuzzer_manager = IoTFuzzerManager.get_instance()
            
            fuzzer_manager._update_campaign_state(campaign_id, {
                'status': 'failed',
                'error_message': str(e),
                'failed_at': datetime.now().isoformat()
            })
            
            # Get error state for WebSocket update
            error_state = fuzzer_manager._get_campaign_state(campaign_id)
            send_campaign_status_update(campaign_id, error_state)
            
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {str(cleanup_error)}")
        
        return {
            'status': 'error',
            'campaign_id': campaign_id,
            'error_message': str(e)
        }


@shared_task(bind=True)
def process_fuzzing_results(self, campaign_id, results_data):
    """
    Background task for processing fuzzing results
    
    Args:
        campaign_id: Campaign ID
        results_data: Results data to process
    """
    try:
        logger.info(f"Processing fuzzing results for campaign: {campaign_id}")
        
        # Process the results (e.g., save to database, analyze crashes, etc.)
        processed_results = []
        
        for result in results_data:
            # Process each result
            processed_result = {
                'campaign_id': campaign_id,
                'test_case_id': result.get('test_case_id'),
                'status': result.get('status'),
                'payload': result.get('payload'),
                'response': result.get('response'),
                'crashed': result.get('crashed', False),
                'processed_at': time.time()
            }
            
            processed_results.append(processed_result)
        
        # Send results update
        send_results_update(campaign_id, processed_results)
        
        logger.info(f"Processed {len(processed_results)} results for campaign {campaign_id}")
        
        return {
            'status': 'success',
            'campaign_id': campaign_id,
            'processed_count': len(processed_results)
        }
        
    except Exception as e:
        logger.error(f"Error processing fuzzing results: {str(e)}")
        return {
            'status': 'error',
            'campaign_id': campaign_id,
            'error_message': str(e)
        }


@shared_task(bind=True)
def generate_fuzzing_report(self, campaign_id, report_config):
    """
    Background task for generating fuzzing reports
    
    Args:
        campaign_id: Campaign ID
        report_config: Report configuration
    """
    try:
        logger.info(f"Generating fuzzing report for campaign: {campaign_id}")
        
        # Get fuzzer manager instance
        from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
        fuzzer_manager = IoTFuzzerManager.get_instance()
        
        # Get campaign statistics
        statistics = fuzzer_manager.get_campaign_statistics(campaign_id)
        
        # Generate report
        report = {
            'campaign_id': campaign_id,
            'generated_at': time.time(),
            'statistics': statistics,
            'report_format': report_config.get('format', 'json'),
            'report_sections': report_config.get('sections', ['summary', 'statistics', 'crashes'])
        }
        
        # Send report ready notification
        send_report_ready_notification(campaign_id, report)
        
        logger.info(f"Report generated for campaign {campaign_id}")
        
        return {
            'status': 'success',
            'campaign_id': campaign_id,
            'report': report
        }
        
    except Exception as e:
        logger.error(f"Error generating fuzzing report: {str(e)}")
        return {
            'status': 'error',
            'campaign_id': campaign_id,
            'error_message': str(e)
        }


def send_campaign_progress_update(campaign_id, progress_data):
    """Helper function to send campaign progress updates"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to campaign-specific group
            group_name = f"iot_fuzzer_campaign_{campaign_id}"
            message = {
                'type': 'fuzzer_event',
                'event_type': 'campaign_progress',
                'data': {
                    'campaign_id': campaign_id,
                    **progress_data
                }
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending campaign progress update: {str(e)}")


def send_campaign_status_update(campaign_id, status_data):
    """Helper function to send campaign status updates"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to campaign-specific group
            group_name = f"iot_fuzzer_campaign_{campaign_id}"
            message = {
                'type': 'fuzzer_event',
                'event_type': 'campaign_status',
                'data': {
                    'campaign_id': campaign_id,
                    'status': status_data
                }
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending campaign status update: {str(e)}")


def send_results_update(campaign_id, results_data):
    """Helper function to send results updates"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to campaign-specific group
            group_name = f"iot_fuzzer_campaign_{campaign_id}"
            message = {
                'type': 'fuzzer_event',
                'event_type': 'results_update',
                'data': {
                    'campaign_id': campaign_id,
                    'results': results_data
                }
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending results update: {str(e)}")


def send_report_ready_notification(campaign_id, report_data):
    """Helper function to send report ready notifications"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to campaign-specific group
            group_name = f"iot_fuzzer_campaign_{campaign_id}"
            message = {
                'type': 'fuzzer_event',
                'event_type': 'report_ready',
                'data': {
                    'campaign_id': campaign_id,
                    'report': report_data
                }
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending report ready notification: {str(e)}")