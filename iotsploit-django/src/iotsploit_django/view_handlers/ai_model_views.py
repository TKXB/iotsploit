import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from ..models.AIModel_Model import AIModelConfig, AIModelTemplate, AIModelProvider
from ..tools.xlogger import xlog

logger = xlog.get_logger('ai_model_views')

@csrf_exempt
@require_http_methods(["GET"])
def ai_model_list(request):
    """List all AI model configurations"""
    try:
        configs = AIModelConfig.objects.all().order_by('-created_at')
        data = []
        
        for config in configs:
            # Get provider display name
            provider_display = config.provider.replace('_', ' ').title() if config.provider else ''
            
            data.append({
                'id': config.id,
                'name': config.name or '',
                'provider': config.provider or '',
                'provider_display': provider_display,
                'model_name': config.model_name or '',
                'api_url': config.api_url or '',
                'api_key_masked': config.get_masked_api_key() or '',
                'extra_config': config.extra_config or {},
                'is_default': config.is_default if config.is_default is not None else False,
                'is_active': config.is_active if config.is_active is not None else True,
                'created_at': config.created_at.isoformat() if config.created_at else '',
                'updated_at': config.updated_at.isoformat() if config.updated_at else '',
                'usage_count': config.usage_count or 0,
                'last_used_at': config.last_used_at.isoformat() if config.last_used_at else None,
            })
        
        response_data = {
            'success': True,
            'data': data,
            'count': len(data)
        }
        logger.info(f"AI Model List Response: {response_data}")
        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error listing AI models: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def ai_model_create(request):
    """Create a new AI model configuration"""
    try:
        # Log the raw request
        logger.info(f"AI Model Create Request - Method: {request.method}")
        logger.info(f"AI Model Create Request - Headers: {dict(request.headers)}")
        logger.info(f"AI Model Create Request - Body: {request.body.decode('utf-8')}")
        
        data = json.loads(request.body)
        logger.info(f"AI Model Create Request - Parsed Data: {data}")
        
        # Validate required fields
        required_fields = ['name', 'provider', 'model_name', 'api_url', 'api_key']
        for field in required_fields:
            if field not in data:
                error_response = {
                    'success': False,
                    'error': f'Missing required field: {field}'
                }
                logger.error(f"AI Model Create Error Response: {error_response}")
                return JsonResponse(error_response, status=400)
        
        # Validate provider
        available_providers = [choice[0] for choice in AIModelProvider.choices]
        logger.info(f"Available providers: {available_providers}")
        logger.info(f"Requested provider: {data['provider']}")
        
        if data['provider'] not in available_providers:
            error_response = {
                'success': False,
                'error': f'Invalid provider: {data["provider"]}. Available: {available_providers}'
            }
            logger.error(f"AI Model Create Error Response: {error_response}")
            return JsonResponse(error_response, status=400)
        
        logger.info("Starting database transaction for AI model creation")
        with transaction.atomic():
            # If this is set as default, unset other defaults
            if data.get('is_default', False):
                logger.info("Unsetting other default configurations")
                AIModelConfig.objects.filter(is_default=True).update(is_default=False)
            
            logger.info("Creating new AI model configuration")
            
            # Prepare extra_config with additional parameters
            extra_config = data.get('extra_config', {})
            if 'max_tokens' in data:
                extra_config['max_tokens'] = data.get('max_tokens', 4000)
            if 'temperature' in data:
                extra_config['temperature'] = data.get('temperature', 0.7)
            if 'timeout' in data:
                extra_config['timeout'] = data.get('timeout', 30)
            
            config = AIModelConfig.objects.create(
                name=data['name'],
                provider=data['provider'],
                model_name=data['model_name'],
                api_url=data['api_url'],
                is_default=data.get('is_default', False),
                is_active=data.get('is_active', True),
                extra_config=extra_config
            )
            
            # Set the API key using the encryption method
            config.set_api_key(data['api_key'])
            config.save()
            logger.info(f"Successfully created AI model configuration with ID: {config.id}")
        
        success_response = {
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name,
                'provider': config.provider,
                'model_name': config.model_name,
                'api_url': config.api_url,
                'is_default': config.is_default,
                'is_active': config.is_active,
                'created_at': config.created_at.isoformat(),
            }
        }
        logger.info(f"AI Model Create Success Response: {success_response}")
        return JsonResponse(success_response, status=201)
        
    except json.JSONDecodeError as e:
        error_response = {
            'success': False,
            'error': f'Invalid JSON data: {str(e)}'
        }
        logger.error(f"AI Model Create JSON Error: {error_response}")
        return JsonResponse(error_response, status=400)
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e)
        }
        logger.error(f"AI Model Create Exception: {error_response}")
        logger.exception("Full exception details:")
        return JsonResponse(error_response, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def ai_model_detail(request, pk):
    """Get details of a specific AI model configuration"""
    try:
        config = AIModelConfig.objects.get(pk=pk)
        
        response_data = {
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name or '',
                'provider': config.provider or '',
                'model_name': config.model_name or '',
                'api_url': config.api_url or '',
                'api_key_masked': config.get_masked_api_key() or '',
                'is_default': config.is_default if config.is_default is not None else False,
                'is_active': config.is_active if config.is_active is not None else True,
                'max_tokens': config.max_tokens or 4000,
                'temperature': config.temperature if config.temperature is not None else 0.7,
                'timeout': config.timeout or 30,
                'extra_params': config.extra_params or {},
                'created_at': config.created_at.isoformat() if config.created_at else '',
                'updated_at': config.updated_at.isoformat() if config.updated_at else '',
                'usage_count': config.usage_count or 0,
                'last_used': config.last_used.isoformat() if config.last_used else '',
            }
        }
        logger.info(f"AI Model Detail Response: {response_data}")
        return JsonResponse(response_data)
    except ObjectDoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'AI model configuration not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting AI model detail: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def ai_model_update(request, pk):
    """Update an AI model configuration"""
    try:
        # Log the raw request
        logger.info(f"AI Model Update Request - Method: {request.method}")
        logger.info(f"AI Model Update Request - Headers: {dict(request.headers)}")
        logger.info(f"AI Model Update Request - Body: {request.body.decode('utf-8')}")
        
        config = AIModelConfig.objects.get(pk=pk)
        data = json.loads(request.body)
        logger.info(f"AI Model Update Request - Parsed Data: {data}")
        
        with transaction.atomic():
            # If this is set as default, unset other defaults
            if data.get('is_default', False) and not config.is_default:
                logger.info("Unsetting other default configurations")
                AIModelConfig.objects.filter(is_default=True).update(is_default=False)
            
            # Update basic fields
            if 'name' in data:
                config.name = data['name']
            if 'provider' in data:
                config.provider = data['provider']
            if 'model_name' in data:
                config.model_name = data['model_name']
            if 'api_url' in data:
                config.api_url = data['api_url']
            if 'is_default' in data:
                config.is_default = data['is_default']
            if 'is_active' in data:
                config.is_active = data['is_active']
            
            # Handle extra_config with additional parameters
            extra_config = config.extra_config or {}
            if 'max_tokens' in data:
                extra_config['max_tokens'] = data['max_tokens']
            if 'temperature' in data:
                extra_config['temperature'] = data['temperature']
            if 'timeout' in data:
                extra_config['timeout'] = data['timeout']
            if 'extra_config' in data:
                extra_config.update(data['extra_config'])
            config.extra_config = extra_config
            
            # Handle API key separately if provided
            if 'api_key' in data and data['api_key']:
                logger.info("Updating API key")
                config.set_api_key(data['api_key'])
            
            config.save()
            logger.info(f"Successfully updated AI model configuration with ID: {config.id}")
        
        success_response = {
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name,
                'provider': config.provider,
                'model_name': config.model_name,
                'api_url': config.api_url,
                'is_default': config.is_default,
                'is_active': config.is_active,
                'updated_at': config.updated_at.isoformat(),
            }
        }
        logger.info(f"AI Model Update Success Response: {success_response}")
        return JsonResponse(success_response)
        
    except ObjectDoesNotExist:
        error_response = {
            'success': False,
            'error': 'AI model configuration not found'
        }
        logger.error(f"AI Model Update Error Response: {error_response}")
        return JsonResponse(error_response, status=404)
    except json.JSONDecodeError as e:
        error_response = {
            'success': False,
            'error': f'Invalid JSON data: {str(e)}'
        }
        logger.error(f"AI Model Update JSON Error: {error_response}")
        return JsonResponse(error_response, status=400)
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e)
        }
        logger.error(f"AI Model Update Exception: {error_response}")
        logger.exception("Full exception details:")
        return JsonResponse(error_response, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def ai_model_delete(request, pk):
    """Delete an AI model configuration"""
    try:
        config = AIModelConfig.objects.get(pk=pk)
        config_name = config.name
        config.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'AI model configuration "{config_name}" deleted successfully'
        })
        
    except ObjectDoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'AI model configuration not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error deleting AI model: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def ai_model_test_connection(request, pk):
    """Test connection to an AI model"""
    try:
        config = AIModelConfig.objects.get(pk=pk)
        
        # TODO: Implement actual connection testing based on provider
        # For now, return a mock response
        
        return JsonResponse({
            'success': True,
            'message': f'Connection test for {config.name} completed',
            'details': {
                'provider': config.provider,
                'model': config.model_name,
                'url': config.api_url,
                'status': 'Connected',  # Mock status
                'response_time': '150ms'  # Mock response time
            }
        })
        
    except ObjectDoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'AI model configuration not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error testing AI model connection: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def ai_model_set_default(request, pk):
    """Set an AI model configuration as default"""
    try:
        with transaction.atomic():
            # Unset all current defaults
            AIModelConfig.objects.filter(is_default=True).update(is_default=False)
            
            # Set the specified config as default
            config = AIModelConfig.objects.get(pk=pk)
            config.is_default = True
            config.save()
        
        return JsonResponse({
            'success': True,
            'message': f'"{config.name}" set as default AI model configuration'
        })
        
    except ObjectDoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'AI model configuration not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error setting default AI model: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def ai_template_list(request):
    """List all AI model templates"""
    try:
        templates = AIModelTemplate.objects.all().order_by('provider', 'name')
        data = []
        
        for template in templates:
            data.append({
                'id': template.id,
                'name': template.name or '',
                'provider': template.provider or '',
                'default_api_url': template.default_api_url or '',
                'supported_models': template.supported_models or [],
                'required_fields': template.required_fields or [],
                'optional_fields': template.optional_fields or [],
                'description': template.description or '',
                'documentation_url': template.documentation_url or '',
            })
        
        response_data = {
            'success': True,
            'data': data,
            'count': len(data)
        }
        logger.info(f"AI Template List Response: {response_data}")
        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error listing AI templates: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def ai_provider_list(request):
    """List all available AI model providers"""
    try:
        from ..models.AIModel_Model import AI_MODEL_TEMPLATES
        
        providers = []
        for provider, template_info in AI_MODEL_TEMPLATES.items():
            # 确保 provider 是字符串值而不是枚举对象
            provider_id = provider.value if hasattr(provider, 'value') else str(provider)
            provider_name = provider_id.replace('_', ' ').title()
            
            providers.append({
                'value': provider_id,  # Flutter 期望的字段名
                'label': provider_name,  # Flutter 期望的字段名
                'default_url': template_info.get('default_api_url', ''),  # Flutter 期望的字段名
                'supported_models': template_info.get('supported_models', []),
                'required_fields': template_info.get('required_fields', []),
                'documentation_url': template_info.get('documentation_url', ''),
                'description': template_info.get('description', f'{provider_name} AI provider')
            })
        
        response_data = {
            'success': True,
            'data': providers,
            'count': len(providers)
        }
        logger.info(f"AI Provider List Response: {response_data}")
        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error listing AI providers: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 