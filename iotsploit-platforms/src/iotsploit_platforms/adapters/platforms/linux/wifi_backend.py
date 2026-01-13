"""
Linux WiFi Backend Implementation.

This module provides Linux-specific WiFi backend implementation using pywifi,
hostapd, and dnsmasq.
"""

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

import netifaces
import pywifi

from iotsploit_core.ports.wifi_backend import WifiBackend
from iotsploit_core.utils.exceptions import NotSupportedError

logger = logging.getLogger(__name__)


class LinuxWifiBackend(WifiBackend):
    """
    Linux WiFi backend implementation.
    
    Uses pywifi for station mode and hostapd/dnsmasq for access point mode.
    """

    _hostapd_config_template = '''
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

    def __init__(self, wifi_iface_name: str = "wlan0", forward_eth_name: Optional[str] = None):
        """
        Initialize Linux WiFi backend.
        
        Args:
            wifi_iface_name: WiFi interface name (e.g., "wlan0", "wlp0s20f3")
            forward_eth_name: Ethernet interface name for forwarding (optional)
        """
        self.wifi_iface_name = wifi_iface_name
        self.forward_eth_name = forward_eth_name
        
        self._wifi_mode = "IDLE"
        self._wifi_proxy_inited = False
        self._sta_conn_wifi_ssid = ""
        self._sta_conn_wifi_passwd = ""
        self._ap_ssid = ""
        self._ap_passwd = ""
        self._ap_wpa_mode = 2
        
        # Setup temp directory
        self._temp_dir = Path(tempfile.gettempdir()) / "iotsploit_tmp"
        os.makedirs(self._temp_dir, exist_ok=True)
        self._ap_hostapd_config_path = str(self._temp_dir / "hostapd.config")
        self._dhclient_pid_path = str(self._temp_dir / f"dhclient.{wifi_iface_name}.pid")
        self._dns_backup_file_path = str(self._temp_dir / "dns_resolv_conf_bak")
        
        # Initialize WiFi proxy
        self._init_wifi_proxy()

    def _exec_shell(self, cmd: str) -> str:
        """Execute shell command and return output."""
        logger.info(f"exec shell cmd: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8"
        )
        logger.info(f"result: {result.stdout}")
        return result.stdout

    def _rebuild_sta_proxy(self) -> Optional[Any]:
        """Rebuild STA proxy for the configured WiFi interface."""
        sta_proxy = None
        try:
            wifi_sta_proxy = pywifi.PyWiFi()
            sta_ifaces = wifi_sta_proxy.interfaces()
            for sta_iface in sta_ifaces:
                if sta_iface.name() == self.wifi_iface_name:
                    sta_proxy = sta_iface
                    break
        except Exception as err:
            logger.error(f"WIFI STA Proxy Rebuild Fail! {err}")
            return None
        
        return sta_proxy

    def _init_wifi_proxy(self):
        """Initialize WiFi proxy (lazy initialization)."""
        if self._wifi_proxy_inited:
            return
        
        self._wifi_proxy_inited = True
        logger.info("WiFi STA Proxy Init Start.")
        logger.info("WiFi STA Proxy Init Finish.")
        
        logger.info("WiFi AP Proxy Init Start.")
        logger.info("WiFi AP Proxy Init Finish.")

        # Reset to IDLE state
        self._wifi_mode = "AP"
        self.ap_stop()
        self._wifi_mode = "STA"
        self.sta_disconnect()
        self._wifi_mode = "IDLE"

    def scan(self) -> List[Dict[str, Any]]:
        """
        Scan for available WiFi networks.
        
        Returns:
            List of dictionaries containing WiFi network information.
        """
        self._init_wifi_proxy()
        
        logger.info("Start Scan WIFI.")
        self.ap_stop()
        self.sta_disconnect()
        
        sta_proxy = self._rebuild_sta_proxy()
        if sta_proxy is None:
            logger.error("Build STA Proxy Fail! Scan WIFI Fail!")
            self.sta_disconnect()
            raise NotSupportedError("Failed to initialize WiFi interface for scanning")
        
        sta_proxy.scan()
        time.sleep(2)
        
        logger.info("Read Scan Result.")
        bss_list = sta_proxy.scan_results()
        
        result_list = []
        for bss in bss_list:
            result_list.append({
                "ssid": bss.ssid,
                "bssid": bss.bssid,
                "signal": bss.signal,
                "security": self._get_security_type(bss),
            })
            logger.info(f"Find WIFI: {bss.ssid} {bss.bssid}")
        
        logger.info(f"result_list: {result_list}")
        return result_list

    def _get_security_type(self, bss: Any) -> str:
        """Get security type string from BSS object."""
        # pywifi doesn't always expose security info directly
        # This is a simplified version - can be enhanced
        if hasattr(bss, 'akm') and bss.akm:
            if pywifi.const.AKM_TYPE_WPA2PSK in bss.akm:
                return "WPA2"
            elif pywifi.const.AKM_TYPE_WPAPSK in bss.akm:
                return "WPA"
        return "OPEN"

    def sta_connect(self, ssid: str, passwd: str) -> None:
        """
        Connect to a WiFi network in station (STA) mode.
        
        Args:
            ssid: Network SSID to connect to
            passwd: Network password (empty string for open networks)
        """
        self._init_wifi_proxy()

        if (self._wifi_mode == "STA" and
            self._sta_conn_wifi_ssid == str(ssid) and
            self._sta_conn_wifi_passwd == str(passwd)):
            status = self.status()
            sta_status = status.get("sta_status", {})
            sat_ip = sta_status.get("ip_address")
            if sat_ip is not None:
                logger.info(f"WiFi_Mgr Connect WIFI:[ {self._sta_conn_wifi_ssid} {self._sta_conn_wifi_passwd} ]. "
                          f"Same With Current Connect. IP:{sat_ip}. Skip")
                return
            else:
                logger.info(f"WiFi_Mgr Connect WIFI:[ {self._sta_conn_wifi_ssid} {self._sta_conn_wifi_passwd} ]. "
                          f"Same With Current Connect. Not Get IP. Force Reconnect")

        self.ap_stop()
        self.sta_disconnect()

        self._sta_conn_wifi_ssid = str(ssid)
        self._sta_conn_wifi_passwd = str(passwd)
        logger.info(f"++ WiFi_Mgr Connect WIFI:[ {self._sta_conn_wifi_ssid} {self._sta_conn_wifi_passwd} ] Start. ++")
        self._wifi_mode = "STA"

        logger.info("1st. Start wpa_supplicant && Build STA Proxy.")
        sta_proxy = self._rebuild_sta_proxy()
        if sta_proxy is None:
            logger.error("Build STA Proxy Fail! STA Connect WIFI Fail!")
            self.sta_disconnect()
            raise NotSupportedError("Failed to initialize WiFi interface for connection")
        
        logger.info("2nd. Make Network Profile And Connect.")
        sta_proxy.remove_all_network_profiles()

        profile = pywifi.Profile()
        profile.ssid = self._sta_conn_wifi_ssid
        profile.auth = pywifi.const.AUTH_ALG_OPEN
        if self._sta_conn_wifi_passwd != "":
            profile.akm.append(pywifi.const.AKM_TYPE_WPA2PSK)
            profile.cipher = pywifi.const.CIPHER_TYPE_CCMP
            profile.key = self._sta_conn_wifi_passwd

        sta_proxy.add_network_profile(profile)
        sta_proxy.connect(profile)
        time.sleep(2)
        self._exec_shell(f"sudo dhclient -nw -pf {self._dhclient_pid_path} {self.wifi_iface_name}")
        time.sleep(2)

        logger.info(f"++ WiFi_Mgr Connect WIFI:[ {self._sta_conn_wifi_ssid} {self._sta_conn_wifi_passwd} ] Finish. ++")
        self.status()

    def sta_disconnect(self) -> None:
        """
        Disconnect from the current WiFi network in station mode.
        """
        self._init_wifi_proxy()

        logger.info("-- WiFi_Mgr Force Stop STA Connection Start. --")
        if self._wifi_mode != "STA":
            logger.info(f"WIFI_MODE:{self._wifi_mode} NOT STA. SKIP")
            return

        self._exec_shell(f"sudo dhclient -x -pf {self._dhclient_pid_path} {self.wifi_iface_name}")
        time.sleep(1)

        self._exec_shell("sudo killall dhclient")

        sta_proxy = self._rebuild_sta_proxy()
        if sta_proxy is not None:
            logger.info("Disconnect Existing STA Connection.")
            sta_proxy.disconnect()
            sta_proxy.remove_all_network_profiles()
            time.sleep(1)

        logger.info("-- WiFi_Mgr Force Stop STA Connection Finish. --")
        if self._wifi_mode == "STA":
            self._wifi_mode = "IDLE"

    def ap_start(self, ssid: Optional[str] = None, passwd: Optional[str] = None, wpa_mode: int = 2) -> Tuple[str, str]:
        """
        Start WiFi access point (AP) mode.
        
        Args:
            ssid: AP SSID (if None, a default will be generated)
            passwd: AP password (if None, a default will be used)
            wpa_mode: WPA mode (1=WPA only, 2=WPA2 only, 3=both)
        
        Returns:
            Tuple of (ssid, passwd) that were actually used
        """
        self._init_wifi_proxy()
        
        if ssid is not None:
            conect_ap_ssid = ssid
        else:
            mac_addr = netifaces.ifaddresses(self.wifi_iface_name)[netifaces.AF_LINK][0]['addr'].upper()
            conect_ap_ssid = "SAT_" + mac_addr[-5:-3] + mac_addr[-2:]
        
        if passwd is not None:
            conect_ap_passwd = passwd
        else:
            conect_ap_passwd = "12345678"

        self.sta_disconnect()
        self.ap_stop()

        logger.info("++ WiFi_Mgr Start SoftAP Start. ++")
        self._wifi_mode = "AP"
        
        logger.info("1st. Disable systemd-resolved Service")
        self._exec_shell("sudo service systemd-resolved stop")

        logger.info("2nd. Start hostapd && dnsmasq")
        self._ap_ssid = conect_ap_ssid
        self._ap_passwd = conect_ap_passwd
        self._ap_wpa_mode = wpa_mode
        
        with open(self._ap_hostapd_config_path, "w") as hostapd_config_file:
            hostapd_config_file.write(
                self._hostapd_config_template.format(
                    self._ap_ssid, self._ap_passwd, self.wifi_iface_name, wpa_mode
                )
            )
        logger.info(f"AP Info: [ {self._ap_ssid} : {self._ap_passwd} WPA_Mode:{wpa_mode} ]")

        self._exec_shell(f"sudo hostapd -B {self._ap_hostapd_config_path}")
        time.sleep(0.5)
        self._exec_shell(f"sudo ifconfig {self.wifi_iface_name} 192.168.100.1 netmask 255.255.255.0 up")
        self._exec_shell(f"sudo dnsmasq --interface={self.wifi_iface_name} --dhcp-range=192.168.100.100,192.168.100.200,255.255.255.0,24h")
        time.sleep(0.5)

        if self.forward_eth_name:
            logger.info("3rd. Enable Forward Rules")
            self._exec_shell(f"sudo iptables -t nat -A POSTROUTING -o {self.forward_eth_name} -j MASQUERADE")
            self._exec_shell("sudo sysctl -w net.ipv4.ip_forward=1")
            time.sleep(1)

        logger.info("++ AP Start SoftAP Finish. ++")
        return self._ap_ssid, self._ap_passwd

    def ap_stop(self) -> None:
        """
        Stop WiFi access point (AP) mode.
        """
        self._init_wifi_proxy()

        logger.info("-- WiFi_Mgr Force Stop SoftAP Start. --")
        if self._wifi_mode != "AP":
            logger.info(f"WIFI_MODE:{self._wifi_mode} NOT AP. SKIP")
            return

        logger.info("1st. Kill hostapd && dnsmasq")
        self._exec_shell("sudo killall hostapd")
        time.sleep(0.5)
        self._exec_shell("sudo killall dnsmasq")

        self._exec_shell(f"sudo ifconfig {self.wifi_iface_name} 0.0.0.0 up")
        self._exec_shell("sudo rm -rf /var/lib/misc/dnsmasq.leases")
        time.sleep(0.5)

        logger.info("2nd. Disable Forward Rules")
        self._exec_shell("sudo iptables -t nat -F")
        self._exec_shell("sudo sysctl -w net.ipv4.ip_forward=0")
        time.sleep(1)

        logger.info("3rd. Enable systemd-resolved Service")
        self._exec_shell("sudo service systemd-resolved start")

        logger.info("-- WiFi_Mgr Force Stop SoftAP Finish. --")
        if self._wifi_mode == "AP":
            self._wifi_mode = "IDLE"

    def status(self) -> Dict[str, Any]:
        """
        Get current WiFi status.
        
        Returns:
            Dictionary containing current WiFi status information.
        """
        self._init_wifi_proxy()

        status_dict = {"wifi_mode": self._wifi_mode}

        if self._wifi_mode == "STA":
            sta_status = {}
            wpa_status = self._exec_shell(f"wpa_cli -i {self.wifi_iface_name} status")
            for single_status in wpa_status.splitlines():
                kev_value = single_status.split("=", 1)
                if len(kev_value) != 2:
                    logger.error(f"Read WPA_STATUS Fail! Status Invalid:{single_status}")
                    continue
                sta_status[kev_value[0]] = kev_value[1]

            status_dict["sta_status"] = sta_status
            status_dict["sta_conn_wifi_ssid"] = self._sta_conn_wifi_ssid
            status_dict["sta_conn_wifi_passwd"] = self._sta_conn_wifi_passwd

        if self._wifi_mode == "AP":
            client_list = []
            client_list_str = self._exec_shell("cat /var/lib/misc/dnsmasq.leases")
            for single_client in client_list_str.splitlines():
                # Format: 1698410310 22:4b:9d:a7:ec:7f 192.168.45.96 KKG-AN70 01:22:4b:9d:a7:ec:7f
                client_info_list = single_client.split(" ")
                if len(client_info_list) != 5:
                    logger.error(f"Read Client List Fail! Status Invalid:{single_client}")
                    continue
                client_list.append({
                    "mac": client_info_list[1],
                    "ip": client_info_list[2],
                    "name": client_info_list[3]
                })

            status_dict["client_list"] = client_list
            status_dict["ap_ssid"] = self._ap_ssid
            status_dict["ap_passwd"] = self._ap_passwd

        logger.info(f"STATUS:{status_dict}")
        return status_dict


# Export the backend class
wifi_backend = LinuxWifiBackend
