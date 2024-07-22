import logging
logger = logging.getLogger(__name__)

import requests
import re

from sat_toolkit.models.ClassifiedInfo_Model import VehiclePIN

class DebugMode_Mgr:

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass


    def query_pin_code_from_db(self, VIN):
        """
        访问本地数据库获取PIN Code

        Return:
        None:获取失败
        (TCAM_PIN, DHU_PIN)
        """
        
        logger.info("Query Vehicle PIN Code From DB Start. VIN:{} -->>".format(VIN))
        try:
            vehicle_pins = VehiclePIN.objects.get(VIN=VIN)
        except Exception as e:
            logger.exception("Query PIN For Vin:{} Fail!".format(VIN))
            return None

        logger.info("Query PIN For Vin:{} Success. TCAM_PIN:{} DHU_PIN:{}".format(VIN, vehicle_pins.TCAM_PIN, vehicle_pins.DHU_PIN))           
        return (vehicle_pins.TCAM_PIN, vehicle_pins.DHU_PIN)     
 
    def query_pin_code_from_web(self, VIN):
        """
        连接内网获取PIN Code

        Return:
        None:获取失败
        (TCAM_PIN, DHU_PIN)
        """

        logger.info("Query Vehicle PIN Code From WEB Start. VIN:{} -->>".format(VIN))

        try:
            url = "http://10.66.252.90/qbay/Base/VinViewer/VinSummary.asp?VIN={}&BuildStatusID=1".format(VIN)
            resp = requests.get(url, timeout=3)

            cookie = resp.cookies['ASPSESSIONIDQCQSADST']
            url = "http://10.66.252.90/qbay/base/vinviewer/VinVCC.asp"
            resp = requests.get(url, cookies={"ASPSESSIONIDQCQSADST":cookie}, timeout=3)
        
        except Exception as e:
            logger.exception("Query PIN For Vin:{} Fail! Network Unavailable! {}".format(VIN, e))
            return None
        
        resp_content = resp.content.decode().replace("<BR/>","")
        TCA019_relist = re.findall("TCA019(\w+),", resp_content)
        if len(TCA019_relist) == 0:
            logger.error("Query TCAM PIN For Vin:{} Fail! Prefix Pattern Not Found!".format(VIN))
            return None

        DHU019_relist = re.findall("DHU019(\w+),", resp_content)
        if len(DHU019_relist) == 0:
            logger.error("Query DHU PIN For Vin:{} Fail! Prefix Pattern Not Found!".format(VIN))
            return None
        
        TCAM_PIN = TCA019_relist[0]
        DHU_PIN = DHU019_relist[0]

        logger.info("Query PIN For Vin:{} Success. TCAM_PIN:{} DHU_PIN:{}".format(VIN, TCAM_PIN, DHU_PIN))   
        return (TCAM_PIN, DHU_PIN)     


_instance = DebugMode_Mgr()
