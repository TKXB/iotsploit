import logging
logger = logging.getLogger(__name__)
import time
import json
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.ssh_mgr import SSH_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr


def get_tcam_ssh():
    tcam_ip = None
    wifi_status = WiFi_Mgr.Instance().status()
    #获取TCAM IP封装成API，IP需要自动获取，不是配置的。
    if wifi_status["WIFI_MODE"] == "STA":
        tcam_ip = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_AP_IP")
        if tcam_ip == None:
            raise_err( "车型未设置TCAM热点内网IP! VehicleModel_TCAM_AP_IP未设置!")
        logger.info("SAT连接TCAM热点, TCAM_IP:{}".format(tcam_ip))
    elif wifi_status["WIFI_MODE"] == "AP":
        tcam_wifi_sta_mac = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_WIFI_STA_MAC")
        if tcam_wifi_sta_mac == None:
            raise_err( "车辆未设置TCAM STA MAC! VehicleInfo_TCAM_WIFI_STA_MAC未设置!")
        
        logger.info("TCAM连接SAT热点, TCAM_WIFI_STA_MAC:{}".format(tcam_wifi_sta_mac))
        for client in wifi_status["client_list"]:
            if client["mac"].upper() == tcam_wifi_sta_mac.upper():
                logger.info("TCAM连接SAT热点, TCAM DHCP INFO:{}".format(client))
                tcam_ip = client["ip"]
                break
        if tcam_ip == None:
            raise_err( "SAT热点中未找到TCAM的连接信息!")
    else:
        raise_err( "SAT网络连接状态:'{}'不支持TCAM Flood测试!".format(wifi_status["WIFI_MODE"]))

    #
    tcam_ssh_user = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_USER")
    tcam_ssh_passwd = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD")
    if tcam_ssh_user == None:
        raise_err( "车型未设置TCAM SSH登录信息! ehicleModel_TCAM_SSH_USER NOT SET!")


    logger.info("SAT登录TCAM SSH IP:{} User:{}-->>".format(tcam_ip, tcam_ssh_user))
    ssh_context = SSH_Mgr.Instance().open_ssh(tcam_ip, tcam_ssh_user, tcam_ssh_passwd)
    if ssh_context == None:
        raise_err( "车辆TCAM无法SSH登录。IP:{} User:{}".format(tcam_ip, tcam_ssh_user))
    
    return 1,ssh_context

def flush_tcam_iptables(ssh_context):
    pass

def add_tcam_internal_ip_route(ssh_context):
    pass

def add_tcam_private_apn_ip_route(ssh_context):
    pass

def main(control:str):
    if control == "enable":
        #reset tcam
        pass
    else:
        ssh_context = get_tcam_ssh()
        flush_tcam_iptables(ssh_context)
        add_tcam_internal_ip_route(ssh_context)
        add_tcam_private_apn_ip_route(ssh_context)
        
    # #TODO 
    # logger.info("TCAM修改内网隔离状态为:{} -->>".format(control))
    # if control == "enable":
    #     SSH_Mgr.Instance().ssh_cmd(ssh_context, "route")
    # else:
    #     SSH_Mgr.Instance().ssh_cmd(ssh_context, "route")
    
    # #不关闭SSH
    # # SSH_Mgr.Instance().close_ssh(ssh_context)

    # raise_ok( "TCAM修改内网隔离状态为:{}".format(control))

if __name__ == '__main__':
    main()