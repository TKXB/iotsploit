import logging
from typing import Dict, Any
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from iotsploit_core.core.tool_service import get_firmware_service
from pathlib import Path

logger = logging.getLogger(__name__)


def _format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _resolved_firmware_paths(resolved: Dict[str, Any]) -> list[Path]:
    """Return all concrete filesystem paths for a resolved firmware entry."""
    paths: list[Path] = []

    top_level_path = resolved.get("path")
    if top_level_path:
        paths.append(Path(top_level_path))

    flash_options = resolved.get("flash_options") or {}
    for entry in flash_options.get("files", []):
        entry_path = entry.get("path")
        if entry_path:
            paths.append(Path(entry_path))

    return paths


def _annotate_file_stats(firmware_service, name: str, info: Dict) -> None:
    """Populate file_exists / file_size / file_size_formatted on ``info``.

    Uses ``resolve_firmware`` so both legacy ``path``-based entries and new
    package-``resource``-based entries produce real filesystem locations.
    """
    try:
        with firmware_service.resolve_firmware(name) as resolved:
            paths = _resolved_firmware_paths(resolved)
            if not paths:
                info['file_exists'] = False
                info['file_size'] = 0
                info['file_size_formatted'] = "No path"
                return

            all_exist = all(path.exists() for path in paths)
            info['file_exists'] = all_exist
            if all_exist:
                try:
                    size = sum(path.stat().st_size for path in paths)
                    info['file_size'] = size
                    info['file_size_formatted'] = _format_file_size(size)
                except Exception:
                    info['file_size'] = 0
                    info['file_size_formatted'] = "Unknown"
            else:
                info['file_size'] = 0
                info['file_size_formatted'] = "File missing"
    except Exception:
        info['file_exists'] = False
        info['file_size'] = 0
        info['file_size_formatted'] = "Unresolvable"

@csrf_exempt
@require_http_methods(["GET"])
def firmware_list(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to list all available firmware
    
    GET /api/firmware/list/
    
    Returns:
        JSON response with list of firmware
    """
    try:
        firmware_service = get_firmware_service()
        firmware_list = firmware_service.list_firmware()
        
        # Add file existence check for each firmware (resolves package
        # resources via the centralized firmware resolver).
        for firmware in firmware_list:
            _annotate_file_stats(firmware_service, firmware.get('name', ''), firmware)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Found {len(firmware_list)} firmware(s)',
            'firmware': firmware_list
        })
        
    except Exception as e:
        logger.error(f"Error listing firmware: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to list firmware: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def firmware_info(request: HttpRequest, name: str) -> JsonResponse:
    """
    API endpoint to get information about specific firmware
    
    GET /api/firmware/<name>/
    
    Parameters:
        name (str): The name of the firmware
    
    Returns:
        JSON response with firmware information
    """
    try:
        firmware_service = get_firmware_service()
        firmware_info = firmware_service.get_firmware_info(name)
        
        if not firmware_info:
            return JsonResponse({
                'status': 'error',
                'message': f'Firmware "{name}" not found'
            }, status=404)
        
        # Add file existence check via the resolver so that both legacy
        # ``path``-based entries and new ``resource``-based entries work.
        _annotate_file_stats(firmware_service, name, firmware_info)

        # Add name to the response
        firmware_info['name'] = name
        
        return JsonResponse({
            'status': 'success',
            'firmware': firmware_info
        })
        
    except Exception as e:
        logger.error(f"Error getting firmware info for {name}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to get firmware info: {str(e)}'
        }, status=500)
