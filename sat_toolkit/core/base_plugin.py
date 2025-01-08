import threading
import logging
from typing import Dict, Any, List, Optional
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamWrapper
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.device_spec import DeviceState

logger = logging.getLogger(__name__)

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

        self._devices: Dict[str, Device] = {}  # 存储设备实例
        
    def get_supported_commands(self) -> Dict[str, str]:
        """Get dictionary of supported commands and their descriptions"""
        if not hasattr(self, 'supported_commands'):
            return {}
        return self.supported_commands

    # Base implementations of device lifecycle methods
    def scan(self) -> List[Device]:
        """Scan for available devices"""
        try:
            devices = self._scan_impl()
            for device in devices:
                self._register_device(device)
            return devices
        except Exception as e:
            logger.error(f"Scan failed: {str(e)}")
            raise

    def initialize(self, device: Device) -> bool:
        """Initialize device"""
        try:
            return self._initialize_impl(device)
        except Exception as e:
            logger.error(f"Initialization failed: {str(e)}")
            raise

    def connect(self, device: Device) -> bool:
        """Connect to device"""
        try:
            return self._connect_impl(device)
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            raise

    def command(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """Execute command"""
        try:
            return self._command_impl(device, command, args)
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            raise

    def reset(self, device: Device) -> bool:
        """Reset device"""
        try:
            return self._reset_impl(device)
        except Exception as e:
            logger.error(f"Reset failed: {str(e)}")
            raise

    def close(self, device: Device) -> bool:
        """Close device"""
        try:
            return self._close_impl(device)
        except Exception as e:
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

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[str]:
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

    def get_device(self, device_id: str) -> Optional[Device]:
        """获取设备实例"""
        return self._devices.get(device_id)

    def _register_device(self, device: Device):
        """注册设备"""
        self._devices[device.device_id] = device