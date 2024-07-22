import logging
import pywifi
logger = logging.getLogger(__name__)

from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

def get_ssid_info(ecu:str):
    cached_ssid = None
    if ecu == "tcam":
        cached_ssid = Env_Mgr.Instance().query("VehicleInfo_TCAM_WIFI_SSID")
    else:
        cached_ssid = Env_Mgr.Instance().query("VehicleInfo_DHU_WIFI_SSID")
    wifi_info = None
    if cached_ssid != None:
        wifi_info = WiFi_Mgr.Instance().query_wifi_info_by_ssid(cached_ssid)
        if wifi_info == None or len(wifi_info) == 0:
            user_select = Input_Mgr.Instance().single_choice(
                "{}热点查询失败,请确认{}热点已经打开并确认热点信息:{}".format(ecu,cached_ssid),
                [ "热点已经打开,信息准确", "热点已经打开,信息不准确,重新输入"])
        else:
            return wifi_info[0]
        if user_select == "热点已经打开,信息准确":
            logger.info("SAT缓存中有{}热点信息{}再次查询中".format(ecu,cached_ssid))
            wifi_info = WiFi_Mgr.Instance().query_wifi_info_by_ssid(cached_ssid)
            if wifi_info == None or len(wifi_info) == 0:
                raise_err("扫描{}热点失败.".format(ecu))
        else:
            logger.info("SAT缓存中清除原有{}热点信息".format(ecu))
            if ecu == "tcam":
                Env_Mgr.Instance().unset("VehicleInfo_TCAM_WIFI_SSID")
                Env_Mgr.Instance().unset("VehicleInfo_TCAM_WIFI_PASSWD")
            else:
                Env_Mgr.Instance().unset("VehicleInfo_DHU_WIFI_SSID")
                Env_Mgr.Instance().unset("VehicleInfo_DHU_WIFI_PASSWD")                
    else:
        logger.info("SAT缓存中没有{}热点信息".format(ecu))
        Input_Mgr.Instance().confirm("首次扫描该汽车的{}热点,请确认热点已经打开".format(ecu))
    
    cached_ssid = None
    for i in range(5):
        ssid_choice_list = []
        ssid_list = WiFi_Mgr.Instance().query_wifi_info_by_ssid(None)
        if ssid_list != None and len(ssid_list) != 0:            
            for wifi_info in ssid_list:
                ssid_choice_list.append(wifi_info.ssid)
        ssid_choice_list = list(set(ssid_choice_list))
        ssid_choice_list.append("重新扫描热点")
        ssid_choice_list.append("取消连接热点")        
        cached_ssid = Input_Mgr.Instance().single_choice(
                    "请选择需要连接的WIFI热点",
                    ssid_choice_list)
        if cached_ssid == "重新扫描热点":
            cached_ssid = None
            continue
        if cached_ssid == "取消连接热点":
            raise_err("连接TCAM的热点失败,用户取消热点连接")
        break

    if cached_ssid == None:
        raise_err("连接TCAM的热点失败,用户没有找到TCAM的热点")

    wifi_info = WiFi_Mgr.Instance().query_wifi_info_by_ssid(cached_ssid)
    if wifi_info == None or len(wifi_info) == 0:
        raise_err("扫描{}热点失败.".format(ecu))

    return wifi_info[0]

def main(ecu:str):
    wifi_ssid_info = None
    if ecu == "tcam":
        wifi_ssid_info = get_ssid_info("tcam")
    else:
        wifi_ssid_info = get_ssid_info("dhu")
    if wifi_ssid_info is not None:
        logger.info("akm:{}".format(wifi_ssid_info.akm))
        logger.info("auth:{}".format(wifi_ssid_info.auth))
        logger.info("cipher:{}".format(wifi_ssid_info.cipher))
        if pywifi.const.AKM_TYPE_WPA2PSK in wifi_ssid_info.akm:
            raise_ok("WIFI加密方式符合")
        else:
            raise_err("WIFI加密方式不符合:{}".format(wifi_ssid_info.akm))
    else:
        raise_err("获取ssid info失败")        


if __name__ == '__main__':
    main()