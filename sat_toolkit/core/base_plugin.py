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
        self._devices: Dict[str, Device] = {}
        
        # Stream management
        self.stream_manager = StreamManager()
        self.stream_wrapper = StreamWrapper(self.stream_manager)
        
        # Acquisition management
        self.acquisition_thread = None
        self.is_acquiring = threading.Event()

        # 确保 supported_commands 总是存在
        if not hasattr(self, 'supported_commands'):
            self.supported_commands = {}  # format: {'command': 'description'}

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

    # Streaming and acquisition control
    def start_streaming(self, device: Device):
        """启动设备数据流（包括数据采集和WebSocket分发）"""
        try:
            logger.info(f"Starting streaming for device {device.device_id}")
            self.stream_wrapper.register_stream(device.device_id)
            self.start_acquisition(device)
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.stop_streaming(device)
            raise

    def stop_streaming(self, device: Device):
        """停止设备数据流（包括数据采集和WebSocket分发）"""
        try:
            logger.info(f"Stopping streaming for device {device.device_id}")
            self.stop_acquisition(device)
            self.stream_wrapper.unregister_stream(device.device_id)
            self.stream_wrapper.stop_broadcast(device.device_id)
        except Exception as e:
            logger.error(f"Error stopping streaming: {e}")
            raise

    def start_acquisition(self, device: Device):
        """启动设备数据采集（不包括WebSocket分发）"""
        try:
            logger.info(f"Starting data acquisition for device {device.device_id}")
            self._setup_acquisition(device)
            if not self.is_acquiring.is_set():
                self.is_acquiring.set()
                self.acquisition_thread = threading.Thread(
                    target=self._acquisition_loop,
                    name=f'{self.__class__.__name__}_Acquisition'
                )
                self.acquisition_thread.daemon = True
                self.acquisition_thread.start()
        except Exception as e:
            logger.error(f"Failed to start acquisition: {e}")
            self.stop_acquisition(device)
            raise

    def stop_acquisition(self, device: Device):
        """停止设备数据采集（不包括WebSocket分发）"""
        logger.info(f"Stopping data acquisition for device {device.device_id}")
        self.is_acquiring.clear()
        if self.acquisition_thread and self.acquisition_thread.is_alive():
            self.acquisition_thread.join(timeout=1.0)
            self.acquisition_thread = None
        try:
            self._cleanup_acquisition(device)
        except Exception as e:
            logger.error(f"Error in acquisition cleanup: {e}")
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

    def _setup_acquisition(self, device: Device):
        """设备特定的采集初始化"""
        pass

    def _cleanup_acquisition(self, device: Device):
        """设备特定的采集清理"""
        pass

    def _acquisition_loop(self):
        """数据采集循环的具体实现"""
        raise NotImplementedError

    def get_device(self, device_id: str) -> Optional[Device]:
        """获取设备实例"""
        return self._devices.get(device_id)

    def _register_device(self, device: Device):
        """注册设备"""
        self._devices[device.device_id] = device

    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            if self.device and hasattr(self, 'state') and self.state != DeviceState.DISCONNECTED:
                self.close(self.device)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")