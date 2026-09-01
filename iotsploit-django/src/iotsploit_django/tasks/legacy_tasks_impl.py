from celery import shared_task
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
import time

from iotsploit_django.adapters.django.threadsafe_channel_layer import send_group

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3)
def run_fuzzing_campaign(self, campaign_id, campaign_config):
    """Celery wrapper around the runtime-neutral campaign owner."""
    from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager

    return IoTFuzzerManager.get_instance().run_campaign(campaign_id, campaign_config)


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
            
            send_group(channel_layer, group_name, message)
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
            
            send_group(channel_layer, group_name, message)
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

            send_group(channel_layer, group_name, message)
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
            
            send_group(channel_layer, group_name, message)
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
            
            send_group(channel_layer, group_name, message)
    except Exception as e:
        logger.error(f"Error sending report ready notification: {str(e)}")
