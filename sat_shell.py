#!/usr/bin/env python
import os
import django
from django.conf import settings
import time
import logging
import cmd2
from cmd2 import ansi

from sat_toolkit.core.plugin_manager import ExploitPluginManager

logger = logging.getLogger(__name__)

class SAT_Shell(cmd2.Cmd):
    intro = '\nWelcome to IoXsploit Shell. Type ' + ansi.style('help', fg=ansi.Fg.YELLOW) + ' or ' + ansi.style('?', fg=ansi.Fg.YELLOW) + ' to list commands.\n'
    prompt = ansi.style('<SAT_SHELL> ', fg=ansi.Fg.BLUE)

    def __init__(self):
        super().__init__()

    def emptyline(self):
        self.onecmd("help")

    @cmd2.with_category('System Commands')
    def do_init(self, arg):
        'Initialize Zeekr SAT System'
        manager = ExploitPluginManager()
        manager.initialize()
        
        # Prompt user for target details
        ip = input(ansi.style("Enter target IP: ", fg=ansi.Fg.GREEN))
        user = input(ansi.style("Enter target username: ", fg=ansi.Fg.GREEN))
        passwd = input(ansi.style("Enter target password: ", fg=ansi.Fg.GREEN))
        cmd = input(ansi.style("Enter command to execute: ", fg=ansi.Fg.GREEN))
        
        target = {
            'ip': ip,
            'user': user,
            'passwd': passwd,
            'cmd': cmd
        }
        
        manager.exploit(target)
    
    @cmd2.with_category('Device Commands')
    def do_device_info(self, arg):
        'Show Zeekr SAT Device Info'
        logger.info("Zeekr SAT Device Info:")
        for key, value in Pi_Mgr.Instance().pi_info().items():
            logger.info("  {}:\t{}".format(key, value))

    @cmd2.with_category('OTA Commands')
    def do_ota_info(self, arg):
        'Show Zeekr SAT Version Info'
        logger.info("Zeekr SAT Version Info:")
        for key, value in OTA_Mgr.Instance().curr_version().items():
            logger.info("  {}:\t{}".format(key, value))

    @cmd2.with_category('Vehicle Commands')
    def do_vehicle_select(self, arg):
        'Select Vehicle Profile'
        select_vehicle_profile = Input_Mgr.Instance().single_choice(
            "Please Select Existing Vehicle Profile",
            Toolkit_Main.Instance().list_vehicle_profiles_to_select()
        )
        logger.info("Vehicle Profile Select Success.")
        Toolkit_Main.Instance().select_vehicle_profile(select_vehicle_profile)

    @cmd2.with_category('Test Commands')
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

    @cmd2.with_category('Test Commands')
    def do_run_test(self, arg):
        'Start Test Project'
        desc = Input_Mgr.Instance().string_input(
            "Please Enter A Description Of This Test",
            None
        )
        Toolkit_Main.Instance().start_audit(desc)

    @cmd2.with_category('Test Commands')
    def do_quick_test(self, arg):
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

    @cmd2.with_category('System Commands')
    def do_exit(self, arg):
        'Exit Zeekr SAT Shell'
        Toolkit_Main.Instance().exit_quick_test()
        Toolkit_Main.Instance().stop_audit()
        logger.info("Zeekr SAT Shell Quit. ByeBye~")
        return True

    @cmd2.with_category('Network Commands')
    def do_connect_lab_wifi(self, arg):
        'Connect Zeekr Lab WiFi'
        logger.info("Connect Zeekr Lab WiFi")
        WiFi_Mgr.Instance().sta_connect_wifi("FHCPE-h6Db-5G", "UybN9Tea")
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

    SAT_Shell().cmdloop()