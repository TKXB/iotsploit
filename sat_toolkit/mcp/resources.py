"""
MCP Resources for SAT Toolkit

Resources provide read-only context and information to LLMs.
These resources expose information about devices, targets, exploits, and security status.
"""

import logging
from typing import Any, Dict, List
from mcp.types import Resource, TextResourceContents
from .adapters import DeviceAdapter, TargetAdapter, ExploitAdapter, SecurityAdapter

logger = logging.getLogger(__name__)

class ResourceProvider:
    """Provides MCP resources for SAT Toolkit"""
    
    def __init__(self):
        self.device_adapter = DeviceAdapter()
        self.target_adapter = TargetAdapter()
        self.exploit_adapter = ExploitAdapter()
        self.security_adapter = SecurityAdapter()
    
    def get_available_resources(self) -> List[Resource]:
        """Get list of all available resources"""
        return [
            Resource(
                uri="sat://devices/list",
                name="Available Devices",
                description="List of all available devices and their current status",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://devices/capabilities",
                name="Device Capabilities",
                description="Capabilities and supported commands for all device drivers",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://targets/current",
                name="Current Target",
                description="Information about the currently selected target system",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://targets/list",
                name="All Targets",
                description="List of all available target systems",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://exploits/catalog",
                name="Exploit Catalog",
                description="Catalog of available exploit plugins and their capabilities",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://security/status",
                name="Security Status",
                description="Overall security status and risk assessment",
                mimeType="application/json"
            ),
            Resource(
                uri="sat://wifi/networks",
                name="WiFi Networks",
                description="Last scanned WiFi networks from connected devices",
                mimeType="application/json"
            )
        ]
    
    def get_resource_content(self, uri: str) -> TextResourceContents:
        """Get content for a specific resource"""
        try:
            if uri == "sat://devices/list":
                return self._get_devices_list()
            elif uri == "sat://devices/capabilities":
                return self._get_device_capabilities()
            elif uri == "sat://targets/current":
                return self._get_current_target()
            elif uri == "sat://targets/list":
                return self._get_all_targets()
            elif uri == "sat://exploits/catalog":
                return self._get_exploit_catalog()
            elif uri == "sat://security/status":
                return self._get_security_status()
            elif uri == "sat://wifi/networks":
                return self._get_wifi_networks()
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
        except Exception as e:
            logger.error(f"Error getting resource content for {uri}: {e}")
            return TextResourceContents(
                type="text",
                text=f"Error retrieving resource: {str(e)}"
            )
    
    def _get_devices_list(self) -> TextResourceContents:
        """Get list of available devices"""
        devices = self.device_adapter.get_available_devices()
        driver_states = self.device_adapter.get_driver_states()
        
        content = {
            "devices": devices,
            "driver_states": driver_states,
            "summary": {
                "total_devices": len(devices),
                "connected_devices": len([d for d in devices if d.get("state") == "CONNECTED"]),
                "active_drivers": len([d for d in driver_states.values() if d.get("enabled", False)])
            }
        }
        
        return TextResourceContents(
            type="text",
            text=f"SAT Toolkit Devices:\n\n{self._format_json(content)}"
        )
    
    def _get_device_capabilities(self) -> TextResourceContents:
        """Get device capabilities for all drivers"""
        capabilities = {}
        
        # Get capabilities for each driver
        for driver_name in self.device_adapter.device_manager.list_drivers():
            if self.device_adapter.device_manager.is_driver_enabled(driver_name):
                capabilities[driver_name] = self.device_adapter.get_device_capabilities(driver_name)
        
        content = {
            "driver_capabilities": capabilities,
            "summary": {
                "total_drivers": len(capabilities),
                "total_commands": sum(len(cmds) for cmds in capabilities.values())
            }
        }
        
        return TextResourceContents(
            type="text",
            text=f"Device Capabilities:\n\n{self._format_json(content)}"
        )
    
    def _get_current_target(self) -> TextResourceContents:
        """Get current target information"""
        current_target = self.target_adapter.get_current_target()
        
        if current_target:
            # Get additional context
            adb_devices = self.target_adapter.get_adb_devices()
            components = self.target_adapter.get_target_components()
            
            content = {
                "target": current_target,
                "adb_devices": adb_devices,
                "components": components,
                "summary": {
                    "target_name": current_target.get("name", "Unknown"),
                    "target_type": current_target.get("type", "Unknown"),
                    "component_count": len(components),
                    "adb_device_count": len(adb_devices)
                }
            }
        else:
            content = {
                "target": None,
                "message": "No target currently selected",
                "available_targets": len(self.target_adapter.get_all_targets())
            }
        
        return TextResourceContents(
            type="text",
            text=f"Current Target:\n\n{self._format_json(content)}"
        )
    
    def _get_all_targets(self) -> TextResourceContents:
        """Get all available targets"""
        targets = self.target_adapter.get_all_targets()
        
        content = {
            "targets": targets,
            "summary": {
                "total_targets": len(targets),
                "target_types": list(set(t.get("type", "unknown") for t in targets))
            }
        }
        
        return TextResourceContents(
            type="text",
            text=f"All Targets:\n\n{self._format_json(content)}"
        )
    
    def _get_exploit_catalog(self) -> TextResourceContents:
        """Get exploit catalog"""
        exploits = self.exploit_adapter.get_available_exploits()
        
        # Categorize exploits by risk level
        safe_exploits = [e for e in exploits if not e.get("requires_root", False)]
        dangerous_exploits = [e for e in exploits if e.get("requires_root", False)]
        
        content = {
            "exploits": exploits,
            "categories": {
                "safe_exploits": safe_exploits,
                "dangerous_exploits": dangerous_exploits
            },
            "summary": {
                "total_exploits": len(exploits),
                "safe_count": len(safe_exploits),
                "dangerous_count": len(dangerous_exploits)
            }
        }
        
        return TextResourceContents(
            type="text",
            text=f"Exploit Catalog:\n\n{self._format_json(content)}"
        )
    
    def _get_security_status(self) -> TextResourceContents:
        """Get overall security status"""
        status = self.security_adapter.get_security_status()
        
        return TextResourceContents(
            type="text",
            text=f"Security Status:\n\n{self._format_json(status)}"
        )
    
    def _get_wifi_networks(self) -> TextResourceContents:
        """Get WiFi networks from connected devices"""
        wifi_data = {"networks": [], "message": "No WiFi data available"}
        
        try:
            # Get devices that support WiFi scanning
            devices = self.device_adapter.get_available_devices()
            esp32_devices = [d for d in devices if d.get("type") == "esp32" or "esp32" in d.get("driver", "")]
            
            if esp32_devices:
                # Try to get WiFi data from ESP32 devices
                for device in esp32_devices:
                    try:
                        # Execute scan_wifi command to get current networks
                        result = self.device_adapter.execute_device_command(
                            device["driver"], 
                            "scan_wifi", 
                            device["device_id"]
                        )
                        if result.get("status") == "success" and "networks" in result:
                            wifi_data["networks"].extend(result["networks"])
                    except Exception as e:
                        logger.debug(f"Could not get WiFi data from device {device['device_id']}: {e}")
                
                if wifi_data["networks"]:
                    wifi_data["message"] = f"Found {len(wifi_data['networks'])} WiFi networks"
                    wifi_data["last_scan"] = "Recent"
                else:
                    wifi_data["message"] = "No WiFi networks found in recent scans"
            else:
                wifi_data["message"] = "No WiFi-capable devices connected"
                
        except Exception as e:
            logger.error(f"Error getting WiFi networks: {e}")
            wifi_data["message"] = f"Error retrieving WiFi data: {str(e)}"
        
        return TextResourceContents(
            type="text",
            text=f"WiFi Networks:\n\n{self._format_json(wifi_data)}"
        )
    
    def _format_json(self, data: Any) -> str:
        """Format data as pretty JSON"""
        import json
        return json.dumps(data, indent=2, default=str) 