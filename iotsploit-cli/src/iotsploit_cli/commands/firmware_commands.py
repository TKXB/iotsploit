#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from .base_commands import BaseCommands
from iotsploit_core.core.tool_service import get_firmware_service
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class FirmwareCommands(BaseCommands):
    """Firmware-related commands for the SAT Shell"""

    @cmd2.with_category('Firmware Commands')
    def do_list_firmware(self, arg):
        'List all available firmware'
        try:
            firmware_service = get_firmware_service()
            firmware_list = firmware_service.list_firmware()
            
            if not firmware_list:
                self.poutput(ansi.style("No firmware found in registry.", fg=ansi.Fg.YELLOW))
                return
            
            self.poutput(ansi.style(f"\nFound {len(firmware_list)} firmware(s):", fg=ansi.Fg.GREEN))
            self.poutput("-" * 80)
            
            for firmware in firmware_list:
                name = firmware['name']
                device_type = firmware.get('device_type', 'unknown')
                version = firmware.get('version', 'unknown')
                path = firmware.get('path', 'unknown')
                
                # Check if file exists
                from pathlib import Path
                file_exists = Path(path).exists() if path != 'unknown' else False
                status_color = ansi.Fg.GREEN if file_exists else ansi.Fg.RED
                status_text = "✓" if file_exists else "✗"
                
                self.poutput(ansi.style(f"  {name}:", fg=ansi.Fg.CYAN, bold=True))
                self.poutput(f"    Device Type: {device_type}")
                self.poutput(f"    Version: {version}")
                self.poutput(f"    Path: {path}")
                self.poutput(f"    Status: {ansi.style(status_text, fg=status_color)} {'(File exists)' if file_exists else '(File missing)'}")
                
                # Show flash options if available
                flash_options = firmware.get('flash_options', {})
                if flash_options:
                    self.poutput(f"    Flash Options: {flash_options}")
                
                self.poutput("")

        except Exception as e:
            logger.error(f"Error listing firmware: {str(e)}")
            self.poutput(ansi.style(f"Error listing firmware: {str(e)}", fg=ansi.Fg.RED))

    do_lsfw = do_list_firmware

    @cmd2.with_category('Firmware Commands')
    def do_add_firmware(self, arg):
        'Add new firmware to the system'
        try:
            # Parse arguments
            args = arg.split()
            if len(args) < 4:
                self.poutput(ansi.style("Usage: add_firmware <name> <path> <device_type> <version> [flash_options_json]", fg=ansi.Fg.YELLOW))
                self.poutput("Example: add_firmware my_esp32 /path/to/firmware.bin esp32 1.0.0")
                return
            
            name = args[0]
            path = args[1]
            device_type = args[2]
            version = args[3]
            
            # Parse optional flash options
            flash_options = None
            if len(args) > 4:
                import json
                try:
                    flash_options = json.loads(' '.join(args[4:]))
                except json.JSONDecodeError:
                    self.poutput(ansi.style("Invalid JSON format for flash options", fg=ansi.Fg.RED))
                    return
            
            firmware_service = get_firmware_service()
            success = firmware_service.add_firmware(name, path, device_type, version, flash_options)
            
            if success:
                self.poutput(ansi.style(f"Successfully added firmware: {name}", fg=ansi.Fg.GREEN))
            else:
                self.poutput(ansi.style(f"Failed to add firmware: {name}", fg=ansi.Fg.RED))
                
        except Exception as e:
            logger.error(f"Error adding firmware: {str(e)}")
            self.poutput(ansi.style(f"Error adding firmware: {str(e)}", fg=ansi.Fg.RED))

    do_addfw = do_add_firmware

    @cmd2.with_category('Firmware Commands')
    def do_flash_firmware(self, arg):
        'Flash firmware to a device'
        try:
            # Parse arguments
            args = arg.split()
            if len(args) < 2:
                self.poutput(ansi.style("Usage: flash_firmware <firmware_name> <device_name> [options_json]", fg=ansi.Fg.YELLOW))
                self.poutput("Example: flash_firmware esp32s3_wifi_penetration_tool esp32")
                return
            
            firmware_name = args[0]
            device_name = args[1]
            
            # Parse optional options
            options = None
            if len(args) > 2:
                import json
                try:
                    options = json.loads(' '.join(args[2:]))
                except json.JSONDecodeError:
                    self.poutput(ansi.style("Invalid JSON format for options", fg=ansi.Fg.RED))
                    return
            
            firmware_service = get_firmware_service()
            
            # Check if firmware exists
            firmware_info = firmware_service.get_firmware_info(firmware_name)
            if not firmware_info:
                self.poutput(ansi.style(f"Firmware '{firmware_name}' not found", fg=ansi.Fg.RED))
                return
            
            self.poutput(ansi.style(f"Flashing firmware '{firmware_name}' to device '{device_name}'...", fg=ansi.Fg.YELLOW))
            
            # Flash the firmware
            success = firmware_service.flash_registered_firmware(firmware_name, options)
            
            if success:
                self.poutput(ansi.style(f"Successfully flashed firmware: {firmware_name}", fg=ansi.Fg.GREEN))
            else:
                self.poutput(ansi.style(f"Failed to flash firmware: {firmware_name}", fg=ansi.Fg.RED))
                
        except Exception as e:
            logger.error(f"Error flashing firmware: {str(e)}")
            self.poutput(ansi.style(f"Error flashing firmware: {str(e)}", fg=ansi.Fg.RED))

    do_flashfw = do_flash_firmware

    @cmd2.with_category('Firmware Commands')
    def do_remove_firmware(self, arg):
        'Remove firmware from the system'
        try:
            if not arg.strip():
                self.poutput(ansi.style("Usage: remove_firmware <firmware_name>", fg=ansi.Fg.YELLOW))
                self.poutput("Example: remove_firmware esp32_blink")
                return
            
            firmware_name = arg.strip()
            firmware_service = get_firmware_service()
            
            # Check if firmware exists
            firmware_info = firmware_service.get_firmware_info(firmware_name)
            if not firmware_info:
                self.poutput(ansi.style(f"Firmware '{firmware_name}' not found", fg=ansi.Fg.RED))
                return
            
            # Confirm removal
            confirm = input(f"Are you sure you want to remove firmware '{firmware_name}'? (y/N): ")
            if confirm.lower() != 'y':
                self.poutput(ansi.style("Firmware removal cancelled", fg=ansi.Fg.YELLOW))
                return
            
            success = firmware_service.remove_firmware(firmware_name)
            
            if success:
                self.poutput(ansi.style(f"Successfully removed firmware: {firmware_name}", fg=ansi.Fg.GREEN))
            else:
                self.poutput(ansi.style(f"Failed to remove firmware: {firmware_name}", fg=ansi.Fg.RED))
                
        except Exception as e:
            logger.error(f"Error removing firmware: {str(e)}")
            self.poutput(ansi.style(f"Error removing firmware: {str(e)}", fg=ansi.Fg.RED))

    do_rmfw = do_remove_firmware

    @cmd2.with_category('Firmware Commands')
    def do_download_firmware(self, arg):
        'Download firmware from URL'
        try:
            if not arg.strip():
                self.poutput(ansi.style("Usage: download_firmware <url> [output_path]", fg=ansi.Fg.YELLOW))
                self.poutput("Example: download_firmware https://example.com/firmware.bin")
                return
            
            args = arg.split()
            url = args[0]
            output_path = args[1] if len(args) > 1 else None
            
            firmware_service = get_firmware_service()
            self.poutput(ansi.style(f"Downloading firmware from: {url}", fg=ansi.Fg.YELLOW))
            
            result_path = firmware_service.download_firmware(url, output_path)
            
            if result_path:
                self.poutput(ansi.style(f"Successfully downloaded firmware to: {result_path}", fg=ansi.Fg.GREEN))
            else:
                self.poutput(ansi.style("Failed to download firmware", fg=ansi.Fg.RED))
                
        except Exception as e:
            logger.error(f"Error downloading firmware: {str(e)}")
            self.poutput(ansi.style(f"Error downloading firmware: {str(e)}", fg=ansi.Fg.RED))

    do_dlfw = do_download_firmware
