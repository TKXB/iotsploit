#!/usr/bin/env python
import os
import sys
import django
import time
import logging
import cmd2
from cmd2 import ansi
import threading
import subprocess
from sat_toolkit.models.Target_Model import TargetManager, Vehicle
import colorlog
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.core.exploit_spec import ExploitResult
from sat_toolkit.core.device_manager import DevicePluginManager  
from sat_toolkit.models.Device_Model import DeviceManager, DeviceType, SerialDevice, USBDevice

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')
django.setup()

# Now it's safe to import Django-related modules
from django.core.management import execute_from_command_line
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.toolkit_main import Toolkit_Main
from sat_toolkit.tools.monitor_mgr import SystemMonitor
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr

logger = logging.getLogger(__name__)

def global_exception_handler(exctype, value, traceback):
    logger.error("Unhandled exception", exc_info=(exctype, value, traceback))

sys.excepthook = global_exception_handler

class SAT_Shell(cmd2.Cmd):
    intro = ansi.style('''
██╗ █████╗ ████████╗███████╗██████╗ ██╗      ██████╗ ██╗████████╗
██║██╔═══██╗╚══██╔══╝██╔════╝██╔══██╗██║     ██╔═══██╗██║╚══██╔══╝
██║██║   ██║   ██║   ███████╗██████╔╝██║     ██║   ██║██║   ██║   
██║██║   ██║   ██║   ╚════██║██╔═══╝ ██║     ██║   ██║██║   ██║   
██║╚██████╔╝   ██║   ███████║██║     ███████╗╚██████╔╝██║   ██║   
╚═╝ ╚═════╝    ╚═╝   ╚══════╝╚═╝     ╚══════╝ ╚═════╝ ╚═╝   ╚═╝   
''', fg=ansi.Fg.GREEN) + '\n' + ansi.style('Welcome to IoTSploit Shell. Type help or ? to list commands.\n', fg=ansi.Fg.YELLOW)

    prompt = ansi.style('<IoX_SHELL> ', fg=ansi.Fg.BLUE)

    def __init__(self):
        # Initialize the command categories dictionary before calling super().__init__()
        self._cmd_to_category = {}
        
        # Now call the parent class initialization
        super().__init__()
        
        # Rest of your initialization code...
        self.django_server_process = None
        self.django_server_thread = None
        self.daphne_server_process = None
        self.daphne_server_thread = None
        self.setup_colored_logger()
        
        # Initialize plugin manager
        self.plugin_manager = ExploitPluginManager()
        self.plugin_manager.initialize()
        
        # Initialize target manager
        self.target_manager = TargetManager.get_instance()
        self.target_manager.register_target("vehicle", Vehicle)
        self.target_manager.parse_and_set_target_from_json('conf/target.json')

        # Initialize device manager
        self.device_manager = DeviceManager.get_instance()
        self.device_manager.register_device(DeviceType.Serial, SerialDevice)
        self.device_manager.register_device(DeviceType.USB, USBDevice)
        self.device_manager.parse_and_set_device_from_json('conf/devices.json')

        # Initialize device plugin manager (if still needed)
        self.device_plugin_manager = DevicePluginManager()

        # Customize help display
        self.help_category_header = ansi.style("\n{:-^80}\n", fg=ansi.Fg.BLUE)
        self.help_category_footer = "\n"
        
        # Group all commands under Shell Commands
        self._cmd_to_category.update({
            'alias': 'Shell Commands',
            'connect_lab_wifi': 'Shell Commands',
            'device_info': 'Shell Commands',
            'edit': 'Shell Commands',
            'execute_plugin': 'Shell Commands',
            'exit': 'Shell Commands',
            'exploit': 'Shell Commands',
            'help': 'Shell Commands',
            'history': 'Shell Commands',
            'list_device_drivers': 'Shell Commands',
            'list_devices': 'Shell Commands',
            'list_plugins': 'Shell Commands',
            'list_targets': 'Shell Commands',
            'ls': 'Shell Commands',
            'lsdev': 'Shell Commands',
            'lsdrv': 'Shell Commands',
            'lsp': 'Shell Commands',
            'lst': 'Shell Commands',
            'lsusb': 'Shell Commands',
            'macro': 'Shell Commands',
            'ota_info': 'Shell Commands',
            'quick_test': 'Shell Commands',
            'quit': 'Shell Commands',
            'run_pyscript': 'Shell Commands',
            'run_script': 'Shell Commands',
            'run_test': 'Shell Commands',
            'runserver': 'Shell Commands',
            'set': 'Shell Commands',
            'set_log_level': 'Shell Commands',
            'shell': 'Shell Commands',
            'shortcuts': 'Shell Commands',
            'stop_server': 'Shell Commands',
            'test_select': 'Shell Commands',
            'vehicle_select': 'Shell Commands'
        })

    def setup_colored_logger(self):
        root_logger = logging.getLogger()
        if root_logger.handlers:
            for handler in root_logger.handlers:
                root_logger.removeHandler(handler)
        
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    def emptyline(self):
        self.onecmd("help")

    @cmd2.with_category('System Commands')
    def do_exploit(self, arg):
        'Execute all plugins in the IotSploit System'
        logger.info(ansi.style("Executing all plugins in the IotSploit System", fg=ansi.Fg.CYAN))
        
        results = self.plugin_manager.exploit()
        
        if not results:
            logger.warning(ansi.style("No results returned from any plugins", fg=ansi.Fg.YELLOW))
        else:
            # Log the results
            for plugin_name, result in results.items():
                if result is None:
                    logger.warning(ansi.style(f"Plugin {plugin_name} returned no result", fg=ansi.Fg.YELLOW))
                elif isinstance(result, ExploitResult):
                    logger.info(ansi.style(f"Plugin {plugin_name} execution result:", fg=ansi.Fg.GREEN))
                    logger.info(f"Success: {result.success}")
                    logger.info(f"Message: {result.message}")
                    logger.info(f"Data: {result.data}")
                else:
                    logger.info(ansi.style(f"Plugin {plugin_name} execution result:", fg=ansi.Fg.GREEN))
                    logger.info(str(result))
        
        logger.info(ansi.style("Exploit execution completed", fg=ansi.Fg.CYAN))

    @cmd2.with_category('Device Commands')
    def do_device_info(self, arg):
        'Show Zeekr SAT Device Info'
        logger.info(ansi.style("Zeekr SAT Device Info:", fg=ansi.Fg.CYAN))
        
        pi_monitor = SystemMonitor.create_monitor("raspberry_pi")
        device_info = SystemMonitor.monitor_device(pi_monitor)
        
        for key, value in device_info.items():
            if isinstance(value, dict):
                logger.info(ansi.style(f"  {key}:", fg=ansi.Fg.CYAN))
                for sub_key, sub_value in value.items():
                    logger.info(ansi.style(f"    {sub_key}: {sub_value}", fg=ansi.Fg.CYAN))
            else:
                logger.info(ansi.style(f"  {key}: {value}", fg=ansi.Fg.CYAN))

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
        logger.info("IotSploit Shell Quit. ByeBye~")
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
        'Start the Django development server and Daphne WebSocket server in the background'
        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            logger.info("Attempting to start Django and Daphne servers in background...")
            
            # Prepare the Django command
            django_cmd = [sys.executable, 'manage.py', 'runserver', '--noreload', '0.0.0.0:8888']
            
            # Prepare the Daphne command - modified to listen on 0.0.0.0
            daphne_cmd = ['daphne', '-b', '0.0.0.0', '-p', '9999', 'sat_django_entry.asgi:application']
            
            logger.info(f"Running Django command: {' '.join(django_cmd)}")
            logger.info(f"Running Daphne command: {' '.join(daphne_cmd)}")
            
            # Start the Django server as a subprocess
            self.django_server_process = subprocess.Popen(django_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            
            # Start the Daphne server as a subprocess
            self.daphne_server_process = subprocess.Popen(daphne_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            
            # Start threads to read the output
            self.django_server_thread = threading.Thread(target=self._read_server_output, args=(self.django_server_process, "Django"), daemon=True)
            self.django_server_thread.start()
            
            self.daphne_server_thread = threading.Thread(target=self._read_server_output, args=(self.daphne_server_process, "Daphne"), daemon=True)
            self.daphne_server_thread.start()
            
            logger.info("Django and Daphne servers started successfully in the background.")
            self.poutput("Servers are now running in the background. Use 'stop_server' to stop them.")
        except Exception as e:
            logger.error(f"Failed to start servers: {str(e)}")
            logger.exception("Detailed traceback:")

    def _read_server_output(self, process, server_name):
        for line in process.stdout:
            logger.info(f"{server_name}: {line.strip()}")

    @cmd2.with_category('Django Commands')
    def do_stop_server(self, arg):
        'Stop the Django development server and Daphne WebSocket server'
        if self.django_server_process:
            self.django_server_process.terminate()
            self.django_server_process = None
            self.django_server_thread = None
        
        if self.daphne_server_process:
            self.daphne_server_process.terminate()
            self.daphne_server_process = None
            self.daphne_server_thread = None
        
        if not self.django_server_process and not self.daphne_server_process:
            logger.info("All servers stopped.")
            self.poutput("All servers have been stopped.")
        else:
            self.poutput("No servers were running.")

    @cmd2.with_category('System Commands')
    def do_set_log_level(self, arg):
        'Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)'
        levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if arg.upper() not in levels:
            self.poutput(f"Invalid log level. Choose from: {', '.join(levels)}")
            return

        level = getattr(logging, arg.upper())
        logging.getLogger().setLevel(level)
        Report_Mgr.Instance().set_log_level(level)
        self.poutput(f"Log level set to {arg.upper()}")

    @cmd2.with_category('Plugin Commands')
    def do_list_plugins(self, arg):
        'List all available plugins'
        plugins = self.plugin_manager.list_plugins()
        
        if plugins:
            logger.info(ansi.style("Available plugins:", fg=ansi.Fg.CYAN))
            for plugin in plugins:
                logger.info(ansi.style(f"  - {plugin}", fg=ansi.Fg.CYAN))
        else:
            logger.info(ansi.style("No plugins available.", fg=ansi.Fg.YELLOW))
    do_lsp = do_list_plugins

    @cmd2.with_category('Plugin Commands')
    def do_execute_plugin(self, arg):
        'Execute a specific plugin'
        plugins = self.plugin_manager.list_plugins()
        
        if not plugins:
            logger.info(ansi.style("No plugins available to execute.", fg=ansi.Fg.YELLOW))
            return

        if not arg:
            choice = Input_Mgr.Instance().single_choice(
                "Please select a plugin to execute",
                plugins
            )
        else:
            choice = arg

        if choice not in plugins:
            logger.error(ansi.style(f"Plugin '{choice}' not found.", fg=ansi.Fg.RED))
            return

        logger.info(ansi.style(f"Executing plugin: {choice}", fg=ansi.Fg.CYAN))
        try:
            result = self.plugin_manager.execute_plugin(choice)
            if isinstance(result, ExploitResult):
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(f"Success: {result.success}")
                logger.info(f"Message: {result.message}")
                logger.info(f"Data: {result.data}")
            else:
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(str(result))
        except Exception as e:
            logger.error(ansi.style(f"Error executing plugin: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Device Commands')
    def do_list_device_drivers(self, arg):
        'List all available device plugins'
        available_devices = self.device_plugin_manager.list_devices()
        if available_devices:
            logger.info(ansi.style("Available device plugins:", fg=ansi.Fg.CYAN))
            for device in available_devices:
                logger.info(ansi.style(f"  - {device}", fg=ansi.Fg.CYAN))
        else:
            logger.info(ansi.style("No device plugins available.", fg=ansi.Fg.YELLOW))

    do_lsdrv = do_list_device_drivers

    @cmd2.with_category('Linux Commands')
    def do_ls(self, arg):
        'List directory contents'
        try:
            result = subprocess.run(['ls'] + arg.split(), capture_output=True, text=True)
            self.poutput(result.stdout)
            if result.stderr:
                self.poutput(result.stderr)
        except Exception as e:
            logger.error(f"Error executing ls: {str(e)}")

    @cmd2.with_category('Linux Commands')
    def do_lsusb(self, arg):
        'List USB devices'
        try:
            result = subprocess.run(['lsusb'] + arg.split(), capture_output=True, text=True)
            self.poutput(result.stdout)
            if result.stderr:
                self.poutput(result.stderr)
        except Exception as e:
            logger.error(f"Error executing lsusb: {str(e)}")

    @cmd2.with_category('Target Commands')
    def do_list_targets(self, arg):
        'List all targets stored in the database'
        try:
            targets = self.target_manager.get_all_targets()
            
            if not targets:
                logger.info(ansi.style("No targets found in the database.", fg=ansi.Fg.YELLOW))
                return

            logger.info(ansi.style("Targets in the database:", fg=ansi.Fg.CYAN))
            for target in targets:
                logger.info(ansi.style(f"  - ID: {target['target_id']}", fg=ansi.Fg.GREEN))
                logger.info(f"    Name: {target['name']}")
                logger.info(f"    Type: {target['type']}")
                logger.info(f"    Status: {target['status']}")
                
                if target['type'] == 'vehicle':
                    logger.info(f"    IP Address: {target.get('ip_address', 'N/A')}")
                    logger.info(f"    Location: {target.get('location', 'N/A')}")
                
                logger.info(f"    Properties: {target['properties']}")
                logger.info("    ---")

        except Exception as e:
            logger.error(ansi.style(f"Error listing targets: {str(e)}", fg=ansi.Fg.RED))

    # Alias for list_targets
    do_lst = do_list_targets

    @cmd2.with_category('Device Commands')
    def do_list_devices(self, arg):
        'List all devices stored in the database'
        try:
            devices = self.device_manager.get_all_devices()
            
            if not devices:
                logger.info(ansi.style("No devices found in the database.", fg=ansi.Fg.YELLOW))
                return

            logger.info(ansi.style("Devices in the database:", fg=ansi.Fg.CYAN))
            for device in devices:
                logger.info(ansi.style(f"  - ID: {device['device_id']}", fg=ansi.Fg.GREEN))
                logger.info(f"    Name: {device['name']}")
                logger.info(f"    Type: {device['device_type']}")
                
                if device['device_type'] == 'Serial':
                    logger.info(f"    Port: {device['attributes'].get('port', 'N/A')}")
                    logger.info(f"    Baud Rate: {device['attributes'].get('baud_rate', 'N/A')}")
                elif device['device_type'] == 'USB':
                    logger.info(f"    Vendor ID: {device['attributes'].get('vendor_id', 'N/A')}")
                    logger.info(f"    Product ID: {device['attributes'].get('product_id', 'N/A')}")
                
                logger.info(f"    Attributes: {device['attributes']}")
                logger.info("    ---")

        except Exception as e:
            logger.error(ansi.style(f"Error listing devices: {str(e)}", fg=ansi.Fg.RED))

    # Alias for list_devices
    do_lsdev = do_list_devices

    def do_help(self, arg):
        'List available commands with "help" or detailed help with "help cmd".'
        if arg:
            # Show help for specific command
            super().do_help(arg)
            return

        # Custom help display for command listing
        self.poutput(ansi.style("\nAvailable Commands:", fg=ansi.Fg.GREEN, bold=True))
        self.poutput(ansi.style("Use 'help <command>' for detailed information about a command.\n", fg=ansi.Fg.YELLOW))

        # Get commands by category
        cmds_by_category = self.get_all_commands_by_category()
        
        # Sort categories for consistent display, but put Shell Commands last
        categories = sorted([cat for cat in cmds_by_category.keys() if cat != 'Shell Commands'])
        if 'Shell Commands' in cmds_by_category:
            categories.append('Shell Commands')
        
        # Print commands by category
        for category in categories:
            if category == 'Uncategorized':
                continue  # Skip uncategorized commands
            
            self.poutput(self.help_category_header.format(f" {category} "))
            cmd_list = sorted(cmds_by_category[category])
            
            # Calculate the maximum command length for proper alignment
            max_cmd_length = max(len(cmd) for cmd in cmd_list) + 2
            
            for cmd in cmd_list:
                doc = self.get_command_doc(cmd)
                # Pad the command name to align all descriptions
                padded_cmd = f"  {cmd:<{max_cmd_length}}"
                self.poutput(ansi.style(padded_cmd, fg=ansi.Fg.CYAN) + 
                            ansi.style(f"- {doc}", fg=ansi.Fg.WHITE))
            self.poutput(self.help_category_footer)

        # Show command count
        total_commands = sum(len(cmds) for cat, cmds in cmds_by_category.items() if cat != 'Uncategorized')
        self.poutput(ansi.style(f"\nTotal commands: {total_commands}", fg=ansi.Fg.GREEN))

    def get_command_doc(self, cmd_name):
        """Get the first line of the command's docstring."""
        cmd_func = getattr(self, 'do_' + cmd_name, None)
        if cmd_func and cmd_func.__doc__:
            return cmd_func.__doc__.split('\n')[0]
        return ''

    def get_all_commands_by_category(self):
        """Return a dict mapping category names to lists of command names."""
        categories = {}
        
        # Get all command names (methods starting with 'do_')
        command_names = [attr[3:] for attr in dir(self) if attr.startswith('do_')]
        
        for cmd_name in command_names:
            # Get the command function
            cmd_func = getattr(self, 'do_' + cmd_name)
            
            # Get category from cmd2's category decorator or from our manual mapping
            if hasattr(cmd_func, 'category'):
                category = cmd_func.category
            else:
                # Check our manual mapping or default to 'Uncategorized'
                category = self._cmd_to_category.get(cmd_name, 'Uncategorized')
            
            # Add command to appropriate category list
            if category not in categories:
                categories[category] = []
            categories[category].append(cmd_name)
        
        return categories

if __name__ == '__main__':
    shell = SAT_Shell()
    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    shell.cmdloop()

