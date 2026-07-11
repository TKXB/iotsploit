from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest
from django.utils import timezone
import json
import logging

from iotsploit_django.iot_fuzzer.service import (
    IoTFuzzerManager,
)
from iotsploit_django.iot_fuzzer.http import method_not_allowed, parse_json_body

# Import Django models

logger = logging.getLogger(__name__)

# Campaign Control Endpoints

@csrf_exempt
def start_campaign(request: HttpRequest):
    """
    POST /api/iot-fuzzer/testing/campaign/start/
    Start a new fuzzing campaign with provided configuration
    Supports test_group_ids parameter for group-based filtering
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        
        # Ensure data is a dictionary
        if not isinstance(data, dict):
            return JsonResponse({
                "status": "error",
                "message": "Invalid JSON format: expected object"
            }, status=400)
        
        campaign_config = data.get('campaign_config', {})
        
        # Extract and validate test_group_ids if provided
        test_group_ids = campaign_config.get('test_group_ids', [])
        if test_group_ids:
            logger.info(f"Starting campaign with test groups: {test_group_ids}")
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        campaign_id = fuzzer_manager.start_campaign(campaign_config)
        
        # Get enhanced campaign information
        campaign_state = fuzzer_manager._get_campaign_state(campaign_id)
        
        # Prepare enhanced response with strategy statistics
        response_data = {
            "status": "success",
            "campaign_id": campaign_id,
            "message": "Campaign started successfully"
        }

        # Persist runtime UUID into DB if possible
        try:
            from iotsploit_django.adapters.django.iot_fuzzer.models import FuzzingCampaign
            # Find or create a campaign record for this run
            protocol_type = (campaign_config.get('protocol_type') or 'unknown').lower()
            name = campaign_config.get('campaign_name') or f"{protocol_type.upper()} Campaign"
            # Try to attach to an existing idle/default or create new
            db_campaign, _ = FuzzingCampaign.objects.get_or_create(
                name=name,
                defaults={
                    'description': 'Auto-created by start_campaign',
                    'status': 'running',
                    'protocol_type': protocol_type,
                    'protocol_config': campaign_config.get('protocol_config', {}),
                    'generator_config': campaign_config.get('generator_config', {}),
                    'monitoring_config': {},
                    'started_at': timezone.now(),
                }
            )
            # Store UUID
            try:
                if not db_campaign.campaign_uuid:
                    db_campaign.campaign_uuid = str(campaign_id)
                else:
                    # If campaign_uuid already set to another value, replace only when different
                    if db_campaign.campaign_uuid != str(campaign_id):
                        db_campaign.campaign_uuid = str(campaign_id)
                db_campaign.status = 'running'
                if not db_campaign.started_at:
                    db_campaign.started_at = timezone.now()
                db_campaign.save()
                response_data["db_campaign_id"] = db_campaign.id
            except Exception as e:
                logger.warning(f"Unable to persist campaign_uuid: {e}")
        except Exception as e:
            logger.warning(f"start_campaign DB persist skipped: {e}")
        
        # Add strategy statistics if available
        if campaign_state:
            strategy_distribution = campaign_state.get('strategy_distribution', {})
            response_data.update({
                "strategy_statistics": {
                    "bit_level_rules": strategy_distribution.get('bit_level', 0),
                    "field_level_rules": strategy_distribution.get('field_level', 0),
                    "total_rules": strategy_distribution.get('total_rules', 0),
                    "total_test_cases": strategy_distribution.get('total_test_cases', 0)
                },
                "test_groups_processed": len(test_group_ids),
                "fuzzing_engine_available": campaign_state.get('fuzzing_engine_available', False)
            })
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except ValueError as e:
        # Handle validation errors as bad requests
        logger.error(f"Validation error starting campaign: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Validation error: {str(e)}"
        }, status=400)
    except Exception as e:
        logger.error(f"Error starting campaign: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to start campaign: {str(e)}"
        }, status=500)

@csrf_exempt
def stop_campaign(request: HttpRequest):
    """
    POST /api/iot-fuzzer/testing/campaign/stop/
    Stop a running fuzzing campaign
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        campaign_id = data.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        result = fuzzer_manager.stop_campaign(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "result": result,
            "message": "Campaign stopped successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error stopping campaign: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to stop campaign: {str(e)}"
        }, status=500)

@csrf_exempt
def pause_campaign(request: HttpRequest):
    """
    POST /api/iot-fuzzer/testing/campaign/pause/
    Pause a running fuzzing campaign
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        campaign_id = data.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        result = fuzzer_manager.pause_campaign(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "result": result,
            "message": "Campaign paused successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error pausing campaign: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to pause campaign: {str(e)}"
        }, status=500)

@csrf_exempt
def reset_campaign(request: HttpRequest):
    """
    POST /api/iot-fuzzer/testing/campaign/reset/
    Reset a fuzzing campaign state
    """
    if request.method != 'POST':
        return method_not_allowed("POST")
    
    try:
        data = parse_json_body(request)
        campaign_id = data.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        result = fuzzer_manager.reset_campaign(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "result": result,
            "message": "Campaign reset successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error resetting campaign: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to reset campaign: {str(e)}"
        }, status=500)

def get_campaign_status(request: HttpRequest):
    """
    GET /api/iot-fuzzer/testing/campaign/status/
    Get current campaign status and progress
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
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        status = fuzzer_manager.get_campaign_status(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "campaign_status": status
        })
        
    except Exception as e:
        logger.error(f"Error getting campaign status: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get campaign status: {str(e)}"
        }, status=500)

def get_campaign_statistics(request: HttpRequest):
    """
    GET /api/iot-fuzzer/testing/statistics/
    Return AFL++-aligned runtime statistics (fixed key set)
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

        fuzzer_manager = IoTFuzzerManager.get_instance()

        # Prefer Redis state as single source of truth
        state = fuzzer_manager._get_campaign_state(campaign_id) or {}

        # Core AFL++ fields with strict defaults (no fallback chains)
        stats = {
            'execs_done': int(state.get('execs_done', 0)),
            'execs_per_sec': float(state.get('execs_per_sec', 0.0)),
            'execs_ps_last_min': float(state.get('execs_ps_last_min', 0.0)),
            'cycles_done': int(state.get('cycles_done', 0)),
            'cycles_wo_finds': int(state.get('cycles_wo_finds', 0)),
            'time_wo_finds': int(state.get('time_wo_finds', 0)),
            'corpus_count': int(state.get('corpus_count', 0)),
            'corpus_favored': int(state.get('corpus_favored', 0)),
            'corpus_found': int(state.get('corpus_found', 0)),
            'pending_total': int(state.get('pending_total', 0)),
            'pending_favs': int(state.get('pending_favs', 0)),
            'bitmap_cvg': float(state.get('bitmap_cvg', 0.0)),
            'stability': float(state.get('stability', 0.0)),
            'saved_crashes': int(state.get('saved_crashes', 0)),
            'saved_hangs': int(state.get('saved_hangs', 0)),
            'total_tmout': int(state.get('total_tmout', 0)),
            'run_time': int(state.get('run_time', 0)),
            'fuzz_time': int(state.get('fuzz_time', 0)),
            'last_update': int(state.get('last_update', 0)),
        }

        # Warn once if keys are missing in state
        missing = [k for k in stats.keys() if k not in state]
        if missing:
            logger.warning(f"[HTTP.get_statistics] Missing keys in Redis state: {missing}")

        return JsonResponse({
            "status": "success",
            "statistics": stats
        })

    except Exception as e:
        logger.error(f"Error getting campaign statistics: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get campaign statistics: {str(e)}"
        }, status=500)

def get_test_groups(request: HttpRequest):
    """
    GET /api/iot-fuzzer/testing/test-groups/
    Get test groups with enhanced information for group selection
    """
    if request.method != 'GET':
        return method_not_allowed("GET")
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        # Get test groups from database with enhanced information
        from iotsploit_django.adapters.django.iot_fuzzer.models import TestGroup
        from django.db.models import Count, Q
        
        # Query test groups with test case counts and strategy information
        test_groups = TestGroup.objects.filter(enabled=True).annotate(
            test_cases_count=Count('test_cases', filter=Q(test_cases__enabled=True))
        ).order_by('name')
        
        groups_data = []
        for group in test_groups:
            # Calculate strategy distribution for this group
            strategy_stats = _calculate_group_strategy_distribution(group)
            
            groups_data.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'priority': group.priority,
                'protocol_type': group.protocol_type,
                'total_cases': group.total_cases,
                'completed_cases': group.completed_cases,
                'enabled_test_cases': group.test_cases_count,
                'strategy_distribution': strategy_stats,
                'has_bit_level_rules': strategy_stats.get('bit_level', 0) > 0,
                'has_field_level_rules': strategy_stats.get('field_level', 0) > 0,
                'campaign_id': campaign_id
            })
        
        return JsonResponse({
            "status": "success",
            "test_groups": groups_data,
            "total_groups": len(groups_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting test groups: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test groups: {str(e)}"
        }, status=500)

def _calculate_group_strategy_distribution(group):
    """Calculate strategy distribution for a test group"""
    try:
        from iotsploit_django.adapters.django.iot_fuzzer.models import FuzzingRule
        
        # Get fuzzing rules for this group's test cases
        rules = FuzzingRule.objects.filter(
            test_case__group=group,
            test_case__enabled=True,
            enabled=True
        )
        
        strategy_counts = {
            'bit_level': 0,
            'field_level': 0,
            'total_rules': rules.count()
        }
        
        for rule in rules:
            if rule.target_type == 'bit':
                strategy_counts['bit_level'] += 1
            elif rule.target_type == 'field':
                strategy_counts['field_level'] += 1
        
        return strategy_counts
        
    except Exception as e:
        logger.error(f"Error calculating strategy distribution for group {group.id}: {e}")
        return {'bit_level': 0, 'field_level': 0, 'total_rules': 0}
