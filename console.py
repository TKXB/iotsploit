#!/usr/bin/env python
import os
import sys
import time
import importlib
import inspect
from typing import Dict
import argparse

# Set up Django settings first, before any Django-related imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')

import django
django.setup()

# Auto-initialize database on first run
def ensure_database_initialized():
    """Automatically initialize database tables if they don't exist"""
    try:
        # Check if Django tables exist by trying to access a model
        from sat_toolkit.models.Plugin_Model import Plugin
        Plugin.objects.exists()  # This will fail if tables don't exist
        
        # Check if SQLAlchemy tables exist
        from sqlalchemy.exc import OperationalError
        from sat_toolkit.models.database import SessionLocal
        from sat_toolkit.models.Device_Model import DeviceDriverState
        
        session = SessionLocal()
        try:
            session.query(DeviceDriverState).first()
            session.close()
        except OperationalError as e:
            session.close()
            if "no such table: device_driver_states" in str(e):
                print("🔧 Setting up SQLAlchemy database tables...")
                from sat_toolkit.models.database import Base, engine
                Base.metadata.create_all(engine)
                print("✅ SQLAlchemy tables created successfully!")
            else:
                raise e
                
    except Exception as e:
        if "no such table" in str(e) or "no such column" in str(e):
            print("🔧 Database not initialized. Setting up database...")
            try:
                # Run Django migrations
                print("📋 Running Django migrations...")
                from django.core.management import execute_from_command_line
                execute_from_command_line(['manage.py', 'migrate'])
                print("✅ Django migrations completed!")
                
                # Create SQLAlchemy tables
                print("📋 Creating SQLAlchemy tables...")
                from sat_toolkit.models.database import Base, engine
                Base.metadata.create_all(engine)
                print("✅ SQLAlchemy tables created!")
                
                print("🎉 Database initialization completed successfully!")
                
            except Exception as init_error:
                print(f"❌ Error initializing database: {init_error}")
                print("💡 You may need to run: python manage.py migrate")
                raise init_error
        else:
            raise e

# Initialize database before proceeding
ensure_database_initialized()

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
from sat_toolkit.tools.monitor_mgr import SystemMonitor
from sat_toolkit.tools.ota_mgr import OTA_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.models.Plugin_Model import Plugin
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.tool_service import get_firmware_service
from sat_toolkit.core.device_registry import DeviceRegistry
from sat_toolkit.tools.xlogger import xlog as logger
from pwnlib import term
term.term_mode = True

def global_exception_handler(exctype, value, traceback):
    logger.error("Unhandled exception", exc_info=(exctype, value, traceback))

sys.excepthook = global_exception_handler

def discover_command_modules():
    """Auto-discover and load all command modules"""
    from commands.base_commands import BaseCommands
    
    command_classes = []
    commands_dir = os.path.join(os.path.dirname(__file__), 'commands')
    
    # Scan all .py files in commands directory
    for filename in os.listdir(commands_dir):
        if filename.endswith('.py') and not filename.startswith('__') and filename != 'base_commands.py':
            module_name = filename[:-3]  # Remove .py extension
            
            try:
                # Import the module
                module = importlib.import_module(f'commands.{module_name}')
                
                # Find classes that inherit from BaseCommands
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseCommands) and 
                        obj != BaseCommands):
                        command_classes.append(obj)
                        logger.debug(f"Discovered command class: {obj.__name__} from {module_name}")
            except ImportError as e:
                logger.warning(f"Could not import {module_name}: {e}")
            except Exception as e:
                logger.error(f"Error loading {module_name}: {e}")
    
    logger.info(f"Auto-discovered {len(command_classes)} command modules")
    return command_classes

# Auto-discover command modules
try:
    CommandMixins = discover_command_modules()
    logger.info(f"Successfully loaded command modules: {[cls.__name__ for cls in CommandMixins]}")
except Exception as e:
    logger.error(f"Failed to discover command modules: {e}")
    CommandMixins = []

# Create dynamic inheritance
SAT_Shell_Base = type('SAT_Shell_Base', (cmd2.Cmd, *CommandMixins), {})

class SAT_Shell(SAT_Shell_Base):
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
        
        # Check if database has any targets, if not, optionally load from JSON as initial setup
        existing_targets = self.target_manager.get_all_targets()
        if not existing_targets:
            logger.info("No targets found in database. You can:")
            logger.info("1. Use Flutter UI to create targets")
            logger.info("2. Use 'target_import' command to import from JSON file")
            logger.info("3. Use target management commands to create targets manually")
        else:
            logger.info(f"Found {len(existing_targets)} targets in database")
        
        # Note: Removed automatic JSON loading to prevent overwriting user changes
        # Use 'target_import conf/target.json' command if you need to import from JSON

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
            'quit': 'Shell Commands',
            'run_pyscript': 'Shell Commands',
            'run_script': 'Shell Commands',
            'runserver': 'Shell Commands',
            'set': 'Shell Commands',
            'set_log_level': 'Shell Commands',
            'shell': 'Shell Commands',
            'shortcuts': 'Shell Commands',
            'stop_server': 'Shell Commands',
        })

    def emptyline(self):
        self.onecmd("help")

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SAT Shell entrypoint')
    parser.add_argument('--runserver', action='store_true', help='Start servers directly and keep running until Ctrl+C; on Ctrl+C, stop servers')
    args = parser.parse_args()

    shell = SAT_Shell()
    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    if args.runserver:
        try:
            # 启动服务并保持运行，直到收到 Ctrl+C
            shell.do_runserver("")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            # 捕获 Ctrl+C，优雅停止服务
            try:
                shell.do_stop_server("")
            finally:
                # 确保设备连接被清理
                try:
                    shell._cleanup_devices()
                except Exception:
                    pass
        sys.exit(0)
    else:
        shell.cmdloop()

