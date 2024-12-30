from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging

from sat_toolkit.tools.toolkit_main import Toolkit_Main
from sat_toolkit.tools.ota_mgr import OTA_Mgr

logger = logging.getLogger(__name__)

def ota_info(request):
    """
    GET     
    Returns OTA and version information
    """    
    curr_version = OTA_Mgr.Instance().curr_version()
    return HttpResponse(json.dumps(curr_version))

def vehicle_info(request):
    """
    GET
    Returns current vehicle profile information
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
def select_vehicle_profile(request):
    """
    POST
    Select a vehicle profile
    """
    user_select = json.loads(request.body).get("user_select", "")
    select_vehicle = None    
    for vehicle_profile in Toolkit_Main.Instance().list_vehicle_profiles_to_select():
        if user_select == str(vehicle_profile):
            select_vehicle = vehicle_profile
            break

    if select_vehicle != None:
        logger.info("User Select Vehicle Profile:{}".format(user_select))
        Toolkit_Main.Instance().select_vehicle_profile(vehicle_profile)
        result = {
            "status": "User Select Vehicle Profile:{}".format(user_select),
            "action": "GET vehicle_info",
            "result": True,
        }
        return HttpResponse(json.dumps(result))

    else:
        logger.error("User Select Vehicle Profile Not Found!:{}".format(user_select))
        result = {
            "status": "User Select Vehicle Profile Not Found!:{}".format(user_select),
            "result": False,
        }
        return HttpResponse(json.dumps(result)) 