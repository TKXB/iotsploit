# addx 20231117-14:14
# Teststep: 直接扫描XXX端口
import logging
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.net_audit_mgr import net_scan
logger = logging.getLogger(__name__)

def main():
    logger.info("Please input the ip you need to scan:")
    # get the ip need to be port scan
    scanip = Input_Mgr.string_input()
    logger.info("now to scan dhu port ...")
    # startting to scan....
    ports = net_scan().Instance().port_detect(scanip,"1-65535")
    # test data, delete it after test
    ports = [22, 23, 5555]
    
    logger.info("Open ports : ", ports)
    # 扫描结果为空，返回1通过，并提示无开放端口
    if ports is None:
        return 1,"No opening ports!"
    # 存在扫描结果，返回-1，不通过，返回端口数据
    else:
        logger.info("存在开放端口:",''.join(str(ports)))
        return -1,ports

if __name__ == '__main__':
    main()