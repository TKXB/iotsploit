import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    files = ADB_Mgr.Instance().query_files_permission_writable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/","",["/dev/","/proc/","/sys/"],["unlabeled"])
    #解析result
    if len(files) == 0:
        raise_ok("DHU无任意可写的文件")
    else:
        # if ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL):
        #     #检查selinux规则
        #     finalfiles = []
        #     passselinuxs = ["unlabeled"]
        #     for file in files:
        #         isPass = False
        #         for selinux in passselinuxs:
        #             if selinux in file['sid']:
        #                 isPass = True
        #                 break
        #         if not isPass:
        #             finalfiles.append(file)
        #     if len(finalfiles) > 0:
        #         raise_err("DHU存在任意可写的文件:{}".format(finalfiles))
        #     else:
        #         raise_ok("由于selinux，DHU不存在任意可写的文件")
        # else:
        raise_err( "DHU存在任意可写的文件:{}".format(files))

if __name__ == '__main__':
    main()