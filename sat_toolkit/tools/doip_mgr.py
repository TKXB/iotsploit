import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

import socket
import struct
import time
import binascii
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.device_info import DeviceInfo

class DoIP_Mgr:
    __wakeupdata = bytes([0x02,0xfd,0x00,0x05,0x00,0x00,0x00,0x07,0x0e,0x80,0x00,0x00,0x00,0x00,0x00])
    __heartbeatdata = bytes([0x02, 0xfd, 0x80, 0x01, 0x00, 0x00, 0x00, 0x06, 0x0e, 0x80, 0x1f, 0xff, 0x3e, 0x80])

    DHU_Addr = 0x1201
    TCAM_Addr = 0x1011

    @staticmethod
    def Instance():
        return _instance
    
    def __init__(self):
        self.__socket = None

    
    def send_doip_package(self, bytes_to_send, recv_long_msg = True):
        """
        DoIP发送自定义DoIP报文
        """
        if self.connect() != True:
            return b""
        try:
            logger.debug("DoIP Send -> {}".format(bytes_to_send.hex()))
            self.__socket.send(bytes_to_send)
            time.sleep(0.5)
            resp_buf = self.__socket.recv(13)
            logger.debug("DoIP Recv -> {}".format(resp_buf.hex()))
            if len(resp_buf) == 13:
                if recv_long_msg == True:
                    time.sleep(0.5)
                    resp_buf = self.__socket.recv(2048)
                    logger.debug("DoIP Not Recv Enough Data. Retry -> {}".format(resp_buf.hex()))
                    return resp_buf
                else:
                    logger.info("DoIP Read Reply ACK")
                    return b""
            else:
                logger.exception("DoIP Read Reply ACK Faild")
                self.disconnect()
                raise_err("DoIP Read Reply ACK Faild")

        except Exception as err:
            if isinstance(err,TimeoutError):
                logger.exception("无响应")
                return b''
            else:
                logger.exception("DoIP Transfer Data Fail!{}".format(err))
                self.disconnect()
                raise_err("DoIP Transfer Data Fail!{}".format(err))

    def send_wakeup_data(self):
        logger.info("DoIP Send WakeUP Data")
        return self.send_doip_package(DoIP_Mgr.__wakeupdata, True)
    
    def send_heartbeat_data(self):
        logger.info("DoIP Send HeartBeat Data")
        return self.send_doip_package(DoIP_Mgr.__heartbeatdata, False)

    def resetvgm(self):
        while True:
            retbuf = self.send_uds_cmd(0x1011,b"1101")
            if len(retbuf) > 0:
                if retbuf[12] != 0x7f:
                    break
        self.disconnect()
        self.connect()
        while True:
            time.sleep(1)
            retbuf = self.send_uds_cmd(0x1011,b"1001")
            if len(retbuf) > 0:
                if retbuf[12] != 0x7f:
                    break

    def send_uds_cmd(self, targetid, udscmd_content):
        """
        DoIP发送自定义UDS诊断报文
        """
        # self.send_heartbeat_data()

        udscmd_pkg = struct.pack(">H",0x0e80) #myid
        udscmd_pkg += struct.pack(">H",targetid)
        udscmd_pkg += udscmd_content
        
        data = b'\x02\xfd'  #ver 
        data += struct.pack(">H",0x8001) #msg type
        data += struct.pack(">I",len(udscmd_pkg))
        data += udscmd_pkg
        logger.info("DoIP Send UDS Cmd Data To Target:{}, Data:{}".format(targetid,data))
        resp_buf = self.send_doip_package(data)  
        # if resp_buf[-3]==0x7f and resp_buf[-1]==0x78:  #繁忙
        #     logger.warning("DoIP BUSY! Sleep && ReSend.")
        #     time.sleep(2)
        #     resp_buf = self.send_doip_package(data)  
        return resp_buf

    @staticmethod
    def __compute_seed_key(seed, pincode):
        #print("Observed seed: ",seed)
        s1 = pincode[0]
        s2 = pincode[1]
        s3 = pincode[2]
        s4 = pincode[3]
        s5 = pincode[4]
        seed_int = int.from_bytes(seed,'big')
        
        or_ed_seed = ((seed_int & 0xFF0000) >> 16) | (seed_int & 0xFF00) | (s1 << 24) | (seed_int & 0xff) << 16

        mucked_value = 0xc541a9
        
        for i in range(0,32):
            a_bit = ((or_ed_seed >> i) & 1 ^ mucked_value & 1) << 23
            v9 = v10 = v8 = a_bit | (mucked_value >> 1)
            mucked_value = v10 & 0xEF6FD7 | ((((v9 & 0x100000) >> 20) ^ ((v8 & 0x800000) >> 23)) << 20) | (((((mucked_value >> 1) & 0x8000) >> 15) ^ ((v8 & 0x800000) >> 23)) << 15) | (((((mucked_value >> 1) & 0x1000) >> 12) ^ ((v8 & 0x800000) >> 23)) << 12) | 32 * ((((mucked_value >> 1) & 0x20) >> 5) ^ ((v8 & 0x800000) >> 23)) | 8 * ((((mucked_value >> 1) & 8) >> 3) ^ ((v8 & 0x800000) >> 23))

        
        for j in range(0,32):
            v11 = ((((s5 << 24) | (s4 << 16) | s2 | (s3 << 8)) >> j) & 1 ^ mucked_value & 1) << 23
            v12 = v11 | (mucked_value >> 1)
            v13 = v11 | (mucked_value >> 1)
            v14 = v11 | (mucked_value >> 1)
            mucked_value = v14 & 0xEF6FD7 | ((((v13 & 0x100000) >> 20) ^ ((v12 & 0x800000) >> 23)) << 20) | (((((mucked_value >> 1) & 0x8000) >> 15) ^ ((v12 & 0x800000) >> 23)) << 15) | (((((mucked_value >> 1) & 0x1000) >> 12) ^ ((v12 & 0x800000) >> 23)) << 12) | 32 * ((((mucked_value >> 1) & 0x20) >> 5) ^ ((v12 & 0x800000) >> 23)) | 8 * ((((mucked_value >> 1) & 8) >> 3) ^ ((v12 & 0x800000) >> 23))

        key = ((mucked_value & 0xF0000) >> 16) | 16 * (mucked_value & 0xF) | ((((mucked_value & 0xF00000) >> 20) | ((mucked_value & 0xF000) >> 8)) << 8) | ((mucked_value & 0xFF0) >> 4 << 16)
        return key.to_bytes(3, 'big')

    def __opendebug(self, VIN, debug_mcu:str):
        logger.info("Open Debug Mode For VIN:{} Debug_MCU:{} Start -->>. ".format(VIN, debug_mcu))        
        if debug_mcu == "dhu" or debug_mcu == "all":
            #DHU debug
            DHU_PIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_DHU_PIN")
            if DHU_PIN == None:
                raise_err( "测试车辆没有绑定DHU_PIN!")

            if self.__unlock_mcu(DoIP_Mgr.DHU_Addr, DHU_PIN) != True:
                logger.error("Open Debug Mode Fail! Unlock DHU Fail!")
                return False
            logger.info("Unlock DHU Success.")

            resp_buf = self.send_uds_cmd(DoIP_Mgr.DHU_Addr, b'\x2e\xc0\x3e\x01')
            if resp_buf[-3] != 0x6e:
                logger.error("Open Debug Mode Fail! Open Debug For DHU Fail!")
            else:
                logger.info("Open Debug For DHU Success.")

        if debug_mcu == "tcam" or debug_mcu == "all":
            # TCAM debug
            TCAM_PIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_PIN")
            if TCAM_PIN == None:
                raise_err( "测试车辆没有绑定TCAM_PIN!")
            if self.__unlock_mcu(DoIP_Mgr.TCAM_Addr, TCAM_PIN) != True:
                logger.error("Open Debug Mode Fail! Unlock TCAM Fail!")
                return False
            logger.info("Unlock TCAM Success.")

            resp_buf = self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x01\x02\x32')
            if resp_buf[-5] == 0x71:
                logger.info("Open Debug For TCAM Success. 1st Cmd")
                return True
            else:
                logger.info("Open Debug For TCAM Fail! Send 2nd Cmd.")
                resp_buf = self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x01\xDC\x01')
                if resp_buf[-5] == 0x71:
                    logger.info("Open Debug For TCAM Success. 2nd Cmd")
                    return True
                else:
                    logger.error("Open Debug Mode Fail! Open Debug For TCAM Fail!")
                    return False
            
    def __closedebug(self, VIN, debug_mcu:str):
        logger.info("Close Debug Mode For VIN:{} Debug_MCU:{} Start -->>. ".format(VIN, debug_mcu))        
        if debug_mcu == "dhu" or debug_mcu == "all":
            #DHU close debug      
            DHU_PIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_DHU_PIN")
            if DHU_PIN == None:
                raise_err( "测试车辆没有绑定DHU_PIN!")
            #DHU close debug        
            if self.__unlock_mcu(DoIP_Mgr.DHU_Addr, DHU_PIN) != True:
                logger.error("Close Debug Mode Fail! Unlock DHU Fail!")
                return False
            logger.info("Unlock DHU Success.")        
            
            resp_buf = self.send_uds_cmd(DoIP_Mgr.DHU_Addr, b'\x2e\xc0\x3e\x00')
            if resp_buf[-3] != 0x6e:
                logger.error("Close Debug Mode Fail! Close Debug For DHU Fail!")
            else:
                # return False
                logger.info("Close Debug For DHU Success.")

        if debug_mcu == "tcam" or debug_mcu == "all":
        # TCAM close debug
            TCAM_PIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_PIN")
            if TCAM_PIN == None:
                raise_err( "测试车辆没有绑定TCAM_PIN!")
            if self.__unlock_mcu(DoIP_Mgr.TCAM_Addr, TCAM_PIN) != True:
                logger.error("Close Debug Mode Fail! Unlock TCAM Fail!")
                return False
            logger.info("Unlock TCAM Success.")       

            resp_buf = self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x02\x02\x32')
            if resp_buf[-5] == 0x71:
                logger.info("Close Debug For TCAM Success. 1st Cmd")
                return True
            else:
                logger.info("Close Debug For TCAM Fail! Send 2nd Cmd.")
                resp_buf = self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x02\xDC\x01')
                if resp_buf[-5] == 0x71:
                    logger.info("Close Debug For TCAM Success. 2nd Cmd")
                    return True
                else:
                    logger.error("Close Debug Mode Fail! Close Debug For TCAM Fail!")
                    return False

    def __enter_program_mode(self, mcu_addr):
        logger.info("DoIP MCU:{} Enter Program Mode Start. CMD:10 03 -->>".format(mcu_addr))
        resp_buf = self.send_uds_cmd(mcu_addr, b'\x10\x03')
        if resp_buf[12] == 0x7F:
            logger.error("DoIP MCU:{} Enter Program Mode Fail! RESP: {}".format(mcu_addr, resp_buf.hex(' ')) )
            return False
        
        logger.info("DoIP MCU:{} Enter Program Mode Success. CMD:10 03 -->>".format(mcu_addr))
        return True

    def unlock_27(self, mcu_addr, type27, mcu_pin):
        logger.info("DoIP Unlock MCU:{} type:{} Start -->>".format(mcu_addr,type27))
        
        logger.info("Step 1: Enter Program Mode -->>")
        result = self.__enter_program_mode(mcu_addr)
        if result != True:
            return result

        logger.info("Step 2: Reed Seed 27 {} -->>".format(type27))
        resp_buf = self.send_uds_cmd(mcu_addr, binascii.a2b_hex("27{}".format(type27)))
        if resp_buf[12] == 0x7F:
            logger.error("DoIP Unlock MCU Fail! Reed Seed Data Fail! RESP: {}".format(resp_buf.hex(' ')))
            return False
        
        logger.info("Step 3: Calc Seed_Key -->>")
        seed = resp_buf[-3:]
        seed_key = DoIP_Mgr.__compute_seed_key(seed, binascii.a2b_hex(mcu_pin))
        logger.info("Seed:{} And Seed_Key:{}".format(seed, seed_key))

        logger.info("Step 4: Send Seed_Key 27 1A -->>")
        bseed = binascii.a2b_hex("27{}".format(str(int(type27)+1)))+seed_key
        resp_buf = self.send_uds_cmd(mcu_addr, bseed)
        if resp_buf[12] == 0x7F:
            logger.error("DoIP Unlock MCU Fail! Send Seed_Key Fail! RESP: {}".format(resp_buf.hex(' ')))
            return False
        
        logger.info("DoIP Unlock MCU:{} Success".format(mcu_addr))
        return True

    def __unlock_mcu(self, mcu_addr, mcu_pin):
        logger.info("DoIP Unlock MCU:{} Start -->>".format(mcu_addr))
        
        logger.info("Step 1: Enter Program Mode -->>")
        result = self.__enter_program_mode(mcu_addr)
        if result != True:
            return result

        logger.info("Step 2: Reed Seed 27 19 -->>")
        resp_buf = self.send_uds_cmd(mcu_addr, b'\x27\x19')
        if resp_buf[12] == 0x7F:
            logger.error("DoIP Unlock MCU Fail! Reed Seed Data Fail! RESP: {}".format(resp_buf.hex(' ')))
            return False
        
        logger.info("Step 3: Calc Seed_Key -->>")
        seed = resp_buf[-3:]
        seed_key = DoIP_Mgr.__compute_seed_key(seed, binascii.a2b_hex(mcu_pin))
        logger.info("Seed:{} And Seed_Key:{}".format(seed, seed_key))

        logger.info("Step 4: Send Seed_Key 27 1A -->>")
        resp_buf = self.send_uds_cmd(mcu_addr, b'\x27\x1A' + seed_key)
        if resp_buf[12] == 0x7F:
            logger.error("DoIP Unlock MCU Fail! Send Seed_Key Fail! RESP: {}".format(resp_buf.hex(' ')))
            return False
        
        logger.info("DoIP Unlock MCU:{} Success".format(mcu_addr))
        return True

    def __read_vin(self):
        """
        DoIP读取汽车VIN
        """
        vin_in_dhu = self.send_uds_cmd(DoIP_Mgr.DHU_Addr, b'\x22\xf1\x90')[-17:].decode() #dhu 
        vin_in_tcam = self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x22\xf1\x90')[-17:].decode() #tcam
        if vin_in_dhu != vin_in_tcam:
            logger.error("Read VIN Fail! VIN@DHU:{} Not Match VIN@TCAM:{}".format(vin_in_dhu, vin_in_tcam))
            return ""
        
        logger.info("Read VIN Success. VIN:{}".format(vin_in_dhu))
        return vin_in_dhu
    
    def opendebug(self, debug_mcu = "all"):
        """
        DoIP打开汽车Debug模式, 
        debug_mcu = dhu
        debug_mcu = tcam
        debug_mcu = all
        
        Raise SAT_Exception 
        
        """
        VIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_VIN")

        if VIN == None:
            raise_err( "测试车辆没有绑定VIN!")

        if self.connect() != True:
            raise_err( "connect error!")

        doip_vin = self.__read_vin()
        if doip_vin == None or len(doip_vin) == 0:
            raise_err( "DoIP读取VIN失败!")

        if doip_vin != VIN:
            raise_err( "DoIP读取VIN:{} 和 待测车辆绑定VIN:{} 不匹配".format(doip_vin, VIN))

        result = self.__opendebug(VIN, debug_mcu)
        self.disconnect()
        return 1

    def closedebug(self, debug_mcu = "all"):
        """
        DoIP关闭汽车Debug模式
        debug_mcu = dhu
        debug_mcu = tcam
        debug_mcu = all
        
        Raise SAT_Exception 
        
        """
        VIN = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_VIN")
        if VIN == None:
            raise_err( "测试车辆没有绑定VIN!")

        if self.connect() != True:
            return -1

        doip_vin = self.__read_vin()
        if doip_vin == None or len(doip_vin) == 0:
            raise_err( "DoIP读取VIN失败!")

        if doip_vin != VIN:
            raise_err( "DoIP读取VIN:{} 和 待测车辆绑定VIN:{} 不匹配".format(doip_vin, VIN))
        
        result = self.__closedebug(VIN, debug_mcu)
        self.disconnect()
        return 1
    
    def read_vin(self):
        if self.connect() != True:
            return None
        result = self.__read_vin()
        self.disconnect()
        return result    
    
    def check_mcu_alive(self, targetid):
        if self.connect() != True:
            return False
        
        #TODO 目前只要有doip返回就认为是正常的
        doip_alive = DoIP_Mgr.Instance().send_uds_cmd(targetid, b'\x10\x01')
        #判断结果
        if len(doip_alive) > 0:
            return True
        
        return False    

    # def check_debug_status(self, VIN, DHU_PIN, TCAM_PIN):
    #     """
    #     DoIP测试汽车是否是解锁状态
    #     """

    #     if self.connect() != True:
    #         logger.error("Read VIN Fail! DoIP Not Connect!")
    #         return None
        
    #     dhu_debug = True
    #     # result = self.__enter_program_mode(DoIP_Mgr.DHU_Addr)
    #     result = self.__unlock_mcu(DoIP_Mgr.DHU_Addr, DHU_PIN)
    #     if result != True:
    #         logger.error("DHU Enter Program Mode Fail!")
    #         return None
    #     else:        
    #         self.send_uds_cmd(DoIP_Mgr.DHU_Addr, b'\x22\xC0\x3E')

    #     tcam_debug = True
    #     # result = self.__enter_program_mode(DoIP_Mgr.TCAM_Addr)
    #     result = self.__unlock_mcu(DoIP_Mgr.TCAM_Addr, TCAM_PIN)
    #     if result != True:
    #         logger.error("TCAM Enter Program Mode Fail!")
    #         return None
    #     else:
    #         self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x03\xDC\x10')
    #         self.send_uds_cmd(DoIP_Mgr.TCAM_Addr, b'\x31\x03\x02\x32')

    #     self.disconnect()
    #     # return dhu_debug, tcam_debug

    def check_connect_status(self):
        """
        DoIP汽车连接状态
        """
        if self.__socket != None:
            return True
        else:
            return False

    def __connect_doip_socket(self, ip, port):
        try:
            logger.info("DoIP Connect Start -->> IP:{} Port:{}".format(ip, port))            
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.settimeout(5) 
            self.__socket.connect((ip,port))
            logger.info("DoIP Connect Success. IP:{} Port:{}".format(ip, port))
            
            self.send_wakeup_data()

            self.send_heartbeat_data()
            return True     
        except Exception as e:
            self.disconnect()
            self.__socket = None
            logger.exception("DoIP Connect Fail! IP:{} Port:{}".format(ip, port))

            return False

    def connect(self, ip="169.254.19.1", port=13400, user_confirm = True):
        """
        DoIP尝试连接汽车
        """
        if self.__socket != None:
            return True

        logger.info("DoIP Connect Start -->> IP:{} Port:{}".format(ip, port))
        logger.info("Modify {} IP Start -->>".format(DeviceInfo.doip_eth_name))
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd(
            "sudo ifconfig {0} 169.254.58.58 netmask 255.255.0.0 && sudo ip r add 169.254.0.0/16 dev {0}".format(DeviceInfo.doip_eth_name))
        if result_code < 0:
            raise_err("Modify {} IP Fail! Bash CMD Fail! Continue..".format(DeviceInfo.doip_eth_name))
        logger.info("Modify {} IP Finish".format(DeviceInfo.doip_eth_name))

        connect_result = self.__connect_doip_socket(ip, port)
        if connect_result == True:
            return True
        
        if user_confirm == False:
            raise_err("DoIP Connect Fail! IP:{} Port:{} Unavailable!".format(ip, port))

        Input_Mgr.Instance().confirm("DoIP连接失败!请连接odb线!")
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd(
            "sudo ifconfig {} 169.254.58.58 netmask 255.255.0.0".format(DeviceInfo.doip_eth_name))
        connect_result = self.__connect_doip_socket(ip, port)
        if connect_result == True:
            return True
        else:
            raise_err("DoIP Connect Fail! IP:{} Port:{} Unavailable! After User Confirm!".format(ip, port))

    def disconnect(self):
        """
        DoIP断开汽车连接
        """

        if self.__socket == None:
            return
        
        try:
            self.__socket.close()
            logger.info("DoIP DisConnect Success.")
        except Exception as e:
            logger.exception("DoIP DisConnect Fail!")

        # logger.info("Reset {} IP Start -->>".format(DeviceInfo.doip_eth_name))
        # result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd(
        #     "sudo ifconfig {} 0.0.0.0".format(DeviceInfo.doip_eth_name))
        # if result_code < 0:
        #     logger.error("Reset {} IP Fail! Bash CMD Fail! Continue..".format(DeviceInfo.doip_eth_name))
        # logger.info("Reset {} IP Finish".format(DeviceInfo.doip_eth_name))

        self.__socket = None


_instance = DoIP_Mgr()

