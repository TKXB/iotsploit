import logging
logger = logging.getLogger(__name__)
from input_mgr import Input_Mgr
from sat_toolkit.tools.usb_mgr import USB_Mgr

logger.info("Connect to ADB shell...")
devices = ADB_Mgr.Instance().list_devices()

# 提取 serial 值
serials = [device.serial for device in devices]

ADB_Mgr().Instance().connect_dev(serials,False) #这里取值有点问题




