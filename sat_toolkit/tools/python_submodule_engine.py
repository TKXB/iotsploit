import logging
logger = logging.getLogger(__name__)

import os
import importlib.util
import sys

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *

class Python_SubModule_Mgr:
    __script_dir = "scripts/python"
    __temp_submodule_file_path = "/dev/shm/__Zeekr_SAT_TMP_FILES/tmp_python_submodule.py"

    @staticmethod
    def Instance():
        return _instance
    
    def __init__(self):
        pass
        
    def __check_result(self, test_step, exec_result):
        if test_step.pass_check() == 0: #record
            logger.info("Python SubModule Result Check Success. Result: Record")
            return 0, "Record Always Success."

        if test_step.pass_check() == 1: #whitelist
            result = -1
            result_desc = ""
            exec_result = exec_result.upper()
            predefined_list = test_step.predefined_list.splitlines()
            predefined_list = Env_Mgr.Instance().explain_env_in_list(predefined_list)

            for check_str in predefined_list:
                if exec_result.find(check_str.upper()) != -1:
                    logger.info("WhilteList '{}' Found In Exec Result. Result: Pass".format(check_str))
                    result = 1
                    result_desc += "WhilteList '{}' Found In Exec Result.\n".format(check_str)

            if result == -1:
                result_desc = "WhilteList NOT Found In Exec Result!"

            logger.info("Python SubModule Result Check Success. Result:{} Result Desc:{}".format(result, result_desc))
            return result, result_desc

        if test_step.pass_check() == 2: #blacklist
            result = 1
            result_desc = ""

            exec_result = exec_result.upper()
            predefined_list = test_step.predefined_list.splitlines()
            predefined_list = Env_Mgr.Instance().explain_env_in_list(predefined_list)

            for check_str in predefined_list:
                if exec_result.find(check_str.upper()) != -1:
                    logger.info("BlackList '{}' Found In Exec Result. Result: Fail".format(check_str))
                    result = -1
                    result_desc += "BlackList '{}' Found In Exec Result.\n".format(check_str)

            if result == 1:
                result_desc = "BlackList NOT Found In Exec Result."

            logger.info("Python SubModule Result Check Success. Result:{} Result Desc:{}".format(result, result_desc))
            return result, result_desc
        
        logger.error("Python SubModule Result Check Fail!. Check Pattern: '{}' Not Support. Result: Fail".format(test_step.pass_condition))
        return -1, "Check Pattern: '{}' Not Support".format(test_step.pass_condition)


    def exec(self, test_step):
        logger.info("Start To Exec Python Submodule -->>")

        if test_step.cmd_type == "Python File":
            cmd_list = test_step.command_detail.split()
            file_abs_path = Python_SubModule_Mgr.__script_dir + "/" + cmd_list[0]
            cmd_param = cmd_list[1:]

            if os.path.isfile(file_abs_path) != True:
                logger.error("Python Submodule Exec Fail! File:{} Not Exist!".format(file_abs_path))
                return -1, "File:{} Not Exist!\n".format(file_abs_path), ""
            
        else:
            try:
                os.makedirs(os.path.dirname(Python_SubModule_Mgr.__temp_submodule_file_path), exist_ok=True)
                tmp_bash_file = open(Python_SubModule_Mgr.__temp_submodule_file_path, "w", encoding="utf-8")
                tmp_bash_file.write(test_step.command_detail)
                tmp_bash_file.close()

            except Exception as err:
                logger.exception("Python Submodule Exec Fail! TEMP File:{} Write Fail!".format(Python_SubModule_Mgr.__temp_submodule_file_path))
                return -1, "File:{} Write Fail!\n".format(Python_SubModule_Mgr.__temp_submodule_file_path), ""
            
            file_abs_path = Python_SubModule_Mgr.__temp_submodule_file_path
            cmd_list = [file_abs_path, ]
            cmd_param = []

        try:
            spec = importlib.util.spec_from_file_location(cmd_list[0].replace(".py", ""), file_abs_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.info("Python SubModule Load Success. FilePath:{} Param:{}. Start To Exec -->>\n".format(file_abs_path, cmd_param))
            # Env_Mgr.Instance().dump()

            Report_Mgr.Instance().start_log_teststep_exec_process(test_step)

            try:
                if len(cmd_param) != 0:
                    result_tuple = module.main(*cmd_param)
                else:
                    result_tuple = module.main()
            except SAT_Exception as err:
                result_tuple = (err.err_code, err.err_msg)
                
            exec_result = Report_Mgr.Instance().stop_log_teststep_exec_process()

            logger.info("Python SubModule Exec Success. FilePath:{} Param:{}".format(file_abs_path, cmd_param))
            # Env_Mgr.Instance().dump()

            if result_tuple != None:
                return result_tuple[0], result_tuple[1], exec_result
            else:
                result, result_desc = self.__check_result(test_step, exec_result)
                return result, result_desc, exec_result
        
        except Exception as err:
            exec_result = Report_Mgr.Instance().stop_log_teststep_exec_process()
            logger.exception("Python Submodule Exec Fail! FilePath:{} Param:{}".format(file_abs_path, cmd_param))
            return -1, err, exec_result

_instance = Python_SubModule_Mgr()

