from django.http import HttpResponse
from django.http import HttpRequest
from django.shortcuts import redirect

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.toolkit_main import Toolkit_Main

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

import logging
logger = logging.getLogger(__name__)

import json
import datetime

from sat_toolkit.core.device_manager import DeviceDriverManager  
from sat_toolkit.models.Target_Model import TargetManager
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree
from sat_toolkit.models.Device_Model import DeviceManager
from asgiref.sync import async_to_sync

import asyncio

from celery.result import AsyncResult
from .tasks import execute_plugin_task

from sat_toolkit.core.stream_manager import StreamManager


def device_info(request:HttpRequest):
    """
    GET		
    {
        "设备名称": "SAT_0102",
        "电池电量": "80%",
        "user_input": "xxxxxx"
    }
    """    
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", False)
    
    battery_charge = "充电中"
    if Pi_Mgr.Instance().pi_info()["battery"]["Charging"] != True:
        battery_charge = "放电中"

    info_dict = {
        "设备名称":  Pi_Mgr.Instance().pi_info()["hostname"],
        "后台WIFI": Pi_Mgr.Instance().pi_info()["admin_wifi"]["SSID"],
        "WIFI密码": Pi_Mgr.Instance().pi_info()["admin_wifi"]["PASSWD"],
        "后台IP":   Pi_Mgr.Instance().pi_info()["admin_wifi"]["ADMIN_IP"],
        "电池电量": Pi_Mgr.Instance().pi_info()["battery"]["Percent"] + " " + battery_charge,
        "核心温度": Pi_Mgr.Instance().pi_info()["cpu_temp"]
    }

    # wifi_staus = WiFi_Mgr.Instance().status()
    # if wifi_staus["WIFI_MODE"] == "IDLE":
    #     info_dict["WIFI状态"] = "待机模式"

    # if wifi_staus["WIFI_MODE"] == "STA":
    #     info_dict["WIFI状态"] = "STA模式"
    #     info_dict["连接WIFI"] = wifi_staus["sta_status"]

    # if wifi_staus["WIFI_MODE"] == "AP":
    #     info_dict["WIFI状态"] = "热点模式"
    #     info_dict["热点名称"] = wifi_staus["ap_ssid"]
    #     info_dict["热点密码"] = wifi_staus["ap_passwd"]
    #     info_dict["设备连接数"] = len(wifi_staus["client_list"])

    return HttpResponse(json.dumps(info_dict))    

def ota_info(request):
    """
    GET		
    {
        "toolkit version": "v0.0.1",
        "database version": "20231112",
        "user_input": "xxxxxx"
    }
    """    
    curr_version = OTA_Mgr.Instance().curr_version()
    
    return HttpResponse(json.dumps(curr_version))

def vehicle_info(request):
    """
    GET
    {
    "描述": "测试车辆1",
    "user_input":  "xxxxxx"
    }
    """
    curr_vehicle = Toolkit_Main.Instance().curr_vehicle_profile()
    if curr_vehicle != None:
        vehicle_dict = {
            "描述": curr_vehicle.Description,
            "车型": curr_vehicle.vehicle_model.Name
        }
    else:
        vehicle_dict = {
            "user_input": "list_vehicle_profiles_to_select"
        }
        
    return HttpResponse(json.dumps(vehicle_dict))

@csrf_exempt
def select_vehicle_profile(request:HttpRequest):
    user_select = json.loads(request.body).get("user_select", "")
    select_vehicle = None    
    for vehicle_profile in Toolkit_Main.Instance().list_vehicle_profiles_to_select():
        if user_select == str(vehicle_profile):
            select_vehicle = vehicle_profile
            break

    if select_vehicle != None:
        logger.info("User Select Vehicle Profile:{}".format(user_select))
        Toolkit_Main.Instance().select_vehicle_profile(vehicle_profile)
        result = \
        {
            "status":"User Select Vehicle Profile:{}".format(user_select),
            "action": "GET vehicle_info",
            "result": True,
        }
        return HttpResponse(json.dumps(result))
        # return redirect('http://example.com/foo/')
        # return HttpResponse("User Select Vehicle Profile:{}".format(user_select))

    else:
        logger.error("User Select Vehicle Profile Not Found!:{}".format(user_select))
        result = \
        {
            "status":"User Select Vehicle Profile Not Found!:{}".format(user_select),
            "result": False,
        }
        return HttpResponse(json.dumps(result))
        # return HttpResponse("User Select Vehicle Profile Not Found!:{}".format(user_select))

def request_enter_test_page(request):
    """
    GET		
{
    "request": true
}
或者
{
    "request": false,
    "user_input": "xxxxxx"
}
    """
    curr_vehicle = Toolkit_Main.Instance().curr_vehicle_profile()
    if curr_vehicle != None:
        result = {"request": True}
    else:
        result = {"request": False, "user_input": "list_vehicle_profiles_to_select"}
        
    return HttpResponse(json.dumps(result))

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

@csrf_exempt
def request_test_status(request):
    if Toolkit_Main.Instance().curr_test_level() == None:
        result_dict = { "user_input": "list_test_level_to_select" }
        return HttpResponse(json.dumps(result_dict))

    if Toolkit_Main.Instance().curr_test_project() == 0:
        result_dict = { "user_input": "list_test_project_to_select" }
        return HttpResponse(json.dumps(result_dict))

    status_dict = {}
    status_dict["category"] = [
        Toolkit_Main.Instance().curr_test_level(),
        str(Toolkit_Main.Instance().curr_test_project())
    ]

    audit_status = Report_Mgr.Instance().audit_status()
    # logger.info("audit_status:{}".format(audit_status))

    if audit_status[0] == "No Audit":
        if Toolkit_Main.Instance().curr_test_project() == None:
            detail_list = [
                {
                    "title": "请选择测试项目!!",
                    # "status": {"result": "通过","color": "green"}
                }
            ]
        else:
            detail_list = []
            children_nodes = Toolkit_Main.Instance().curr_test_project().list_child_nodes( parent_list = [])
            for child_node in children_nodes:
                detail_list.append(
                    {
                        "title": child_node,
                        "status": {"result": "未开始","color": "white"}
                    }
                )
        status_dict["detail"] = detail_list
        result_status = {
            "result_code":0,
            "result": "未开始",
            "color": "white"
        }
        status_dict["status"] = result_status

    if audit_status[0] == "Audit In Process":
        curr_time = datetime.datetime.now()
        start_time = Env_Mgr.Instance().get("AUDIT_START_TIME")
        
        expand_list = []
        __expand_toc_list(audit_status[1], expand_list)
        status_dict["detail"] = expand_list
        result_status = {
            "result_code":1,
            "result": "进行中 " + calculate_time_difference(start_time, curr_time),
            "color": "yellow"
        }
        status_dict["status"] = result_status
        ui_input = Env_Mgr.Instance().query("SAT_NEED_UI")
        if ui_input != None:
            status_dict["user_input"] = ui_input

    if audit_status[0] == "Audit Finish":
        expand_list = []
        __expand_toc_list(audit_status[1], expand_list)
        status_dict["detail"] = expand_list
        if audit_status[2] < 0:
            result_status = {
                "result_code":2,
                "result": "通过",
                "color": "red",
                "report_url":"Audit_Report.html"
            }
        elif audit_status[2] > 0:
            result_status = {
                "result_code":2,                
                "result": "通过",
                "color": "green",
                "report_url":"Audit_Report.html"
            }
        else:
            result_status = {
                "result_code":2,
                "result": "完成",
                "color": "blue",
                "report_url":"Audit_Report.html"
            }
        status_dict["status"] = result_status

    # logger.info("audit_status resp:{}".format(status_dict))
    return HttpResponse(json.dumps(status_dict))

@csrf_exempt
def select_test_level(request):
    test_level = json.loads(request.body).get("user_select", "")
    
    if test_level == "":
        if Toolkit_Main.Instance().curr_test_level() == None:
            result_dict = { "user_input": "list_test_level_to_select" }
            return HttpResponse(json.dumps(result_dict))
        else:
            pass
            # logger.info("User Already Selected Test Level")
    else:
        logger.info("User Select Test Level:{}".format(test_level))
        Toolkit_Main.Instance().select_test_level(test_level)
        Report_Mgr.Instance().reset_audit_result()

    result_dict = { "user_input": "list_test_project_to_select" }
    return HttpResponse(json.dumps(result_dict))


@csrf_exempt
def select_test_project(request):
    test_project = json.loads(request.body).get("user_select", "")
    
    if test_project == "":
        if Toolkit_Main.Instance().curr_test_project() == None:
            result_dict = { "result": False, "user_input": "list_test_project_to_select" }
            return HttpResponse(json.dumps(result_dict))
        else:
            pass
            # logger.info("User Already Selected Test Level")
    else:       
        select_test_project = None
        for project in Toolkit_Main.Instance().list_test_projects_to_select():
            if test_project == str(project):
                select_test_project = project
                break

        if select_test_project != None:
            logger.info("User Select Test Project:{}".format(select_test_project))
            Toolkit_Main.Instance().select_test_project(select_test_project)
            Report_Mgr.Instance().reset_audit_result()
            result_dict = { 
                "status":"User Select Test Project:{}".format(select_test_project),
                "action": "GET request_test_status",
                "result": True,
            }
            return HttpResponse(json.dumps(result_dict))
        else:
            logger.error("User Select Test Project Not Found!:{}".format(test_project))
            result_dict = { "result": False, "user_input": "list_test_project_to_select" }
            return HttpResponse(json.dumps(result_dict))

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


def __user_input_list_vehicle_profiles_to_select(request:HttpRequest):
    result_dict = { "id" : request.GET.get("id") }
    result_dict.update(
        __build_single_choice_dialog(
            "请选择测试车辆",
            Toolkit_Main.Instance().list_vehicle_profiles_to_select(),
            [
                {
                    "name": "确认",
                    "color": "active",
                    "action": "POST select_vehicle_profile"
                },
                {
                    "name": "取消",
                    "action": "Dismiss"
                }
            ]
        )
    )
    return HttpResponse(json.dumps(result_dict))

def __user_input_list_test_level_to_select(request:HttpRequest):
    result_dict = { "id" : request.GET.get("id") }
    result_dict.update(
        __build_single_choice_dialog(
            "请选择测试层级",
            Toolkit_Main.Instance().list_test_levels_to_select(),
            [
                {
                    "name": "确认",
                    "color": "active",
                    "action": "POST select_test_level"
                },
                {
                    "name": "取消",
                    "action": "Dismiss"
                }
            ]
        )
    )
    return HttpResponse(json.dumps(result_dict))

def __user_input_list_test_project_to_select(request:HttpRequest):
    if Toolkit_Main.Instance().curr_test_level() == None:
        result_dict = { "user_input": "list_test_level_to_select" }
    else:
        result_dict = { "id" : request.GET.get("id") }
        result_dict.update(
            __build_single_choice_dialog(
                "请选择测试项目",
                Toolkit_Main.Instance().list_test_projects_to_select(),
                [
                    {
                        "name": "确认",
                        "color": "active",
                        "action": "POST select_test_project"
                    },
                    {
                        "name": "取消",
                        "action": "Dismiss"
                    }
                ]
            )
        )
    logger.info("list_test_project_to_select Response:{}".format(result_dict))        
    return HttpResponse(json.dumps(result_dict))

def __user_input_notice_user_to_stop_test(request:HttpRequest):
    result_dict = { "id" : request.GET.get("id") }
    result_dict.update(
        __build_confirm_dialog(
            "请先停止测试",
            [
                {
                    "name": "确认",
                    "color": "active",
                    "action": "Dismiss"
                }
            ]
        )
    )
    return HttpResponse(json.dumps(result_dict))

def user_input(request:HttpRequest):
    sub_func_dict = {
        "list_vehicle_profiles_to_select": __user_input_list_vehicle_profiles_to_select,
        "list_test_level_to_select":       __user_input_list_test_level_to_select,
        "list_test_project_to_select":     __user_input_list_test_project_to_select,
        "notice_user_to_stop_test":        __user_input_notice_user_to_stop_test,
    }

    user_input_id = request.GET.get("id", "")
    sub_func = sub_func_dict.get(user_input_id)
    if sub_func != None:
        return sub_func(request)
    else:
        logger.error("User Input ID:{} Invalid!".format(user_input_id))
        return HttpResponse("User Input ID:{} Invalid!".format(user_input_id))

def request_exit_test_page(request):
    """
    GET
{
    "request": true
}
或者
{
    "request": false,
    "user_input": "xxxxxx"
}
    """

    test_status = Toolkit_Main.Instance().check_test_status()
    if test_status != True:
        result = {"request": True}
    else:
        result = {"request": False, "user_input": "notice_user_to_stop_test"}
        
    return HttpResponse(json.dumps(result))

@csrf_exempt
def start_test(request):
    if Toolkit_Main.Instance().curr_test_level() == None:
        result_dict = { "user_input": "list_test_level_to_select" }
        return HttpResponse(json.dumps(result_dict))
    if Toolkit_Main.Instance().curr_test_project() == None:
        result_dict = { "user_input": "list_test_project_to_select" }
        return HttpResponse(json.dumps(result_dict))  
    Toolkit_Main.Instance().start_audit("UI Audit", False)

    result = {"status": "success"}
    return HttpResponse(json.dumps(result))

@csrf_exempt
def stop_test(request):
    Toolkit_Main.Instance().stop_audit()

    result = {"status": "success"}
    return HttpResponse(json.dumps(result))


@csrf_exempt
def record_user_input(request):
    Env_Mgr.Instance().unset("SAT_NEED_UI")
    user_select = json.loads(request.body).get("user_select", "")
    logger.info("Recv Use Input:{}".format(user_select))
    Env_Mgr.Instance().set("SAT_UI_RESULT", user_select)

    result = {"status": "success", "recv":user_select}
    return HttpResponse(json.dumps(result))


def list_plugins(request):
    plugin_manager = ExploitPluginManager()
    plugins = plugin_manager.list_plugins()
    return JsonResponse({'plugins': plugins})

def list_device_plugins(request):
    """
    GET
    Returns a list of available device plugins
    """
    device_manager = DeviceDriverManager()
    available_devices = device_manager.list_devices()
    
    if available_devices:
        result = {
            "status": "success",
            "devices": available_devices
        }
    else:
        result = {
            "status": "success",
            "devices": [],
            "message": "No device plugins available."
        }
    
    return JsonResponse(result)

@csrf_exempt
def exploit(request):
    """
    POST
    Execute all plugins in the IotSploit System
    """
    plugin_manager = ExploitPluginManager()
    plugin_manager.initialize()
    
    results = plugin_manager.exploit()
    
    if not results:
        return JsonResponse({
            "status": "warning",
            "message": "No results returned from any plugins"
        })
    else:
        formatted_results = {}
        for plugin_name, result in results.items():
            if result is None:
                formatted_results[plugin_name] = {
                    "status": "warning",
                    "message": f"Plugin {plugin_name} returned no result"
                }
            elif isinstance(result, ExploitResult):
                formatted_results[plugin_name] = {
                    "status": "success" if result.success else "failure",
                    "message": result.message,
                    "data": result.data
                }
            else:
                formatted_results[plugin_name] = {
                    "status": "success",
                    "result": str(result)
                }
        
        return JsonResponse({
            "status": "success",
            "message": "Exploit execution completed",
            "results": formatted_results
        })

def get_all_devices(request):
    """
    GET
    Returns a list of all registered devices
    """
    try:
        device_manager = DeviceManager.get_instance()
        devices = device_manager.get_all_devices()
        
        return JsonResponse({
            "status": "success",
            "devices": devices
        })
        
    except Exception as e:
        logger.error(f"Error retrieving devices: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to retrieve devices: {str(e)}"
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

def scan_all_devices(request):
    """
    GET
    Scans for all devices using the DeviceDriverManager
    """
    device_manager = DeviceDriverManager()
    scan_results = device_manager.scan_all_devices()
    
    return JsonResponse(scan_results)

@csrf_exempt
def execute_plugin(request):
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
        result = plugin_manager.execute_plugin(
            plugin_name, 
            target=current_target,
            parameters=parameters
        )
        logger.debug(f"Plugin execution result over http: {result}")
        
        if result is None:
            return JsonResponse({
                "status": "error",
                "message": f"Plugin {plugin_name} execution failed"
            }, status=400)
            
        if isinstance(result, ExploitResult):
            response_data = {
                "status": "success",
                "result": {
                    "success": result.success,
                    "message": result.message,
                    "data": result.data
                }
            }
        else:
            response_data = {
                "status": "success",
                "result": {
                    "message": str(result)
                }
            }
        logger.debug(f"Plugin execution result over http: {response_data}")
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
    plugin_manager = ExploitPluginManager()
    
    try:
        # Get plugin info
        plugin_info_dict = plugin_manager.list_plugin_info()
        
        # Format the response with success/failure indicators
        formatted_plugins = []
        has_valid_plugins = False
        
        for plugin_name, info in plugin_info_dict.items():
            plugin_entry = {
                "name": plugin_name,
                "info": info,
                "status": "success" if "error" not in info else "failure"
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
            
            # Format plugins in this group
            plugins = [{
                "name": plugin.name,
                "enabled": plugin.enabled,
                "description": plugin.description
            } for plugin in group.plugins.all()]
            
            # Format parent groups
            parent_groups = [{
                "name": relation.parent.name,
                "force_exec": relation.force_exec
            } for relation in parent_relations]
            
            # Format child groups
            child_groups = [{
                "name": relation.child.name,
                "force_exec": relation.force_exec
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
        available_devices = device_manager.list_devices()
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
def execute_device_command(request, device_name):
    """
    POST
    Execute a command on a specific device
    
    Parameters:
        device_name (str): Name of the device driver
    
    Request Body:
        {
            "command": "command_name",
            "args": "command_arguments",  # Optional
            "hardware_id": "device_id"    # Optional, for hardware device selection
        }
    
    Returns:
        JSON response containing the command execution result
    """
    if request.method != 'POST':
        return JsonResponse({
            "status": "error",
            "message": "Only POST method is allowed"
        }, status=405)
        
    try:
        # Parse request body
        data = json.loads(request.body)
        command = data.get('command')
        args = data.get('args', '')
        hardware_id = data.get('hardware_id', '')  # New parameter
        
        if not command:
            return JsonResponse({
                "status": "error",
                "message": "Command name is required"
            }, status=400)

        # Get device plugin manager
        device_manager = DeviceDriverManager()
        
        # Verify device exists
        available_plugins = device_manager.list_devices()
        if device_name not in available_plugins:
            return JsonResponse({
                "status": "error",
                "message": f"Device '{device_name}' not found. Available devices: {available_plugins}"
            }, status=404)

        # Get driver instance
        driver = device_manager.get_driver_instance(device_name)

        if not driver:
            return JsonResponse({
                "status": "error",
                "message": f"No driver found for device: {device_name}"
            }, status=404)
        
        if not driver.connected:
            # Need to scan and select the device
            logger.info(f"Scanning for devices with plugin: {device_name}")
            scan_result = driver.scan()
            if not scan_result:
                logger.warning(f"No devices found during scan for plugin: {device_name}")
                return JsonResponse({
                    "status": "error", 
                    "message": f"No devices found for plugin: {device_name}"
                }, status=404)
            
            logger.info(f"Found {len(scan_result)} devices: {[dev.device_id for dev in scan_result]}")
            
            selected_device = None
            if hardware_id:
                logger.info(f"Attempting to find device with hardware_id: {hardware_id}")
                selected_device = next(
                    (dev for dev in scan_result if dev.device_id == hardware_id),
                    None
                )
                if not selected_device:
                    logger.error(f"Hardware device with ID {hardware_id} not found in scan results")
                    return JsonResponse({
                        "status": "error",
                        "message": f"Hardware device with ID {hardware_id} not found"
                    }, status=404)
                logger.info(f"Found matching device: {selected_device.device_id}")
            else:
                selected_device = scan_result[0]
                logger.info(f"No hardware_id specified, defaulting to first device: {selected_device.device_id}")
            
            logger.info(f"Initializing driver for device: {selected_device.device_id}")
            driver.initialize(selected_device)
            
            logger.info(f"Connecting to device: {selected_device.device_id}")
            driver.connect(selected_device)
            logger.info(f"Successfully connected to device: {selected_device.device_id}")

        # Execute the command
        result = driver.command(driver.device, f"{command} {args}".strip())
        return JsonResponse({
            "status": "success",
            "device": device_name,
            "hardware_device": hardware_id or driver.device.device_id,
            "command": command,
            "args": args,
            "result": result
        })

    except Exception as e:
        logger.error(f"Error executing device command: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to execute device command: {str(e)}"
        }, status=500)

