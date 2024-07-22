import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr


def main():
    result = ADB_Mgr.Instance().query_files_permission_suid(ADB_Mgr.DHU_ADB_SERIAL)
    #解析result
    if len(result) == 0:
        raise_ok("DHU无SUID程序")
    else:
        raise_err( "DHU存在SUID程序:{}".format(result))
    raise_ok( "DHU SUID程序:{}".format(result))
if __name__ == '__main__':
    main()