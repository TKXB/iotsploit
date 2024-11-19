import logging
import re
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main():
    # results1 = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find / -perm -2 -type f -print0 -name \"*.log\" 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null").strip()
    # results = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find / -perm -4 -type f  -name \"*.log\" -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null").strip()
    # # results = (results1 + "\n" + results2).strip()
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
    files = ADB_Mgr.Instance().query_files_permission_readable_by_any_user(ADB_Mgr.DHU_ADB_SERIAL,"/","*.log",[],[])
    if len(files) > 0:
        raise_err( "DHU 日志文件权限有问题，可以被其他人读取。 List:{}".format(files))
    else:    
        raise_ok( "DHU 日志文件权限没问题")
if __name__ == '__main__':
    main()