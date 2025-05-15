import logging
logger = logging.getLogger(__name__)

import netifaces

import pywifi

import os
import subprocess
import tempfile
from pathlib import Path

from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *
import time

from sat_toolkit.tools.device_info import DeviceInfo

class WiFi_Mgr:
    __hostapd_config_template = '''
#sets the wifi interface to use, is wlan0 in most cases
interface={2}

driver=nl80211
ssid={0}
hw_mode=g
channel=6
macaddr_acl=0
auth_algs=1

#1 - wpa only
#2 - wpa2 only
#3 - both
wpa={3}
wpa_passphrase={1}
wpa_key_mgmt=WPA-PSK


#sets encryption used by WPA
wpa_pairwise=TKIP
#sets encryption used by WPA2
rsn_pairwise=CCMP
'''
    
    __temp_dir = Path(tempfile.gettempdir()) / "sat_toolkit_tmp"
    __ap_hostapd_config_path = str(__temp_dir / "hostapd.config")
    __dhclient_pid_path = str(__temp_dir / "dhclient.wlan0.pid")
    __dns_backup_file_path = str(__temp_dir / "dns_resolv_conf_bak")

    @staticmethod
    def Instance():
        return _instance

    @staticmethod
    def __exec_shell(cmd):
        logger.info("exec shell cmd:{}".format(cmd))
        result = subprocess.run(cmd, 
                                shell=True, 
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        logger.info("result:{}".format(result.stdout))
        return result.stdout

    @staticmethod
    def __rebuild_sta_proxy():
        sta_proxy = None
        try:
            wifi_sta_proxy = pywifi.PyWiFi()
            sta_ifaces = wifi_sta_proxy.interfaces()
            for sta_iface in sta_ifaces:
                if sta_iface.name() == DeviceInfo.wifi_iface_name:
                    sta_proxy = sta_iface
                    break
        except Exception as err:
            logger.error("WIFI STA Proxy Rebuild Fail!")
            return None
        
        return sta_proxy

    def __init__(self):
        self.__wifi_mode = "IDLE"
        self.__wifi_proxy_inited = False
        # Ensure temp directory exists
        os.makedirs(WiFi_Mgr.__temp_dir, exist_ok=True)

    def __init_wifi_proxy(self):
        if self.__wifi_proxy_inited == True:
            return 
        self.__wifi_proxy_inited = True
        
        logger.info("WiFi STA Proxy Init Start.")
        self.__sta_conn_wifi_ssid = ""
        self.__sta_conn_wifi_passwd = ""
        # Directory is already created in __init__
        # self.__exec_shell("sudo cp -rf /etc/resolv.conf {0}; cat {0}".format(WiFi_Mgr.__dns_backup_file_path))

        logger.info("WiFi STA Proxy Init Finish.")
        
        logger.info("WiFi AP Proxy Init Start.")
        # Directory is already created in __init__
        self.__ap_ssid = "" 
        self.__ap_passwd = ""
        self.__ap_wpa_mode = 2
        logger.info("WiFi AP Proxy Init Finish.")

        self.__wifi_mode = "AP"
        self.ap_stop()
        self.__wifi_mode = "STA"
        self.sta_disconnect()
        self.__wifi_mode = "IDLE"


    def sta_connect_wifi(self, SSID, Passwd):
        """
        连接指定的WIFI

        """
        self.__init_wifi_proxy()

        if self.__wifi_mode == "STA" and \
           self.__sta_conn_wifi_ssid == str(SSID) and \
            self.__sta_conn_wifi_passwd == str(Passwd):
                sat_ip = self.status().get("sta_status",[]).get("ip_address")
                if sat_ip != None:
                    logger.info("++ WiFi_Mgr Connect WIFI:[ {} {} ]. Same With Current Connect. IP:{}. Skip".format(self.__sta_conn_wifi_ssid, self.__sta_conn_wifi_passwd, sat_ip))
                    return
                else:
                    logger.info("++ WiFi_Mgr Connect WIFI:[ {} {} ]. Same With Current Connect. Not Get IP. Force Reconnect ".format(self.__sta_conn_wifi_ssid, self.__sta_conn_wifi_passwd))                

        self.ap_stop()
        self.sta_disconnect()

        self.__sta_conn_wifi_ssid = str(SSID)
        self.__sta_conn_wifi_passwd = str(Passwd)
        logger.info("++ WiFi_Mgr Connect WIFI:[ {} {} ] Start. ++".format(self.__sta_conn_wifi_ssid, self.__sta_conn_wifi_passwd))
        self.__wifi_mode = "STA"

        logger.info("1st. Start wpa_supplicant && Build STA Proxy.")
        sta_proxy = WiFi_Mgr.__rebuild_sta_proxy()
        if sta_proxy == None:
            logger.error("Build STA Proxy Fail! STA Connect WIFI Fail!")
            self.sta_disconnect()
            return
        
        logger.info("2nd. Make Network Profile And Connect.")
        sta_proxy.remove_all_network_profiles()

        profile = pywifi.Profile()
        profile.ssid = self.__sta_conn_wifi_ssid
        profile.auth = pywifi.const.AUTH_ALG_OPEN
        if self.__sta_conn_wifi_passwd != "":
            profile.akm.append(pywifi.const.AKM_TYPE_WPA2PSK)
            profile.cipher = pywifi.const.CIPHER_TYPE_CCMP
            profile.key = self.__sta_conn_wifi_passwd

        sta_proxy.add_network_profile(profile)
        sta_proxy.connect(profile)
        time.sleep(2)
        self.__exec_shell("sudo dhclient -nw -pf {} {}".format(WiFi_Mgr.__dhclient_pid_path, DeviceInfo.wifi_iface_name))
        time.sleep(2)

        logger.info("++ WiFi_Mgr Connect WIFI:[ {} {} ] Finish. ++".format(self.__sta_conn_wifi_ssid, self.__sta_conn_wifi_passwd))
        self.status()

    def sta_disconnect(self):
        """
        解除连接WIFI

        """
        self.__init_wifi_proxy()

        logger.info("-- WiFi_Mgr Force Stop STA Connection Start. --")
        if self.__wifi_mode != "STA":
            logger.info("WIFI_MODE:{} NOT STA. SKIP".format(self.__wifi_mode))
            return        

        self.__exec_shell("sudo dhclient -x -pf {} {}".format(WiFi_Mgr.__dhclient_pid_path, DeviceInfo.wifi_iface_name))
        time.sleep(1)
        # self.__exec_shell("sudo cp -rf {0} /etc/resolv.conf; cat /etc/resolv.conf".format(WiFi_Mgr.__dns_backup_file_path))

        self.__exec_shell("sudo killall dhclient")

        sta_proxy = self.__rebuild_sta_proxy()
        if sta_proxy != None:
            logger.info("Disconnect Existing STA Connection.")
            sta_proxy.disconnect()
            sta_proxy.remove_all_network_profiles()
            time.sleep(1)

        logger.info("-- WiFi_Mgr Force Stop STA Connection Finish. --")
        if self.__wifi_mode == "STA":
            self.__wifi_mode = "IDLE"

    def ap_start(self, ssid=None, passwd=None, wpa_mode=2):
        """
        打开热点，支持自定义ssid和passwd

        """
        self.__init_wifi_proxy()        
        
        if ssid != None:
            conect_ap_ssid = ssid
        else:
            mac_addr = netifaces.ifaddresses(DeviceInfo.wifi_iface_name)[netifaces.AF_LINK][0]['addr'].upper()
            conect_ap_ssid = "SAT_" + mac_addr[-5:-3] + mac_addr[-2:]
        
        if passwd != None:
            conect_ap_passwd = passwd
        else:
            conect_ap_passwd = "12345678"

        # if self.__wifi_mode == "AP" and \
        #    self.__ap_ssid == conect_ap_ssid and \
        #     self.__ap_passwd == conect_ap_passwd and \
        #     self.__ap_wpa_mode == wpa_mode:
        #     logger.info("WiFI Start SoftAP [ {} : {} WPA_Mode:{} ] Same With Current AP. Skip".format(self.__ap_ssid, self.__ap_passwd, wpa_mode))
        #     return self.__ap_ssid, self.__ap_passwd

        self.sta_disconnect()
        self.ap_stop()

        logger.info("++ WiFi_Mgr Start SoftAP Start. ++")
        self.__wifi_mode = "AP"
        
        logger.info("1st. Disable systemd-resolved Service")
        self.__exec_shell("sudo service systemd-resolved stop")

        logger.info("2nd. Start hostapd && dnsmasq")
        self.__ap_ssid = conect_ap_ssid
        self.__ap_passwd = conect_ap_passwd
        self.__ap_wpa_mode = wpa_mode  
    
        with open(WiFi_Mgr.__ap_hostapd_config_path, "w") as hostapd_config_file:
            hostapd_config_file.write(WiFi_Mgr.__hostapd_config_template.format(self.__ap_ssid, self.__ap_passwd, DeviceInfo.wifi_iface_name, wpa_mode))
        logger.info("AP Info: [ {} : {} WPA_Mode:{} ]".format(self.__ap_ssid, self.__ap_passwd, wpa_mode))

        self.__exec_shell("sudo hostapd -B {}".format(WiFi_Mgr.__ap_hostapd_config_path))
        time.sleep(0.5)
        self.__exec_shell("sudo ifconfig {} 192.168.100.1 netmask 255.255.255.0 up".format(DeviceInfo.wifi_iface_name))
        self.__exec_shell("sudo dnsmasq --interface={} --dhcp-range=192.168.100.100,192.168.100.200,255.255.255.0,24h".format(DeviceInfo.wifi_iface_name))
        time.sleep(0.5)

        logger.info("3rd. Enable Forward Rules")
        self.__exec_shell("sudo iptables -t nat -A POSTROUTING -o {} -j MASQUERADE".format(DeviceInfo.forward_eth_name))
        self.__exec_shell("sudo sysctl -w net.ipv4.ip_forward=1")
        time.sleep(1)

        logger.info("++ AP Start SoftAP Finish. ++")
        return self.__ap_ssid, self.__ap_passwd

    def ap_stop(self):
        """
        关闭热点

        """
        self.__init_wifi_proxy()               

        logger.info("-- WiFi_Mgr Force Stop SoftAP Start. --")
        if self.__wifi_mode != "AP":
            logger.info("WIFI_MODE:{} NOT AP. SKIP".format(self.__wifi_mode))
            return

        logger.info("1st. Kill hostapd && dnsmasq")
        self.__exec_shell("sudo killall hostapd")
        time.sleep(0.5)
        self.__exec_shell("sudo killall dnsmasq")

        self.__exec_shell("sudo ifconfig {} 0.0.0.0 up".format(DeviceInfo.wifi_iface_name))        
        self.__exec_shell("sudo rm -rf /var/lib/misc/dnsmasq.leases")
        time.sleep(0.5)

        logger.info("2nd. Disable Forward Rules")
        self.__exec_shell("sudo iptables -t nat -F")
        self.__exec_shell("sudo sysctl -w net.ipv4.ip_forward=0")
        time.sleep(1)

        logger.info("3rd. Enable systemd-resolved Service")
        self.__exec_shell("sudo service systemd-resolved start")

        logger.info("-- WiFi_Mgr Force Stop SoftAP Finish. --")
        if self.__wifi_mode == "AP":
            self.__wifi_mode = "IDLE"

    def status(self):
        """
        查看当前无线网卡状态

        """
        self.__init_wifi_proxy()   

        status_dict = {"WIFI_MODE":self.__wifi_mode}

            

        if self.__wifi_mode == "STA":
            sta_status = {}
            wpa_status = self.__exec_shell("wpa_cli -i {} status".format(DeviceInfo.wifi_iface_name))
            for single_status in wpa_status.splitlines():
                kev_value = single_status.split("=", 1)
                if len(kev_value) != 2:
                    logger.error("Read WPA_STATUS Fail! Status Invalid:{}".format(single_status))
                    continue
                sta_status[ kev_value[0] ] = kev_value[1]

            status_dict["sta_status"] = sta_status
            status_dict["sta_conn_wifi_ssid"] = self.__sta_conn_wifi_ssid 
            status_dict["sta_conn_wifi_passwd"] = self.__sta_conn_wifi_passwd             
        
        if self.__wifi_mode == "AP":
            client_list = []
            client_list_str = self.__exec_shell("cat /var/lib/misc/dnsmasq.leases")
            for single_client in client_list_str.splitlines():
            # 1698410310 22:4b:9d:a7:ec:7f 192.168.45.96 KKG-AN70 01:22:4b:9d:a7:ec:7fsud    
                client_info_list = single_client.split(" ")
                if len(client_info_list) != 5:
                    logger.error("Read Client List Fail! Status Invalid:{}".format(single_client))
                    continue
                client_list.append(
                        {
                        "mac":  client_info_list[1],
                        "ip":   client_info_list[2],
                        "name": client_info_list[3]
                    }
                )

            status_dict["client_list"] = client_list
            status_dict["ap_ssid"] = self.__ap_ssid
            status_dict["ap_passwd"] = self.__ap_passwd

        logger.info("STATUS:{}".format(status_dict))
        return status_dict

    def query_wifi_info_by_bssid(self, bssid:str):
        """
        查询wifi信息BY bssid
        Return:
        None:扫描失败
        list: WIFI列表

        """
        self.__init_wifi_proxy()           

        logger.info("QUERY WIFI INFO BY Match BSSID:{} Start -->>".format(bssid))
        self.ap_stop()
        self.sta_disconnect()
        logger.info("1st. Start Scan WIFI.")
        sta_proxy = WiFi_Mgr.__rebuild_sta_proxy()
        if sta_proxy == None:
            logger.error("Build STA Proxy Fail! STA Connect WIFI Fail!")
            self.sta_disconnect()
            return None
        
        sta_proxy.scan()
        time.sleep(2)
        
        logger.info("2nd. Read Scan Result.")
        bss_list = sta_proxy.scan_results()

        result_list = []
        bssid = bssid.lower()
        for bss in bss_list:
            if bss.bssid.lower() == bssid:
                result_list.append(bss)
                logger.info("Find Match WIFI:{}".format(bss.ssid))

        logger.info("result_list:{}".format(result_list))
        return result_list

    def query_wifi_info_by_ssid(self, ssid:str):
        """
        查询wifi信息BY ssid
        Return:
        None:扫描失败
        list: WIFI列表

        """
        self.__init_wifi_proxy()           

        logger.info("QUERY WIFI INFO BY Match SSID:{} Start -->>".format(ssid))
        self.ap_stop()
        self.sta_disconnect()
        logger.info("1st. Start Scan WIFI.")
        sta_proxy = WiFi_Mgr.__rebuild_sta_proxy()
        if sta_proxy == None:
            logger.error("Build STA Proxy Fail! STA Connect WIFI Fail!")
            self.sta_disconnect()
            return None
        
        sta_proxy.scan()
        time.sleep(2)
        
        logger.info("2nd. Read Scan Result.")
        bss_list = sta_proxy.scan_results()

        result_list = []
        for bss in bss_list:
            #ssid为空时不进行筛选,全部都拿走
            #ssid不为空时,对ssid进行匹配
            if ssid == None or bss.ssid == ssid:
                result_list.append(bss)
                logger.info("Find Match WIFI:{} {}".format(bss.ssid, bss.bssid))

        logger.info("result_list:{}".format(result_list))
        return result_list


_instance = WiFi_Mgr()