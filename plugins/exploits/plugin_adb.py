import logging
import pluggy
from typing import Optional, Any
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.core.exploit_spec import ExploitResult


logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("exploit_mgr")

class TCAMCheckPlugin:
    @hookimpl
    def initialize(self):
        logger.info("Initializing ADBExploitPlugin")

    @hookimpl
    def execute(self, target: Optional[Any] = None) -> ExploitResult:
        Input_Mgr.Instance().confirm("请确认TCAM已经通过USB连接SAT，且TCAM的ADB已经关闭")
        return
        vehicle_tcam_serial = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_ADB_SERIAL_ID")
        if vehicle_tcam_serial is None:
            raise_err("车辆未设置TCAM ADB SERIAL ID! VehicleInfo_TCAM_ADB_SERIAL_ID NOT SET!")

        logger.info("TCAM ADB SERIAL ID:{} 尝试本地匹配".format(vehicle_tcam_serial))
        
        adb_devices = ADB_Mgr.Instance().list_devices()
        for dev in adb_devices:
            if dev.serial == vehicle_tcam_serial:
                raise_err("SAT已经扫描到TCAM的ADB设备:{}".format(dev))

        raise_ok("SAT没有扫描到TCAM的ADB设备")

def register_plugin(pm):
    pm.register(TCAMCheckPlugin())
