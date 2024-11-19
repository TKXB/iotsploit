import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    adb_pull_file_path = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_ADB_PULL_FILE")    
    adb_push_file_path = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_ADB_PUSH_FILE")
    sat_pull_file_path = "/dev/shm/__Zeekr_SAT_TMP_FILES/adb_pull_check.txt"
    sat_push_file_path = "/home/sat/zeekr_sat_rep_local/scripts/python/tcam/adb/adb_push_check.txt"
    logger.info("adb_pull_file_path:{}".format(adb_pull_file_path))
    logger.info("adb_push_file_path:{}".format(adb_push_file_path))
    logger.info("sat_pull_file_path:{}".format(sat_pull_file_path))
    logger.info("sat_push_file_path:{}".format(sat_push_file_path))

    pull_result = ADB_Mgr.Instance().pull_file(ADB_Mgr.TCAM_ADB_SERIAL, adb_pull_file_path, sat_pull_file_path)
    push_result = ADB_Mgr.Instance().push_file(ADB_Mgr.TCAM_ADB_SERIAL, sat_push_file_path, adb_push_file_path)

    total_result = \
"""
TCAM ADB PUSH && PULL TEST RESULT
adb_pull_file_path:{}
adb_push_file_path:{}
sat_pull_file_path:{}
sat_push_file_path:{}

ADB ROOT
pull: {}
push: {}
""".format(adb_pull_file_path, adb_push_file_path, sat_pull_file_path, sat_push_file_path,
           pull_result, pull_result)
    
    raise_ok( total_result)




if __name__ == '__main__':
    main()