#!/usr/bin/env python3
"""
JSON-based Tool Configuration Management
=======================================

Manages tool configurations using JSON files instead of hardcoded Python dictionaries.
This allows for easy modification of tool definitions without code changes.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

@dataclass
class ToolConfig:
    """Tool configuration data structure"""
    name: str
    aliases: List[str] = field(default_factory=list)
    min_version: Optional[str] = None
    platforms: List[str] = field(default_factory=lambda: ['linux', 'darwin', 'windows'])
    path: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    required: bool = False
    install_hint: Optional[str] = None
    version_command: List[str] = field(default_factory=lambda: ['--version'])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolConfig':
        """Create from dictionary loaded from JSON"""
        # Filter out fields that are not part of ToolConfig constructor
        # These fields are runtime fields that should not be passed to constructor
        excluded_fields = {
            'version', 'status', 'last_checked', 'metadata', 'dependencies',
            'max_version'
        }
        
        # Create a filtered copy of the data
        filtered_data = {k: v for k, v in data.items() if k not in excluded_fields}
        
        return cls(**filtered_data)

class ToolConfigManager:
    """Manages tool configurations from JSON files"""
    
    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        self.config_dir = Path(config_dir) if config_dir else self._get_default_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("tool_config")
        self._tool_configs: Dict[str, ToolConfig] = {}
        self._category_configs: Dict[str, Dict[str, Any]] = {}
        
        # Load configurations
        self._load_all_configs()
    
    def _get_default_config_dir(self) -> Path:
        """Get default configuration directory"""
        # Use project root/configs/tools
        project_root = Path(__file__).parent.parent.parent
        return project_root / "configs" / "tools"
    
    def _load_all_configs(self):
        """Load all tool configurations from JSON files"""
        self.logger.info(f"Loading tool configurations from {self.config_dir}")
        
        # Load category configurations
        self._load_category_configs()
        
        # Load individual tool configurations
        self._load_tool_configs()
        
        self.logger.info(f"Loaded {len(self._tool_configs)} tool configurations")
    
    def _load_category_configs(self):
        """Load category configuration files"""
        category_files = list(self.config_dir.glob("*_category.json"))
        
        for category_file in category_files:
            try:
                with open(category_file, 'r', encoding='utf-8') as f:
                    category_data = json.load(f)
                
                category_name = category_file.stem.replace('_category', '')
                self._category_configs[category_name] = category_data
                
                self.logger.debug(f"Loaded category config: {category_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to load category config {category_file}: {e}")
    
    def _load_tool_configs(self):
        """Load tool configuration files"""
        # Load from category files
        for category_name, category_data in self._category_configs.items():
            tools = category_data.get('tools', [])
            for tool_data in tools:
                try:
                    # Add category info to tool
                    tool_data['category'] = category_name
                    tool_config = ToolConfig.from_dict(tool_data)
                    self._tool_configs[tool_config.name] = tool_config
                    
                    # Also register aliases
                    for alias in tool_config.aliases:
                        self._tool_configs[alias] = tool_config
                        
                except Exception as e:
                    self.logger.error(f"Failed to load tool config {tool_data.get('name', 'unknown')}: {e}")
        
        # Load individual tool files
        tool_files = [f for f in self.config_dir.glob("*.json") if not f.name.endswith('_category.json')]
        
        for tool_file in tool_files:
            try:
                with open(tool_file, 'r', encoding='utf-8') as f:
                    tool_data = json.load(f)
                
                # Handle different JSON structures
                if 'tools' in tool_data and isinstance(tool_data['tools'], list):
                    # This is a tools collection file (like tools.json)
                    tools = tool_data['tools']
                    for tool_item in tools:
                        try:
                            tool_config = ToolConfig.from_dict(tool_item)
                            self._tool_configs[tool_config.name] = tool_config
                            
                            # Also register aliases
                            for alias in tool_config.aliases:
                                self._tool_configs[alias] = tool_config
                        except Exception as e:
                            self.logger.error(f"Failed to load tool {tool_item.get('name', 'unknown')} from {tool_file.name}: {e}")
                
                elif isinstance(tool_data, list):
                    # This is an array of tools
                    tools = tool_data
                    for tool_item in tools:
                        try:
                            tool_config = ToolConfig.from_dict(tool_item)
                            self._tool_configs[tool_config.name] = tool_config
                            
                            # Also register aliases
                            for alias in tool_config.aliases:
                                self._tool_configs[alias] = tool_config
                        except Exception as e:
                            self.logger.error(f"Failed to load tool {tool_item.get('name', 'unknown')} from {tool_file.name}: {e}")
                
                elif 'name' in tool_data:
                    # This is a single tool configuration
                    tool_config = ToolConfig.from_dict(tool_data)
                    self._tool_configs[tool_config.name] = tool_config
                    
                    # Also register aliases
                    for alias in tool_config.aliases:
                        self._tool_configs[alias] = tool_config
                
                else:
                    self.logger.warning(f"Unrecognized tool config format in {tool_file.name}")
                
                self.logger.debug(f"Loaded tool config file: {tool_file.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to load tool config {tool_file}: {e}")
    
    def get_tool_config(self, tool_name: str) -> Optional[ToolConfig]:
        """Get tool configuration by name or alias"""
        return self._tool_configs.get(tool_name)
    
    def get_tools_by_category(self, category: str) -> List[ToolConfig]:
        """Get all tools in a specific category"""
        return [config for config in self._tool_configs.values() 
                if config.category == category and config.name in self._tool_configs]
    
    def get_all_categories(self) -> List[str]:
        """Get list of all categories"""
        categories = set()
        for config in self._tool_configs.values():
            if config.category:
                categories.add(config.category)
        return sorted(list(categories))
    
    def get_category_info(self, category: str) -> Optional[Dict[str, Any]]:
        """Get category information"""
        return self._category_configs.get(category)
    
    def add_tool_config(self, tool_config: ToolConfig, save: bool = True) -> bool:
        """Add a new tool configuration"""
        try:
            self._tool_configs[tool_config.name] = tool_config
            
            # Register aliases
            for alias in tool_config.aliases:
                self._tool_configs[alias] = tool_config
            
            if save:
                self._save_tool_config(tool_config)
            
            self.logger.info(f"Added tool configuration: {tool_config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add tool config {tool_config.name}: {e}")
            return False
    
    def _save_tool_config(self, tool_config: ToolConfig):
        """Save tool configuration to JSON file"""
        if tool_config.category:
            # Save to category file
            category_file = self.config_dir / f"{tool_config.category}_category.json"
            
            if category_file.exists():
                with open(category_file, 'r', encoding='utf-8') as f:
                    category_data = json.load(f)
            else:
                category_data = {
                    "name": tool_config.category.title(),
                    "description": f"Tools for {tool_config.category}",
                    "tools": []
                }
            
            # Add or update tool in category
            tools = category_data.get('tools', [])
            tool_dict = tool_config.to_dict()
            del tool_dict['category']  # Don't store category in tool data
            
            # Remove existing tool if present
            tools = [t for t in tools if t.get('name') != tool_config.name]
            tools.append(tool_dict)
            
            category_data['tools'] = tools
            
            with open(category_file, 'w', encoding='utf-8') as f:
                json.dump(category_data, f, indent=2, ensure_ascii=False)
        else:
            # Save as individual tool file
            tool_file = self.config_dir / f"{tool_config.name}.json"
            with open(tool_file, 'w', encoding='utf-8') as f:
                json.dump(tool_config.to_dict(), f, indent=2, ensure_ascii=False)
    
    def remove_tool_config(self, tool_name: str) -> bool:
        """Remove tool configuration"""
        try:
            if tool_name in self._tool_configs:
                tool_config = self._tool_configs[tool_name]
                
                # Remove from memory
                del self._tool_configs[tool_name]
                for alias in tool_config.aliases:
                    if alias in self._tool_configs:
                        del self._tool_configs[alias]
                
                # Remove from file
                self._remove_tool_from_file(tool_config)
                
                self.logger.info(f"Removed tool configuration: {tool_name}")
                return True
            else:
                self.logger.warning(f"Tool configuration not found: {tool_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to remove tool config {tool_name}: {e}")
            return False
    
    def _remove_tool_from_file(self, tool_config: ToolConfig):
        """Remove tool from its configuration file"""
        if tool_config.category:
            # Remove from category file
            category_file = self.config_dir / f"{tool_config.category}_category.json"
            
            if category_file.exists():
                with open(category_file, 'r', encoding='utf-8') as f:
                    category_data = json.load(f)
                
                tools = category_data.get('tools', [])
                tools = [t for t in tools if t.get('name') != tool_config.name]
                category_data['tools'] = tools
                
                with open(category_file, 'w', encoding='utf-8') as f:
                    json.dump(category_data, f, indent=2, ensure_ascii=False)
        else:
            # Remove individual tool file
            tool_file = self.config_dir / f"{tool_config.name}.json"
            if tool_file.exists():
                tool_file.unlink()
    
    def reload_configs(self):
        """Reload all configurations from files"""
        self._tool_configs.clear()
        self._category_configs.clear()
        self._load_all_configs()
        self.logger.info("Reloaded all tool configurations")
    
    def export_config(self, output_file: Union[str, Path]) -> bool:
        """Export all configurations to a single JSON file"""
        try:
            output_path = Path(output_file)
            
            export_data = {
                "categories": self._category_configs,
                "tools": {name: config.to_dict() for name, config in self._tool_configs.items()
                         if name == config.name}  # Only export primary names, not aliases
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Exported configurations to {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export configurations: {e}")
            return False
    
    def import_config(self, input_file: Union[str, Path]) -> bool:
        """Import configurations from a JSON file"""
        try:
            input_path = Path(input_file)
            
            with open(input_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Import categories
            categories = import_data.get('categories', {})
            for category_name, category_data in categories.items():
                self._category_configs[category_name] = category_data
            
            # Import tools
            tools = import_data.get('tools', {})
            for tool_name, tool_data in tools.items():
                tool_config = ToolConfig.from_dict(tool_data)
                self._tool_configs[tool_config.name] = tool_config
                
                # Register aliases
                for alias in tool_config.aliases:
                    self._tool_configs[alias] = tool_config
            
            self.logger.info(f"Imported configurations from {input_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to import configurations: {e}")
            return False
    
    def validate_configs(self) -> Dict[str, List[str]]:
        """Validate all tool configurations"""
        issues = {
            'missing_required_fields': [],
            'invalid_platforms': [],
            'duplicate_names': [],
            'invalid_categories': []
        }
        
        seen_names = set()
        valid_platforms = {'linux', 'darwin', 'windows'}
        
        for tool_name, config in self._tool_configs.items():
            # Skip aliases
            if tool_name != config.name:
                continue
            
            # Check required fields
            if not config.name:
                issues['missing_required_fields'].append(f"Tool missing name")
            
            # Check for duplicates
            if config.name in seen_names:
                issues['duplicate_names'].append(config.name)
            seen_names.add(config.name)
            
            # Check platforms
            for platform in config.platforms:
                if platform not in valid_platforms:
                    issues['invalid_platforms'].append(f"{config.name}: {platform}")
            
            # Check category exists
            if config.category and config.category not in self._category_configs:
                issues['invalid_categories'].append(f"{config.name}: {config.category}")
        
        return issues
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded configurations"""
        unique_tools = {config.name: config for config in self._tool_configs.values()}
        
        stats = {
            'total_tools': len(unique_tools),
            'total_aliases': len(self._tool_configs) - len(unique_tools),
            'categories': len(self._category_configs),
            'tools_by_category': {},
            'tools_by_platform': {'linux': 0, 'darwin': 0, 'windows': 0},
            'required_tools': 0,
            'optional_tools': 0
        }
        
        for config in unique_tools.values():
            # Count by category
            category = config.category or 'uncategorized'
            stats['tools_by_category'][category] = stats['tools_by_category'].get(category, 0) + 1
            
            # Count by platform
            for platform in config.platforms:
                if platform in stats['tools_by_platform']:
                    stats['tools_by_platform'][platform] += 1
            
            # Count required vs optional
            if config.required:
                stats['required_tools'] += 1
            else:
                stats['optional_tools'] += 1
        
        return stats

# Singleton instance
_config_manager = None

def get_tool_config_manager() -> ToolConfigManager:
    """Get singleton tool configuration manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ToolConfigManager()
    return _config_manager 