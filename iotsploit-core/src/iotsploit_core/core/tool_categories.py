#!/usr/bin/env python3
"""
Simplified Tool Categories for IoTSploit Tool Manager
====================================================

Simplified to use just one category for all tools instead of multiple categories.
All tools are loaded from a single JSON configuration file.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from .tool_manager import ToolManager, ToolInfo, ToolStatus
from .tool_config import get_tool_config_manager, ToolConfig

logger = logging.getLogger(__name__)

@dataclass
class CategoryInfo:
    """Information about the tool category"""
    name: str
    description: str
    tools: List[str] = field(default_factory=list)

class ToolCategoryManager:
    """Simplified manager for all tools in one category"""
    
    def __init__(self, tool_manager: ToolManager):
        self.tool_manager = tool_manager
        self.config_manager = get_tool_config_manager()
        self.logger = logging.getLogger("tool_categories")
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize all tools from JSON configuration"""
        self.logger.info("Initializing tools from JSON config")
        
        # Get tools from the main tools.json file
        tool_configs = self.config_manager.get_tools_by_category("tools")
        
        # If no tools found in "tools" category, try loading from the main config
        if not tool_configs:
            # Try to load from tools.json in conf directory first, then fallback
            tools_file = Path('conf') / 'tools.json'
            if not tools_file.exists():
                tools_file = self.config_manager.config_dir / "tools.json"
            
            if tools_file.exists():
                import json
                with open(tools_file, 'r', encoding='utf-8') as f:
                    tools_data = json.load(f)
                
                tools_added = 0
                # 支持 tools 字段为 dict 或 list
                tools_section = tools_data.get('tools', [])
                if isinstance(tools_section, dict):
                    items = tools_section.items()
                else:
                    items = [(td.get('name', 'unknown'), td) for td in tools_section if isinstance(td, dict)]
                for tool_name, tool_data in items:
                    try:
                        # 构建 tool_data 字典并保证包含 name
                        data = tool_data.copy() if isinstance(tool_data, dict) else {}
                        data.setdefault('name', tool_name)
                        tool_config = ToolConfig.from_dict(data)
                        tool_config.category = "tools"
                        # Add tool to manager (don't save config for each tool)
                        success = self.tool_manager.add_tool(
                            name=tool_config.name,
                            aliases=tool_config.aliases,
                            min_version=tool_config.min_version,
                            platforms=tool_config.platforms,
                            path=tool_config.path,
                            save_config=False
                        )
                        if success:
                            tools_added += 1
                            self.logger.debug(f"Added tool: {tool_config.name}")
                        else:
                            self.logger.warning(f"Failed to add tool: {tool_config.name}")
                    except Exception as e:
                        self.logger.error(f"Error adding tool {tool_name}: {e}")
                
                # Save config once at the end
                if tools_added > 0:
                    self.tool_manager.registry.save_config()
                    self.logger.info(f"Successfully initialized {tools_added} tools")
        else:
            # Load tools from category
            tools_added = 0
            for tool_config in tool_configs:
                try:
                    success = self.tool_manager.add_tool(
                        name=tool_config.name,
                        aliases=tool_config.aliases,
                        min_version=tool_config.min_version,
                        platforms=tool_config.platforms,
                        path=tool_config.path,
                        save_config=False  # Don't save for each tool
                    )
                    
                    if success:
                        tools_added += 1
                        self.logger.debug(f"Added tool: {tool_config.name}")
                    else:
                        self.logger.warning(f"Failed to add tool: {tool_config.name}")
                        
                except Exception as e:
                    self.logger.error(f"Error adding tool {tool_config.name}: {e}")
            
            # Save config once at the end
            if tools_added > 0:
                self.tool_manager.registry.save_config()
                self.logger.info(f"Successfully initialized {tools_added} tools")
    
    def get_category_info(self) -> CategoryInfo:
        """Get category information from JSON config"""
        # Try to get from tools.json in conf directory first, then fallback
        tools_file = Path('conf') / 'tools.json'
        if not tools_file.exists():
            tools_file = self.config_manager.config_dir / "tools.json"
        
        if tools_file.exists():
            import json
            try:
                with open(tools_file, 'r', encoding='utf-8') as f:
                    tools_data = json.load(f)
                
                # 处理 tools 字段，支持字典或列表格式
                tools_section = tools_data.get('tools', [])
                all_tools = []
                
                if isinstance(tools_section, dict):
                    # tools 字段是字典格式：{"tool_name": {...}, ...}
                    all_tools = list(tools_section.keys())
                elif isinstance(tools_section, list):
                    # tools 字段是列表格式：[{"name": "tool_name", ...}, ...]
                    all_tools = [tool.get('name', 'unknown') for tool in tools_section if isinstance(tool, dict)]
                
                return CategoryInfo(
                    name=tools_data.get('name', 'IoTSploit Tools'),
                    description=tools_data.get('description', 'All tools for IoTSploit'),
                    tools=all_tools
                )
            except Exception as e:
                self.logger.error(f"Error reading tools.json: {e}")
        
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
            if self.tool_manager.is_available(tool_name):
                available.append(tool_name)
        
        return available
    
    def get_missing_tools(self) -> List[str]:
        """Get list of missing tools"""
        category_info = self.get_category_info()
        missing = []
        
        for tool_name in category_info.tools:
            if not self.tool_manager.is_available(tool_name):
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
            if self.tool_manager.is_available(tool_name):
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
        self.logger.info("Reloaded all tool configurations from JSON files")
    
    def add_tool(self, tool_config: ToolConfig) -> bool:
        """Add a new tool"""
        tool_config.category = "tools"
        success = self.config_manager.add_tool_config(tool_config, save=True)
        
        if success:
            self._initialize_tools()  # Reinitialize to pick up new tool
        
        return success
    
    def get_config_stats(self) -> Dict[str, Any]:
        """Get statistics about tool configurations"""
        return self.config_manager.get_stats()
    
    # Convenience methods for common operations
    def flash_esp32(self, port: str, firmware_path: str, **kwargs) -> Dict[str, Any]:
        """Convenience method for ESP32 flashing"""
        if not self.tool_manager.is_available('esptool'):
            return {"status": "error", "message": "esptool not available"}
        
        args = [
            '--chip', kwargs.get('chip', 'esp32s3'),
            '--port', port,
            '--baud', kwargs.get('baud', '460800'),
            'write_flash', kwargs.get('address', '0x10000'), firmware_path
        ]
        
        result = self.tool_manager.execute('esptool', args, timeout=300)
        return {
            "status": "success" if result.success else "error",
            "message": "Flash completed" if result.success else result.stderr,
            "execution_time": result.execution_time
        }
    
    def port_scan(self, target: str, ports: str = "1-1000", 
                 scan_type: str = "syn") -> Dict[str, Any]:
        """Convenience method for port scanning"""
        if not self.tool_manager.is_available('nmap'):
            return {"status": "error", "message": "nmap not available"}
        
        scan_args = {
            'syn': ['-sS'],
            'tcp': ['-sT'],
            'udp': ['-sU'],
            'ping': ['-sn']
        }
        
        args = scan_args.get(scan_type, ['-sS'])
        args.extend(['-p', ports, target])
        
        result = self.tool_manager.execute('nmap', args, timeout=300)
        return {
            "status": "success" if result.success else "error",
            "message": "Scan completed" if result.success else result.stderr,
            "output": result.stdout,
            "execution_time": result.execution_time
        }
    
    def extract_strings(self, file_path: str, min_length: int = 4) -> Dict[str, Any]:
        """Convenience method for string extraction"""
        if not self.tool_manager.is_available('strings'):
            return {"status": "error", "message": "strings tool not available"}
        
        args = [f'-n{min_length}', file_path]
        result = self.tool_manager.execute('strings', args)
        
        return {
            "status": "success" if result.success else "error",
            "message": "Strings extracted" if result.success else result.stderr,
            "strings": result.stdout.split('\n') if result.success else [],
            "execution_time": result.execution_time
        }
    
    def adb_devices(self) -> Dict[str, Any]:
        """Convenience method for listing ADB devices"""
        if not self.tool_manager.is_available('adb'):
            return {"status": "error", "message": "adb not available"}
        
        result = self.tool_manager.execute('adb', ['devices'])
        
        devices = []
        if result.success:
            lines = result.stdout.split('\n')[1:]  # Skip header
            for line in lines:
                line = line.strip()
                if line and '\t' in line:
                    device_id, status = line.split('\t')
                    devices.append({'id': device_id, 'status': status})
        
        return {
            "status": "success" if result.success else "error",
            "message": "Devices listed" if result.success else result.stderr,
            "devices": devices,
            "execution_time": result.execution_time
        }

# Singleton instance
_category_manager = None

def get_category_manager() -> ToolCategoryManager:
    """Get singleton category manager"""
    global _category_manager
    if _category_manager is None:
        from .tool_manager import get_tool_manager
        _category_manager = ToolCategoryManager(get_tool_manager())
    return _category_manager 