import logging
logger = logging.getLogger(__name__)
import time
import json

from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.net_audit_mgr import NetAudit_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.adb_mgr import *

def my_check_ecu_alive(ecu,checktype,attack_type):
    if not check_ecu_alive(ecu,checktype):
        if attack_type == "icmp":
            NetAudit_Mgr.Instance().stop_icmp_flood_attack()
        elif attack_type == "udp":
            NetAudit_Mgr.Instance().stop_udp_flood_attack()
        elif attack_type == "tcp":
            NetAudit_Mgr.Instance().stop_tcp_flood_attack()
        elif attack_type == "mac":
            NetAudit_Mgr.Instance().stop_mac_flood_attack()          
        raise_err("{}异常".format(ecu))

def main(attack_type:str,ecu:str):

    logger.info("before {} {} flood check".format(ecu,attack_type))
    my_check_ecu_alive(ecu,"ip",attack_type)
    
    ecu_ip = ""
    if ecu == "tcam":
        ecu_ip = query_tcam_ip()
    elif ecu == "dhu":
        ecu_ip = query_dhu_ip()
    elif ecu == "vgm":
        ecu_ip = "169.254.19.1"

    if attack_type == "icmp":
        NetAudit_Mgr.Instance().start_icmp_flood_attack(ecu_ip)
    elif attack_type == "udp":
        NetAudit_Mgr.Instance().start_udp_flood_attack(ecu_ip)
    elif attack_type == "tcp":
        NetAudit_Mgr.Instance().start_tcp_flood_attack(ecu_ip)
    elif attack_type == "mac":
        if ecu == "vgm":
            NetAudit_Mgr.Instance().start_mac_flood_attack(ecu_ip,"eth0")
        else:
            NetAudit_Mgr.Instance().start_mac_flood_attack(ecu_ip)

    logger.info("in {} {} flood check".format(ecu,attack_type))
    for i in range(0,6): #间隔5秒，检查30秒
        time.sleep(5)
        my_check_ecu_alive(ecu,"ip",attack_type)

    if attack_type == "icmp":
        NetAudit_Mgr.Instance().stop_icmp_flood_attack()
    elif attack_type == "udp":
        NetAudit_Mgr.Instance().stop_udp_flood_attack()
    elif attack_type == "tcp":
        NetAudit_Mgr.Instance().stop_tcp_flood_attack()
    elif attack_type == "mac":
        NetAudit_Mgr.Instance().stop_mac_flood_attack()    

    logger.info("after {} {} flood check".format(ecu,attack_type))
    my_check_ecu_alive(ecu,"ip",attack_type)

    raise_ok("{} {} flood ok".format(ecu,attack_type))
    
if __name__ == '__main__':
    main()