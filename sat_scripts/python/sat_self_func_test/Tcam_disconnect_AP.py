import logging
import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
logger = logging.getLogger(__name__)

logger.info("DisConnect to Tcam Ap ...")

Input_Mgr().Instance().confirm("是否断开热点?")
ap_stop()