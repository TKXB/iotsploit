from django.http import HttpResponse
from django.http import HttpRequest
from django.shortcuts import redirect

from iotsploit_django.tools.report_mgr import Report_Mgr

from iotsploit_django.tools.monitor_mgr import Pi_Mgr
from iotsploit_django.tools.ota_mgr import OTA_Mgr
from iotsploit_django.tools.wifi_mgr import WiFi_Mgr

from iotsploit_django.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from iotsploit_django.composition_root.wiring import (
    ensure_stream_backend_configured,
    get_device_driver_manager,
    get_exploit_plugin_manager,
)
from iotsploit_core.core.exploit_spec import ExploitResult
from iotsploit_core.core.base_plugin import BasePlugin, BaseDeviceDriver
ensure_stream_backend_configured()
from iotsploit_django.adapters.django.plugins.models import Plugin

from iotsploit_django.tools.xlogger import xlog

import logging
logger = xlog.get_logger('views')

import json
import datetime

from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_django.adapters.django.plugins.models import PluginGroup, PluginGroupTree, PluginSequence
from iotsploit_django.adapters.django.device_models import DeviceManager
from asgiref.sync import async_to_sync

import asyncio

from celery.result import AsyncResult
from iotsploit_django.tasks.plugin_tasks import execute_plugin_task

from iotsploit_core.core.stream_manager import StreamManager

from iotsploit_core.core.tool_manager import get_tool_manager

from django.views.decorators.http import require_http_methods


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
    plugin_manager = get_exploit_plugin_manager()
    plugins = plugin_manager.list_plugins()
    return JsonResponse({'plugins': plugins})


@require_http_methods(["GET"])
def list_enabled_exploit_plugins(request):
    """SSOT endpoint for MCP runtime.

    Returns the enabled exploit plugin metas from Django DB (single source of truth).
    """
    try:
        from iotsploit_django.ports_impl.plugin_repo import DjangoPluginMetaRepository

        repo = DjangoPluginMetaRepository()
        metas = repo.list_enabled()
        return JsonResponse(
            {
                "status": "success",
                "plugins": [
                    {
                        "name": m.name,
                        "module_path": m.module_path,
                        "enabled": bool(m.enabled),
                        "description": m.description,
                        "author": m.author,
                        "license": m.license,
                        "parameters": m.parameters or {},
                    }
                    for m in metas
                ],
            }
        )
    except Exception as e:
        logger.error(f"Error listing enabled exploit plugins: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e), "plugins": []}, status=500)


@csrf_exempt
def discovered_exploit_plugins(request):
    """Optional: MCP nodes can report locally discovered plugins for Django to upsert."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST method is allowed"}, status=405)
    try:
        from iotsploit_core.domain.plugin import PluginMeta
        from iotsploit_django.ports_impl.plugin_repo import DjangoPluginMetaRepository

        payload = json.loads(request.body or b"{}")
        items = payload.get("plugins") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return JsonResponse({"status": "error", "message": "Expected a list of plugins"}, status=400)

        repo = DjangoPluginMetaRepository()
        count = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or "").strip()
            module_path = (it.get("module_path") or "").strip()
            if not name or not module_path:
                continue

            meta = PluginMeta(
                name=name,
                module_path=module_path,
                enabled=True,
                description=str(it.get("description", "") or ""),
                author=str(it.get("author", "") or ""),
                license=str(it.get("license", "") or ""),
                parameters=it.get("parameters") if isinstance(it.get("parameters"), dict) else None,
            )
            repo.upsert(meta)
            count += 1

        return JsonResponse({"status": "accepted", "upserted": count})
    except Exception as e:
        logger.error(f"Error upserting discovered exploit plugins: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def enable_exploit_plugin(request, name: str):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST method is allowed"}, status=405)
    try:
        updated = int(Plugin.objects.filter(name=name).update(enabled=True))
        if updated == 0:
            return JsonResponse({"status": "error", "message": f"Plugin '{name}' not found"}, status=404)
        return JsonResponse({"status": "success", "name": name, "enabled": True})
    except Exception as e:
        logger.error(f"Error enabling exploit plugin {name}: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def disable_exploit_plugin(request, name: str):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST method is allowed"}, status=405)
    try:
        updated = int(Plugin.objects.filter(name=name).update(enabled=False))
        if updated == 0:
            return JsonResponse({"status": "error", "message": f"Plugin '{name}' not found"}, status=404)
        return JsonResponse({"status": "success", "name": name, "enabled": False})
    except Exception as e:
        logger.error(f"Error disabling exploit plugin {name}: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def list_enabled_plugin_groups(request):
    """SSOT endpoint for MCP runtime: returns enabled group specs."""
    try:
        from iotsploit_django.ports_impl.plugin_repo import DjangoPluginGroupRepository

        repo = DjangoPluginGroupRepository()
        groups = repo.list_enabled_groups()
        return JsonResponse(
            {
                "status": "success",
                "groups": [
                    {
                        "name": g.name,
                        "enabled": bool(g.enabled),
                        "plugin_steps": [
                            {"sequence": s.sequence, "plugin_name": s.plugin_name, "ignore_fail": bool(s.ignore_fail)}
                            for s in g.plugin_steps
                        ],
                        "group_steps": [
                            {
                                "sequence": s.sequence,
                                "group_name": s.group_name,
                                "ignore_fail": bool(s.ignore_fail),
                                "force_exec": bool(s.force_exec),
                            }
                            for s in g.group_steps
                        ],
                    }
                    for g in groups
                ],
            }
        )
    except Exception as e:
        logger.error(f"Error listing enabled plugin groups: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e), "groups": []}, status=500)


@require_http_methods(["GET"])
def get_plugin_group(request, name: str):
    """SSOT endpoint for MCP runtime: returns a single group spec by name."""
    try:
        from iotsploit_django.ports_impl.plugin_repo import DjangoPluginGroupRepository

        repo = DjangoPluginGroupRepository()
        g = repo.get_group(name)
        if g is None:
            return JsonResponse({"status": "error", "message": f"Group '{name}' not found"}, status=404)
        return JsonResponse(
            {
                "status": "success",
                "group": {
                    "name": g.name,
                    "enabled": bool(g.enabled),
                    "plugin_steps": [
                        {"sequence": s.sequence, "plugin_name": s.plugin_name, "ignore_fail": bool(s.ignore_fail)}
                        for s in g.plugin_steps
                    ],
                    "group_steps": [
                        {
                            "sequence": s.sequence,
                            "group_name": s.group_name,
                            "ignore_fail": bool(s.ignore_fail),
                            "force_exec": bool(s.force_exec),
                        }
                        for s in g.group_steps
                    ],
                },
            }
        )
    except Exception as e:
        logger.error(f"Error getting plugin group {name}: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

def list_device_drivers(request):
    """
    GET
    Returns a list of available device drivers
    """
    device_manager = get_device_driver_manager()
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

        plugin_manager = get_exploit_plugin_manager()
        plugin_manager.initialize()

        # Check if plugin requires root privileges
        plugin_info = plugin_manager.get_plugin_info(plugin_name)
        requires_root = plugin_info and plugin_info.get('RequiresRoot', False)
        
        if requires_root:
            # Use sudo runner for root-required plugins
            logger.info(f"Plugin '{plugin_name}' requires root privileges, using sudo runner")
            from iotsploit_django.tools.privilege_mgr import PrivilegeManager
            
            priv_mgr = PrivilegeManager()
            
            # Convert target to dict for JSON serialization
            target_dict = None
            if current_target:
                if hasattr(current_target, '__dict__'):
                    target_dict = {
                        'name': getattr(current_target, 'name', ''),
                        'ip_address': getattr(current_target, 'ip_address', ''),
                        'type': getattr(current_target, 'type', 'vehicle'),
                        'description': getattr(current_target, 'description', ''),
                        'id': getattr(current_target, 'id', None)
                    }
                elif isinstance(current_target, dict):
                    target_dict = current_target
            
            logger.debug(f"Calling sudo runner with target_dict: {target_dict}, parameters: {parameters}")
            
            # Track timing of the sudo execution
            import time
            start_time = time.time()
            
            # Log the exact plugin name being passed
            logger.info(f"Passing plugin_name to sudo runner: '{plugin_name}'")
            
            success, output = priv_mgr.run_plugin_with_sudo(
                plugin_name=plugin_name,
                target=target_dict,
                parameters=parameters
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            logger.info(f"Django sudo execution completed in {execution_time:.2f} seconds")
            logger.debug(f"Sudo runner returned: success={success}, output length={len(output) if output else 0}")
            logger.debug(f"Raw sudo output: {repr(output[:500])}")  # First 500 chars with escape sequences visible
            
            if success:
                try:
                    # Parse JSON result from Redis
                    import json as json_module
                    logger.debug(f"Attempting to parse JSON: {output[:200]}...")
                    result = json_module.loads(output)
                    logger.debug(f"Successfully parsed JSON result: {result}")
                        
                except json_module.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from Redis result: {e}")
                    logger.error(f"Full Redis result was: {repr(output)}")
                    # Fallback if output is not valid JSON
                    result = {
                        "success": False,
                        "message": f"Plugin executed but result parsing failed: {str(e)}",
                        "data": {"raw_output": output[:200]}
                    }
            else:
                logger.error(f"Sudo execution failed with output: {repr(output)}")
                result = {
                    "success": False,
                    "message": f"Sudo execution failed: {output}",
                    "data": {}
                }
        else:
            # Use normal execution for non-root plugins
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



def list_plugin_info(request):
    """
    GET
    Returns information about all available plugins with status indicators.
    """
    plugin_manager = get_exploit_plugin_manager()
    
    try:
        # Get plugin info
        plugin_info_dict = plugin_manager.list_plugin_info()
        
        # Get plugin database entries to access file paths
        from iotsploit_django.adapters.django.plugins.models import Plugin
        plugin_db_entries = {p.name: p for p in Plugin.objects.all()}
        
        # Format the response with success/failure indicators
        formatted_plugins = []
        has_valid_plugins = False
        
        for plugin_name, info in plugin_info_dict.items():
            # Get the plugin path from the database
            plugin_path = None
            if plugin_name in plugin_db_entries:
                db_entry = plugin_db_entries[plugin_name]
                if db_entry.module_path:
                    mp = db_entry.module_path
                    if mp.startswith("file://") and "::" in mp:
                        plugin_path = mp[len("file://"):].split("::", 1)[0]
                    else:
                        import importlib.util
                        module_dotted = mp.rsplit(".", 1)[0]
                        try:
                            spec = importlib.util.find_spec(module_dotted)
                            plugin_path = spec.origin if spec is not None else None
                        except (ModuleNotFoundError, ValueError):
                            plugin_path = None
            
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
        plugin_manager = get_exploit_plugin_manager()
            
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
        device_manager = get_device_driver_manager()
        
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
        device_manager = get_device_driver_manager()
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

        normalized_plugins = []
        for plugin_item in selected_plugins:
            if isinstance(plugin_item, str):
                plugin_name = plugin_item
                sequence = 100
                ignore_fail = False
            else:
                plugin_name = plugin_item.get('name')
                sequence = plugin_item.get('sequence', 100)
                ignore_fail = plugin_item.get('ignore_fail', False)

            if not plugin_name:
                continue

            normalized_plugins.append({
                "name": plugin_name,
                "sequence": sequence,
                "ignore_fail": ignore_fail,
            })

        existing_plugins = {
            plugin.name: plugin
            for plugin in Plugin.objects.filter(name__in=[item["name"] for item in normalized_plugins])
        }
        missing_plugins = [
            item["name"] for item in normalized_plugins if item["name"] not in existing_plugins
        ]
        if missing_plugins:
            return JsonResponse({
                "status": "error",
                "message": "Plugins must be discovered before they can be added to a group",
                "missing_plugins": missing_plugins,
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
            from iotsploit_django.adapters.django.plugins.models import PluginSequence
            PluginSequence.objects.filter(plugingroup=group).delete()
        
        # Add selected plugins to the group with sequence information
        added_plugins = []
        for plugin_item in normalized_plugins:
            plugin_name = plugin_item['name']
            sequence = plugin_item['sequence']
            ignore_fail = plugin_item['ignore_fail']
            plugin = existing_plugins[plugin_name]
            
            # Create the sequence entry
            from iotsploit_django.adapters.django.plugins.models import PluginSequence
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
        plugin_manager = get_exploit_plugin_manager()
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
        if '..' in plugin_path:
            return JsonResponse({'status': 'error', 'message': 'Invalid plugin path'})

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
        if '..' in plugin_path:
            return JsonResponse({'status': 'error', 'message': 'Invalid plugin path'})

        # Only allow editing legacy plugins inside the plugins/ directory.
        # Packaged plugins (installed via entry points) are read-only.
        from pathlib import Path as _Path
        from iotsploit_django.config import REPO_ROOT
        _legacy_root = (REPO_ROOT / 'plugins').resolve()
        try:
            _Path(plugin_path).resolve().relative_to(_legacy_root)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Packaged plugins are read-only and cannot be edited here'})

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
            plugin_manager = get_exploit_plugin_manager(use_celery=False)
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
        device_manager = get_device_driver_manager()
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
            
        device_manager = get_device_driver_manager()
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
            
        device_manager = get_device_driver_manager()
        result = device_manager.disable_driver(driver_name, description)
        
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error disabling driver: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to disable driver: {str(e)}"
        }, status=500)

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
