from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Sum
from django.utils import timezone
import json
import logging
import os
import mimetypes

from iotsploit_django.iot_fuzzer.service import (
    IoTFuzzerService,
)
from iotsploit_django.iot_fuzzer.http import method_not_allowed, parse_json_body

# Import Django models
from iotsploit_django.adapters.django.iot_fuzzer.models import (
    FuzzingCampaign, FuzzingResult, LiveLog
)

logger = logging.getLogger(__name__)

# Campaign Control Endpoints

def get_files_tree(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/files/tree/
    Return file tree structure
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        file_tree = fuzzer_service.get_files_tree(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "file_tree": file_tree
        })
        
    except Exception as e:
        logger.error(f"Error getting files tree: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get files tree: {str(e)}"
        }, status=500)

def get_file_content(request: HttpRequest, file_id):
    """
    GET /api/iot-fuzzer/results/files/content/<id>/
    Return file content
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        fuzzer_service = IoTFuzzerService.get_instance()
        file_content = fuzzer_service.get_file_content(file_id)
        
        return JsonResponse({
            "status": "success",
            "file_content": file_content
        })
        
    except Exception as e:
        logger.error(f"Error getting file content: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get file content: {str(e)}"
        }, status=500)

def download_file(request: HttpRequest, file_id):
    """
    GET /api/iot-fuzzer/results/files/download/<id>/
    Download file
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        fuzzer_service = IoTFuzzerService.get_instance()
        file_path = fuzzer_service.get_file_path(file_id)
        
        if not os.path.exists(file_path):
            return JsonResponse({
                "status": "error",
                "message": "File not found"
            }, status=404)
        
        file_name = os.path.basename(file_path)
        content_type, _ = mimetypes.guess_type(file_path)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type or 'application/octet-stream'
        )
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to download file: {str(e)}"
        }, status=500)

def get_logs_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/logs/list/
    Return test logs with filtering
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        category = request.GET.get('category')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        
        logs = LiveLog.objects.select_related('campaign')
        
        if campaign_id:
            logs = logs.filter(campaign_id=campaign_id)
        if category:
            logs = logs.filter(category=category)
        
        logs = logs.order_by('-timestamp')
        
        paginator = Paginator(logs, page_size)
        page_obj = paginator.get_page(page)
        
        logs_data = []
        for log in page_obj:
            item = {
                'id': log.id,
                'campaign_id': log.campaign.id,
                'campaign_name': log.campaign.name,
                'timestamp': log.timestamp.isoformat(),
                'message': log.message,
                'category': log.category,
                'source': log.source,
                'extra_data': log.extra_data,
                'formatted_timestamp': log.get_formatted_timestamp(),
                'is_error': log.is_error()
            }
            logs_data.append(item)
        
        return JsonResponse({
            "status": "success",
            "logs": logs_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "total_count": paginator.count,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting logs list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get logs list: {str(e)}"
        }, status=500)

@csrf_exempt
def filter_logs(request: HttpRequest):
    """
    POST /api/iot-fuzzer/results/logs/filter/
    Filter logs by criteria
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        filter_criteria = data.get('filter_criteria', {})
        
        logs = LiveLog.objects.select_related('campaign')
        
        # Apply filters
        if 'campaign_id' in filter_criteria:
            logs = logs.filter(campaign_id=filter_criteria['campaign_id'])
        if 'category' in filter_criteria:
            logs = logs.filter(category=filter_criteria['category'])
        if 'source' in filter_criteria:
            logs = logs.filter(source__icontains=filter_criteria['source'])
        if 'message' in filter_criteria:
            logs = logs.filter(message__icontains=filter_criteria['message'])
        if 'date_from' in filter_criteria:
            logs = logs.filter(timestamp__gte=filter_criteria['date_from'])
        if 'date_to' in filter_criteria:
            logs = logs.filter(timestamp__lte=filter_criteria['date_to'])
        
        logs = logs.order_by('-timestamp')
        
        # Pagination
        page = int(filter_criteria.get('page', 1))
        page_size = int(filter_criteria.get('page_size', 50))
        
        paginator = Paginator(logs, page_size)
        page_obj = paginator.get_page(page)
        
        logs_data = []
        for log in page_obj:
            item = {
                'id': log.id,
                'campaign_id': log.campaign.id,
                'campaign_name': log.campaign.name,
                'timestamp': log.timestamp.isoformat(),
                'message': log.message,
                'category': log.category,
                'source': log.source,
                'extra_data': log.extra_data,
                'formatted_timestamp': log.get_formatted_timestamp(),
                'is_error': log.is_error()
            }
            logs_data.append(item)
        
        return JsonResponse({
            "status": "success",
            "logs": logs_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "total_count": paginator.count,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error filtering logs: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to filter logs: {str(e)}"
        }, status=500)

def get_results_summary(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/analysis/summary/
    Return comprehensive result summary
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')

        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)

        # Resolve campaign by numeric id or campaign_uuid
        campaign = None
        try:
            if str(campaign_id).isdigit():
                campaign = FuzzingCampaign.objects.get(id=int(campaign_id))
        except Exception:
            campaign = None

        if campaign is None:
            # Prefer official campaign_uuid field
            try:
                if 'campaign_uuid' in [f.name for f in FuzzingCampaign._meta.fields]:
                    campaign = FuzzingCampaign.objects.filter(campaign_uuid=str(campaign_id)).first()
            except Exception:
                campaign = None

        if campaign is None:
            return JsonResponse({
                "status": "error",
                "message": "Campaign not found"
            }, status=404)

        # Get result statistics
        results = FuzzingResult.objects.filter(campaign=campaign)

        # Compute duration safely without relying on model helpers
        started_at = getattr(campaign, 'started_at', None)
        completed_at = getattr(campaign, 'completed_at', None)
        end_time = completed_at or timezone.now() if started_at else None
        duration_seconds = int((end_time - started_at).total_seconds()) if (started_at and end_time) else 0

        def _format_duration(seconds: int) -> str:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            return f"{h:02d}:{m:02d}:{s:02d}"

        summary = {
            'campaign_info': {
                'id': getattr(campaign, 'id', None),
                'name': getattr(campaign, 'name', ''),
                'status': getattr(campaign, 'status', 'unknown'),
                'protocol_type': getattr(campaign, 'protocol_type', 'unknown'),
                'started_at': started_at.isoformat() if started_at else None,
                'completed_at': completed_at.isoformat() if completed_at else None,
                'duration': _format_duration(duration_seconds),
                'progress_percentage': 0
            },
            'execution_stats': {
                'total_results': results.count(),
                'success_count': results.filter(status='success').count(),
                'crash_count': results.filter(status='crash').count(),
                'timeout_count': results.filter(status='timeout').count(),
                'error_count': results.filter(status='error').count(),
                'anomaly_count': results.filter(status='anomaly').count()
            },
            'performance_stats': {
                'avg_response_time': results.aggregate(avg_time=Avg('response_time_ms'))['avg_time'] or 0,
                'total_payload_size': results.aggregate(total_size=Sum('payload_size'))['total_size'] or 0,
                'crashes_per_hour': 0,
                'test_cases_per_second': 0
            }
        }

        if duration_seconds > 0:
            summary['performance_stats']['crashes_per_hour'] = (
                summary['execution_stats']['crash_count'] / duration_seconds * 3600
            )
            summary['performance_stats']['test_cases_per_second'] = (
                summary['execution_stats']['total_results'] / duration_seconds
            )

        return JsonResponse({
            "status": "success",
            "summary": summary
        })
        
    except FuzzingCampaign.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Campaign not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting results summary: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get results summary: {str(e)}"
        }, status=500)

def get_results_charts(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/analysis/charts/
    Return chart data for visualization
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        chart_type = request.GET.get('chart_type', 'all')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        campaign = FuzzingCampaign.objects.get(id=campaign_id)
        results = FuzzingResult.objects.filter(campaign=campaign)
        
        charts_data = {}
        
        if chart_type in ['all', 'status_distribution']:
            # Status distribution pie chart
            status_counts = results.values('status').annotate(count=Count('status'))
            charts_data['status_distribution'] = {
                'labels': [item['status'] for item in status_counts],
                'data': [item['count'] for item in status_counts]
            }
        
        if chart_type in ['all', 'timeline']:
            # Timeline chart
            timeline_data = results.extra(
                select={'hour': 'strftime("%%Y-%%m-%%d %%H:00:00", executed_at)'}
            ).values('hour').annotate(count=Count('id')).order_by('hour')
            
            charts_data['timeline'] = {
                'labels': [item['hour'] for item in timeline_data],
                'data': [item['count'] for item in timeline_data]
            }
        
        if chart_type in ['all', 'response_time']:
            # Response time distribution
            response_times = results.filter(
                response_time_ms__isnull=False
            ).values_list('response_time_ms', flat=True)
            
            charts_data['response_time'] = {
                'data': list(response_times)
            }
        
        return JsonResponse({
            "status": "success",
            "charts_data": charts_data
        })
        
    except FuzzingCampaign.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Campaign not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting results charts: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get results charts: {str(e)}"
        }, status=500)

@csrf_exempt
def export_results(request: HttpRequest):
    """
    POST /api/iot-fuzzer/results/analysis/export/
    Export results and analysis
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        export_config = data.get('export_config', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        export_result = fuzzer_service.export_results(export_config)
        
        return JsonResponse({
            "status": "success",
            "export_result": export_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error exporting results: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to export results: {str(e)}"
        }, status=500)

def get_artifacts(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/artifacts/
    Return crash artifacts and interesting findings
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        # Get interesting results (crashes, anomalies, etc.)
        results = FuzzingResult.objects.filter(
            campaign_id=campaign_id,
            status__in=['crash', 'anomaly']
        ).select_related('campaign', 'test_case')
        
        artifacts_data = []
        for result in results:
            artifacts_data.append({
                'id': result.id,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'test_case_id': result.test_case.id if result.test_case else None,
                'test_case_name': result.test_case.name if result.test_case else None,
                'iteration_number': result.iteration_number,
                'status': result.status,
                'executed_at': result.executed_at.isoformat(),
                'payload_preview': result.get_payload_preview(),
                'payload_size': result.payload_size,
                'response_time_ms': result.response_time_ms,
                'crashed': result.crashed,
                'crash_info': result.crash_info,
                'artifact_path': result.artifact_path,
                'has_response': result.has_response(),
                'is_interesting': result.is_interesting()
            })
        
        return JsonResponse({
            "status": "success",
            "artifacts": artifacts_data
        })
        
    except Exception as e:
        logger.error(f"Error getting artifacts: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get artifacts: {str(e)}"
        }, status=500)
