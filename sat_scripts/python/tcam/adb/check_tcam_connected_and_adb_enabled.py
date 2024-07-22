import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr

def main():
    # Input_Mgr.Instance().confirm("请确认连接了usb线，并切换ADB为Device模式。")
    isOpenADB = ADB_Mgr.Instance().check_connect_status(ADB_Mgr.TCAM_ADB_SERIAL)
    if isOpenADB:
        raise_ok("已经开了adb")
    else:
        ret = Input_Mgr.Instance().single_choice("TCAM是否已开启调试模式",["是","否"])
        if ret == "否":
            Input_Mgr.Instance().confirm("即将开启调试模式，请确认已连接了odb线。")
            DoIP_Mgr.Instance().opendebug("tcam")
            Input_Mgr.Instance().confirm("已开启调试模式，请切换ADB为Device模式。")
            isOpenADB = ADB_Mgr.Instance().check_connect_status(ADB_Mgr.TCAM_ADB_SERIAL)
            if isOpenADB:
                raise_ok("已经开了adb")
            else:
                raise_err("连接adb失败")

if __name__ == '__main__':
    main()