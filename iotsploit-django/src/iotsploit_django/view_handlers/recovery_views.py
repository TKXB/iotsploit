from iotsploit_django.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from iotsploit_django.composition_root.wiring import (
    ensure_stream_backend_configured,
    get_device_driver_manager,
)
ensure_stream_backend_configured()

from iotsploit_django.tools.xlogger import xlog

logger = xlog.get_logger('views')

import json






from django.views.decorators.http import require_http_methods



@require_http_methods(["GET"])
def list_recovery_drivers(request):
    """
    Get a list of all device drivers that support recovery operations

    Returns:
        JSON response with recovery-capable drivers and their supported operations
    """
    try:
        device_manager = get_device_driver_manager()
        available_drivers = device_manager.list_drivers()

        recovery_drivers = []

        for driver_name in available_drivers:
            try:
                # Get driver instance
                driver_instance = device_manager.get_driver_instance(driver_name)
                if driver_instance and hasattr(driver_instance, 'get_supported_recovery_operations'):
                    # Get supported recovery operations
                    recovery_operations = driver_instance.get_supported_recovery_operations()

                    if recovery_operations:
                        recovery_drivers.append({
                            'driver_name': driver_name,
                            'recovery_operations': recovery_operations,
                            'operation_count': len(recovery_operations)
                        })

            except Exception as e:
                logger.warning(f"Error checking recovery support for driver {driver_name}: {str(e)}")
                continue

        return JsonResponse({
            'status': 'success',
            'message': f'Found {len(recovery_drivers)} recovery-capable drivers',
            'recovery_drivers': recovery_drivers,
            'total_drivers': len(available_drivers),
            'recovery_capable_count': len(recovery_drivers)
        })

    except Exception as e:
        logger.error(f"Error listing recovery drivers: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to list recovery drivers: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def execute_recovery(request, driver_name):
    """
    Execute a recovery operation on a specific device driver

    Args:
        driver_name: Name of the device driver

    Expected JSON body:
    {
        "recovery_type": "flash_firmware_sram|flash_firmware_spiflash|flash_bitstream|load_sram|openocd_attach",
        "device_id": "optional_device_id",
        "firmware_name": "optional_firmware_name",
        "target": "optional_target_specification",
        "options": {...}  // Additional driver-specific options
    }

    Returns:
        JSON response with recovery operation result
    """
    try:
        data = json.loads(request.body)
        recovery_type = data.get('recovery_type')
        device_id = data.get('device_id')

        if not recovery_type:
            return JsonResponse({
                'status': 'error',
                'message': 'recovery_type is required'
            }, status=400)

        device_manager = get_device_driver_manager()

        # Verify driver exists
        available_drivers = device_manager.list_drivers()
        if driver_name not in available_drivers:
            return JsonResponse({
                'status': 'error',
                'message': f'Driver {driver_name} not found. Available drivers: {available_drivers}'
            }, status=404)

        # Get driver instance
        driver_instance = device_manager.get_driver_instance(driver_name)
        if not driver_instance:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to get driver instance for {driver_name}'
            }, status=500)

        # Check if driver supports recovery operations
        if not hasattr(driver_instance, 'recovery'):
            return JsonResponse({
                'status': 'error',
                'message': f'Driver {driver_name} does not support recovery operations'
            }, status=400)

        # Get supported recovery operations
        supported_operations = driver_instance.get_supported_recovery_operations()
        if recovery_type not in supported_operations:
            return JsonResponse({
                'status': 'error',
                'message': f'Recovery operation {recovery_type} not supported by {driver_name}. Supported: {supported_operations}'
            }, status=400)

        # For recovery operations, we may not need a specific device instance
        # Create a minimal device object for the recovery operation
        from iotsploit_core.domain.device import Device, DeviceType

        if device_id:
            # Try to get existing device
            device = Device(
                device_id=device_id,
                name=f"Recovery Device ({driver_name})",
                device_type=DeviceType.USB  # Default type, may be overridden by driver
            )
        else:
            # Create a generic recovery device
            device = Device(
                device_id=f"recovery_{driver_name}",
                name=f"Recovery Device ({driver_name})",
                device_type=DeviceType.USB
            )

        # Prepare recovery parameters
        recovery_kwargs = {
            'firmware_name': data.get('firmware_name'),
            'target': data.get('target'),
            'options': data.get('options', {}),
            'device_id': device_id
        }

        # Remove None values
        recovery_kwargs = {k: v for k, v in recovery_kwargs.items() if v is not None}

        # Execute recovery operation
        logger.info(f"Executing recovery operation '{recovery_type}' on driver '{driver_name}'")
        result = driver_instance.recovery(device, recovery_type, **recovery_kwargs)

        # Log the result
        logger.info(f"Recovery operation completed with status: {result.get('status')}")

        return JsonResponse({
            'status': 'success',
            'driver_name': driver_name,
            'recovery_type': recovery_type,
            'result': result
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error executing recovery operation: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to execute recovery operation: {str(e)}'
        }, status=500)
