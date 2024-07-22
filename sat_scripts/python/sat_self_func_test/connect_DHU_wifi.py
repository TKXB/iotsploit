import logging
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.wifi_mgr import Wifi_Mgr
logger = logging.getLogger(__name__)

logger.info("Connect to DHU Ap ...")

wifi_ssid = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_DHU_WIFI_SSID")
wifi_passwd = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_DHU_WIFI_PASSWD")
Wifi_Mgr().Instance().sta_connect_wifi(wifi_ssid,wifi_passwd)
