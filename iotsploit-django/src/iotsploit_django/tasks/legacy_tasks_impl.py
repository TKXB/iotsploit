from celery import shared_task
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from iotsploit_django.adapters.django.target_models import TargetManager
import asyncio
import time
import os
from datetime import datetime
from iotsploit_django.adapters.django.exploit_manager_factory import get_exploit_plugin_manager

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
            'status': 'success',
            'message': str(raw_result.message) if hasattr(raw_result, 'message') else 'Completed',
            'data': raw_result.data if hasattr(raw_result, 'data') else None,
            'progress': raw_result.progress if hasattr(raw_result, 'progress') else 100
        }
        
        send_task_status(self.request.id, result)
        return result

    except Exception as e:
        error_result = {
            'status': 'error',
            'message': str(e),
            'data': None
        }
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
        
        from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
        fuzzer_manager = IoTFuzzerManager.get_instance()
        
        campaign_state = fuzzer_manager._get_campaign_state(campaign_id)
        if not campaign_state:
            raise Exception(f"Campaign {campaign_id} not found in Redis")
        
        protocol_adapter = fuzzer_manager._get_protocol_adapter()
        
        campaign_config_with_id = campaign_config.copy()
        campaign_config_with_id['campaign_id'] = campaign_id
        
        orchestrator_adapter = protocol_adapter.create_orchestrator_adapter(campaign_config_with_id)
        monitor_adapter = protocol_adapter.create_monitor_adapter(campaign_config_with_id, orchestrator_adapter)
        
        fuzzer_manager.orchestrator_adapters[campaign_id] = orchestrator_adapter
        fuzzer_manager.monitor_adapters[campaign_id] = monitor_adapter
        
        orchestrator_adapter.start()
        
        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': 'running'
        })
        
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
            current_state = fuzzer_manager._get_campaign_state(campaign_id)
            if not current_state or current_state.get('status') != 'running':
                logger.info(f"Campaign {campaign_id} status changed to {current_state.get('status') if current_state else 'not found'}, stopping")
                orchestrator_adapter.stop()
                break

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

                send_campaign_statistics_update(campaign_id, updates)

                last_reported_execs = execs_done

            time.sleep(0.1)
        
        orchestrator_adapter.stop()
        logger.info("[Celery.run_fuzzing_campaign] campaign=%s stopped", campaign_id)

        fuzzer_manager._update_campaign_state(campaign_id, {
            'status': 'stopped',
            'completed_at': datetime.now().isoformat(),
            'last_update': int(time.time())
        })
        
        final_state = fuzzer_manager._get_campaign_state(campaign_id)
        
        send_campaign_status_update(campaign_id, final_state)
        
        logger.info(f"Fuzzing campaign task completed: {campaign_id}")
        
        return {
            'status': 'success',
            'campaign_id': campaign_id,
            'final_status': 'stopped'
        }
        
    except Exception as e:
        logger.error(f"Error in fuzzing campaign task: {str(e)}")
        
        try:
            from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
            fuzzer_manager = IoTFuzzerManager.get_instance()
            
            fuzzer_manager._update_campaign_state(campaign_id, {
                'status': 'failed',
                'error_message': str(e),
                'failed_at': datetime.now().isoformat()
            })
            
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
        
        processed_results = []
        
        for result in results_data:
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
        
        from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
        fuzzer_manager = IoTFuzzerManager.get_instance()
        
        statistics = fuzzer_manager.get_campaign_statistics(campaign_id)
        
        report = {
            'campaign_id': campaign_id,
            'generated_at': time.time(),
            'statistics': statistics,
            'report_format': report_config.get('format', 'json'),
            'report_sections': report_config.get('sections', ['summary', 'statistics', 'crashes'])
        }
        
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