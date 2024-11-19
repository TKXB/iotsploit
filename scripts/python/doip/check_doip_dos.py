import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *

DOS_STATIC_1101 = "1101staticdos"
DOS_STATIC_1002 = "1101staticdos"
#临时硬编码，后面用诊断数据库替代
ecus = [
        {"name":"dhu","doipaddr":0x1201},
        {"name":"tcam","doipaddr":0x1011},
        {"name":"vgm","doipaddr":0x1001},
        {"name":"adcu","doipaddr":0x1301},
        {"name":"cem","doipaddr":0x1A01}
    ]
def make1101dos(doipaddr):
    resp_buf = DoIP_Mgr.Instance().send_uds_cmd(doipaddr,b'\x11\x01')
    #判断resp_buf
    
def make1002dos(doipaddr):
    resp_buf = DoIP_Mgr.Instance().send_uds_cmd(doipaddr,b'\x10\x02')
    #判断resp_buf

def staticdos(type:str):
    DoIP_Mgr.Instance().connect()
    Input_Mgr.Instance().confirm("请确实车辆处于静止状态！")
    Env_Mgr.Instance().set(DOS_STATIC_1101,[])
    Env_Mgr.Instance().set(DOS_STATIC_1002,[])
    doslist = []
    for ecu in ecus:
        doipaddr = ecu['doipaddr']
        if type == "1101":
            if make1101dos(doipaddr):
                doslist.append(ecu)
        elif type == "1002":
            if make1002dos(doipaddr):
                doslist.append(ecu)
    if type == "1101":
        Env_Mgr.Instance().set(DOS_STATIC_1101,doslist)
    elif type == "1002":
        Env_Mgr.Instance().set(DOS_STATIC_1002,doslist)

def dynamicdos(type:str):
    doslist = []
    if type == "1101":
        doslist = Env_Mgr.Instance().get(DOS_STATIC_1101)
    elif type == "1002":
        doslist = Env_Mgr.Instance().get(DOS_STATIC_1002)
    if len(doslist) == 0:
        raise_ok("静止状态没有dos，动态不用测试，通过。")

    DoIP_Mgr.Instance().connect()
    Input_Mgr.Instance().confirm("请确实车速大于15码的状态！")
    
    dynamicdoslist = []
    for ecu in doslist:
        doipaddr = ecu['doipaddr']
        if type == "1101":
            if make1101dos(doipaddr):
                dynamicdoslist.append(ecu)
        elif type == "1002":
            if make1002dos(doipaddr):
                dynamicdoslist.append(ecu)        

    DoIP_Mgr.Instance().disconnect()
    if len(dynamicdoslist) == 0:
        raise_ok("{} DOS攻击测试通过".format(type))
    else:
        raise_err("{} DOS攻击测试不通过. {} ".format(type,dynamicdoslist))    


def main(speedtype:str,dostype:str):
    if speedtype == "static":
        staticdos(dostype)
    elif speedtype == "dynamic":
        dynamicdos(dostype)

        # cmd_content = bytearray.fromhex("1101")
        # resp_buf = DoIP_Mgr.Instance().send_uds_cmd(doipaddr, cmd_content)
        #判断resp_buf
        # hidecmdlist.append({"ecu":ecu,"hidecmd":i})
    
    # DoIP_Mgr.Instance().disconnect()
    # if len(hidecmdlist) == 0:
    #     raise_ok("No Hide 10 CMD")
    # else:
    #     raise_err("存在隐藏10服务.{}".format(hidecmdlist))



if __name__ == '__main__':
    main()