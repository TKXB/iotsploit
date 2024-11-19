import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    passselinuxs = ["unlabeled","vendor_data_file","vendor_secure_element_vendor_data_file","zeekr_data_file"]
    dirs = ADB_Mgr.Instance().query_dirs_permission_writable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/","",["/dev/","/sys/","/proc/"],passselinuxs)
    #解析result
    if len(dirs) == 0:
        raise_ok("DHU无任意可写的文件夹")
    else:
        # if ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL):
        #     #检查selinux规则
        #     #检查selinux规则
        #     finaldirs = []
        #     passselinuxs = ["unlabeled","vendor_data_file","vendor_secure_element_vendor_data_file","zeekr_data_file"]
        #     for dir in dirs:
        #         logger.info(dir)
        #         isPass = False
        #         for selinux in passselinuxs:
        #             if selinux in dir['sid']:
        #                 isPass = True
        #                 break
        #         if not isPass:
        #             finaldirs.append(dir)
        #     if len(finaldirs) > 0:
        #         raise_err("DHU存在任意可写的文件夹:{}".format(finaldirs))
        #     else:
        #         raise_ok("由于selinux，DHU不存在任意可写的文件夹")
        # else:
        raise_err( "DHU存在任意可写的文件夹:{}".format(dirs))

if __name__ == '__main__':
    main()