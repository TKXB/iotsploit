import json
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


@csrf_exempt
@require_http_methods(["POST"])
def firmware_add(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to add new firmware to the system
    
    POST /api/firmware/add/
    
    JSON Body:
        {
            "name": "firmware_name",
            "path": "/path/to/firmware.bin",
            "device_type": "esp32",
            "version": "1.0.0",
            "flash_options": {}  // optional
        }
    
    Returns:
        JSON response indicating success or failure
    """
    try:
        if request.content_type != 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }, status=400)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        
        # Validate required fields
        required_fields = ['name', 'path', 'device_type', 'version']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return JsonResponse({
                'status': 'error',
                'message': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)
        
        name = data['name']
        path = data['path']
        device_type = data['device_type']
        version = data['version']
        flash_options = data.get('flash_options')
        
        firmware_service = get_firmware_service()
        
        # Check if firmware already exists
        if firmware_service.get_firmware_info(name):
            return JsonResponse({
                'status': 'error',
                'message': f'Firmware "{name}" already exists'
            }, status=409)
        
        success = firmware_service.add_firmware(name, path, device_type, version, flash_options)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully added firmware: {name}'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to add firmware: {name}'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error adding firmware: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to add firmware: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def firmware_remove(request: HttpRequest, name: str) -> JsonResponse:
    """
    API endpoint to remove firmware from the system
    
    DELETE /api/firmware/remove/<name>/
    
    Parameters:
        name (str): The name of the firmware to remove
    
    Returns:
        JSON response indicating success or failure
    """
    try:
        firmware_service = get_firmware_service()
        
        # Check if firmware exists
        if not firmware_service.get_firmware_info(name):
            return JsonResponse({
                'status': 'error',
                'message': f'Firmware "{name}" not found'
            }, status=404)
        
        success = firmware_service.remove_firmware(name)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully removed firmware: {name}'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to remove firmware: {name}'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error removing firmware {name}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to remove firmware: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def firmware_flash(request: HttpRequest) -> JsonResponse:
    logger.debug(f"[BACKEND FLASH] method={request.method}, content_type={request.content_type}, body={request.body[:500]!r}")
    try:
        if request.content_type != 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }, status=400)
        
        try:
            data = json.loads(request.body)
            print(data)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        
        # Validate required fields
        if 'firmware_name' not in data:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: firmware_name'
            }, status=400)
        
        firmware_name = data['firmware_name']
        options = data.get('options', {})
        
        firmware_service = get_firmware_service()
        
        # Check if firmware exists in the manifest. The actual file check is
        # delegated to flash_registered_firmware, which uses resolve_firmware
        # to materialize package-resource references into real paths.
        if not firmware_service.get_firmware_info(firmware_name):
            return JsonResponse({
                'status': 'error',
                'message': f'Firmware "{firmware_name}" not found'
            }, status=404)

        success = firmware_service.flash_registered_firmware(firmware_name, options)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully flashed firmware: {firmware_name}'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to flash firmware: {firmware_name}'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error flashing firmware: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to flash firmware: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def firmware_download(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to download firmware from URL
    
    POST /api/firmware/download/
    
    JSON Body:
        {
            "url": "https://example.com/firmware.bin",
            "output_path": "/path/to/save/firmware.bin"  // optional
        }
    
    Returns:
        JSON response with download result
    """
    try:
        if request.content_type != 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }, status=400)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        
        # Validate required fields
        if 'url' not in data:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: url'
            }, status=400)
        
        url = data['url']
        output_path = data.get('output_path')
        
        firmware_service = get_firmware_service()
        result_path = firmware_service.download_firmware(url, output_path)
        
        if result_path:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully downloaded firmware',
                'path': result_path
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to download firmware'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error downloading firmware: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to download firmware: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def firmware_erase(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to erase device flash memory
    
    POST /api/firmware/erase/
    
    JSON Body:
        {
            "device_type": "esp32",
            "options": {
                "port": "/dev/ttyACM2",
                "chip": "esp32s3",
                "baud": "460800"
            }
        }
    
    Returns:
        JSON response indicating success or failure
    """
    try:
        if request.content_type != 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }, status=400)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        
        # Validate required fields
        if 'device_type' not in data:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: device_type'
            }, status=400)
        
        device_type = data['device_type']
        options = data.get('options', {})
        
        firmware_service = get_firmware_service()
        
        # Route to appropriate programmer based on device type
        if device_type.lower().startswith('esp32'):
            port = options.get('port', '/dev/ttyACM2')
            chip = options.get('chip', 'esp32s3')
            baud = options.get('baud', '460800')
            
            result = firmware_service.esp32.erase_flash(port=port, chip=chip, baud=baud)
            
            if result.success:
                return JsonResponse({
                    'status': 'success',
                    'message': f'Successfully erased {device_type} flash',
                    'execution_time': result.execution_time
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to erase flash: {result.stderr or "Unknown error"}',
                    'return_code': result.return_code
                }, status=500)
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Flash erase not supported for device type: {device_type}'
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error erasing flash: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to erase flash: {str(e)}'
        }, status=500)
