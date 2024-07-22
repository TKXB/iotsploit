import logging
import subprocess
import re
import usb
logger = logging.getLogger(__name__)

from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr

class USB_Mgr:

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass

    #TODO SAT模拟为U盘
    def mount_as_usb_flash_disk(self):
        logger.info("mount_as_usb_flash_disk called! 功能尚未实现")
        return 1


    #TODO SAT模拟为鼠标 模拟各种USB设备
    def mount_as_usb_mouse(self):
        logger.info("mount_as_usb_mouse called! 功能尚未实现")
        return 1


    #TODO SAT模拟为键盘 模拟各种USB设备
    def mount_as_usb_keyboard(self):
        logger.info("mount_as_usb_keyboard called! 功能尚未实现")
        return 1

    def list_usb_devices(self):
        """
        [{'description': 'GenesysLogic USB3.1 Hub', 'idVendor': 1507, 'idProduct': 1574, 'iSerialNumber': None}, {'description': 'Linux 6.1.0-rpi6-rpi-v8 xhci-hcd xHCI Host Controller', 'idVendor': 7531, 'idProduct': 3, 'iSerialNumber': '0000:01:00.0'}, {'description': 'GenesysLogic USB2.1 Hub', 'idVendor': 1507, 'idProduct': 1552, 'iSerialNumber': None}, {'description': 'ALK,Incorporated ALK Mobile Boardband', 'idVendor': 6610, 'idProduct': 1368, 'iSerialNumber': '1234567890ABCDEF'}, {'description': 'None USB2.0 Hub', 'idVendor': 8457, 'idProduct': 13361, 'iSerialNumber': None}, {'description': 'Linux 6.1.0-rpi6-rpi-v8 xhci-hcd xHCI Host Controller', 'idVendor': 7531, 'idProduct': 2, 'iSerialNumber': '0000:01:00.0'}]

        """
        logger.info("List Usb Devices Start -->>")
        # 解析输出
        devices = []
        for usb_dev in usb.core.find(find_all=True):                
            try:
                description = "{} {}".format(usb_dev.manufacturer, usb_dev.product)
            except Exception as err:
                description = "{}".format(str(usb_dev))

            devices.append(
                {
                    'description':description,
                    'idVendor':  usb_dev.idVendor,
                    'idProduct': usb_dev.idProduct,
                    'iSerialNumber':usb_dev.serial_number,
                })

        logger.info("List Usb Devices Finish. Result:\n{}".format(devices))
        return devices

_instance = USB_Mgr()
