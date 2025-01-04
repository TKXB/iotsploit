import threading
import logging
import pluggy
from typing import Dict, Any, List
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamWrapper
from sat_toolkit.models.Device_Model import Device

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
        self.device_interface = None
        self.supported_commands = {}  # format: {'command': 'description'}
        self.bus = None
        self.receiver_thread = None
        self.running = threading.Event()
        self.current_interface = None
        self.stream_manager = StreamManager()
        self.stream_wrapper = StreamWrapper(self.stream_manager)
        self.device = None
        self.connected = False

    def start_receiver(self):
        """Helper method to start the receiver thread if it's not already running"""
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

    def start_monitoring(self, device):
        """Helper method to start monitoring"""
        self.stop_receiver()
        logger.info("Starting message monitoring")
        channel = device.device_id
        self.stream_wrapper.register_stream(channel)
        self.start_receiver()

    def stop_monitoring(self, device):
        """Helper method to stop monitoring"""
        channel = device.device_id
        self.stream_wrapper.unregister_stream(channel)
        self.stream_wrapper.stop_broadcast(channel)
        self.stop_receiver()
        self.bus = None

    def is_connected(self):
        """Check if device is connected"""
        return self.connected

    def get_supported_commands(self) -> Dict[str, str]:
        """Get dictionary of supported commands and their descriptions"""
        return self.supported_commands

    # Plugin interface methods implementing DevicePluginSpec
    @hookimpl
    def scan(self) -> List[Device]:
        """Scan for available devices.
            
        Returns:
            list[Device]: A list of discovered devices matching the configuration.
        """
        raise NotImplementedError

    @hookimpl
    def initialize(self, device: Device):
        """Initialize the plugin for a specific device."""
        raise NotImplementedError

    @hookimpl
    def connect(self, device: Device):
        """Connect to the device."""
        raise NotImplementedError

    @hookimpl
    def command(self, device: Device, command: str):
        """Send a command to the device."""
        raise NotImplementedError

    @hookimpl
    def reset(self, device: Device):
        """Reset the device to its initial state."""
        raise NotImplementedError

    @hookimpl
    def close(self, device: Device):
        """Close the device."""
        raise NotImplementedError