from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpRequest, HttpResponse
import json
import logging
from django.apps import apps

from sat_toolkit.core.device_manager import DeviceDriverManager
from sat_toolkit.models.Device_Model import DeviceManager
from sat_toolkit.tools.monitor_mgr import Pi_Mgr
from sat_toolkit.core.device_registry import DeviceRegistry
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.apps import SatToolkitConfig

logger = logging.getLogger(__name__)

def device_info(request: HttpRequest):
    """Get device information including battery, WiFi, etc."""
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", False)
    
    battery_charge = "充电中" if Pi_Mgr.Instance().pi_info()["battery"]["Charging"] else "放电中"

    info_dict = {
        "设备名称": Pi_Mgr.Instance().pi_info()["hostname"],
        "后台WIFI": Pi_Mgr.Instance().pi_info()["admin_wifi"]["SSID"],
        "WIFI密码": Pi_Mgr.Instance().pi_info()["admin_wifi"]["PASSWD"],
        "后台IP": Pi_Mgr.Instance().pi_info()["admin_wifi"]["ADMIN_IP"],
        "电池电量": Pi_Mgr.Instance().pi_info()["battery"]["Percent"] + " " + battery_charge,
        "核心温度": Pi_Mgr.Instance().pi_info()["cpu_temp"]
    }
    
    return HttpResponse(json.dumps(info_dict))

def get_all_devices(request):
    """Get all registered devices from the device manager."""
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

def scan_all_devices(request):
    """Scan for all devices using the DeviceDriverManager."""
    device_manager = DeviceDriverManager()
    scan_results = device_manager.scan_all_devices()
    return JsonResponse(scan_results)

@csrf_exempt
def scan_specific_device(request, driver_name):
    """Scan for devices using a specific device driver."""
    try:
        device_manager = DeviceDriverManager()
        
        available_drivers = device_manager.list_drivers()
        if driver_name not in available_drivers:
            return JsonResponse({
                "status": "error",
                "message": f"Device '{driver_name}' not found. Available devices: {available_drivers}"
            }, status=404)
        
        driver = device_manager.get_driver_instance(driver_name)
        if not driver:
            return JsonResponse({
                "status": "error",
                "message": f"No driver found for device: {driver_name}"
            }, status=404)
            
        scan_result = driver.scan()
        
        if scan_result:
            if isinstance(scan_result, list):
                devices = [dev.to_dict(encode_json=True) for dev in scan_result]
            else:
                devices = [scan_result.to_dict(encode_json=True)]
                
            return JsonResponse({
                "status": "success",
                "driver": driver_name,
                "devices_found": True,
                "devices": devices
            })
        else:
            return JsonResponse({
                "status": "success",
                "driver": driver_name,
                "devices_found": False,
                "message": "No devices found"
            })
            
    except Exception as e:
        logger.error(f"Error scanning with device driver: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to scan with device driver: {str(e)}"
        }, status=500)

@csrf_exempt
def list_devices(request):
    """
    Scan for devices and show detailed information.
    Returns all device properties in a single list.
    """
    try:
        # Get device registry instance
        device_registry = DeviceRegistry()
        device_registry.initialize()
        
        # Perform device scan
        logger.info("Scanning for devices...")
        discovered_devices = device_registry.scan_devices()
        
        # Get all devices and their sources
        all_devices = device_registry.device_store.devices
        device_sources = device_registry.device_store.device_sources
        
        # Format response with all device properties
        response = {
            "status": "success",
            "devices": []
        }
        
        # Add all devices with their complete properties
        for device_id, device in all_devices.items():
            try:
                # Convert device to dictionary using dataclasses-json
                device_dict = device.to_dict(encode_json=True)
                
                # Convert DeviceType enum to string
                device_dict["device_type"] = device.device_type.value
                
                # Add source at the top level (not in attributes)
                source = device_sources.get(device_id, "unknown")
                
                # Create new device dictionary with source at the top level
                formatted_device = {
                    "device_id": device_dict["device_id"],
                    "name": device_dict["name"],
                    "device_type": device_dict["device_type"],
                    "source": source
                }
                
                # Add other device-specific fields
                if "port" in device_dict:
                    formatted_device["port"] = device_dict["port"]
                if "baud_rate" in device_dict:
                    formatted_device["baud_rate"] = device_dict["baud_rate"]
                if "vendor_id" in device_dict:
                    formatted_device["vendor_id"] = device_dict["vendor_id"]
                if "product_id" in device_dict:
                    formatted_device["product_id"] = device_dict["product_id"]
                if "interface" in device_dict:
                    formatted_device["interface"] = device_dict["interface"]
                
                # Add attributes last
                if "attributes" in device_dict:
                    formatted_device["attributes"] = device_dict["attributes"]
                
                response["devices"].append(formatted_device)
                
            except Exception as e:
                logger.error(f"Error converting device {device_id} to dict: {str(e)}")
                continue
        
        if not all_devices:
            response["message"] = "No devices found"
            
        return JsonResponse(response)
        
    except Exception as e:
        logger.error(f"Error scanning devices: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": f"Failed to scan devices: {str(e)}"
        }, status=500)

def initialize_devices(request):
    """
    GET
    Initialize all available devices
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    try:
        # 直接使用 DeviceDriverManager 的单例
        device_manager = DeviceDriverManager()
        
        # Log driver states before initialization
        logger.info("Driver states before initialization:")
        for driver_name, enabled in device_manager.driver_states.items():
            logger.info(f"  Driver {driver_name}: {'enabled' if enabled else 'disabled'}")
        
        results = device_manager.initialize_all_devices()
        
        return JsonResponse({
            "status": "success",
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in device initialization: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

def cleanup_devices(request):
    """
    GET
    Clean up all device connections and reset states
    """
    if request.method != 'GET':
        return JsonResponse({
            "status": "error",
            "message": "Only GET method is allowed"
        }, status=405)
    try:
        device_manager = DeviceDriverManager()
        if not device_manager:
            return JsonResponse({
                "status": "success",
                "message": "No device manager to clean up"
            })

        results = device_manager.cleanup_all_devices()
        return JsonResponse({
            "status": "success",
            "results": results
        })

    except Exception as e:
        logger.error(f"Error in device cleanup: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)
