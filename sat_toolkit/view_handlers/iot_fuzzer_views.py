from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest, HttpResponse
import json
import logging
from django.apps import apps

from sat_toolkit.tools.iot_fuzzer_manager import IoTFuzzerManager
from sat_toolkit.tools.iot_fuzzer_service import IoTFuzzerService
from sat_toolkit.tools.iot_protocol_adapter import IoTProtocolAdapter
from sat_toolkit.tools.iot_fuzzer_bridge import IoTFuzzerBridge

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