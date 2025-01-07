import threading
import logging
import pluggy
from typing import Dict, Any, List, Optional
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamWrapper
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.device_spec import DeviceState

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("device_mgr")

class BasePlugin:
    def __init__(self, info: Dict[str, Any] = None):
        self.info = info or {}

    def update_info(self, new_info: Dict[str, Any]):
        self.info.update(new_info)

    def get_info(self) -> Dict[str, Any]:
        return self.info

class BaseDeviceDriver(BasePlugin):
    """Base class for device drivers implementing the DevicePluginSpec interface"""
    
    def __init__(self, info: Dict[str, Any] = None):
        super().__init__(info)
        # State management
        self.state = DeviceState.UNKNOWN
        self._state_lock = threading.Lock()
        
        # Device management
        self.device = None
        self.device_interface = None
        
        # 确保 supported_commands 总是存在
        if not hasattr(self, 'supported_commands'):
            self.supported_commands = {}  # format: {'command': 'description'}
        
        # Stream management
        self.stream_manager = StreamManager()
        self.stream_wrapper = StreamWrapper(self.stream_manager)
        
        # Thread management
        self.receiver_thread = None
        self.running = threading.Event()

    def _set_state(self, new_state: DeviceState):
        """Thread-safe state transition"""
        with self._state_lock:
            old_state = self.state
            self.state = new_state
            logger.debug(f"Device state changed: {old_state.value} -> {new_state.value}")

    def _validate_state(self, expected_states: List[DeviceState], operation: str):
        """Validate current state against expected states"""
        if self.state not in expected_states:
            raise RuntimeError(
                f"Cannot perform {operation} in current state {self.state.value}. "
                f"Expected states: {[s.value for s in expected_states]}"
            )

    def get_state(self) -> DeviceState:
        """Get current device state"""
        with self._state_lock:
            return self.state

    def is_connected(self) -> bool:
        """Check if device is in CONNECTED state"""
        return self.state == DeviceState.CONNECTED

    def get_supported_commands(self) -> Dict[str, str]:
        """Get dictionary of supported commands and their descriptions"""
        # 如果子类没有定义 supported_commands，返回空字典
        if not hasattr(self, 'supported_commands'):
            return {}
        return self.supported_commands

    # Base implementations of device lifecycle methods
    @hookimpl
    def scan(self) -> List[Device]:
        """Scan for available devices with state management"""
        self._set_state(DeviceState.UNKNOWN)
        try:
            devices = self._scan_impl()
            if devices:
                self._set_state(DeviceState.DISCOVERED)
            return devices
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Scan failed: {str(e)}")
            raise

    @hookimpl
    def initialize(self, device: Device) -> bool:
        """Initialize device with state management"""
        self._validate_state(
            [DeviceState.DISCOVERED, DeviceState.DISCONNECTED], 
            "initialize"
        )
        try:
            success = self._initialize_impl(device)
            if success:
                self._set_state(DeviceState.INITIALIZED)
            return success
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Initialization failed: {str(e)}")
            raise

    @hookimpl
    def connect(self, device: Device) -> bool:
        """Connect to device with state management"""
        self._validate_state([DeviceState.INITIALIZED], "connect")
        try:
            success = self._connect_impl(device)
            if success:
                self._set_state(DeviceState.CONNECTED)
            return success
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Connection failed: {str(e)}")
            raise

    @hookimpl
    def command(self, device: Device, command: str) -> Optional[str]:
        """Execute command with state management"""
        self._validate_state([DeviceState.CONNECTED], "command")
        try:
            self._set_state(DeviceState.ACTIVE)
            result = self._command_impl(device, command)
            self._set_state(DeviceState.CONNECTED)
            return result
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Command execution failed: {str(e)}")
            raise

    @hookimpl
    def reset(self, device: Device) -> bool:
        """Reset device with state management"""
        try:
            success = self._reset_impl(device)
            if success:
                self._set_state(DeviceState.INITIALIZED)
            return success
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Reset failed: {str(e)}")
            raise

    @hookimpl
    def close(self, device: Device) -> bool:
        """Close device with state management"""
        if self.state == DeviceState.UNKNOWN:
            return True
            
        try:
            success = self._close_impl(device)
            if success:
                self._set_state(DeviceState.DISCONNECTED)
            return success
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            logger.error(f"Close failed: {str(e)}")
            raise

    # Methods to be implemented by derived classes
    def _scan_impl(self) -> List[Device]:
        """Implementation of device scanning"""
        raise NotImplementedError

    def _initialize_impl(self, device: Device) -> bool:
        """Implementation of device initialization"""
        raise NotImplementedError

    def _connect_impl(self, device: Device) -> bool:
        """Implementation of device connection"""
        raise NotImplementedError

    def _command_impl(self, device: Device, command: str) -> Optional[str]:
        """Implementation of command execution"""
        raise NotImplementedError

    def _reset_impl(self, device: Device) -> bool:
        """Implementation of device reset"""
        raise NotImplementedError

    def _close_impl(self, device: Device) -> bool:
        """Implementation of device closure"""
        raise NotImplementedError

    # Thread management methods
    def start_receiver(self):
        """Helper method to start the receiver thread"""
        if not self.running.is_set() and not (self.receiver_thread and self.receiver_thread.is_alive()):
            self.running.set()
            self.receiver_thread = threading.Thread(
                target=self.receiver_thread_fn,
                name=f'{self.__class__.__name__}_RECEIVER'
            )
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            logger.info("Started message monitoring")

    def stop_receiver(self):
        """Helper method to stop the receiver thread"""
        self.running.clear()
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=1.0)
            self.receiver_thread = None
        logger.info("Stopped message monitoring")

    def receiver_thread_fn(self):
        """Override this method in derived classes"""
        raise NotImplementedError

    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            if self.device and self.state != DeviceState.DISCONNECTED:
                self.close(self.device)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")