import logging
import json
import os
import threading
from sat_toolkit.tools.sat_utils import *

# Configure logging
logger = logging.getLogger(__name__)

class Env_Mgr:
    ENV_PreFix = "__SAT_ENV__"
    
    # Singleton pattern implementation with thread safety
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Env_Mgr, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    @staticmethod
    def Instance():
        return Env_Mgr()
    
    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            logger.info("Initializing Env_Mgr singleton")
            self.__sat_env = {}
            self.__sat_env[Env_Mgr.ENV_PreFix + "DHU_TMP_DIR"] = "/sdcard/sat_snapshot"
            self._initialized = True

    def unset(self, key):
        with self._lock:
            if key.startswith(Env_Mgr.ENV_PreFix) != True:
                key = Env_Mgr.ENV_PreFix + key        
            self.__sat_env.pop(key, "")

    def set(self, key, value):
        with self._lock:
            if key.startswith(Env_Mgr.ENV_PreFix) != True:
                key = Env_Mgr.ENV_PreFix + key
            self.__sat_env[key] = value
            logger.debug("SAT Env Update. Key:{} Value:{}".format(key, value))

    def dump(self):
        logger.info("SAT Env: {}".format(self.__sat_env))

    def clear(self):
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            for key,value in out_env_dict.items():
                if key.startswith(Env_Mgr.ENV_PreFix):
                    self.__sat_env[key] = value
            # self.dump()

    def explain_env_in_list(self, str_list:list):
        result_list = []
        for single_str in str_list:
            if isinstance(single_str, str) and single_str.startswith("$") and single_str[1:] in self.__sat_env:
                logger.info("Found ENV Param. Replace {} To {}".format(single_str, self.__sat_env[ single_str[1:] ]))
                result_list.append(self.__sat_env[ single_str[1:] ])
            else:
                result_list.append(single_str)
        return result_list
    
    def save_to_file(self, file_path:str):
        """Save environment variables to a JSON file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert all values to JSON-serializable types
            serializable_env = {}
            for key, value in self.__sat_env.items():
                # Skip complex objects that can't be serialized
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    serializable_env[key] = value
                else:
                    # Convert complex objects to string representation
                    serializable_env[key] = str(value)
                    
            with open(file_path, 'w') as f:
                json.dump(serializable_env, f, indent=2)
                
            logger.info(f"Environment saved to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save environment to {file_path}: {str(e)}")
            return False

    def load_from_file(self, file_path:str):
        """Load environment variables from a JSON file"""
        if not os.path.exists(file_path):
            logger.warning(f"Environment file {file_path} does not exist")
            return False
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            with self._lock:
                for key, value in data.items():
                    self.__sat_env[key] = value
                    
            logger.info(f"Environment loaded from {file_path}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to load environment from {file_path}: {str(e)}")
            return False

if __name__ == "__main__":
    # Example usage
    print("Starting script...")
    env_mgr = Env_Mgr.Instance()
    env_mgr.set("test_key", "test_value")
    env_mgr.dump()
    
    # Retrieve values
    try:
        value = env_mgr.get("test_key")
        print(f"Value: {value}")
    except Exception as e:
        print(f"Error: {e}")
