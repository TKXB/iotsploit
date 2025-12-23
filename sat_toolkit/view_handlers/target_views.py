from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from sat_toolkit.adapters.django.target_models import TargetManager
from sat_toolkit.domain.target import ComponentFactory
from sat_toolkit.tools.xlogger import xlog
import json

logger = xlog.get_logger('target_views')

def list_targets(request):
    """
    GET
    Returns a list of all targets
    """
    target_manager = TargetManager.get_instance()
    all_targets = target_manager.get_all_targets()
    
    if all_targets:
        result = {
            "status": "success",
            "targets": all_targets
        }
    else:
        result = {
            "status": "success",
            "targets": [],
            "message": "No targets available."
        }
    
    return JsonResponse(result)

@csrf_exempt
def select_target(request):
    """
    POST
    Select a target for testing
    
    Expected JSON body:
    {
        "target_id": "target_id_to_select"
    }
    """
    if request.method != 'POST':
        logger.debug("select_target: Invalid method, only POST allowed")
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
        
    try:
        logger.debug("select_target: Starting target selection process")
        
        data = json.loads(request.body)
        target_id = data.get('target_id')
        logger.debug(f"select_target: Received request to select target_id: {target_id}")
        
        if not target_id:
            logger.debug("select_target: No target_id provided in request")
            return JsonResponse({'error': 'target_id is required'}, status=400)

        target_manager = TargetManager.get_instance()
        targets = target_manager.get_all_targets()
        logger.debug(f"select_target: Found {len(targets)} total targets in database")
        
        # Log available targets for debugging
        if targets:
            logger.debug("select_target: Available targets:")
            for i, target in enumerate(targets):
                logger.debug(f"  [{i+1}] {target.get('target_id', 'Unknown ID')} - {target.get('name', 'Unknown Name')} ({target.get('type', 'Unknown Type')})")
        else:
            logger.debug("select_target: No targets found in database")
        
        # Find the target with the matching ID
        selected_target = next((t for t in targets if t['target_id'] == target_id), None)
        if not selected_target:
            logger.debug(f"select_target: Target with ID '{target_id}' not found in available targets")
            return JsonResponse({'error': 'Target not found'}, status=404)
        
        logger.debug(f"select_target: Found target: {selected_target.get('name', 'Unknown')} (Type: {selected_target.get('type', 'Unknown')})")
        
        # Log target details before creating instance
        logger.debug("select_target: Target details:")
        logger.debug(f"  Name: {selected_target.get('name', 'Unknown')}")
        logger.debug(f"  Type: {selected_target.get('type', 'Unknown')}")
        logger.debug(f"  Status: {selected_target.get('status', 'Unknown')}")
        logger.debug(f"  IP Address: {selected_target.get('ip_address', 'None')}")
        logger.debug(f"  Location: {selected_target.get('location', 'None')}")
        
        # Log components if available
        if selected_target.get('components'):
            logger.debug(f"  Components ({len(selected_target['components'])}):")
            for i, comp in enumerate(selected_target['components']):
                logger.debug(f"    [{i+1}] {comp.get('name', 'Unknown')} ({comp.get('type', 'Unknown')})")
                if comp.get('adb_serial_id'):
                    logger.debug(f"        ADB Serial: {comp['adb_serial_id']}")
        else:
            logger.debug("  No components found")
        
        # Log interfaces if available
        if selected_target.get('interfaces'):
            logger.debug(f"  Interfaces ({len(selected_target['interfaces'])}):")
            for i, intf in enumerate(selected_target['interfaces']):
                logger.debug(f"    [{i+1}] {intf.get('name', 'Unknown')} ({intf.get('type', 'Unknown')})")
        else:
            logger.debug("  No interfaces found")
        
        # Create a target instance and set it as current
        logger.debug("select_target: Creating target instance")
        target_instance = target_manager.create_target_instance(selected_target)
        logger.debug(f"select_target: Created target instance of type: {type(target_instance).__name__}")
        
        logger.debug("select_target: Setting as current target")
        target_manager.set_current_target(target_instance)
        
        # Verify the target was set correctly
        current_target = target_manager.get_current_target()
        if current_target:
            logger.debug(f"select_target: Successfully set current target: {current_target.name}")
            
            # Log ADB devices if this is a vehicle target
            if hasattr(current_target, 'get_adb_devices'):
                adb_devices = current_target.get_adb_devices()
                if adb_devices:
                    logger.debug(f"select_target: Available ADB devices in target:")
                    for name, device in adb_devices.items():
                        logger.debug(f"  {name}: {device.adb_serial_id}")
                else:
                    logger.debug("select_target: No ADB devices found in target")
        else:
            logger.warning("select_target: Failed to set current target - current target is None")
        
        logger.debug("select_target: Target selection completed successfully")
        return JsonResponse({
            'status': 'success', 
            'message': 'Target selected successfully',
            'target': selected_target
        })
    except json.JSONDecodeError as e:
        logger.error(f"select_target: Invalid JSON in request body: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"select_target: Error selecting target: {str(e)}")
        logger.debug(f"select_target: Exception details: {type(e).__name__}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def edit_target(request):
    """
    POST
    Edit an existing target in the database
    
    Expected JSON body:
    {
        "target_id": "target_id_to_edit",
        "updates": {
            "name": "new_name",
            "status": "new_status", 
            "ip_address": "new_ip",
            "location": "new_location",
            "properties": {
                "key": "value"
            }
        }
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        target_id = data.get('target_id')
        updates = data.get('updates', {})
        
        if not target_id:
            return JsonResponse({'error': 'target_id is required'}, status=400)
            
        if not updates:
            return JsonResponse({'error': 'updates are required'}, status=400)

        target_manager = TargetManager.get_instance()
        targets = target_manager.get_all_targets()
        
        # Find the target with the matching ID
        target = next((t for t in targets if t['target_id'] == target_id), None)
        if not target:
            return JsonResponse({'error': 'Target not found'}, status=404)
        
        # Log the incoming updates for debugging
        logger.debug(f"Received updates for target {target_id}: {updates}")
        
        # Apply updates to the target
        for key, value in updates.items():
            if key in ['name', 'status', 'ip_address', 'location', 'components', 'interfaces']:
                target[key] = value
                logger.debug(f"Updated {key}: {value}")
            elif key == 'properties' and isinstance(value, dict):
                # Replace properties completely
                target['properties'] = value
                logger.debug(f"Updated properties: {value}")
        
        logger.debug(f"Final target data before database update: {target}")
        
        # Special handling for components and interfaces to ensure they're properly formatted
        if 'components' in target:
            logger.debug(f"Components to update: {target['components']}")
        if 'interfaces' in target:
            logger.debug(f"Interfaces to update: {target['interfaces']}")
        
        # Update the target in the database
        success = target_manager.update_target(target)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully updated target {target_id}',
                'target': target
            })
        else:
            return JsonResponse({'error': f'Failed to update target {target_id}'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error editing target: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def create_target(request):
    """
    POST
    Create a new target in the database
    
    Expected JSON body:
    {
        "target_id": "unique_target_id",
        "name": "target_name",
        "type": "vehicle|smartphone|camera|router",
        "status": "active|inactive",
        "ip_address": "optional_ip_address",
        "location": "optional_location",
        "properties": {
            "key": "value"
        },
        "components": [],
        "interfaces": []
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        
        # Required fields
        required_fields = ['target_id', 'name', 'type']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'{field} is required'}, status=400)
        
        target_manager = TargetManager.get_instance()
        
        # Check if target_id already exists
        existing_targets = target_manager.get_all_targets()
        if any(t['target_id'] == data['target_id'] for t in existing_targets):
            return JsonResponse({'error': 'Target ID already exists'}, status=400)
        
        # Set default values
        target_data = {
            'target_id': data['target_id'],
            'name': data['name'],
            'type': data['type'],
            'status': data.get('status', 'active'),
            'ip_address': data.get('ip_address'),
            'location': data.get('location'),
            'properties': data.get('properties', {}),
            'components': data.get('components', []),
            'interfaces': data.get('interfaces', [])
        }
        
        # Add the target to the database
        success = target_manager.add_target(target_data)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully created target {target_data["target_id"]}',
                'target': target_data
            })
        else:
            return JsonResponse({'error': f'Failed to create target {target_data["target_id"]}'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error creating target: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def delete_target(request):
    """
    POST
    Delete a target from the database
    
    Expected JSON body:
    {
        "target_id": "target_id_to_delete"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        target_id = data.get('target_id')
        
        if not target_id:
            return JsonResponse({'error': 'target_id is required'}, status=400)

        target_manager = TargetManager.get_instance()
        
        # Check if target exists
        targets = target_manager.get_all_targets()
        target = next((t for t in targets if t['target_id'] == target_id), None)
        if not target:
            return JsonResponse({'error': 'Target not found'}, status=404)
        
        # Delete the target
        success = target_manager.delete_target(target_id)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully deleted target {target_id}'
            })
        else:
            return JsonResponse({'error': f'Failed to delete target {target_id}'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error deleting target: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

def get_current_target(request):
    """
    GET
    Get the currently selected target
    """
    target_manager = TargetManager.get_instance()
    current_target = target_manager.get_current_target()
    
    if current_target:
        return JsonResponse({
            'status': 'success',
            'target': current_target.get_info()
        })
    else:
        return JsonResponse({
            'status': 'success',
            'target': None,
            'message': 'No target currently selected'
        })

def get_component_types(request):
    """
    GET
    Get list of supported component types
    """
    try:
        supported_types = ComponentFactory.get_supported_types()
        return JsonResponse({
            'status': 'success',
            'component_types': supported_types
        })
    except Exception as e:
        logger.error(f"Error getting component types: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500) 