import logging
logger = logging.getLogger(__name__)

import os
from pathlib import Path

from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr

class OTA_Mgr:
    __system_version = "v20231101"
    __testsuite_version = "0000001"
    # Default UI directory name, can be changed via set_ui_dir
    __ui_dir = "sat_ui"

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass
    
    def set_ui_dir(self, ui_dir):
        """Set the UI directory path"""
        self.__ui_dir = ui_dir
        logger.info(f"UI directory set to: {self.__ui_dir}")

    def __ui_version(self):
        logger.info("Curr UI Version:")
        result_code, version = Bash_Script_Mgr.Instance().exec_cmd(
f"""
cd {self.__ui_dir}; git log -1 --pretty="%cd_%h" --date=short
""")
        logger.info("UI Version Query Result: {} {}".format(result_code, version))
        if result_code < 0:
            version = "unknown"
        return version.replace("-","")     
    
    def __sat_core_version(self):
        logger.info("Curr SAT Core Version:")
        result_code, version = Bash_Script_Mgr.Instance().exec_cmd(
"""
git log -1 --pretty="%cd_%h" --date=short
""")
        logger.info("SAT Core Version Query Result: {} {}".format(result_code, version))
        if result_code < 0:
            version = "unknown"
        return version.replace("-","")   

    def __sat_testproject_version(self):
        logger.info("Curr SAT TestProject Version:")
        version = "20231223"
        return version.replace("_","")   

    def curr_version(self):
        return \
        {
            "框架版本":OTA_Mgr.Instance().__sat_core_version(),
            "用例版本": OTA_Mgr.Instance().__sat_testproject_version(),
            "UI版本":  OTA_Mgr.Instance().__ui_version(),
        }

_instance = OTA_Mgr()

