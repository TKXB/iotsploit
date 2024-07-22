import logging
import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.net_audit_mgr import net_scan
logger = logging.getLogger(__name__)

logger.info("DisConnect to Tcam Ap ...")

Input_Mgr().Instance().confirm("请操作TCAM连接工具热点")


net_scan().Instance().port_detect("192.168.225.1","1-65535")


net_scan().Instance().port_detect("192.168.15.1","1-65535")