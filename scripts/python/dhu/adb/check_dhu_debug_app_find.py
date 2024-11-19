import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr


def main():
    #只需要给app list，然后由step进行判断
    result = ADB_Mgr.Instance().list_debug_apps(ADB_Mgr.DHU_ADB_SERIAL,["debug","test"])
    #再加上find / -name "*debug*" 2>/dev/null

    logger.info(result)
    #判断result
    if len(result) > 0:
        raise_err("DHU Debug App List:{}".format(result))
    else:
        raise_ok("DHU没有测试类程序")

if __name__ == '__main__':
    main()