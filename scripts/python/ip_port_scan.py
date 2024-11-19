import logging
logger = logging.getLogger(__name__)
import time
import json
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.net_audit_mgr import NetAudit_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.ssh_mgr import SSH_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr
from pwn import *
import xml.etree.ElementTree as ET
scan_iplist_full = [
    "10.0.0.0/8", #扫这个段会很慢
    "198.18.0.0/16",
    "198.99.0.0/16",
    "192.168.0.0/16",
    "169.254.0.0/16",
    ]

scan_iplist_fast = [
    "198.18.34.1",
    "198.18.36.1",
    "198.18.36.2",
    "198.18.36.3",
    "198.18.36.4",
    "198.18.35.2",
    "198.18.35.3",
    "198.18.35.7",
    "198.18.36.177",
    "198.18.35.4",
    "198.18.35.11",
    "198.18.35.12",
    "198.18.35.13",
    "198.18.35.14",
    "198.18.32.18",
    "198.18.32.1",
    "198.18.32.2",
    "198.99.34.1",
    "198.18.34.2",
    "198.18.34.10",
    "198.18.34.11",
    "198.18.34.15",
    "198.18.32.19",
    "198.18.34.3",
    "198.18.34.4",
    "198.18.34.5",
    "198.18.34.14",
    "198.18.37.20",
    "198.18.35.5",
    "198.18.35.161",
    "198.18.35.6",
    "198.18.35.128",
    "198.18.36.96",
    "198.18.35.8",
    "198.18.32.17",
    "198.18.35.9",
    "198.18.35.10",
    "198.18.32.24",
    "198.99.34.15",
    "192.168.1.3",
    "10.1.6.6",
    "10.1.4.6",
    "10.1.2.6",
    "10.1.5.6",
    "10.1.3.6"
    #后续再补充进来，找几个各种车的公网，私网的ip
    ]
tcam_ips = ["198.18.32.17"]
dhu_ips = ["198.18.34.15","198.99.34.15","10.1.6.6","10.1.4.6","10.1.2.6","10.1.5.6","192.168.1.3","10.1.3.6"]
obd_ips = ["169.254.19.1","198.18.32.1"]

fast_ports = "21,22,23,5555,50000,8000,11111,12345,10086,53,1883,13400"

TCAM_AP_SCAN_IP_LIST = "tcam_ap_scan_ip_list"
TCAM_STA_SCAN_IP_LIST = "tcam_sta_forward_ip_list"
DHU_AP_SCAN_IP_LIST = "dhu_ap_scan_ip_list"
OBD_SCAN_IP_LIST = "obd_scan_ip_list"
TCAM_PRIVATEAPN_SCAN_IP_LIST = "tcam_privateapn_scan_ip_list"
DEL_ROUTES_CMDS = "del_routes_cmds"
scan_iplist = []
scan_portlist = ""

def AddRoutes(viaip,dstips):
    #配置路由
    for ip in dstips:
        route_cmds = Env_Mgr.Instance().query(DEL_ROUTES_CMDS,[])
        route_cmds.append("ip route del {} via {}".format(ip,viaip))
        Env_Mgr.Instance().set(DEL_ROUTES_CMDS,route_cmds)
        Bash_Script_Mgr.Instance().exec_cmd("ip route add {} via {}".format(ip,viaip))
def DelRoutes():
    #删除路由
    route_cmds = Env_Mgr.Instance().query(DEL_ROUTES_CMDS,[])
    for cmd in route_cmds:
        Bash_Script_Mgr.Instance().exec_cmd(cmd)
    Env_Mgr.Instance().set(DEL_ROUTES_CMDS,[])
    
def tcam_ap_ip_scan():
    iplist = Env_Mgr.Instance().query(TCAM_AP_SCAN_IP_LIST)
    if iplist == None:
        tcamip = query_tcam_ip()
        if tcamip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "STA":
            #配置路由
            AddRoutes(tcamip,scan_iplist)
            iplist = NetAudit_Mgr.Instance().ip_detect(scan_iplist)
            Env_Mgr.Instance().set(TCAM_STA_SCAN_IP_LIST,iplist)
            #删除路由
            DelRoutes()
            Env_Mgr.Instance().set(TCAM_AP_SCAN_IP_LIST,iplist)
        else:
            raise_err("wifi状态不对.")
    return iplist
def tcam_ap_port_scan(scan_iplist):
    tcamip = query_tcam_ip()
    if tcamip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "STA":
        AddRoutes(tcamip,scan_iplist)
        portresult =  NetAudit_Mgr.Instance().port_detect(scan_iplist,scan_portlist)
        DelRoutes()
        return portresult
    else:
        raise_err("wifi状态不对.")
def dhu_ap_ip_scan():
    iplist = Env_Mgr.Instance().query(DHU_AP_SCAN_IP_LIST)
    if iplist == None:
        dhuip = query_dhu_ip()
        if dhuip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "STA":
            AddRoutes(dhuip,scan_iplist)
            iplist = NetAudit_Mgr.Instance().ip_detect(scan_iplist)
            Env_Mgr.Instance().set(DHU_AP_SCAN_IP_LIST,iplist)
            DelRoutes()
        else:
            raise_err("wifi状态不对.")
    return iplist
def dhu_ap_port_scan(scan_iplist):
    dhuip = query_dhu_ip()
    if dhuip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "STA":
        AddRoutes(dhuip,scan_iplist)
        portresult = NetAudit_Mgr.Instance().port_detect(scan_iplist,scan_portlist)
        DelRoutes()
        return portresult
    else:
        raise_err("wifi状态不对.")
def tcam_sta_ip_scan():
    iplist = Env_Mgr.Instance().query(TCAM_STA_SCAN_IP_LIST)
    if iplist == None:
        tcamip = query_tcam_ip()
        if tcamip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "AP":
            AddRoutes(tcamip,scan_iplist)
            iplist = NetAudit_Mgr.Instance().ip_detect(scan_iplist)
            Env_Mgr.Instance().set(TCAM_STA_SCAN_IP_LIST,iplist)
            DelRoutes()
        else:
            raise_err("wifi状态不对.")
    return iplist
def tcam_sta_port_scan(scan_iplist):
    tcamip = query_tcam_ip()
    if tcamip and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "AP":
        #配置路由
        AddRoutes(tcamip,scan_iplist)
        time.sleep(5)
        portlist = NetAudit_Mgr.Instance().port_detect(scan_iplist,scan_portlist)
        if len(portlist) == 0:
            portlist = NetAudit_Mgr.Instance().port_detect(scan_iplist,scan_portlist)
        DelRoutes()
        return portlist
    else:
        raise_err("wifi状态不对.")

def obd_ip_scan():
    iplist = Env_Mgr.Instance().query(OBD_SCAN_IP_LIST)
    if iplist == None:
        DoIP_Mgr.Instance().connect()
        #配置路由
        obdip = "169.254.19.1"
        AddRoutes(obdip,scan_iplist)
        iplist = NetAudit_Mgr.Instance().ip_detect(scan_iplist)
        Env_Mgr.Instance().set(OBD_SCAN_IP_LIST,iplist)
        DelRoutes()
        DoIP_Mgr.Instance().disconnect()
    return iplist
def obd_port_scan(scan_iplist):
    DoIP_Mgr.Instance().connect()
    #配置路由
    obdip = "169.254.19.1"
    AddRoutes(obdip,scan_iplist)
    portlist = NetAudit_Mgr.Instance().port_detect(scan_iplist,scan_portlist)
    DelRoutes()
    DoIP_Mgr.Instance().disconnect()
    return portlist

def tcam_ap_forward_ip_scan(isPortCall=False):
    iplist = tcam_ap_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉tcam ap的地址
        if isPortCall:
            return iplist
        raise_err( "tcam ap下内网IP暴露:{}".format(iplist))
    else:
        raise_ok("tcam ap下内网没有暴露IP")

def tcam_sta_forward_ip_scan(isPortCall=False):
    iplist = tcam_sta_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉tcam sta的地址
        if isPortCall:
            return iplist
        raise_err( "tcam sta下内网IP暴露:{}".format(iplist))
    else:
        raise_ok("tcam sta下内网没有暴露IP")
    
def tcam_ap_input_ip_scan(isPortCall=False):
    iplist = tcam_ap_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉非tcam的地址
        iplist = list(set(iplist) & set(tcam_ips))
        if isPortCall:
            #需要加上wifi的ip
            iplist.append(query_tcam_ip())
            return iplist
        raise_err("tcam ap下自身其他IP暴露:{}".format(iplist))
    else:
        if isPortCall:
            iplist = []
            iplist.append(query_tcam_ip())
            return iplist
        raise_ok("tcam ap下自身没有暴露其他IP")
    
def tcam_sta_input_ip_scan(isPortCall=False):
    iplist = tcam_sta_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉非tcam的地址
        iplist = list(set(iplist) & set(tcam_ips))
        if isPortCall:
            #需要加上wifi的ip
            iplist.append(query_tcam_ip())
            return iplist
        raise_err( "tcam sta下自身其他IP暴露:{}".format(iplist))
    else:
        if isPortCall:
            iplist = []
            iplist.append(query_tcam_ip())
            return iplist
        raise_ok("tcam sta下自身没有暴露其他IP")

def dhu_ap_forward_ip_scan(isPortCall=False):
    iplist = dhu_ap_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉dhu ap的地址
        if isPortCall:
            return iplist
        raise_err( "dhu ap下内网IP暴露:{}".format(iplist))
    else:
        raise_ok("dhu ap下内网没有暴露IP")

def dhu_ap_input_ip_scan(isPortCall=False):
    iplist = dhu_ap_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉非dhu的地址
        iplist = list(set(iplist) & set(dhu_ips))
        if isPortCall:
            #需要加上wifi的ip
            iplist.append(query_dhu_ip())
            return iplist
        raise_err( "dhu ap下自身其他IP暴露:{}".format(iplist))
    else:
        if isPortCall:
            iplist = []
            iplist.append(query_dhu_ip())
            return iplist
        raise_ok("dhu ap下自身没有暴露其他IP")

def tcam_ap_publicapn_ip_scan(isPortCall=False):
    iplist = tcam_ap_ip_scan()
    if len(iplist) > 0:
        #判断一下，选择出public apn的ip
        apniplist = []
        for ip in iplist:
            if ip.startswith("10."):
                apniplist.append(ip)
        iplist = apniplist
        if isPortCall:
            return iplist
        raise_err( "tcam的public apn没有做隔离:{}".format(iplist))
    else:
        raise_ok("tcam的public apn做了隔离")

def obd_forward_ip_scan(isPortCall=False):
    iplist = obd_ip_scan()
    if len(iplist) > 0:
        #判断一下，排除掉vgm的ip
        if isPortCall:
            return iplist
        raise_err( "obd内网IP暴露:{}".format(iplist))
    else: 
        raise_ok("obd没有暴露内网IP")

def obd_input_ip_scan(isPortCall=False):
    iplist = obd_ip_scan()
    logger.info("dasfdadfasfasdfa:{}".format(iplist))
    if len(iplist) > 0:
        #判断一下，排除掉非vgm的ip
        iplist = list(set(iplist) & set(obd_ips))
        if isPortCall:
            #需要加上obd的ip
            iplist.append("169.254.19.1")
            return iplist
        raise_err( "obd自身其他IP暴露:{}".format(iplist))
    else:
        if isPortCall:
            iplist = ["169.254.19.1"]
            return iplist
        raise_ok("obd没有暴露自身其他IP")

def tcam_ap_forward_port_scan():
    iplist = tcam_ap_forward_ip_scan(True)
    portlist = tcam_ap_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("tcam ap下内网暴露端口{}".format(portlist))
    else:
        raise_ok("tcam ap下内网没有暴露端口")

def tcam_sta_forward_port_scan():
    iplist = tcam_sta_forward_ip_scan(True)
    portlist = tcam_sta_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("tcam sta下内网暴露端口{}".format(portlist))
    else:
        raise_ok("tcam sta下内网没有暴露端口")

def tcam_ap_input_port_scan():
    iplist = tcam_ap_input_ip_scan(True)
    portlist = tcam_ap_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("tcam ap下自身暴露端口{}".format(portlist))
    else:
        raise_ok("tcam ap下自身没有暴露端口")

def tcam_sta_input_port_scan():
    iplist = tcam_sta_input_ip_scan(True)
    portlist = tcam_sta_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("tcam sta下自身暴露端口{}".format(portlist))
    else:
        raise_ok("tcam sta下自身没有暴露端口")

def dhu_ap_forward_port_scan():
    iplist = dhu_ap_forward_ip_scan(True)
    portlist = dhu_ap_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("dhu ap下内网暴露端口{}".format(portlist))
    else:
        raise_ok("dhu ap下内网没有暴露端口")

def dhu_ap_input_port_scan():
    iplist = dhu_ap_input_ip_scan(True)
    portlist = dhu_ap_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("dhu ap下自身暴露端口{}".format(portlist))
    else:
        raise_ok("dhu ap下自身没有暴露端口")

def obd_forward_port_scan():
    iplist = obd_forward_ip_scan(True)
    portlist = obd_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("obd下内网暴露端口{}".format(portlist))
    else:
        raise_ok("obd下内网没有暴露端口")

def obd_input_port_scan():
    iplist = obd_input_ip_scan(True)
    portlist = obd_port_scan(iplist)
    if len(portlist) > 0:
        #判断portlist
        logger.info(portlist)
        raise_err("obd下自身暴露端口{}".format(portlist))
    else:
        raise_ok("obd下自身没有暴露端口")

def tcam_privateapn_ip_scan():
    if WiFi_Mgr.Instance().status()['WIFI_MODE'] != "STA":
        raise_err("wifi状态不对")
    tcamip = query_tcam_ip()
    if tcamip == "192.168.225.1":
        pass
        #东软的tcam
        # sshctx = SSH_Mgr.Instance().open_tcam_ssh()
        # SSH_Mgr.Instance().ssh_cmd(sshctx,"ip rule delete from fwmark") #这个不行，mark号不同
        # SSH_Mgr.Instance().ssh_cmd(sshctx,"iptables -F && iptables -t nat -I POSTROUTING -s 192.168.225.0/24 -j MASQUERADE")
        # SSH_Mgr.Instance().ssh_cmd(sshctx,"ip route del default")
        # SSH_Mgr.Instance().ssh_cmd(sshctx,"ip route add default dev rmnet_data1")
    elif tcamip == "192.168.15.1":
        #高新兴和联乘的tcam
        pass
    else:
        raise_err("wifi ip不对")
    iplist = Env_Mgr.Instance().query(TCAM_PRIVATEAPN_SCAN_IP_LIST)
    if iplist == None:
        iplist = NetAudit_Mgr.Instance().ip_detect(["10.0.0.0/8"])
        Env_Mgr.Instance().set(TCAM_PRIVATEAPN_SCAN_IP_LIST,iplist)
    return iplist


def tcam_privateapn_ip_car_scan(isPortCall):
    iplist = tcam_privateapn_ip_scan()
    if len(iplist) > 0:
        #判断一下,是否有car
        if isPortCall:
            return iplist
        raise_err( "私网apn暴露车辆:{}".format(iplist))
    else:
        raise_ok("私网apn没有暴露车辆")    

def tcam_privateapn_ip_tsp_scan(isPortCall):
    iplist = tcam_privateapn_ip_scan()
    if len(iplist) > 0:
        #判断一下,是否有car
        if isPortCall:
            return iplist
        raise_err("私网apn暴露tsp内部服务:{}".format(iplist))
    else:
        raise_ok("私网apn没有暴露tsp内部服务")    
    

def dhu_ss_port_scan():
    baseDir = "/home/sat/zeekr_sat_main/scripts/"
    ADB_Mgr.Instance().push_file(ADB_Mgr.DHU_ADB_SERIAL,baseDir+"ss_static","/data/local/tmp/")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"chmod +x /data/local/tmp/ss_static")
    result = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"/data/local/tmp/ss_static -npltu")
    #解析result
    raise_ok("ss扫描结束,结果如下:\n{}".format(result))

def tcam_ss_port_scan():
    tcamip = query_tcam_ip()
    Bash_Script_Mgr.Instance().exec_cmd('sshpass -p "{}" scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no /home/sat/zeekr_sat_main/scripts/ss_static root@{}:/tmp/'.format(Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD"),tcamip))
    sshctx = open_tcam_ssh()
    sshctx.sendline("/tmp/ss_static -npltu;exit;")
    data = sshctx.recvall().decode()
    sshctx.close()
    raise_ok("tcam ss扫描结束,结果如下:\n{}".format(data))


def nmap_ip_detect(nmapdata):
        # """
        # Starting Nmap 7.91 ( https://nmap.org ) at 2021-10-01 14:15 PDT
        # Nmap scan report for 192.168.1.1
        # Host is up (0.0027s latency).
        # MAC Address: 11:22:33:44:55:66 (Some manufacturer)
        # Nmap done: 1 IP address (1 host up) scanned in 0.09 seconds
        # """
    logger.info(nmapdata)
    ip_list = []
    for line in nmapdata.splitlines():
        if line.startswith("Nmap scan report for "):
            ip_dict = {}
            ip_dict["ip"] = line.replace("Nmap scan report for ", "")
            # ip_list.append(ip_dict)
            ip_list.append(ip_dict["ip"])
        if line.startswith("Host is "):
            ip_dict["status"] = line.replace("Host is ", "").split(" ")[0]
    return ip_list

def nmap_port_detect(nmapdatafile):
    tree = ET.parse(nmapdatafile)
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
    return results

def dhu_internal_ip_scan():
    baseDir = "/home/sat/zeekr_sat_main/scripts/"
    ADB_Mgr.Instance().push_file(ADB_Mgr.DHU_ADB_SERIAL,baseDir+"nmap_dhu.tar","/data/local/tmp/")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"tar -xvf /data/local/tmp/nmap_dhu.tar")
    scaniplist = list(set(scan_iplist) ^ set(dhu_ips))
    result = ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"/data/local/tmp/nmap/bin/nmap -sn {}".format(' '.join(scaniplist)))
    iplist = nmap_ip_detect(result)
    return iplist

def dhu_internal_port_scan():
    iplist = dhu_internal_ip_scan()
    if len(iplist) > 0:
        ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"/data/local/tmp/nmap/bin/nmap -vv -sT -T2 -p {} {} -oX {}".format(scan_portlist, ' '.join(iplist), "/data/local/tmp/nmap/nmapresult"))
        ADB_Mgr.Instance().pull_file(ADB_Mgr.DHU_ADB_SERIAL,"/data/local/tmp/nmap/nmapresult","/tmp/nmapresult")
        portlist = nmap_port_detect("/tmp/nmapresult")
        if len(portlist) > 0:
            raise_err("通过dhu可以访问到内网端口：{}".format(portlist))
        else:
            raise_ok("通过dhu无法访问到内网端口。")
    else:
        raise_err("dhu无法扫描到其他ip")
    #检查result

def tcam_internal_ip_scan():
    tcamip = query_tcam_ip()
    Bash_Script_Mgr.Instance().exec_cmd('sshpass -p "{}" scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no /home/sat/zeekr_sat_main/scripts/nmap_tcam.tar root@{}:/tmp/'.format(Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD"),tcamip))
    # context.log_level='debug'
    io = open_tcam_ssh()
    scaniplist = list(set(scan_iplist) ^ set(tcam_ips))
    cmd = "cd /tmp/;/tmp/nmap/run-nmap.sh -sn {}".format(' '.join(scaniplist))
    io.sendline("cd /tmp/;tar -xvf /tmp/nmap_tcam.tar")
    io.sendline(cmd)
    io.recvuntil("Starting Nmap")
    nmapdata = io.recvuntil("Nmap done").decode()
    logger.info(cmd)
    logger.info(nmapdata)
    io.close()
    iplist = nmap_ip_detect(nmapdata)
    return iplist

def tcam_internal_port_scan():
    iplist = tcam_internal_ip_scan()
    if len(iplist) > 0:
        tcamip = query_tcam_ip()
        sshctx = open_tcam_ssh()
        sshctx.sendline("/tmp/nmap/run-nmap.sh -vv -sT -T2 -p {} {} -oX {}".format(scan_portlist, ' '.join(iplist), "/tmp/nmapresult"))
        sshctx.recvuntil("Nmap done")
        Bash_Script_Mgr.Instance().exec_cmd('sshpass -p "{}" scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@{}:/tmp/nmapresult /tmp/nmapresult'.format(Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD"),tcamip))
        portlist = nmap_port_detect("/tmp/nmapresult")
        if len(portlist) > 0:
            raise_err("通过tcam可以访问到内网端口：{}".format(portlist))
        else:
            raise_ok("通过tcam无法访问到内网端口。")
    else:
        raise_err("tcam无法扫描到其他ip")

def main(scantype:str,scanmode:str):
    global scan_iplist
    global scan_portlist
    if scanmode == "fast":
        scan_iplist = scan_iplist_fast
        scan_portlist = fast_ports
    elif scanmode == "full":
        scan_iplist = scan_iplist_full
        scan_portlist = "1-65535"
    if scantype == "ip_tcamapforward":
        tcam_ap_forward_ip_scan()
    elif scantype == "ip_tcamstaforward":
        tcam_sta_forward_ip_scan()
    elif scantype == "ip_tcamapinput":
        tcam_ap_input_ip_scan()
    elif scantype == "ip_tcamstainput":
        tcam_sta_input_ip_scan()
    elif scantype == "ip_tcamap_publicapn":
        if scanmode == "fast":
            raise_err("此用例不支持快速模式")
        tcam_ap_publicapn_ip_scan()
    elif scantype == "ip_dhuapforward":
        dhu_ap_forward_ip_scan()
    elif scantype == "ip_dhuapinput":
        dhu_ap_input_ip_scan()
    elif scantype == "ip_obdforward":
        obd_forward_ip_scan()
    elif scantype == "ip_obdinput":
        obd_input_ip_scan()
    elif scantype == "port_tcamapforward":
        tcam_ap_forward_port_scan()
    elif scantype == "port_tcamstaforward":
        tcam_sta_forward_port_scan()
    elif scantype == "port_tcamapinput":
        tcam_ap_input_port_scan()
    elif scantype == "port_tcamstainput":
        tcam_sta_input_port_scan()
    elif scantype == "port_dhuapforward":
        dhu_ap_forward_port_scan()
    elif scantype == "port_dhuapinput":
        dhu_ap_input_port_scan()
    elif scantype == "port_obdforward":
        obd_forward_port_scan()
    elif scantype == "port_obdinput":
        obd_input_port_scan()
    elif scantype == "ip_tcam_privateapn_car":
        if scanmode == "fast":
            raise_err("此用例不支持快速模式")
        tcam_privateapn_ip_car_scan()
    elif scantype == "ip_tcam_privateapn_tsp":
        if scanmode == "fast":
            raise_err("此用例不支持快速模式")
        tcam_privateapn_ip_tsp_scan()
    elif scantype == "port_dhu_ss":
        dhu_ss_port_scan()
    elif scantype == "port_tcam_ss":
        tcam_ss_port_scan()
    elif scantype == "port_dhu_internal_scan":
        dhu_internal_port_scan()
    elif scantype == "port_tcam_internal_scan":
        tcam_internal_port_scan()
    # internal_ip_dict = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_INTERNAL_IP_DICT")
    # if internal_ip_dict == None:
    #     raise_err("车型未设置内网IP序列! VehicleModel_INTERNAL_IP_DICT NOT SET")
    # internal_ip_dict = json.loads(internal_ip_dict)
    # logger.info("Internal IP Dict:{} IP Alive Detect Start -->>".format(internal_ip_dict))
    # Env_Mgr.Instance().set("")
    # if active_ip_list == None:
    #     raise_err( "内网活跃IP检测失败! IP List:{}".format((internal_ip_dict.keys())))
    # logger.info("Internal IP Alive Detect Result:{}".format(internal_ip_dict))
    # if len(active_ip_list) > 0:
    #     raise_err( "内网IP暴露:{}".format(active_ip_list))
    # else:
    #     raise_ok("内网没有暴露IP")
    # #active_ip_list需要保存在环境变量，方便后续扫端口使用
    # if invisible_check == "check" and len(active_ip_list) != 0:
    #     raise_err( "内网IP暴露:{}".format(active_ip_list))
    # else:
    #     raise_ok( "内网IP活跃状态:{}".format(active_ip_list))
if __name__ == '__main__':
    main()