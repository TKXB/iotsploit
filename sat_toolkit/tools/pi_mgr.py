import logging
logger = logging.getLogger(__name__)

import platform
import socket
from sat_toolkit.tools.third_party.INA219 import INA219

from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.device_info import DeviceInfo
import netifaces

class Pi_Mgr:
    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass


    def pi_info(self):
        return \
        {
            "admin_wifi": self.__admin_wifi(),
            "cpu_temp": self.__cpu_temperature(),
            "battery":  self.__battery_status(),
            "uname":    self.__uname(),
            "hostname": self.__hostname()
        }
        
    def __get_admin_ip(self):
        try:
            admin_ip = netifaces.ifaddresses(DeviceInfo.forward_eth_name)[netifaces.AF_INET][0]['addr']
            logger.info("WIFI Forward Eth IP:{}".format(admin_ip))
            return admin_ip

        except Exception as err:
            logger.exception("Get Forward Eth IP Fail!")
        return "unknown"        
    
    def __admin_wifi(self):
        logger.info("Curr SAT Admin WIFI:")
        wifi_status = \
        { 
            "SSID": DeviceInfo.admin_wifi_ssid,
            "PASSWD": DeviceInfo.admin_wifi_passwd,
            "ADMIN_IP": self.__get_admin_ip(),
        }

        logger.info(wifi_status)
        return wifi_status    

    def __cpu_temperature(self):
        logger.info("Curr CPU Temperature:")
        format_temp_str = "正常"
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as temp_file:
            temp = temp_file.read().strip()
            format_temp_str = "{:.1f}°C".format(float(temp) / 1000)

        logger.info(format_temp_str)
        return format_temp_str    

    def __battery_status(self):
        logger.info("Curr Battery Status:")
        try:
            ina219 = INA219(addr=0x41)
            bus_voltage = ina219.getBusVoltage_V()             # voltage on V- (load side)
            shunt_voltage = ina219.getShuntVoltage_mV() / 1000 # voltage between V+ and V- across the shunt
            current = ina219.getCurrent_mA()                   # current in mA
            power = ina219.getPower_W()                        # power in W
            p = (bus_voltage - 9)/3.6*100
            if(p > 100):p = 100
            if(p < 0):p = 0

            battery_charging = True
            if current < 0:
                battery_charging = False

            battery_status = \
            {
                "Charging": battery_charging,
                "Percent":  "{:3.1f}%".format(p),
                "Power"  :  "{:6.3f} W".format(power),
                "Current":  "{:9.6f} A".format(current/1000),
                "Load Voltage" : "{:6.3f} V".format(bus_voltage),
                "Shunt Voltage": "{:9.6f} V".format(shunt_voltage),
                "PSU Voltage": "{:6.3f} V".format(bus_voltage + shunt_voltage)
            }            

        except Exception as err:
            logger.exception("Read Battery Status Fail! Hardware Not Support!")
            battery_status = \
            {
                "Charging": True,
                "Percent":  "100%",
            }

        logger.info(battery_status)
        return battery_status


    def __uname(self):
        name = platform.uname()
        # logger.info("PI Uname:{}".format(name))
        return name
    
    def __hostname(self):
        host_name = socket.gethostname()
        # logger.info("PI HostName:{}".format(host_name))
        return host_name

_instance = Pi_Mgr()

