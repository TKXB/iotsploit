from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest
import json
import logging

from iotsploit_django.iot_fuzzer.service import (
    IoTFuzzerService,
    IoTProtocolAdapter,
)
from iotsploit_django.iot_fuzzer.http import method_not_allowed, parse_json_body

# Import Django models
from iotsploit_django.adapters.django.iot_fuzzer.models import (
    ConfigTemplate, IoTConfiguration
)

logger = logging.getLogger(__name__)

# Campaign Control Endpoints

def get_protocol_types(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/protocols/types/
    Get available protocol types and their parameters
    """
    if request.method != 'GET':
        return method_not_allowed("GET")

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
        return method_not_allowed("GET")

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
    POST /api/iot-fuzzer/configuration/protocols/config/save/
    Save protocol configuration to database
    """
    if request.method != 'POST':
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
        config_data = data.get('config', {})

        # Extract configuration components
        protocol_type = config_data.get('protocol_type', 'uart')
        protocol_settings = {
            'device_path': config_data.get('device_path', '/dev/ttyACM0'),
            'baud_rate': config_data.get('baud_rate', '115200'),
            'timeout': config_data.get('timeout', 1000),
        }

        generator_type = config_data.get('generator_type', 'radamsa')
        generator_settings = {
            'mutation_rate': config_data.get('mutation_rate', 0.5),
            'coverage_feedback': config_data.get('coverage_feedback', True),
            'radamsa_path': config_data.get('radamsa_path', '/usr/bin/radamsa'),
        }

        campaign_settings = {
            'total_iterations': config_data.get('total_iterations', 1000),
            'delay_between_tests': config_data.get('delay_between_tests', 100),
            'crash_detection': config_data.get('crash_detection', True),
            'save_artifacts': config_data.get('save_artifacts', True),
        }

        monitoring_settings = {
            'log_level': config_data.get('log_level', 'info'),
            'output_directory': config_data.get('output_directory', '/tmp/fuzzer_output'),
            'realtime_monitoring': config_data.get('realtime_monitoring', True),
            'performance_metrics': config_data.get('performance_metrics', True),
        }

        # Create or update IoTConfiguration
        config_name = config_data.get('name', f'{protocol_type.upper()} Configuration')
        config_description = config_data.get('description', f'Auto-generated {protocol_type} configuration')

        # Try to find existing active configuration for this protocol type
        existing_config = IoTConfiguration.objects.filter(
            protocol_type=protocol_type,
            is_active=True
        ).first()

        if existing_config:
            # Update existing configuration
            existing_config.name = config_name
            existing_config.description = config_description
            existing_config.protocol_settings = protocol_settings
            existing_config.generator_type = generator_type
            existing_config.generator_settings = generator_settings
            existing_config.campaign_settings = campaign_settings
            existing_config.monitoring_settings = monitoring_settings
            existing_config.save()
            config_id = existing_config.id
            logger.info(f"Updated existing IoT configuration {config_id}")
        else:
            # Create new configuration
            new_config = IoTConfiguration.objects.create(
                name=config_name,
                description=config_description,
                protocol_type=protocol_type,
                protocol_settings=protocol_settings,
                generator_type=generator_type,
                generator_settings=generator_settings,
                campaign_settings=campaign_settings,
                monitoring_settings=monitoring_settings,
                is_active=True
            )
            config_id = new_config.id
            logger.info(f"Created new IoT configuration {config_id}")

        return JsonResponse({
            "status": "success",
            "config_id": config_id,
            "message": "Configuration saved to database successfully"
        })

    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error saving configuration to database: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to save configuration: {str(e)}"
        }, status=500)

@csrf_exempt
def get_saved_config(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/saved/
    Get saved configuration from database
    """
    if request.method != 'GET':
        return method_not_allowed("GET")

    try:
        # Get protocol type from query parameters
        protocol_type = request.GET.get('protocol_type', 'uart')

        # Find active configuration for this protocol type
        config = IoTConfiguration.objects.filter(
            protocol_type=protocol_type,
            is_active=True
        ).first()

        if not config:
            return JsonResponse({
                "status": "error",
                "message": f"No active configuration found for protocol type: {protocol_type}"
            }, status=404)

        # Convert to dictionary format
        config_data = config.to_dict()

        return JsonResponse({
            "status": "success",
            "config": config_data,
            "message": "Configuration retrieved successfully"
        })

    except Exception as e:
        logger.error(f"Error retrieving configuration from database: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to retrieve configuration: {str(e)}"
        }, status=500)

@csrf_exempt
def test_protocol_connection(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/protocols/test-connection/
    Test protocol connection
    """
    if request.method != 'POST':
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
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

def get_generator_types(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/generators/types/
    Get available generator types and their parameters
    """
    if request.method != 'GET':
        return method_not_allowed("GET")

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
        return method_not_allowed("GET")

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
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
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

def get_templates_list(request: HttpRequest):
    """
    GET /api/iot-fuzzer/configuration/templates/list/
    Return available configuration templates
    """
    if request.method != 'GET':
        return method_not_allowed("GET")

    try:
        category = request.GET.get('category')

        templates = ConfigTemplate.objects.all()
        if category:
            templates = templates.filter(category=category)

        templates_data = []
        for template in templates:
            item = {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'category': template.category,
                'is_default': template.is_default,
                'usage_count': template.usage_count,
                'created_at': template.created_at.isoformat()
            }

            # Include saved configuration blocks if present, so frontend can show previews
            if template.protocol_config is not None:
                item['protocol_config'] = template.protocol_config
            if template.generator_config is not None:
                item['generator_config'] = template.generator_config
            if template.monitoring_config is not None:
                item['monitoring_config'] = template.monitoring_config

            templates_data.append(item)

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
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
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
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
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

@csrf_exempt
def delete_template(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/templates/delete/
    Delete a configuration template by id
    """
    if request.method != 'POST':
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
        template_id = data.get('template_id')

        if not template_id:
            return JsonResponse({
                "status": "error",
                "message": "Template ID is required"
            }, status=400)

        # Accept both int and string IDs
        try:
            template_obj = ConfigTemplate.objects.get(id=int(template_id))
        except (ConfigTemplate.DoesNotExist, ValueError):
            return JsonResponse({
                "status": "error",
                "message": "Template not found"
            }, status=404)

        template_obj.delete()

        return JsonResponse({
            "status": "success",
            "message": "Template deleted successfully"
        })
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete template: {str(e)}"
        }, status=500)

@csrf_exempt
def validate_configuration(request: HttpRequest):
    """
    POST /api/iot-fuzzer/configuration/validate/
    Validate complete configuration
    """
    if request.method != 'POST':
        return method_not_allowed("POST")

    try:
        data = parse_json_body(request)
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
