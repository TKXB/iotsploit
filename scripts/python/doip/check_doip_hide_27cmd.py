import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *

def main():
#TODO
#1.在车辆静止的状态下遍历发送27 XX服务
    DoIP_Mgr.Instance().connect()
    #临时硬编码，后面用诊断数据库替代
    ecus = [
            {"name":"dhu","doipaddr":0x1201},
            {"name":"tcam","doipaddr":0x1011},
            {"name":"vgm","doipaddr":0x1001},
            {"name":"adcu","doipaddr":0x1301},
            {"name":"cem","doipaddr":0x1A01}
        ]
    hidecmdlist = []
    for ecu in ecus:
        doipaddr = ecu['doipaddr']
        noresp_count = 0
        for i in range(0x7f):
            if i == 1 or i == 19 or i == 11 or i == 5 or i == 3:
                continue
            cmd_content = bytearray.fromhex("27{:02X}".format(i))
            resp_buf = DoIP_Mgr.Instance().send_uds_cmd(doipaddr, cmd_content)
            #判断resp_buf
            logger.info(resp_buf)
            if len(resp_buf) == 0:
                hidecmdlist.append({"ecu":ecu,"hidecmd":i,"reason":"noresp","resp":resp_buf})
                noresp_count += 1
                if noresp_count == 10:
                    break
                continue
            if resp_buf[12] != b'\x7f':
                hidecmdlist.append({"ecu":ecu,"hidecmd":i,"reason":"noerr","resp":resp_buf})
        DoIP_Mgr.Instance().resetvgm()
    DoIP_Mgr.Instance().disconnect()
    if len(hidecmdlist) == 0:
        raise_ok("No Hide 27 CMD")
    else:
        raise_err("存在隐藏27服务.{}".format(hidecmdlist))

if __name__ == '__main__':
    main()