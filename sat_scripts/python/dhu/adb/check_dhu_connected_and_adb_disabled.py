import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr

def main(isCloseADB:str):
    isOpenADB = False
    try:
        isOpenADB = ADB_Mgr.Instance().check_connect_status(ADB_Mgr.DHU_ADB_SERIAL)
    except SAT_Exception:
        isOpenADB = False
    if isOpenADB:
        if isCloseADB == "true":
            DoIP_Mgr.Instance().closedebug("dhu")
            isOpenADB = False
            try:
                isOpenADB = ADB_Mgr.Instance().check_connect_status(ADB_Mgr.DHU_ADB_SERIAL)
            except SAT_Exception:
                isOpenADB = False
            if isOpenADB:
                raise_err("关adb失败")
            else:
                raise_ok("关adb成功")
        else:
            raise_err("没有关adb")
    else:
        raise_ok("已关闭adb")
        
if __name__ == '__main__':
    main()