import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr



def main():
    result = ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL)
    if result == True:
        raise_ok( "DHU 启动了selinux")
    else:
        raise_err( "DHU 未启动selinux")

if __name__ == '__main__':
    main()