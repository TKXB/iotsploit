#!/usr/bin/env python3
"""Tool management: discovery, validation, and cross-platform execution."""

import os
import sys
import shutil
import subprocess
import platform
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class ToolStatus(Enum):
    """Tool availability status"""
    AVAILABLE = "available"
    MISSING = "missing"
    INVALID = "invalid"
    PERMISSION_DENIED = "permission_denied"
    VERSION_MISMATCH = "version_mismatch"

@dataclass
class ToolInfo:
    """Information about a tool"""
    name: str
    path: Optional[str] = None
    version: Optional[str] = None
    status: ToolStatus = ToolStatus.MISSING
    aliases: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=lambda: ["linux", "darwin", "windows"])
    min_version: Optional[str] = None
    max_version: Optional[str] = None
    last_checked: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionResult:
    """Result of tool execution"""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    command: str
    tool_path: str

class ToolRegistry:
    """Central registry for managing tool information"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.tools: Dict[str, ToolInfo] = {}
        self.config_path = config_path or self._get_default_config_path()
        self._lock = threading.RLock()
        self._load_config()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path, preferring project-specific config"""
        # First try project-specific configuration
        project_config = Path('conf') / 'tools.json'
        if project_config.exists():
            return str(project_config)
        
        # Fall back to user-specific configuration
        config_dir = Path.home() / ".iotsploit"
        config_dir.mkdir(exist_ok=True)
        return str(config_dir / "tools.json")
    
    def _load_config(self):
        """Load tool configuration from file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    for tool_name, tool_data in config.get('tools', {}).items():
                        # Convert status string back to enum if needed
                        if 'status' in tool_data and isinstance(tool_data['status'], str):
                            try:
                                tool_data['status'] = ToolStatus(tool_data['status'])
                            except ValueError:
                                # If status string is invalid, default to MISSING
                                tool_data['status'] = ToolStatus.MISSING
                        self.tools[tool_name] = ToolInfo(**tool_data)
                logger.info(f"Loaded {len(self.tools)} tools from config")
            except Exception as e:
                logger.error(f"Failed to load tool config: {e}")
        else:
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default tool configuration"""
        default_tools = {
            'nmap': ToolInfo(
                name='nmap',
                aliases=['nmap'],
                platforms=['linux', 'darwin', 'windows'],
                min_version='7.0'
            ),
            'adb': ToolInfo(
                name='adb',
                aliases=['adb'],
                platforms=['linux', 'darwin', 'windows']
            ),
            'openssl': ToolInfo(
                name='openssl',
                aliases=['openssl'],
                platforms=['linux', 'darwin', 'windows']
            ),
            'binwalk': ToolInfo(
                name='binwalk',
                aliases=['binwalk'],
                platforms=['linux', 'darwin']
            ),
            'john': ToolInfo(
                name='john',
                aliases=['john', 'john-the-ripper'],
                platforms=['linux', 'darwin', 'windows']
            ),
            'hashcat': ToolInfo(
                name='hashcat',
                aliases=['hashcat'],
                platforms=['linux', 'darwin', 'windows']
            )
        }
        
        for name, tool_info in default_tools.items():
            self.tools[name] = tool_info
        
        self.save_config()
    
    def save_config(self):
        """Save tool configuration to file"""
        try:
            config = {
                'tools': {
                    name: {
                        'name': tool.name,
                        'path': tool.path,
                        'version': tool.version,
                        'status': tool.status.value if hasattr(tool.status, 'value') else str(tool.status),
                        'aliases': tool.aliases,
                        'dependencies': tool.dependencies,
                        'platforms': tool.platforms,
                        'min_version': tool.min_version,
                        'max_version': tool.max_version,
                        'last_checked': tool.last_checked,
                        'metadata': tool.metadata
                    }
                    for name, tool in self.tools.items()
                }
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.debug(f"Saved tool config to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save tool config: {e}")
            # Add more detailed error information
            import traceback
            logger.debug(f"Save config traceback: {traceback.format_exc()}")
    
    def register_tool(self, tool_info: ToolInfo, save_config: bool = True):
        """Register a new tool"""
        with self._lock:
            self.tools[tool_info.name] = tool_info
            if save_config:
                self.save_config()
    
    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """Get tool information by name or alias"""
        with self._lock:
            # Direct name match
            if name in self.tools:
                return self.tools[name]
            
            # Alias match
            for tool in self.tools.values():
                if name in tool.aliases:
                    return tool
            
            return None
    
    def list_tools(self) -> List[ToolInfo]:
        """List all registered tools"""
        with self._lock:
            return list(self.tools.values())

class PathResolver:
    """Resolves tool paths across different platforms"""
    
    def __init__(self):
        self.platform = platform.system().lower()
        self.search_paths = self._get_search_paths()
        self._path_cache: Dict[str, str] = {}
    
    def _get_search_paths(self) -> List[str]:
        """Get platform-specific search paths"""
        paths = []
        
        # System PATH
        system_path = os.environ.get('PATH', '')
        if system_path:
            paths.extend(system_path.split(os.pathsep))
        
        # Platform-specific paths
        if self.platform == 'linux':
            paths.extend([
                '/usr/bin', '/usr/local/bin', '/bin', '/sbin',
                '/usr/sbin', '/usr/local/sbin', '/opt/bin'
            ])
        elif self.platform == 'darwin':  # macOS
            paths.extend([
                '/usr/bin', '/usr/local/bin', '/bin', '/sbin',
                '/usr/sbin', '/opt/homebrew/bin', '/usr/local/sbin'
            ])
        elif self.platform == 'windows':
            paths.extend([
                'C:\\Windows\\System32', 'C:\\Windows',
                'C:\\Program Files', 'C:\\Program Files (x86)'
            ])
        
        # User-specific paths
        home = Path.home()
        paths.extend([
            str(home / 'bin'),
            str(home / '.local' / 'bin'),
            str(home / 'go' / 'bin')
        ])
        
        return [p for p in paths if p and os.path.exists(p)]
    
    def resolve_tool_path(self, tool_name: str, aliases: List[str] = None) -> Optional[str]:
        """Resolve the full path to a tool"""
        # Check cache first
        cache_key = f"{tool_name}:{','.join(aliases or [])}"
        if cache_key in self._path_cache:
            cached_path = self._path_cache[cache_key]
            if os.path.exists(cached_path):
                return cached_path
            else:
                # Remove invalid cache entry
                del self._path_cache[cache_key]
        
        # Try tool name and aliases
        names_to_try = [tool_name] + (aliases or [])
        
        for name in names_to_try:
            # Try shutil.which first (respects PATH)
            path = shutil.which(name)
            if path and self._validate_executable(path):
                self._path_cache[cache_key] = path
                return path
            
            # Manual search in known paths
            for search_path in self.search_paths:
                potential_path = os.path.join(search_path, name)
                
                # Add .exe extension on Windows
                if self.platform == 'windows' and not potential_path.endswith('.exe'):
                    potential_path += '.exe'
                
                if os.path.exists(potential_path) and self._validate_executable(potential_path):
                    self._path_cache[cache_key] = potential_path
                    return potential_path
        
        return None
    
    def _validate_executable(self, path: str) -> bool:
        """Validate that a path points to an executable file"""
        try:
            return os.path.isfile(path) and os.access(path, os.X_OK)
        except (OSError, PermissionError):
            return False

class ToolValidator:
    """Validates tool availability and versions"""
    
    def __init__(self, path_resolver: PathResolver):
        self.path_resolver = path_resolver
    
    def validate_tool(self, tool_info: ToolInfo) -> ToolInfo:
        """Validate a tool and update its status"""
        # Check if tool is supported on current platform
        current_platform = platform.system().lower()
        if current_platform not in tool_info.platforms:
            tool_info.status = ToolStatus.INVALID
            return tool_info
        
        # Resolve tool path
        if not tool_info.path:
            tool_info.path = self.path_resolver.resolve_tool_path(
                tool_info.name, tool_info.aliases
            )
        
        if not tool_info.path:
            tool_info.status = ToolStatus.MISSING
            return tool_info
        
        # Validate executable permissions
        if not os.access(tool_info.path, os.X_OK):
            tool_info.status = ToolStatus.PERMISSION_DENIED
            return tool_info
        
        # Get and validate version
        try:
            version = self._get_tool_version(tool_info)
            if version:
                tool_info.version = version
                if self._check_version_compatibility(tool_info):
                    tool_info.status = ToolStatus.AVAILABLE
                else:
                    tool_info.status = ToolStatus.VERSION_MISMATCH
            else:
                tool_info.status = ToolStatus.AVAILABLE  # Version check failed but tool exists
        except Exception as e:
            logger.warning(f"Version check failed for {tool_info.name}: {e}")
            tool_info.status = ToolStatus.AVAILABLE  # Assume available if version check fails
        
        tool_info.last_checked = time.time()
        return tool_info
    
    def _get_tool_version(self, tool_info: ToolInfo) -> Optional[str]:
        """Get tool version"""
        version_commands = [
            ['--version'],
            ['-v'],
            ['-V'],
            ['version'],
            ['--help']  # Some tools only show version in help
        ]
        
        for cmd_args in version_commands:
            try:
                result = subprocess.run(
                    [tool_info.path] + cmd_args,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Look for version in stdout or stderr
                output = result.stdout + result.stderr
                version = self._extract_version(output)
                if version:
                    return version
                    
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                continue
        
        return None
    
    def _extract_version(self, output: str) -> Optional[str]:
        """Extract version number from command output"""
        import re
        
        # Common version patterns
        patterns = [
            r'version\s+(\d+\.\d+(?:\.\d+)?)',
            r'v(\d+\.\d+(?:\.\d+)?)',
            r'(\d+\.\d+(?:\.\d+)?)',
            r'Version:\s*(\d+\.\d+(?:\.\d+)?)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _check_version_compatibility(self, tool_info: ToolInfo) -> bool:
        """Check if tool version meets requirements"""
        if not tool_info.version:
            return True  # No version info, assume compatible
        
        try:
            from packaging import version
            tool_version = version.parse(tool_info.version)
            
            if tool_info.min_version:
                min_ver = version.parse(tool_info.min_version)
                if tool_version < min_ver:
                    return False
            
            if tool_info.max_version:
                max_ver = version.parse(tool_info.max_version)
                if tool_version > max_ver:
                    return False
            
            return True
        except Exception:
            # If version parsing fails, assume compatible
            return True

class ToolExecutor:
    """Executes tools with proper environment and error handling"""
    
    def __init__(self, tool_registry: ToolRegistry, validator: ToolValidator):
        self.registry = tool_registry
        self.validator = validator
    
    def execute_tool(self, tool_name: str, args: List[str], 
                    working_dir: Optional[str] = None,
                    env: Optional[Dict[str, str]] = None,
                    timeout: Optional[int] = None) -> ExecutionResult:
        """Execute a tool with given arguments"""
        
        # Get tool info
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            raise ValueError(f"Tool '{tool_name}' not found in registry")
        
        # Validate tool
        tool_info = self.validator.validate_tool(tool_info)
        if tool_info.status != ToolStatus.AVAILABLE:
            raise RuntimeError(f"Tool '{tool_name}' is not available: {tool_info.status.value}")
        
        # Prepare execution environment
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        
        # Build command
        command = [tool_info.path] + args
        command_str = ' '.join(command)
        
        logger.info(f"Executing: {command_str}")
        
        start_time = time.time()
        try:
            result = subprocess.run(
                command,
                cwd=working_dir,
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_info.path
            )
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Command timed out after {timeout} seconds",
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_info.path
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_info.path
            )

class ToolManager:
    """Main tool management interface"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.registry = ToolRegistry(config_path)
        self.path_resolver = PathResolver()
        self.validator = ToolValidator(self.path_resolver)
        self.executor = ToolExecutor(self.registry, self.validator)
    
    def discover_tools(self) -> Dict[str, ToolStatus]:
        """Discover and validate all registered tools"""
        results = {}
        
        for tool_name, tool_info in self.registry.tools.items():
            validated_tool = self.validator.validate_tool(tool_info)
            self.registry.tools[tool_name] = validated_tool
            results[tool_name] = validated_tool.status
        
        self.registry.save_config()
        return results
    
    def get_tool_status(self, tool_name: str) -> Optional[ToolStatus]:
        """Get the status of a specific tool"""
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            return None
        
        # Refresh status if not checked recently
        if not tool_info.last_checked or (time.time() - tool_info.last_checked) > 3600:
            tool_info = self.validator.validate_tool(tool_info)
            self.registry.tools[tool_info.name] = tool_info
            self.registry.save_config()
        
        return tool_info.status
    
    def execute(self, tool_name: str, args: List[str], **kwargs) -> ExecutionResult:
        """Execute a tool with arguments"""
        return self.executor.execute_tool(tool_name, args, **kwargs)
    
    def is_available(self, tool_name: str) -> bool:
        """Check if a tool is available for use"""
        status = self.get_tool_status(tool_name)
        return status == ToolStatus.AVAILABLE
    
    def list_available_tools(self) -> List[str]:
        """List all available tools"""
        available = []
        for tool_name in self.registry.tools.keys():
            if self.is_available(tool_name):
                available.append(tool_name)
        return available
    
    def add_tool(self, name: str, path: Optional[str] = None, 
                aliases: List[str] = None, save_config: bool = True, **kwargs) -> bool:
        """Add a new tool to the registry"""
        tool_info = ToolInfo(
            name=name,
            path=path,
            aliases=aliases or [],
            **kwargs
        )
        
        # Validate the tool
        validated_tool = self.validator.validate_tool(tool_info)
        self.registry.register_tool(validated_tool, save_config=save_config)
        
        return validated_tool.status == ToolStatus.AVAILABLE

# Convenience
def get_tool_manager() -> ToolManager:
    """Get a singleton tool manager instance"""
    if not hasattr(get_tool_manager, '_instance'):
        get_tool_manager._instance = ToolManager()
    return get_tool_manager._instance

def execute_tool(tool_name: str, args: List[str], **kwargs) -> ExecutionResult:
    """Execute a tool using the default tool manager"""
    return get_tool_manager().execute(tool_name, args, **kwargs)

def is_tool_available(tool_name: str) -> bool:
    """Check if a tool is available"""
    return get_tool_manager().is_available(tool_name) 