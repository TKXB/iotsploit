#!/usr/bin/env python
import os
import sys
import django
from django.conf import settings
import time
import logging
import cmd2
from cmd2 import ansi
import argparse
import threading
import subprocess

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')
django.setup()

# Now it's safe to import Django-related modules
from django.core.management import execute_from_command_line
from sat_toolkit.core.plugin_manager import ExploitPluginManager
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.toolkit_main import Toolkit_Main
from sat_toolkit.tools.pi_mgr import Pi_Mgr
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

logger = logging.getLogger(__name__)

class SAT_Shell(cmd2.Cmd):
    intro = '\nWelcome to IoXsploit Shell. Type ' + ansi.style('help', fg=ansi.Fg.YELLOW) + ' or ' + ansi.style('?', fg=ansi.Fg.YELLOW) + ' to list commands.\n'
    prompt = ansi.style('<SAT_SHELL> ', fg=ansi.Fg.BLUE)

    def __init__(self):
        super().__init__()
        self.django_server_process = None
        self.django_server_thread = None

    def emptyline(self):
        self.onecmd("help")

    @cmd2.with_category('System Commands')
    def do_init(self, arg):
        'Initialize IotSploit System'
        manager = ExploitPluginManager()
        manager.initialize()
        
        # Load target details from JSON file using Env_Mgr
        env_mgr = Env_Mgr.Instance()
        env_mgr.parse_and_set_env_from_json('conf/target.json')     
        manager.exploit()
    
    @cmd2.with_category('Device Commands')
    def do_device_info(self, arg):
        'Show Zeekr SAT Device Info'
        logger.info(ansi.style("Zeekr SAT Device Info:", fg=ansi.Fg.CYAN))
        for key, value in Pi_Mgr.Instance().pi_info().items():
            logger.info(ansi.style(f"  {key}:\t{value}", fg=ansi.Fg.CYAN))

    @cmd2.with_category('OTA Commands')
    def do_ota_info(self, arg):
        'Show Zeekr SAT Version Info'
        logger.info(ansi.style("Zeekr SAT Version Info:", fg=ansi.Fg.CYAN))
        for key, value in OTA_Mgr.Instance().curr_version().items():
            logger.info(ansi.style(f"  {key}:\t{value}", fg=ansi.Fg.CYAN))

    @cmd2.with_category('Vehicle Commands')
    def do_vehicle_select(self, arg):
        'Select Vehicle Profile'
        select_vehicle_profile = Input_Mgr.Instance().single_choice(
            "Please Select Existing Vehicle Profile",
            Toolkit_Main.Instance().list_vehicle_profiles_to_select()
        )
        logger.info(ansi.style("Vehicle Profile Select Success.", fg=ansi.Fg.GREEN))
        Toolkit_Main.Instance().select_vehicle_profile(select_vehicle_profile)

    @cmd2.with_category('Test Commands')
    def do_test_select(self, arg):
        'Select Test Project'
        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestLevel",
            Toolkit_Main.Instance().list_test_levels_to_select()
        )
        logger.info(ansi.style("Test Level Select Success.", fg=ansi.Fg.GREEN))
        Toolkit_Main.Instance().select_test_level(choice)

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestProject",
            Toolkit_Main.Instance().list_test_projects_to_select()
        )
        logger.info(ansi.style("Test Project Select Success.", fg=ansi.Fg.GREEN))
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
        logger.info(ansi.style("Test Level Select Success.", fg=ansi.Fg.GREEN))
        Toolkit_Main.Instance().select_test_level(choice)

        choice = Input_Mgr.Instance().single_choice(
            "Please Select TestProject",
            Toolkit_Main.Instance().list_test_projects_to_select()
        )
        logger.info(ansi.style("Test Project Select Success.", fg=ansi.Fg.GREEN))
        Toolkit_Main.Instance().quick_test(choice)

    @cmd2.with_category('System Commands')
    def do_exit(self, arg):
        'Exit Zeekr SAT Shell'
        if self.django_server_process:
            self.do_stop_server(arg)
        Toolkit_Main.Instance().exit_quick_test()
        Toolkit_Main.Instance().stop_audit()
        logger.info(ansi.style("Zeekr SAT Shell Quit. ByeBye~", fg=ansi.Fg.RED))
        return True

    @cmd2.with_category('Network Commands')
    def do_connect_lab_wifi(self, arg):
        'Connect Zeekr Lab WiFi'
        logger.info(ansi.style("Connect Zeekr Lab WiFi", fg=ansi.Fg.CYAN))
        WiFi_Mgr.Instance().sta_connect_wifi("FHCPE-h6Db-5G", "UybN9Tea")
        time.sleep(2)
        WiFi_Mgr.Instance().status()

    @cmd2.with_category('Django Commands')
    def do_runserver(self, arg):
        'Start the Django development server in the background'
        if self.django_server_process:
            self.poutput("Django server is already running.")
            return

        try:
            logger.info("Attempting to start Django development server in background...")
            
            # Prepare the command
            cmd = [sys.executable, 'manage.py', 'runserver', '--noreload']
            if arg:
                cmd.extend(arg.split())
            
            logger.info(f"Running Django command: {' '.join(cmd)}")
            
            # Start the Django server as a subprocess
            self.django_server_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            
            # Start a thread to read the output
            self.django_server_thread = threading.Thread(target=self._read_django_output, daemon=True)
            self.django_server_thread.start()
            
            logger.info("Django development server started successfully in the background.")
            self.poutput("Django server is now running in the background. Use 'stop_server' to stop it.")
        except Exception as e:
            logger.error(f"Failed to start Django server: {str(e)}")
            logger.exception("Detailed traceback:")

    def _read_django_output(self):
        for line in self.django_server_process.stdout:
            logger.info(f"Django: {line.strip()}")

    @cmd2.with_category('Django Commands')
    def do_stop_server(self, arg):
        'Stop the Django development server'
        if self.django_server_process:
            self.django_server_process.terminate()
            self.django_server_process = None
            self.django_server_thread = None
            logger.info("Django server stopped.")
            self.poutput("Django server has been stopped.")
        else:
            self.poutput("No Django server is currently running.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start the SAT Shell.')
    parser.add_argument('--log-level', default='INFO', help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), None))

    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    SAT_Shell().cmdloop()