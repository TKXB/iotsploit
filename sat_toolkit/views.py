from django.http import HttpResponse
from django.http import HttpRequest
from django.shortcuts import redirect

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.toolkit_main import Toolkit_Main

from sat_toolkit.tools.pi_mgr import Pi_Mgr
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.core.exploit_spec import ExploitResult

import logging
logger = logging.getLogger(__name__)

import json
import datetime

from sat_toolkit.core.device_manager import DevicePluginManager  # Add this import
from sat_toolkit.models.Target_Model import TargetManager

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
                "result": "不通过",
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

def list_devices(request):
    """
    GET
    Returns a list of available device plugins
    """
    device_manager = DevicePluginManager()
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
    Scans for all devices using the DevicePluginManager
    """
    device_manager = DevicePluginManager()
    scan_results = device_manager.scan_all_devices()
    
    return JsonResponse(scan_results)