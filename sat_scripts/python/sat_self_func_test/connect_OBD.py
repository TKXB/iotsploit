import logging
import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
logger = logging.getLogger(__name__)

logger.info("Connect to OBD ...")

Input_Mgr().Instance().confirm("请操作工具箱连接OBD")