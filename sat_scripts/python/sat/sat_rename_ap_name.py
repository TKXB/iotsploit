import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

def main():
    logger.info("SAT使用特定SSID开启热点开始-->>")

    ssid = "%s%s%s%s%p%p%n%p%n%n%s%p%n%s%s"
    # ssid = "bbbbbbb"
    pwd = "12345678"
    WiFi_Mgr.Instance().ap_start(ssid,pwd)
    Input_Mgr.Instance().confirm("请用错误的密码连接热点:{},密码:88888888".format(ssid))
    tcam_alive = check_tcam_alive("doip")
    dhu_alive =  check_dhu_alive("doip")
    if tcam_alive == False or dhu_alive == False:
        raise_err("wifi格式化字符串，车辆出现异常.tcam:{},dhu:{}".format(tcam_alive,dhu_alive))

    Input_Mgr.Instance().confirm("请用正确的密码连接热点:{},密码:{}".format(ssid,pwd))
    tcam_alive = check_tcam_alive("doip")
    dhu_alive =  check_dhu_alive("doip")
    if tcam_alive == False or dhu_alive == False:
        raise_err("wifi格式化字符串，车辆出现异常.tcam:{},dhu:{}".format(tcam_alive,dhu_alive))

    raise_ok("wifi不受到格式化字符串影响")

if __name__ == '__main__':
    main()