# Logic Analyzer Protocol Implementation
# Contains shared code for the Enxor Logic Analyzer

import os
import sys
import time
import json
import serial
import threading
from threading import Thread
import serial.tools.list_ports

from sat_toolkit.tools.xlogger import xlog as logger

# Constants from original logic analyzer
TRIGGER_DELAY_ENABLE_HEADER = b'\xF7'
TRIGGER_DELAY_HEADER = b'\xF8'
SCALER_HEADER = b'\xFA'
CHANNEL_HEADER = b'\xFB'
TRIG_TYPE_HEADER = b'\xFC'
ENABLE_HEADER = b'\xFD'
STOP_HEADER = b'\xFF'
PRECAP_SIZE = b'\xFE'
PRE_BUFFER_HEADER = b'\xA1'
POST_BUFFER_HEADER = b'\xA3'
START_READ_HEADER = b'\xF9'
TRIGGERED_STATE_HEADER = b'\xA7'
DONE_HEADER = b'\xAF'
TRIGGER_RISING_EDGE = 1
TRIGGER_FALLING_EDGE = 0
MAX_TIMER_COUNT = 255

class LogicAnalyzerModel:
    """Logic Analyzer model that stores analyzer configuration and data"""
    def __init__(self):
        self.port = ''
        self.baud = 115200
        self.scaler = 1
        self.channel = 0
        self.trigger_type = TRIGGER_RISING_EDGE
        self.trigger_delay_enabled = 0
        self.trigger_delay = 0
        self.mem_depth = 0
        self.precap_size = 4
        self.pre_trigger_byte_count = 0
        self.post_trigger_byte_count = 0
        self.total_time_units = 0
        self.channel_data = []
        self.compressed_data = []
        self.timestamps = []
        self.x_axis = []
        self.num_channels = 0
        self.bytes_per_row = 0
        self.clk_freq = 1

    # Helper methods for time calculations
    def get_max_capture_time(self, divisor):
        return (MAX_TIMER_COUNT*self.mem_depth) / (self.clk_freq/divisor)

    def get_min_capture_time(self, divisor):
        return (self.mem_depth) / (self.clk_freq/divisor)

    def get_samples_interval_in_seconds(self, divisor):
        return 1 / (self.clk_freq / divisor)

    # Configuration methods
    def initialize_from_config_file(self, file_path):
        with open(file_path, 'r') as config_file:
            obj = json.loads(config_file.read())

            # if config file does not have a field, keep it the same
            self.baud = obj.get('baud_rate', self.baud)
            self.port = obj.get('port_name', self.port)
            self.precap_size = obj.get('precap_size', self.precap_size)
            self.scaler = obj.get('sample_rate', self.scaler)
            self.channel = obj.get('trig_channel', self.channel)
            self.trigger_type = obj.get('trig_type', self.trigger_type)
            # these fields are required
            try:
                self.mem_depth = obj['mem_depth']
                self.clk_freq = obj['clk_freq']
                self.num_channels = obj['num_channels']
                self.bytes_per_row = (self.num_channels // 8) + 2
            except Exception:
                return False

            return True

    def save_to_config_file(self, file_path):
        with open(file_path, 'w') as config_file:
            text = {
                "baud_rate": self.baud,
                "port_name": self.port,
                "clk_freq": self.clk_freq,
                "mem_depth": self.mem_depth,
                "precap_size": self.precap_size,
                "sample_rate": self.scaler,
                "trig_channel": self.channel,
                "trig_type": self.trigger_type,
                "num_channels": self.num_channels
            }
            json.dump(text, config_file)

    # Convert to JSON for API
    def to_json(self):
        """Convert logic analyzer data to JSON for API"""
        return {
            "port": self.port,
            "baud": self.baud,
            "scaler": self.scaler,
            "channel": self.channel,
            "trigger_type": self.trigger_type,
            "mem_depth": self.mem_depth,
            "num_channels": self.num_channels,
            "pre_trigger_count": self.pre_trigger_byte_count,
            "post_trigger_count": self.post_trigger_byte_count,
            "total_time_units": self.total_time_units,
            "timestamps": self.x_axis,
            "channel_data": self.channel_data,
            "trigger_point": self.x_axis[self.pre_trigger_byte_count-1] if self.pre_trigger_byte_count > 0 and self.x_axis else 0
        }

# File I/O functions
def write_logic_analyzer_data_to_file(file_path, la):
    with open(file_path, 'w') as capture_file:
        capture = {
            'clk-freq': la.clk_freq,
            'mem-depth': la.mem_depth,
            'precap-size': la.pre_trigger_byte_count,
            'num-channels': la.num_channels,
            'trig-channel': la.channel,
            'scaler': la.scaler,
            'trig-point': la.x_axis[la.pre_trigger_byte_count-1] if la.pre_trigger_byte_count > 0 and la.x_axis else 0,
            'timestamps': la.x_axis,
            'channel-data': la.compressed_data
        }

        json.dump({'capture': capture}, capture_file)

def read_logic_analyzer_data_from_file(file_path):
    with open(file_path, 'r') as capture_file:
        capture = json.loads(capture_file.read())['capture']
        la = LogicAnalyzerModel()
        la.clk_freq = capture.get('clk-freq')
        la.mem_depth = capture.get('mem-depth')
        la.pre_trigger_byte_count = capture.get('precap-size')
        la.num_channels = capture.get('num-channels')
        la.channel = capture.get('trig-channel')
        la.scaler = capture.get('scaler')
        la.x_axis = capture.get('timestamps')
        la.total_time_units = la.x_axis[-1] if la.x_axis else 0
        la.compressed_data = capture.get('channel-data')

        for _ in range(la.num_channels):
            la.channel_data.append([])
        
        for data in la.compressed_data:
            for bit in range(la.num_channels):
                # separate the byte into each individual channel
                la.channel_data[bit].append((data >> bit) & 1)

        return la

def read_input_stream(byte_arr, las):
    las.channel_data = []
    las.x_axis = []
    las.timestamps = []
    las.post_trigger_byte_count = 0
    las.pre_trigger_byte_count = 0
    las.total_time_units = 0
    las.compressed_data = []

    for _ in range(las.num_channels):
        las.channel_data.append([])

    entry_num = 0
    while entry_num < len(byte_arr) - 2:
        byte_header = byte_arr[entry_num]
        entry_num += 1

        if not byte_header:
            break
        elif byte_header == ord(PRE_BUFFER_HEADER):
            las.pre_trigger_byte_count += 1
        elif byte_header == ord(POST_BUFFER_HEADER):
            las.post_trigger_byte_count += 1
        else:
            # This will realign the bytes to get correct offset
            continue

        # Get data byte
        data_byte = 0
        for offset in range(0, las.num_channels, 8):
            current_byte = byte_arr[entry_num]
            entry_num += 1
            data_byte = current_byte

            for bit in range(8):
                if bit+offset < las.num_channels:
                    las.channel_data[bit+offset].append((data_byte >> bit) & 1)
        
        # Save compressed data for file saving
        las.compressed_data.append(data_byte)

        # Get timestamp
        timestamp = byte_arr[entry_num]
        entry_num += 1
        las.timestamps.append(timestamp)
        las.total_time_units += timestamp
        las.x_axis.append(las.total_time_units)

    logger.info(f'Precaptured bytes - {las.pre_trigger_byte_count}')
    logger.info(f'Postcaptured bytes - {las.post_trigger_byte_count}')
    return las

# Serial communication helpers
def get_available_serial_ports():
    ports = serial.tools.list_ports.comports(include_links=False)
    port_names = []
    for port in ports:
        port_names.append(port.device)

    return port_names

def configure_logic_analyzer(las):
    try:
        ser = serial.Serial(port=las.port, baudrate=las.baud, timeout=None, xonxoff=False)
        ser.reset_input_buffer()
        ser.open
        # set scaler
        # MSB
        ser.write(SCALER_HEADER)
        scaler = las.scaler - 1
        ser.write(bytes([(scaler>>8) & 0xFF]))
        # LSB
        ser.write(SCALER_HEADER)
        ser.write(bytes([(scaler) & 0xFF]))
        # set precapture memory size
        # MSB
        ser.write(PRECAP_SIZE)
        ser.write(bytes([(las.precap_size>>8) & 0xFF]))
        # LSB
        ser.write(PRECAP_SIZE)
        ser.write(bytes([(las.precap_size) & 0xFF]))
        # set channel
        ser.write(CHANNEL_HEADER)
        ser.write(bytes([las.channel]))
        # trigger type
        ser.write(TRIG_TYPE_HEADER)
        ser.write(bytes([las.trigger_type]))
        # set trigger delay enable
        ser.write(TRIGGER_DELAY_ENABLE_HEADER)
        ser.write(bytes([las.trigger_delay_enabled]))
        # trigger delay time
        ser.write(TRIGGER_DELAY_HEADER)
        ser.write(bytes([las.trigger_delay]))
        # ensure enable is off to start to reset the logic
        ser.write(ENABLE_HEADER)
        ser.write(b'\x00')
        # ensure start read is off
        ser.write(START_READ_HEADER)
        ser.write(b'\x00')

        ser.close()
        return True
    except Exception as e:
        logger.error(f"Error configuring logic analyzer: {str(e)}")
        return False

class AsyncReadSerial(Thread):
    def __init__(self, las):
        super().__init__()

        self.las = las
        self.kill = False
        self.full = False
        self.triggered = False
        self.start_read = False
        self.total_bytes = 0
        self.status = "WAITING"  # Status string for UI
        self.buffer = []  # Buffer to store partial data for incremental processing

    def run(self):
        self.status = "RUNNING"
        # Run the serial reading in a more incremental fashion
        self.read_data_incrementally()

    def read_data_incrementally(self):
        """Read and process data incrementally as it becomes available"""
        try:
            ser = serial.Serial(port=self.las.port, baudrate=self.las.baud, timeout=None, xonxoff=False)
            ser.reset_input_buffer()
            ser.open

            # Start capture
            ser.write(ENABLE_HEADER)
            ser.write(b'\x01')
            logger.info(f"Started capture on {self.las.port} with settings: chan={self.las.channel}, trig={self.las.trigger_type}, rate={self.las.scaler}")

            # Monitor for trigger
            last_check = time.time()
            timeout_seconds = 20  # Maximum time to wait for trigger
            start_time = time.time()

            while (not self.full and not self.triggered) and not self.kill and (time.time() - start_time < timeout_seconds):
                # Check for available bytes
                bytesToRead = ser.inWaiting()

                if bytesToRead >= 2:
                    logger.info("TRIGGERED & DONE at once")
                    self.full = True
                    self.triggered = True
                    ser.read(bytesToRead)  # Read and discard these bytes
                    break

                elif bytesToRead == 1:
                    b = ser.read(bytesToRead)

                    if b == TRIGGERED_STATE_HEADER:
                        logger.info("TRIGGERED - starting data collection")
                        self.triggered = True
                        self.status = "TRIGGERED"
                        # Immediately start reading data after trigger
                        self.start_read = True
                        ser.write(START_READ_HEADER)
                        ser.write(b'\x01')
                        break
                    elif b == DONE_HEADER:
                        logger.info("DONE received before trigger")
                        self.full = True
                        break
                    else:
                        logger.error(f"ERROR -- RECEIVED UNEXPECTED BYTE: {b}")
                        # Don't break - let's keep trying

                # Add small sleep to avoid tight loop
                if time.time() - last_check > 0.5:
                    last_check = time.time()
                    logger.debug(f"Waiting for trigger... {int(time.time() - start_time)}s elapsed")

                time.sleep(0.01)

            # Handle case where we got killed before trigger
            if self.kill:
                logger.info("STOPPING - capture killed")
                self.status = "STOPPED"
                ser.write(STOP_HEADER)
                ser.write(b'\x01')
                ser.write(STOP_HEADER)
                ser.write(b'\x00')
                ser.close()
                return

            # Handle timeout without trigger
            if not self.triggered and time.time() - start_time >= timeout_seconds:
                logger.warning("Timeout waiting for trigger")
                self.status = "TIMEOUT"
                ser.write(ENABLE_HEADER)
                ser.write(b'\x00')
                ser.close()
                return

            # If we didn't get a trigger, don't proceed with reading
            if not self.triggered:
                logger.warning("No trigger detected")
                ser.write(ENABLE_HEADER)
                ser.write(b'\x00')
                ser.close()
                return

            # Read data in chunks
            self.status = "READING"
            logger.info("Reading data from device...")
            
            # Calculate read timeout
            max_time = ((1 / self.las.baud) * self.las.mem_depth * self.las.bytes_per_row * 10) + 5.0
            timeout = time.time() + max_time
            expected_bytes = self.las.mem_depth * self.las.bytes_per_row
            
            # Read data in chunks, incrementally processing
            byte_chunks = []
            prev_chunk_time = time.time()
            
            while time.time() < timeout and not self.kill:
                bytesToRead = ser.inWaiting()
                
                if bytesToRead > 0:
                    chunk = ser.read(bytesToRead)
                    byte_chunks.append(chunk)
                    self.total_bytes += len(chunk)
                    logger.debug(f"Read {len(chunk)} bytes, total: {self.total_bytes}/{expected_bytes} ({int((self.total_bytes/expected_bytes)*100)}%)")
                    
                    # Process incremental data if we have enough
                    if time.time() - prev_chunk_time > 0.5 and len(byte_chunks) > 0:
                        # Combine chunks received so far
                        self.process_partial_data(byte_chunks)
                        prev_chunk_time = time.time()
                    
                    # Break if we've read all expected data
                    if self.total_bytes >= expected_bytes:
                        logger.info(f"All expected data received: {self.total_bytes} bytes")
                        break
                
                # Short sleep to avoid CPU spinning
                time.sleep(0.01)
            
            # Finish the capture
            ser.write(START_READ_HEADER)
            ser.write(b'\x00')
            ser.write(ENABLE_HEADER)
            ser.write(b'\x00')
            ser.close()
            
            # Final data processing if we have data
            if self.total_bytes > 0:
                combined_data = self.convert_byte_lists(byte_chunks)
                read_input_stream(combined_data, self.las)
                self.status = "COMPLETED"
                logger.info(f"Data processing complete: {len(self.las.channel_data)} channels with {len(self.las.channel_data[0]) if self.las.channel_data and len(self.las.channel_data) > 0 else 0} samples")
            else:
                self.status = "FAILED"
                logger.error("No data received from device")
            
        except Exception as e:
            logger.error(f"Error in serial communication: {str(e)}")
            self.status = "ERROR"
            import traceback
            logger.error(traceback.format_exc())

    def process_partial_data(self, byte_chunks):
        """Process partial data as it's being received"""
        try:
            # Only process if we have enough data to be meaningful
            if self.total_bytes < 10:
                return
                
            # Convert all chunks collected so far
            partial_data = self.convert_byte_lists(byte_chunks)
            
            # Create a temporary copy of the logic analyzer model
            temp_las = LogicAnalyzerModel()
            temp_las.port = self.las.port
            temp_las.baud = self.las.baud
            temp_las.channel = self.las.channel
            temp_las.trigger_type = self.las.trigger_type
            temp_las.mem_depth = self.las.mem_depth
            temp_las.num_channels = self.las.num_channels
            temp_las.bytes_per_row = self.las.bytes_per_row
            
            # Try to process partial data
            read_input_stream(partial_data, temp_las)
            
            # If we have valid channel data, update the main logic analyzer object
            if temp_las.channel_data and len(temp_las.channel_data) > 0 and len(temp_las.channel_data[0]) > 0:
                self.las.channel_data = temp_las.channel_data
                self.las.compressed_data = temp_las.compressed_data
                self.las.x_axis = temp_las.x_axis
                self.las.timestamps = temp_las.timestamps
                self.las.total_time_units = temp_las.total_time_units
                self.las.pre_trigger_byte_count = temp_las.pre_trigger_byte_count
                self.las.post_trigger_byte_count = temp_las.post_trigger_byte_count
                logger.debug(f"Processed partial data: {len(self.las.channel_data[0])} samples")
            
        except Exception as e:
            logger.error(f"Error processing partial data: {str(e)}")
            # This is just a warning - we'll try again with more data

    def convert_byte_lists(self, byte_chunks):
        if not byte_chunks:
            return b''
            
        combined = byte_chunks[0]
        for x in range(1, len(byte_chunks)):
            combined += byte_chunks[x]

        return combined

def convert_sec_to_relevant_time(seconds):
    """Convert seconds to appropriate time unit format"""
    units = 0
    # last item is 's' to account for seconds == 0
    unit_names = ['s', 'ms', 'us', 'ns', 'ps', 's']

    while int(seconds) == 0 and units < (len(unit_names) - 1):
        seconds *= 1000
        units += 1

    return '{:.2f} '.format(seconds) + unit_names[units]
