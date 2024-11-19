from logging import critical
import re
from tkinter import MITER

if __name__ == '__main__':
    with open("./tcpprocess.log", "r+") as f:
        data = f.read()
        data = data.replace("\x00", " ")
        f.seek(0)
        f.write(data)
        f.truncate()
        f.flush()
    
    f_process = open("./tcpprocess.log", "r") 
    f_dns = open("./dnslog.txt","r")
    f_mitm = open("./mitmlog.txt","r")
    f_result = open("./mitm_result.txt","w")
    f_result_noprocess = open("./mitm_result_noprocess.txt","w")
    
    mitmlist = []
    mitm_re = re.compile("[.*].*<=>(.+) .*\) (.*)")
    for line in f_mitm.readlines():
        matchs = mitm_re.findall(line)
        # print(matchs)
        if len(matchs) > 0:
            matchs2 = re.findall("(.*):(.*) .*",matchs[0][0])
            # print(matchs2)
            if len(matchs2) > 0:
                mitmobj = {"dstip":matchs2[0][0],"dstport":matchs2[0][1],"comm":matchs[0][1]}
                if mitmobj not in mitmlist:
                    mitmlist.append(mitmobj)
    
    dnslist = []
    dns_re = re.compile("ip:(.*),.*domain:(.*)")
    for line in f_dns.readlines():
        matchs = dns_re.findall(line)
        if len(matchs) > 0:
            if matchs[0][0] != "<nil>":
                dnsobj = {"ip":matchs[0][0],"domain":matchs[0][1]}
                if dnsobj not in dnslist:
                    dnslist.append(dnsobj)
    
    
    processlist = []
    process_re = re.compile("Process:(.*),dstip:(.*):(.*)")
    for line in f_process.readlines():
        matchs = process_re.findall(line)
        if len(matchs) > 0:
            processobj = {"process":matchs[0][0],"ip":matchs[0][1],"port":matchs[0][2]}
            if processobj not in processlist:
                processlist.append(processobj)
    
    resultlist = []
    for mitmobj in mitmlist:
        dstip = mitmobj["dstip"]
        dstport = mitmobj["dstport"]
        mitmcomm = mitmobj["comm"]
        dstdomain = ""
        dstprocess = ""
        for dnsobj in dnslist:
            ip = dnsobj["ip"]
            if dstip == ip:
                dstdomain = dnsobj["domain"]
                break
        for processobj in processlist:
            ip = processobj["ip"]
            port = processobj["port"]
            if dstip == ip and dstport == port:
                dstprocess = processobj["process"]
                break
        resultobj = {
            "ip":dstip,
            "port":dstport,
            "domain":dstdomain,
            "process":dstprocess,
            "comm":mitmcomm
        }
        if resultobj not in resultlist:
            resultlist.append(resultobj)
    
    
    for resultobj in resultlist:
        resultstr = "Process:{} , Domain:{} , Port:{} , Ip:{} , Comm:{}\n"
        resultstr = resultstr.format(resultobj['process'],resultobj['domain'],resultobj['port'],resultobj['ip'],resultobj['comm'])
        if resultobj['process'] != '':
            f_result.write(resultstr)
            f_result.flush()
        else:
            f_result_noprocess.write(resultstr)
            f_result_noprocess.flush()
    
    f_process.close() 
    f_dns.close()
    f_mitm.close()
    f_result.close()
    f_result_noprocess.close()
    
    
    