import logging
logger = logging.getLogger(__name__)

import datetime
import os

import shutil

from sat_toolkit.tools.env_mgr import Env_Mgr

import mistune
from sat_toolkit.tools.sat_utils import *

# import markdown

class Report_Mgr:
    __test_ok_label =      """<span style="color:green;font-weight:bold;">通过</span>"""
    __test_no_label =      """<span style="color:red;font-weight:bold;">不通过</span>"""
    __test_fail_label =    """<span style="color:red;font-weight:bold;">失败</span>"""    
    __test_finish_label =  """<span style="color:blue;font-weight:bold;">完成</span>"""

    __log_root_dir = "sat_logs"
    __detail_log_formatter =  logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    __raw_log_formatter =     logging.Formatter("%(message)s")
    __console_log_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")


    @staticmethod
    def Instance():
        return _instance
    
    def __init__(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        Report_Mgr.__log_root_dir = root_dir + "/sat_logs"
        self.__currlog_dir = "{}/{}".format(Report_Mgr.__log_root_dir, "QUICK_TEST")
        # shutil.rmtree(self.__currlog_dir, ignore_errors=True)

        Env_Mgr.Instance().set(Env_Mgr.ENV_PreFix + "LOG_DIR", self.__currlog_dir)
        
        self.__root_log_file_handler = None
        self.__root_log_console_handler = None

        self.__teststep_log_file_handler = None
        self.__teststep_log_file_path = None

        self.__root_log_console_handler = logging.StreamHandler()
        self.__root_log_console_handler.setFormatter(Report_Mgr.__console_log_formatter)
        logging.getLogger().addHandler(self.__root_log_console_handler)
        logging.getLogger().setLevel("DEBUG")


        self.__report_toc_file = None
        self.__report_detail_file = None
        self.__report_toc_tree_list = None
        self.__report_detail_tree_list = None

        self.__report_test_result = None
        self.__report_test_result_desc = None
        self.__report_test_result_tree_list = None
                
    def log_init(self):
        pass

    def reset_audit_result(self):
        self.__report_test_result = None
        self.__report_test_result_desc = None
        self.__report_test_result_tree_list = None
        try:
            os.unlink(Report_Mgr.__log_root_dir + "/Audit_Report.html")
        except Exception as err:
            pass
        
    def audit_status(self):
        if self.__report_test_result != None:
            return "Audit Finish", self.__report_test_result_tree_list, self.__report_test_result
        
        if self.__report_test_result_tree_list != None:
            return "Audit In Process", self.__report_test_result_tree_list
        else:
            return "No Audit", None

    def start_audit(self, audit_desc, vehicle_profile, test_project):
        self.stop_audit()
        Report_Mgr.Instance().reset_audit_result()

        Env_Mgr.Instance().unset("AUDIT_STOP_TIME")  
        curr_time = datetime.datetime.now()
        Env_Mgr.Instance().set("AUDIT_START_TIME", curr_time)

        self.__currlog_dir = "{}/{}__{}".format(Report_Mgr.__log_root_dir, curr_time.strftime("%Y%m%d_%H%M%S"), audit_desc.replace(" ","_"))
        os.makedirs(self.__currlog_dir, exist_ok=True)
        Env_Mgr.Instance().set(Env_Mgr.ENV_PreFix + "LOG_DIR", self.__currlog_dir)

        self.__root_log_file_handler = logging.FileHandler(self.__currlog_dir +"/sat_audit.log", "w", encoding="utf-8")
        self.__root_log_file_handler.setFormatter(Report_Mgr.__detail_log_formatter)
        logging.getLogger().addHandler(self.__root_log_file_handler)

        logger.info("Audit Time:{}".format(curr_time.strftime("%Y-%m-%d %H:%M:%S")))
        logger.info("Audit Desc:{}".format(audit_desc))
        self.__root_log_file_handler.flush()

        os.makedirs(self.__currlog_dir + "/audit_report", exist_ok=True)
        self.__report_toc_file = open(self.__currlog_dir + "/audit_report/TMP_Report_TOC.md", "w", encoding="utf-8")
        self.__report_detail_file = open(self.__currlog_dir + "/audit_report/TMP_Report_Detail.md", "w", encoding="utf-8")

        self.__report_toc_file.write(
"""
# 测试报告

**测试时间**: {}
**测试项目**: {}
**测试说明**: {}
**测试结论**: 
##RESULT_NOT_SET##

# 测试车辆

Vehicle Profile ID:  {}
Vehicle Description: {}
Vehicle Model:       {}
Vehicle VIN:         {}
Vehicle TCAM_WIFI_SSID:	 {}
Vehicle TCAM_WIFI_BSSID: {}
Vehicle TCAM_WIFI_PASSWD:{}
Vehicle DHU_WIFI_SSID:	 {}
Vehicle DHU_WIFI_BSSID:  {}
Vehicle DHU_WIFI_PASSWD: {}
Vehicle TCAM_BLE_NAME:	 {}
Vehicle TCAM_BLE_MAC:	 {}
Vehicle DHU_ADB_SERIAL_ID:{}
Vehicle DHU_ADB_NAME:     {}
Vehicle TCAM_ADB_SERIAL_ID:{}
Vehicle TCAM_ADB_NAME:     {}
Vehicle ATTRIBUTES:
```
{}
```

# 测试列表

|测试项目|测试耗时(秒)|测试结果|
|-----------|-----------|-----------|
""".format(curr_time.strftime("%Y-%m-%d %H:%M:%S"), test_project, audit_desc,
    vehicle_profile.pk, vehicle_profile.Description,
    vehicle_profile.vehicle_model, vehicle_profile.Vehicle_Pin,
    vehicle_profile.TCAM_WIFI_SSID, vehicle_profile.TCAM_WIFI_BSSID, vehicle_profile.TCAM_WIFI_PASSWD, 
    vehicle_profile.DHU_WIFI_SSID, vehicle_profile.DHU_WIFI_BSSID, vehicle_profile.DHU_WIFI_PASSWD,     
    vehicle_profile.TCAM_BLE_NAME, vehicle_profile.TCAM_BLE_MAC,
    vehicle_profile.DHU_ADB_SERIAL_ID, vehicle_profile.DHU_ADB_NAME,
    vehicle_profile.TCAM_ADB_SERIAL_ID, vehicle_profile.TCAM_ADB_NAME,    
    vehicle_profile.Attributes))
        
        self.__report_toc_tree_list = []
        self.__report_test_result_tree_list = []
                
        self.__report_detail_file.write(
"""
""")
        self.__report_detail_tree_list = []

#######################

    def __calc_emsp_str(self, toc_level):
        emsp_str = ""
        while toc_level > 0:
            emsp_str = "&emsp;&emsp;" + emsp_str
            toc_level -= 1
        return emsp_str
    
    def __calc_hashtag_str(self, toc_level):
        hash_str = "#"
        while toc_level > 0:
            hash_str = "#" + hash_str
            toc_level -= 1
        return hash_str    

    def __calc_execution_time(self, start_ts:datetime.datetime, finish_ts:datetime.datetime):
        diff = finish_ts - start_ts
        return str(diff)

    def __format_toc_title(self, str_input):
        return str(str_input).replace("|", "\|")

    def record_TestStand_before_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return

        record_dict["ts_before_teststand"] = datetime.datetime.now()
        record_dict["teststand_toc"] = record_dict["toc_level"]

        toc_active_teststand_list = ["", []]
        detail_active_teststand_list = ["", []]
        result_active_teststand_list = [{"test_project":record_dict["test_stand"], "toc_level":record_dict["teststand_toc"], "status":"进行中"}, []]

        record_dict["active_teststand_list"] = (toc_active_teststand_list, detail_active_teststand_list, result_active_teststand_list)
        
        #测试stand一定是根目录执行
        self.__report_toc_tree_list.append(toc_active_teststand_list)
        self.__report_detail_tree_list.append(detail_active_teststand_list)
        self.__report_test_result_tree_list.append(result_active_teststand_list)

        return
        
    def record_TestStand_after_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return
        record_dict["ts_after_teststand"] = datetime.datetime.now()

####### TOC 
        emsp_str = self.__calc_emsp_str(record_dict["teststand_toc"]) + "└"
        record_toc = "|{} {}(#TestStand{})|".format(emsp_str, self.__format_toc_title(record_dict["test_stand"]), record_dict["ts_before_teststand"].timestamp())
        record_toc += self.__calc_execution_time(record_dict["ts_before_teststand"],  record_dict["ts_after_teststand"])
        if record_dict["test_result"] < 0:
            result_label = "{}".format(Report_Mgr.__test_no_label)
            record_dict["active_teststand_list"][2][0]["status"] = "不通过"
        else:
            result_label = "{}".format(Report_Mgr.__test_ok_label)
            record_dict["active_teststand_list"][2][0]["status"] = "通过"

        record_toc += "|{}|".format(result_label)
        record_dict["active_teststand_list"][0][0] = record_toc

####### DETAIL
        list_detail = ""
        for test_group in record_dict["test_stand"].test_groups.all():
            list_detail += " * {}\n".format(test_group)

        hashtag_str = self.__calc_hashtag_str(record_dict["teststand_toc"])
        record_detail = \
"""
{hashtag}# <a id="TestStand{timestamp}">{test_stand}</a>

{hashtag}## 详细信息
ID:\t {pk}
Desc:\t {desc}
NAME:\t {name}
TestGroups List (Total Count:{count}):
{list_detail}

{hashtag}## 测试结果
**{result}**

{hashtag}### 判定理由
{result_desc}

{hashtag}### 测试日志
开始时间:\t{ts_before}
结束时间:\t{ts_after}
测试耗时(秒):\t{ts_diff}


""".format(hashtag=hashtag_str, 
           desc=record_dict["test_stand"].description,
           test_stand=record_dict["test_stand"], pk=record_dict["test_stand"].pk, name=record_dict["test_stand"].name, count=record_dict["test_stand"].test_groups_count(),
           list_detail=list_detail,
           timestamp=record_dict["ts_before_teststand"].timestamp(),
           ts_before=record_dict["ts_before_teststand"], ts_after=record_dict["ts_after_teststand"],ts_diff = self.__calc_execution_time(record_dict["ts_before_teststand"],  record_dict["ts_after_teststand"]),
           result=result_label, result_desc=record_dict["test_result_desc"])
        record_dict["active_teststand_list"][1][0] = record_detail

        self.__flush_audit_report()
        return 

#######################
    def record_TestGroup_before_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return

        record_dict["ts_before_testgroup"] = datetime.datetime.now()
        record_dict["testgroup_toc"] = record_dict["toc_level"]

        toc_active_testgroup_list = ["", []]
        detail_active_testgroup_list = ["", []]
        result_active_testgroup_list = [{"test_project":record_dict["test_group"], "toc_level":record_dict["testgroup_toc"], "status":"进行中"}, []]

        record_dict["active_testgroup_list"] = (toc_active_testgroup_list, detail_active_testgroup_list, result_active_testgroup_list)

        if record_dict["toc_level"] == 0:
            self.__report_toc_tree_list.append(toc_active_testgroup_list)
            self.__report_detail_tree_list.append(detail_active_testgroup_list)
            self.__report_test_result_tree_list.append(result_active_testgroup_list)

        else:
            record_dict["active_teststand_list"][0][1].append(toc_active_testgroup_list)
            record_dict["active_teststand_list"][1][1].append(detail_active_testgroup_list)
            record_dict["active_teststand_list"][2][1].append(result_active_testgroup_list)

        return
        
    def record_TestGroup_after_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return
        
        record_dict["ts_after_testgroup"] = datetime.datetime.now()

####### TOC 
        emsp_str = self.__calc_emsp_str(record_dict["testgroup_toc"]) + "└"
        record_toc = "|{} {}(#TestGroup{})|".format(emsp_str, self.__format_toc_title(record_dict["test_group"]), record_dict["ts_before_testgroup"].timestamp())
        record_toc += self.__calc_execution_time(record_dict["ts_before_testgroup"],  record_dict["ts_after_testgroup"])
        if record_dict["test_result"] < 0:
            result_label = "{}".format(Report_Mgr.__test_no_label)
            record_dict["active_testgroup_list"][2][0]["status"] = "不通过"            
        else:
            result_label = "{}".format(Report_Mgr.__test_ok_label)
            record_dict["active_testgroup_list"][2][0]["status"] = "通过"

        record_toc += "|{}|".format(result_label)
        record_dict["active_testgroup_list"][0][0] = record_toc

####### DETAIL
        testgrouplist_detail = ""
        for test_group in record_dict["test_group"].test_groups.all():
            testgrouplist_detail += " * {}\n".format(test_group)

        testcaselist_detail = ""
        for test_case in record_dict["test_group"].test_cases.all():
            testcaselist_detail += " * {}\n".format(test_case)

        hashtag_str = self.__calc_hashtag_str(record_dict["testgroup_toc"])
        record_detail = \
"""
{hashtag}# <a id="TestGroup{timestamp}">{test_group}</a>

{hashtag}## 详细信息
ID:\t {pk}
Desc:\t {desc}
NAME:\t {name}
TestGroups List (Total Count:{test_groups_count}):
{testgrouplist_detail}
TestCases List (Total Count:{test_cases_count}):
{testcaselist_detail}

{hashtag}## 测试结果
**{result}**

{hashtag}### 判定理由
{result_desc}

{hashtag}### 测试日志
开始时间:\t{ts_before}
结束时间:\t{ts_after}
测试耗时(秒):\t{ts_diff}


""".format(hashtag=hashtag_str, 
           desc=record_dict["test_group"].description,
           test_group=record_dict["test_group"], pk=record_dict["test_group"].pk, name=record_dict["test_group"].name, 
           test_groups_count=record_dict["test_group"].test_groups_count(), testgrouplist_detail=testgrouplist_detail,
           test_cases_count=record_dict["test_group"].test_cases_count(),   testcaselist_detail=testcaselist_detail,           
           timestamp=record_dict["ts_before_testgroup"].timestamp(),
           ts_before=record_dict["ts_before_testgroup"], ts_after=record_dict["ts_after_testgroup"],ts_diff = self.__calc_execution_time(record_dict["ts_before_testgroup"],  record_dict["ts_after_testgroup"]),
           result=result_label, result_desc=record_dict["test_result_desc"])
        record_dict["active_testgroup_list"][1][0] = record_detail

        if record_dict["testgroup_toc"] == 0:
            self.__flush_audit_report()
        return 

#######################
    def record_TestCase_before_audit(self, record_dict:dict):     
        if self.__report_toc_tree_list == None:
            return

        record_dict["ts_before_testcase"] = datetime.datetime.now()
        record_dict["testcase_toc"] = record_dict["toc_level"]

        toc_active_testcase_list = ["", []]
        detail_active_testcase_list = ["", []]
        result_active_testcase_list = [{"test_project":record_dict["test_case"], "toc_level":record_dict["testcase_toc"], "status":"进行中"}, []]

        record_dict["active_testcase_list"] = (toc_active_testcase_list, detail_active_testcase_list, result_active_testcase_list)

        if record_dict["toc_level"] == 0:
            self.__report_toc_tree_list.append(toc_active_testcase_list)
            self.__report_detail_tree_list.append(detail_active_testcase_list)
            self.__report_test_result_tree_list.append(result_active_testcase_list)

        else:
            record_dict["active_testgroup_list"][0][1].append(toc_active_testcase_list)
            record_dict["active_testgroup_list"][1][1].append(detail_active_testcase_list)
            record_dict["active_testgroup_list"][2][1].append(result_active_testcase_list)

        return
    
    def record_TestCase_after_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return
                
        record_dict["ts_after_testcase"] = datetime.datetime.now()

####### TOC 
        emsp_str = self.__calc_emsp_str(record_dict["testcase_toc"]) + "└"
        record_toc = "|{} {}(#TestCase{})|".format(emsp_str, self.__format_toc_title(record_dict["test_case"]), record_dict["ts_before_testcase"].timestamp())
        record_toc += self.__calc_execution_time(record_dict["ts_before_testcase"],  record_dict["ts_after_testcase"])
        if record_dict["test_result"] < 0:
            result_label = "{}".format(Report_Mgr.__test_no_label)
            record_dict["active_testcase_list"][2][0]["status"] = "不通过"            

        else:
            result_label = "{}".format(Report_Mgr.__test_ok_label)
            record_dict["active_testcase_list"][2][0]["status"] = "通过"            

        record_toc += "|{}|".format(result_label)
        record_dict["active_testcase_list"][0][0] = record_toc

####### DETAIL
        list_detail = ""
        for step_seq in record_dict["test_case"].test_steps_seqs():
            list_detail += " * Sequence:{} \t TestStep:{} Ignore Fail:{}\n".format(step_seq.sequence, step_seq.teststep, step_seq.ignore_fail)

        hashtag_str = self.__calc_hashtag_str(record_dict["testcase_toc"])
        record_detail = \
"""
{hashtag}# <a id="TestCase{timestamp}">{test_case}</a>

{hashtag}## 详细信息
ID:\t {pk}
Desc:\t {desc}
NAME:\t {name}
Init TestStep:    {init_step}
Cleanup TestStep: {cleanup_step}
TestSteps List (Total Count:{count}):
{list_detail}

{hashtag}## 测试结果
**{result}**

{hashtag}### 判定理由
{result_desc}

{hashtag}### 测试日志
开始时间:\t{ts_before}
结束时间:\t{ts_after}
测试耗时(秒):\t{ts_diff}

""".format(hashtag=hashtag_str, 
           desc=record_dict["test_case"].description, 
           test_case=record_dict["test_case"], pk=record_dict["test_case"].pk, name=record_dict["test_case"].name, count=record_dict["test_case"].test_steps_count(),
           list_detail=list_detail, init_step=record_dict["test_case"].init_step, cleanup_step=record_dict["test_case"].cleanup_step,
           timestamp=record_dict["ts_before_testcase"].timestamp(),
           ts_before=record_dict["ts_before_testcase"], ts_after=record_dict["ts_after_testcase"],ts_diff = self.__calc_execution_time(record_dict["ts_before_testcase"],  record_dict["ts_after_testcase"]),
           result=result_label, result_desc=record_dict["test_result_desc"])
        record_dict["active_testcase_list"][1][0] = record_detail

        if record_dict["testcase_toc"] == 0:
            self.__flush_audit_report()
        return 

#######################
    def record_TestStep_before_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return

        record_dict["ts_before_teststep"] = datetime.datetime.now()
        record_dict["teststep_toc"] = record_dict["toc_level"]

        toc_active_teststep = ""
        detail_active_teststep = ""
        result_active_teststep = {"test_project":record_dict["test_step"], "toc_level":record_dict["teststep_toc"], "status":"进行中"}
        record_dict["active_teststep_list"] = (toc_active_teststep, detail_active_teststep, result_active_teststep)

        if record_dict["toc_level"] == 0:
            self.__report_test_result_tree_list.append(result_active_teststep)
        else:
            record_dict["active_testcase_list"][2][1].append(result_active_teststep)

        return
    
    def record_TestStep_after_audit(self, record_dict:dict):
        if self.__report_toc_tree_list == None:
            return

        record_dict["ts_after_teststep"] = datetime.datetime.now()

####### TOC 
        if record_dict["teststep_toc"] == 0:          
            emsp_str = self.__calc_emsp_str(record_dict["teststep_toc"]) + "└"
        else:
            emsp_str = self.__calc_emsp_str(record_dict["teststep_toc"]) + "\|-"

        record_toc = "|{} {}(#TestStep{})|".format(emsp_str, self.__format_toc_title(record_dict["test_step"]), record_dict["ts_before_teststep"].timestamp())
        record_toc += self.__calc_execution_time(record_dict["ts_before_teststep"],  record_dict["ts_after_teststep"])
        if record_dict["test_result"] < SAT_Exception.FAIL__ERRORCODE__START:
            result_label = "{}".format(Report_Mgr.__test_no_label)
            record_dict["active_teststep_list"][2]["status"] = "不通过"

        elif record_dict["test_result"] < SAT_Exception.ERROR__ERRORCODE__START:
            result_label = "{}".format(Report_Mgr.__test_no_label)
            record_dict["active_teststep_list"][2]["status"] = "不通过"
            # result_label = "{}".format(Report_Mgr.__test_fail_label)
            # record_dict["active_teststep_list"][2]["status"] = "失败"
        
        elif record_dict["test_result"] == 0:
            result_label = "{}".format(Report_Mgr.__test_finish_label)
            record_dict["active_teststep_list"][2]["status"] = "完成"
        
        else:
            result_label = "{}".format(Report_Mgr.__test_ok_label) 
            record_dict["active_teststep_list"][2]["status"] = "通过"

        record_toc += "|{}|".format(result_label)

####### DETAIL
        hashtag_str = self.__calc_hashtag_str(record_dict["teststep_toc"])
        record_detail = \
"""
{hashtag}# <a id="TestStep{timestamp}">{test_step}</a>

{hashtag}## 详细信息
ID:\t {pk}
NAME:\t {name}
DESC:\t {desc}

{hashtag}## 测试结果
**{result}**

{hashtag}## 判定依据
```
{result_desc}
```
{hashtag}## 测试日志
开始时间:\t{ts_before}
结束时间:\t{ts_after}
测试耗时(秒):\t{ts_diff}
""".format(hashtag=hashtag_str, 
           desc=record_dict["test_step"].description,
           test_step=record_dict["test_step"], pk=record_dict["test_step"].pk, name=record_dict["test_step"].name,
           cmd_type=record_dict["test_step"].cmd_type, command_detail=record_dict["test_step"].command_detail,
           pass_condition=record_dict["test_step"].pass_condition, predefined_list=record_dict["test_step"].predefined_list,
           timestamp=record_dict["ts_before_teststep"].timestamp(),
           ts_before=record_dict["ts_before_teststep"], ts_after=record_dict["ts_after_teststep"],ts_diff = self.__calc_execution_time(record_dict["ts_before_teststep"],  record_dict["ts_after_teststep"]),
           result=result_label, result_desc=record_dict["test_result_desc"])
        
        if len(record_dict["test_result_log"]) != 0:
            record_detail += \
"""
执行日志:
```
{log}
```
""".format(log=record_dict["test_result_log"])

        test_result_png = Env_Mgr.Instance().query(Env_Mgr.ENV_PreFix + "TestResut_PNG")
        if test_result_png != None:
            test_result_png = test_result_png.replace(self.__currlog_dir, "..")
            record_detail += \
"""
执行截图:
![{0}]({1} "{2}")
""".format(test_result_png, test_result_png, record_dict["test_step"])

        if record_dict["teststep_toc"] == 0:
            self.__report_toc_tree_list.append(record_toc)
            self.__report_detail_tree_list.append(record_detail)

            self.__flush_audit_report()
        else:
            record_dict["active_testcase_list"][0][1].append(record_toc)
            record_dict["active_testcase_list"][1][1].append(record_detail)
       

        return 

#######################

    def __flush_audit_report(self):
        if self.__report_toc_file != None:
            self.__write_toc_list(self.__report_toc_tree_list)
            self.__report_toc_tree_list = []
            self.__report_toc_file.flush()
        
        if self.__report_detail_file != None:
            self.__write_detail_list(self.__report_detail_tree_list)
            self.__report_detail_tree_list = []
            self.__report_detail_file.flush()            

    def __write_toc_list(self, tree_list):
        for item in tree_list:
            if isinstance(item, list):
                self.__write_toc_list(item)
            else:
                self.__report_toc_file.write(item + "\n")

    def __write_detail_list(self, tree_list):
        for item in tree_list:
            if isinstance(item, list):
                self.__write_detail_list(item)
            else:
                self.__report_detail_file.write(item + "\n")

    # def __expand_toc_list(self, tree_list, expand_list):
    #     for item in tree_list:
    #         if isinstance(item, list):
    #             self.__expand_toc_list(item, expand_list)
    #         else:
    #             expand_list.append(str(item))


    def stop_audit(self, test_result = 0, test_result_desc = ""):     
        # self.__report_test_toc_tree_list = []
        # logger.info("self.__report_toc_tree_list:{}".format(self.__report_toc_tree_list))
        # if self.__report_toc_tree_list != None:
        #     self.__expand_toc_list(self.__report_toc_tree_list, self.__report_test_toc_tree_list)

        curr_time = datetime.datetime.now()
        Env_Mgr.Instance().set("AUDIT_STOP_TIME", curr_time)

        self.__report_test_result = test_result
        self.__report_test_result_desc = test_result_desc           

        self.__flush_audit_report()
        self.__report_toc_tree_list = None
        self.__report_detail_tree_list = None

        if self.__report_toc_file != None:
            self.__report_toc_file.close()
            self.__report_toc_file = None

        if self.__report_detail_file != None:
            self.__report_detail_file.close()
            self.__report_detail_file = None

            logger.info("Audit Stop. Start To Generate Audit Report.")

            tmp_toc_file = open(self.__currlog_dir + "/audit_report/TMP_Report_TOC.md", "r", encoding="utf-8")
            tmp_detail_file = open(self.__currlog_dir + "/audit_report/TMP_Report_Detail.md", "r", encoding="utf-8")
            audit_report_file = open(self.__currlog_dir + "/audit_report/Audit_Report.md", "w", encoding="utf-8")

            toc_content = tmp_toc_file.read()

            if test_result < 0:
                toc_content = toc_content.replace("##RESULT_NOT_SET##", """<span style="color:red;font-weight:bold;font-size:20pt;">不通过</span>""")
            else:
                toc_content = toc_content.replace("##RESULT_NOT_SET##", """<span style="color:green;font-weight:bold;font-size:20pt;">通过</span>""")

            audit_report_file.write(toc_content)
            for line in tmp_detail_file:
                audit_report_file.write(line)
            audit_report_file.close()
            logger.info("Audit_Report.md Generate Success. Path:" + self.__currlog_dir + "/audit_report/Audit_Report.md")
            
            with open(self.__currlog_dir + "/audit_report/Audit_Report.md", 'r') as f:
                markdown_text = f.read()
                render = mistune.create_markdown(
                    escape=False,
                    hard_wrap = True,
                    plugins=['strikethrough', 'footnotes', 'table', 'speedup']
                )
                html = render(markdown_text)
                with open(self.__currlog_dir + "/audit_report/Audit_Report.html", 'w') as output:
                    output.write(html)

            logger.info("Audit_Report.html Generate Success. Path:" + self.__currlog_dir + "/audit_report/Audit_Report.html")
            try:
                os.unlink(Report_Mgr.__log_root_dir + "/Audit_Report.html")
            except Exception as err:
                pass

            try:
                os.symlink(self.__currlog_dir + "/audit_report/Audit_Report.html", Report_Mgr.__log_root_dir + "/Audit_Report.html")
                logger.info("Audit_Report.html LinkTo :{} Success.".format(Report_Mgr.__log_root_dir + "/Audit_Report.html"))
            except Exception as err:
                logger.exception("Audit_Report.html LinkTo :{} Fail!".format(Report_Mgr.__log_root_dir + "/Audit_Report.html"))
        
        if self.__root_log_file_handler != None:
            self.__root_log_file_handler.flush()
            logging.getLogger().removeHandler(self.__root_log_file_handler)
            self.__root_log_file_handler = None
        
        self.__currlog_dir = "{}/{}".format(Report_Mgr.__log_root_dir, "QUICK_TEST")
        return
    
#######################
    def start_log_teststep_exec_process(self, test_step):
        if self.__teststep_log_file_handler != None:
            self.__teststep_log_file_handler.flush()
            logging.getLogger().removeHandler(self.__teststep_log_file_handler)

        log_name_compatible = test_step.name.replace(" ","_").replace("|","_")
        self.__teststep_log_file_path = "{}/TestStep/{}_{}##{}.log".format(self.__currlog_dir, datetime.datetime.now().timestamp(), test_step.pk, log_name_compatible)
        os.makedirs(os.path.dirname(self.__teststep_log_file_path), exist_ok=True)
        logger.info("TestStep LOG Start. FilePath:{} \n----------".format(self.__teststep_log_file_path))
        
        self.__teststep_log_file_handler = logging.FileHandler(self.__teststep_log_file_path, "w", encoding="utf-8")
        self.__teststep_log_file_handler.setFormatter(Report_Mgr.__raw_log_formatter)
        logging.getLogger().addHandler(self.__teststep_log_file_handler)
        
        if self.__root_log_file_handler != None:
            self.__root_log_file_handler.setFormatter(Report_Mgr.__raw_log_formatter)
        self.__root_log_console_handler.setFormatter(Report_Mgr.__raw_log_formatter)


    def stop_log_teststep_exec_process(self):        
        if self.__teststep_log_file_handler != None:
            self.__teststep_log_file_handler.flush()
            logging.getLogger().removeHandler(self.__teststep_log_file_handler)
        self.__teststep_log_file_handler = None

        logger.info("----------")
        if self.__root_log_file_handler != None:
            self.__root_log_file_handler.setFormatter(Report_Mgr.__detail_log_formatter)
        self.__root_log_console_handler.setFormatter(Report_Mgr.__detail_log_formatter)
        logger.info("TestStep LOG Finish. FilePath:{}".format(self.__teststep_log_file_path))

        if self.__teststep_log_file_path != None:
            with open(self.__teststep_log_file_path, 'r', encoding="utf-8") as f:
                log_content = f.read()

            self.__teststep_log_file_path = None
            return log_content
        else:
            return ""

#######################


_instance = Report_Mgr()

