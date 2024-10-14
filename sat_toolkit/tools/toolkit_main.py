import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.monitor_mgr import Pi_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.adb_mgr import ADB_Mgr


from sat_toolkit.models.VehicleInfo_Model import VehicleInfo

from sat_toolkit.models.TestStep_Model import TestStep
from sat_toolkit.models.TestCase_Model import TestCase
from sat_toolkit.models.TestGroup_Model import TestGroup
from sat_toolkit.models.TestStands_Model import TestStands
from sat_toolkit.tools.env_mgr import Env_Mgr

import threading

class _SAT_Audit_Thread(threading.Thread):
    def __init__(self, active_vehicle_profile, active_test_project, audit_desc):
        super().__init__()

        self.__active_vehicle_profile = active_vehicle_profile
        self.__active_test_project = active_test_project
        self.__audit_desc = audit_desc

        logger.info("SAT Audit Thread Inited! Vehicle:{} TestProject:{} Desc:{}".format(active_vehicle_profile, active_test_project, audit_desc))

    def run(self):
        self.run_in_curr_thread()

    def run_in_curr_thread(self):
        logger.info("SAT Audit Thread Start -->>")

        Env_Mgr.Instance().set("SAT_AUDIT_STOP", False)

        Env_Mgr.Instance().set("TEST_PROJECT", self.__active_test_project)
        
        Report_Mgr.Instance().start_audit(self.__audit_desc, self.__active_vehicle_profile, self.__active_test_project)

        logger.info("SAT Env Before Test")
        Env_Mgr.Instance().dump()

        logger.info("Audit Vehicle Profile Before Test")
        self.__active_vehicle_profile.detail()
        
        logger.info("Audit Test Project Info:{}".format(self.__active_test_project))

        logger.info("<<-- Audit Test Project Start -->>")
        test_result, test_result_desc = self.__active_test_project.exec()
        logger.info(">>-- Audit Test Project Finish --<<")

        Env_Mgr.Instance().set("SAT_AUDIT_STOP", False)

        Report_Mgr.Instance().stop_audit(test_result, test_result_desc)
        logger.info("SAT Audit Thread Finish <<--")

    def stop(self):
        logger.info("-->> Rev SAT Audit Thread Stop CMD <<--")  
        Env_Mgr.Instance().set("SAT_AUDIT_STOP", True)


class Toolkit_Main:
    test_level_list = [
        "测试层级",
        "测试标准",
        "测试集合",
        "测试用例",
        "测试步骤",
    ]

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        self.__active_vehicle_profile = None
        self.__active_test_level = None
        self.__active_test_project = None
        self.__in_quick_test = False
        self.__audit_thread = None
        Report_Mgr.Instance().log_init()
        ADB_Mgr.Instance().init_adb_service()

######
    def curr_vehicle_profile(self):
        return self.__active_vehicle_profile

    def list_vehicle_profiles_to_select(self):
        return VehicleInfo.list_enabled()
    
    def select_vehicle_profile(self, vehicle_profile): 
        logger.info("Select Vehicle Profile: {}".format(vehicle_profile))
        vehicle_profile.detail()
        self.__active_vehicle_profile = vehicle_profile
        Env_Mgr.Instance().update_vehicle_env(self.__active_vehicle_profile)

######
    def curr_test_level(self):
        return self.__active_test_level

    def list_test_levels_to_select(self):
        return Toolkit_Main.test_level_list[1:]

    def select_test_level(self, test_level): 
        logger.info("Select Test Level: {} . Reset Test Project".format(test_level))
        self.__active_test_level = test_level
        self.__active_test_project = None

######
    def curr_test_project(self):
        return self.__active_test_project

    def list_test_projects_to_select(self):
        if self.__active_test_level == Toolkit_Main.test_level_list[1]:
            return TestStands.list_enabled()

        elif self.__active_test_level == Toolkit_Main.test_level_list[2]:
            return TestGroup.list_enabled()
                
        elif self.__active_test_level == Toolkit_Main.test_level_list[3]:
            return TestCase.list_enabled()

        elif self.__active_test_level == Toolkit_Main.test_level_list[4]:
            return TestStep.list_enabled()
        else:
            logger.error("active_test_level:{} Invalid! Should Not Enter Here!".format(self.__active_test_level))
            return ["SHOUD NOT ENTER HERE!"]
 
    def select_test_project(self, test_project):
        logger.info("Select Test Project: {}".format(test_project))
        self.__active_test_project = test_project       
       
        test_project.detail()

    def start_audit(self, desc, from_shell=True):
        if self.__active_vehicle_profile == None:
            logger.error("Vehicle Profile Not Set.")
            return -1

        if self.__active_test_project == None:
            logger.error("Test Project Not Set.")
            return -2
            
        if self.__in_quick_test == True:
            logger.error("Quick Audit Test is Running. Wait Quick Test Exit!")
            return -4
        
        if self.__audit_thread != None:
            if self.__audit_thread.is_alive() == True:
                logger.error("Last Audit Thread is Running. Stop Test")
                self.stop_audit()
            else:
                self.__audit_thread = None

        logger.info("Start Audit Thread-->>")  
        self.__audit_thread = _SAT_Audit_Thread(self.__active_vehicle_profile, self.__active_test_project, desc)
        if from_shell:
            Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)
            self.__audit_thread.run_in_curr_thread()
        else:
            Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", False)            
            self.__audit_thread.start()
        return 0

    def stop_audit(self):
        if self.__in_quick_test == True:
            logger.info("Quick Audit Test is Running. Wait Quick Test Exit!")
            return
        
        if self.__audit_thread == None:
            logger.info("No Audit Thread is Running. Need Not Stop.")
            return
        
        logger.info("Stop Audit Thread-->>")  
        if self.__audit_thread.is_alive() == True:
            logger.info("Stop Audit Thread. thread is alive. stop thread ")  
            self.__audit_thread.stop()
            logger.info("Stop Audit Thread. thread is stoped. join thread ")  
            self.__audit_thread.join(5)
            if self.__audit_thread.is_alive() == True:
                logger.error("Join Timeout. Audit Thread Is Alive")  
            else:
                logger.error("Join Finish. Audit Thread Is STOP")  



            logger.info("Stop Audit Thread Finish.")  
        self.__audit_thread = None
    
    def quick_test(self, test_project):
        if self.__active_vehicle_profile == None:
            logger.error("Vehicle Profile Not Set.")
            return -1

        if self.__in_quick_test == False:
            Env_Mgr.Instance().set("SAT_AUDIT_STOP", False)

            Report_Mgr.Instance().start_audit("QUICK_TEST", self.__active_vehicle_profile, "QUICK TEST UNITS")
            self.__in_quick_test = True

        self.select_test_project(test_project)
        Env_Mgr.Instance().set("TEST_PROJECT", self.__active_test_project)
        logger.info("<<-- Quick Test Start -->>")
        test_result, test_result_desc = self.__active_test_project.exec()
        logger.info(">>-- Quick Test Finish --<<")

    def exit_quick_test(self):
        if self.__in_quick_test == True:
            logger.info("Exit Quick Test.")
            Report_Mgr.Instance().stop_audit()
            self.__in_quick_test = False
    
    def check_test_status(self):
        if self.__in_quick_test == True:
            logger.info("Quick Test is Running.")
            return True
        
        if self.__audit_thread != None:
            if self.__audit_thread.is_alive() == True:
                logger.info("Audit Thread is Running.")
                return True
            
        logger.info("NO Test is Running.")
        return False
        

_instance = Toolkit_Main()

