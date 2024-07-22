import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

def main(type:str):
    normal_result = ADB_Mgr.Instance().connect_dev(ADB_Mgr.DHU_ADB_SERIAL)
    if normal_result != None:
        if type == "su":
            idresult = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"su;id")
            #检查id
            logger.info(idresult)
        else:
            root_result = ADB_Mgr.Instance().connect_dev(ADB_Mgr.DHU_ADB_SERIAL, True)
            if root_result != None:
                raise_err("车辆可以adb root")
            else:
                raise_ok("车辆不可以adb root")
                # #通过改属性来绕过adb root
                # propdebug = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"getprop ro.debugable")
                # if propdebug == "0":
                #     raise_ok("车辆无法adb root")
                # else:
                #     ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"setprop xxx")
                #     Input_Mgr.Instance().confirm("请关闭adb并重新打开adb")
                #     idresult = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"id")
                #     #检查id
    else:
        raise_err("车辆未连接adb shell")

if __name__ == '__main__':
    main()