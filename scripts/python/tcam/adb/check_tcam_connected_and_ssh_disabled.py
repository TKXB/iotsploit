import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.vehicle_utils import *

def main():
    tcamip = query_tcam_ip()
    portlist = NetAudit_Mgr.Instance().port_detect([tcamip],"22")
    if len(portlist) > 0:
        Input_Mgr.Instance().confirm("即将关闭tcam调试模式，请确认已连接了odb线。")
        DoIP_Mgr.Instance().closedebug("tcam")
        portlist = NetAudit_Mgr.Instance().port_detect([tcamip],"22")
        if len(portlist) > 0:
            raise_err("关闭tcam ssh失败")
    raise_ok("tcam ssh已关闭")
    # Input_Mgr.Instance().confirm("请确认TCAM已经通过USB连接SAT，且TCAM的ADB已经关闭")
    # #这个不能用人工输入的serial来比对，自动化方法如下：
    # #1. lsusb -v 可以拿到iproduct,ivendor，这个对于tcam和dhu是不一样的。
    # #2. 找到tcam和dhu后，然后lsusb -v里的iserial就是adb的serial
    # vehicle_tcam_serial = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_ADB_SERIAL_ID")
    # if vehicle_tcam_serial == None:
    #     raise_err( "车辆未设置TCAM ADB SERIAL ID! VehicleInfo_TCAM_ADB_SERIAL_ID NOT SET!")

    # logger.info("TCAM ADB SERIAL ID:{} 尝试本地匹配".format(vehicle_tcam_serial))
    
    # adb_devices = ADB_Mgr.Instance().list_devices()
    # for dev in adb_devices:
    #     if dev.serial == vehicle_tcam_serial:
    #         raise_err( "SAT已经扫描到TCAM的ADB设备:{}".format(dev))

    # raise_ok( "SAT没有扫描到TCAM的ADB设备")

if __name__ == '__main__':
    main()