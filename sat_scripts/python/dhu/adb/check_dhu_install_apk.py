import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    isInstallOK = ADB_Mgr.Instance().install_apk(ADB_Mgr.DHU_ADB_SERIAL, "sat_scripts/python/dhu/adb/test.apk")
    if isInstallOK == True:
        raise_err("adb可以安装任意应用")
    else:
        raise_ok("adb不可以安装任意应用")
if __name__ == '__main__':
    main()