import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.usb_mgr import USB_Mgr



def main(usb_type:str):
    logger.info("SAT模拟为USB设备开始. USB TYPE:{} -->>".format(usb_type))

    if usb_type == "usb_flash_disk":
        result = USB_Mgr.Instance().mount_as_usb_flash_disk()    
    elif usb_type == "usb_mouse":
        result = USB_Mgr.Instance().mount_as_usb_mouse()
    elif usb_type == "usb_keyboard":
        result = USB_Mgr.Instance().mount_as_usb_keyboard()
    else:
        result = -1
    
    if result < 0:
        raise_err( "SAT模拟为USB设备失败. USB TYPE:{}".format(usb_type))
    else:
        raise_ok( "SAT模拟为USB设备成功. USB TYPE:{}".format(usb_type))

if __name__ == '__main__':
    main()