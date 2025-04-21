# File: plugins/devices/logic/drv_logic.py

import os
import sys
import time
import json
import serial
import threading
from threading import Thread
import serial.tools.list_ports
import traceback

from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.models.Device_Model import Device, SerialDevice
from sat_toolkit.tools.xlogger import xlog as logger
from sat_toolkit.core.stream_manager import StreamData, StreamType, StreamSource, StreamAction

# Import components from protocol - using absolute import instead of relative
from plugins.devices.logic.protocol import (
    LogicAnalyzerModel, 
    AsyncReadSerial, 
    get_available_serial_ports, 
    configure_logic_analyzer, 
    read_logic_analyzer_data_from_file,
    write_logic_analyzer_data_to_file,
    read_input_stream,
    convert_sec_to_relevant_time,
    # Constants
    TRIGGER_RISING_EDGE,
    TRIGGER_FALLING_EDGE
)

class EnxorLogicAnalyzerDriver(BaseDeviceDriver):
    """Enxor Logic Analyzer device driver for zeekr_sat_main-master framework"""
    
    def __init__(self):
        super().__init__()
        self.name = "enxor_logic_analyzer"
        self.version = "1.0.0"
        self.logic_analyzer = None
        self.capture_thread = None
        self.is_capturing = False
        self.is_connected = False
        self.config_path = 'conf/logic_analyzer_config.json'
        
        # Default configuration
        self.default_config = {
            "baud_rate": 115200,
            "clk_freq": 48000000,
            "mem_depth": 8192,
            "precap_size": 1024,
            "sample_rate": 238,
            "trig_channel": 0,
            "trig_type": 1,
            "num_channels": 8
        }
        
        # Available commands for this driver
        self.supported_commands = {
            "scan": "Scan for available serial ports",
            "connect": "Connect to the logic analyzer",
            "configure": "Configure the logic analyzer",
            "start": "Start capture",
            "stop": "Stop capture",
            "save": "Save captured data to file",
            "load": "Load captured data from file",
            "status": "Show current status",
            "get_data": "Get captured data for visualization"
        }
    
    def get_info(self):
        """Return plugin information"""
        return {
            "name": self.name,
            "version": self.version,
            "description": "Enxor Logic Analyzer driver for signal analysis",
            "author": "Based on Matthew Crump's work, adapted for zeekr_sat_main",
            "device_type": "Serial",
            "commands": self.supported_commands,
            "Parameters": {
                "port": {"type": "str", "required": True, "description": "Serial port for the logic analyzer"},
                "baud_rate": {"type": "int", "required": False, "default": 115200, "description": "Baud rate"},
                "config_file": {"type": "str", "required": False, "description": "Path to configuration file"}
            }
        }
    
    def _initialize_impl(self, device):
        """Implementation of device initialization"""
        try:
            # Create the logic analyzer model
            self.logic_analyzer = LogicAnalyzerModel()
            
            # Get configuration from device if available
            device_info = device.attributes if hasattr(device, "attributes") else {}
            
            # Try to load from config file if it exists
            config_file = self.config_path
            if device_info and 'config_file' in device_info:
                config_file = device_info['config_file']
            
            if os.path.exists(config_file):
                logger.info(f"Loading configuration from {config_file}")
                result = self.logic_analyzer.initialize_from_config_file(config_file)
                if not result:
                    logger.warning("Failed to load from config file, using defaults")
                    self._initialize_defaults()
            else:
                logger.info("No config file found, using defaults")
                self._initialize_defaults()
            
            # Set port from device_info if provided
            if device_info and 'port' in device_info:
                self.logic_analyzer.port = device_info['port']
            if device_info and 'baud_rate' in device_info:
                self.logic_analyzer.baud = device_info['baud_rate']
            
            logger.info(f"Logic analyzer initialized with port={self.logic_analyzer.port}, "
                        f"baud={self.logic_analyzer.baud}, channels={self.logic_analyzer.num_channels}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize logic analyzer: {str(e)}")
            return False
    
    def _initialize_defaults(self):
        """Initialize logic analyzer with default settings"""
        self.logic_analyzer.baud = self.default_config['baud_rate']
        self.logic_analyzer.clk_freq = self.default_config['clk_freq']
        self.logic_analyzer.mem_depth = self.default_config['mem_depth']
        self.logic_analyzer.precap_size = self.default_config['precap_size']
        self.logic_analyzer.scaler = self.default_config['sample_rate']
        self.logic_analyzer.channel = self.default_config['trig_channel']
        self.logic_analyzer.trigger_type = self.default_config['trig_type']
        self.logic_analyzer.num_channels = self.default_config['num_channels']
        self.logic_analyzer.bytes_per_row = (self.logic_analyzer.num_channels // 8) + 2
    
    def connect(self, device, **kwargs):
        """Compatibility method for direct connection"""
        return self._connect_impl(device)
    
    def _connect_impl(self, device):
        """Implementation of device connection"""
        try:
            if not self.logic_analyzer:
                logger.error("Logic analyzer not initialized")
                return False
            
            # Update port if specified in device
            if hasattr(device, 'attributes') and 'port' in device.attributes:
                self.logic_analyzer.port = device.attributes['port']
            
            # Validate port
            if not self.logic_analyzer.port:
                logger.error("No serial port specified")
                return False
            
            available_ports = get_available_serial_ports()
            logger.info(f"Available ports: {available_ports}")
            
            if self.logic_analyzer.port not in available_ports:
                logger.error(f"Port {self.logic_analyzer.port} not available. Available ports: {available_ports}")
                return False
            
            # Verify serial port is accessible
            try:
                # Test opening the port
                ser = serial.Serial(port=self.logic_analyzer.port, baudrate=self.logic_analyzer.baud, timeout=1)
                ser.close()
                logger.info(f"Successfully tested port {self.logic_analyzer.port}")
            except Exception as e:
                logger.error(f"Error accessing serial port {self.logic_analyzer.port}: {str(e)}")
                return False
            
            # Try to configure the analyzer
            if configure_logic_analyzer(self.logic_analyzer):
                self.is_connected = True
                logger.info(f"Successfully connected to logic analyzer on {self.logic_analyzer.port}")
                return True
            else:
                logger.error(f"Failed to configure logic analyzer on {self.logic_analyzer.port}")
                return False
        
        except Exception as e:
            logger.error(f"Error connecting to logic analyzer: {str(e)}")
            return False
    
    def _close_impl(self, device):
        """Implementation of device closure"""
        try:
            if self.is_capturing:
                self.stop_capture()
            
            self.is_connected = False
            logger.info("Disconnected from logic analyzer")
            return True
        
        except Exception as e:
            logger.error(f"Error disconnecting from logic analyzer: {str(e)}")
            return False
    
    def _scan_impl(self):
        """Implementation of device scanning"""
        try:
            available_ports = get_available_serial_ports()
            devices = []
            
            for port in available_ports:
                # Create SerialDevice which already has DeviceType.Serial set by default
                device = SerialDevice(
                    device_id=f"enxor_la_{port.replace('/', '_')}",
                    name=f"Enxor Logic Analyzer ({port})",
                    port=port,
                    baud_rate=115200,
                    attributes={"port": port, "baud_rate": 115200}
                )
                devices.append(device)
            
            return devices
        
        except Exception as e:
            logger.error(f"Error scanning for devices: {str(e)}")
            return []
    
    def _command_impl(self, device, command, args=None):
        """Implementation of command execution"""
        args = args or {}
        
        try:
            cmd_parts = command.lower().split() if isinstance(command, str) else []
            cmd = cmd_parts[0] if cmd_parts else ""
            
            if cmd == "scan":
                return self.scan_devices()
            
            elif cmd == "connect":
                result = self._connect_impl(device)
                return {"status": "success" if result else "error", 
                        "message": f"Connected to {self.logic_analyzer.port}" if result else "Failed to connect"}
            
            elif cmd == "configure":
                if not self.is_connected:
                    return {"status": "error", "message": "Not connected to logic analyzer"}
                
                # Update configuration based on args
                for key, value in args.items():
                    if key == "port":
                        self.logic_analyzer.port = value
                    elif key == "baud_rate":
                        self.logic_analyzer.baud = int(value)
                    elif key == "trigger_channel":
                        self.logic_analyzer.channel = int(value)
                    elif key == "trigger_type":
                        self.logic_analyzer.trigger_type = int(value)
                    elif key == "sample_rate":
                        self.logic_analyzer.scaler = int(value)
                    elif key == "precap_size":
                        self.logic_analyzer.precap_size = int(value)
                
                # Save to config file if requested
                if args.get("save_config", False):
                    self.logic_analyzer.save_to_config_file(self.config_path)
                
                return {"status": "success", "message": "Configuration updated"}
            
            elif cmd == "start":
                # Use the base class's start_streaming method
                # This will properly register WebSocket streams
                self.start_streaming(device)
                return {"status": "success", "message": "Capture started"}
            
            elif cmd == "stop":
                # Use the base class's stop_streaming method
                # This will properly unregister WebSocket streams
                self.stop_streaming(device)
                return {"status": "success", "message": "Capture stopped"}
            
            elif cmd == "status":
                return self.get_capture_status()
            
            elif cmd == "save":
                file_path = args.get("file_path", "captures/capture.xor")
                return self.save_capture(file_path)
            
            elif cmd == "load":
                file_path = args.get("file_path")
                if not file_path:
                    return {"status": "error", "message": "No file path provided"}
                return self.load_capture(file_path)
            
            elif cmd == "get_data":
                return self.get_capture_data()
            
            else:
                return {"status": "error", "message": f"Unknown command: {command}"}
                
        except Exception as e:
            logger.error(f"Error executing command {command}: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _reset_impl(self, device):
        """Implementation of device reset"""
        try:
            # Stop any capture in progress
            if self.is_capturing:
                self.stop_capture()
            
            # Re-configure the device
            if self.is_connected:
                return configure_logic_analyzer(self.logic_analyzer)
                
            return True
        except Exception as e:
            logger.error(f"Error resetting device: {str(e)}")
            return False
    
    def _broadcast_debug_info(self, message, data=None):
        """Helper method to broadcast debug information via WebSocket"""
        if not self.device or not hasattr(self.device, 'device_id'):
            return
            
        debug_data = {
            "type": "debug",
            "message": message,
            "timestamp": time.time(),
            "data": data or {}
        }
        
        stream_data = StreamData(
            stream_type=StreamType.CUSTOM,
            channel=self.device.device_id,
            timestamp=time.time(),
            source=StreamSource.SERVER,
            action=StreamAction.STATUS,
            data=debug_data,
            metadata={"device_type": "logic_analyzer"}
        )
        
        try:
            self.stream_wrapper.broadcast_data(stream_data)
            logger.debug(f"Broadcast debug info: {message}")
        except Exception as e:
            logger.error(f"Failed to broadcast debug info: {str(e)}")

    def _acquisition_loop(self):
        """Implementation of data acquisition loop"""
        logger.info("Starting acquisition loop")
        
        # Broadcast debug info
        self._broadcast_debug_info("Starting acquisition loop")
        
        # Start the actual capture if not already running
        if not self.is_capturing:
            capture_result = self.start_capture()
            if capture_result.get("status") == "error":
                error_msg = capture_result.get('message', 'Unknown error')
                logger.error(f"Failed to start capture: {error_msg}")
                self._broadcast_debug_info("Failed to start capture", {"error": error_msg})
                self.is_acquiring.clear()
                return
        
        # Broadcast more debug info about the device
        if self.logic_analyzer:
            device_info = {
                "port": self.logic_analyzer.port,
                "baud_rate": self.logic_analyzer.baud,
                "sample_rate": self.logic_analyzer.scaler,
                "mem_depth": self.logic_analyzer.mem_depth,
                "bytes_per_row": self.logic_analyzer.bytes_per_row,
                "num_channels": self.logic_analyzer.num_channels
            }
            self._broadcast_debug_info("Logic analyzer configuration", device_info)
        
        # Keep track of last time we broadcast channel data
        last_data_broadcast = 0
        last_sample_count = 0
        
        while self.is_acquiring.is_set():
            try:
                # If there's a capture thread running, check its status
                if self.capture_thread and self.capture_thread.is_alive():
                    status = self.get_capture_status()
                    
                    # Broadcast status via stream manager
                    if self.device and hasattr(self.device, 'device_id'):
                        stream_data = StreamData(
                            stream_type=StreamType.CUSTOM,
                            channel=self.device.device_id,
                            timestamp=time.time(),
                            source=StreamSource.SERVER,
                            action=StreamAction.STATUS,
                            data={"type": "status", "data": status},
                            metadata={"device_type": "logic_analyzer"}
                        )
                        self.stream_wrapper.broadcast_data(stream_data)
                    
                    # Check if we have partial data to broadcast
                    # Only broadcast every 1 second to avoid flooding, and only if we have new samples
                    if (time.time() - last_data_broadcast > 1.0 and 
                        self.logic_analyzer and 
                        hasattr(self.logic_analyzer, 'channel_data') and 
                        self.logic_analyzer.channel_data):
                        
                        # Get current sample count
                        current_samples = 0
                        if len(self.logic_analyzer.channel_data) > 0:
                            current_samples = len(self.logic_analyzer.channel_data[0])
                        
                        # Only broadcast if we have new data
                        if current_samples > last_sample_count and current_samples > 10:
                            last_sample_count = current_samples
                            
                            # Log partial data info
                            self._broadcast_debug_info(
                                f"Broadcasting partial data with {current_samples} samples", 
                                {"channels": len(self.logic_analyzer.channel_data)}
                            )
                            
                            # Send partial data through WebSocket
                            la_data = self.logic_analyzer.to_json()
                            stream_data = StreamData(
                                stream_type=StreamType.CUSTOM,
                                channel=self.device.device_id,
                                timestamp=time.time(),
                                source=StreamSource.SERVER,
                                action=StreamAction.DATA,
                                data={"type": "data", "data": la_data, "partial": True},
                                metadata={"device_type": "logic_analyzer"}
                            )
                            self.stream_wrapper.broadcast_data(stream_data)
                            last_data_broadcast = time.time()
                    
                    # If capture completed, broadcast final data
                    if status.get("status") == "completed" and self.logic_analyzer:
                        self._broadcast_debug_info("Capture completed, retrieving final data")
                        data = self.get_capture_data()
                        if data.get("status") == "success":
                            # Check if we have actual data
                            la_data = data.get("data", {})
                            channels = la_data.get("channel_data", [])
                            
                            if not channels or len(channels) == 0:
                                self._broadcast_debug_info("No channel data available in completed capture")
                            else:
                                self._broadcast_debug_info(f"Got final channel data: {len(channels)} channels with {len(channels[0])} samples each")
                            
                            stream_data = StreamData(
                                stream_type=StreamType.CUSTOM,
                                channel=self.device.device_id,
                                timestamp=time.time(),
                                source=StreamSource.SERVER,
                                action=StreamAction.DATA,
                                data={"type": "data", "data": la_data, "partial": False},
                                metadata={"device_type": "logic_analyzer"}
                            )
                            self.stream_wrapper.broadcast_data(stream_data)
                            logger.info(f"Broadcast completed capture data for device {self.device.device_id}")
                            # After broadcasting completed data, we can stop acquisition
                            self.is_acquiring.clear()
                        else:
                            self._broadcast_debug_info("Failed to get capture data", 
                                                      {"error": data.get("message", "Unknown error")})
                elif self.capture_thread and not self.capture_thread.is_alive():
                    self._broadcast_debug_info("Capture thread is no longer alive")
                    # If the thread has died unexpectedly, stop acquisition
                    if self.is_capturing:
                        self.is_capturing = False
                        self._broadcast_debug_info("Stopped capturing due to thread death")
            except Exception as e:
                logger.error(f"Error in acquisition loop: {str(e)}")
                self._broadcast_debug_info("Error in acquisition loop", 
                                          {"error": str(e), "traceback": traceback.format_exc()})
            
            # Slow down the polling loop
            time.sleep(0.1)
        
        logger.info("Acquisition loop ended")
        self._broadcast_debug_info("Acquisition loop ended")
        
        # Make sure to stop the capture when acquisition ends
        if self.is_capturing:
            self.stop_capture()
    
    def _setup_acquisition(self, device):
        """Set up acquisition for the given device"""
        logger.info(f"Setting up acquisition for device {device.device_id}")
        self.device = device
        
        # Ensure we're connected before starting capture
        if not self.is_connected:
            self._connect_impl(device)
    
    def _cleanup_acquisition(self, device):
        """Clean up acquisition for the given device"""
        logger.info(f"Cleaning up acquisition for device {device.device_id}")
        
        # Stop the capture if it's running
        if self.is_capturing:
            self.stop_capture()
    
    def start_capture(self):
        """Start capture from the logic analyzer"""
        if self.is_capturing:
            return {"status": "error", "message": "Capture already in progress"}
        
        if not self.is_connected:
            return {"status": "error", "message": "Not connected to logic analyzer"}
        
        try:
            # Check if the logic analyzer has been properly initialized
            if not self.logic_analyzer or not self.logic_analyzer.port:
                return {"status": "error", "message": "Logic analyzer not properly initialized"}
            
            # Verify port is still available
            available_ports = get_available_serial_ports()
            if self.logic_analyzer.port not in available_ports:
                logger.error(f"Port {self.logic_analyzer.port} no longer available")
                return {"status": "error", "message": f"Port {self.logic_analyzer.port} no longer available"}
            
            # Configure the analyzer
            logger.info(f"Configuring logic analyzer on port {self.logic_analyzer.port}...")
            
            if not configure_logic_analyzer(self.logic_analyzer):
                return {"status": "error", "message": "Failed to configure logic analyzer"}
            
            # Create and start capture thread
            logger.info("Starting AsyncReadSerial thread...")
            
            # Verify memory depth and bytes_per_row are set
            if not self.logic_analyzer.mem_depth or not self.logic_analyzer.bytes_per_row:
                logger.error("Memory depth or bytes_per_row not properly set")
                return {"status": "error", "message": "Memory depth or bytes_per_row not properly set"}
            
            self.capture_thread = AsyncReadSerial(self.logic_analyzer)
            self.capture_thread.daemon = True  # Make thread a daemon so it doesn't block shutdown
            self.capture_thread.start()
            self.is_capturing = True
            
            logger.info(f"Started capture on port {self.logic_analyzer.port} with sample rate {self.logic_analyzer.scaler}")
            logger.info(f"Memory depth: {self.logic_analyzer.mem_depth}, Bytes per row: {self.logic_analyzer.bytes_per_row}")
            logger.info(f"Expecting total bytes: {self.logic_analyzer.mem_depth * self.logic_analyzer.bytes_per_row}")
            
            return {"status": "success", "message": "Capture started"}
        
        except Exception as e:
            logger.error(f"Error starting capture: {str(e)}")
            if self.capture_thread:
                try:
                    self.capture_thread.kill = True
                except:
                    pass
            self.is_capturing = False
            return {"status": "error", "message": str(e)}
    
    def stop_capture(self):
        """Stop capture from the logic analyzer"""
        if not self.is_capturing:
            return {"status": "error", "message": "No capture in progress"}
        
        try:
            # Stop the capture thread
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.kill = True
                self.capture_thread.join(timeout=2.0)  # Wait for thread to terminate
            
            self.is_capturing = False
            
            return {"status": "success", "message": "Capture stopped"}
        
        except Exception as e:
            logger.error(f"Error stopping capture: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_capture_status(self):
        """Get status of the current capture"""
        if not self.capture_thread:
            return {"status": "idle", "message": "No capture initialized"}
        
        if not self.is_capturing:
            return {"status": "idle", "message": "No capture in progress"}
        
        if not self.capture_thread.is_alive():
            self.is_capturing = False
            if hasattr(self.capture_thread, 'triggered') and self.capture_thread.triggered:
                return {"status": "completed", "message": "Capture completed successfully", "bytes_read": getattr(self.capture_thread, 'total_bytes', 0)}
            else:
                return {"status": "failed", "message": "Capture failed"}
        
        # Get the status of the capture thread
        status = "waiting"
        if hasattr(self.capture_thread, 'status'):
            status = self.capture_thread.status.lower()
        elif hasattr(self.capture_thread, 'triggered') and self.capture_thread.triggered:
            if hasattr(self.capture_thread, 'start_read') and self.capture_thread.start_read:
                status = "reading"
            else:
                status = "triggered"
        
        bytes_read = getattr(self.capture_thread, 'total_bytes', 0)
        expected_bytes = self.logic_analyzer.mem_depth * self.logic_analyzer.bytes_per_row if self.logic_analyzer else 0
        progress = 0
        if expected_bytes > 0:
            progress = int((bytes_read / expected_bytes) * 100)
            
        return {
            "status": status,
            "message": f"Capture {status}",
            "bytes_read": bytes_read,
            "expected_bytes": expected_bytes,
            "progress": progress
        }
    
    def save_capture(self, file_path):
        """Save capture data to file"""
        if not self.logic_analyzer or self.logic_analyzer.total_time_units == 0:
            return {"status": "error", "message": "No capture data available"}
        
        try:
            write_logic_analyzer_data_to_file(file_path, self.logic_analyzer)
            return {"status": "success", "message": f"Capture saved to {file_path}"}
        
        except Exception as e:
            logger.error(f"Error saving capture: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def load_capture(self, file_path):
        """Load capture data from file"""
        try:
            self.logic_analyzer = read_logic_analyzer_data_from_file(file_path)
            return {"status": "success", "message": f"Capture loaded from {file_path}"}
        
        except Exception as e:
            logger.error(f"Error loading capture: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_capture_data(self):
        """Get current capture data for visualization"""
        if not self.logic_analyzer or not hasattr(self.logic_analyzer, 'channel_data') or not self.logic_analyzer.channel_data:
            return {"status": "error", "message": "No capture data available"}
        
        return {
            "status": "success",
            "data": self.logic_analyzer.to_json()
        }
    
    def scan_devices(self):
        """Convenience method to scan for devices and return formatted results"""
        devices = self._scan_impl()
        if not devices:
            return {"status": "success", "message": "No serial ports found", "devices": []}
        
        return {"status": "success", "devices": devices}