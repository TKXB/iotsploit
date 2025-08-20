import logging
logger = logging.getLogger(__name__)

# from sat_toolkit.models.TestStep_Model import TestStep
import os
import importlib.util
import sys
import subprocess
import tempfile
from pathlib import Path

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr


class Bash_Script_Mgr:
    __script_dir = "scripts/bash"
    __temp_dir = Path(tempfile.gettempdir()) / "sat_toolkit_tmp"
    __temp_script_file_path = str(__temp_dir / "tmp_bash_script.sh")

    @staticmethod
    def Instance():
        return _instance
    
    def __init__(self):
        # Ensure temp directory exists
        os.makedirs(self.__temp_dir, exist_ok=True)
        
    def __truncate(self, text: str) -> str:
        """Trim long outputs for concise logging."""
        try:
            max_len = int(os.environ.get("SAT_BASH_LOG_MAX_CHARS", "400"))
        except Exception:
            max_len = 400
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"... [truncated {len(text) - max_len} chars]"
        
    def __check_result(self, test_step, exec_result):
        if test_step.pass_check() == 0: #record
            logger.info("Bash Script Result Check Success. Result: Record")
            return 0, ""

        if test_step.pass_check() == 1: #whitelist
            exec_result = exec_result.upper()
            predefined_list = test_step.predefined_list.splitlines()
            predefined_list = Env_Mgr.Instance().explain_env_in_list(predefined_list)

            for check_str in predefined_list:
                if exec_result.find(check_str.upper()) != -1:
                    logger.info("Bash Script Result Check Success. WhilteList '{}' Found In Exec Result. Result: Pass".format(check_str))
                    return 1, ""
            logger.info("Bash Script Result Check Success. WhilteList NOT Found In Exec Result. Result: Fail")
            return -1, "WhilteList NOT Found In Exec Result"

        if test_step.pass_check() == 2: #blacklist
            exec_result = exec_result.upper()
            predefined_list = test_step.predefined_list.splitlines()
            predefined_list = Env_Mgr.Instance().explain_env_in_list(predefined_list)

            for check_str in predefined_list:
                if exec_result.find(check_str.upper()) != -1:
                    logger.info("Bash Script Result Check Success. BlackList '{}' Found In Exec Result. Result: Fail".format(check_str))
                    return -1, "BlackList '{}' Found In Exec Result.".format(check_str)
            logger.info("Bash Script Result Check Success. BlackList NOT Found In Exec Result. Result: Pass")
            return 1, ""
        
        logger.error("Bash Script Result Check Fail!. Check Pattern: '{}' Not Support. Result: Fail".format(test_step.pass_condition))
        return -1, "Check Pattern: '{}' Not Support".format(test_step.pass_condition)


    def exec_file(self, cmd_list:str):
        logger.info("Start To Exec Bash Script File:{} -->>".format(cmd_list))
        if os.path.isfile(cmd_list[0]) != True:
            logger.error("Bash Script Exec Fail! File:{} Not Exist!".format(cmd_list[0]))
            return -1, "File:{} Not Exist!".format(cmd_list[0])

        cmd_list.insert(0, "bash")
        try:
            process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                       stdin=subprocess.PIPE,
                                       env = Env_Mgr.Instance().fork_sat_env(),
                                       encoding="utf-8")
            out_buf, err_buf = process.communicate()
            return_code = process.returncode
            
            if return_code == 0:
                logger.info("Bash Script Exec Success. ExitCode:{} Cmd:{}".format(return_code, cmd_list))
                # For success, keep output at debug level to reduce noise
                logger.debug("Output:\n%s", self.__truncate(out_buf))
                Env_Mgr.Instance().read_sat_env_from_log(out_buf)
                return 1, out_buf
            else:
                logger.error("Bash Script Exec Fail. ExitCode:{} Cmd:{} Output:\n{}".format(return_code, cmd_list, self.__truncate(out_buf)))
                return -1, out_buf
        
        except Exception as err:
            logger.exception("Bash Script Exec Fail! Cmd:{}".format(cmd_list))
            return -2, err

    def exec_cmd(self, cmd_list:str):
        logger.info("Start To Exec Bash Script Cmd -->> %s" % self.__truncate(cmd_list.replace("\n", " | ")))
        tmp_path = None
        try:
            os.makedirs(str(Bash_Script_Mgr.__temp_dir), exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix="tmp_bash_script_", suffix=".sh", dir=str(Bash_Script_Mgr.__temp_dir))
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_bash_file:
                for single_line in cmd_list.splitlines():
                    tmp_bash_file.write(single_line + "\n")

            logger.info("Bash Script Cmd Write To TEMP File Success. File:{}".format(tmp_path))
        except Exception as err:
            logger.exception("Bash Script Cmd Exec Fail! TEMP File Write Fail! Dir:{}".format(str(Bash_Script_Mgr.__temp_dir)))
            return -1, "TEMP File Write Fail in Dir:{}\n".format(str(Bash_Script_Mgr.__temp_dir))
        
        try:
            return self.exec_file([tmp_path])
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def exec(self, test_step):
        logger.info("Start To Exec Bash Script -->>")
        
        if test_step.cmd_type == "Bash File":
            cmd_list = test_step.command_detail.split()
            file_abs_path = Bash_Script_Mgr.__script_dir + "/" + cmd_list[0]

            if os.path.isfile(file_abs_path) != True:
                logger.error("Bash Script Exec Fail! File:{} Not Exist!".format(file_abs_path))
                return -1, "File:{} Not Exist!\n".format(file_abs_path), ""
            
            cmd_list[0] = file_abs_path
        else:
            tmp_path = None
            try:
                os.makedirs(str(Bash_Script_Mgr.__temp_dir), exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(prefix="tmp_bash_script_", suffix=".sh", dir=str(Bash_Script_Mgr.__temp_dir))
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_bash_file:
                    for single_line in test_step.command_detail.splitlines():
                        tmp_bash_file.write(single_line + "\n")

                cmd_list = [tmp_path,]
            except Exception as err:
                logger.exception("Bash Script Exec Fail! TEMP File Write Fail! Dir:{}".format(str(Bash_Script_Mgr.__temp_dir)))
                return -1, "TEMP File Write Fail in Dir:{}\n".format(str(Bash_Script_Mgr.__temp_dir)), ""

        cmd_list.insert(0, "bash")
        try:
            logger.info("Bash Script Load Success. Cmd:{} . Start To Exec -->>\n".format(cmd_list)) 

            Report_Mgr.Instance().start_log_teststep_exec_process(test_step)
            process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                       stdin=subprocess.PIPE,
                                       env = Env_Mgr.Instance().fork_sat_env(),
                                       encoding="utf-8")            
            while True:
                # Avoid spamming logs; only log full output at the end
                return_code = process.poll()
                if return_code != None:
                    break
            
            exec_result = Report_Mgr.Instance().stop_log_teststep_exec_process()
            if return_code == 0:
                logger.info("Bash Script Exec Success. ReturnCode:{} Cmd:{}".format(return_code, cmd_list))
                logger.debug("Output:\n%s", self.__truncate(exec_result))
            else:
                logger.error("Bash Script Exec Fail. ReturnCode:{} Cmd:{} Output:\n{}".format(return_code, cmd_list, self.__truncate(exec_result)))
            Env_Mgr.Instance().read_sat_env_from_log(exec_result)

            result, result_desc = self.__check_result(test_step, exec_result)
            return result, result_desc, exec_result
        
        except Exception as err:
            exec_result = Report_Mgr.Instance().stop_log_teststep_exec_process()
            logger.exception("Bash Script Exec Fail! Cmd:{}".format(cmd_list))
            return -1, err, exec_result
        finally:
            try:
                if 'tmp_path' in locals() and tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

_instance = Bash_Script_Mgr()