from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Avg, Sum
from django.conf import settings
from django.utils import timezone
import json
import logging
import os
import mimetypes
from django.apps import apps

from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
from sat_toolkit.tools.iot_fuzzer_service import IoTFuzzerService
from sat_toolkit.tools.iot_protocol_adapter import IoTProtocolAdapter
from sat_toolkit.tools.iot_fuzzer_bridge import IoTFuzzerBridge

# Import Django models
from sat_toolkit.models.IoTFuzzer_Model import (
    FuzzingCampaign, TestGroup, TestCase, FuzzingResult, ConfigTemplate, LiveLog,
    ProtocolConfiguration, FrameField, FuzzingRule
)

logger = logging.getLogger(__name__)

# Campaign Control Endpoints
@csrf_exempt
def start_campaign(request: HttpRequest):
    """
    POST /api/iot-fuzzer/testing/campaign/start/
    Start a new fuzzing campaign with provided configuration
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        print(f"start_campaign POST body: {data}")
        campaign_config = data.get('campaign_config', {})
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        campaign_id = fuzzer_manager.start_campaign(campaign_config)
        
        return JsonResponse({
            "status": "success",
            "campaign_id": campaign_id,
            "message": "Campaign started successfully"
        })
        
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
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
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
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
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
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
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

# Status and Statistics Endpoints
def get_campaign_status(request: HttpRequest):
    """
    GET /api/iot-fuzzer/testing/campaign/status/
    Get current campaign status and progress
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        status = fuzzer_manager.get_campaign_status(campaign_id)
        print(f"get_campaign_status: {status}")
        
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
    Get detailed campaign statistics
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        fuzzer_manager = IoTFuzzerManager.get_instance()
        statistics = fuzzer_manager.get_campaign_statistics(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "statistics": statistics
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
    Get test groups with progress information
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        test_groups = fuzzer_service.get_test_groups(campaign_id)
        
        return JsonResponse({
            "status": "success",
            "test_groups": test_groups
        })
        
    except Exception as e:
        logger.error(f"Error getting test groups: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test groups: {str(e)}"
        }, status=500)

# Configuration Endpoints
def get_protocol_types(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/protocols/types/
    Get available protocol types and their parameters
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        protocol_adapter = IoTProtocolAdapter.get_instance()
        protocol_types = protocol_adapter.get_supported_protocols()
        
        return JsonResponse({
            "status": "success",
            "protocol_types": protocol_types
        })
        
    except Exception as e:
        logger.error(f"Error getting protocol types: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get protocol types: {str(e)}"
        }, status=500)

def get_protocol_config(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/protocols/config/
    Get current protocol configuration
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        config_id = request.GET.get('config_id')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        config = fuzzer_service.get_protocol_config(config_id)
        
        return JsonResponse({
            "status": "success",
            "config": config
        })
        
    except Exception as e:
        logger.error(f"Error getting protocol config: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get protocol config: {str(e)}"
        }, status=500)

@csrf_exempt
def save_protocol_config(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/protocols/config/
    Save protocol configuration
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        config_data = data.get('config', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        config_id = fuzzer_service.save_protocol_config(config_data)
        
        return JsonResponse({
            "status": "success",
            "config_id": config_id,
            "message": "Protocol configuration saved successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error saving protocol config: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to save protocol config: {str(e)}"
        }, status=500)

@csrf_exempt
def test_protocol_connection(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/protocols/test-connection/
    Test protocol connection
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        config_data = data.get('config', {})
        
        protocol_adapter = IoTProtocolAdapter.get_instance()
        test_result = protocol_adapter.test_connection(config_data)
        
        return JsonResponse({
            "status": "success",
            "test_result": test_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error testing protocol connection: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to test protocol connection: {str(e)}"
        }, status=500)


# ============================================================================
# Phase 3.2: Configuration Page Endpoints (Additional)
# ============================================================================

# Generator Configuration Endpoints
def get_generator_types(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/generators/types/
    Get available generator types and their parameters
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        protocol_adapter = IoTProtocolAdapter.get_instance()
        generator_types = protocol_adapter.get_supported_generators()
        
        return JsonResponse({
            "status": "success",
            "generator_types": generator_types
        })
        
    except Exception as e:
        logger.error(f"Error getting generator types: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get generator types: {str(e)}"
        }, status=500)

def get_generator_config(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/generators/config/
    Get current generator configuration
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        config_id = request.GET.get('config_id')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        config = fuzzer_service.get_generator_config(config_id)
        
        return JsonResponse({
            "status": "success",
            "config": config
        })
        
    except Exception as e:
        logger.error(f"Error getting generator config: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get generator config: {str(e)}"
        }, status=500)

@csrf_exempt
def save_generator_config(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/generators/config/
    Save generator configuration
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        config_data = data.get('config', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        config_id = fuzzer_service.save_generator_config(config_data)
        
        return JsonResponse({
            "status": "success",
            "config_id": config_id,
            "message": "Generator configuration saved successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error saving generator config: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to save generator config: {str(e)}"
        }, status=500)

# Template Management Endpoints
def get_templates_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/templates/list/
    Return available configuration templates
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        category = request.GET.get('category')
        
        templates = ConfigTemplate.objects.all()
        if category:
            templates = templates.filter(category=category)
        
        templates_data = []
        for template in templates:
            templates_data.append({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'category': template.category,
                'is_default': template.is_default,
                'usage_count': template.usage_count,
                'created_at': template.created_at.isoformat()
            })
        
        return JsonResponse({
            "status": "success",
            "templates": templates_data
        })
        
    except Exception as e:
        logger.error(f"Error getting templates list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get templates list: {str(e)}"
        }, status=500)

@csrf_exempt
def load_template(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/templates/load/
    Load selected template configuration
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        template_id = data.get('template_id')
        
        if not template_id:
            return JsonResponse({
                "status": "error",
                "message": "Template ID is required"
            }, status=400)
        
        template = ConfigTemplate.objects.get(id=template_id)
        template.increment_usage()
        
        return JsonResponse({
            "status": "success",
            "config": template.get_full_config(),
            "message": "Template loaded successfully"
        })
        
    except ConfigTemplate.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Template not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error loading template: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to load template: {str(e)}"
        }, status=500)

@csrf_exempt
def save_template(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/templates/save/
    Save current configuration as template
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        template_data = data.get('template', {})
        
        template = ConfigTemplate.objects.create(
            name=template_data.get('name', ''),
            description=template_data.get('description', ''),
            category=template_data.get('category', 'custom'),
            protocol_config=template_data.get('protocol_config', {}),
            generator_config=template_data.get('generator_config', {}),
            monitoring_config=template_data.get('monitoring_config', {}),
            is_default=template_data.get('is_default', False)
        )
        
        return JsonResponse({
            "status": "success",
            "template_id": template.id,
            "message": "Template saved successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error saving template: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to save template: {str(e)}"
        }, status=500)

# Configuration Validation
@csrf_exempt
def validate_configuration(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/validate/
    Validate complete configuration
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        config_data = data.get('config', {})
        
        protocol_adapter = IoTProtocolAdapter.get_instance()
        validation_result = protocol_adapter.validate_configuration(config_data)
        
        return JsonResponse({
            "status": "success",
            "validation_result": validation_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating configuration: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to validate configuration: {str(e)}"
        }, status=500)


# ============================================================================
# Phase 3.3: Management Page Endpoints (Pure Django)
# ============================================================================

# Test Group Management
def get_test_groups_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/test-groups/list/
    Return all test groups with metadata
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        test_groups = TestGroup.objects.select_related('campaign').prefetch_related('test_cases')
        
        if campaign_id:
            test_groups = test_groups.filter(campaign_id=campaign_id)
        
        groups_data = []
        for group in test_groups:
            groups_data.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'campaign_id': group.campaign.id,
                'campaign_name': group.campaign.name,
                'priority': group.priority,
                'enabled': group.enabled,
                'protocol_type': group.protocol_type,
                'total_cases': group.total_cases,
                'completed_cases': group.completed_cases,
                'failed_cases': group.failed_cases,
                'completion_percentage': group.get_completion_percentage(),
                'created_at': group.created_at.isoformat()
            })
        
        return JsonResponse({
            "status": "success",
            "test_groups": groups_data
        })
        
    except Exception as e:
        logger.error(f"Error getting test groups list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test groups list: {str(e)}"
        }, status=500)

@csrf_exempt
def create_test_group(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-groups/create/
    Create new test group
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        
        # Handle both nested and flat data formats
        if 'group' in data:
            group_data = data.get('group', {})
        else:
            group_data = data
        
        campaign_id = group_data.get('campaign_id')
        if not campaign_id:
            # Create or get default campaign if none provided
            campaign, created = FuzzingCampaign.objects.get_or_create(
                name='Default Campaign',
                defaults={
                    'description': 'Default campaign for test groups',
                    'protocol_type': group_data.get('protocol_type', 'can'),
                    'status': 'idle'
                }
            )
        else:
            try:
                campaign = FuzzingCampaign.objects.get(id=campaign_id)
            except FuzzingCampaign.DoesNotExist:
                return JsonResponse({
                    "status": "error",
                    "message": f"Campaign with ID {campaign_id} not found"
                }, status=404)
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": f"Invalid campaign ID format: {campaign_id}"
                }, status=400)
        
        test_group = TestGroup.objects.create(
            name=group_data.get('name', ''),
            description=group_data.get('description', ''),
            campaign=campaign,
            priority=group_data.get('priority', 'normal'),
            enabled=group_data.get('enabled', True),
            protocol_type=group_data.get('protocol_type', campaign.protocol_type)
        )
        
        return JsonResponse({
            "status": "success",
            "group_id": test_group.id,
            "message": "Test group created successfully"
        })
        
    except FuzzingCampaign.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Campaign not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to create test group: {str(e)}"
        }, status=500)

@csrf_exempt
def update_test_group(request: HttpRequest, group_id):
    """
    PUT /api/iot-fuzzer/management/test-groups/update/<id>/
    Update test group properties
    """
    if request.method != 'PUT':
        return JsonResponse({
            "status": "error",
            "message": "Only PUT method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        group_data = data.get('group', {})
        
        test_group = TestGroup.objects.get(id=group_id)
        
        # Update fields
        if 'name' in group_data:
            test_group.name = group_data['name']
        if 'description' in group_data:
            test_group.description = group_data['description']
        if 'priority' in group_data:
            test_group.priority = group_data['priority']
        if 'enabled' in group_data:
            test_group.enabled = group_data['enabled']
        
        test_group.save()
        
        return JsonResponse({
            "status": "success",
            "message": "Test group updated successfully"
        })
        
    except TestGroup.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test group not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to update test group: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_test_group(request: HttpRequest, group_id):
    """
    DELETE /api/iot-fuzzer/management/test-groups/delete/<id>/
    Delete test group and associated test cases
    """
    if request.method != 'DELETE':
        return JsonResponse({
            "status": "error",
            "message": "Only DELETE method is allowed"
        }, status=405)
    
    try:
        test_group = TestGroup.objects.get(id=group_id)
        test_group.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Test group deleted successfully"
        })
        
    except TestGroup.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test group not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting test group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete test group: {str(e)}"
        }, status=500)

# Test Case Management
def get_test_cases_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/test-cases/list/
    Return test cases with group assignment
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        group_id = request.GET.get('group_id')
        campaign_id = request.GET.get('campaign_id')
        
        test_cases = TestCase.objects.select_related('group', 'group__campaign', 'protocol_config').prefetch_related('frame_fields', 'fuzzing_rules')
        
        if group_id:
            test_cases = test_cases.filter(group_id=group_id)
        elif campaign_id:
            test_cases = test_cases.filter(group__campaign_id=campaign_id)
        
        cases_data = []
        for case in test_cases:
            # Build protocol frame from frame fields for backward compatibility
            protocol_frame = {}
            for field in case.frame_fields.order_by('field_order'):
                protocol_frame[field.field_id] = field.value
            
            # Get fuzzing rules summary
            fuzzing_targets = case.get_fuzzing_targets()
            
            cases_data.append({
                'id': case.id,
                'name': case.name,
                'description': case.description,
                'group_id': case.group.id,
                'group_name': case.group.name,
                'campaign_id': case.group.campaign.id,
                'campaign_name': case.group.campaign.name,
                'priority': case.priority,
                'enabled': case.enabled,
                'protocol_frame': protocol_frame,  # Reconstructed from frame fields
                'frame_name': case.frame_name,
                'frame_description': case.frame_description,
                'protocol_type': case.protocol_config.protocol_type,
                'protocol_settings': case.protocol_config.settings,
                'fuzzing_targets': fuzzing_targets,
                'expected_response': case.expected_response,
                'timeout_seconds': case.timeout_seconds,
                'timeout': int(case.timeout_seconds * 1000),  # Convert to milliseconds for Flutter
                'iterations': case.iterations,  # Now an actual field in the model
                'execution_count': case.execution_count,
                'last_executed': case.last_executed.isoformat() if case.last_executed else None,
                'last_result': case.last_result,
                'created_at': case.created_at.isoformat()
            })
        
        return JsonResponse({
            "status": "success",
            "test_cases": cases_data
        })
        
    except Exception as e:
        logger.error(f"Error getting test cases list: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get test cases list: {str(e)}"
        }, status=500)

@csrf_exempt
def create_test_case(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-cases/create/
    Create new test case
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        # Support both nested (case: {}) and flat data formats
        case_data = data.get('case', data)

        print(f"test_case_data: {case_data}")
        
        group_id = case_data.get('group_id')
        if not group_id:
            return JsonResponse({
                "status": "error",
                "message": "Group ID is required"
            }, status=400)
        
        # Handle both string and integer group IDs
        try:
            # Try to find by integer ID first
            if isinstance(group_id, str) and group_id.isdigit():
                group = TestGroup.objects.get(id=int(group_id))
            elif isinstance(group_id, int):
                group = TestGroup.objects.get(id=group_id)
            else:
                # If it's a string ID like 'offline-group-1', create a default group first
                if group_id.startswith('offline-'):
                    # Create or get default campaign if none exists
                    campaign, created = FuzzingCampaign.objects.get_or_create(
                        name='Default Campaign',
                        defaults={
                            'description': 'Default campaign for test cases',
                            'protocol_type': 'can',
                            'status': 'idle'
                        }
                    )
                    
                    # Create the group if it doesn't exist
                    group, created = TestGroup.objects.get_or_create(
                        name=case_data.get('name', 'Default Group'),
                        campaign=campaign,
                        defaults={
                            'description': 'Default test group',
                            'protocol_type': 'can',
                            'priority': 'normal',
                            'enabled': True
                        }
                    )
                else:
                    return JsonResponse({
                        "status": "error",
                        "message": f"Invalid group ID format: {group_id}"
                    }, status=400)
        except (TestGroup.DoesNotExist, ValueError):
            return JsonResponse({
                "status": "error",
                "message": f"Test group with ID {group_id} not found"
            }, status=404)
        
        # Convert timeout from milliseconds to seconds if needed
        timeout_value = case_data.get('timeout', case_data.get('timeout_seconds', 1.0))
        if timeout_value > 100:  # Assume it's in milliseconds if > 100
            timeout_value = timeout_value / 1000.0
        
        # Get or create a default protocol configuration
        protocol_type = case_data.get('protocol_type', group.protocol_type)
        protocol_config, created = ProtocolConfiguration.objects.get_or_create(
            protocol_type=protocol_type,
            defaults={
                'settings': {
                    'baud_rate': 500000 if protocol_type == 'can' else 115200,
                    'default': True
                }
            }
        )
        
        test_case = TestCase.objects.create(
            name=case_data.get('name', ''),
            description=case_data.get('description', ''),
            group=group,
            protocol_config=protocol_config,
            frame_name=case_data.get('frame_name', 'Protocol Frame'),
            frame_description=case_data.get('frame_description', ''),
            priority=case_data.get('priority', 'normal'),
            enabled=case_data.get('enabled', True),
            expected_response=case_data.get('expected_response'),
            timeout_seconds=timeout_value,
            iterations=case_data.get('iterations', 100)
        )
        
        # Create frame fields from protocol_frame data (for backward compatibility)
        protocol_frame = case_data.get('protocol_frame', {})
        if protocol_frame:
            field_order = 1
            for field_id, value in protocol_frame.items():
                FrameField.objects.create(
                    test_case=test_case,
                    field_name=field_id.replace('_', ' ').title(),
                    field_id=field_id,
                    field_type='hex' if isinstance(value, str) and value.startswith('0x') else 'dec',
                    value=str(value),
                    field_order=field_order,
                    is_required=(field_id in ['service_id', 'sid', 'id'])
                )
                field_order += 1
        
        # Update group statistics
        group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "case_id": test_case.id,
            "message": "Test case created successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to create test case: {str(e)}"
        }, status=500)

@csrf_exempt
def update_test_case(request: HttpRequest, case_id):
    """
    PUT /api/iot-fuzzer/management/test-cases/update/<id>/
    Update test case properties
    """
    if request.method != 'PUT':
        return JsonResponse({
            "status": "error",
            "message": "Only PUT method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        case_data = data.get('case', {})

        print(f"update test_case_data: {case_data}")
        
        test_case = TestCase.objects.get(id=case_id)
        
        # Update fields
        if 'name' in case_data:
            test_case.name = case_data['name']
        if 'description' in case_data:
            test_case.description = case_data['description']
        if 'frame_name' in case_data:
            test_case.frame_name = case_data['frame_name']
        if 'frame_description' in case_data:
            test_case.frame_description = case_data['frame_description']
        if 'priority' in case_data:
            test_case.priority = case_data['priority']
        if 'enabled' in case_data:
            test_case.enabled = case_data['enabled']
        if 'expected_response' in case_data:
            test_case.expected_response = case_data['expected_response']
        if 'timeout_seconds' in case_data:
            test_case.timeout_seconds = case_data['timeout_seconds']
        if 'iterations' in case_data:
            test_case.iterations = case_data['iterations']
        
        # Handle protocol_type updates
        if 'protocol_type' in case_data:
            protocol_type = case_data['protocol_type']
            # Find or create ProtocolConfiguration for this protocol type
            protocol_config, created = ProtocolConfiguration.objects.get_or_create(
                protocol_type=protocol_type,
                defaults={'settings': {}}
            )
            test_case.protocol_config = protocol_config
        
        # Handle protocol_frame updates by updating frame fields
        if 'protocol_frame' in case_data:
            protocol_frame = case_data['protocol_frame']
            
            # Update existing frame fields or create new ones
            existing_fields = {f.field_id: f for f in test_case.frame_fields.all()}
            
            field_order = 1
            for field_id, value in protocol_frame.items():
                if field_id in existing_fields:
                    # Update existing field
                    field = existing_fields[field_id]
                    field.value = str(value)
                    field.save()
                else:
                    # Create new field
                    FrameField.objects.create(
                        test_case=test_case,
                        field_name=field_id.replace('_', ' ').title(),
                        field_id=field_id,
                        field_type='hex' if isinstance(value, str) and value.startswith('0x') else 'dec',
                        value=str(value),
                        field_order=field_order,
                        is_required=(field_id in ['service_id', 'sid', 'id'])
                    )
                field_order += 1
        
        test_case.save()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case updated successfully"
        })
        
    except TestCase.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test case not found"
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to update test case: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_test_case(request: HttpRequest, case_id):
    """
    DELETE /api/iot-fuzzer/management/test-cases/delete/<id>/
    Delete test case
    """
    if request.method != 'DELETE':
        return JsonResponse({
            "status": "error",
            "message": "Only DELETE method is allowed"
        }, status=405)
    
    try:
        test_case = TestCase.objects.get(id=case_id)
        group = test_case.group
        test_case.delete()
        
        # Update group statistics
        group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case deleted successfully"
        })
        
    except TestCase.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Test case not found"
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete test case: {str(e)}"
        }, status=500)

@csrf_exempt
def move_test_case(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/test-cases/move/
    Move test case between groups
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        # Support both case_id and test_case_id field names
        case_id = data.get('case_id') or data.get('test_case_id')
        target_group_id = data.get('target_group_id')
        
        if not case_id:
            return JsonResponse({
                "status": "error",
                "message": "Test case ID is required"
            }, status=400)
        
        if not target_group_id:
            return JsonResponse({
                "status": "error",
                "message": "Target group ID is required"
            }, status=400)
        
        try:
            test_case = TestCase.objects.get(id=case_id)
        except TestCase.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Test case not found"
            }, status=404)
        
        try:
            # Handle both string and integer group IDs
            if isinstance(target_group_id, str) and target_group_id.isdigit():
                new_group = TestGroup.objects.get(id=int(target_group_id))
            elif isinstance(target_group_id, int):
                new_group = TestGroup.objects.get(id=target_group_id)
            else:
                return JsonResponse({
                    "status": "error",
                    "message": f"Invalid target group ID format: {target_group_id}"
                }, status=400)
        except TestGroup.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Target group not found"
            }, status=404)
        
        old_group = test_case.group
        
        # Validate group compatibility
        if old_group.campaign != new_group.campaign:
            return JsonResponse({
                "status": "error",
                "message": "Cannot move test case to different campaign"
            }, status=400)
        
        test_case.group = new_group
        test_case.save()
        
        # Update statistics for both groups
        old_group.update_statistics()
        new_group.update_statistics()
        
        return JsonResponse({
            "status": "success",
            "message": "Test case moved successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error moving test case: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to move test case: {str(e)}"
        }, status=500)

# Protocol Frame Builder
@csrf_exempt
def build_protocol_frame(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/protocol-frames/build/
    Build protocol frame from field specifications
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        frame_spec = data.get('frame_spec', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        frame_data = fuzzer_service.build_protocol_frame(frame_spec)
        
        return JsonResponse({
            "status": "success",
            "frame_data": frame_data
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error building protocol frame: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to build protocol frame: {str(e)}"
        }, status=500)

@csrf_exempt
def validate_protocol_frame(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/protocol-frames/validate/
    Validate protocol frame structure
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        frame_data = data.get('frame_data', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        validation_result = fuzzer_service.validate_protocol_frame(frame_data)
        
        return JsonResponse({
            "status": "success",
            "validation_result": validation_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating protocol frame: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to validate protocol frame: {str(e)}"
        }, status=500)

def get_protocol_frame_templates(request: HttpRequest):
    """
    GET /api/iot-fuzzer/management/protocol-frames/templates/
    Return protocol frame templates
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        protocol_type = request.GET.get('protocol_type')
        
        fuzzer_service = IoTFuzzerService.get_instance()
        templates = fuzzer_service.get_protocol_frame_templates(protocol_type)
        
        return JsonResponse({
            "status": "success",
            "templates": templates
        })
        
    except Exception as e:
        logger.error(f"Error getting protocol frame templates: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get protocol frame templates: {str(e)}"
        }, status=500)

# Export/Import Functionality
@csrf_exempt
def export_test_data(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/export/
    Export test groups and cases
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        export_config = data.get('export_config', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        export_result = fuzzer_service.export_test_data(export_config)
        
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
        logger.error(f"Error exporting test data: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to export test data: {str(e)}"
        }, status=500)

@csrf_exempt
def import_test_data(request: HttpRequest):
    """
    POST /api/iot-fuzzer/management/import/
    Import test groups and cases
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        import_data = data.get('import_data', {})
        
        fuzzer_service = IoTFuzzerService.get_instance()
        import_result = fuzzer_service.import_test_data(import_data)
        
        return JsonResponse({
            "status": "success",
            "import_result": import_result
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error importing test data: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to import test data: {str(e)}"
        }, status=500)


# ============================================================================
# Phase 3.4: Results Page Endpoints (Django with Adapter Data)
# ============================================================================

# File Management
def get_files_tree(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/files/tree/
    Return file tree structure
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
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
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
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
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
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

# Log Management
def get_logs_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/logs/list/
    Return test logs with filtering
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        log_level = request.GET.get('log_level')
        category = request.GET.get('category')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        
        logs = LiveLog.objects.select_related('campaign')
        
        if campaign_id:
            logs = logs.filter(campaign_id=campaign_id)
        if log_level:
            logs = logs.filter(log_level=log_level)
        if category:
            logs = logs.filter(category=category)
        
        logs = logs.order_by('-timestamp')
        
        paginator = Paginator(logs, page_size)
        page_obj = paginator.get_page(page)
        
        logs_data = []
        for log in page_obj:
            logs_data.append({
                'id': log.id,
                'campaign_id': log.campaign.id,
                'campaign_name': log.campaign.name,
                'timestamp': log.timestamp.isoformat(),
                'log_level': log.log_level,
                'message': log.message,
                'category': log.category,
                'source': log.source,
                'extra_data': log.extra_data,
                'formatted_timestamp': log.get_formatted_timestamp(),
                'is_error': log.is_error()
            })
        
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
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
        filter_criteria = data.get('filter_criteria', {})
        
        logs = LiveLog.objects.select_related('campaign')
        
        # Apply filters
        if 'campaign_id' in filter_criteria:
            logs = logs.filter(campaign_id=filter_criteria['campaign_id'])
        if 'log_level' in filter_criteria:
            logs = logs.filter(log_level=filter_criteria['log_level'])
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
            logs_data.append({
                'id': log.id,
                'campaign_id': log.campaign.id,
                'campaign_name': log.campaign.name,
                'timestamp': log.timestamp.isoformat(),
                'log_level': log.log_level,
                'message': log.message,
                'category': log.category,
                'source': log.source,
                'extra_data': log.extra_data,
                'formatted_timestamp': log.get_formatted_timestamp(),
                'is_error': log.is_error()
            })
        
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

# Results Analysis
def get_results_summary(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/analysis/summary/
    Return comprehensive result summary
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
    try:
        campaign_id = request.GET.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                "status": "error",
                "message": "Campaign ID is required"
            }, status=400)
        
        campaign = FuzzingCampaign.objects.get(id=campaign_id)
        
        # Get result statistics
        results = FuzzingResult.objects.filter(campaign=campaign)
        
        summary = {
            'campaign_info': {
                'id': campaign.id,
                'name': campaign.name,
                'status': campaign.status,
                'protocol_type': campaign.protocol_type,
                'started_at': campaign.started_at.isoformat() if campaign.started_at else None,
                'completed_at': campaign.completed_at.isoformat() if campaign.completed_at else None,
                'duration': campaign.get_duration_formatted(),
                'progress_percentage': campaign.get_progress_percentage()
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
                'crashes_per_hour': 0,  # Calculate based on duration
                'test_cases_per_second': 0  # Calculate based on duration
            }
        }
        
        # Calculate performance metrics
        if campaign.duration_seconds > 0:
            summary['performance_stats']['crashes_per_hour'] = (
                summary['execution_stats']['crash_count'] / campaign.duration_seconds * 3600
            )
            summary['performance_stats']['test_cases_per_second'] = (
                summary['execution_stats']['total_results'] / campaign.duration_seconds
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
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
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
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
    
    try:
        data = json.loads(request.body)
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

# Artifact Management
def get_artifacts(request: HttpRequest):
    """
    GET /api/iot-fuzzer/results/artifacts/
    Return crash artifacts and interesting findings
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    
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