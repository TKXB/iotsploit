"""
Adapters to connect MCP with existing SAT Toolkit components.
These adapters bridge the MCP interface with the actual SAT Toolkit managers.
"""

import logging
from typing import Dict, List, Optional, Any
from sat_toolkit.core.device_manager import DeviceDriverManager
from sat_toolkit.core.exploit_manager import ExploitPluginManager
from sat_toolkit.models.Target_Model import TargetManager
from sat_toolkit.models.Device_Model import Device

logger = logging.getLogger(__name__)

class DeviceAdapter:
    """Adapter for SAT Toolkit Device Manager"""
    
    def __init__(self):
        self.device_manager = DeviceDriverManager()
    
    def get_available_devices(self) -> List[Dict[str, Any]]:
        """Get all available devices from all drivers"""
        devices = []
        try:
            for driver_name in self.device_manager.list_drivers():
                if self.device_manager.is_driver_enabled(driver_name):
                    # Scan for devices using this driver
                    scan_result = self.device_manager.scan_devices(driver_name)
                    if scan_result.get("status") == "success" and "devices" in scan_result:
                        for device in scan_result["devices"]:
                            devices.append({
                                "driver": driver_name,
                                "device_id": device.device_id,
                                "name": device.name,
                                "type": device.device_type.value if hasattr(device.device_type, 'value') else str(device.device_type),
                                "attributes": device.attributes,
                                "state": self.device_manager.get_device_state(driver_name, device.device_id).value
                            })
        except Exception as e:
            logger.error(f"Error getting available devices: {e}")
        
        return devices
    
    def get_device_capabilities(self, driver_name: str) -> Dict[str, str]:
        """Get supported commands for a device driver"""
        try:
            return self.device_manager.get_supported_commands(driver_name)
        except Exception as e:
            logger.error(f"Error getting device capabilities for {driver_name}: {e}")
            return {}
    
    def get_driver_states(self) -> Dict[str, Dict]:
        """Get the state of all drivers"""
        try:
            return self.device_manager.get_driver_states()
        except Exception as e:
            logger.error(f"Error getting driver states: {e}")
            return {}
    
    def execute_device_command(self, driver_name: str, command: str, device_id: str = "", **kwargs) -> Dict:
        """Execute a command on a device"""
        try:
            return self.device_manager.execute_command(driver_name, command, device_id, **kwargs)
        except Exception as e:
            logger.error(f"Error executing device command {command} on {driver_name}: {e}")
            return {"status": "error", "message": str(e)}
    
    def scan_devices(self, driver_name: str) -> Dict:
        """Scan for devices using a specific driver"""
        try:
            return self.device_manager.scan_devices(driver_name)
        except Exception as e:
            logger.error(f"Error scanning devices with {driver_name}: {e}")
            return {"status": "error", "message": str(e)}

class ExploitAdapter:
    """Adapter for SAT Toolkit Exploit Manager"""
    
    def __init__(self):
        self.exploit_manager = ExploitPluginManager()
    
    def get_available_exploits(self) -> List[Dict[str, Any]]:
        """Get all available exploit plugins"""
        exploits = []
        try:
            plugin_info = self.exploit_manager.list_plugin_info()
            for plugin_name, info in plugin_info.items():
                exploits.append({
                    "name": plugin_name,
                    "description": info.get("description", ""),
                    "author": info.get("author", ""),
                    "license": info.get("license", ""),
                    "parameters": info.get("parameters", {}),
                    "requires_root": info.get("requires_root", False)
                })
        except Exception as e:
            logger.error(f"Error getting available exploits: {e}")
        
        return exploits
    
    def get_exploit_info(self, exploit_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific exploit"""
        try:
            plugin = self.exploit_manager.get_plugin(exploit_name)
            if plugin:
                info = plugin.get_info()
                return {
                    "name": info.get("Name", exploit_name),
                    "description": info.get("Description", ""),
                    "author": info.get("Author", ""),
                    "license": info.get("License", ""),
                    "parameters": info.get("Parameters", {}),
                    "requires_root": info.get("RequiresRoot", False)
                }
        except Exception as e:
            logger.error(f"Error getting exploit info for {exploit_name}: {e}")
        
        return None
    
    def execute_exploit(self, exploit_name: str, target: Optional[Any] = None, parameters: Optional[Dict] = None) -> Dict:
        """Execute an exploit plugin"""
        try:
            result = self.exploit_manager.execute_plugin(exploit_name, target, parameters)
            if result:
                return {
                    "status": "success" if result.success else "failed",
                    "message": result.message,
                    "data": result.data
                }
            else:
                return {"status": "error", "message": "Plugin execution returned None"}
        except Exception as e:
            logger.error(f"Error executing exploit {exploit_name}: {e}")
            return {"status": "error", "message": str(e)}

class TargetAdapter:
    """Adapter for SAT Toolkit Target Manager"""
    
    def __init__(self):
        self.target_manager = TargetManager.get_instance()
    
    def get_current_target(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected target"""
        try:
            current_target = self.target_manager.get_current_target()
            if current_target:
                return current_target.get_info()
        except Exception as e:
            logger.error(f"Error getting current target: {e}")
        
        return None
    
    def get_all_targets(self) -> List[Dict[str, Any]]:
        """Get all available targets"""
        try:
            return self.target_manager.get_all_targets()
        except Exception as e:
            logger.error(f"Error getting all targets: {e}")
            return []
    
    def get_target_components(self, target_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get components of a target (current target if target_id is None)"""
        components = []
        try:
            if target_id:
                # Get specific target by ID
                targets = self.target_manager.get_all_targets()
                target_data = next((t for t in targets if t.get("target_id") == target_id), None)
            else:
                # Get current target
                current_target = self.target_manager.get_current_target()
                target_data = current_target.get_info() if current_target else None
            
            if target_data and "components" in target_data:
                components = target_data["components"]
        except Exception as e:
            logger.error(f"Error getting target components: {e}")
        
        return components
    
    def get_adb_devices(self, target_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get ADB devices from a target"""
        adb_devices = []
        try:
            components = self.get_target_components(target_id)
            for component in components:
                if component.get("type") == "adb_device":
                    adb_devices.append(component)
        except Exception as e:
            logger.error(f"Error getting ADB devices: {e}")
        
        return adb_devices

class SecurityAdapter:
    """Adapter for security-related operations"""
    
    def __init__(self):
        self.device_adapter = DeviceAdapter()
        self.exploit_adapter = ExploitAdapter()
        self.target_adapter = TargetAdapter()
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get overall security status of the system"""
        try:
            current_target = self.target_adapter.get_current_target()
            devices = self.device_adapter.get_available_devices()
            exploits = self.exploit_adapter.get_available_exploits()
            
            # Count safe vs dangerous exploits
            safe_exploits = [e for e in exploits if not e.get("requires_root", False)]
            dangerous_exploits = [e for e in exploits if e.get("requires_root", False)]
            
            return {
                "current_target": current_target.get("name") if current_target else "None",
                "connected_devices": len(devices),
                "available_exploits": len(exploits),
                "safe_exploits": len(safe_exploits),
                "dangerous_exploits": len(dangerous_exploits),
                "active_drivers": len([d for d in self.device_adapter.get_driver_states().values() if d.get("enabled", False)])
            }
        except Exception as e:
            logger.error(f"Error getting security status: {e}")
            return {"error": str(e)}
    
    def classify_operation_risk(self, operation: str, parameters: Dict = None) -> str:
        """Classify the risk level of an operation"""
        parameters = parameters or {}
        
        # High-risk operations
        high_risk_operations = [
            "flash_firmware", "erase_flash", "reset", "factory_reset",
            "root_device", "unlock_bootloader", "modify_system"
        ]
        
        # Medium-risk operations
        medium_risk_operations = [
            "execute_exploit", "brute_force", "password_attack",
            "network_scan", "port_scan"
        ]
        
        # Check operation name
        if any(risk_op in operation.lower() for risk_op in high_risk_operations):
            return "dangerous"
        elif any(risk_op in operation.lower() for risk_op in medium_risk_operations):
            return "medium"
        
        # Check parameters for risky settings
        if parameters.get("require_root", False) or parameters.get("try_root", False):
            return "dangerous"
        
        if parameters.get("force", False) or parameters.get("destructive", False):
            return "dangerous"
        
        return "safe" 