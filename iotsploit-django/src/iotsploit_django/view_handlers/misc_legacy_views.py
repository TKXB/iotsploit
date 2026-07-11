from iotsploit_django.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from iotsploit_django.composition_root.wiring import (
    ensure_stream_backend_configured,
)
ensure_stream_backend_configured()

from iotsploit_django.tools.xlogger import xlog

logger = xlog.get_logger('views')

import json




from iotsploit_core.core.stream_manager import StreamManager





def active_channels(request):
    """
    GET
    Returns a list of all active data stream channels
    """
    try:
        stream_manager = StreamManager()
        active_channels = stream_manager.get_active_channels()
        broadcast_channels = stream_manager.get_broadcast_channels()

        return JsonResponse({
            "status": "success",
            "active_channels": active_channels,
            "broadcast_channels": broadcast_channels
        })

    except Exception as e:
        logger.error(f"Error retrieving active channels: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to retrieve active channels: {str(e)}"
        }, status=500)

def list_urls(request):
    """
    GET
    Returns a list of all available API endpoints
    """
    try:
        # Stage-3.5+: derive patterns from the
        # stage-2 route aggregation layer instead.
        from django.urls.resolvers import URLPattern, URLResolver
        from iotsploit_django.web.api import urls as api_urls

        def _walk(patterns, prefix: str = ""):
            out = []
            for p in patterns:
                if isinstance(p, URLPattern):
                    if getattr(p, "name", None):
                        out.append(
                            {
                                "name": str(p.name),
                                "pattern": f"/api/{prefix}{p.pattern}",
                                "method": "POST"
                                if getattr(p.callback, "csrf_exempt", False)
                                else "GET",
                                "description": (getattr(p.callback, "__doc__", "") or "").strip(),
                                "deprecated": "DEPRECATED"
                                in ((getattr(p.callback, "__doc__", "") or "")),
                            }
                        )
                elif isinstance(p, URLResolver):
                    out.extend(_walk(list(p.url_patterns), prefix=f"{prefix}{p.pattern}"))
            return out

        url_patterns = _walk(list(api_urls.urlpatterns))

        # Group endpoints by category based on their names or patterns
        categorized_endpoints = {
            'device': [],
            'vehicle': [],
            'test': [],
            'plugin': [],
            'group': [],
            'misc': []
        }

        for pattern in url_patterns:
            name = pattern['name']
            if 'device' in name:
                categorized_endpoints['device'].append(pattern)
            elif 'vehicle' in name or 'ota' in name:
                categorized_endpoints['vehicle'].append(pattern)
            elif 'test' in name:
                categorized_endpoints['test'].append(pattern)
            elif 'plugin' in name:
                categorized_endpoints['plugin'].append(pattern)
            elif 'group' in name:
                categorized_endpoints['group'].append(pattern)
            else:
                categorized_endpoints['misc'].append(pattern)

        return JsonResponse({
            'status': 'success',
            'message': f'Found {len(url_patterns)} endpoints',
            'endpoints': categorized_endpoints
        })

    except Exception as e:
        logger.error(f"Error listing URLs: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to list URLs: {str(e)}'
        }, status=500)

@csrf_exempt
def set_log_level(request):
    """
    POST
    Set the logging level for all xloggers

    Expected JSON body:
    {
        "level": "DEBUG|INFO|WARNING|ERROR|CRITICAL"
    }
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)

    try:
        data = json.loads(request.body)
        level = data.get('level', '').upper()

        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

        if not level:
            return JsonResponse({
                "status": "error",
                "message": "Log level is required",
                "valid_levels": valid_levels
            }, status=400)

        if level not in valid_levels:
            return JsonResponse({
                "status": "error",
                "message": f"Invalid log level. Must be one of: {', '.join(valid_levels)}",
                "valid_levels": valid_levels
            }, status=400)

        # Set the log level for all loggers
        for logger_name in xlog._loggers.keys():
            xlog.set_level(level, name=logger_name)

        return JsonResponse({
            "status": "success",
            "message": f"Log level set to {level} for all loggers",
            "level": level,
            "affected_loggers": list(xlog._loggers.keys())
        })

    except Exception as e:
        xlog.error(f"Error setting log level: {str(e)}", name="views")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to set log level: {str(e)}"
        }, status=500)
