import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *
import re
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
#不用了
def main(file_path:str):
    results1 = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find {} -perm -2 -type f -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(file_path)).strip()
    results2 = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL, "find {} -perm -4 -type f -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(file_path)).strip()
    results = (results1 + "\n" + results2).strip()
    logger.info(results)
    files = []
    itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
    for item in results.splitlines():
        finditem = itemregx.findall(item)
        rwx = finditem[0][0]
        owner = finditem[0][1]
        group = finditem[0][2]
        sid = finditem[0][3]
        filepath = finditem[0][4]
        file = {"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath}
        if file not in files:
            files.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath})
    if len(files) > 0:
        raise_err( "DHU {} 目录里文件权限有问题 List:{}".format(file_path,files))
    else:    
        raise_ok( "DHU {} 目录里文件权限没问题".format(file_path))

if __name__ == '__main__':
    main()