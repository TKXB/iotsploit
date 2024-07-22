import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *

def main(type27:str):
#TODO
# 2.在车辆静止的状态下遍历发送10 XX服务
# 3.记录所有除了10 01、10 02、10 03之外的响应子服务
    DoIP_Mgr.Instance().connect()
    #临时硬编码，后面用诊断数据库替代
    ecus = [
            {"name":"dhu","doipaddr":0x1201},
            {"name":"tcam","doipaddr":0x1011},
            {"name":"vgm","doipaddr":0x1001},
            {"name":"adcu","doipaddr":0x1301},
            {"name":"cem","doipaddr":0x1A01}
        ]
    static27list = []
    for ecu in ecus:
        doipaddr = ecu['doipaddr']
        isUnLock = DoIP_Mgr.Instance().unlock_27(doipaddr,type27,"FFFFFFFFFF")
        if isUnLock == False:
            isUnLock = DoIP_Mgr.Instance().unlock_27(doipaddr,type27,"5555555555")
        if isUnLock:
            static27list.append({"ecu":ecu})
    DoIP_Mgr.Instance().disconnect()
    if len(static27list) == 0:
        raise_ok("No static 27 {} PINCODE".format(type27))
    else:
        raise_err("ECUs: {} 存在固定27 {} Pincode.".format(static27list,type27))

if __name__ == '__main__':
    main()