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

    def int_input(self, title:str, min_val:int=None, max_val:int=None):
        def verify_int(input_str):
            try:
                val = int(input_str)
                if min_val is not None and val < min_val:
                    logger.error(f"Input must be greater than or equal to {min_val}")
                    return False
                if max_val is not None and val > max_val:
                    logger.error(f"Input must be less than or equal to {max_val}")
                    return False
                return True
            except ValueError:
                logger.error("Input must be an integer")
                return False

        run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")
        if run_in_shell:
            while True:
                logger.info("-------------- Please Input Integer --------------")
                logger.info(title)
                range_str = ""
                if min_val is not None and max_val is not None:
                    range_str = f" ({min_val}-{max_val})"
                user_input = self.__shell_color_input(f"Please Input Integer{range_str}:")
                if verify_int(user_input):
                    logger.info("User Input:{}\n".format(user_input))
                    return int(user_input)
        else:
            logger.info("-------------- Please Input Integer --------------")
            Env_Mgr.Instance().set("SAT_NEED_UI", 
                {
                    "type":"int_input", 
                    "title":title,
                    "min": min_val,
                    "max": max_val,
                    'buttonlist': [{'name': '确认', 'color': 'active', 'action': 'POST record_user_input'}]                
                })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")
                
                if verify_int(ui_result):
                    logger.info("User Input:{}\n".format(ui_result))
                    return int(ui_result)

    def multiple_choice(self, title:str, choice_list:list):
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

                user_input = self.__shell_color_input("Please Input Numbers (1-{}) Separated By Spaces:".format(index))
                
                try:
                    # Split input string and convert to integers
                    selected_indices = [int(x) for x in user_input.split()]
                    
                    # Validate all inputs are within range
                    if all(1 <= x <= index for x in selected_indices):
                        selected_items = [choice_list[i-1] for i in selected_indices]
                        logger.debug("User Selected: {}\n".format(", ".join(selected_items)))
                        return selected_items
                    else:
                        logger.error("Some inputs are not in range 1-{}!".format(index))
                except ValueError:
                    logger.error("Invalid input! Please enter numbers separated by spaces.")
                    continue
        else:
            logger.info("----------------------------")
            logger.info(title)

            Env_Mgr.Instance().set("SAT_NEED_UI",
                {
                    "type":"multiple_choice", 
                    "title":title,
                    "multiple_choice":choice_list,
                    'buttonlist': [{'name': '确认', 'color': 'active', 'action': 'POST record_user_input'}]             
                })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")

                logger.info("User Selected:{}\n".format(ui_result))
                return ui_result

    def yes_no_input(self, title:str, default:bool=True):
        """
        Get a yes/no input from the user.
        Args:
            title: The prompt to show to the user
            default: The default value if user just hits enter (True=Yes, False=No)
        Returns:
            bool: True for yes, False for no
        """
        run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")
        if run_in_shell:
            default_text = "[Y/n]" if default else "[y/N]"
            while True:
                logger.info("-------------- Yes/No Question --------------")
                logger.info(title)
                user_input = self.__shell_color_input(f"Please Input {default_text}:").lower()
                
                if user_input == "":
                    logger.info(f"User chose default: {'Yes' if default else 'No'}\n")
                    return default
                elif user_input in ['y', 'yes']:
                    logger.info("User chose: Yes\n")
                    return True
                elif user_input in ['n', 'no']:
                    logger.info("User chose: No\n")
                    return False
                else:
                    logger.error("Invalid input! Please enter Y/N")
        else:
            logger.info("-------------- Yes/No Question --------------")
            logger.info(title)
            
            Env_Mgr.Instance().set("SAT_NEED_UI",
                {
                    "type": "yes_no_input",
                    "title": title,
                    "default": default,
                    'buttonlist': [
                        {'name': '是', 'color': 'active', 'action': 'POST record_user_input'},
                        {'name': '否', 'color': 'negative', 'action': 'POST record_user_input'}
                    ]
                })

            while True:
                time.sleep(0.5)
                ui_result = Env_Mgr.Instance().query("SAT_UI_RESULT", None)
                if ui_result == None:
                    continue
                Env_Mgr.Instance().unset("SAT_UI_RESULT")
                
                result = ui_result == "是"
                logger.info(f"User chose: {'Yes' if result else 'No'}\n")
                return result

_instance = Input_Mgr()
