import logging
logger = logging.getLogger(__name__)
import datetime

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *
import time

class Input_Mgr:
    BLUE = "\033[1;34m"
    RED = "\033[1;31m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        pass

    def __shell_color_input(self, string):
        return input(Input_Mgr.YELLOW + string + Input_Mgr.RESET)

    def confirm(self, title:str):
        logger.info("-------------- Please Confirm --------------")
        logger.info(title)
        run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")
        if run_in_shell:
            user_input = self.__shell_color_input("Press 'Y' To Confirm, Others To Cancel:")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result = "User Confirm '{}' At Time:{}".format(user_input, ts)
            logger.info(result)
            if user_input == "Y" or user_input == "y":
                return
            else:
                raise_err(result)
        else:
            Env_Mgr.Instance().set("SAT_NEED_UI", 
                {
                    "type":"confirm", 
                    "title":title,
                    'buttonlist': [{'name': '确认', 'color': 'active',   'action': 'POST record_user_input'}, 
                                   {'name': '否认', 'color': 'negative', 'action': 'POST record_user_input'}]                
                    })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")                
                result = "User Confirm '{}' At Time:{}".format(ui_result, ts)
                logger.info(result)
                if ui_result == "确认":
                    return
                else:
                    raise_err(result)


    def string_input(self, title:str, verify_func = None):
        run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")
        if run_in_shell:
            while True:
                logger.info("-------------- Please Input --------------")
                logger.info(title)
                user_input = self.__shell_color_input("Please Input:")
                if verify_func != None and verify_func(user_input) != True:
                    logger.error("User Input:{} Verify Fail!".format(user_input))
                    continue

                logger.info("User Input:{}\n".format(user_input))
                return user_input
        else:
            logger.info("-------------- Please Input --------------")
            Env_Mgr.Instance().set("SAT_NEED_UI", 
                {
                    "type":"string_input", 
                    "title":title,
                    'buttonlist': [{'name': '确认', 'color': 'active',   'action': 'POST record_user_input'}]                
                    })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")

                logger.info("User Input:{}\n".format(ui_result))
                return ui_result


    def single_choice(self, title:str, choice_list:list):
        run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")
        if run_in_shell:
            while True:
                logger.info("----------------------------")
                logger.info(title)
                logger.info("  ID  \t{}".format("Description"))

                index = 0
                for choice in choice_list:
                    index += 1
                    logger.info("  {}: \t{}".format(index, choice))

                user_input = self.__shell_color_input("Please Input 1 ~ {}:".format(index))
                try:
                    user_input_int = int(user_input)
                except Exception as err:
                    logger.exception("User Input:{} Is Inavlid!".format(user_input))
                    continue
                
                if user_input_int < 1 or user_input_int > index:
                    logger.error("User Input:{} Not In '1 ~ {}'!".format(user_input_int, index))
                    continue
                else:
                    logger.debug("User Input:{}  Select '{}: {}'\n".format(user_input, user_input_int, choice_list[user_input_int-1]))

                    return choice_list[user_input_int-1]
                
        else:
            logger.info("----------------------------")
            logger.info(title)

            Env_Mgr.Instance().set("SAT_NEED_UI",
                {
                    "type":"single_choice", 
                    "title":title,
                    "single_choice":choice_list,
                    'buttonlist': [{'name': '确认', 'color': 'active',   'action': 'POST record_user_input'}]             
                    })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")

                logger.info("User Select:{}\n".format(ui_result))
                return ui_result

_instance = Input_Mgr()

