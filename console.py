#!/usr/bin/env python
import os
import sys
import logging
import colorlog

# Set up Django settings first, before any Django-related imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')

import django
django.setup()

# Now it's safe to import Django and other modules
import cmd2
from cmd2 import ansi
import threading
import subprocess
from sat_toolkit.models.Target_Model import TargetManager, Vehicle
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.core.exploit_spec import ExploitResult
from sat_toolkit.core.device_manager import DevicePluginManager  
from sat_toolkit.models.Device_Model import DeviceManager, DeviceType, SerialDevice, USBDevice
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.toolkit_main import Toolkit_Main
from sat_toolkit.tools.monitor_mgr import SystemMonitor
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.models.Plugin_Model import Plugin
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree
from sat_toolkit.core.device_manager import DevicePluginManager
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.models.Device_Model import Device

logger = logging.getLogger(__name__)

def global_exception_handler(exctype, value, traceback):
    logger.error("Unhandled exception", exc_info=(exctype, value, traceback))

sys.excepthook = global_exception_handler

class SAT_Shell(cmd2.Cmd):
    intro = ansi.style('''
██╗  █████╗ ████████╗███████╗██████╗ ██╗      ██████╗ ██╗████████╗
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
        self.celery_worker_process = None
        self.celery_worker_thread = None
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
            'exec': 'Shell Commands',
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
        'Start Django development server, Daphne WebSocket server, and Celery worker in the background'
        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            logger.info("Attempting to start Django, Daphne, and Celery servers in background...")
            
            # Prepare the Django command
            django_cmd = [sys.executable, 'manage.py', 'runserver', '--noreload', '0.0.0.0:8888']
            
            # Prepare the Daphne command
            daphne_cmd = [
                sys.executable, 
                '-m', 
                'daphne', 
                '-b', 
                '0.0.0.0', 
                '-p', 
                '9999', 
                'sat_django_entry.asgi:application'
            ]
            
            # Prepare the Celery command
            celery_cmd = [
                sys.executable,
                '-m',
                'celery',
                '-A',
                'sat_toolkit',
                'worker',
                '--loglevel=info'
            ]
            
            logger.info(f"Running Django command: {' '.join(django_cmd)}")
            logger.info(f"Running Daphne command: {' '.join(daphne_cmd)}")
            logger.info(f"Running Celery command: {' '.join(celery_cmd)}")
            
            # Start the Django server as a subprocess
            self.django_server_process = subprocess.Popen(
                django_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                universal_newlines=True
            )
            
            # Start the Daphne server as a subprocess
            self.daphne_server_process = subprocess.Popen(
                daphne_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                universal_newlines=True
            )
            
            # Start the Celery worker as a subprocess
            self.celery_worker_process = subprocess.Popen(
                celery_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Start threads to read the output
            self.django_server_thread = threading.Thread(
                target=self._read_server_output, 
                args=(self.django_server_process, "Django"), 
                daemon=True
            )
            self.django_server_thread.start()
            
            self.daphne_server_thread = threading.Thread(
                target=self._read_server_output, 
                args=(self.daphne_server_process, "Daphne"), 
                daemon=True
            )
            self.daphne_server_thread.start()
            
            self.celery_worker_thread = threading.Thread(
                target=self._read_server_output,
                args=(self.celery_worker_process, "Celery"),
                daemon=True
            )
            self.celery_worker_thread.start()
            
            logger.info("All servers started successfully in the background.")
        except Exception as e:
            logger.error(f"Failed to start servers: {str(e)}")
            logger.exception("Detailed traceback:")

    def _read_server_output(self, process, server_name):
        for line in process.stdout:
            logger.info(f"{server_name}: {line.strip()}")

    @cmd2.with_category('Django Commands')
    def do_stop_server(self, arg):
        'Stop Django development server, Daphne WebSocket server, and Celery worker'
        if self.django_server_process:
            self.django_server_process.terminate()
            self.django_server_process = None
            self.django_server_thread = None
        
        if self.daphne_server_process:
            self.daphne_server_process.terminate()
            self.daphne_server_process = None
            self.daphne_server_thread = None
        
        if hasattr(self, 'celery_worker_process') and self.celery_worker_process:
            self.celery_worker_process.terminate()
            self.celery_worker_process = None
            self.celery_worker_thread = None
        
        if not any([self.django_server_process, self.daphne_server_process, 
                    getattr(self, 'celery_worker_process', None)]):
            logger.info("All servers stopped.")
        else:
            logger.error("No servers were running.")

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
    do_exec = do_execute_plugin

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

    @cmd2.with_category('Target Commands')
    def do_target_select(self, arg):
        'Select a target from available targets'
        try:
            targets = self.target_manager.get_all_targets()
            
            if not targets:
                logger.info(ansi.style("No targets found in the database.", fg=ansi.Fg.YELLOW))
                return

            # Create list of target choices for display
            target_choices = [f"{t['name']} ({t['ip_address']})" for t in targets if t.get('ip_address')]
            
            # Use Input_Mgr for target selection
            selected_choice = Input_Mgr.Instance().single_choice(
                "Select target for operation:",
                target_choices
            )
            
            # Find the index of the selected choice
            selected_index = target_choices.index(selected_choice)
            
            # Convert the selected target dictionary to a Vehicle instance using create_target_instance
            selected_target_dict = targets[selected_index]
            selected_target = self.target_manager.create_target_instance(selected_target_dict)
            
            # Set the selected target as current
            self.target_manager.set_current_target(selected_target)
            
            logger.info(ansi.style(f"Selected target: {selected_target.name}", fg=ansi.Fg.GREEN))

        except Exception as e:
            logger.error(ansi.style(f"Error selecting target: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Plugin Commands')
    def do_flash_plugins(self, arg):
        'Refresh and reload all plugins from the plugins directory'
        try:
            logger.info(ansi.style("Starting plugin refresh...", fg=ansi.Fg.CYAN))
            
            # Get current plugin count
            initial_plugins = len(self.plugin_manager.list_plugins())
            
            # Run auto-discovery
            self.plugin_manager.auto_discover_plugins()
            
            # Get new plugin count
            final_plugins = len(self.plugin_manager.list_plugins())
            
            # Calculate changes
            if final_plugins > initial_plugins:
                logger.info(ansi.style(
                    f"Plugin refresh complete! Added {final_plugins - initial_plugins} new plugins.", 
                    fg=ansi.Fg.GREEN
                ))
            elif final_plugins < initial_plugins:
                logger.info(ansi.style(
                    f"Plugin refresh complete! Removed {initial_plugins - final_plugins} plugins.", 
                    fg=ansi.Fg.YELLOW
                ))
            else:
                logger.info(ansi.style(
                    "Plugin refresh complete! No changes detected.", 
                    fg=ansi.Fg.CYAN
                ))
            
            # Display current plugins
            logger.info(ansi.style("\nCurrent plugins:", fg=ansi.Fg.CYAN))
            for plugin in self.plugin_manager.list_plugins():
                logger.info(ansi.style(f"  - {plugin}", fg=ansi.Fg.CYAN))
                
        except Exception as e:
            logger.error(ansi.style(f"Error refreshing plugins: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for the flash_plugins command
    do_fp = do_flash_plugins

    @cmd2.with_category('Plugin Commands')
    def do_create_group(self, arg):
        'Create a plugin group and add selected plugins to it'
        try:
            # Get group name and description from user
            group_name = Input_Mgr.Instance().string_input(
                "Enter group name",
                None
            )
            
            group_description = Input_Mgr.Instance().string_input(
                "Enter group description (optional)",
                None
            )
                        
            # Create the plugin group
            group, created = PluginGroup.objects.get_or_create(
                name=group_name,
                defaults={
                    'description': group_description,
                    'enabled': True
                }
            )
            
            if not created:
                logger.warning(ansi.style(f"Group '{group_name}' already exists.", fg=ansi.Fg.YELLOW))
                overwrite = Input_Mgr.Instance().yes_no_input("Do you want to update it?", False)
                if not overwrite:
                    return
                group.description = group_description
                group.save()
            
            # Get available plugins
            available_plugins = self.plugin_manager.list_plugins()
            if not available_plugins:
                logger.warning(ansi.style("No plugins available to add to the group.", fg=ansi.Fg.YELLOW))
                return
            
            # Let user select multiple plugins
            selected_plugins = Input_Mgr.Instance().multiple_choice(
                "Select plugins to add to the group (space-separated numbers)",
                available_plugins
            )
            
            # Add selected plugins to the group
            for plugin_name in selected_plugins:
                plugin, created = Plugin.objects.get_or_create(
                    name=plugin_name,
                    defaults={
                        'description': f'Plugin {plugin_name}',
                        'enabled': True,
                        'module_path': f'plugins.exploits.{plugin_name}'
                    }
                )
                group.plugins.add(plugin)
            
            # Optionally nest this group under another group
            nest_group = Input_Mgr.Instance().yes_no_input("Do you want to nest this group under another group?", False)
            if nest_group:
                # Get available groups excluding the current one
                available_groups = [g.name for g in PluginGroup.objects.exclude(id=group.id)]
                if available_groups:
                    parent_group_name = Input_Mgr.Instance().single_choice(
                        "Select parent group",
                        available_groups
                    )
                    parent_group = PluginGroup.objects.get(name=parent_group_name)
                    force_exec = Input_Mgr.Instance().yes_no_input("Force execution of this group?", True)
                    
                    PluginGroupTree.objects.get_or_create(
                        parent=parent_group,
                        child=group,
                        defaults={'force_exec': force_exec}
                    )
            
            logger.info(ansi.style(f"Successfully created group '{group_name}' with {len(selected_plugins)} plugins", fg=ansi.Fg.GREEN))
            
            # Show group details
            group.detail()
            
        except Exception as e:
            logger.error(ansi.style(f"Error creating plugin group: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for create_group
    do_cg = do_create_group

    @cmd2.with_category('Plugin Commands')
    def do_execute_group(self, arg):
        'Execute plugins in a selected group'
        try:
            # Get all plugin groups
            groups = PluginGroup.objects.filter(enabled=True)
            
            if not groups.exists():
                logger.warning(ansi.style("No plugin groups available.", fg=ansi.Fg.YELLOW))
                return

            # Create list of group choices
            group_choices = [f"{group.name} - {group.description}" for group in groups]
            
            # Let user select a group
            selected = Input_Mgr.Instance().single_choice(
                "Select plugin group to execute",
                group_choices
            )
            
            # Extract group name from selection (remove description)
            group_name = selected.split(" - ")[0]
            
            # Confirm execution
            if Input_Mgr.Instance().yes_no_input(
                f"Are you sure you want to execute group '{group_name}'?",
                default=True
            ):
                logger.info(ansi.style(f"Executing plugin group: {group_name}", fg=ansi.Fg.CYAN))
                
                # Execute the group
                result = self.plugin_manager.execute_plugin_group(group_name)
                
                if result:
                    logger.info(ansi.style("Plugin group execution completed successfully", fg=ansi.Fg.GREEN))
                else:
                    logger.warning(ansi.style("Plugin group execution completed with some failures", fg=ansi.Fg.YELLOW))
            else:
                logger.info(ansi.style("Group execution cancelled", fg=ansi.Fg.YELLOW))

        except Exception as e:
            logger.error(ansi.style(f"Error executing plugin group: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for execute_group
    do_eg = do_execute_group

    @cmd2.with_category('Plugin Commands')
    def do_list_groups(self, arg):
        'List all available plugin groups'
        try:
            groups = PluginGroup.objects.all()
            
            if not groups.exists():
                logger.info(ansi.style("No plugin groups available.", fg=ansi.Fg.YELLOW))
                return

            logger.info(ansi.style("\nAvailable plugin groups:", fg=ansi.Fg.CYAN))
            for group in groups:
                enabled_status = ansi.style("Enabled", fg=ansi.Fg.GREEN) if group.enabled else ansi.style("Disabled", fg=ansi.Fg.RED)
                logger.info(ansi.style(f"\nGroup: {group.name} [{enabled_status}]", fg=ansi.Fg.CYAN))
                if group.description:
                    logger.info(f"Description: {group.description}")
                
                # List plugins in this group
                plugins = group.plugins.all()
                if plugins.exists():
                    logger.info("Plugins:")
                    for plugin in plugins:
                        plugin_status = ansi.style("✓", fg=ansi.Fg.GREEN) if plugin.enabled else ansi.style("✗", fg=ansi.Fg.RED)
                        logger.info(f"  - {plugin.name} [{plugin_status}]")
                else:
                    logger.info("  No plugins in this group")

                # Show parent/child relationships if any
                try:
                    parent_relations = PluginGroupTree.objects.filter(child=group)
                    child_relations = PluginGroupTree.objects.filter(parent=group)
                    
                    if parent_relations.exists():
                        logger.info("Parent Groups:")
                        for relation in parent_relations:
                            force_exec = "(Force Execute)" if relation.force_exec else ""
                            logger.info(f"  - {relation.parent.name} {force_exec}")
                    
                    if child_relations.exists():
                        logger.info("Child Groups:")
                        for relation in child_relations:
                            force_exec = "(Force Execute)" if relation.force_exec else ""
                            logger.info(f"  - {relation.child.name} {force_exec}")
                except Exception as e:
                    logger.debug(f"Error getting group relationships: {str(e)}")

            logger.info("\n")  # Add blank line at end

        except Exception as e:
            logger.error(ansi.style(f"Error listing plugin groups: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for list_groups
    do_lg = do_list_groups

    @cmd2.with_category('Target Commands')
    def do_edit_target(self, arg):
        'Edit an existing target in the database'
        try:
            # Get all targets
            targets = self.target_manager.get_all_targets()
            if not targets:
                logger.warning(ansi.style("No targets available to edit.", fg=ansi.Fg.YELLOW))
                return

            # Create list of target choices
            target_choices = [f"{t['name']} ({t['target_id']})" for t in targets]
            
            # Let user select a target
            selected = Input_Mgr.Instance().single_choice(
                "Select target to edit",
                target_choices
            )
            
            # Get target ID from selection
            target_id = selected.split('(')[1].split(')')[0]
            target = next(t for t in targets if t['target_id'] == target_id)
            
            # Fields that can be edited
            editable_fields = {
                'name': str,
                'status': str,
                'ip_address': str,
                'location': str
            }
            
            # Let user select which field to edit
            field_choices = list(editable_fields.keys()) + ['properties']
            field = Input_Mgr.Instance().single_choice(
                "Select field to edit",
                field_choices
            )
            
            if field == 'properties':
                # Handle properties editing
                print("\nCurrent properties:")
                for key, value in target['properties'].items():
                    print(f"{key}: {value}")
                
                # Let user choose to add/edit/delete property
                action = Input_Mgr.Instance().single_choice(
                    "Select action",
                    ['Add property', 'Edit property', 'Delete property']
                )
                
                if action == 'Add property':
                    key = Input_Mgr.Instance().string_input("Enter property name")
                    value = Input_Mgr.Instance().string_input("Enter property value")
                    target['properties'][key] = value
                
                elif action == 'Edit property':
                    if not target['properties']:
                        logger.warning(ansi.style("No properties to edit.", fg=ansi.Fg.YELLOW))
                        return
                    prop_key = Input_Mgr.Instance().single_choice(
                        "Select property to edit",
                        list(target['properties'].keys())
                    )
                    new_value = Input_Mgr.Instance().string_input(
                        f"Enter new value for {prop_key}"
                    )
                    target['properties'][prop_key] = new_value
                
                elif action == 'Delete property':
                    if not target['properties']:
                        logger.warning(ansi.style("No properties to delete.", fg=ansi.Fg.YELLOW))
                        return
                    prop_key = Input_Mgr.Instance().single_choice(
                        "Select property to delete",
                        list(target['properties'].keys())
                    )
                    del target['properties'][prop_key]
            
            else:
                # Handle regular field editing
                current_value = target.get(field, '')
                new_value = Input_Mgr.Instance().string_input(
                    f"Enter new value for {field}"
                )
                target[field] = new_value
            
            # Update the target in the database
            success = self.target_manager.update_target(target)
            
            if success:
                logger.info(ansi.style(f"Successfully updated target {target_id}", fg=ansi.Fg.GREEN))
            else:
                logger.error(ansi.style(f"Failed to update target {target_id}", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error editing target: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for edit_target
    do_et = do_edit_target

    @cmd2.with_category('Device Commands')
    def do_send_command(self, arg):
        'Send a command to a device. Usage: send_command <command_string>'
        try:
            if not arg:
                logger.error(ansi.style("Usage: send_command <command_string>", fg=ansi.Fg.RED))
                return

            # Get available device plugins
            available_plugins = self.device_plugin_manager.list_devices()
            if not available_plugins:
                logger.error(ansi.style("No device plugins available", fg=ansi.Fg.RED))
                return

            # Let user select a plugin
            selected_plugin = Input_Mgr.Instance().single_choice(
                "Select device plugin",
                available_plugins
            )

            # Create a temporary plugin instance to scan for devices
            plugin_instance = self.device_plugin_manager.plugins[selected_plugin]
            for attr_name in dir(plugin_instance):
                attr = getattr(plugin_instance, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseDeviceDriver) and 
                    attr != BaseDeviceDriver):
                    driver = attr()
                    scan_result = driver.scan()
                    break

            if not scan_result:
                logger.error(ansi.style(f"No devices found for plugin: {selected_plugin}", fg=ansi.Fg.RED))
                return

            # Let user select a device
            device_choices = [f"{dev.name} ({dev.device_type.value})" for dev in scan_result]
            selected = Input_Mgr.Instance().single_choice(
                "Select device",
                device_choices
            )

            # Get the selected device
            selected_idx = device_choices.index(selected)
            device = scan_result[selected_idx]

            # Initialize and connect to the device
            if driver.initialize(device) and driver.connect(device):
                # Send the command to the device
                driver.command(device, arg)
            else:
                logger.error(ansi.style("Failed to initialize or connect to device", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error sending command: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for send_command
    do_cmd = do_send_command

if __name__ == '__main__':
    shell = SAT_Shell()
    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    shell.cmdloop()

