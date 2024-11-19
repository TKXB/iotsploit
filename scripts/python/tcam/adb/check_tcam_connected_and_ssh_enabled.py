import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.vehicle_utils import *
def main():
    connect_tcam_wifi()
    portlist = NetAudit_Mgr.Instance().port_detect([query_tcam_ip()],"22")
    if len(portlist) > 0:
        raise_ok("tcam已开启ssh")
    else:
        Input_Mgr.Instance().confirm("即将开启tcam调试模式，请确认已连接了odb线。")
        DoIP_Mgr.Instance().opendebug("tcam")
        connect_tcam_wifi()
        portlist = NetAudit_Mgr.Instance().port_detect([query_tcam_ip()],"22")
        if len(portlist) > 0:
            raise_ok("tcam已开启ssh")
    raise_err("连接tcam ssh失败")

if __name__ == '__main__':
    main()