from iotsploit_django.tools.sat_utils import *


from django.http import JsonResponse
from iotsploit_django.composition_root.wiring import (
    ensure_stream_backend_configured,
)
ensure_stream_backend_configured()

from iotsploit_django.tools.xlogger import xlog

logger = xlog.get_logger('views')






from iotsploit_core.core.tool_manager import get_tool_manager

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt



@require_http_methods(["GET"])
def get_tools_status(request):
    """
    Get comprehensive tools status including discovery results, categories, and health info.

    Returns:
        JSON response with tools status, categories, and system health information
    """
    try:
        manager = get_tool_manager()

        # Get comprehensive tool information
        discovery_results = manager.discover_tools()
        system_health = manager.get_system_health(force_refresh=True)
        available_tools = manager.get_available_tools()
        missing_tools = manager.get_missing_tools()
        required_tools = manager.get_required_tools()
        optional_tools = manager.get_optional_tools()
        category_info = manager.get_category_info()
        install_recommendations = manager.get_installation_recommendations()

        # Create detailed tool list with status
        tools_detail = []
        for tool_name, status in discovery_results.items():
            tool_config = manager.get_tool_config(tool_name)
            tool_info = manager.registry.get_tool(tool_name)

            tools_detail.append({
                'name': tool_name,
                'status': status.value,
                'available': status.value == 'available',
                'required': tool_name in required_tools,
                'description': tool_config.description if tool_config else 'No description available',
                'version': tool_info.version if tool_info else None,
                'path': tool_info.path if tool_info else None,
                'install_hint': manager.get_install_hints().get(tool_name, 'No installation hint available')
            })

        response_data = {
            'status': 'success',
            'timestamp': manager._get_timestamp(),
            'system_health': {
                'status': system_health.status,
                'total_tools': system_health.total_tools,
                'available_tools': system_health.available_tools,
                'missing_tools': system_health.missing_tools,
                'missing_critical_tools': system_health.missing_critical_tools,
                'can_operate': system_health.category_status['tools']['can_operate'],
                'recommendations': system_health.recommendations
            },
            'category': {
                'name': category_info.name,
                'description': category_info.description,
                'total_tools': len(category_info.tools)
            },
            'tools': {
                'all': tools_detail,
                'available': available_tools,
                'missing': missing_tools,
                'required': required_tools,
                'optional': optional_tools
            },
            'installation': install_recommendations
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("Error getting tools status")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def refresh_tools(request):
    """
    Refresh tool discovery and validation.

    Returns:
        JSON response with updated discovery results
    """
    try:
        manager = get_tool_manager()

        # Force refresh tools
        discovery_results = manager.discover_tools()
        system_health = manager.get_system_health(force_refresh=True)

        response_data = {
            'status': 'success',
            'message': 'Tools refreshed successfully',
            'timestamp': manager._get_timestamp(),
            'discovery_results': {name: status.value for name, status in discovery_results.items()},
            'system_health': {
                'status': system_health.status,
                'available_tools': system_health.available_tools,
                'missing_tools': system_health.missing_tools,
                'can_operate': system_health.category_status['tools']['can_operate']
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("Error refreshing tools")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def get_tool_details(request, tool_name):
    """
    Get detailed information about a specific tool.

    Args:
        tool_name: Name of the tool to get details for

    Returns:
        JSON response with detailed tool information
    """
    try:
        manager = get_tool_manager()

        # Get tool information
        tool_info = manager.registry.get_tool(tool_name)
        if not tool_info:
            return JsonResponse({
                'status': 'error',
                'message': f'Tool {tool_name} not found'
            }, status=404)

        # Validate tool to get current status
        validated_tool = manager.validator.validate_tool(tool_info)
        tool_config = manager.get_tool_config(tool_name)
        install_hints = manager.get_install_hints()

        response_data = {
            'status': 'success',
            'tool': {
                'name': validated_tool.name,
                'status': validated_tool.status.value,
                'available': validated_tool.status.value == 'available',
                'path': validated_tool.path,
                'version': validated_tool.version,
                'aliases': validated_tool.aliases,
                'platforms': validated_tool.platforms,
                'min_version': validated_tool.min_version,
                'max_version': validated_tool.max_version,
                'last_checked': validated_tool.last_checked,
                'description': tool_config.description if tool_config else 'No description available',
                'required': tool_config.required if tool_config else False,
                'install_hint': install_hints.get(tool_name, 'No installation hint available'),
                'metadata': validated_tool.metadata
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception(f"Error getting tool details for {tool_name}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def get_system_health(request):
    """
    Get current system health status.

    Returns:
        JSON response with system health information
    """
    try:
        manager = get_tool_manager()

        # Get health report
        health_report = manager.get_health_report()

        return JsonResponse({
            'status': 'success',
            'health_report': health_report
        })

    except Exception as e:
        logger.exception("Error getting system health")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
