#!/usr/bin/env python
import os
import sys
import time
from typing import Dict

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
from sat_toolkit.core.device_manager import DeviceDriverManager  
from sat_toolkit.models.Device_Model import DeviceManager, DeviceType, SerialDevice, USBDevice, SocketCANDevice
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
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.tools.firmware_mgr import FirmwareManager
from sat_toolkit.core.device_registry import DeviceRegistry
from sat_toolkit.tools.xlogger import xlog as logger

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
        self.daphne_server_process = None
        self.celery_worker_process = None
        
        # Initialize device manager and connected devices
        self.device_driver_manager = DeviceDriverManager()
        # 初始化设备相关属性
        self._current_plugin = None
        self._current_device = None
        self._current_driver = None
        self.connected_devices = {}
        
        
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
        self.device_manager.register_device(DeviceType.CAN, SocketCANDevice)
        self.device_manager.parse_and_set_device_from_json('conf/devices.json')


        # Customize help display
        self.help_category_header = ansi.style("\n{:-^80}\n", fg=ansi.Fg.BLUE)
        self.help_category_footer = "\n"
        
        # Group all commands under Shell Commands
        self._cmd_to_category.update({
            'alias': 'Shell Commands',
            'connect_wifi': 'Shell Commands',
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
        'Show IoTSploit Host Info'
        logger.info(ansi.style("Host Device Info:", fg=ansi.Fg.CYAN))
        
        pi_monitor = SystemMonitor.create_monitor("raspberry_pi")
        device_info = SystemMonitor.monitor_device(pi_monitor)
        
        for key, value in device_info.items():
            if isinstance(value, dict):
                logger.info(ansi.style(f"  {key}:", fg=ansi.Fg.CYAN))
                for sub_key, sub_value in value.items():
                    logger.info(ansi.style(f"    {sub_key}: {sub_value}", fg=ansi.Fg.CYAN))
            else:
                logger.info(ansi.style(f"  {key}: {value}", fg=ansi.Fg.CYAN))

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
        'Exit Console'
        if self.django_server_process:
            self.do_stop_server(arg)
        Toolkit_Main.Instance().exit_quick_test()
        Toolkit_Main.Instance().stop_audit()
        self._cleanup_devices()  # Add device cleanup
        logger.info("IotSploit Shell Quit. ByeBye~")
        return True

    @cmd2.with_category('Network Commands')
    def do_connect_wifi(self, arg):
        'Connect to WiFi network by providing SSID and password'
        logger.info(ansi.style("WiFi Connection Setup", fg=ansi.Fg.CYAN))
        
        # Get SSID from user
        ssid = Input_Mgr.Instance().string_input("Enter WiFi SSID")
        
        # Get password from user
        password = Input_Mgr.Instance().string_input("Enter WiFi password")
        
        # Attempt to connect
        logger.info(ansi.style(f"Attempting to connect to {ssid}...", fg=ansi.Fg.CYAN))
        WiFi_Mgr.Instance().sta_connect_wifi(ssid, password)
        
        # Wait for connection to establish
        time.sleep(2)
        
        # Show connection status
        WiFi_Mgr.Instance().status()

    @cmd2.with_category('Django Commands')
    def do_runserver(self, arg):
        'Start Django development server, Daphne WebSocket server, and Celery worker in the background'
        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            logger.info("Attempting to start Django, Daphne, and Celery servers in background...")
            
            # Prepare the commands
            django_cmd = [sys.executable, 'manage.py', 'runserver', '--noreload', '0.0.0.0:8888']
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
            
            # Start the processes with direct output to stdout/stderr
            self.django_server_process = subprocess.Popen(
                django_cmd, 
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            self.daphne_server_process = subprocess.Popen(
                daphne_cmd, 
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            self.celery_worker_process = subprocess.Popen(
                celery_cmd,
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            logger.info("All servers started successfully in the background.")
            
            # Wait for HTTP server to be available and initialize devices
            import requests
            import time
            max_retries = 30
            retry_interval = 1
            
            logger.info("Waiting for HTTP server to be available...")
            for i in range(max_retries):
                try:
                    # Try to initialize devices using the HTTP endpoint (GET method)
                    response = requests.get('http://127.0.0.1:8888/api/initialize_devices/')
                    if response.status_code == 200:
                        logger.info("Devices initialized successfully via HTTP API")
                        break
                    else:
                        logger.error(f"Failed to initialize devices: {response.text}")
                        break
                except requests.exceptions.ConnectionError:
                    if i < max_retries - 1:
                        time.sleep(retry_interval)
                    else:
                        logger.error("HTTP server did not become available in time")
                    continue
                except Exception as e:
                    logger.error(f"Error initializing devices: {str(e)}")
                    break
            
        except Exception as e:
            logger.error(f"Failed to start servers: {str(e)}")
            logger.debug("Detailed traceback:", exc_info=True)

    @cmd2.with_category('Django Commands')
    def do_stop_server(self, arg):
        'Stop Django development server, Daphne WebSocket server, and Celery worker'
        try:
            # Cleanup devices using HTTP endpoint (GET method)
            import requests
            try:
                response = requests.get('http://127.0.0.1:8888/api/cleanup_devices/')
                if response.status_code == 200:
                    logger.info("Devices cleaned up successfully via HTTP API")
                else:
                    logger.error(f"Failed to cleanup devices: {response.text}")
            except requests.exceptions.ConnectionError:
                logger.warning("Could not reach HTTP server for device cleanup")
            except Exception as e:
                logger.error(f"Error during device cleanup: {str(e)}")
            
            # Stop the servers
            if self.django_server_process:
                self.django_server_process.terminate()
                self.django_server_process = None
            
            if self.daphne_server_process:
                self.daphne_server_process.terminate()
                self.daphne_server_process = None
            
            if hasattr(self, 'celery_worker_process') and self.celery_worker_process:
                self.celery_worker_process.terminate()
                self.celery_worker_process = None
            
            if not any([self.django_server_process, self.daphne_server_process, 
                        getattr(self, 'celery_worker_process', None)]):
                logger.info("All servers stopped.")
            else:
                logger.error("No servers were running.")
                
        except Exception as e:
            logger.error(f"Error stopping servers: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    @cmd2.with_category('System Commands')
    def do_set_log_level(self, arg):
        'Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)'
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
        if not arg:
            # If no argument provided, let user select from valid levels
            selected_level = Input_Mgr.Instance().single_choice(
                "Select logging level",
                valid_levels
            )
        else:
            # If argument provided, validate it
            selected_level = arg.upper()
            if selected_level not in valid_levels:
                logger.error(ansi.style(f"Invalid log level. Choose from: {', '.join(valid_levels)}", fg=ansi.Fg.RED))
                return

        try:
            # Set the log level using XLogger's set_level method
            logger.set_level(selected_level)
            logger.info(ansi.style(f"Log level set to {selected_level}", fg=ansi.Fg.GREEN))
        except Exception as e:
            logger.error(ansi.style(f"Error setting log level: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for set_log_level
    do_sll = do_set_log_level

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

    # runserver to start celery worker
    # target_select to select target
    # execute_plugin to execute plugin
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
            # Get the plugin instance to access its parameters
            plugin_instance = self.plugin_manager.get_plugin(choice)
            if not plugin_instance:
                logger.error(ansi.style(f"Could not get plugin instance for '{choice}'", fg=ansi.Fg.RED))
                return
                
            # Get plugin info with parameters
            plugin_info = plugin_instance.get_info()
            plugin_params = plugin_info.get('Parameters', {})
            
            # Get current target from target manager
            target_manager = self.target_manager
            current_target = target_manager.get_current_target()
            
            # Prepare target dictionary
            target_dict = {}
            
            # If we have a target, include its properties
            if current_target:
                # Add target properties to target dictionary
                target_dict = current_target.get_info() if hasattr(current_target, 'get_info') else {}
            
            # Prompt for required parameters that are not in the target
            for param_name, param_info in plugin_params.items():
                if param_name not in target_dict and param_info.get('required', False):
                    param_type = param_info.get('type', 'str')
                    description = param_info.get('description', f"Enter {param_name}")
                    default = param_info.get('default')
                    validation = param_info.get('validation', {})
                    
                    if param_type == 'str':
                        if 'choices' in validation:
                            # Use single_choice for string with choices
                            value = Input_Mgr.Instance().single_choice(
                                f"{description} (Choose one)",
                                validation['choices']
                            )
                        else:
                            # Regular string input
                            value = Input_Mgr.Instance().string_input(description)
                    elif param_type == 'int':
                        # Integer input with optional min/max validation
                        min_val = validation.get('min')
                        max_val = validation.get('max')
                        value = Input_Mgr.Instance().int_input(
                            description,
                            min_val=min_val,
                            max_val=max_val
                        )
                    elif param_type == 'bool':
                        # Boolean input
                        value = Input_Mgr.Instance().yes_no_input(
                            description,
                            default=default if default is not None else True
                        )
                    else:
                        # Default to string for unknown types
                        value = Input_Mgr.Instance().string_input(description)
                    
                    # Add to target dict
                    target_dict[param_name] = value
            
            logger.debug(f"Executing plugin with target configuration: {target_dict}")
            
            # Now execute the plugin with our target dictionary
            result = self.plugin_manager.execute_plugin(choice, target=target_dict)
            
            # Check if this is an async execution
            if isinstance(result, dict) and result.get('execution_type') == 'async':
                task_id = result.get('task_id')
                logger.info(ansi.style(f"Plugin running asynchronously with task ID: {task_id}", fg=ansi.Fg.CYAN))
                
                # Ask user if they want to wait for results
                wait_for_results = Input_Mgr.Instance().yes_no_input(
                    "Do you want to wait for the asynchronous task to complete?",
                    default=True
                )
                
                if wait_for_results:
                    # Import celery here to avoid circular imports
                    try:
                        from celery.result import AsyncResult
                        from sat_toolkit import celery_app
                        import time

                        task_result = AsyncResult(task_id, app=celery_app)
                        
                        # Poll for results with a progress bar
                        progress = 0
                        start_time = time.time()
                        
                        logger.info(ansi.style("Waiting for task to complete...", fg=ansi.Fg.CYAN))
                        
                        while not task_result.ready():
                            # Try to get progress information
                            task_info = task_result.info
                            
                            if isinstance(task_info, dict):
                                new_progress = task_info.get('progress', 0)
                                message = task_info.get('message', 'Processing...')
                                
                                # Only update if progress has changed
                                if new_progress != progress:
                                    progress = new_progress
                                    # Print progress bar
                                    bar_length = 50
                                    filled_length = int(bar_length * progress / 100)
                                    bar = '█' * filled_length + '-' * (bar_length - filled_length)
                                    logger.info(f"Progress: [{bar}] {progress:.1f}% - {message}")
                            
                            # Sleep briefly before checking again
                            time.sleep(0.5)
                            
                            # Add a timeout to prevent infinite waiting
                            if time.time() - start_time > 300:  # 5 minutes
                                logger.warning(ansi.style("Timeout waiting for task to complete", fg=ansi.Fg.YELLOW))
                                break
                        
                        # Get final result
                        final_result = task_result.get(timeout=5)  # 5 second timeout for final result
                        
                        logger.info(ansi.style("Async plugin execution completed", fg=ansi.Fg.GREEN))
                        if isinstance(final_result, dict):
                            logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                            for key, value in final_result.items():
                                logger.info(f"{key}: {value}")
                        else:
                            logger.info(f"Result: {final_result}")
                    
                    except ImportError as e:
                        logger.error(ansi.style(f"Error importing Celery modules: {str(e)}", fg=ansi.Fg.RED))
                    except Exception as e:
                        logger.error(ansi.style(f"Error getting async result: {str(e)}", fg=ansi.Fg.RED))
                        logger.debug("Detailed error:", exc_info=True)
                
                # Display initial async info regardless
                logger.info(ansi.style("Initial async task info:", fg=ansi.Fg.GREEN))
                logger.info(str(result))
                
            elif isinstance(result, ExploitResult):
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(f"Success: {result.success}")
                logger.info(f"Message: {result.message}")
                logger.info(f"Data: {result.data}")
            else:
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(str(result))
        except Exception as e:
            logger.error(ansi.style(f"Error executing plugin: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)
    do_exec = do_execute_plugin

    @cmd2.with_category('Device Commands')
    def do_list_device_drivers(self, arg):
        'List all available device plugins'
        available_devices = self.device_driver_manager.list_drivers()
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
    def do_execute_device_command(self, arg):
        'Send a command to a device. Usage: device_command [command_string]'
        try:
            # Check if we need to select a device first
            if not hasattr(self, '_current_device') or not hasattr(self, '_current_driver'):
                logger.info(ansi.style("No device selected. Please select a device first.", fg=ansi.Fg.YELLOW))
                if not self._select_device():
                    return
            
            # Now we can be sure we have a device selected
            if not arg:
                # If no command provided, list available commands and let user select one
                commands = self.device_driver_manager.get_plugin_commands(self._current_plugin)
                if commands:
                    logger.info(ansi.style(f"\nAvailable commands for {self._current_plugin}:", fg=ansi.Fg.CYAN))
                    
                    # Create list of command choices with descriptions
                    cmd_choices = [f"{cmd:<10} - {desc}" for cmd, desc in commands.items()]
                    
                    # Let user select a command
                    selected = Input_Mgr.Instance().single_choice(
                        "Select command to execute",
                        cmd_choices
                    )
                    
                    # Extract just the command name from the selection
                    selected_cmd = selected.split()[0].strip()
                    
                    # Execute the selected command
                    self._current_driver.command(self._current_device, selected_cmd)
                else:
                    logger.warning(ansi.style(f"No commands available for driver: {self._current_plugin}", fg=ansi.Fg.YELLOW))
            else:
                # Send the command to the device
                self._current_driver.command(self._current_device, arg)

        except Exception as e:
            logger.error(ansi.style(f"Error sending command: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    def _select_device(self):
        """Helper method to handle device selection process"""
        try:
            # Get available device plugins with connected devices
            available_plugins = [
                driver_name for driver_name, device 
                in self.connected_devices.items()
            ]
            
            if not available_plugins:
                logger.error(ansi.style("No initialized devices available", fg=ansi.Fg.RED))
                return False

            # Let user select a plugin
            selected_plugin = Input_Mgr.Instance().single_choice(
                "Select device plugin",
                available_plugins
            )

            # Get the already connected device
            device = self.connected_devices.get(selected_plugin)
            if not device:
                logger.error(ansi.style(f"Device not found for {selected_plugin}", fg=ansi.Fg.RED))
                return False

            # Store the current device and driver information
            self._current_device = device
            self._current_driver = self.device_driver_manager.get_driver_instance(selected_plugin)
            self._current_plugin = selected_plugin

            logger.info(ansi.style(f"Selected device: {device.name}", fg=ansi.Fg.GREEN))
            return True

        except Exception as e:
            logger.error(ansi.style(f"Error during device selection: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)
            return False

    @cmd2.with_category('Device Commands')
    def do_select_device(self, arg):
        'Select a device for subsequent commands'
        if self._select_device():
            logger.info(ansi.style("Device selected successfully. Use 'execute_device_command' to send commands.", fg=ansi.Fg.GREEN))
        else:
            logger.error(ansi.style("Device selection failed.", fg=ansi.Fg.RED))

    # Add alias for select_device
    do_sd = do_select_device

    @cmd2.with_category('Device Commands')
    def do_switch_device(self, arg):
        'Switch to a different device'
        if hasattr(self, '_current_device'):
            # Try to disconnect current device if possible
            try:
                if hasattr(self._current_driver, 'disconnect'):
                    self._current_driver.disconnect(self._current_device)
            except Exception as e:
                logger.debug(f"Error disconnecting device: {str(e)}")

            delattr(self, '_current_device')
            delattr(self, '_current_driver')
            delattr(self, '_current_plugin')
            
        # Immediately prompt for new device selection
        if self._select_device():
            logger.info(ansi.style("Successfully switched to new device.", fg=ansi.Fg.GREEN))
        else:
            logger.error(ansi.style("Failed to switch device.", fg=ansi.Fg.RED))

    @cmd2.with_category('Device Commands')
    def do_list_device_commands(self, arg):
        'List available commands for a device driver'
        try:
            # Get available device plugins
            available_plugins = self.device_driver_manager.list_drivers()
            if not available_plugins:
                logger.error(ansi.style("No device plugins available", fg=ansi.Fg.RED))
                return

            # Let user select a plugin
            selected_plugin = Input_Mgr.Instance().single_choice(
                "Select device plugin",
                available_plugins
            )

            # Get commands for the selected plugin
            commands = self.device_driver_manager.get_plugin_commands(selected_plugin)
            
            if not commands:
                logger.warning(ansi.style(f"No commands available for plugin: {selected_plugin}", fg=ansi.Fg.YELLOW))
                return

            # Display commands and their descriptions
            logger.info(ansi.style(f"\nAvailable commands for {selected_plugin}:", fg=ansi.Fg.CYAN))
            for cmd, description in commands.items():
                logger.info(ansi.style(f"  {cmd:<10}", fg=ansi.Fg.GREEN) + 
                          ansi.style(f"- {description}", fg=ansi.Fg.WHITE))

        except Exception as e:
            logger.error(ansi.style(f"Error listing commands: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for list_device_commands
    do_lscmd = do_list_device_commands

    @cmd2.with_category('Firmware Commands')
    def do_list_firmware(self, arg):
        'List all available firmware'
        try:
            firmware_list = FirmwareManager.Instance().list_firmware()
            
            if not firmware_list:
                logger.info(ansi.style("No firmware available.", fg=ansi.Fg.YELLOW))
                return

            logger.info(ansi.style("\nAvailable Firmware:", fg=ansi.Fg.CYAN))
            for fw in firmware_list:
                logger.info(ansi.style(f"\nName: {fw['name']}", fg=ansi.Fg.GREEN))
                logger.info(f"Device Type: {fw['device_type']}")
                logger.info(f"Version: {fw['version']}")
                logger.info(f"Path: {fw['path']}")

        except Exception as e:
            logger.error(ansi.style(f"Error listing firmware: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Firmware Commands')
    def do_add_firmware(self, arg):
        'Add new firmware to the system'
        try:
            # Get firmware details from user
            name = Input_Mgr.Instance().string_input("Enter firmware name")
            path = Input_Mgr.Instance().string_input("Enter firmware file path")
            device_type = Input_Mgr.Instance().string_input("Enter device type")
            version = Input_Mgr.Instance().string_input("Enter firmware version")

            success = FirmwareManager.Instance().add_firmware(
                name=name,
                path=path,
                device_type=device_type,
                version=version
            )

            if success:
                logger.info(ansi.style(f"Successfully added firmware: {name}", fg=ansi.Fg.GREEN))
            else:
                logger.error(ansi.style("Failed to add firmware", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error adding firmware: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Firmware Commands')
    def do_flash_firmware(self, arg):
        'Flash firmware to a device'
        try:
            # Get available firmware
            firmware_list = FirmwareManager.Instance().list_firmware()
            if not firmware_list:
                logger.error(ansi.style("No firmware available to flash", fg=ansi.Fg.RED))
                return

            # Let user select firmware
            firmware_choices = [fw['name'] for fw in firmware_list]
            selected_firmware = Input_Mgr.Instance().single_choice(
                "Select firmware to flash",
                firmware_choices
            )

            # Optionally specify port
            use_port = Input_Mgr.Instance().yes_no_input("Specify a port?", False)
            port = None
            if use_port:
                port = Input_Mgr.Instance().string_input("Enter port")

            # Confirm flashing
            if Input_Mgr.Instance().yes_no_input(
                f"Are you sure you want to flash {selected_firmware}?",
                False
            ):
                success = FirmwareManager.Instance().flash_firmware(
                    name=selected_firmware,
                    port=port
                )

                if success:
                    logger.info(ansi.style(f"Successfully flashed firmware: {selected_firmware}", fg=ansi.Fg.GREEN))
                else:
                    logger.error(ansi.style("Failed to flash firmware", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error flashing firmware: {str(e)}", fg=ansi.Fg.RED))

    @cmd2.with_category('Firmware Commands')
    def do_remove_firmware(self, arg):
        'Remove firmware from the system'
        try:
            # Get available firmware
            firmware_list = FirmwareManager.Instance().list_firmware()
            if not firmware_list:
                logger.error(ansi.style("No firmware available to remove", fg=ansi.Fg.RED))
                return

            # Let user select firmware
            firmware_choices = [fw['name'] for fw in firmware_list]
            selected_firmware = Input_Mgr.Instance().single_choice(
                "Select firmware to remove",
                firmware_choices
            )

            # Confirm removal
            if Input_Mgr.Instance().yes_no_input(
                f"Are you sure you want to remove {selected_firmware}?",
                False
            ):
                success = FirmwareManager.Instance().remove_firmware(selected_firmware)

                if success:
                    logger.info(ansi.style(f"Successfully removed firmware: {selected_firmware}", fg=ansi.Fg.GREEN))
                else:
                    logger.error(ansi.style("Failed to remove firmware", fg=ansi.Fg.RED))

        except Exception as e:
            logger.error(ansi.style(f"Error removing firmware: {str(e)}", fg=ansi.Fg.RED))

    # Add aliases
    do_lsfw = do_list_firmware
    do_addfw = do_add_firmware
    do_flashfw = do_flash_firmware
    do_rmfw = do_remove_firmware

    @cmd2.with_category('Plugin Commands')
    def do_delete_group(self, arg):
        'Delete a plugin group. Usage: delete_group'
        try:
            # Get all groups
            groups = PluginGroup.objects.all()
            if not groups.exists():
                logger.warning(ansi.style("No plugin groups available to delete.", fg=ansi.Fg.YELLOW))
                return

            # Create list of group choices
            group_choices = [group.name for group in groups]
            
            # Let user select a group
            selected = Input_Mgr.Instance().single_choice(
                "Select group to delete",
                group_choices
            )
            
            # Confirm deletion
            if Input_Mgr.Instance().yes_no_input(
                f"Are you sure you want to delete group '{selected}'?",
                False
            ):
                try:
                    group = PluginGroup.objects.get(name=selected)
                    group.delete()
                    logger.info(ansi.style(f"Successfully deleted group: {selected}", fg=ansi.Fg.GREEN))
                except PluginGroup.DoesNotExist:
                    logger.error(ansi.style(f"Group not found: {selected}", fg=ansi.Fg.RED))
            else:
                logger.info("Deletion cancelled.")

        except Exception as e:
            logger.error(ansi.style(f"Error deleting group: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for delete_group
    do_dg = do_delete_group

    @cmd2.with_category('Device Commands')
    def do_scan_devices(self, arg):
        'Scan for devices and show detailed information'
        try:
            # 获取设备注册表实例
            device_registry = DeviceRegistry()
            device_registry.initialize()  # 确保已初始化
            
            # 执行设备扫描
            logger.info(ansi.style("Scanning for devices...", fg=ansi.Fg.CYAN))
            discovered_devices = device_registry.scan_devices()
            
            # 获取所有设备（包括已存储的和新发现的）
            all_devices = device_registry.device_store.devices
            device_sources = device_registry.device_store.device_sources  # 直接获取设备来源字典
            
            # 分类显示设备
            static_devices = {
                device_id: device 
                for device_id, device in all_devices.items()
                if device_sources.get(device_id) == "static"
            }
            
            dynamic_devices = {
                device_id: device 
                for device_id, device in all_devices.items()
                if device_sources.get(device_id) == "dynamic"
            }
            
            if static_devices:
                logger.info(ansi.style("\nConfigured Devices:", fg=ansi.Fg.BLUE))
                self._display_devices(static_devices, device_sources)
            
            if dynamic_devices:
                logger.info(ansi.style("\nDynamically Discovered Devices:", fg=ansi.Fg.GREEN))
                self._display_devices(dynamic_devices, device_sources)
            
            if not static_devices and not dynamic_devices:
                logger.info(ansi.style("No devices found.", fg=ansi.Fg.YELLOW))

        except Exception as e:
            logger.error(ansi.style(f"Error scanning devices: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    def _display_devices(self, devices: Dict, sources: Dict):
        """Helper method to display device information"""
        for device_id, device in devices.items():
            source = sources.get(device_id, "unknown")
            source_color = ansi.Fg.GREEN if source == "dynamic" else ansi.Fg.BLUE
            
            # Only display ID, Name, and Source
            logger.info(ansi.style(f"\n  Device ID: {device_id}", fg=ansi.Fg.CYAN))
            logger.info(ansi.style(f"  Source: {source}", fg=source_color))
            logger.info(f"  Name: {device.name}")
            logger.info("  " + "-" * 40)  # Separator line

    # 添加命令别名
    do_scan = do_scan_devices

    # Add alias for execute_device_command
    do_dc = do_execute_device_command

    def _auto_initialize_devices(self):
        """自动扫描并初始化所有可用设备"""
        logger.info("Automatic device initialization started...")
        
        available_drivers = list(self.device_driver_manager.drivers.keys())
        if not available_drivers:
            logger.warning("No device drivers available!")
            return

        logger.info(f"Found {len(available_drivers)} drivers: {', '.join(available_drivers)}")

        for driver_name in available_drivers:
            try:
                logger.info(f"Initializing {driver_name}...")
                
                scan_result = self.device_driver_manager.scan_devices(driver_name)
                if scan_result['status'] != 'success':
                    logger.error(f"Failed to scan {driver_name}: {scan_result.get('message', 'Unknown error')}")
                    continue
                
                devices = scan_result.get('devices', [])
                if not devices:
                    logger.warning(f"No devices found for {driver_name}")
                    continue

                logger.info(f"Found {len(devices)} device(s) for {driver_name}")

                for device in devices:
                    try:
                        logger.info(f"Processing device: {device.name} (ID: {device.device_id})")

                        init_result = self.device_driver_manager.initialize_device(driver_name, device)
                        if init_result['status'] != 'success':
                            logger.error(f"Failed to initialize {device.name}: {init_result['message']}")
                            continue

                        connect_result = self.device_driver_manager.connect_device(driver_name, device)
                        if connect_result['status'] != 'success':
                            logger.error(f"Failed to connect {device.name}: {connect_result['message']}")
                            continue

                        self.connected_devices[driver_name] = device
                        logger.info(f"Successfully connected {device.name} using {driver_name}")

                    except Exception as e:
                        logger.error(f"Error processing device: {str(e)}")

            except Exception as e:
                logger.error(f"Error initializing {driver_name}: {str(e)}")

        self._show_initialization_summary()

    def _show_initialization_summary(self):
        """打印设备初始化摘要"""
        logger.info("Device Initialization Summary:")
        
        for driver_name, driver in self.device_driver_manager.drivers.items():
            logger.info("")
            logger.info(f"{driver_name}:")
            
            # 获取当前设备
            current_device = self.connected_devices.get(driver_name)
            
            if current_device:
                # 使用当前设备的 device_id 获取状态
                state = self.device_driver_manager.get_device_state(
                    driver_name, 
                    device_id=current_device.device_id
                )
                logger.info(f"  Device: {current_device.name}")
                logger.info(f"  State: {state.value}")
            else:
                logger.info(f"  Device: No device connected")
                logger.info(f"  State: unknown")
                
            # 获取支持的命令
            commands = self.device_driver_manager.get_supported_commands(driver_name)
            if commands:
                logger.info(f"  Commands: {', '.join(commands.keys())}")

    def _cleanup_devices(self):
        """清理所有设备连接"""
        if not self.connected_devices:
            return

        logger.info("Cleaning up device connections...")
        for driver_name, device in list(self.connected_devices.items()):
            try:
                result = self.device_driver_manager.close_device(driver_name, device)
                if result['status'] == 'success':
                    logger.info(f"Successfully closed {device.name}")
                    del self.connected_devices[driver_name]
                else:
                    logger.error(f"Failed to close {device.name}: {result['message']}")
            except Exception as e:
                logger.error(f"Error closing {device.name}: {str(e)}")

    @cmd2.with_category('Device Commands')
    def do_initialize_devices(self, arg):
        'Auto-initialize all available devices'
        logger.info("Starting device initialization...")
        self._auto_initialize_devices()

    # Add alias for initialize_devices
    do_initdev = do_initialize_devices

if __name__ == '__main__':
    shell = SAT_Shell()
    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    shell.cmdloop()

