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
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
import time
from contextlib import contextmanager

# Import ExecutionResult from execution_backend to avoid duplication
from .execution_backend import ExecutionResult, get_execution_backend_manager
from .tool_config import get_tool_config_manager, ToolConfig
from .execution_queue import get_execution_queue

logger = logging.getLogger(__name__)

# Detection results older than this (seconds) are re-probed; fresh ones are served
# from the runtime cache instead of re-running every tool's `--version`.
TOOL_CACHE_TTL_SECONDS = 3600

# Curated, version-controlled fields. These live in conf/tools.json and are never
# rewritten by runtime detection.
STATIC_TOOL_FIELDS = (
    "name", "aliases", "dependencies", "platforms",
    "min_version", "max_version", "metadata",
)
# Machine-specific detection results. These live in the gitignored runtime cache
# (.tools_cache.json) because they differ per host and change on every probe.
RUNTIME_TOOL_FIELDS = ("path", "version", "status", "last_checked")

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
class CategoryInfo:
    """Information about the tool category"""
    name: str
    description: str
    tools: List[str] = field(default_factory=list)

class SystemHealth(Enum):
    """System health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"

@dataclass
class SystemStatus:
    """Overall system status"""
    health: SystemHealth
    total_tools: int
    available_tools: int
    missing_tools: int
    required_missing: int
    can_operate: bool
    recommendations: List[str] = field(default_factory=list)

class ToolRegistry:
    """Central registry for managing tool information"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.tools: Dict[str, ToolInfo] = {}
        self.config_path = config_path or self._get_default_config_path()
        # Runtime detection cache lives next to the config but is gitignored.
        self.cache_path = str(Path(self.config_path).parent / ".tools_cache.json")
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
        """Load curated tool definitions from the version-controlled config file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                known_fields = set(STATIC_TOOL_FIELDS) | set(RUNTIME_TOOL_FIELDS)
                for tool_name, tool_data in config.get('tools', {}).items():
                    # Tolerate legacy files that still carry runtime fields, and drop
                    # any unknown keys so the ToolInfo constructor never fails.
                    data = {k: v for k, v in tool_data.items() if k in known_fields}
                    data.setdefault('name', tool_name)
                    if isinstance(data.get('status'), str):
                        try:
                            data['status'] = ToolStatus(data['status'])
                        except ValueError:
                            data['status'] = ToolStatus.MISSING
                    self.tools[tool_name] = ToolInfo(**data)
                logger.info(f"Loaded {len(self.tools)} tool definitions from config")
            except Exception as e:
                logger.error(f"Failed to load tool config: {e}")
        else:
            self._create_default_config()
        # Overlay machine-specific detection results from the runtime cache.
        self._load_cache()
    
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
    
    def _load_cache(self):
        """Overlay machine-specific detection results from the runtime cache onto
        the loaded definitions. A missing or unreadable cache is normal."""
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, 'r') as f:
                cache = json.load(f)
        except Exception as e:
            logger.warning(f"Ignoring unreadable tool cache {self.cache_path}: {e}")
            return
        for name, runtime in cache.get('tools', {}).items():
            tool = self.tools.get(name)
            if not tool:
                continue
            if 'path' in runtime:
                tool.path = runtime['path']
            if 'version' in runtime:
                tool.version = runtime['version']
            if 'last_checked' in runtime:
                tool.last_checked = runtime['last_checked']
            if isinstance(runtime.get('status'), str):
                try:
                    tool.status = ToolStatus(runtime['status'])
                except ValueError:
                    tool.status = ToolStatus.MISSING

    def save_config(self):
        """Persist the curated tool definitions (static fields only).

        Detection results are intentionally excluded — they belong in the runtime
        cache (see save_cache) so this version-controlled file stays stable across
        hosts and process restarts. Call this only when a definition changes."""
        try:
            config = {
                'tools': {
                    name: {field: getattr(tool, field) for field in STATIC_TOOL_FIELDS}
                    for name, tool in self.tools.items()
                }
            }
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.debug(f"Saved tool definitions to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save tool config: {e}")
            import traceback
            logger.debug(f"Save config traceback: {traceback.format_exc()}")

    def save_cache(self):
        """Persist machine-specific detection results to the gitignored runtime cache.

        path/version/status/last_checked differ per host and change on every probe,
        so they must never land in the version-controlled tools.json."""
        try:
            cache = {
                'tools': {
                    name: {
                        'path': tool.path,
                        'version': tool.version,
                        'status': tool.status.value if hasattr(tool.status, 'value') else str(tool.status),
                        'last_checked': tool.last_checked,
                    }
                    for name, tool in self.tools.items()
                }
            }
            Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
            # Guarded by self._lock against threads, but not against multiple
            # processes sharing one cache file. TODO: add file locking if iotsploit
            # is ever run as concurrent processes against the same cache.
            with open(self.cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
            logger.debug(f"Saved tool runtime cache to {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to save tool cache: {e}")
    
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
        self.backend_manager = get_execution_backend_manager()
    
    def execute_tool(self, tool_name: str, args: List[str], 
                    working_dir: Optional[str] = None,
                    env: Optional[Dict[str, str]] = None,
                    timeout: Optional[int] = None,
                    backend: Optional[str] = None) -> ExecutionResult:
        """Execute a tool with given arguments"""
        
        # Get tool info
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            raise ValueError(f"Tool '{tool_name}' not found in registry")
        
        # Validate tool
        tool_info = self.validator.validate_tool(tool_info)
        if tool_info.status != ToolStatus.AVAILABLE:
            raise RuntimeError(f"Tool '{tool_name}' is not available: {tool_info.status.value}")
        
        logger.info(f"Executing: {tool_info.path} {' '.join(args)}")
        
        # Execute using backend manager
        return self.backend_manager.execute(
            tool_path=tool_info.path,
            args=args,
            backend=backend,
            working_dir=working_dir,
            env=env,
                timeout=timeout
            )

class ToolManager:
    """Main tool management interface"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.registry = ToolRegistry(config_path)
        self.path_resolver = PathResolver()
        self.validator = ToolValidator(self.path_resolver)
        self.executor = ToolExecutor(self.registry, self.validator)
        self.config_manager = get_tool_config_manager()
        self.backend_manager = get_execution_backend_manager()
        self.queue_manager = get_execution_queue()
        # Initialize tools from JSON configuration
        self._initialize_tools()
    
    def discover_tools(self) -> Dict[str, ToolStatus]:
        """Discover and validate all registered tools"""
        results = {}
        
        for tool_name, tool_info in self.registry.tools.items():
            validated_tool = self.validator.validate_tool(tool_info)
            self.registry.tools[tool_name] = validated_tool
            results[tool_name] = validated_tool.status

        self.registry.save_cache()
        return results
    
    def get_tool_status(self, tool_name: str) -> Optional[ToolStatus]:
        """Get the status of a specific tool"""
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            return None
        
        # Refresh status if not checked recently
        if not tool_info.last_checked or (time.time() - tool_info.last_checked) > TOOL_CACHE_TTL_SECONDS:
            tool_info = self.validator.validate_tool(tool_info)
            self.registry.tools[tool_info.name] = tool_info
            self.registry.save_cache()

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
        if save_config:
            # Persisting a new tool also persists its freshly-probed runtime state.
            self.registry.save_cache()

        return validated_tool.status == ToolStatus.AVAILABLE
    
    # ========== Methods from ToolCategoryManager ==========
    
    def _initialize_tools(self):
        """Validate registered tools, honoring the runtime cache so tools probed
        recently are not re-probed on every startup."""
        logger.info("Initializing tools from configuration")

        # The registry already loaded curated definitions (and any cached runtime
        # state) from tools.json. If it came up empty, fall back to the category
        # manager as the definition source.
        if not self.registry.tools:
            for tool_config in self.config_manager.get_tools_by_category("tools"):
                try:
                    self.registry.tools[tool_config.name] = ToolInfo(
                        name=tool_config.name,
                        path=tool_config.path,
                        aliases=tool_config.aliases or [],
                        min_version=tool_config.min_version,
                        platforms=tool_config.platforms or ["linux", "darwin", "windows"],
                    )
                except Exception as e:
                    logger.error(f"Error adding tool {tool_config.name}: {e}")

        now = time.time()
        revalidated = 0
        for name, tool_info in list(self.registry.tools.items()):
            # Skip tools whose cached detection result is still fresh.
            if tool_info.last_checked and (now - tool_info.last_checked) < TOOL_CACHE_TTL_SECONDS:
                continue
            self.registry.tools[name] = self.validator.validate_tool(tool_info)
            revalidated += 1

        # Only touch the runtime cache when something was actually re-probed.
        if revalidated:
            self.registry.save_cache()
        logger.info(
            f"Initialized {len(self.registry.tools)} tools ({revalidated} re-probed)"
        )
    
    def get_category_info(self) -> CategoryInfo:
        """Get category information from JSON config"""
        # Try to get from tools.json in conf directory first, then fallback
        tools_file = Path('conf') / 'tools.json'
        if not tools_file.exists():
            tools_file = self.config_manager.config_dir / "tools.json"
        
        if tools_file.exists():
            try:
                with open(tools_file, 'r', encoding='utf-8') as f:
                    tools_data = json.load(f)
                
                # Handle tools field, support dict or list format
                tools_section = tools_data.get('tools', [])
                all_tools = []
                
                if isinstance(tools_section, dict):
                    # tools field is dict format: {"tool_name": {...}, ...}
                    all_tools = list(tools_section.keys())
                elif isinstance(tools_section, list):
                    # tools field is list format: [{"name": "tool_name", ...}, ...]
                    all_tools = [tool.get('name', 'unknown') for tool in tools_section if isinstance(tool, dict)]
                
                return CategoryInfo(
                    name=tools_data.get('name', 'IoTSploit Tools'),
                    description=tools_data.get('description', 'All tools for IoTSploit'),
                    tools=all_tools
                )
            except Exception as e:
                logger.error(f"Error reading tools.json: {e}")
        
        # Fallback
        return CategoryInfo(
            name="IoTSploit Tools",
            description="All tools for IoTSploit security testing",
            tools=[]
        )
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        category_info = self.get_category_info()
        available = []
        
        for tool_name in category_info.tools:
            if self.is_available(tool_name):
                available.append(tool_name)
        
        return available
    
    def get_missing_tools(self) -> List[str]:
        """Get list of missing tools"""
        category_info = self.get_category_info()
        missing = []
        
        for tool_name in category_info.tools:
            if not self.is_available(tool_name):
                missing.append(tool_name)
        
        return missing
    
    def get_required_tools(self) -> List[str]:
        """Get list of required tools"""
        category_info = self.get_category_info()
        required = []
        
        for tool_name in category_info.tools:
            tool_config = self.get_tool_config(tool_name)
            if tool_config and tool_config.required:
                required.append(tool_name)
        
        return required
    
    def get_optional_tools(self) -> List[str]:
        """Get list of optional tools"""
        category_info = self.get_category_info()
        optional = []
        
        for tool_name in category_info.tools:
            tool_config = self.get_tool_config(tool_name)
            if tool_config and not tool_config.required:
                optional.append(tool_name)
        
        return optional
    
    def validate_tools(self) -> Dict[str, Any]:
        """Validate all tools"""
        category_info = self.get_category_info()
        required_tools = self.get_required_tools()
        
        results = {
            'total_tools': len(category_info.tools),
            'available_tools': [],
            'missing_tools': [],
            'required_missing': [],
            'can_operate': True
        }
        
        for tool_name in category_info.tools:
            if self.is_available(tool_name):
                results['available_tools'].append(tool_name)
            else:
                results['missing_tools'].append(tool_name)
                if tool_name in required_tools:
                    results['required_missing'].append(tool_name)
        
        # Check if we can operate
        results['can_operate'] = len(results['required_missing']) == 0
        
        return results
    
    def get_tool_config(self, tool_name: str) -> Optional[ToolConfig]:
        """Get tool configuration from JSON"""
        return self.config_manager.get_tool_config(tool_name)
    
    def get_install_hints(self) -> Dict[str, str]:
        """Get installation hints for missing tools"""
        missing_tools = self.get_missing_tools()
        hints = {}
        
        for tool_name in missing_tools:
            tool_config = self.get_tool_config(tool_name)
            if tool_config and tool_config.install_hint:
                hints[tool_name] = tool_config.install_hint
        
        return hints
    
    def reload_configurations(self):
        """Reload all configurations from JSON files"""
        self.config_manager.reload_configs()
        self._initialize_tools()
        logger.info("Reloaded all tool configurations from JSON files")
    
    def get_config_stats(self) -> Dict[str, Any]:
        """Get statistics about tool configurations"""
        return self.config_manager.get_stats()
    
    # ========== Methods from CentralizedToolManager ==========
    
    def get_system_status(self) -> SystemStatus:
        """Get comprehensive system status"""
        validation = self.validate_tools()
        
        # Determine health status
        if validation['required_missing']:
            health = SystemHealth.CRITICAL
        elif validation['missing_tools']:
            health = SystemHealth.DEGRADED
        else:
            health = SystemHealth.HEALTHY
        
        # Generate recommendations
        recommendations = []
        if validation['required_missing']:
            recommendations.append(f"Install {len(validation['required_missing'])} required tools")
        if len(validation['missing_tools']) > len(validation['required_missing']):
            optional_missing = len(validation['missing_tools']) - len(validation['required_missing'])
            recommendations.append(f"Consider installing {optional_missing} optional tools")
        
        return SystemStatus(
            health=health,
            total_tools=validation['total_tools'],
            available_tools=len(validation['available_tools']),
            missing_tools=len(validation['missing_tools']),
            required_missing=len(validation['required_missing']),
            can_operate=validation['can_operate'],
            recommendations=recommendations
        )
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get detailed health report"""
        status = self.get_system_status()
        validation = self.validate_tools()
        
        report = {
            'timestamp': self._get_timestamp(),
            'system_health': status.health.value,
            'can_operate': status.can_operate,
            'summary': {
                'total_tools': status.total_tools,
                'available_tools': status.available_tools,
                'missing_tools': status.missing_tools,
                'required_missing': status.required_missing
            },
            'tools': {
                'available': validation['available_tools'],
                'missing': validation['missing_tools'],
                'required_missing': validation['required_missing']
            },
            'recommendations': status.recommendations,
            'backend_status': self.backend_manager.get_status(),
            'queue_status': asdict(self.queue_manager.get_stats())
        }
        
        return report
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_system_health(self, force_refresh: bool = False):
        """Get system health with category status"""
        status = self.get_system_status()
        validation = self.validate_tools()
        
        # Create a health object with category status
        class HealthStatus:
            def __init__(self, status, validation):
                self.status = status.health.value
                self.total_tools = status.total_tools
                self.available_tools = status.available_tools
                self.missing_tools = status.missing_tools
                self.missing_critical_tools = status.required_missing
                self.recommendations = status.recommendations
                self.category_status = {
                    "tools": {
                        "total_tools": validation['total_tools'],
                        "available_tools": validation['available_tools'],
                        "missing_tools": validation['missing_tools'],
                        "can_operate": validation['can_operate']
                    }
                }
        
        return HealthStatus(status, validation)
    
    def get_installation_recommendations(self) -> Dict[str, Dict[str, List[str]]]:
        """Get installation recommendations by category"""
        missing_tools = self.get_missing_tools()
        required_tools = self.get_required_tools()
        
        required_missing = [t for t in missing_tools if t in required_tools]
        optional_missing = [t for t in missing_tools if t not in required_tools]
        
        return {
            "tools": {
                "required": required_missing,
                "optional": optional_missing
            }
        }
    
    # Lifecycle management
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.queue_manager.shutdown()
            logger.info("Tool manager cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def shutdown(self, wait: bool = True):
        """Shutdown the system"""
        self.cleanup()

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