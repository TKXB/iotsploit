# File: plugins/devices/logic/drv_logic.py

import os
import sys
import time
import json
import serial
import threading
from threading import Thread
import serial.tools.list_ports

from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.models.Device_Model import Device
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
            if self.logic_analyzer.port not in available_ports:
                logger.error(f"Port {self.logic_analyzer.port} not available. Available ports: {available_ports}")
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
                device = Device(
                    device_id=f"enxor_la_{port.replace('/', '_')}",
                    name=f"Enxor Logic Analyzer ({port})",
                    device_type="Serial",
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
    
    def _acquisition_loop(self):
        """Implementation of data acquisition loop"""
        logger.info("Starting acquisition loop")
        
        # Start the actual capture if not already running
        if not self.is_capturing:
            self.start_capture()
        
        while self.is_acquiring.is_set():
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
                
                # If capture completed, broadcast data
                if status.get("status") == "completed" and self.logic_analyzer:
                    data = self.get_capture_data()
                    if data.get("status") == "success":
                        stream_data = StreamData(
                            stream_type=StreamType.CUSTOM,
                            channel=self.device.device_id,
                            timestamp=time.time(),
                            source=StreamSource.SERVER,
                            action=StreamAction.DATA,
                            data={"type": "data", "data": data.get("data", {})},
                            metadata={"device_type": "logic_analyzer"}
                        )
                        self.stream_wrapper.broadcast_data(stream_data)
                        # After broadcasting completed data, we can stop acquisition
                        self.is_acquiring.clear()
            
            # Slow down the polling loop
            time.sleep(0.1)
        
        logger.info("Acquisition loop ended")
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
            # Configure the analyzer
            if not configure_logic_analyzer(self.logic_analyzer):
                return {"status": "error", "message": "Failed to configure logic analyzer"}
            
            # Start capture thread
            self.capture_thread = AsyncReadSerial(self.logic_analyzer)
            self.capture_thread.start()
            self.is_capturing = True
            
            return {"status": "success", "message": "Capture started"}
        
        except Exception as e:
            logger.error(f"Error starting capture: {str(e)}")
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
            if self.capture_thread.triggered:
                return {"status": "completed", "message": "Capture completed successfully"}
            else:
                return {"status": "failed", "message": "Capture failed"}
        
        return {
            "status": self.capture_thread.status.lower(),
            "message": f"Capture {self.capture_thread.status.lower()}",
            "bytes_read": self.capture_thread.total_bytes
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