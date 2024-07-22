import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.usb_mgr import USB_Mgr


def main():
    logger.info("SAT查找本地USB DEBUG端口开始 -->>")

    #串口监控这样做不够，需要监控/dev/中是否有新增tty*的文件。
    dev_list = USB_Mgr.Instance().list_usb_devices()
    debug_ports = []
    for dev in dev_list:
        desc = dev["description"].upper()
        if desc.find("UART".upper()) != -1 or \
        desc.find("Fibocom SDXPRAIRIE-ADP".upper()) != -1 or \
        desc.find("Serial".upper()) != -1 :
            debug_ports.append(dev)
    
    if len(debug_ports) == 0:
        raise_ok( "SAT未发现本地USB DEBUG端口")

    else:
        raise_err( "SAT发现本地USB DEBUG端口:{}".format(debug_ports))

if __name__ == '__main__':
    main()