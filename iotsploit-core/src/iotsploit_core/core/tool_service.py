#!/usr/bin/env python3
"""Unified tool management and execution service for plugins."""

import json
import logging
from typing import Dict, List, Optional, Any

from .tool_manager import get_tool_manager, ExecutionResult

logger = logging.getLogger(__name__)

class ToolService:
    """
    Tool Management Service
    
    Provides a simple interface for plugins to manage and execute third-party tools
    without worrying about path resolution, version checking, or cross-platform compatibility.
    """
    
    def __init__(self):
        self.tool_manager = get_tool_manager()  # Use singleton instead of creating new instance
        self.logger = logging.getLogger("tool_service")
        self._registered_tools = set()
    
    def register_tool(self, tool_name: str, min_version: str = None, 
                     aliases: List[str] = None, required: bool = True) -> bool:
        """
        Register a tool for use by the calling plugin.
        
        Args:
            tool_name: Name of the tool (e.g., 'esptool', 'nmap')
            min_version: Minimum required version (optional)
            aliases: Alternative names for the tool (optional)
            required: Whether this tool is required for plugin operation
            
        Returns:
            bool: True if tool is available, False otherwise
        """
        self.logger.debug(f"Registering tool: {tool_name}")
        
        # Add tool to registry if not already present
        if not self.tool_manager.registry.get_tool(tool_name):
            success = self.tool_manager.add_tool(
                name=tool_name,
                aliases=aliases or [],
                min_version=min_version
            )
            
            if not success and required:
                self.logger.error(f"Required tool '{tool_name}' is not available")
                return False
            elif not success:
                self.logger.warning(f"Optional tool '{tool_name}' is not available")
        
        self._registered_tools.add(tool_name)
        return self.tool_manager.is_available(tool_name)
    
    def is_tool_available(self, tool_name: str) -> bool:
        """
        Check if a tool is available for use.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            bool: True if tool is available, False otherwise
        """
        return self.tool_manager.is_available(tool_name)
    
    def get_tool_path(self, tool_name: str) -> Optional[str]:
        """
        Get the full path to a tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            str: Full path to the tool, or None if not found
        """
        tool_info = self.tool_manager.registry.get_tool(tool_name)
        if tool_info and tool_info.path:
            return tool_info.path
        return None
    
    def get_tool_version(self, tool_name: str) -> Optional[str]:
        """
        Get the version of a tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            str: Version string, or None if not available
        """
        tool_info = self.tool_manager.registry.get_tool(tool_name)
        if tool_info:
            return tool_info.version
        return None
    
    def execute_tool(self, tool_name: str, args: List[str], 
                    working_dir: Optional[str] = None,
                    env: Optional[Dict[str, str]] = None,
                    timeout: Optional[int] = None,
                    check_availability: bool = True) -> ExecutionResult:
        """
        Execute a tool with the given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            args: List of command-line arguments
            working_dir: Working directory for execution (optional)
            env: Environment variables (optional)
            timeout: Execution timeout in seconds (optional)
            check_availability: Whether to check tool availability first
            
        Returns:
            ExecutionResult: Result of the tool execution
            
        Raises:
            RuntimeError: If tool is not available
            ValueError: If tool is not registered
        """
        if check_availability and not self.is_tool_available(tool_name):
            raise RuntimeError(f"Tool '{tool_name}' is not available")
        
        self.logger.info(f"Executing {tool_name} with args: {args}")
        
        try:
            result = self.tool_manager.execute(
                tool_name, args, 
                working_dir=working_dir,
                env=env,
                timeout=timeout
            )
            
            if result.success:
                self.logger.debug(f"{tool_name} executed successfully in {result.execution_time:.2f}s")
            else:
                self.logger.warning(f"{tool_name} failed with return code {result.return_code}")
                if result.stderr:
                    self.logger.debug(f"stderr: {result.stderr}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to execute {tool_name}: {e}")
            raise
    
    def execute_tool_simple(self, tool_name: str, args: List[str], **kwargs) -> bool:
        """
        Simple tool execution that returns only success/failure.
        
        Args:
            tool_name: Name of the tool to execute
            args: List of command-line arguments
            **kwargs: Additional arguments passed to execute_tool
            
        Returns:
            bool: True if execution was successful, False otherwise
        """
        try:
            result = self.execute_tool(tool_name, args, **kwargs)
            return result.success
        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}")
            return False
    
    def get_tool_output(self, tool_name: str, args: List[str], **kwargs) -> Optional[str]:
        """
        Execute a tool and return its output.
        
        Args:
            tool_name: Name of the tool to execute
            args: List of command-line arguments
            **kwargs: Additional arguments passed to execute_tool
            
        Returns:
            str: Tool output (stdout), or None if execution failed
        """
        try:
            result = self.execute_tool(tool_name, args, **kwargs)
            return result.stdout if result.success else None
        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}")
            return None
    
    def check_tool_requirements(self, required_tools: List[str], 
                               optional_tools: List[str] = None) -> Dict[str, bool]:
        """
        Check availability of multiple tools.
        
        Args:
            required_tools: List of required tool names
            optional_tools: List of optional tool names
            
        Returns:
            dict: Tool name -> availability mapping
        """
        results = {}
        
        for tool in required_tools:
            is_available = self.is_tool_available(tool)
            results[tool] = is_available
            if not is_available:
                self.logger.error(f"Required tool '{tool}' is not available")
        
        for tool in (optional_tools or []):
            is_available = self.is_tool_available(tool)
            results[tool] = is_available
            if not is_available:
                self.logger.warning(f"Optional tool '{tool}' is not available")
        
        return results
    
    def get_registered_tools(self) -> List[str]:
        """
        Get list of tools registered by this service instance.
        
        Returns:
            list: Names of registered tools
        """
        return list(self._registered_tools)

class BaseProgrammer:
    """Base class for all programmers"""
    
    def __init__(self, tool_service: 'ToolService'):
        self.tool_service = tool_service
        self.logger = logging.getLogger(f"programmer.{self.__class__.__name__}")
    
    def is_tool_available(self, tool_name: str) -> bool:
        """Check if required tool is available"""
        return self.tool_service.is_tool_available(tool_name)
    
    def execute_tool(self, tool_name: str, args: List[str], **kwargs):
        """Execute tool through the tool service"""
        return self.tool_service.execute_tool(tool_name, args, **kwargs)

class ESP32Programmer(BaseProgrammer):
    """ESP32 device programmer using esptool"""
    
    def __init__(self, tool_service: 'ToolService'):
        super().__init__(tool_service)
        self.tool_service.register_tool('esptool', required=False)
    
    def flash_single(self, port: str, firmware_path: str, address: str = "0x10000",
                    chip: str = "esp32", baud: str = "460800") -> 'ExecutionResult':
        """
        Flash single firmware file to ESP32 device.
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0')
            firmware_path: Path to firmware file
            address: Flash address (default: 0x10000)
            chip: Chip type (default: esp32)
            baud: Baud rate (default: 460800)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('esptool'):
            raise RuntimeError("esptool is not available")
        
        args = [
            '--chip', chip,
            '--port', port,
            '--baud', baud,
            'write_flash', address, firmware_path
        ]
        
        return self.execute_tool('esptool', args, timeout=300)
    
    def flash_multi(self, port: str, files: List[Dict[str, str]], 
                   chip: str = "esp32s3", baud: str = "460800",
                   flash_mode: str = "dio", flash_freq: str = "80m",
                   flash_size: str = "2MB") -> 'ExecutionResult':
        """
        Flash multiple files to ESP32 device (bootloader, partition table, app).
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0')
            files: List of dicts with 'address' and 'path' keys
            chip: Chip type (default: esp32s3)
            baud: Baud rate (default: 460800)
            flash_mode: Flash mode (default: dio)
            flash_freq: Flash frequency (default: 80m)
            flash_size: Flash size (default: 2MB)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('esptool'):
            raise RuntimeError("esptool is not available")
        
        args = [
            '--chip', chip,
            '--port', port,
            '--baud', baud,
            '--before', 'default_reset',
            '--after', 'hard_reset',
            'write_flash',
            '--flash_mode', flash_mode,
            '--flash_freq', flash_freq,
            '--flash_size', flash_size
        ]
        
        # Add each file with its address
        for file_info in files:
            args.extend([file_info['address'], file_info['path']])
        
        return self.execute_tool('esptool', args, timeout=300)
    
    def erase_flash(self, port: str, chip: str = "esp32s3", 
                   baud: str = "460800") -> 'ExecutionResult':
        """Erase ESP32 flash memory"""
        if not self.is_tool_available('esptool'):
            raise RuntimeError("esptool is not available")
        
        args = [
            '--chip', chip,
            '--port', port,
            '--baud', baud,
            'erase_flash'
        ]
        
        return self.execute_tool('esptool', args, timeout=120)
    
    def get_chip_info(self, port: str, baud: str = "460800") -> 'ExecutionResult':
        """Get ESP32 chip information"""
        if not self.is_tool_available('esptool'):
            raise RuntimeError("esptool is not available")
        
        args = [
            '--port', port,
            '--baud', baud,
            'chip_id'
        ]
        
        return self.execute_tool('esptool', args, timeout=30)

class STM32Programmer(BaseProgrammer):
    """STM32 device programmer using OpenOCD"""
    
    def __init__(self, tool_service: 'ToolService'):
        super().__init__(tool_service)
        self.tool_service.register_tool('openocd', required=False)
    
    def flash_firmware(self, firmware_path: str, interface: str = "stlink", 
                      target: str = "stm32f4x") -> 'ExecutionResult':
        """
        Flash firmware to STM32 device using OpenOCD.
        
        Args:
            firmware_path: Path to firmware file
            interface: Debug interface (default: stlink)
            target: Target configuration (default: stm32f4x)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('openocd'):
            raise RuntimeError("openocd is not available")
        
        import tempfile
        import os
        
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
            args = ['-f', script_path]
            result = self.execute_tool('openocd', args, timeout=300)
            os.unlink(script_path)
            return result
        except Exception:
            if os.path.exists(script_path):
                os.unlink(script_path)
            raise

class DFUProgrammer(BaseProgrammer):
    """DFU device programmer using dfu-util"""
    
    def __init__(self, tool_service: 'ToolService'):
        super().__init__(tool_service)
        self.tool_service.register_tool('dfu-util', required=False)
    
    def flash_firmware(self, firmware_path: str, vid: str, pid: str, 
                      alt: Optional[str] = None) -> 'ExecutionResult':
        """
        Flash firmware via DFU.
        
        Args:
            firmware_path: Path to firmware file
            vid: Vendor ID
            pid: Product ID
            alt: Alternative setting (optional)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('dfu-util'):
            raise RuntimeError("dfu-util is not available")
        
        args = ['-d', f"{vid}:{pid}", '-D', firmware_path]
        
        if alt is not None:
            args.extend(['-a', str(alt)])
        
        return self.execute_tool('dfu-util', args, timeout=300)

class FPGAProgrammer(BaseProgrammer):
    """FPGA programmer using openFPGALoader"""
    
    def __init__(self, tool_service: 'ToolService'):
        super().__init__(tool_service)
        self.tool_service.register_tool('openFPGALoader', required=False)
    
    def is_tool_available(self, tool_name: str = 'openFPGALoader') -> bool:
        """Check if openFPGALoader is available, with fallback to direct detection"""
        # First try the centralized tool service
        if self.tool_service.is_tool_available(tool_name):
            return True
        
        # Fallback to direct detection if tool service fails
        import shutil
        return shutil.which(tool_name) is not None
    
    def load_sram(self, bitstream_path: str, board: Optional[str] = None,
                 cable: Optional[str] = None) -> 'ExecutionResult':
        """
        Load bitstream to FPGA SRAM (temporary).
        
        Args:
            bitstream_path: Path to bitstream file
            board: Board type (optional)
            cable: Cable type (optional)
            
        Returns:
            ExecutionResult: Result of the load operation
        """
        if not self.is_tool_available('openFPGALoader'):
            raise RuntimeError("openFPGALoader is not available")
        
        args = ['--bitstream', bitstream_path]
        
        if board:
            args.extend(['--board', board])
        if cable:
            args.extend(['--cable', cable])
        
        try:
            return self.execute_tool('openFPGALoader', args, timeout=300)
        except RuntimeError:
            # Fallback to direct execution if tool service fails
            import shutil
            import subprocess
            import time
            
            tool_path = shutil.which('openFPGALoader')
            if not tool_path:
                raise RuntimeError("openFPGALoader is not available")
            
            command = [tool_path] + args
            start_time = time.time()
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                command=' '.join(command),
                tool_path=tool_path
            )
    
    def flash_bitstream(self, bitstream_path: str, board: Optional[str] = None,
                       cable: Optional[str] = None, external_flash: bool = False) -> 'ExecutionResult':
        """
        Flash bitstream to FPGA configuration flash (permanent).
        
        Args:
            bitstream_path: Path to bitstream file
            board: Board type (optional)
            cable: Cable type (optional)
            external_flash: Use external flash (optional)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('openFPGALoader'):
            raise RuntimeError("openFPGALoader is not available")
        
        args = ['--write-flash', '--bitstream', bitstream_path]
        
        if board:
            args.extend(['--board', board])
        if cable:
            args.extend(['--cable', cable])
        if external_flash:
            args.append('--external-flash')
        
        try:
            return self.execute_tool('openFPGALoader', args, timeout=300)
        except RuntimeError:
            # Fallback to direct execution if tool service fails
            import shutil
            import subprocess
            import time
            
            tool_path = shutil.which('openFPGALoader')
            if not tool_path:
                raise RuntimeError("openFPGALoader is not available")
            
            command = [tool_path] + args
            start_time = time.time()
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                command=' '.join(command),
                tool_path=tool_path
            )

class GreatFETProgrammer(BaseProgrammer):
    """GreatFET programmer using greatfet_firmware"""
    
    def __init__(self, tool_service: 'ToolService'):
        super().__init__(tool_service)
        self.tool_service.register_tool('greatfet_firmware', required=False)
    
    def flash_firmware(self, firmware_path: str, target: str = "spi", 
                      serial: Optional[str] = None, board: Optional[str] = None) -> 'ExecutionResult':
        """
        Flash firmware to GreatFET device.
        
        Args:
            firmware_path: Path to firmware file
            target: Target memory (sram or spi)
            serial: Device serial number (optional)
            board: Board type (optional)
            
        Returns:
            ExecutionResult: Result of the flash operation
        """
        if not self.is_tool_available('greatfet_firmware'):
            raise RuntimeError("greatfet_firmware is not available")
        
        if target.lower() == 'sram':
            args = ['-V', firmware_path]
        else:
            args = ['-w', firmware_path]
        
        if serial:
            args.extend(['-s', serial])
        if board:
            args.extend(['-b', board])
        
        return self.execute_tool('greatfet_firmware', args, timeout=300)

class FirmwareToolService(ToolService):
    """Tool service specialized for firmware operations.

    Manifest resolution order (later entries override earlier ones):
      1. Built-in manifest shipped inside the ``iotsploit_drivers`` package at
         ``resources/firmware_manifest.json``.
      2. User override manifest at ``~/.iotsploit/firmware_manifest.json``
         (also where runtime-added firmware entries are persisted).

    Firmware entries may reference their binary in two ways:
      * ``"resource": "<package>:<relpath>"`` — a logical reference resolved
        via :func:`importlib.resources.as_file`. Preferred for bundled
        defaults so wheels and editable installs both work.
      * ``"path": "<filesystem path>"`` — a plain filesystem path. Intended
        for user-added firmware.

    Multi-file entries may use ``flash_options.files`` where each item has
    either ``"resource"`` or ``"path"``.

    Call :meth:`resolve_firmware` to obtain a context manager that yields
    a dict with all ``resource`` entries materialized to real filesystem
    paths — required for subprocess tools like ``esptool`` and
    ``openFPGALoader`` that need a concrete path on disk.
    """

    #: Name of the built-in manifest resource inside iotsploit_drivers.
    _BUILTIN_MANIFEST_PACKAGE = "iotsploit_drivers"
    _BUILTIN_MANIFEST_RELPATH = "resources/firmware_manifest.json"

    def __init__(self):
        super().__init__()

        from pathlib import Path

        # User directory for overrides and runtime-added firmware.
        self.user_dir = Path.home() / ".iotsploit"
        self.user_dir.mkdir(exist_ok=True)
        self.user_manifest_file = self.user_dir / "firmware_manifest.json"

        self.manifests = self._load_manifests()

        # Initialize programmers
        self.esp32 = ESP32Programmer(self)
        self.stm32 = STM32Programmer(self)
        self.dfu = DFUProgrammer(self)
        self.fpga = FPGAProgrammer(self)
        self.greatfet = GreatFETProgrammer(self)

    # ------------------------------------------------------------------
    # Manifest loading
    # ------------------------------------------------------------------

    def _load_builtin_manifest(self) -> Dict:
        """Load the manifest shipped inside the iotsploit_drivers package."""
        try:
            from importlib.resources import files
        except ImportError:  # pragma: no cover - Python <3.9 not supported
            return {}

        try:
            traversable = files(self._BUILTIN_MANIFEST_PACKAGE).joinpath(
                self._BUILTIN_MANIFEST_RELPATH
            )
            data = json.loads(traversable.read_text(encoding="utf-8"))
        except (ModuleNotFoundError, FileNotFoundError):
            self.logger.warning(
                "Built-in firmware manifest not found in %s:%s",
                self._BUILTIN_MANIFEST_PACKAGE,
                self._BUILTIN_MANIFEST_RELPATH,
            )
            return {}
        except json.JSONDecodeError as exc:
            self.logger.error("Built-in firmware manifest is invalid JSON: %s", exc)
            return {}

        # Drop schema metadata key if present.
        data.pop("_schema", None)
        return data

    def _load_user_manifest(self) -> Dict:
        """Load the user override manifest from ~/.iotsploit."""
        if not self.user_manifest_file.exists():
            return {}
        try:
            with open(self.user_manifest_file, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            self.logger.error(
                "User firmware manifest %s is invalid JSON: %s",
                self.user_manifest_file,
                exc,
            )
            return {}
        data.pop("_schema", None)
        return data

    def _load_manifests(self) -> Dict:
        """Merge built-in and user manifests. User entries take precedence."""
        merged: Dict = {}
        merged.update(self._load_builtin_manifest())
        merged.update(self._load_user_manifest())
        return merged

    # ------------------------------------------------------------------
    # Firmware resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_resource_ref(resource_ref: str):
        """Parse ``"<package>:<relpath>"`` into its components."""
        if ":" not in resource_ref:
            raise ValueError(
                f"Invalid resource ref {resource_ref!r}; "
                f"expected '<package>:<relpath>'"
            )
        package, relpath = resource_ref.split(":", 1)
        package = package.strip()
        relpath = relpath.strip().lstrip("/")
        if not package or not relpath:
            raise ValueError(f"Invalid resource ref {resource_ref!r}")
        return package, relpath

    @classmethod
    def _resource_as_path(cls, resource_ref: str):
        """Return a context manager yielding a concrete Path for a resource ref.

        Uses :func:`importlib.resources.as_file` so resources packed inside
        zipped wheels are materialized to a temp file for the duration of the
        ``with`` block.
        """
        from importlib.resources import files, as_file

        package, relpath = cls._parse_resource_ref(resource_ref)
        traversable = files(package).joinpath(relpath)
        return as_file(traversable)

    def resolve_firmware(self, name: str):
        """Context manager yielding a firmware_info dict with real paths.

        The yielded dict is a shallow copy of the manifest entry where:
          * ``resource`` has been replaced by ``path`` (a real filesystem str)
          * ``flash_options.files[*].resource`` has been replaced by ``path``

        All temporary files (if any) are kept alive for the duration of the
        ``with`` block. Raises :class:`KeyError` if ``name`` is not in the
        manifest.
        """
        from contextlib import contextmanager, ExitStack

        info = self.manifests.get(name)
        if info is None:
            raise KeyError(f"Firmware {name!r} not found in manifest")

        @contextmanager
        def _ctx():
            with ExitStack() as stack:
                resolved = dict(info)

                # Top-level resource/path.
                if "resource" in info:
                    p = stack.enter_context(self._resource_as_path(info["resource"]))
                    resolved["path"] = str(p)
                    resolved.pop("resource", None)
                elif "path" in info:
                    resolved["path"] = str(info["path"])

                # flash_options.files[*]
                flash_options = dict(info.get("flash_options", {}))
                if "files" in flash_options:
                    new_files = []
                    for entry in flash_options["files"]:
                        new_entry = dict(entry)
                        if "resource" in entry:
                            p = stack.enter_context(
                                self._resource_as_path(entry["resource"])
                            )
                            new_entry["path"] = str(p)
                            new_entry.pop("resource", None)
                        elif "path" in entry:
                            new_entry["path"] = str(entry["path"])
                        new_files.append(new_entry)
                    flash_options["files"] = new_files

                resolved["flash_options"] = flash_options
                yield resolved

        return _ctx()
    
    def add_firmware(self, name: str, path: str, device_type: str, version: str, 
                    flash_options: Optional[Dict[str, Any]] = None) -> bool:
        """Add firmware to registry"""
        try:
            from pathlib import Path
            firmware_path = Path(path)
            if not firmware_path.exists():
                self.logger.error(f"Firmware file not found: {path}")
                return False

            firmware_info = {
                "path": str(firmware_path),
                "device_type": device_type,
                "version": version
            }
            
            if flash_options:
                firmware_info["flash_options"] = flash_options

            self.manifests[name] = firmware_info
            self._save_manifests()
            self.logger.info(f"Successfully added firmware: {name}")
            return True

        except Exception as e:
            self.logger.error(f"Error adding firmware: {str(e)}")
            return False
    
    def get_firmware_info(self, name: str) -> Optional[Dict]:
        """Get information about specific firmware"""
        return self.manifests.get(name)
    
    def list_firmware(self) -> List[Dict]:
        """List all available firmware"""
        return [{"name": name, **info} for name, info in self.manifests.items()]
    
    def remove_firmware(self, name: str) -> bool:
        """Remove firmware from registry"""
        try:
            if name not in self.manifests:
                self.logger.error(f"Firmware not found: {name}")
                return False

            del self.manifests[name]
            self._save_manifests()
            self.logger.info(f"Successfully removed firmware: {name}")
            return True

        except Exception as e:
            self.logger.error(f"Error removing firmware: {str(e)}")
            return False
    
    def download_firmware(self, url: str, output_path: Optional[str] = None) -> Optional[str]:
        """Download firmware from URL"""
        try:
            import requests
            self.logger.info(f"Downloading firmware from: {url}")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            if not output_path:
                filename = url.split('/')[-1]
                if not filename:
                    filename = "downloaded_firmware.bin"
                downloads_dir = self.user_dir / "firmware"
                downloads_dir.mkdir(parents=True, exist_ok=True)
                output_path = str(downloads_dir / filename)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            self.logger.info(f"Firmware downloaded to: {output_path}")
            return output_path
        
        except Exception as e:
            self.logger.error(f"Error downloading firmware: {str(e)}")
            return None
    
    def flash_registered_firmware(self, name: str, options: Optional[Dict[str, Any]] = None) -> bool:
        """
        Flash firmware from registry using appropriate programmer based on device type.
        
        Args:
            name: Name of registered firmware
            options: Additional options to override defaults
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if name not in self.manifests:
                self.logger.error(f"Firmware not found: {name}")
                return False

            with self.resolve_firmware(name) as firmware_info:
                device_type = firmware_info.get('device_type', '').lower()
                firmware_path = firmware_info.get('path')

                # Merge options from manifest and provided options
                flash_options = dict(firmware_info.get('flash_options', {}))
                if options:
                    flash_options.update(options)

                # Route to appropriate programmer based on device type
                if device_type.startswith('esp32'):
                    if 'files' in flash_options:
                        # Multi-file ESP32 flash
                        result = self.esp32.flash_multi(
                            port=flash_options.get('port', '/dev/ttyUSB0'),
                            files=flash_options['files'],
                            chip=flash_options.get('chip', 'esp32s3'),
                            baud=flash_options.get('baud', '460800')
                        )
                    else:
                        # Single file ESP32 flash
                        result = self.esp32.flash_single(
                            port=flash_options.get('port', '/dev/ttyUSB0'),
                            firmware_path=firmware_path,
                            address=flash_options.get('address', '0x10000'),
                            chip=flash_options.get('chip', 'esp32'),
                            baud=flash_options.get('baud', '460800')
                        )
                    return result.success

                elif device_type.startswith('stm32'):
                    result = self.stm32.flash_firmware(
                        firmware_path=firmware_path,
                        interface=flash_options.get('interface', 'stlink'),
                        target=flash_options.get('target', 'stm32f4x')
                    )
                    return result.success

                elif device_type == 'dfu':
                    result = self.dfu.flash_firmware(
                        firmware_path=firmware_path,
                        vid=flash_options.get('vid'),
                        pid=flash_options.get('pid'),
                        alt=flash_options.get('alt')
                    )
                    return result.success

                elif device_type.startswith('fpga'):
                    target = flash_options.get('target', 'sram').lower()
                    if target == 'sram':
                        result = self.fpga.load_sram(
                            bitstream_path=firmware_path,
                            board=flash_options.get('board'),
                            cable=flash_options.get('cable')
                        )
                    else:
                        result = self.fpga.flash_bitstream(
                            bitstream_path=firmware_path,
                            board=flash_options.get('board'),
                            cable=flash_options.get('cable'),
                            external_flash=flash_options.get('external_flash', False)
                        )
                    return result.success

                elif device_type.startswith('greatfet'):
                    result = self.greatfet.flash_firmware(
                        firmware_path=firmware_path,
                        target=flash_options.get('target', 'spi'),
                        serial=flash_options.get('serial'),
                        board=flash_options.get('board')
                    )
                    return result.success

                else:
                    self.logger.error(f"Unsupported device type: {device_type}")
                    return False

        except Exception as e:
            self.logger.error(f"Error flashing firmware: {str(e)}")
            return False
    
    def _save_manifests(self):
        """Persist user-facing manifest entries to ``~/.iotsploit/firmware_manifest.json``.

        Only entries that differ from the built-in manifest are written so
        that the user override file stays minimal and keeps working even when
        the bundled defaults change in a future iotsploit-drivers release.
        """
        try:
            builtin = self._load_builtin_manifest()
            user_entries = {
                name: info
                for name, info in self.manifests.items()
                if builtin.get(name) != info
            }
            with open(self.user_manifest_file, 'w') as f:
                json.dump(user_entries, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving firmware manifest: {str(e)}")

class NetworkToolService(ToolService):
    """Tool service specialized for network operations"""
    
    def __init__(self):
        super().__init__()
        # Pre-register common network tools
        self.register_tool('nmap', '7.0', required=False)
        self.register_tool('masscan', required=False)
        self.register_tool('curl', required=False)
        self.register_tool('wget', required=False)
        self.register_tool('ping', required=False)
        self.register_tool('hydra', required=False)
    
    def port_scan(self, target: str, ports: str = "1-1000", 
                 scan_type: str = "syn") -> ExecutionResult:
        """
        Perform port scan using nmap.
        
        Args:
            target: Target IP or hostname
            ports: Port range (default: 1-1000)
            scan_type: Scan type (syn, tcp, udp, ping)
            
        Returns:
            ExecutionResult: Result of the scan
        """
        if not self.is_tool_available('nmap'):
            raise RuntimeError("nmap is not available")
        
        scan_args = {
            'syn': ['-sS'],
            'tcp': ['-sT'],
            'udp': ['-sU'],
            'ping': ['-sn']
        }
        
        args = scan_args.get(scan_type, ['-sS'])
        args.extend(['-p', ports, target])
        
        return self.execute_tool('nmap', args, timeout=300)
    

_firmware_service_instance = None
_network_service_instance = None

def get_firmware_service() -> FirmwareToolService:
    """Get singleton FirmwareToolService instance"""
    global _firmware_service_instance
    if _firmware_service_instance is None:
        _firmware_service_instance = FirmwareToolService()
    return _firmware_service_instance

def get_network_service() -> NetworkToolService:
    """Get singleton NetworkToolService instance"""
    global _network_service_instance
    if _network_service_instance is None:
        _network_service_instance = NetworkToolService()
    return _network_service_instance