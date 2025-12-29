import logging
logger = logging.getLogger(__name__)


class DeviceInfo:
    #DoIP ETH网卡名称
    doip_eth_name = "enx68da73a73741"
    
    #USB无线网卡模拟出的有线网卡名称
    forward_eth_name = "enxac46b07144f2"

    #内置wifi网卡名称
    wifi_iface_name =  "wlp0s20f3"  

    #USB无线网卡生成的wifi网络名称
    admin_wifi_ssid =  "SAT_ADMIN_34C0"
    admin_wifi_passwd = "1234567890"


    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass



_instance = DeviceInfo()

