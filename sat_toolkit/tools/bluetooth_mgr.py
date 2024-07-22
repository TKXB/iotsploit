import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from bluepy.btle import *

class Bluetooth_Mgr:

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass


#=============
    #TODO 开始l2ping攻击
    def start_l2ping_attack(self):
        pass

    #TODO 停止l2ping攻击
    def stop_l2ping_attack(self):
        pass

#=============
    #TODO 开始deauth攻击
    def start_deauth_attack(self):
        pass

    #TODO 停止deauth攻击
    def stop_deauth_attack(self):
        pass

#=============

    def query_classic_dev_list(self):
        """
        查询经典蓝牙信息
        classic_list = Bluetooth_Mgr.Instance().query_classic_dev_list()

        Return:
        [{'mac': 'A4:04:50:31:44:54', 'name': 'Lotus', 'class': 'Audio/Video, Hands-free (0x260408)'}, {'mac': '80:A5:89:53:86:5C', 'name': 'Pixel C', 'class': 'Computer, Unknown (reserved) minor device class (0x1a011c)'}]
        """
        bash_cmd = \
"""
sudo hciconfig hci0 reset
sudo hcitool scan --flush --class
"""

        logger.info("BlueTooth Classic Device List Scan Start. -->>")
        result_code, result_buffer = Bash_Script_Mgr.Instance().exec_cmd(bash_cmd)
        if result_code < 0:
            logger.error("BlueTooth Classic Device List Scan Fail! <<--")
            return None
        """
        Scanning ...

        BD Address:     A4:04:50:31:44:54 [mode 1, clkoffset 0x77f9]
        Device name:    Lotus
        Device class:   Audio/Video, Hands-free (0x260408)

        BD Address:     22:22:45:08:FB:7F [mode 1, clkoffset 0x4b33]
        Device name:    Lotus
        Device class:   Audio/Video, Hands-free (0x360408)

        """        
        classic_dev_list = []
        for line in result_buffer.splitlines():
            if line.startswith("BD Address:"):
                mac = line.replace("BD Address:", "", 1).lstrip().split(" ", 1)[0]
                dev_dict = { "mac":mac }
                classic_dev_list.append(dev_dict)
            if line.startswith("Device name:"):
                name = line.replace("Device name:", "", 1).lstrip()
                dev_dict["name"] = name
            if line.startswith("Device class:"):
                dev_class = line.replace("Device class:", "", 1).lstrip()
                dev_dict["class"] = dev_class
    
        logger.info("BlueTooth Classic Device List Scan Finish. Device List:\n{}".format(classic_dev_list))
        return classic_dev_list

    def query_classic_dev_info_by_mac_addr(self, mac_addr:str):
        """
        查询经典蓝牙信息by mac
        dev_info = Bluetooth_Mgr.Instance().query_classic_dev_info_by_mac_addr("A4:04:50:31:44:54")

        Return:
        {'mac': 'A4:04:50:31:44:54', 'oui': 'nFore Technology Inc. (A4-04-50)', 'name': '5.2 (0xb) LMP Subversion: 0x55b9', 'Manufacturer': 'Qualcomm (29)'}        
        """

        mac_addr = mac_addr.upper()
        bash_cmd = \
"""
sudo hciconfig hci0 reset
sudo hcitool info {}
""".format(mac_addr)

        logger.info("BlueTooth Classic Device Info Scan Start. MAC:{} -->>".format(mac_addr))
        result_code, result_buffer = Bash_Script_Mgr.Instance().exec_cmd(bash_cmd)
        if result_code < 0:
            logger.error("BlueTooth Classic Device Info Scan Fail! MAC:{}  <<--".format(mac_addr))
            return None
        """
        Requesting information ...
        BD Address:  BC:64:D9:83:19:30
        OUI Company: GUANGDONG OPPO MOBILE TELECOMMUNICATIONS CORP.,LTD (BC-64-D9)
        Device Name: 一加 Ace 2
        LMP Version:  (0xc) LMP Subversion: 0x4c61
        Manufacturer: Qualcomm (29)
        Features page 0: 0xff 0xfe 0x8f 0xfe 0xd8 0x3f 0x5b 0x87
                <3-slot packets> <5-slot packets> <encryption> <slot offset>
                ......
                <non-flush flag> <LSTO> <inquiry TX power> <EPC>
                <extended features>
        Features page 1: 0x0b 0x00 0x00 0x00 0x00 0x00 0x00 0x00
        Features page 2: 0x55 0x03 0x00 0x00 0x00 0x00 0x00 0x00
        """
        
        dev_dict = {}
        for line in result_buffer.splitlines():
            if line.lstrip().startswith("BD Address:"):
                dev_dict["mac"] = line.replace("BD Address:", "", 1).lstrip()
            if line.lstrip().startswith("OUI Company:"):
                dev_dict["oui"] = line.replace("OUI Company:", "", 1).lstrip()
            if line.lstrip().startswith("Device Name:"):
                dev_dict["name"] = line.replace("Device Name:", "", 1).lstrip()
            if line.lstrip().startswith("LMP Version:"):
                dev_dict["lmp"] = line.replace("LMP Version:", "", 1).lstrip()
            if line.lstrip().startswith("Manufacturer:"):
                dev_dict["Manufacturer"] = line.replace("Manufacturer:", "", 1).lstrip()

        logger.info("BlueTooth Classic Device Info Scan Finish. MAC:{} Device Info:\n{}".format(mac_addr, dev_dict))
        return dev_dict


    #TODO 查询经典蓝牙信息by name
    def query_classic_dev_info_by_name(self, name:str):
        """
        查询经典蓝牙信息by name
        classic_list = Bluetooth_Mgr.Instance().query_classic_dev_info_by_name("OPPO Find X6 Pro")

        Return:
        {'mac': 'A4:04:50:31:44:54', 'oui': 'nFore Technology Inc. (A4-04-50)', 'name': '5.2 (0xb) LMP Subversion: 0x55b9', 'Manufacturer': 'Qualcomm (29)'}   
        """
        
        logger.info("BlueTooth Classic Device Info Scan Start. Name:{} -->>".format(name))

        classic_list = Bluetooth_Mgr.Instance().query_classic_dev_list()
        if classic_list == None:
            logger.error("BlueTooth Classic Device Info Scan Fail! Name:{} Classic Device List Query Fail!".format(name))
            return None
        
        for dev in classic_list:
            if dev["name"] == name:
                logger.info("Find First Device:{} Match Name.Use This Device Mac".format(dev))
                return self.query_classic_dev_info_by_mac_addr(dev["mac"])
        
        logger.info("BlueTooth Classic Device Info Scan Finish.No Device Name Match. Name:{} <<--".format(name))
        return None    

#=============
    def query_ble_info_by_mac_addr(self, mac_addr:str):
        """
        查询BLE信息by mac
        dev_info = Bluetooth_Mgr.Instance().query_ble_info_by_mac_addr("70:B9:50:F7:BB:7F")

        Return:
        
        """

        mac_addr = mac_addr.upper()
        bash_cmd = \
"""
sudo hciconfig hci0 reset
sudo hcitool leinfo {}
""".format(mac_addr)

        logger.info("BlueTooth BLE Info Scan Start. MAC:{} -->>".format(mac_addr))
        result_code, result_buffer = Bash_Script_Mgr.Instance().exec_cmd(bash_cmd)
        if result_code < 0:
            logger.error("BlueTooth BLE Info Scan Fail! MAC:{}  <<--".format(mac_addr))
            return None
        """
        Requesting information ...
                Handle: 64 (0x0040)
                LMP Version: 5.1 (0xa) LMP Subversion: 0x221
                Manufacturer: Texas Instruments Inc. (13)
                Features: 0x3f 0x00 0x00 0x00 0x00 0x00 0x00 0x00
        """
        
        dev_dict = {}
        for line in result_buffer.splitlines():
            if line.lstrip().startswith("Handle:"):
                dev_dict["handle"] = line.replace("Handle:", "", 1).lstrip()
            if line.lstrip().startswith("LMP Version:"):
                dev_dict["lmp"] = line.replace("LMP Version:", "", 1).lstrip()
            if line.lstrip().startswith("Manufacturer:"):
                dev_dict["Manufacturer"] = line.replace("Manufacturer:", "", 1).lstrip()
            if line.lstrip().startswith("Features:"):
                dev_dict["Features"] = line.replace("Features:", "", 1).lstrip()

        try:
            remote_dev = Peripheral(mac_addr, ADDR_TYPE_PUBLIC)
            dev_dict["STATUS"] = remote_dev.getState()

            service_list = []
            dev_dict["service_list"] = service_list
            logger.info("DEV STATUS:{}".format(remote_dev.getState()))
            logger.info("DEV Services:")
            for single_service in remote_dev.getServices():
                service_dict = {}
                service_list.append(service_dict)
                service_dict["uuid"] = single_service.uuid
                logger.info("\tservice uuid:{}".format(single_service.uuid))
                # chars = single_service.getCharacteristics()
                # logger.info("\t\t<handle>\t<property>\t<can read>\tuuid")
                # for single_char in chars:
                #     logger.info("\t\t{}\t{}({})\t{}\t{}".format
                #                 (hex(single_char.getHandle()),single_char.propertiesToString(),hex(single_char.properties),  single_char.supportsRead(), single_char.uuid )  )

            # logger.info("DEV Characteristics:")
            # logger.info("\t<handle>\t<can read>\t<property>\tuuid")
            # for single_char in remote_dev.getCharacteristics():    
            #     logger.info("\t{}\t{}({})\t{}\t{}".format
            #                 (hex(single_char.getHandle()),single_char.propertiesToString(),hex(single_char.properties),  single_char.supportsRead(), single_char.uuid )  )

            # logger.info("DEV Descriptors:")
            # for remote_decs in remote_dev.getDescriptors():
            #     logger.info("\t{}".format(remote_decs))

            remote_dev.disconnect()
        except Exception as err:
            logger.exception("BlueTooth BLE Info Service Read Fail! MAC:{}  <<--".format(mac_addr))

        logger.info("BlueTooth BLE Info Scan Finish. MAC:{} Device Info:\n{}".format(mac_addr, dev_dict))
        return dev_dict

    #TODO 查询BLE信息by name
    def query_ble_info_by_name(self, name:str):
        pass


#=============
    #TODO 打开经典蓝牙广播
    def enable_classic_adv(self, name:str, auth_mode:str):
        """
        打开经典蓝牙广播
        不加密
        Bluetooth_Mgr.Instance().enable_classic_adv("SATTestOPEN", "OPEN")
        使用PIN_CODE配对,PIN码固定为1234. (目前有点问题)
        Bluetooth_Mgr.Instance().enable_classic_adv("SATTestPIN_CODE", "PIN_CODE")
        使用简单配对
        Bluetooth_Mgr.Instance().enable_classic_adv("SATTestJust_Works", "Just_Works")

        Return:
        """
        logger.info("BlueTooth Enable Classic Adv Start. Name:{} auth_mode:{}".format(name, auth_mode))

        auth_cmd = "sudo hciconfig hci0 noauth"
        if auth_mode == "PIN_CODE":
            auth_cmd = "sudo hciconfig hci0 sspmode 1\nsudo hciconfig hci0 ssp 1234"
        if auth_mode == "Just_Works":
            auth_cmd = "sudo hciconfig hci0 sspmode 0"

        bash_cmd = \
"""
sudo hciconfig hci0 reset
sudo hciconfig hci0 piscan
sudo hciconfig hci0 name "{}"
sudo hciconfig hci0 class 0x100
{}
""".format(name, auth_cmd)

        result_code, result_buffer = Bash_Script_Mgr.Instance().exec_cmd(bash_cmd)
        if result_code < 0:
            logger.error("BlueTooth Enable Classic Adv Fail! Name:{} auth_mode:{}".format(name, auth_mode))
            return result_code
     
        logger.info("BlueTooth Enable Classic Adv Success. Name:{} auth_mode:{}".format(name, auth_mode))
        return 1


    #TODO 
    def disable_classic_adv(self):
        """
        关闭经典蓝牙广播
        Bluetooth_Mgr.Instance().disable_classic_adv()

        Return:
        """
        logger.info("BlueTooth Disable Classic Adv Start. Name:{} auth_mode:{}")
        bash_cmd = \
"""
sudo hciconfig hci0 noscan
"""
        result_code, result_buffer = Bash_Script_Mgr.Instance().exec_cmd(bash_cmd)
        if result_code < 0:
            logger.error("BlueTooth Disable Classic Adv Fail!")
            return result_code

        logger.info("BlueTooth Disable Classic Adv Success.")
        return 1

#=============
    #TODO 打开蓝牙ble广播
    def enable_ble(self, name:str):
        pass


    #TODO 关闭蓝牙ble广播
    def disable_ble(self, name:str):
        pass



_instance = Bluetooth_Mgr()

