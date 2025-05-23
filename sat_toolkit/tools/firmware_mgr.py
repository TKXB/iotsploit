#!/usr/bin/env python
import os
import logging
import subprocess
import tempfile
import requests
from pathlib import Path
import shutil
from typing import Optional, List, Dict, Union, Any
import json

logger = logging.getLogger(__name__)

# Configuration management for tools
class ToolConfiguration:
    _instance = None
    
    def __init__(self):
        self.config_dir = Path(os.path.expanduser("~/.sat_toolkit"))
        self.config_file = self.config_dir / "tools_config.json"
        self.config = self._load_config()
    
    @classmethod
    def Instance(cls):
        if cls._instance is None:
            cls._instance = ToolConfiguration()
        return cls._instance
    
    def _load_config(self) -> Dict:
        """Load tool configuration from JSON file"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error("Error loading tool configuration file")
                return self._get_default_config()
        return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Return default tool configuration"""
        return {
            "tools": {
                "esptool": {
                    "path": shutil.which('esptool.py'),
                    "environment_var": "ESPTOOL_PATH"
                },
                "openocd": {
                    "path": shutil.which('openocd'),
                    "environment_var": "OPENOCD_PATH"
                },
                "openfpgaloader": {
                    "path": shutil.which('openFPGALoader'),
                    "environment_var": "OPENFPGALOADER_PATH"
                },
                "dfu_util": {
                    "path": shutil.which('dfu-util'),
                    "environment_var": "DFU_UTIL_PATH"
                },
                "greatfet_firmware": {
                    "path": shutil.which('greatfet_firmware'),
                    "environment_var": "GREATFET_FIRMWARE_PATH"
                }
            }
        }
    
    def save_config(self):
        """Save tool configuration to JSON file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
                logger.info(f"Tool configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving tool configuration: {str(e)}")
    
    def get_tool_path(self, tool_name: str) -> Optional[str]:
        """Get path for specified tool, checking configuration, environment variables, and PATH"""
        if tool_name not in self.config.get("tools", {}):
            logger.warning(f"Tool {tool_name} not found in configuration")
            return None
            
        tool_config = self.config["tools"][tool_name]
        
        # First check if we have a configured path
        if tool_config.get("path") and os.path.exists(tool_config["path"]):
            return tool_config["path"]
            
        # Then check for an environment variable
        env_var = tool_config.get("environment_var")
        if env_var and os.environ.get(env_var) and os.path.exists(os.environ.get(env_var)):
            # Update the stored path with the environment variable value
            tool_config["path"] = os.environ.get(env_var)
            self.save_config()
            return tool_config["path"]
            
        # Finally check PATH
        path_from_which = shutil.which(tool_name)
        if path_from_which:
            # Update the stored path with the detected value
            tool_config["path"] = path_from_which
            self.save_config()
            return path_from_which
            
        return None
    
    def set_tool_path(self, tool_name: str, path: str) -> bool:
        """Set custom path for specified tool"""
        if not os.path.exists(path):
            logger.error(f"Path {path} does not exist")
            return False
            
        if tool_name not in self.config.get("tools", {}):
            self.config.setdefault("tools", {})[tool_name] = {
                "path": path,
                "environment_var": f"{tool_name.upper()}_PATH"
            }
        else:
            self.config["tools"][tool_name]["path"] = path
            
        self.save_config()
        logger.info(f"Set {tool_name} path to {path}")
        return True
    
    def get_all_tool_paths(self) -> Dict[str, str]:
        """Get paths for all configured tools"""
        result = {}
        for tool_name in self.config.get("tools", {}):
            path = self.get_tool_path(tool_name)
            if path:
                result[tool_name] = path
        return result


# Generic Programmer base class inspired by LiteX's architecture
class GenericProgrammer:
    def __init__(self, name: str):
        self.name = name
        self.tool_config = ToolConfiguration.Instance()
        
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Flash firmware to device - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement flash_firmware")
    
    def verify_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Verify firmware on device - optional method"""
        logger.info(f"Verification not implemented for {self.name} programmer")
        return True
    
    def call(self, command: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and handle errors"""
        logger.debug(f"Running command: {' '.join(command)}")
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if check and result.returncode != 0:
                msg = f"Error occurred during {self.name} programmer call:\n"
                msg += f"Command: {' '.join(command)}\n"
                msg += f"Error: {result.stderr}\n"
                msg += "Please check:\n"
                msg += f"- {self.name} tool installation\n"
                msg += "- Access permissions\n"
                msg += "- Hardware and cable connection\n"
                msg += "- Firmware file existence and format"
                logger.error(msg)
                raise RuntimeError(msg)
            return result
        except Exception as e:
            logger.error(f"Exception during command execution: {str(e)}")
            raise

# FPGA Programmer base class for FPGA-specific operations
class FPGAProgrammer(GenericProgrammer):
    def __init__(self, name: str):
        super().__init__(name)
    
    def load_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Load bitstream to FPGA SRAM (temporary, lost on power cycle)"""
        raise NotImplementedError("Subclasses must implement load_bitstream")
    
    def flash_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Flash bitstream to FPGA's configuration flash (permanent)"""
        raise NotImplementedError("Subclasses must implement flash_bitstream")
    
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Generic flash method that routes to either load_bitstream or flash_bitstream"""
        # Determine if we're loading to SRAM or flashing to SPI flash
        target = options.get('target', 'sram').lower()
        
        if target == 'sram':
            logger.info(f"Loading bitstream to FPGA SRAM (temporary): {firmware_path}")
            return self.load_bitstream(firmware_path, options)
        elif target in ['flash', 'spi', 'spiflash']:
            logger.info(f"Flashing bitstream to FPGA configuration flash (permanent): {firmware_path}")
            return self.flash_bitstream(firmware_path, options)
        else:
            logger.error(f"Unknown target '{target}'. Use 'sram' for temporary or 'flash' for permanent programming")
            return False

# OpenFPGALoader for FPGA gateware programming
class OpenFPGALoader(FPGAProgrammer):
    def __init__(self):
        super().__init__("OpenFPGALoader")
        self.openfpgaloader_path = self.tool_config.get_tool_path("openfpgaloader")
        if not self.openfpgaloader_path:
            logger.warning("openFPGALoader not found. Please install it or set its path using ToolConfiguration")
    
    def _build_base_command(self, options: Dict[str, Any]) -> List[str]:
        """Build the base command with common options"""
        # Use tool_path from options if provided, otherwise use configured path
        tool_path = options.get('tool_path')
        if tool_path and os.path.exists(tool_path):
            cmd = [tool_path]
            # Update the configured path if needed
            self.tool_config.set_tool_path("openfpgaloader", tool_path)
        else:
            cmd = [self.openfpgaloader_path]
        
        # Add board option if specified
        board = options.get('board', '')
        if board:
            cmd.extend(['--board', board])
        
        # Add FPGA part/device if specified
        fpga_part = options.get('fpga_part', '')
        if fpga_part:
            cmd.extend(['--fpga-part', fpga_part])
        
        # Add cable option if specified
        cable = options.get('cable', '')
        if cable:
            cmd.extend(['--cable', cable])
        
        # Add frequency option if specified
        freq = options.get('freq', 0)
        if freq:
            cmd.extend(['--freq', str(int(float(freq)))])
        
        # Add index in JTAG chain if specified
        index_chain = options.get('index_chain')
        if index_chain is not None:
            cmd.extend(['--index-chain', str(int(index_chain))])
        
        # Add FTDI serial if specified
        ftdi_serial = options.get('ftdi_serial')
        if ftdi_serial is not None:
            cmd.extend(['--ftdi-serial', str(ftdi_serial)])
            
        return cmd
    
    def load_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Load bitstream to FPGA SRAM (temporary, lost on power cycle)"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.openfpgaloader_path = options.get('tool_path')
            self.tool_config.set_tool_path("openfpgaloader", self.openfpgaloader_path)
        
        if not self.openfpgaloader_path:
            logger.error("openFPGALoader not found. Please install it or set its path")
            return False
        
        # Build base command
        cmd = self._build_base_command(options)
        
        # Add bitstream path for direct FPGA configuration
        cmd.extend(['--bitstream', bitstream_path])
        
        # Handle any additional options
        for key, value in options.items():
            if key not in ['board', 'fpga_part', 'cable', 'freq', 'index_chain', 
                          'ftdi_serial', 'target', 'tool_path']:
                cmd_key = f"--{key.replace('_', '-')}"
                if value is not None:
                    cmd.append(cmd_key)
                    if not isinstance(value, bool):
                        cmd.append(str(value))
                elif isinstance(value, bool) and value:
                    cmd.append(cmd_key)
        
        try:
            logger.info(f"Loading bitstream to FPGA SRAM: {bitstream_path}")
            logger.debug(f"Command: {' '.join(cmd)}")
            self.call(cmd)
            logger.info("FPGA bitstream loaded successfully to SRAM")
            return True
        except Exception as e:
            logger.error(f"Failed to load bitstream to FPGA SRAM: {str(e)}")
            return False
    
    def flash_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Flash bitstream to FPGA's configuration flash (permanent)"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.openfpgaloader_path = options.get('tool_path')
            self.tool_config.set_tool_path("openfpgaloader", self.openfpgaloader_path)
        
        if not self.openfpgaloader_path:
            logger.error("openFPGALoader not found. Please install it or set its path")
            return False
        
        # Build base command
        cmd = self._build_base_command(options)
        
        # Add write-flash command
        cmd.extend(['--write-flash', '--bitstream', bitstream_path])
        
        # External flash option
        external_flash = options.get('external_flash', False)
        if external_flash:
            cmd.append('--external-flash')
        
        # Flash offset/address
        address = options.get('address', 0)
        if address:
            cmd.extend(['--offset', str(address)])
        
        # Unprotect flash option
        unprotect_flash = options.get('unprotect_flash', False)
        if unprotect_flash:
            cmd.append('--unprotect-flash')
        
        # Verify option
        verify = options.get('verify', False)
        if verify:
            cmd.append('--verify')
        
        # Handle any additional options
        for key, value in options.items():
            if key not in ['board', 'fpga_part', 'cable', 'freq', 'index_chain', 
                          'ftdi_serial', 'external_flash', 'address', 
                          'verify', 'unprotect_flash', 'target', 'tool_path']:
                cmd_key = f"--{key.replace('_', '-')}"
                if value is not None:
                    cmd.append(cmd_key)
                    if not isinstance(value, bool):
                        cmd.append(str(value))
                elif isinstance(value, bool) and value:
                    cmd.append(cmd_key)
        
        try:
            logger.info(f"Flashing bitstream to FPGA configuration flash: {bitstream_path}")
            logger.debug(f"Command: {' '.join(cmd)}")
            self.call(cmd)
            logger.info("FPGA bitstream flashed successfully to configuration flash")
            return True
        except Exception as e:
            logger.error(f"Failed to flash bitstream to FPGA configuration flash: {str(e)}")
            return False
    
    def verify_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Verify firmware on FPGA - only applicable for flash operations"""
        target = options.get('target', 'sram').lower()
        
        if target == 'sram':
            logger.warning("Verification is not supported for SRAM loading")
            return True
        
        # For flash operations, we can use the same flash_bitstream method with verify=True
        verify_options = options.copy()
        verify_options['verify'] = True
        return self.flash_bitstream(firmware_path, verify_options)

# OpenOCD FPGA Programmer
class OpenOCDFPGAProgrammer(FPGAProgrammer):
    def __init__(self):
        super().__init__("OpenOCD FPGA")
        self.openocd_path = self.tool_config.get_tool_path("openocd")
        if not self.openocd_path:
            logger.warning("openocd not found. Please install it or set its path using ToolConfiguration")
    
    def load_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Load bitstream to FPGA SRAM using OpenOCD"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.openocd_path = options.get('tool_path')
            self.tool_config.set_tool_path("openocd", self.openocd_path)
        
        if not self.openocd_path:
            logger.error("openocd not found. Please install it or set its path")
            return False
        
        config_file = options.get('config')
        if not config_file:
            logger.error("OpenOCD requires a config file specified in options")
            return False
        
        # Create temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cfg', delete=False) as f:
            script_path = f.name
            f.write("; ".join([
                "init",
                f"pld load 0 {{{bitstream_path}}}",
                "exit",
            ]))
        
        try:
            logger.info(f"Loading bitstream to FPGA SRAM using OpenOCD: {bitstream_path}")
            cmd = [self.openocd_path, '-f', config_file, '-f', script_path]
            self.call(cmd)
            logger.info("FPGA bitstream loaded successfully to SRAM")
            os.unlink(script_path)
            return True
        except Exception as e:
            logger.error(f"Failed to load bitstream to FPGA SRAM: {str(e)}")
            if os.path.exists(script_path):
                os.unlink(script_path)
            return False
    
    def flash_bitstream(self, bitstream_path: str, options: Dict[str, Any]) -> bool:
        """Flash bitstream to FPGA's configuration flash using OpenOCD"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.openocd_path = options.get('tool_path')
            self.tool_config.set_tool_path("openocd", self.openocd_path)
        
        if not self.openocd_path:
            logger.error("openocd not found. Please install it or set its path")
            return False
        
        config_file = options.get('config')
        if not config_file:
            logger.error("OpenOCD requires a config file specified in options")
            return False
        
        flash_proxy = options.get('flash_proxy')
        if not flash_proxy:
            logger.error("OpenOCD requires a flash proxy bitstream for SPI flash programming")
            return False
        
        address = options.get('address', 0)
        set_qe = options.get('set_qe', False)
        
        # Create temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cfg', delete=False) as f:
            script_path = f.name
            
            script_commands = [
                "init",
                f"jtagspi_init 0 {{{flash_proxy}}}"
            ]
            
            # Add any initialization commands
            init_commands = options.get('init_commands', [])
            script_commands.extend(init_commands)
            
            # Add set_qe command if needed
            if set_qe:
                script_commands.append("jtagspi set_qe 0 1")
            
            # Add program command
            script_commands.append(f"jtagspi_program {{{bitstream_path}}} 0x{address:x}")
            
            # Add fpga_program command to load from flash
            script_commands.append("fpga_program")
            
            # Add exit command
            script_commands.append("exit")
            
            f.write("; ".join(script_commands))
        
        try:
            logger.info(f"Flashing bitstream to FPGA configuration flash using OpenOCD: {bitstream_path}")
            cmd = [self.openocd_path, '-f', config_file, '-f', script_path]
            self.call(cmd)
            logger.info("FPGA bitstream flashed successfully to configuration flash")
            os.unlink(script_path)
            return True
        except Exception as e:
            logger.error(f"Failed to flash bitstream to FPGA configuration flash: {str(e)}")
            if os.path.exists(script_path):
                os.unlink(script_path)
            return False

# ESP32 Programmer using esptool.py
class ESP32Programmer(GenericProgrammer):
    def __init__(self):
        super().__init__("ESP32")
        self.esptool_path = self.tool_config.get_tool_path("esptool")
        if not self.esptool_path:
            logger.warning("esptool.py not found. Please install it using: pip install esptool or set its path using ToolConfiguration")
    
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Flash firmware to ESP32 device"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.esptool_path = options.get('tool_path')
            self.tool_config.set_tool_path("esptool", self.esptool_path)
        
        if not self.esptool_path:
            logger.error("esptool.py not found. Please install it using: pip install esptool or set its path")
            return False
            
        port = options.get('port', '/dev/ttyUSB0')
        baud = options.get('baud', '921600')
        flash_mode = options.get('flash_mode', 'dio')
        flash_freq = options.get('flash_freq', '40m')
        flash_size = options.get('flash_size', 'detect')
        address = options.get('address', '0x0')
        chip = options.get('chip', 'esp32')
        
        cmd = [
            self.esptool_path,
            '--chip', chip,
            '-p', port,
            '-b', baud,
            'write_flash',
            '--flash_mode', flash_mode,
            '--flash_freq', flash_freq,
            '--flash_size', flash_size,
            address, firmware_path
        ]
        
        try:
            logger.info(f"Flashing {chip} firmware: {firmware_path} to address {address}")
            result = self.call(cmd)
            logger.info(f"{chip} firmware flashed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to flash {chip} firmware: {str(e)}")
            return False
            
    def verify_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Verify firmware on ESP32 device"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.esptool_path = options.get('tool_path')
            self.tool_config.set_tool_path("esptool", self.esptool_path)
        
        if not self.esptool_path:
            logger.error("esptool.py not found. Please install it using: pip install esptool or set its path")
            return False
            
        port = options.get('port', '/dev/ttyUSB0')
        baud = options.get('baud', '921600')
        address = options.get('address', '0x0')
        chip = options.get('chip', 'esp32')
        
        cmd = [
            self.esptool_path,
            '--chip', chip,
            '-p', port,
            '-b', baud,
            'verify_flash',
            address, firmware_path
        ]
        
        try:
            logger.info(f"Verifying {chip} firmware: {firmware_path}")
            result = self.call(cmd)
            logger.info(f"{chip} firmware verified successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to verify {chip} firmware: {str(e)}")
            return False

# STM32 Programmer using OpenOCD
class STM32Programmer(GenericProgrammer):
    def __init__(self):
        super().__init__("STM32")
        self.openocd_path = self.tool_config.get_tool_path("openocd")
        if not self.openocd_path:
            logger.warning("openocd not found. Please install it or set its path using ToolConfiguration")
        
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Flash firmware to STM32 device"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.openocd_path = options.get('tool_path')
            self.tool_config.set_tool_path("openocd", self.openocd_path)
        
        if not self.openocd_path:
            logger.error("openocd not found. Please install it or set its path")
            return False
            
        interface = options.get('interface', 'stlink')
        target = options.get('target', 'stm32f4x')
        
        # Create temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cfg', delete=False) as f:
            script_path = f.name
            f.write(f"""
source [find interface/{interface}.cfg]
transport select hla_swd
source [find target/{target}.cfg]
reset_config srst_only
init
reset halt
flash write_image erase {firmware_path} 0x08000000
reset run
exit
""")
        
        try:
            logger.info(f"Flashing STM32 firmware: {firmware_path}")
            cmd = [self.openocd_path, '-f', script_path]
            result = self.call(cmd)
            logger.info("STM32 firmware flashed successfully")
            os.unlink(script_path)
            return True
        except Exception as e:
            logger.error(f"Failed to flash STM32 firmware: {str(e)}")
            if os.path.exists(script_path):
                os.unlink(script_path)
            return False

# DFU Programmer for USB DFU devices
class DFUProgrammer(GenericProgrammer):
    def __init__(self):
        super().__init__("DFU")
        self.dfu_util_path = self.tool_config.get_tool_path("dfu_util")
        if not self.dfu_util_path:
            logger.warning("dfu-util not found. Please install it or set its path using ToolConfiguration")
        
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Flash firmware to DFU device"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.dfu_util_path = options.get('tool_path')
            self.tool_config.set_tool_path("dfu_util", self.dfu_util_path)
        
        if not self.dfu_util_path:
            logger.error("dfu-util not found. Please install it or set its path")
            return False
            
        vid = options.get('vid')
        pid = options.get('pid')
        alt = options.get('alt')
        
        if not vid or not pid:
            logger.error("VID and PID are required for DFU programming")
            return False
            
        try:
            logger.info(f"Flashing firmware via DFU: {firmware_path}")
            cmd = [self.dfu_util_path, '-d', f"{vid}:{pid}", '-D', firmware_path]
            
            if alt is not None:
                cmd.extend(['-a', str(alt)])
                
            self.call(cmd)
            logger.info("Firmware flashed successfully via DFU")
            return True
        except Exception as e:
            logger.error(f"Failed to flash firmware via DFU: {str(e)}")
            return False

# GreatFET Programmer for flashing GreatFET devices
class GreatFETProgrammer(GenericProgrammer):
    def __init__(self):
        super().__init__("GreatFET")
        self.greatfet_firmware_path = self.tool_config.get_tool_path("greatfet_firmware")
        if not self.greatfet_firmware_path:
            logger.warning("greatfet_firmware not found. Please install it or set its path using ToolConfiguration")
    
    def flash_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Flash firmware to GreatFET device"""
        # Update tool path from options if provided
        if options.get('tool_path') and os.path.exists(options.get('tool_path')):
            self.greatfet_firmware_path = options.get('tool_path')
            self.tool_config.set_tool_path("greatfet_firmware", self.greatfet_firmware_path)
        
        if not self.greatfet_firmware_path:
            logger.error("greatfet_firmware not found. Please install it or set its path")
            return False
        
        # Determine if we're loading to SRAM or flashing to SPI flash
        target = options.get('target', 'spi').lower()
        
        try:
            if target == 'sram':
                # Flash to SRAM (temporary)
                logger.info(f"Loading firmware to GreatFET SRAM: {firmware_path}")
                cmd = [self.greatfet_firmware_path, '-V', firmware_path]
            else:
                # Flash to SPI flash (permanent)
                logger.info(f"Flashing firmware to GreatFET SPI flash: {firmware_path}")
                cmd = [self.greatfet_firmware_path, '-w', firmware_path]
            
            # Add serial number if specified
            serial = options.get('serial')
            if serial:
                cmd.extend(['-s', serial])
            
            # Add board option if specified
            board = options.get('board')
            if board:
                cmd.extend(['-b', board])
            
            # Execute the command
            self.call(cmd)
            
            if target == 'sram':
                logger.info("GreatFET firmware loaded successfully to SRAM")
            else:
                logger.info("GreatFET firmware flashed successfully to SPI flash")
            
            return True
        except Exception as e:
            if target == 'sram':
                logger.error(f"Failed to load GreatFET firmware to SRAM: {str(e)}")
            else:
                logger.error(f"Failed to flash GreatFET firmware to SPI flash: {str(e)}")
            return False
    
    def verify_firmware(self, firmware_path: str, options: Dict[str, Any]) -> bool:
        """Verify firmware on GreatFET device - not implemented"""
        logger.warning("Firmware verification not implemented for GreatFET devices")
        return True

class FirmwareManager:
    _instance = None
    
    def __init__(self):
        self.firmware_dir = Path('firmware')
        self.firmware_dir.mkdir(exist_ok=True)
        self.manifest_file = self.firmware_dir / 'firmware_manifest.json'
        self.manifests = self._load_manifests()
        
        # Get tool configuration
        self.tool_config = ToolConfiguration.Instance()
        
        # Initialize programmers
        self.programmers = {
            'esp32': ESP32Programmer(),
            'stm32': STM32Programmer(),
            'dfu': DFUProgrammer(),
            'fpga': OpenFPGALoader(),
            'fpga_openocd': OpenOCDFPGAProgrammer(),
            'greatfet': GreatFETProgrammer()
        }

    @classmethod
    def Instance(cls):
        if cls._instance is None:
            cls._instance = FirmwareManager()
        return cls._instance

    def _load_manifests(self) -> Dict:
        """Load firmware manifests from JSON file"""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error("Error loading firmware manifest file")
                return {}
        return {}

    def _save_manifests(self):
        """Save firmware manifests to JSON file"""
        try:
            with open(self.manifest_file, 'w') as f:
                json.dump(self.manifests, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving firmware manifest: {str(e)}")

    def set_tool_path(self, tool_name: str, path: str) -> bool:
        """Set custom path for a specific tool"""
        return self.tool_config.set_tool_path(tool_name, path)

    def get_tool_path(self, tool_name: str) -> Optional[str]:
        """Get the configured path for a specific tool"""
        return self.tool_config.get_tool_path(tool_name)

    def get_all_tool_paths(self) -> Dict[str, str]:
        """Get paths for all configured tools"""
        return self.tool_config.get_all_tool_paths()

    def init_workspace(self, name: str) -> bool:
        """Initialize a new West workspace"""
        try:
            workspace_path = self.firmware_dir / name
            if workspace_path.exists():
                logger.warning(f"Workspace {name} already exists")
                return False

            west_path = self.tool_config.get_tool_path("west") or shutil.which('west')
            if not west_path:
                logger.error("West tool not found. Please install it using: pip install west")
                return False

            cmd = [west_path, 'init', '-m', str(workspace_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully initialized workspace: {name}")
                return True
            else:
                logger.error(f"Failed to initialize workspace: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing workspace: {str(e)}")
            return False

    def add_firmware(self, name: str, path: str, device_type: str, version: str, 
                    flash_options: Optional[Dict[str, Any]] = None) -> bool:
        """Add firmware to manifest"""
        try:
            firmware_path = Path(path)
            if not firmware_path.exists():
                logger.error(f"Firmware file not found: {path}")
                return False

            firmware_info = {
                "path": str(firmware_path),
                "device_type": device_type,
                "version": version
            }
            
            # Add flash options if provided
            if flash_options:
                firmware_info["flash_options"] = flash_options

            self.manifests[name] = firmware_info
            self._save_manifests()
            logger.info(f"Successfully added firmware: {name}")
            return True

        except Exception as e:
            logger.error(f"Error adding firmware: {str(e)}")
            return False

    def list_firmware(self) -> List[Dict]:
        """List all available firmware"""
        return [{"name": name, **info} for name, info in self.manifests.items()]

    def flash_firmware(self, name: str, options: Optional[Dict[str, Any]] = None) -> bool:
        """Flash firmware using appropriate programmer based on device type"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            firmware_info = self.manifests[name]
            device_type = firmware_info.get('device_type', '').lower()
            firmware_path = firmware_info['path']

            # Merge options from manifest and provided options
            flash_options = firmware_info.get('flash_options', {}).copy()
            if options:
                flash_options.update(options)
            
            # Select appropriate programmer
            programmer = None
            for device_prefix, prog in self.programmers.items():
                if device_type.startswith(device_prefix):
                    programmer = prog
                    break
            
            if not programmer:
                logger.error(f"Unsupported device type: {device_type}")
                return False

            logger.info(f"Flashing firmware: {name} using {programmer.name} programmer")
            result = programmer.flash_firmware(firmware_path, flash_options)
            
            if result:
                logger.info(f"Successfully flashed firmware: {name}")
                return True
            else:
                logger.error(f"Failed to flash firmware: {name}")
                return False

        except Exception as e:
            logger.error(f"Error flashing firmware: {str(e)}")
            return False
    
    def verify_firmware(self, name: str, options: Optional[Dict[str, Any]] = None) -> bool:
        """Verify firmware using appropriate programmer based on device type"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            firmware_info = self.manifests[name]
            device_type = firmware_info.get('device_type', '').lower()
            firmware_path = firmware_info['path']
            
            # Merge options from manifest and provided options
            verify_options = firmware_info.get('flash_options', {}).copy()
            if options:
                verify_options.update(options)
            
            # Select appropriate programmer
            programmer = None
            for device_prefix, prog in self.programmers.items():
                if device_type.startswith(device_prefix):
                    programmer = prog
                    break
            
            if not programmer:
                logger.error(f"Unsupported device type: {device_type}")
                return False
            
            logger.info(f"Verifying firmware: {name} using {programmer.name} programmer")
            result = programmer.verify_firmware(firmware_path, verify_options)
            
            if result:
                logger.info(f"Successfully verified firmware: {name}")
                return True
            else:
                logger.error(f"Failed to verify firmware: {name}")
                return False

        except Exception as e:
            logger.error(f"Error verifying firmware: {str(e)}")
            return False

    def remove_firmware(self, name: str) -> bool:
        """Remove firmware from manifest"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            del self.manifests[name]
            self._save_manifests()
            logger.info(f"Successfully removed firmware: {name}")
            return True

        except Exception as e:
            logger.error(f"Error removing firmware: {str(e)}")
            return False

    def get_firmware_info(self, name: str) -> Optional[Dict]:
        """Get information about specific firmware"""
        return self.manifests.get(name) 
    
    def download_firmware(self, url: str, output_path: Optional[str] = None) -> Optional[str]:
        """Download firmware from URL"""
        try:
            logger.info(f"Downloading firmware from: {url}")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            if not output_path:
                # Extract filename from URL or use a default name
                filename = url.split('/')[-1]
                if not filename:
                    filename = "downloaded_firmware.bin"
                output_path = str(self.firmware_dir / filename)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Firmware downloaded to: {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Error downloading firmware: {str(e)}")
            return None

    def load_fpga_bitstream(self, name: str, options: Optional[Dict[str, Any]] = None) -> bool:
        """Load bitstream to FPGA SRAM (temporary, lost on power cycle)"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            firmware_info = self.manifests[name]
            device_type = firmware_info.get('device_type', '').lower()
            firmware_path = firmware_info['path']
            
            # Check if this is an FPGA device
            if not any(device_type.startswith(prefix) for prefix in ['fpga']):
                logger.error(f"Device type '{device_type}' is not an FPGA device")
                return False
            
            # Merge options from manifest and provided options
            load_options = firmware_info.get('flash_options', {}).copy()
            if options:
                load_options.update(options)
            
            # Set target to SRAM
            load_options['target'] = 'sram'
            
            # Select appropriate programmer
            programmer = None
            for device_prefix, prog in self.programmers.items():
                if device_type == device_prefix:
                    programmer = prog
                    break
            
            # Default to OpenFPGALoader if no specific match
            if not programmer and isinstance(self.programmers.get('fpga'), FPGAProgrammer):
                programmer = self.programmers['fpga']
            
            if not programmer or not isinstance(programmer, FPGAProgrammer):
                logger.error(f"No suitable FPGA programmer found for device type: {device_type}")
                return False
            
            logger.info(f"Loading bitstream to FPGA SRAM: {name} using {programmer.name}")
            result = programmer.flash_firmware(firmware_path, load_options)
            
            if result:
                logger.info(f"Successfully loaded bitstream to FPGA SRAM: {name}")
                return True
            else:
                logger.error(f"Failed to load bitstream to FPGA SRAM: {name}")
                return False

        except Exception as e:
            logger.error(f"Error loading bitstream to FPGA SRAM: {str(e)}")
            return False
    
    def flash_fpga_bitstream(self, name: str, options: Optional[Dict[str, Any]] = None) -> bool:
        """Flash bitstream to FPGA configuration flash (permanent)"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            firmware_info = self.manifests[name]
            device_type = firmware_info.get('device_type', '').lower()
            firmware_path = firmware_info['path']
            
            # Check if this is an FPGA device
            if not any(device_type.startswith(prefix) for prefix in ['fpga']):
                logger.error(f"Device type '{device_type}' is not an FPGA device")
                return False
            
            # Merge options from manifest and provided options
            flash_options = firmware_info.get('flash_options', {}).copy()
            if options:
                flash_options.update(options)
            
            # Set target to flash
            flash_options['target'] = 'flash'
            
            # Select appropriate programmer
            programmer = None
            for device_prefix, prog in self.programmers.items():
                if device_type == device_prefix:
                    programmer = prog
                    break
            
            # Default to OpenFPGALoader if no specific match
            if not programmer and isinstance(self.programmers.get('fpga'), FPGAProgrammer):
                programmer = self.programmers['fpga']
            
            if not programmer or not isinstance(programmer, FPGAProgrammer):
                logger.error(f"No suitable FPGA programmer found for device type: {device_type}")
                return False
            
            logger.info(f"Flashing bitstream to FPGA configuration flash: {name} using {programmer.name}")
            result = programmer.flash_firmware(firmware_path, flash_options)
            
            if result:
                logger.info(f"Successfully flashed bitstream to FPGA configuration flash: {name}")
                return True
            else:
                logger.error(f"Failed to flash bitstream to FPGA configuration flash: {name}")
                return False

        except Exception as e:
            logger.error(f"Error flashing bitstream to FPGA configuration flash: {str(e)}")
            return False