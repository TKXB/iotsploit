#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.usb_mgr import USB_Mgr

def main(key, value):
    logger.info("ALL ENV Before Update")
    list usb_device_list =  USB_Mgr.Instance().get_usb_list
        # 打印解析结果
    for device in usb_device_list:
        # 打印每个设备的信息
        print(f"Bus {device['bus']} Device {device['device']}: ID {device['vendor_product_id']} {device['description']}")
        # 这里需要添加过滤
    return -1,"test"