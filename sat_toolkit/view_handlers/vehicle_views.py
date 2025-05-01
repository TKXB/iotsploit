from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging

from sat_toolkit.tools.ota_mgr import OTA_Mgr

logger = logging.getLogger(__name__)

def ota_info(request):
    """
    GET     
    Returns OTA and version information
    """    
    curr_version = OTA_Mgr.Instance().curr_version()
    return HttpResponse(json.dumps(curr_version)) 