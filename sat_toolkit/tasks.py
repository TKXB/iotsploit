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
import os
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
        
        # Add campaign_id to config for event emission
        campaign_config_with_id = campaign_config.copy()
        campaign_config_with_id['campaign_id'] = campaign_id
        
        orchestrator_adapter = protocol_adapter.create_orchestrator_adapter(campaign_config_with_id)
        monitor_adapter = protocol_adapter.create_monitor_adapter(campaign_config_with_id, orchestrator_adapter)
        
        # Store adapters in this worker process
        fuzzer_manager.orchestrator_adapters[campaign_id] = orchestrator_adapter
        fuzzer_manager.monitor_adapters[campaign_id] = monitor_adapter
        
        # Start the actual fuzzing process
        orchestrator_adapter.start()
        
        # Update campaign to running status in Redis
        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': 'running'
        })
        
        # Main fuzzing loop - monitor progress and report on execs_done threshold
        REPORT_THRESHOLD_EXECS = int(os.getenv('FUZZER_REPORT_THRESHOLD_EXECS', 50))
        logger.info(
            "[Celery.run_fuzzing_campaign] campaign=%s threshold_execs=%d",
            campaign_id,
            REPORT_THRESHOLD_EXECS,
        )
        execs_done = 0
        last_reported_execs = 0
        printed_monitor_raw = False

        while getattr(orchestrator_adapter, 'is_running', False):
            # Get current campaign state from Redis to check for status changes
            current_state = fuzzer_manager._get_campaign_state(campaign_id)
            if not current_state or current_state.get('status') != 'running':
                logger.info(f"Campaign {campaign_id} status changed to {current_state.get('status') if current_state else 'not found'}, stopping")
                orchestrator_adapter.stop()
                break

            # Get detailed statistics (AFL++ keys)
            detail = monitor_adapter.get_statistics() or {}
            if not printed_monitor_raw:
                logger.info(
                    "[Celery.monitor.raw] campaign=%s stats=%s keys=%s",
                    campaign_id,
                    detail,
                    list(detail.keys()),
                )
                printed_monitor_raw = True
            current_execs = int(detail.get('execs_done', 0) or 0)
            if current_execs > execs_done:
                logger.info(
                    "[Celery.stats] execs_done advanced: %d -> %d (eps=%.2f, cycles=%d, crashes=%d, tmout=%d)",
                    execs_done,
                    current_execs,
                    float(detail.get('execs_per_sec', 0.0) or 0.0),
                    int(detail.get('cycles_done', 0) or 0),
                    int(detail.get('saved_crashes', 0) or 0),
                    int(detail.get('total_tmout', 0) or 0),
                )
                execs_done = current_execs

            # Update Redis + push when threshold reached
            if execs_done - last_reported_execs >= REPORT_THRESHOLD_EXECS:
                updates = {
                    'execs_done': execs_done,
                    'execs_per_sec': float(detail.get('execs_per_sec', 0.0) or 0.0),
                    'cycles_done': int(detail.get('cycles_done', 0) or 0),
                    'corpus_count': int(detail.get('corpus_count', 0) or 0),
                    'corpus_favored': int(detail.get('corpus_favored', 0) or 0),
                    'corpus_found': int(detail.get('corpus_found', 0) or 0),
                    'pending_total': int(detail.get('pending_total', 0) or 0),
                    'pending_favs': int(detail.get('pending_favs', 0) or 0),
                    'bitmap_cvg': float(detail.get('bitmap_cvg', 0.0) or 0.0),
                    'saved_crashes': int(detail.get('saved_crashes', 0) or 0),
                    'saved_hangs': int(detail.get('saved_hangs', 0) or 0),
                    'total_tmout': int(detail.get('total_tmout', 0) or 0),
                    'run_time': int(detail.get('run_time', 0) or 0),
                    'last_update': int(time.time()),
                }
                logger.info(
                    "[Celery.threshold] campaign=%s report execs_done %d (+%d): eps=%.2f cycles=%d crashes=%d tmout=%d",
                    campaign_id,
                    execs_done,
                    execs_done - last_reported_execs,
                    updates['execs_per_sec'],
                    updates['cycles_done'],
                    updates['saved_crashes'],
                    updates['total_tmout'],
                )
                fuzzer_manager._update_campaign_state(campaign_id, updates)

                # WebSocket: send statistics_update with nested statistics payload
                send_campaign_statistics_update(campaign_id, updates)

                last_reported_execs = execs_done

            # pacing
            time.sleep(0.1)
        
        # Ensure orchestrator is stopped
        orchestrator_adapter.stop()
        logger.info("[Celery.run_fuzzing_campaign] campaign=%s stopped", campaign_id)

        # Update final state in Redis
        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': 'stopped',
            'completed_at': datetime.now().isoformat(),
            'last_update': int(time.time())
        })
        
        # Get final state for response
        final_state = fuzzer_manager._get_campaign_state(campaign_id)
        
        # Send final status update
        send_campaign_status_update(campaign_id, final_state)
        
        logger.info(f"Fuzzing campaign task completed: {campaign_id}")
        
        return {
            'status': 'success',
            'campaign_id': campaign_id,
            'final_status': 'stopped'
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


def send_campaign_statistics_update(campaign_id, statistics_data):
    """Helper function to send campaign statistics updates (AFL++ keys)"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f"iot_fuzzer_campaign_{campaign_id}"
            message = {
                'type': 'fuzzer_event',
                'event_type': 'statistics_update',
                'data': {
                    'campaign_id': campaign_id,
                    'statistics': statistics_data
                }
            }

            async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending campaign statistics update: {str(e)}")


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