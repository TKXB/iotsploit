import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

def main(type:str):
    if type == "engineer":
        isAmOK = False
        if Input_Mgr.Instance().single_choice("使用测试app开启工程模式，是否有工程模式界面弹出",["是","否"]) == "是":
            isAmOK = True
        if isAmOK:
            raise_err("可以通过am启动工程模式")
        else:
            raise_ok("不可以通过am启动工程模式")
    elif type == "settings":
        isAmOK = False
        if Input_Mgr.Instance().single_choice("使用测试 app开启系统设置，是否有系统设置界面弹出",["是","否"]) == "是":
            isAmOK = True
        if isAmOK:
            raise_err("可以通过am启动系统设置")
        else:
            raise_ok("不可以通过am启动系统设置")
    else:
        raise_err("am type错误")

if __name__ == '__main__':
    main()