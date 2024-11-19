import logging
import re
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    files = ADB_Mgr.Instance().query_files_permission_writable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/","*.conf",["/dev/","/proc/","/sys/"],["unlabeled"])
    if len(files) > 0:
        raise_err( "DHU 配置文件权限有问题，可以被其他人改。 List:{}".format(files))
    else:    
        raise_ok( "DHU 配置文件权限没问题")
if __name__ == '__main__':
    main()