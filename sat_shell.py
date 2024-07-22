#!/usr/bin/env python
import cmd
import os
import django
from django.conf import settings
import time

import logging
logger = logging.getLogger(__name__)

# import moduls added in main 


class SAT_Shell(cmd.Cmd):
    BLUE = "\033[1;34m"
    RED = "\033[1;31m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"

    intro = '\nWelcome to Zeekr SAT Shell. Type ' + YELLOW +'help' + RESET +' or ' + YELLOW +'?' + RESET + ' to list commands.\n'
    prompt = BLUE + '<SAT_SHELL> ' + RESET

    def emptyline(self):
        self.onecmd("?")

    def do_device_info(self, arg):
        'Show Zeekr SAT Device Info'
        logger.info("Zeekr SAT Device Info:")
        for key, value in Pi_Mgr.Instance().pi_info().items():
            logger.info("  {}:\t{}".format(key, value))
        
        return

    def do_ota_info(self, arg):
        'Show Zeekr SAT Version Info'
        logger.info("Zeekr SAT Version Info:")
        for key, value in OTA_Mgr.Instance().curr_version().items():
            logger.info("  {}:\t{}".format(key, value))

        return

    def do_vehicle_select(self, arg):
        'Select Vehicle Profile'

        select_vehicle_profile = Input_Mgr.Instance().single_choice(
            "Please Select Existing Verhicle Profile",
            Toolkit_Main.Instance().list_vehicle_profiles_to_select()
            )
        logger.info("Vehicle Profile Select Success.")
        Toolkit_Main.Instance().select_vehicle_profile(select_vehicle_profile)
        return

    def do_test_select(self, arg):
        'Select Test Project'

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestLevel",
            Toolkit_Main.Instance().list_test_levels_to_select()
        )
        logger.info("Test Level Select Success.")
        Toolkit_Main.Instance().select_test_level(choice)

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestProject",
            Toolkit_Main.Instance().list_test_projects_to_select()
        )
        logger.info("Test Project Select Success.")
        Toolkit_Main.Instance().select_test_project(choice)
        Report_Mgr.Instance().reset_audit_result()
        return

    def do_run_test(self, org):
        'Start Test Project'
        desc = Input_Mgr.Instance().string_input(
                "Please Enter A Description Of This Test",
                None
            )
        Toolkit_Main.Instance().start_audit(desc)

    def do_quick_test(self, org):
        'Run Test Project In Quick.'

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestLevel",
            Toolkit_Main.Instance().list_test_levels_to_select()
        )
        logger.info("Test Level Select Success.")
        Toolkit_Main.Instance().select_test_level(choice)

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestProject",
            Toolkit_Main.Instance().list_test_projects_to_select()
        )
        logger.info("Test Project Select Success.")
        Toolkit_Main.Instance().quick_test(choice)

    def do_exit(self, arg):
        'Exit Zeekr SAT Shell'

        Toolkit_Main.Instance().exit_quick_test()
        Toolkit_Main.Instance().stop_audit()
        logger.info("Zeekr SAT Shell Quit. ByeBye~")
        return True

    def do_connect_lab_wifi(self, arg):
        'Connect Zeekr Lab WiFi'
        logger.info("Connect Zeekr Lab WiFi")
        WiFi_Mgr.Instance().sta_connect_wifi("FHCPE-h6Db-5G", "UybN9Tea")
        # WiFi_Mgr.Instance().sta_connect_wifi("ASUS_AX68U", "zeekrzero1234")
        time.sleep(2)
        WiFi_Mgr.Instance().status()
        


if __name__ == '__main__':

    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')
        settings.INSTALLED_APPS
        django.setup()        
    except Exception as err:
        logger.exception("Django Init Fail!")

    from sat_toolkit.tools.report_mgr import Report_Mgr
    from sat_toolkit.tools.toolkit_main import Toolkit_Main

    from sat_toolkit.tools.pi_mgr import Pi_Mgr
    from sat_toolkit.tools.ota_mgr import OTA_Mgr
    from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
    from sat_toolkit.tools.input_mgr import Input_Mgr
    from sat_toolkit.tools.env_mgr import Env_Mgr

    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    # WiFi_Mgr.Instance().init_wifi_proxy()

    
    SAT_Shell().cmdloop()