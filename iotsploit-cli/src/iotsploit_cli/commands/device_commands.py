#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from typing import Dict
from .base_commands import BaseCommands
from iotsploit_django.tools.monitor_mgr import SystemMonitor
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_django.adapters.django.device_registry_factory import get_device_registry
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class DeviceCommands(BaseCommands):
    """Device-related commands for the SAT Shell"""

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

    def _select_device(self, selected_plugin=None):
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
            if selected_plugin:
                if selected_plugin not in available_plugins:
                    logger.error(
                        ansi.style(
                            f"Device '{selected_plugin}' is not initialized. "
                            f"Available devices: {', '.join(available_plugins)}",
                            fg=ansi.Fg.RED,
                        )
                    )
                    return False
            else:
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
        selected_plugin = arg.strip() if arg else None
        if self._select_device(selected_plugin):
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

            selected_plugin = arg.strip() if arg else None
            if selected_plugin:
                if selected_plugin not in available_plugins:
                    logger.error(
                        ansi.style(
                            f"Driver '{selected_plugin}' not found. "
                            f"Available drivers: {', '.join(available_plugins)}",
                            fg=ansi.Fg.RED,
                        )
                    )
                    return
            else:
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

    @cmd2.with_category('Device Commands')
    def do_scan_devices(self, arg):
        'Scan for devices and show detailed information'
        try:
            # 获取设备注册表实例
            device_registry = get_device_registry()
            device_registry.initialize()  # 确保已初始化
            
            # 执行设备扫描
            logger.info(ansi.style("Scanning for devices...", fg=ansi.Fg.CYAN))
            device_registry.scan_devices()
            
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

    @cmd2.with_category('Device Commands')
    def do_initialize_devices(self, arg):
        'Auto-initialize all available devices'
        logger.info("Starting device initialization...")
        self._auto_initialize_devices()

    # Add alias for initialize_devices
    do_initdev = do_initialize_devices

    @cmd2.with_category('Device Commands')
    def do_get_driver_states(self, arg):
        'Show enabled/disabled state of all device drivers'
        try:
            driver_states = self.device_driver_manager.get_driver_states()
            
            if not driver_states:
                logger.info(ansi.style("No device drivers found.", fg=ansi.Fg.YELLOW))
                return
                
            logger.info(ansi.style("\nDevice Driver States:", fg=ansi.Fg.CYAN))
            
            # Calculate column widths for alignment
            max_name_len = max(len(name) for name in driver_states.keys())
            
            # Display stats
            enabled_count = sum(1 for state in driver_states.values() if state.get("enabled", True))
            disabled_count = len(driver_states) - enabled_count
            
            logger.info(ansi.style(f"Total: {len(driver_states)} | Enabled: {enabled_count} | Disabled: {disabled_count}\n", fg=ansi.Fg.BLUE))
            
            # Display detailed info for each driver
            for driver_name, state in driver_states.items():
                enabled = state.get("enabled", True)
                status_color = ansi.Fg.GREEN if enabled else ansi.Fg.RED
                status_text = "Enabled" if enabled else "Disabled"
                
                logger.info(ansi.style(f"{driver_name:<{max_name_len}} : ", fg=ansi.Fg.CYAN) + 
                            ansi.style(f"{status_text}", fg=status_color))
                
                # Show description if available
                description = state.get("description")
                if description:
                    logger.info(f"  Description: {description}")
                
                # Show last update time if available
                last_updated = state.get("last_updated")
                if last_updated:
                    logger.info(f"  Last updated: {last_updated}")
                
                logger.info("")  # Empty line between drivers
            
        except Exception as e:
            logger.error(ansi.style(f"Error getting driver states: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add alias for get_driver_states
    do_gds = do_get_driver_states

    @cmd2.with_category('Device Commands')
    def do_enable_driver(self, arg):
        'Enable a device driver. Usage: enable_driver [driver_name]'
        try:
            # Get list of all drivers
            all_drivers = self.device_driver_manager.list_drivers()
            
            if not all_drivers:
                logger.warning(ansi.style("No device drivers available.", fg=ansi.Fg.YELLOW))
                return
            
            # If driver name is provided as an argument, use it
            # Otherwise, let user select from available drivers
            driver_name = arg.strip() if arg else None
            
            if not driver_name:
                # Get current states to show which are disabled
                states = self.device_driver_manager.get_driver_states()
                
                # Create list with status indicators
                driver_choices = []
                for drv in all_drivers:
                    status = states.get(drv, {}).get("enabled", True)
                    status_text = "Enabled" if status else "Disabled"
                    driver_choices.append(f"{drv} [{status_text}]")
                
                # Let user select a driver
                selected = Input_Mgr.Instance().single_choice(
                    "Select driver to enable",
                    driver_choices
                )
                
                # Extract driver name from selection
                driver_name = selected.split()[0]
            
            # Ask for optional description
            description = Input_Mgr.Instance().string_input(
                "Enter reason for enabling (optional)"
            )
            
            # Enable the driver - only pass description if it's not empty
            if description.strip():
                result = self.device_driver_manager.enable_driver(driver_name, description)
            else:
                result = self.device_driver_manager.enable_driver(driver_name)
            
            if result.get("status") == "success":
                logger.info(ansi.style(f"Successfully enabled driver: {driver_name}", fg=ansi.Fg.GREEN))
            else:
                logger.error(ansi.style(f"Failed to enable driver: {result.get('message', 'Unknown error')}", fg=ansi.Fg.RED))
            
        except Exception as e:
            logger.error(ansi.style(f"Error enabling driver: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add alias for enable_driver
    do_ed = do_enable_driver

    @cmd2.with_category('Device Commands')
    def do_disable_driver(self, arg):
        'Disable a device driver. Usage: disable_driver [driver_name]'
        try:
            # Get list of all drivers
            all_drivers = self.device_driver_manager.list_drivers()
            
            if not all_drivers:
                logger.warning(ansi.style("No device drivers available.", fg=ansi.Fg.YELLOW))
                return
            
            # If driver name is provided as an argument, use it
            # Otherwise, let user select from available drivers
            driver_name = arg.strip() if arg else None
            
            if not driver_name:
                # Get current states to show which are enabled
                states = self.device_driver_manager.get_driver_states()
                
                # Create list with status indicators
                driver_choices = []
                for drv in all_drivers:
                    status = states.get(drv, {}).get("enabled", True)
                    status_text = "Enabled" if status else "Disabled"
                    driver_choices.append(f"{drv} [{status_text}]")
                
                # Let user select a driver
                selected = Input_Mgr.Instance().single_choice(
                    "Select driver to disable",
                    driver_choices
                )
                
                # Extract driver name from selection
                driver_name = selected.split()[0]
            
            # Warning and confirmation before disabling
            logger.warning(ansi.style("Warning: Disabling a driver will close all connected devices for that driver!", fg=ansi.Fg.YELLOW))
            
            confirm = Input_Mgr.Instance().yes_no_input(
                f"Are you sure you want to disable driver '{driver_name}'?",
                default=False
            )
            
            if not confirm:
                logger.info("Operation cancelled.")
                return
            
            # Ask for optional description
            description = Input_Mgr.Instance().string_input("Enter reason for disabling (optional)")
            
            # Disable the driver
            result = self.device_driver_manager.disable_driver(driver_name, description or None)
            
            if result.get("status") == "success":
                logger.info(ansi.style(f"Successfully disabled driver: {driver_name}", fg=ansi.Fg.GREEN))
                
                # Report on closed devices
                closed_devices = result.get("closed_devices", [])
                if closed_devices:
                    logger.info(f"Closed {len(closed_devices)} device(s): {', '.join(closed_devices)}")
                
                # Remove from connected_devices if needed
                if driver_name in self.connected_devices:
                    del self.connected_devices[driver_name]
            else:
                logger.error(ansi.style(f"Failed to disable driver: {result.get('message', 'Unknown error')}", fg=ansi.Fg.RED))
            
        except Exception as e:
            logger.error(ansi.style(f"Error disabling driver: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add alias for disable_driver
    do_dd = do_disable_driver

    @cmd2.with_category('Device Commands')
    def do_device_import(self, arg):
        '''Import devices from a JSON file into the database.
        
        Usage: device_import <json_file_path>
        
        Example: device_import conf/devices.json
        
        JSON file format:
        {
            "devices": [
                {
                    "device_id": "serial_001",
                    "name": "Serial Device",
                    "device_type": "Serial",
                    "port": "",
                    "baud_rate": 115200
                },
                {
                    "device_id": "usb_001",
                    "name": "USB Device",
                    "device_type": "USB",
                    "vendor_id": "1234",
                    "product_id": "5678"
                }
            ]
        }
        '''
        import os
        import warnings
        
        if not arg:
            logger.error(ansi.style("Usage: device_import <json_file_path>", fg=ansi.Fg.RED))
            logger.info(ansi.style("Example: device_import conf/devices.json", fg=ansi.Fg.CYAN))
            return
        
        json_file_path = arg.strip()
        
        if not os.path.exists(json_file_path):
            logger.error(ansi.style(f"File not found: {json_file_path}", fg=ansi.Fg.RED))
            return
        
        try:
            logger.info(ansi.style(f"Importing devices from: {json_file_path}", fg=ansi.Fg.CYAN))
            
            # Suppress deprecation warning since we're intentionally using this for import
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                self.device_manager.parse_and_set_device_from_json(json_file_path)
            
            logger.info(ansi.style("Device import completed successfully!", fg=ansi.Fg.GREEN))
            logger.info(ansi.style("Use 'list_devices' or 'lsdev' to view imported devices.", fg=ansi.Fg.CYAN))
            
        except Exception as e:
            logger.error(ansi.style(f"Error importing devices: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add alias for device_import
    do_dimport = do_device_import
