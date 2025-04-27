
import os
import importlib.util
import logging
import threading
from typing import Dict, List, Optional, Any
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.core.device_spec import DeviceState
from sat_toolkit.config import DEVICE_PLUGINS_DIR

logger = logging.getLogger(__name__)

class DeviceDriverManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DeviceDriverManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info("Initializing DeviceDriverManager")
            self.plugins = {}
            self.drivers = {}  # Store driver instances
            self.device_states = {}  # Store device states, format: 'driver_name::device_id': DeviceState
            self._connection_locks = {}  # Device operation locks, format: 'driver_name::device_id': Lock
            
            # Define valid state transitions
            self._state_transitions = {
                DeviceState.UNKNOWN: [DeviceState.DISCOVERED],
                DeviceState.DISCOVERED: [DeviceState.INITIALIZED],
                DeviceState.INITIALIZED: [DeviceState.CONNECTED, DeviceState.DISCONNECTED],
                DeviceState.CONNECTED: [DeviceState.ACTIVE, DeviceState.DISCONNECTED],
                DeviceState.ACTIVE: [DeviceState.CONNECTED, DeviceState.ERROR],
                DeviceState.ERROR: [DeviceState.DISCONNECTED],
                DeviceState.DISCONNECTED: [DeviceState.INITIALIZED]
            }
            
            self.load_plugins()
            self._initialized = True
            logger.info("DeviceDriverManager initialized")

    def load_plugins(self):
        """Load all device driver plugins"""
        plugin_dir = os.path.join(os.path.dirname(__file__), DEVICE_PLUGINS_DIR)
        logger.info(f"Loading device plugins from {plugin_dir}")
        for root, _, files in os.walk(plugin_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("__"):
                    self.load_plugin(os.path.join(root, filename))

    def load_plugin(self, filepath: str):
        """Load a single plugin"""
        try:
            module_name = os.path.splitext(os.path.basename(filepath))[0]
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Modify plugin registration logic, remove pluggy related code
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseDeviceDriver) and 
                    attr != BaseDeviceDriver):
                    driver_instance = attr()
                    self.plugins[module_name] = module
                    self.drivers[module_name] = driver_instance
                    logger.info(f"Loaded device plugin: {module_name} ({attr_name})")
                    break
        except Exception as e:
            logger.error(f"Failed to load plugin {filepath}: {str(e)}")

    def execute_command(self, driver_name: str, command: str, device_id: str = "", **kwargs) -> Dict:
        """Execute device command
        
        Args:
            driver_name: Driver name (e.g., 'drv_socketcan')
            command: Command to execute
            device_id: Optional device ID for multi-device scenarios
            **kwargs: Command parameters
        
        Returns:
            Dict: Dictionary containing operation results
        """
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='command',
            device_id=device_id,
            command=command,
            args=kwargs
        )

    def scan_devices(self, driver_name: str) -> Dict:
        """Scan devices"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='scan'
        )

    def initialize_device(self, driver_name: str, device: Device) -> Dict:
        """Initialize device"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='initialize',
            device=device
        )

    def connect_device(self, driver_name: str, device: Device) -> Dict:
        """Connect device"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='connect',
            device=device
        )

    def reset_device(self, driver_name: str, device: Device) -> Dict:
        """Reset device"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='reset',
            device=device
        )

    def close_device(self, driver_name: str, device: Device) -> Dict:
        """Close device"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='close',
            device=device
        )

    def get_device_state(self, driver_name: str, device_id: str = "") -> DeviceState:
        """Get current device state"""
        device_key = self._get_device_key(driver_name, device_id=device_id)
        return self.device_states.get(device_key, DeviceState.UNKNOWN)

    def get_supported_commands(self, driver_name: str) -> Dict[str, str]:
        """Get commands supported by the device"""
        driver = self.get_driver_instance(driver_name)
        if driver:
            return driver.get_supported_commands()
        return {}

    def get_plugin_commands(self, plugin_name: str) -> Dict[str, str]:
        """Get commands supported by the plugin
        
        Args:
            plugin_name: Plugin name
            
        Returns:
            Dict[str, str]: Dictionary of command names and descriptions
        """
        driver = self.get_driver_instance(plugin_name)
        if driver:
            return driver.get_supported_commands()
        return {}

    def _manage_device_lifecycle(self, driver_name: str, action: str, **kwargs) -> Dict:
        """Internal method for device lifecycle management"""
        try:
            driver = self.get_driver_instance(driver_name)
            if not driver:
                return {
                    "status": "error",
                    "message": f"Driver {driver_name} not found"
                }

            device = kwargs.get('device')
            device_id = kwargs.get('device_id', '')
            device_key = self._get_device_key(driver_name, device, device_id)

            with self._get_device_lock(device_key):
                current_state = self.device_states.get(device_key, DeviceState.UNKNOWN)
                
                # Modify state transition logic
                if action != 'scan':
                    if action == 'initialize':
                        # For initialization operations, only execute in uninitialized state
                        if current_state not in [DeviceState.UNKNOWN, DeviceState.DISCOVERED]:
                            return {
                                "status": "error",
                                "message": f"Cannot perform initialize in current state {current_state}. Expected states: [unknown, discovered]"
                            }
                    elif action == 'connect':
                        # For connection operations, ensure the device is initialized
                        if current_state == DeviceState.UNKNOWN:
                            # Auto scan
                            scan_result = self._handle_scan(driver, driver_name, **kwargs)
                            if scan_result["status"] != "success":
                                return scan_result
                            current_state = self.device_states.get(device_key, DeviceState.UNKNOWN)
                        
                        if current_state == DeviceState.DISCOVERED:
                            # Only initialize in discovered state
                            init_result = self._handle_initialize(driver, driver_name, **kwargs)
                            if init_result["status"] != "success":
                                return init_result
                            current_state = self.device_states.get(device_key, DeviceState.UNKNOWN)
                        
                        if current_state != DeviceState.INITIALIZED:
                            return {
                                "status": "error",
                                "message": f"Cannot connect device in state {current_state}. Expected state: initialized"
                            }

                return self._execute_action(driver, action, current_state, device_key, driver_name, **kwargs)

        except Exception as e:
            logger.error(f"Lifecycle management failed: {str(e)}", exc_info=True)
            self._update_device_state(device_key, DeviceState.ERROR)
            return {
                "status": "error",
                "message": str(e)
            }

    def _get_device_lock(self, device_key: str) -> threading.Lock:
        """Get device operation lock"""
        if device_key not in self._connection_locks:
            self._connection_locks[device_key] = threading.Lock()
        return self._connection_locks[device_key]

    def _update_device_state(self, device_key: str, new_state: DeviceState):
        """Update device state"""
        current_state = self.device_states.get(device_key, DeviceState.UNKNOWN)
        
        if current_state == new_state:
            return
        
        if new_state in self._state_transitions.get(current_state, []):
            self.device_states[device_key] = new_state
            logger.info(f"Device {device_key} state changed: {current_state} -> {new_state}")
        else:
            # Special handling: don't downgrade if device is in a higher state
            state_hierarchy = {
                DeviceState.UNKNOWN: 0,
                DeviceState.DISCOVERED: 1,
                DeviceState.INITIALIZED: 2,
                DeviceState.CONNECTED: 3,
                DeviceState.ACTIVE: 4,
            }
            
            # Only update when new state's level is higher than current state
            if state_hierarchy.get(new_state, 0) > state_hierarchy.get(current_state, 0):
                self.device_states[device_key] = new_state
                logger.info(f"Device {device_key} state upgraded: {current_state} -> {new_state}")
            else:
                logger.info(f"Ignoring state transition: {current_state} -> {new_state}")

    def _execute_action(self, 
                        driver: BaseDeviceDriver, 
                        action: str, 
                        current_state: DeviceState, 
                        device_key: str, 
                        driver_name: str,
                        **kwargs) -> Dict:
        """Execute specific action"""
        try:
            if action == 'scan':
                return self._handle_scan(driver, driver_name, **kwargs)
            elif action == 'initialize':
                return self._handle_initialize(driver, driver_name, **kwargs)
            elif action == 'connect':
                return self._handle_connect(driver, driver_name, **kwargs)
            elif action == 'command':
                return self._handle_command(driver, driver_name, device_key, **kwargs)
            elif action == 'reset':
                return self._handle_reset(driver, driver_name, **kwargs)
            elif action == 'close':
                return self._handle_close(driver, driver_name, **kwargs)
            else:
                return {"status": "error", "message": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            self._update_device_state(device_key, DeviceState.ERROR)
            return {"status": "error", "message": str(e)}

    def _get_device_key(self, driver_name: str, device: Device = None, device_id: str = "") -> str:
        """Method to generate unified device key
        
        Args:
            driver_name: Driver name (e.g., 'drv_socketcan')
            device: Device instance (optional)
            device_id: Device ID (optional, used when device doesn't exist)
            
        Returns:
            str: Formatted device key (e.g., 'drv_socketcan::vcan0')
        """
        if device and hasattr(device, 'device_id'):
            key = f"{driver_name}::{device.device_id}"
        else:
            key = f"{driver_name}::{device_id}"
        return key

    def _parse_device_key(self, device_key: str) -> tuple[str, str]:
        """Parse device key
        
        Args:
            device_key: Device key (e.g., 'drv_socketcan::vcan0')
            
        Returns:
            tuple[str, str]: (driver_name, device_id)
        """
        try:
            driver_name, device_id = device_key.split("::", 1)
            return driver_name, device_id
        except ValueError:
            logger.error(f"Invalid device key format: {device_key}")
            return "", ""

    def _handle_scan(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """Handle scan operation"""
        try:
            devices = driver.scan()
            for device in devices:
                device_key = self._get_device_key(driver_name, device)
                self._update_device_state(device_key, DeviceState.DISCOVERED)
            return {
                "status": "success",
                "devices": devices
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_initialize(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """Handle initialization operation"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}

            success = driver.initialize(device)
            device_key = self._get_device_key(driver_name, device)
            if success:
                self._update_device_state(device_key, DeviceState.INITIALIZED)
                return {
                    "status": "success",
                    "message": "Device initialized"
                }
            return {
                "status": "error",
                "message": "Initialization failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_connect(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """Handle connection operation"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}

            success = driver.connect(device)
            device_key = self._get_device_key(driver_name, device)
            if success:
                self._update_device_state(device_key, DeviceState.CONNECTED)
                return {
                    "status": "success",
                    "message": "Device connected"
                }
            return {
                "status": "error",
                "message": "Connection failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_command(self, driver: BaseDeviceDriver, driver_name: str, device_key: str, **kwargs) -> Dict:
        """Handle command execution"""
        try:
            command = kwargs.get('command')
            args = kwargs.get('args', {})
            device_id = kwargs.get('device_id')
            
            if not command:
                return {"status": "error", "message": "Command not specified"}

            # Get device instance
            device = driver.get_device(device_id)
            if not device:
                return {"status": "error", "message": f"Device {device_id} not found"}

            # Move to ACTIVE
            self._update_device_state(device_key, DeviceState.ACTIVE)

            try:
                # Execute command using device instance
                result = driver.command(device, command, args)

                # Transition back to CONNECTED
                self._update_device_state(device_key, DeviceState.CONNECTED)

                return {
                    "status": "success",
                    "result": result
                }
            except Exception as cmd_error:
                # On command execution failure, still return to CONNECTED state, not ERROR
                self._update_device_state(device_key, DeviceState.CONNECTED)
                raise cmd_error

        except Exception as e:
            # Only set ERROR state when there's an issue with the device itself
            if isinstance(e, (IOError, ConnectionError)):
                self._update_device_state(device_key, DeviceState.ERROR)
            return {"status": "error", "message": str(e)}

    def _handle_reset(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """Handle reset operation"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}
            
            success = driver.reset(device)
            return {
                "status": "success" if success else "error",
                "message": "Device reset" if success else "Reset failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_close(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """Handle close operation"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}
            
            success = driver.close(device)
            return {
                "status": "success" if success else "error",
                "message": "Device closed" if success else "Close failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_driver_instance(self, plugin_name: str) -> Optional[BaseDeviceDriver]:
        """Get driver instance"""
        return self.drivers.get(plugin_name)

    def list_drivers(self) -> List[str]:
        """Get list of all loaded drivers
        
        Returns:
            List[str]: List of driver names
        """
        return list(self.drivers.keys())

    def cleanup_all_devices(self) -> Dict:
        """Clean up all device connections and reset states"""
        logger.info("Starting device cleanup")
        
        results = {}
        for device_key in list(self.device_states.keys()):
            logger.info(f"Closing device: {device_key}")
            try:
                driver_name, device_id = self._parse_device_key(device_key)
                if not driver_name:
                    continue
                    
                driver = self.get_driver_instance(driver_name)
                if not driver:
                    logger.warning(f"Driver {driver_name} not found")
                    continue
                
                device = driver.get_device(device_id)
                if device:
                    result = self._manage_device_lifecycle(
                        driver_name=driver_name,
                        action='close',
                        device=device
                    )
                    results[driver_name] = result
                else:
                    logger.warning(f"Device not found for ID: {device_id}")
                    
            except Exception as e:
                logger.error(f"Error closing device {device_key}: {str(e)}")
                results[driver_name if 'driver_name' in locals() else device_key] = {
                    "status": "error",
                    "message": str(e)
                }

        # Reset all internal state
        self.device_states.clear()
        self._connection_locks.clear()
        
        # Reset all drivers
        for driver_name, driver in self.drivers.items():
            try:
                if hasattr(driver, 'reset'):
                    driver.reset()
            except Exception as e:
                logger.warning(f"Failed to reset driver {driver_name}: {e}")

        return results

    def initialize_all_devices(self) -> Dict:
        """Initialize and connect all available devices"""
        logger.info("Starting device initialization")
        
        # Reset internal state
        self.device_states.clear()
        self._connection_locks.clear()
        
        # Get all available drivers
        available_drivers = list(self.drivers.keys())
        if not available_drivers:
            return {
                "status": "warning",
                "message": "No device drivers available!"
            }

        results = {}
        for driver_name in available_drivers:
            try:
                logger.info(f"Initializing {driver_name}...")
                
                # Scan devices using _manage_device_lifecycle
                scan_result = self._manage_device_lifecycle(
                    driver_name=driver_name,
                    action='scan'
                )
                
                if scan_result['status'] != 'success':
                    results[driver_name] = {
                        "status": "error",
                        "message": f"Failed to scan: {scan_result.get('message', 'Unknown error')}"
                    }
                    continue
                
                devices = scan_result.get('devices', [])
                if not devices:
                    results[driver_name] = {
                        "status": "warning",
                        "message": "No devices found"
                    }
                    continue

                # Process each device
                device_results = []
                for device in devices:
                    try:
                        # Initialize device using _manage_device_lifecycle
                        init_result = self._manage_device_lifecycle(
                            driver_name=driver_name,
                            action='initialize',
                            device=device
                        )
                        if init_result['status'] != 'success':
                            device_results.append({
                                "device": device.name,
                                "status": "error",
                                "message": f"Init failed: {init_result['message']}"
                            })
                            continue

                        # Connect device using _manage_device_lifecycle
                        connect_result = self._manage_device_lifecycle(
                            driver_name=driver_name,
                            action='connect',
                            device=device
                        )
                        if connect_result['status'] != 'success':
                            device_results.append({
                                "device": device.name,
                                "status": "error",
                                "message": f"Connect failed: {connect_result['message']}"
                            })
                            continue

                        device_results.append({
                            "device": device.name,
                            "status": "success",
                            "message": "Successfully connected"
                        })

                    except Exception as e:
                        device_results.append({
                            "device": getattr(device, 'name', 'Unknown'),
                            "status": "error",
                            "message": str(e)
                        })

                results[driver_name] = {
                    "status": "success",
                    "devices": device_results
                }

            except Exception as e:
                results[driver_name] = {
                    "status": "error",
                    "message": str(e)
                }

        return results

