import logging
logger = logging.getLogger(__name__)
import time
import random
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr

#这个不能用mac去判断，没办法知道车上tcam的mac
#就直接只允许一个SAT来链接AP就行了
def main():
    # tcam_wifi_sta_mac = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_WIFI_STA_MAC")
    # if tcam_wifi_sta_mac == None:
    #     raise_err( "车辆未设置TCAM STA MAC! VehicleInfo_TCAM_WIFI_STA_MAC未设置!")
    # logger.info("TCAM连接SAT热点, TCAM_WIFI_STA_MAC:{}".format(tcam_wifi_sta_mac))  
    # 
    random_suffix = ''.join(str(random.randint(0, 9)) for _ in range(6))  
    
    sat_ssid, sat_passwd = WiFi_Mgr.Instance().ap_start(ssid = "SAT_" + random_suffix) #密码或ssid需随机生成，防止自动连接
    logger.info("SAT热点已经打开:[{}:{}]".format(sat_ssid, sat_passwd))
    confirm_str = "SAT热点已经打开:[{}:{}],请操作TCAM连接该热点".format(sat_ssid, sat_passwd)
    Input_Mgr.Instance().confirm(confirm_str)
    for i in range(0,10):
        time.sleep(1)
        if len(WiFi_Mgr.Instance().status()['client_list']) > 0:
            break
    query_tcam_ip() 

    # wifi_status = WiFi_Mgr.Instance().status()
    # for client in wifi_status["client_list"]:
    #     if client["mac"].upper() == tcam_wifi_sta_mac.upper():
    #         raise_ok( "TCAM连接SAT热点成功, TCAM DHCP INFO:{}".format(client))
    # raise_err( "TCAM连接SAT热点失败! SAT热点中未找到TCAM的连接信息!")

if __name__ == '__main__':
    main()
