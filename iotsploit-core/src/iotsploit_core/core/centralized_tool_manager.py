#!/usr/bin/env python3
"""
Centralized Tool Manager for IoTSploit
=====================================

Provides a unified interface for managing all third-party tools with simplified single category.
Orchestrates tool discovery, execution, health monitoring, and installation recommendations.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum

from .tool_manager import get_tool_manager, ToolManager, ExecutionResult
from .execution_backend import get_execution_backend_manager
from .execution_queue import get_execution_queue, get_task_scheduler
from .tool_categories import get_category_manager, ToolCategoryManager

logger = logging.getLogger(__name__)

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

class CentralizedToolManager:
    """
    Centralized manager that orchestrates all tool management components
    """
    
    def __init__(self):
        self.logger = logging.getLogger("centralized_tool_manager")
        
        # Initialize core components
        self.tool_manager = get_tool_manager()
        self.backend_manager = get_execution_backend_manager()
        self.queue_manager = get_execution_queue()
        self.category_manager = get_category_manager()
        
        self.logger.info("Centralized Tool Manager initialized")
    
    def get_system_status(self) -> SystemStatus:
        """Get comprehensive system status"""
        validation = self.category_manager.validate_tools()
        
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
        validation = self.category_manager.validate_tools()
        
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
            'queue_status': self.queue_manager.get_stats()
        }
        
        return report
    
    def get_installation_guide(self) -> Dict[str, Any]:
        """Get installation recommendations with hints"""
        missing_tools = self.category_manager.get_missing_tools()
        install_hints = self.category_manager.get_install_hints()
        required_tools = self.category_manager.get_required_tools()
        optional_tools = self.category_manager.get_optional_tools()
        
        # Separate required and optional missing tools
        required_missing = [t for t in missing_tools if t in required_tools]
        optional_missing = [t for t in missing_tools if t in optional_tools]
        
        guide = {
            'required_tools': {},
            'optional_tools': {},
            'priority_order': required_missing + optional_missing[:5]  # Top 5 optional
        }
        
        for tool in required_missing:
            guide['required_tools'][tool] = {
                'description': self._get_tool_description(tool),
                'install_hint': install_hints.get(tool, "No installation hint available"),
                'priority': 'HIGH'
            }
        
        for tool in optional_missing:
            guide['optional_tools'][tool] = {
                'description': self._get_tool_description(tool),
                'install_hint': install_hints.get(tool, "No installation hint available"),
                'priority': 'MEDIUM'
            }
        
        return guide
    
    def _get_tool_description(self, tool_name: str) -> str:
        """Get tool description from config"""
        tool_config = self.category_manager.get_tool_config(tool_name)
        return tool_config.description if tool_config else "No description available"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    # Tool execution methods
    def execute_tool(self, tool_name: str, args: List[str], **kwargs) -> ExecutionResult:
        """Execute a tool directly"""
        return self.tool_manager.execute(tool_name, args, **kwargs)
    
    def is_tool_available(self, tool_name: str) -> bool:
        """Check if a tool is available"""
        return self.tool_manager.is_available(tool_name)
    
    def discover_tools(self) -> Dict[str, Any]:
        """Discover and validate all tools"""
        return self.tool_manager.discover_tools()
    
    # Convenience methods
    def flash_esp32(self, port: str, firmware_path: str, **kwargs) -> Dict[str, Any]:
        """Flash ESP32 firmware"""
        return self.category_manager.flash_esp32(port, firmware_path, **kwargs)
    
    def scan_network(self, target: str, ports: str = "1-1000", **kwargs) -> Dict[str, Any]:
        """Perform network scan"""
        return self.category_manager.port_scan(target, ports, **kwargs)
    
    def extract_strings(self, file_path: str, min_length: int = 4) -> Dict[str, Any]:
        """Extract strings from file"""
        return self.category_manager.extract_strings(file_path, min_length)
    
    def list_adb_devices(self) -> Dict[str, Any]:
        """List ADB devices"""
        return self.category_manager.adb_devices()
    
    # Configuration management
    def reload_configurations(self):
        """Reload all tool configurations"""
        self.category_manager.reload_configurations()
        self.logger.info("Reloaded all configurations")
    
    def add_tool(self, tool_config) -> bool:
        """Add a new tool"""
        return self.category_manager.add_tool(tool_config)
    
    def get_config_stats(self) -> Dict[str, Any]:
        """Get configuration statistics"""
        return self.category_manager.get_config_stats()
    
    # System management
    def initialize(self) -> bool:
        """Initialize the system"""
        try:
            self.logger.info("Initializing centralized tool manager...")
            
            # Discover tools
            discovery_results = self.discover_tools()
            self.logger.info(f"Discovered {len(discovery_results)} tools")
            
            # Check system health
            status = self.get_system_status()
            self.logger.info(f"System health: {status.health.value}")
            
            if status.health == SystemHealth.CRITICAL:
                self.logger.warning(f"System is in CRITICAL state - {status.required_missing} required tools missing")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize system: {e}")
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.queue_manager.shutdown()
            self.logger.info("Centralized tool manager cleaned up")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()

    def submit_task(self, tool_name: str, args: List[str], 
                   priority: Union[str, "TaskPriority"] = "normal", **kwargs) -> str:
        """Submit a tool execution task to the queue"""
        from .execution_queue import TaskPriority
        
        # Handle both string and enum priority inputs
        if isinstance(priority, TaskPriority):
            task_priority = priority
        else:
            # Convert priority string to enum
            priority_map = {
                'critical': TaskPriority.CRITICAL,
                'high': TaskPriority.HIGH,
                'normal': TaskPriority.NORMAL,
                'low': TaskPriority.LOW,
                'background': TaskPriority.BACKGROUND
            }
            task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
        
        # Get tool path
        tool_info = self.tool_manager.registry.get_tool(tool_name)
        if not tool_info:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        return self.queue_manager.submit_task(
            tool_name=tool_name,
            tool_path=tool_info.path,
            args=args,
            priority=task_priority,
            **kwargs
        )
    
    def get_task(self, task_id: str):
        """Get task by ID"""
        return self.queue_manager.get_task(task_id)
    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None):
        """Wait for task completion"""
        return self.queue_manager.wait_for_task(task_id, timeout)
    
    def get_queue_stats(self):
        """Get queue statistics"""
        return self.queue_manager.get_stats()
    
    def list_execution_backends(self) -> List[str]:
        """List available execution backends"""
        return self.backend_manager.list_available_backends()
    
    def set_default_backend(self, backend_name: str):
        """Set default execution backend"""
        self.backend_manager.set_default_backend(backend_name)
    
    def get_system_health(self, force_refresh: bool = False):
        """Get system health with category status"""
        status = self.get_system_status()
        validation = self.category_manager.validate_tools()
        
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
        missing_tools = self.category_manager.get_missing_tools()
        required_tools = self.category_manager.get_required_tools()
        
        required_missing = [t for t in missing_tools if t in required_tools]
        optional_missing = [t for t in missing_tools if t not in required_tools]
        
        return {
            "tools": {
                "required": required_missing,
                "optional": optional_missing
            }
        }
    
    def shutdown(self, wait: bool = True):
        """Shutdown the system"""
        self.cleanup()

# Singleton instance
_centralized_manager = None

def get_centralized_tool_manager() -> CentralizedToolManager:
    """Get singleton centralized tool manager"""
    global _centralized_manager
    if _centralized_manager is None:
        _centralized_manager = CentralizedToolManager()
    return _centralized_manager

def print_system_report():
    """Print a comprehensive system report"""
    manager = get_centralized_tool_manager()
    
    print("\n" + "="*60)
    print("🔧 IOTSPLOIT TOOL MANAGEMENT SYSTEM REPORT")
    print("="*60)
    
    # Get system status
    status = manager.get_system_status()
    health_icon = {
        "healthy": "✅",
        "degraded": "⚠️",
        "critical": "❌"
    }.get(status.health.value, "❓")
    
    print(f"\n📊 System Health: {health_icon} {status.health.value.upper()}")
    print(f"🔧 Total Tools: {status.total_tools}")
    print(f"✅ Available: {status.available_tools}")
    print(f"❌ Missing: {status.missing_tools}")
    print(f"🔴 Required Missing: {status.required_missing}")
    print(f"🚀 Can Operate: {'Yes' if status.can_operate else 'No'}")
    
    # Show recommendations
    if status.recommendations:
        print(f"\n💡 Recommendations:")
        for rec in status.recommendations:
            print(f"   • {rec}")
    
    # Show queue stats
    try:
        queue_stats = manager.get_queue_stats()
        print(f"\n📋 Queue Status:")
        print(f"   • Total Tasks: {queue_stats.total_tasks}")
        print(f"   • Running: {queue_stats.running_tasks}")
        print(f"   • Pending: {queue_stats.pending_tasks}")
        print(f"   • Completed: {queue_stats.completed_tasks}")
        print(f"   • Failed: {queue_stats.failed_tasks}")
        if queue_stats.average_execution_time > 0:
            print(f"   • Avg Execution Time: {queue_stats.average_execution_time:.2f}s")
    except Exception as e:
        print(f"\n📋 Queue Status: Error - {e}")
    
    # Show category info
    try:
        category_info = manager.category_manager.get_category_info()
        print(f"\n📂 Tool Category: {category_info.name}")
        print(f"   Description: {category_info.description}")
        print(f"   Tools: {len(category_info.tools)}")
        
        # Show available vs missing
        available = manager.category_manager.get_available_tools()
        missing = manager.category_manager.get_missing_tools()
        required = manager.category_manager.get_required_tools()
        
        print(f"\n🔧 Tool Breakdown:")
        print(f"   ✅ Available: {len(available)}")
        if available[:5]:  # Show first 5
            for tool in available[:5]:
                print(f"      • {tool}")
            if len(available) > 5:
                print(f"      ... and {len(available) - 5} more")
        
        if missing:
            print(f"   ❌ Missing: {len(missing)}")
            required_missing = [t for t in missing if t in required]
            optional_missing = [t for t in missing if t not in required]
            
            if required_missing:
                print(f"      🔴 Required: {', '.join(required_missing[:3])}")
                if len(required_missing) > 3:
                    print(f"         ... and {len(required_missing) - 3} more")
            
            if optional_missing:
                print(f"      🟡 Optional: {', '.join(optional_missing[:3])}")
                if len(optional_missing) > 3:
                    print(f"         ... and {len(optional_missing) - 3} more")
    
    except Exception as e:
        print(f"\n📂 Category Status: Error - {e}")
    
    print("\n" + "="*60) 