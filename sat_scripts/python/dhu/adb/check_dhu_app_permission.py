import logging
import re
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    # results1 = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find /data/data/ -perm -2 -type f -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null").strip()
    # results2 = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find /data/data/ -perm -4 -type f -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null").strip()
    # results = (results1 + "\n" + results2).strip()
    # logger.info(results)
    # files = []
    # itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
    # for item in results.splitlines():
    #     finditem = itemregx.findall(item)
    #     rwx = finditem[0][0]
    #     owner = finditem[0][1]
    #     group = finditem[0][2]
    #     sid = finditem[0][3]
    #     filepath = finditem[0][4]
    #     file = {"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath}
    #     if file not in files:
    #         files.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath})
    files = ADB_Mgr.Instance().query_files_permission_writable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/data/data/","",["/dev/","/proc/","/sys/"],["unlabeled"])
    files2 = ADB_Mgr.Instance().query_files_permission_readable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/data/data/","",[],[])
    for f in files2:
        if f not in files:
            files.append(f)
    if len(files) > 0:
        raise_err( "DHU App数据权限有问题 List:{}".format(files))
    else:    
        raise_ok( "DHU App数据权限没问题")
if __name__ == '__main__':
    main()