from django.http import HttpResponse
from django.http import HttpRequest
from django.shortcuts import redirect

from sat_toolkit.tools.report_mgr import Report_Mgr

from sat_toolkit.tools.monitor_mgr import Pi_Mgr
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.core.exploit_spec import ExploitResult
from sat_toolkit.core.base_plugin import BasePlugin, BaseDeviceDriver
from sat_toolkit.core.device_manager import DeviceDriverManager
from sat_toolkit.models.Plugin_Model import Plugin

from sat_toolkit.tools.xlogger import xlog

import logging
logger = xlog.get_logger('views')

import json
import datetime

from sat_toolkit.core.device_manager import DeviceDriverManager  
from sat_toolkit.models.Target_Model import TargetManager
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree
from sat_toolkit.models.PluginSequence_Model import PluginSequence
from sat_toolkit.models.Device_Model import DeviceManager
from asgiref.sync import async_to_sync

import asyncio

from celery.result import AsyncResult
from .tasks import execute_plugin_task

from sat_toolkit.core.stream_manager import StreamManager


def __calc_emsp_str(toc_level):
    emsp_str = ""
    while toc_level > 0:
        emsp_str = "&emsp;" + emsp_str
        toc_level -= 1
    return emsp_str

def __expand_toc_list(tree_list, expand_list):
    for item in tree_list:
        if isinstance(item, list):
            __expand_toc_list(item, expand_list)
        else:
            #{"test_project":record_dict["test_case"], "toc_level":record_dict["testcase_toc"], "status":"进行中"}, []]
            # "title": child_node,
            # "status": {"result": "通过","color": "green"}
            toc_dict = {
                "title": __calc_emsp_str(item["toc_level"]) + "└" + str(item["test_project"]),
                "status": {"result": "进行中","color": "yellow"}
            }
            if item["status"] == "通过":
                toc_dict["status"] = {"result": "通过","color": "green"}
            if item["status"] == "完成":
                toc_dict["status"] = {"result": "完成","color": "blue"}
            if item["status"] == "不通过":
                toc_dict["status"] = {"result": "不通过","color": "red"}
            if item["status"] == "失败":
                toc_dict["status"] = {"result": "失败","color": "red"}     

            expand_list.append(toc_dict)

def __build_single_choice_dialog(title:str, choice_list:list, button_list:list):
    single_choice_list = []
    for choice in choice_list:
        single_choice_list.append(str(choice))

    single_choce_dict = { 
        "type": "single_choice",
        "single_choice": single_choice_list,
        "buttonlist": button_list
        }
    logger.info("Build Single Choice Dialog:{}".format(single_choce_dict))
    return single_choce_dict

def __build_confirm_dialog(title:str, button_list:list):
    confirm_dict = { 
        "type": "confirm",
        "confirm": title,
        "buttonlist": button_list
        }
    logger.info("Build Confirm Dialog:{}".format(confirm_dict))
    return confirm_dict


    user_input_id = request.GET.get("id", "")
    sub_func = sub_func_dict.get(user_input_id)
    if sub_func != None:
        return sub_func(request)
    else:
        logger.error("User Input ID:{} Invalid!".format(user_input_id))
        return HttpResponse("User Input ID:{} Invalid!".format(user_input_id))

def list_plugins(request):
    plugin_manager = ExploitPluginManager()
    plugins = plugin_manager.list_plugins()
    return JsonResponse({'plugins': plugins})

def list_device_drivers(request):
    """
    GET
    Returns a list of available device drivers
    """
    device_manager = DeviceDriverManager()
    available_drivers = device_manager.list_drivers()
    
    if available_drivers:
        result = {
            "status": "success",
            "drivers": available_drivers
        }
    else:
        result = {
            "status": "success",
            "drivers": [],
            "message": "No device drivers available."
        }
    
    return JsonResponse(result)

@csrf_exempt
def execute_plugin(request):
    """
    POST
    Execute a plugin either synchronously or asynchronously based on plugin type or request parameters.
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        logger.info(f"Received POST data for execute_plugin: {data}")
        
        plugin_name = data.get('plugin_name')
        parameters = data.get('parameters', {})
        
        if not plugin_name:
            return JsonResponse({
                "status": "error",
                "message": "Plugin name is required"
            }, status=400)

        # Get the current target
        target_manager = TargetManager.get_instance()
        current_target = target_manager.get_current_target()
        
        # If no current target, select the first available vehicle target
        if not current_target:
            logger.debug("No current target, selecting first available vehicle target")
            all_targets = target_manager.get_all_targets()
            vehicle_targets = [t for t in all_targets if t.get('type') == 'vehicle']
            
            if vehicle_targets:
                try:
                    # Convert dict to Vehicle object
                    selected_target = target_manager.create_target_instance(vehicle_targets[0])
                    target_manager.set_current_target(selected_target)
                    current_target = selected_target
                    logger.info(f"Automatically selected vehicle target: {selected_target.name}")
                except Exception as e:
                    logger.error(f"Error creating vehicle target: {str(e)}")
                    return JsonResponse({
                        "status": "error",
                        "message": f"Error creating vehicle target: {str(e)}"
                    }, status=400)
            else:
                logger.error("No vehicle targets available to select.")
                return JsonResponse({
                    "status": "error",
                    "message": "No vehicle targets available to select."
                }, status=400)
        elif isinstance(current_target, dict):
            try:
                # Convert dict to Vehicle object if needed
                current_target = target_manager.create_target_instance(current_target)
            except Exception as e:
                logger.error(f"Error converting current target to Vehicle object: {str(e)}")
                return JsonResponse({
                    "status": "error",
                    "message": f"Error converting current target to Vehicle object: {str(e)}"
                }, status=400)

        plugin_manager = ExploitPluginManager()
        plugin_manager.initialize()

        # Let ExploitPluginManager handle the execution mode
        result = plugin_manager.execute_plugin(plugin_name, target=current_target, parameters=parameters)
        
        if isinstance(result, dict) and result.get('execution_type') == 'async':
            # For async execution, return task information
            response = {
                "status": "success", 
                "execution_type": "async",
                "task_id": result.get('task_id'),
                "message": "Async execution started",
                "websocket_url": f"/ws/exploit/{result.get('task_id')}/"
            }
            logger.debug(f"Async execution response: {response}")
            return JsonResponse(response)
        else:
            # For sync execution, return the result directly
            if result is None:
                return JsonResponse({
                    "status": "error",
                    "execution_type": "sync",
                    "message": f"Plugin {plugin_name} execution failed"
                }, status=400)
                
            response_data = {
                "status": "success",
                "execution_type": "sync",
                "result": result
            }
            
            logger.debug(f"Plugin execution result: {response_data}")
            return JsonResponse(response_data)
            
    except Exception as e:
        logger.error(f"Error executing plugin: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Error executing plugin: {str(e)}"
        }, status=500)

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

def list_plugin_info(request):
    """
    GET
    Returns information about all available plugins with status indicators.
    """
    plugin_manager = ExploitPluginManager()
    
    try:
        # Get plugin info
        plugin_info_dict = plugin_manager.list_plugin_info()
        
        # Get plugin database entries to access file paths
        from sat_toolkit.models.Plugin_Model import Plugin
        plugin_db_entries = {p.name: p for p in Plugin.objects.all()}
        
        # Format the response with success/failure indicators
        formatted_plugins = []
        has_valid_plugins = False
        
        for plugin_name, info in plugin_info_dict.items():
            # Get the plugin path from the database
            plugin_path = None
            if plugin_name in plugin_db_entries:
                db_entry = plugin_db_entries[plugin_name]
                # Extract the file path from the module path
                if db_entry.module_path:
                    module_parts = db_entry.module_path.split('.')
                    # Convert module path to file path
                    file_path = '/'.join(module_parts[:-1]) + '.py'
                    plugin_path = file_path
            
            plugin_entry = {
                "name": plugin_name,
                "info": info,
                "status": "success" if "error" not in info else "failure",
                "path": plugin_path
            }
            formatted_plugins.append(plugin_entry)
            if "error" not in info:
                has_valid_plugins = True
        
        response = {
            "status": "success" if has_valid_plugins else "partial",
            "message": "Successfully retrieved plugin information" if has_valid_plugins 
                      else "Some plugins failed to load properly",
            "plugins": formatted_plugins,
            "total_plugins": len(formatted_plugins),
            "valid_plugins": sum(1 for p in formatted_plugins if p["status"] == "success")
        }
        
        logger.debug(f"Retrieved plugin info: {response}")
        return JsonResponse(response)
        
    except Exception as e:
        logger.error(f"Error retrieving plugin information: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to retrieve plugin information: {str(e)}",
            "plugins": []
        }, status=500)

def list_groups(request):
    """
    GET
    Returns information about all available plugin groups and their relationships
    """
    try:
        groups = PluginGroup.objects.all()
        
        if not groups.exists():
            return JsonResponse({
                "status": "success",
                "message": "No plugin groups available.",
                "groups": []
            })

        formatted_groups = []
        for group in groups:
            # Get parent/child relationships
            parent_relations = PluginGroupTree.objects.filter(child=group)
            child_relations = PluginGroupTree.objects.filter(parent=group)
            
            # Format plugins in this group with sequence information
            plugins = []
            for seq in group.plugin_sequences():
                plugins.append({
                    "name": seq.plugin.name,
                    "enabled": seq.plugin.enabled,
                    "description": seq.plugin.description,
                    "sequence": seq.sequence,
                    "ignore_fail": seq.ignore_fail
                })
            
            # Format parent groups with sequence and ignore_fail
            parent_groups = [{
                "name": relation.parent.name,
                "force_exec": relation.force_exec,
                "sequence": relation.sequence,
                "ignore_fail": relation.ignore_fail
            } for relation in parent_relations]
            
            # Format child groups with sequence and ignore_fail
            child_groups = [{
                "name": relation.child.name,
                "force_exec": relation.force_exec,
                "sequence": relation.sequence,
                "ignore_fail": relation.ignore_fail
            } for relation in child_relations]
            
            # Create group entry
            group_entry = {
                "name": group.name,
                "description": group.description,
                "enabled": group.enabled,
                "plugins": plugins,
                "parent_groups": parent_groups,
                "child_groups": child_groups
            }
            
            formatted_groups.append(group_entry)

        return JsonResponse({
            "status": "success",
            "message": f"Found {len(formatted_groups)} plugin groups",
            "groups": formatted_groups
        })

    except Exception as e:
        logger.error(f"Error listing plugin groups: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to list plugin groups: {str(e)}",
            "groups": []
        }, status=500)

@csrf_exempt
def execute_group(request):
    """
    POST
    Execute plugins in a selected group with proper sequence and failure handling
    
    Expected JSON body:
    {
        "group_name": "name_of_group",
        "force_exec": true/false (optional, default: true),
        "target": {...} (optional target data),
        "parameters": {...} (optional parameters for plugins)
    }
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        group_name = data.get('group_name')
        force_exec = data.get('force_exec', True)
        target_data = data.get('target')
        parameters = data.get('parameters')
        
        if not group_name:
            return JsonResponse({
                "status": "error",
                "message": "Group name is required"
            }, status=400)
            
        # Get the plugin group
        try:
            group = PluginGroup.objects.get(name=group_name)
        except PluginGroup.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": f"Group '{group_name}' not found"
            }, status=404)
            
        # Check if group is enabled
        if not group.enabled and not force_exec:
            return JsonResponse({
                "status": "warning",
                "message": f"Group '{group_name}' is disabled"
            })
            
        # Set up target if provided
        target = None
        if target_data:
            # Create a target instance from the provided data
            target_manager = TargetManager.get_instance()
            try:
                target = target_manager.create_target_instance(target_data)
            except Exception as e:
                logger.warning(f"Could not create target from provided data: {str(e)}")
                # Fall back to current target
                target = target_manager.get_current_target()
        else:
            # Use current target
            target_manager = TargetManager.get_instance()
            target = target_manager.get_current_target()
            
        # Get plugin manager
        plugin_manager = ExploitPluginManager()
            
        # Execute the group
        logger.info(f"Executing plugin group: {group_name}")
        result = plugin_manager.execute_plugin_group(
            group_name=group_name,
            target=target,
            parameters=parameters,
            force_exec=force_exec
        )
        
        # Build response based on execution result
        if result:
            response = {
                "status": "success",
                "message": f"Plugin group '{group_name}' executed successfully",
                "result": result
            }
        else:
            response = {
                "status": "warning",
                "message": f"Plugin group '{group_name}' execution completed with failures",
                "result": result
            }
            
        return JsonResponse(response)
            
    except Exception as e:
        logger.error(f"Error executing plugin group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to execute plugin group: {str(e)}"
        }, status=500)

@csrf_exempt
def select_target(request):
    """
    Select a target for testing
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
            'message': 'Target selected successfully',
            'target': selected_target
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def execute_plugin_async(request):
    """
    POST
    Execute a plugin asynchronously and return a task ID for tracking progress
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        plugin_name = data.get('plugin_name')
        parameters = data.get('parameters', {})
        
        if not plugin_name:
            return JsonResponse({
                "status": "error",
                "message": "Plugin name is required"
            }, status=400)

        # Get the current target
        target_manager = TargetManager.get_instance()
        current_target = target_manager.get_current_target()
        
        # Start Celery task
        logger.info(f"Starting Celery task for plugin: {plugin_name}")
        task = execute_plugin_task.delay(
            plugin_name,
            target=current_target,
            parameters=parameters
        )
        
        return JsonResponse({
            "status": "success",
            "task_id": task.id,
            "message": "Async execution started",
            "websocket_url": f"/ws/exploit/{task.id}/"
        })
        
    except Exception as e:
        logger.error(f"Error executing async plugin: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Error executing async plugin: {str(e)}"
        }, status=500)

@csrf_exempt
def stop_plugin_async(request):
    """
    POST
    Stop an async plugin execution by task ID
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        
        if not task_id:
            return JsonResponse({
                "status": "error",
                "message": "Task ID is required"
            }, status=400)

        # Revoke Celery task
        AsyncResult(task_id).revoke(terminate=True)
        
        return JsonResponse({
            "status": "success",
            "message": f"Task {task_id} stopped successfully"
        })
        
    except Exception as e:
        logger.error(f"Error stopping async plugin: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Error stopping async plugin: {str(e)}"
        }, status=500)

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

def list_device_commands(request, device_name):
    """
    GET
    Returns a list of available commands for a specific device driver
    
    Parameters:
        device_name (str): Name of the device driver (e.g., 'drv_socketcan')
    
    Returns:
        JSON response containing the available commands and their descriptions
    """
    try:
        device_manager = DeviceDriverManager()
        
        # Verify the device exists
        available_devices = device_manager.list_drivers()
        if device_name not in available_devices:
            return JsonResponse({
                "status": "error",
                "message": f"Device '{device_name}' not found. Available devices: {available_devices}"
            }, status=404)
        
        # Get commands for the selected device
        commands = device_manager.get_plugin_commands(device_name)
        
        if not commands:
            return JsonResponse({
                "status": "success",
                "message": f"No commands available for device: {device_name}",
                "commands": {}
            })
            
        return JsonResponse({
            "status": "success",
            "device": device_name,
            "commands": commands
        })
        
    except Exception as e:
        logger.error(f"Error listing device commands: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to list device commands: {str(e)}"
        }, status=500)

@csrf_exempt
def execute_device_command(request, driver_name):
    """
    POST
    Execute a command on a specific device
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        # 打印原始请求体
        logger.info(f"Raw request body: {request.body}")
        
        data = json.loads(request.body)
        command = data.get('command')
        device_id = data.get('device_id')
        args = data.get('args', '')
        
        if not command:
            return JsonResponse({
                "status": "error",
                "message": "Command name is required"
            }, status=400)

        # 使用 DeviceDriverManager 执行命令
        device_manager = DeviceDriverManager()
        result = device_manager.execute_command(
            driver_name=driver_name,
            command=command,
            device_id=device_id,
            args=args
        )
        
        return JsonResponse(result)

    except Exception as e:
        logger.error(f"Error executing device command: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to execute device command: {str(e)}"
        }, status=500)

@csrf_exempt
def create_group(request):
    """
    POST
    Create a new plugin group with selected plugins
    
    Expected JSON body:
    {
        "group_name": "name_of_group",
        "group_description": "optional description",
        "selected_plugins": [
            {"name": "plugin1", "sequence": 10, "ignore_fail": false},
            {"name": "plugin2", "sequence": 20, "ignore_fail": true}
        ],
        "nest_group": true/false,
        "parent_group_name": "optional_parent_name",  # Required if nest_group is true
        "parent_options": {                          # Optional settings for parent relation
            "sequence": 100,
            "ignore_fail": false,
            "force_exec": true
        }
    }
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        group_name = data.get('group_name')
        group_description = data.get('group_description', '')
        selected_plugins = data.get('selected_plugins', [])
        nest_group = data.get('nest_group', False)
        
        if not group_name:
            return JsonResponse({
                "status": "error",
                "message": "Group name is required"
            }, status=400)
            
        # Create or update the plugin group
        group, created = PluginGroup.objects.get_or_create(
            name=group_name,
            defaults={
                'description': group_description,
                'enabled': True
            }
        )
        
        if not created:
            # Update existing group
            group.description = group_description
            group.save()
            # Clear existing plugin sequences to avoid duplicates
            from sat_toolkit.models.PluginSequence_Model import PluginSequence
            PluginSequence.objects.filter(plugingroup=group).delete()
        
        # Add selected plugins to the group with sequence information
        added_plugins = []
        for plugin_item in selected_plugins:
            # Handle both simple string format and detailed object format
            if isinstance(plugin_item, str):
                plugin_name = plugin_item
                sequence = 100  # Default sequence
                ignore_fail = False  # Default ignore_fail
            else:
                plugin_name = plugin_item.get('name')
                sequence = plugin_item.get('sequence', 100)
                ignore_fail = plugin_item.get('ignore_fail', False)
            
            if not plugin_name:
                continue
                
            plugin, _ = Plugin.objects.get_or_create(
                name=plugin_name,
                defaults={
                    'description': f'Plugin {plugin_name}',
                    'enabled': True,
                    'module_path': f'plugins.exploits.{plugin_name}'
                }
            )
            
            # Create the sequence entry
            from sat_toolkit.models.PluginSequence_Model import PluginSequence
            plugin_seq = PluginSequence.objects.create(
                plugingroup=group,
                plugin=plugin,
                sequence=sequence,
                ignore_fail=ignore_fail
            )
            
            added_plugins.append({
                'name': plugin_name,
                'sequence': sequence,
                'ignore_fail': ignore_fail
            })
        
        # Handle nesting under another group if requested
        if nest_group:
            parent_group_name = data.get('parent_group_name')
            parent_options = data.get('parent_options', {})
            
            if not parent_group_name:
                return JsonResponse({
                    "status": "error",
                    "message": "Parent group name is required when nesting"
                }, status=400)
            
            try:
                parent_group = PluginGroup.objects.get(name=parent_group_name)
                
                # Get options for the parent-child relationship
                force_exec = parent_options.get('force_exec', True)
                sequence = parent_options.get('sequence', 100)
                ignore_fail = parent_options.get('ignore_fail', False)
                
                # Create or update the tree relationship
                tree, _ = PluginGroupTree.objects.update_or_create(
                    parent=parent_group,
                    child=group,
                    defaults={
                        'force_exec': force_exec,
                        'sequence': sequence,
                        'ignore_fail': ignore_fail
                    }
                )
            except PluginGroup.DoesNotExist:
                return JsonResponse({
                    "status": "warning",
                    "message": f"Parent group {parent_group_name} not found",
                    "group": {
                        "name": group.name,
                        "description": group.description,
                        "plugins": added_plugins
                    }
                })
        
        # Show group details in response
        response_data = {
            "status": "success",
            "message": f"Successfully {'created' if created else 'updated'} group '{group_name}'",
            "group": {
                "name": group.name,
                "description": group.description,
                "enabled": group.enabled,
                "plugins": added_plugins,
                "plugins_count": group.plugins_count()
            }
        }
        
        if nest_group:
            parent_options = data.get('parent_options', {})
            response_data["group"]["parent_group"] = parent_group_name
            response_data["group"]["parent_options"] = {
                "force_exec": parent_options.get('force_exec', True),
                "sequence": parent_options.get('sequence', 100),
                "ignore_fail": parent_options.get('ignore_fail', False)
            }
            
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error creating plugin group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to create plugin group: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_group(request):
    """
    POST
    Delete a plugin group
    
    Expected JSON body:
    {
        "group_name": "name_of_group_to_delete"
    }
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        group_name = data.get('group_name')
        
        if not group_name:
            return JsonResponse({
                "status": "error",
                "message": "Group name is required"
            }, status=400)
            
        try:
            group = PluginGroup.objects.get(name=group_name)
            group.delete()
            
            return JsonResponse({
                "status": "success",
                "message": f"Successfully deleted group: {group_name}"
            })
            
        except PluginGroup.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": f"Group not found: {group_name}"
            }, status=404)
            
    except Exception as e:
        logger.error(f"Error deleting group: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to delete group: {str(e)}"
        }, status=500)

def list_urls(request):
    """
    GET
    Returns a list of all available API endpoints
    """
    try:
        from .urls import get_url_patterns
        
        url_patterns = get_url_patterns()
        
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
def cleanup_plugins(request):
    """
    POST
    Cleanup all plugins and their resources
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        plugin_manager = ExploitPluginManager()
        plugin_manager.cleanup_all_plugins()
        
        return JsonResponse({
            "status": "success",
            "message": "All plugins cleaned up successfully"
        })
        
    except Exception as e:
        logger.error(f"Error cleaning up plugins: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to cleanup plugins: {str(e)}"
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

@csrf_exempt
def get_plugin_code(request):
    """
    API endpoint to get the code of a plugin file
    
    POST parameters:
    - plugin_path: Path to the plugin file
    
    Returns:
    - JSON response with the plugin code
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'})
    
    try:
        data = json.loads(request.body)
        plugin_path = data.get('plugin_path')
        
        if not plugin_path:
            return JsonResponse({'status': 'error', 'message': 'Plugin path is required'})
        
        # Security check to prevent directory traversal
        if '..' in plugin_path or plugin_path.startswith('/'):
            return JsonResponse({'status': 'error', 'message': 'Invalid plugin path'})
        
        # Ensure the path is within the plugins directory
        if not plugin_path.startswith('plugins/'):
            plugin_path = f'plugins/{plugin_path}'
        
        try:
            with open(plugin_path, 'r') as file:
                code = file.read()
            
            return JsonResponse({
                'status': 'success',
                'code': code
            })
        except FileNotFoundError:
            return JsonResponse({'status': 'error', 'message': f'Plugin file not found: {plugin_path}'})
        except Exception as e:
            logger.error(f"Error reading plugin file: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Error reading plugin file: {str(e)}'})
    
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in get_plugin_code: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'})

@csrf_exempt
def save_plugin_code(request):
    """
    API endpoint to save the code of a plugin file
    
    POST parameters:
    - plugin_path: Path to the plugin file
    - code: New content for the plugin file
    
    Returns:
    - JSON response indicating success or failure
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'})
    
    try:
        data = json.loads(request.body)
        plugin_path = data.get('plugin_path')
        code = data.get('code')
        
        if not plugin_path:
            return JsonResponse({'status': 'error', 'message': 'Plugin path is required'})
        
        if code is None:
            return JsonResponse({'status': 'error', 'message': 'Plugin code is required'})
        
        # Security check to prevent directory traversal
        if '..' in plugin_path or plugin_path.startswith('/'):
            return JsonResponse({'status': 'error', 'message': 'Invalid plugin path'})
        
        # Ensure the path is within the plugins directory
        if not plugin_path.startswith('plugins/'):
            plugin_path = f'plugins/{plugin_path}'
        
        try:
            # Create a backup of the original file
            import os
            import shutil
            from datetime import datetime
            
            if os.path.exists(plugin_path):
                backup_dir = os.path.join(os.path.dirname(plugin_path), 'backups')
                os.makedirs(backup_dir, exist_ok=True)
                
                filename = os.path.basename(plugin_path)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = os.path.join(backup_dir, f"{filename}.{timestamp}.bak")
                
                shutil.copy2(plugin_path, backup_path)
                logger.info(f"Created backup of {plugin_path} at {backup_path}")
            
            # Write the new code to the file
            with open(plugin_path, 'w') as file:
                file.write(code)
            
            # Reload the plugin if it's already loaded
            plugin_manager = ExploitPluginManager()
            plugin_name = os.path.basename(plugin_path).replace('.py', '')
            
            try:
                plugin_manager.reload_plugin(plugin_name)
                logger.info(f"Reloaded plugin: {plugin_name}")
            except Exception as e:
                logger.warning(f"Could not reload plugin {plugin_name}: {str(e)}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Plugin saved successfully'
            })
        except Exception as e:
            logger.error(f"Error saving plugin file: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Error saving plugin file: {str(e)}'})
    
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in save_plugin_code: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'})

@csrf_exempt
def file_download(request, file_path=''):
    """
    API endpoint to download files from the firmware directory
    
    Parameters:
        file_path (str): The path of the file to download relative to the firmware directory
    
    Returns:
        File response for download or error message
    """
    try:
        import os
        from django.http import FileResponse, HttpResponse
        from django.utils.encoding import smart_str
        from pathlib import Path
        
        # Base directory for firmware files
        firmware_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'firmware')
        
        # Handle empty path - list available files
        if not file_path:
            try:
                file_list = []
                for root, dirs, files in os.walk(firmware_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, firmware_dir)
                        file_size = os.path.getsize(full_path)
                        # Format file size
                        if file_size < 1024:
                            size_str = f"{file_size} B"
                        elif file_size < 1024*1024:
                            size_str = f"{file_size/1024:.1f} KB"
                        else:
                            size_str = f"{file_size/(1024*1024):.1f} MB"
                        
                        file_list.append({
                            'name': file,
                            'path': rel_path,
                            'size': size_str,
                            'download_url': f"/api/download_firmware/{rel_path}"
                        })
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'Found {len(file_list)} files',
                    'files': file_list
                })
            except Exception as e:
                logger.error(f"Error listing firmware files: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to list firmware files: {str(e)}'
                }, status=500)
        
        # Construct the full file path, ensuring we don't allow directory traversal
        file_path = file_path.replace('..', '').replace('\\', '/').lstrip('/')
        full_path = os.path.normpath(os.path.join(firmware_dir, file_path))
        
        # Security check: ensure the requested file is within the firmware directory
        if not full_path.startswith(os.path.normpath(firmware_dir)):
            logger.warning(f"Security violation: Attempted path traversal: {file_path}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid file path. Access denied.'
            }, status=403)
        
        # Check if file exists
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            logger.error(f"File not found: {full_path}")
            return JsonResponse({
                'status': 'error',
                'message': f'File not found: {file_path}'
            }, status=404)
        
        # Get file name and extension
        file_name = os.path.basename(full_path)
        file_extension = os.path.splitext(file_name)[1].lower()
        
        # Open the file and create a FileResponse
        file = open(full_path, 'rb')
        response = FileResponse(file)
        
        # Set content type based on file extension
        if file_extension == '.pdf':
            response['Content-Type'] = 'application/pdf'
        elif file_extension == '.zip':
            response['Content-Type'] = 'application/zip'
        elif file_extension == '.bin':
            response['Content-Type'] = 'application/octet-stream'
        elif file_extension == '.hex':
            response['Content-Type'] = 'text/plain'
        elif file_extension == '.json':
            response['Content-Type'] = 'application/json'
        else:
            response['Content-Type'] = 'application/octet-stream'
        
        # Set Content-Disposition to attachment to force download
        response['Content-Disposition'] = f'attachment; filename={smart_str(file_name)}'
        
        logger.info(f"Serving download for file: {file_path}")
        return response
        
    except Exception as e:
        logger.error(f"Error in file_download: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error downloading file: {str(e)}'
        }, status=500)

@csrf_exempt
def get_driver_states(request):
    """
    GET
    Get the enabled/disabled state of all device drivers
    
    Returns:
        JSON response with all driver states
    """
    try:
        device_manager = DeviceDriverManager()
        driver_states = device_manager.get_driver_states()
        
        # Format response to include more useful information
        response = {
            "status": "success",
            "driver_count": len(driver_states),
            "enabled_count": sum(1 for state in driver_states.values() if state["enabled"]),
            "disabled_count": sum(1 for state in driver_states.values() if not state["enabled"]),
            "drivers": driver_states
        }
        
        return JsonResponse(response)
    except Exception as e:
        logger.error(f"Error getting driver states: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to get driver states: {str(e)}"
        }, status=500)

@csrf_exempt
def enable_driver(request):
    """
    POST
    Enable a device driver
    
    Expected JSON body:
    {
        "driver_name": "name_of_driver",
        "description": "optional reason for enabling"
    }
    
    Returns:
        JSON response with operation result
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        driver_name = data.get('driver_name')
        description = data.get('description')
        
        if not driver_name:
            return JsonResponse({
                "status": "error",
                "message": "Driver name is required"
            }, status=400)
            
        device_manager = DeviceDriverManager()
        result = device_manager.enable_driver(driver_name, description)
        
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error enabling driver: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to enable driver: {str(e)}"
        }, status=500)

@csrf_exempt
def disable_driver(request):
    """
    POST
    Disable a device driver
    
    Expected JSON body:
    {
        "driver_name": "name_of_driver",
        "description": "optional reason for disabling"
    }
    
    Returns:
        JSON response with operation result
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        data = json.loads(request.body)
        driver_name = data.get('driver_name')
        description = data.get('description')
        
        if not driver_name:
            return JsonResponse({
                "status": "error",
                "message": "Driver name is required"
            }, status=400)
            
        device_manager = DeviceDriverManager()
        result = device_manager.disable_driver(driver_name, description)
        
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error disabling driver: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to disable driver: {str(e)}"
        }, status=500)

