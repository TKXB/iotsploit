import logging
logger = logging.getLogger(__name__)
import time
import netifaces
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.net_audit_mgr import NetAudit_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.ssh_mgr import SSH_Mgr

def check_ecu_alive(ecu:str,checktype:str):
    if ecu == "tcam":
        return check_tcam_alive(checktype)
    elif ecu == "dhu":
        return check_dhu_alive(checktype)
    elif ecu == "vgm":
        return check_vgm_alive(checktype)

def check_tcam_alive(usetype:str):
    try:
        if usetype == "ip":
            tcam_ip = query_tcam_ip()
            tacm_ip_alive = NetAudit_Mgr.Instance().ip_detect([tcam_ip])
            if len(tacm_ip_alive) == 0:
                return False
            return True
        else:
            tcam_doip_alive = DoIP_Mgr.Instance().check_mcu_alive(DoIP_Mgr.TCAM_Addr)
            if tcam_doip_alive == False:
                return False
            return True
    except SAT_Exception:
        return False    
    
def check_dhu_alive(usetype:str):
    try:
        if usetype == "ip":
            dhu_ip = query_dhu_ip()
            dhu_ip_alive = NetAudit_Mgr.Instance().ip_detect([dhu_ip])
            if len(dhu_ip_alive) == 0:
                return False
            return True
        else:
            dhu_doip_alive = DoIP_Mgr.Instance().check_mcu_alive(DoIP_Mgr.DHU_Addr)
            if dhu_doip_alive == False:
                return False
            return True
    except SAT_Exception:
        return False
    
def check_vgm_alive(usetype:str):
    try:
        if usetype == "ip":
            vgm_ip = "169.254.19.1"
            vgm_ip_alive = NetAudit_Mgr.Instance().ip_detect([vgm_ip])
            if len(vgm_ip_alive) == 0:
                return False
            return True
        else:
            vgm_doip_alive = DoIP_Mgr.Instance().check_mcu_alive(0x1001)
            if vgm_doip_alive == False:
                return False
            return True
    except SAT_Exception:
        return False

def query_tcam_ipv6():
    """
    查看当前TCAM的IP
    Raise SAT_Exception 

        """
    wifi_status = WiFi_Mgr.Instance().status()
    if wifi_status["WIFI_MODE"] == "STA":
        sat_ip = wifi_status.get("sta_status",[]).get("ip_address")
        if sat_ip == None:
            raise_err( "SAT没有获取到IP地址,SAT连接TCAM热点失败！")
            
        gw_ipv6 = netifaces.gateways()['default'][netifaces.AF_INET6][0]            
        if gw_ipv6 == None:
            raise_err( "SAT没有获取到WIFI0的网关IP地址,SAT连接TCAM热点失败！")

        logger.info("SAT成功连接TCAM热点,GW IPV6:{}".format(gw_ipv6))
        return gw_ipv6 

    else:
        raise_err( "SAT网络连接状态:'{}'不支持获取TCAM IPV6".format(wifi_status["WIFI_MODE"]))        

def query_tcam_ip():
    """
    查看当前TCAM的IP
    Raise SAT_Exception 

        """
    wifi_status = WiFi_Mgr.Instance().status()
    if wifi_status["WIFI_MODE"] == "STA":
        tcam_ip = Env_Mgr.Instance().query("__SAT_ENV__VehicleModel_TCAM_AP_IP")
        if tcam_ip != None:
            logger.info("车型设置了TCAM热点内网IP:{}".format(tcam_ip))
            return tcam_ip

        sat_ip = wifi_status.get("sta_status",[]).get("ip_address")
        if sat_ip == None:
            raise_err( "SAT没有获取到IP地址,SAT连接TCAM热点失败！")
            
        gw_ip = netifaces.gateways()['default'][netifaces.AF_INET][0]
        if gw_ip == None:
            raise_err( "SAT没有获取到WIFI0的网关IP地址,SAT连接TCAM热点失败！")

        logger.info("SAT成功连接TCAM热点,GW IP:{}".format(gw_ip))
        return gw_ip 
            
    elif wifi_status["WIFI_MODE"] == "AP":
        tcam_wifi_sta_mac = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_TCAM_WIFI_STA_MAC")
        if tcam_wifi_sta_mac != None:
            for client in wifi_status["client_list"]:
                if client["mac"].upper() == tcam_wifi_sta_mac.upper():
                    logger.info("TCAM设置了STA MAC,且连接SAT热点, TCAM DHCP INFO:{}".format(client))
                    return client["ip"]
            raise_err( "TCAM设置了STA MAC:{} SAT热点中未找到TCAM的连接信息!".format(tcam_wifi_sta_mac))
        else:
            if len(wifi_status["client_list"]) == 0:
                raise_err( "TCAM未设置STA MAC. SAT热点中没有设备连接!")
            else:
                client = wifi_status["client_list"][0]
                logger.info("TCAM未设置STA MAC. SAT热点中选取第一个设备为TCAM:{}".format(client))
                return client["ip"]    
    else:
        raise_err( "SAT网络连接状态:'{}'不支持获取TCAM IP".format(wifi_status["WIFI_MODE"]))        


def query_dhu_ip():
    """
    查看当前DHU的IP
    Raise SAT_Exception 

    """
    wifi_status = WiFi_Mgr.Instance().status()
    if wifi_status["WIFI_MODE"] == "STA":
        dhu_ip = Env_Mgr.Instance().query("__SAT_ENV__VehicleModel_DHU_AP_IP")
        if dhu_ip != None:
            logger.info("车型设置了DHU热点内网IP:{}".format(dhu_ip))
            return dhu_ip

        sat_ip = wifi_status.get("sta_status",[]).get("ip_address")
        if sat_ip == None:
            raise_err( "SAT没有获取到IP地址,SAT连接DHU热点失败！")
        
        gw_ip = netifaces.gateways()['default'][netifaces.AF_INET][0]
        if gw_ip == None:
            raise_err( "SAT没有获取到WIFI0的网关IP地址,SAT连接DHU热点失败！")

        logger.info("SAT成功连接DHU热点,GW IP:{}".format(gw_ip))
        return gw_ip 
        
    elif wifi_status["WIFI_MODE"] == "AP":
        dhu_wifi_sta_mac = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_DHU_WIFI_STA_MAC")
        if dhu_wifi_sta_mac != None:
            for client in wifi_status["client_list"]:
                if client["mac"].upper() == dhu_wifi_sta_mac.upper():
                    logger.info("DHU设置了STA MAC,且连接SAT热点, DHU DHCP INFO:{}".format(client))
                    return client["ip"]
            raise_err( "DHU设置了STA MAC:{} SAT热点中未找到DHU的连接信息!".format(dhu_wifi_sta_mac))
        else:
            if len(wifi_status["client_list"]) == 0:
                raise_err( "DHU未设置STA MAC. SAT热点中没有设备连接!")
            else:
                client = wifi_status["client_list"][0]
                logger.info("DHU未设置STA MAC. SAT热点中选取第一个设备为DHU:{}".format(client))
                return client["ip"]    
    else:
        raise_err( "SAT网络连接状态:'{}'不支持获取DHU IP".format(wifi_status["WIFI_MODE"]))     


def open_tcam_ssh():
    """
    获取TCAM的SSH
    Raise SAT_Exception
    
    xxx = SSH_Mgr().Instance().open_tcam_ssh()

    Return:
    None:连接失败
    ssh_context:连接成功
    """
    tcam_ip = query_tcam_ip()
    
    tcam_ssh_user = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_USER")
    tcam_ssh_passwd = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD")
    if tcam_ssh_user == None:
        raise_err( "车型未设置TCAM SSH登录信息! ehicleModel_TCAM_SSH_USER NOT SET!")

    logger.info("SAT登录TCAM SSH IP:{} User:{}-->>".format(tcam_ip, tcam_ssh_user))
    ssh_context = SSH_Mgr.Instance().open_ssh(tcam_ip, tcam_ssh_user, tcam_ssh_passwd)
    if ssh_context == None:
        raise_err( "车辆TCAM无法SSH登录。IP:{} User:{}".format(tcam_ip, tcam_ssh_user))

    return ssh_context


def connect_tcam_wifi():
    cached_ssid = Env_Mgr.Instance().query("VehicleInfo_TCAM_WIFI_SSID")
    cached_passwd = Env_Mgr.Instance().query("VehicleInfo_TCAM_WIFI_PASSWD")
    if cached_ssid != None:
        logger.info("SAT缓存中有TCAM热点信息{} {} 自动连接中".format(cached_ssid, cached_passwd))
        ssid_list = WiFi_Mgr.Instance().query_wifi_info_by_ssid(cached_ssid)
        if ssid_list != None and len(ssid_list) != 0:
            WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT等待TCAM热点分配IP中:{}".format(i))
                sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
                if sta_status.get("ip_address") != None:
                    raise_ok( "SAT连接TCAM设备:{}的热点成功.连接信息:{}".format(cached_ssid,sta_status))   

        user_select = Input_Mgr.Instance().single_choice(
            "TCAM热点连接失败,请确认TCAM热点已经打开并确认热点信息:{} {}".format(cached_ssid, cached_passwd),
            [ "热点已经打开,信息准确", "热点已经打开,信息不准确,重新输入"])
        
        if user_select == "热点已经打开,信息准确":
            logger.info("SAT缓存中有TCAM热点信息{} {} 再次自动连接中".format(cached_ssid, cached_passwd))
            WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT等待TCAM热点分配IP中:{}".format(i))
                sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
                if sta_status.get("ip_address") != None:
                    raise_ok( "SAT连接TCAM的热点成功.连接信息:{}".format(sta_status))
            raise_err( "SAT连接TCAM的热点失败.")
        else:
            logger.info("SAT缓存中清除原有TCAM热点信息")
            Env_Mgr.Instance().unset("VehicleInfo_TCAM_WIFI_SSID")
            Env_Mgr.Instance().unset("VehicleInfo_TCAM_WIFI_PASSWD")
    else:
        logger.info("SAT缓存中没有TCAM热点信息")
        Input_Mgr.Instance().confirm("首次连接该汽车的TCAM热点,请确认TCAM热点已经打开")
    
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

    cached_passwd = Input_Mgr.Instance().string_input(
                "请输入TCAM WIFI热点:{} 对应的WIFI密码".format(cached_ssid))
    for retry_passwd in range(5):
        WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
        for i in range(30):
            sat_sleep(1)
            logger.info("SAT等待热点分配IP中:{}".format(i))
            sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
            if sta_status.get("ip_address") != None:
                Env_Mgr.Instance().set("VehicleInfo_TCAM_WIFI_SSID", cached_ssid)
                Env_Mgr.Instance().set("VehicleInfo_TCAM_WIFI_PASSWD", cached_passwd)  
                vehicle_profile = Env_Mgr.Instance().query("VEHICLE_PROFILE")
                if vehicle_profile != None:
                    vehicle_profile.save_wifi_info(cached_ssid, None, cached_passwd,
                                                   None, None, None)
                else:
                    logger.error("VEHICLE_PROFILE NOT FOUND In ENV!!")

                raise_ok( "SAT连接TCAM的热点成功.连接信息:{}".format(sta_status))

        cached_passwd = Input_Mgr.Instance().string_input(
                "连接超时{}.请重新输入TCAM WIFI热点:{} 对应的WIFI密码".format(retry_passwd, cached_ssid)) 

    raise_err("连接TCAM的热点失败, 用户输入的TCAM热点信息:{} {}无法连接".format(cached_ssid, cached_passwd))


def connect_dhu_wifi():
    cached_ssid = Env_Mgr.Instance().query("VehicleInfo_DHU_WIFI_SSID")
    cached_passwd = Env_Mgr.Instance().query("VehicleInfo_DHU_WIFI_PASSWD")
    if cached_ssid != None:
        logger.info("SAT缓存中有DHU热点信息{} {} 自动连接中".format(cached_ssid, cached_passwd))
        ssid_list = WiFi_Mgr.Instance().query_wifi_info_by_ssid(cached_ssid)
        if ssid_list != None and len(ssid_list) != 0:
            WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT等待DHU热点分配IP中:{}".format(i))
                sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
                if sta_status.get("ip_address") != None:
                    raise_ok( "SAT连接DHU设备:{}的热点成功.连接信息:{}".format(cached_ssid,sta_status))   

        user_select = Input_Mgr.Instance().single_choice(
            "DHU热点连接失败,请确认DHU热点已经打开并确认热点信息:{} {}".format(cached_ssid, cached_passwd),
            [ "热点已经打开,信息准确", "热点已经打开,信息不准确,重新输入"])
        
        if user_select == "热点已经打开,信息准确":
            logger.info("SAT缓存中有DHU热点信息{} {} 再次自动连接中".format(cached_ssid, cached_passwd))
            WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT等待DHU热点分配IP中:{}".format(i))
                sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
                if sta_status.get("ip_address") != None:
                    raise_ok( "SAT连接DHU的热点成功.连接信息:{}".format(sta_status))
            raise_err( "SAT连接DHU的热点失败.")
        else:
            logger.info("SAT缓存中清除原有DHU热点信息")
            Env_Mgr.Instance().unset("VehicleInfo_DHU_WIFI_SSID")
            Env_Mgr.Instance().unset("VehicleInfo_DHU_WIFI_PASSWD")
    else:
        logger.info("SAT缓存中没有DHU热点信息")
        Input_Mgr.Instance().confirm("首次连接该汽车的DHU热点,请确认DHU热点已经打开")
    
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
            raise_err("连接DHU的热点失败,用户取消热点连接")        
        break

    if cached_ssid == None:
        raise_err("连接DHU的热点失败,用户没有找到DHU的热点")

    cached_passwd = Input_Mgr.Instance().string_input(
                "请输入DHU WIFI热点:{} 对应的WIFI密码".format(cached_ssid))
    for retry_passwd in range(5):
        WiFi_Mgr.Instance().sta_connect_wifi(cached_ssid, cached_passwd)
        for i in range(30):
            sat_sleep(1)
            logger.info("SAT等待热点分配IP中:{}".format(i))
            sta_status = WiFi_Mgr.Instance().status().get("sta_status",{})
            if sta_status.get("ip_address") != None:
                Env_Mgr.Instance().set("VehicleInfo_DHU_WIFI_SSID", cached_ssid)
                Env_Mgr.Instance().set("VehicleInfo_DHU_WIFI_PASSWD", cached_passwd)  
                vehicle_profile = Env_Mgr.Instance().query("VEHICLE_PROFILE")
                if vehicle_profile != None:
                    vehicle_profile.save_wifi_info(None, None, None,
                                                   cached_ssid, None, cached_passwd
                                                    )
                else:
                    logger.error("VEHICLE_PROFILE NOT FOUND In ENV!!")

                raise_ok( "SAT连接DHU的热点成功.连接信息:{}".format(sta_status))

        cached_passwd = Input_Mgr.Instance().string_input(
                "连接超时{}.请重新输入DHU WIFI热点:{} 对应的WIFI密码".format(retry_passwd, cached_ssid)) 

    raise_err("连接DHU的热点失败, 用户输入的DHU热点信息:{} {}无法连接".format(cached_ssid, cached_passwd))
