import logging
import re
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr

def main(version1:str,version2:str,version3:str,version4:str):
    version = ADB_Mgr.Instance().query_android_webview_version(ADB_Mgr.DHU_ADB_SERIAL).strip()
    #解析result
    # logger.info("webview版本:{}".format(version))
    #versionName=83.0.4103.120
    restr = re.compile("versionName=(.*)\.(.*)\.(.*)\.(.*)")
    versions = restr.findall(version)[0]
    isOK = False
    if int(versions[0]) > int(version1):
        isOK = True
    elif int(versions[0]) == int(version1):
        if int(versions[1]) > int(version2):
            isOK = True
        elif int(versions[1]) == int(version2):
            if int(versions[2]) > int(version3):
                isOK = True
            elif int(versions[2]) == int(version3):
                if int(versions[3]) >= int(version4):
                    isOK = True
    if isOK:
        raise_ok("DHU WebView Version:{} is OK，大于{}.{}.{}.{}".format(version,version1,version2,version3,version4))
    else:
        raise_err("DHU WebView Version:{} is Not OK，小于{}.{}.{}.{}".format(version,version1,version2,version3,version4))

if __name__ == '__main__':
    main()