"""
MCP Security Manager

Simple security controls for MCP tool access.
"""

import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

class SecurityManager:
    """Simple security manager for MCP operations"""
    
    def __init__(self):
        # Define safe operations that don't require special permissions
        self.safe_operations = {
            "scan_wifi_networks",
            "get_device_info", 
            "get_system_status",
            "start_wifi_monitoring",
            "stop_wifi_monitoring"
        }
        
        # Define operations that require confirmation
        self.confirmation_required = {
            "reset_device",
            "flash_firmware",
            "erase_flash"
        }
        
        # Define safe exploits
        self.safe_exploits = {
            "adb_check"
        }
        
        # Define dangerous exploits that require approval
        self.dangerous_exploits = {
            "hydra_ssh_attack"
        }
    
    def is_operation_allowed(self, operation_name: str, risk_level: str = "safe") -> bool:
        """Check if an operation is allowed based on risk level"""
        try:
            # Always allow safe operations
            if risk_level == "safe" or operation_name in self.safe_operations:
                return True
            
            # Medium risk operations require basic checks
            if risk_level == "medium":
                return True  # Allow for now, could add more checks
            
            # Dangerous operations require explicit approval
            if risk_level == "dangerous":
                return False  # Require explicit confirmation
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking operation permission: {e}")
            return False
    
    async def authorize_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Simple authorization check for tool calls
        
        Returns True if the operation is authorized, False otherwise.
        """
        try:
            # Always allow safe operations
            if tool_name in self.safe_operations:
                return True
            
            # Check confirmation for dangerous operations
            if tool_name in self.confirmation_required:
                return self._check_confirmation(arguments)
            
            # Handle exploit operations
            if tool_name == "run_safe_exploit":
                exploit_name = arguments.get("exploit_name")
                return exploit_name in self.safe_exploits
            
            if tool_name == "run_dangerous_exploit":
                # This would require approval token in a real implementation
                return self._check_approval_token(arguments)
            
            # Default: allow unknown operations (for development)
            # In production, this should be False
            logger.warning(f"Unknown tool '{tool_name}' - allowing for development")
            return True
            
        except Exception as e:
            logger.error(f"Error in authorization check: {e}")
            return False
    
    def _check_confirmation(self, arguments: Dict[str, Any]) -> bool:
        """Check if confirmation is provided for dangerous operations"""
        confirm = arguments.get("confirm", False)
        if not confirm:
            logger.warning("Operation requires confirmation but none provided")
            return False
        return True
    
    def _check_approval_token(self, arguments: Dict[str, Any]) -> bool:
        """Check approval token for dangerous exploits"""
        token = arguments.get("approval_token")
        if not token:
            logger.warning("Dangerous exploit requires approval token")
            return False
        
        # Simple token validation (in production, use proper JWT/OAuth)
        # For now, just check if token is present and not empty
        return len(token.strip()) > 0
    
    def get_security_info(self) -> Dict[str, Any]:
        """Get information about security policies"""
        return {
            "safe_operations": list(self.safe_operations),
            "confirmation_required": list(self.confirmation_required),
            "safe_exploits": list(self.safe_exploits),
            "dangerous_exploits": list(self.dangerous_exploits),
            "policies": {
                "confirmation_required_for_destructive_ops": True,
                "approval_token_required_for_dangerous_exploits": True,
                "safe_operations_always_allowed": True
            }
        } 