import logging
import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
logger = logging.getLogger(__name__)

logger.info("DisConnect to Tcam Ap ...")

Input_Mgr().Instance().confirm("请操作TCAM连接工具热点")
ap_start(AP)
#提示用户操作TCAM连接AP

