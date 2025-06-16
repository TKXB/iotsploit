from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from sat_toolkit.models.Target_Model import TargetManager
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
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        target_id = data.get('target_id')
        if not target_id:
            return JsonResponse({'error': 'target_id is required'}, status=400)

        target_manager = TargetManager.get_instance()
        targets = target_manager.get_all_targets()
        
        # Find the target with the matching ID
        selected_target = next((t for t in targets if t['target_id'] == target_id), None)
        if not selected_target:
            return JsonResponse({'error': 'Target not found'}, status=404)
        
        # Create a target instance and set it as current
        target_instance = target_manager.create_target_instance(selected_target)
        target_manager.set_current_target(target_instance)
        
        return JsonResponse({
            'status': 'success', 
            'message': 'Target selected successfully',
            'target': selected_target
        })
    except Exception as e:
        logger.error(f"Error selecting target: {str(e)}")
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
        
        # Apply updates to the target
        for key, value in updates.items():
            if key in ['name', 'status', 'ip_address', 'location', 'components', 'interfaces']:
                target[key] = value
            elif key == 'properties' and isinstance(value, dict):
                # Replace properties completely
                target['properties'] = value
        
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
    try:
        target_manager = TargetManager.get_instance()
        current_target = target_manager.get_current_target()
        
        if current_target:
            # Convert target instance to dictionary for JSON response
            if hasattr(current_target, 'get_info'):
                target_info = current_target.get_info()
            else:
                target_info = current_target
                
            return JsonResponse({
                'status': 'success',
                'current_target': target_info
            })
        else:
            return JsonResponse({
                'status': 'success',
                'current_target': None,
                'message': 'No target currently selected'
            })
            
    except Exception as e:
        logger.error(f"Error getting current target: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500) 