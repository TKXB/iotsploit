import logging
import datetime
import re
logger = logging.getLogger(__name__)
import base64
import os
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.net_audit_mgr import NetAudit_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.adb_mgr import *

def StopMITM():
    Bash_Script_Mgr.Instance().exec_cmd("pkill -9 -f dnssniffer")
    Bash_Script_Mgr.Instance().exec_cmd("pkill -9 -f nogotofail")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"pkill -9 -f tcpprocess")

def doMITM_DHU():
    StopMITM()
    basedir = "/home/sat/zeekr_sat_main/scripts/mitm/"
    #
    ADB_Mgr.Instance().push_file(ADB_Mgr.DHU_ADB_SERIAL,basedir+"tcpprocess","/data/local/tmp/tcpprocess")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"chmod +x /data/local/tmp/tcpprocess")
    ADB_Mgr.Instance().shell_cmd(ADB_Mgr.DHU_ADB_SERIAL,"cd /data/local/tmp/;nohup /data/local/tmp/tcpprocess &>/dev/null &")
    #
    Bash_Script_Mgr.Instance().exec_cmd("cd {};nohup sh {}start_dnssniffer.sh &>/dev/null &".format(basedir,basedir))
    Bash_Script_Mgr.Instance().exec_cmd("cd {};nohup sh {}start_nogotofail.sh &>/dev/null &".format(basedir,basedir))
    #
    Input_Mgr.Instance().confirm("请进行各类网络功能的操作，操作完成后确认。")
    StopMITM()
    #
    resultdir = basedir+"mitm_{}_{}_{}_{}_{}_{}_{}/".format("DC1E",datetime.datetime.now().year,datetime.datetime.now().month,datetime.datetime.now().day,datetime.datetime.now().hour,datetime.datetime.now().minute,datetime.datetime.now().second)
    Bash_Script_Mgr.Instance().exec_cmd("mkdir {}".format(resultdir))
    #
    ADB_Mgr.Instance().pull_file(ADB_Mgr.DHU_ADB_SERIAL,"/data/local/tmp/tcpprocess.log",resultdir+"tcpprocess.log")
    Bash_Script_Mgr.Instance().exec_cmd("mv {}mitmlog.txt {}".format(basedir,resultdir))
    Bash_Script_Mgr.Instance().exec_cmd("mv {}dnslog.txt {}".format(basedir,resultdir))
    Bash_Script_Mgr.Instance().exec_cmd("cp {}mitm_result.py {}".format(basedir,resultdir))
    #
    Bash_Script_Mgr.Instance().exec_cmd("python3 {}mitm_result.py".format(resultdir))
    #
    results = ""
    with open(resultdir+"mitm_result.txt","r") as resultfile:
        results = resultfile.readlines()
    '''
    Process:com.tencent.wecarflow,Domain:ins-5776sx9h.ias.tencent-cloud.net,Port:8081,Ip:58.19.160.100,Comm:MITMSuccess!NotTLS!
    Process:com.zeekr.speech.daemon,Domain:jhjl75qs28jwye3ouc2zvtonjvcfdgkd.yundunwaf2.com,Port:443,Ip:121.199.83.216,Comm:MITMSuccess!Certfile:/tmp/._cert_ca.pem_-3259428682631496663.pem
    Process:com.zeekr.speech.daemon,Domain:jhjl75qs28jwye3ouc2zvtonjvcfdgkd.yundunwaf2.com,Port:443,Ip:121.199.83.216,Comm:HTTPrequestPOSTzkl-dlp.zeekrlife.com/approve/notice

    '''
    mitmre = re.compile("Process:(.*),Domain:(.*),Port:(.*),Ip:(.*),Comm:(.*)")
    mitmlist = []
    for line in results:
        line = line.replace(" ","")
        mitmregroup = mitmre.findall(line)
        mitmobj = {
            "line":line,"Process":"","Domain":"","Port":"","IP":"","Comm":"",
            "mitmtype":""
            }
        #待处理
    return mitmlist

def main(checktype:str,ecu:str):
    if checktype == "stop":
        StopMITM()
        raise_ok("stop ok")
    if query_tcam_ip() and WiFi_Mgr.Instance().status()['WIFI_MODE'] == "AP":
        mitmlist = Env_Mgr.Instance().query("mitmlist")
        if mitmlist == None:
            mitmlist = doMITM_DHU()
            Env_Mgr.Instance().set(mitmlist)
        for mitmitem in mitmlist:
            if checktype == "http":
                pass
            elif checktype == "https":
                pass
            elif checktype == "tls":
                pass
            elif checktype == "tcp":
                pass
    else:
        raise_err("tcam没有连接AP")
if __name__ == '__main__':
    main()