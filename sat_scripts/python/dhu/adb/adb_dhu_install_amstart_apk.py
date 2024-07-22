import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"settings put global verifier_verify_adb_installs 0")
    isInstallOK = ADB_Mgr.Instance().install_apk(ADB_Mgr.DHU_ADB_SERIAL, "sat_scripts/sattest.apk")
    # ADB_Mgr.Instance().push_file(ADB_Mgr.DHU_ADB_SERIAL,"sat_scripts/wait_start_sattest.sh","/data/local/tmp/")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"settings put global verifier_verify_adb_installs 1")
    # ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"cd /data/local/tmp/;nohup sh /data/local/tmp/wait_start_sattest.sh &")
    if isInstallOK == True: 
        raise_ok("安装测试am start的apk成功")
    else:
        raise_err("安装应用失败")
if __name__ == '__main__':
    main()