import logging
logger = logging.getLogger(__name__)

import os
from sat_toolkit.tools.sat_utils import *

class Env_Mgr:
    ENV_PreFix = "__SAT_ENV__"

    @staticmethod
    def Instance():
        return _instance
    
    def __init__(self):
        self.__sat_env = {}
        self.__sat_env[Env_Mgr.ENV_PreFix + "DHU_TMP_DIR"] = "/sdcard/sat_snapshot"

    def unset(self, key):
        if key.startswith(Env_Mgr.ENV_PreFix) != True:
            key = Env_Mgr.ENV_PreFix + key        
        self.__sat_env.pop(key, "")

    def set(self, key, value):
        if key.startswith(Env_Mgr.ENV_PreFix) != True:
            key = Env_Mgr.ENV_PreFix + key
        self.__sat_env[key] = value
        logger.info("SAT Env Update. Key:{} Value:{}".format(key, value))

    def dump(self):
        logger.info("SAT Env: {}".format(self.__sat_env))

    def clear(self):
        self.__sat_env.clear()

    def get(self, key, effective_check = True):
        if key.startswith(Env_Mgr.ENV_PreFix) != True:
            key = Env_Mgr.ENV_PreFix + key
        if key in self.__sat_env:
            value = self.__sat_env[key]
            if effective_check == True:
                if isinstance(value, str) and len(value) == 0:
                    raise_err("{} Found In ENV.Empty String.Effective Check Fail!".format(key))
                    
            return value
        else:
            raise_err("{} Not Found In ENV!".format(key))

    def query(self, key, default_value = None, effective_check = True):
        if key.startswith(Env_Mgr.ENV_PreFix) != True:
            key = Env_Mgr.ENV_PreFix + key

        if key in self.__sat_env:
            value = self.__sat_env[key]
            if effective_check == True:
                if isinstance(value, str) and len(value) == 0:
                    logger.info("{} Found In ENV.Empty String.Effective Check Fail. Return Default Value".format(key))
                    return default_value
            return value
        else:
            # logger.info("{} Not Found In ENV. Return Default Value".format(key))

            return default_value

    def fork_sat_env(self):
        bash_env = os.environ.copy()
        for key, value in self.__sat_env.items():
            bash_env[key] = str(value)
        
        # 只支持字符串的value
        # bash_env.update(self.__sat_env)
        # logger.info("SAT Bash Env:\n{}".format(bash_env))

        return bash_env
        # return self.__sat_env

    def read_sat_env_from_log(self, log_content:str):
        if log_content.startswith("__SAT_ENV__EXPORT__INCLUDED") != True:
            return
        for line in log_content.splitlines():
            if line.startswith("__SAT_ENV__EXPORT:__SAT_ENV__"):
                key_list = line.split(":", 1)
                if len(key_list) != 2:
                    logger.error("Read SAT_ENV Fail! LOG PreFix Format Invalid:{}".format(line))
                    continue
                kev_value = key_list[1].split("=", 1)
                if len(kev_value) != 2:
                    logger.error("Read SAT_ENV Fail! LOG KeyValue Format Invalid:{}".format(line))
                    continue
                self.__sat_env[kev_value[0]] = kev_value[1]
                logger.info("Read SAT_ENV Success. {}:{}".format(kev_value[0], kev_value[1]))

        self.dump()

    def update_vehicle_env(self, vehicle):
        delete_key_list = []
        for key in self.__sat_env.keys():
            if key.startswith("__SAT_ENV__VehicleInfo_") or key.startswith("__SAT_ENV__VehicleModel_"):
                delete_key_list.append(key)

        for delete_key in delete_key_list:
            self.unset(delete_key)

        self.__sat_env.update(vehicle.export_env())
        
        self.set("VEHICLE_PROFILE", vehicle)        
        # self.dump()

    def merge_env(self, out_env_dict):
        for key,value in out_env_dict.items():
            if key.startswith(Env_Mgr.ENV_PreFix):
                self.__sat_env[key] = value
        # self.dump()

    def explain_env_in_list(self, str_list:str):
        result_list = []
        for single_str in str_list:
            if single_str[0] == "$" and single_str[1:] in self.__sat_env:
                logger.info("Found ENV Param. Replace {} To {}".format(single_str, self.__sat_env[ single_str[1:] ]))
                result_list.append(self.__sat_env[ single_str[1:] ])
            else:
                result_list.append(single_str)
        return result_list
    
    #TODO 环境变量支持保存
    def save_to_file(self, file_path:str):
        pass

    #TODO 环境变量支持载入
    def load_from_file(self,file_path:str):
        pass
    
_instance = Env_Mgr()

