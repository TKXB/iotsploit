import logging
import datetime
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

#allowday允许patch早于当前时间多少天，比如三个月就是90天
def main(allowday:str):
    result = ADB_Mgr.Instance().query_android_security_patch_status(ADB_Mgr.DHU_ADB_SERIAL).strip()
    #判断patch的日期是否超过了allowday
    #2020-08-05
    patchdate = datetime.datetime.strptime(result, "%Y-%m-%d")
    delta = datetime.datetime.now() - patchdate
    if delta.days > int(allowday):
        raise_err( "DHU Android Security Patch{}超过了{}天".format(result,delta.days))
    else:
        raise_ok( "DHU Android Security Patch{}没超过{}天".format(result,delta.days))

if __name__ == '__main__':
    main()