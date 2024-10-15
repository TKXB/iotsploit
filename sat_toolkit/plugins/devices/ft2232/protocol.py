import logging
from pyftdi.ftdi import Ftdi, FtdiError
from pyftdi.serialext import serial_for_url
from pyftdi.spi import SpiController
from pyftdi.jtag import JtagController

logger = logging.getLogger(__name__)

# UART functions
def uart_open(url, baudrate=115200):
    return serial_for_url(url, baudrate=baudrate)

def uart_close(port):
    port.close()

def uart_read(port, size):
    return port.read(size)

def uart_write(port, data):
    return port.write(data)

# SPI functions
def spi_open(url, frequency=1000000):
    controller = SpiController()
    controller.configure(url)
    return controller.get_port(cs=0, freq=frequency, mode=0)

def spi_close(port):
    port._controller.terminate()

def spi_exchange(port, data, readlen=0):
    return port.exchange(data, readlen)

# JTAG functions
def jtag_open(url, frequency=1000000):
    controller = JtagController()
    controller.configure(url, frequency=frequency)
    return controller

def jtag_close(controller):
    controller.terminate()

def jtag_write_tms(controller, tms, should_read=False):
    return controller.write_tms(tms, should_read)

def jtag_write_tdi(controller, data, should_read=False):
    return controller.write(data, should_read)

# Generic read and write functions
def ftdi_read(ftdi_device: Ftdi, size: int) -> bytes:
    """
    Read data from the FTDI device.

    Args:
        ftdi_device (Ftdi): The FTDI device object.
        size (int): The number of bytes to read.

    Returns:
        bytes: The data read from the device.

    Raises:
        FtdiError: If there's an error reading from the device.
    """
    try:
        data = ftdi_device.read_data(size)
        if len(data) < size:
            logger.warning(f"Read {len(data)} bytes, expected {size} bytes.")
        return data
    except FtdiError as e:
        logger.error(f"USB data read failed: {str(e)}")
        raise

def ftdi_write(ftdi_device: Ftdi, data: bytes) -> int:
    """
    Write data to the FTDI device.

    Args:
        ftdi_device (Ftdi): The FTDI device object.
        data (bytes): The data to write to the device.

    Returns:
        int: The number of bytes written.

    Raises:
        FtdiError: If there's an error writing to the device.
    """
    try:
        written = ftdi_device.write_data(data)
        if written != len(data):
            logger.warning(f"USB data write length mismatch. Wrote {written} bytes, expected {len(data)} bytes.")
        return written
    except FtdiError as e:
        logger.error(f"USB data write failed: {str(e)}")
        raise

# Function to create the appropriate interface based on the mode
def create_ft2232_interface(mode, url):
    if mode == 'uart':
        return uart_open(url)
    elif mode == 'spi':
        return spi_open(url)
    elif mode == 'jtag':
        return jtag_open(url)
    else:
        raise ValueError(f"Invalid mode: {mode}. Choose 'uart', 'spi', or 'jtag'.")

# Function to close the interface based on the mode
def close_ft2232_interface(mode, interface):
    if mode == 'uart':
        uart_close(interface)
    elif mode == 'spi':
        spi_close(interface)
    elif mode == 'jtag':
        jtag_close(interface)
    else:
        raise ValueError(f"Invalid mode: {mode}. Choose 'uart', 'spi', or 'jtag'.")

# Example usage
if __name__ == "__main__":
    # Replace with your actual device URL
    device_url = 'ftdi://ftdi:2232h/1'

    # UART example
    uart_port = create_ft2232_interface('uart', device_url)
    try:
        uart_write(uart_port, b'Hello, UART!')
        response = uart_read(uart_port, 20)
        print(f"UART response: {response}")
    finally:
        close_ft2232_interface('uart', uart_port)

    # SPI example
    spi_port = create_ft2232_interface('spi', device_url)
    try:
        response = spi_exchange(spi_port, [0x12, 0x34, 0x56], readlen=3)
        print(f"SPI response: {response}")
    finally:
        close_ft2232_interface('spi', spi_port)

    # JTAG example
    # jtag_controller = create_ft2232_interface('jtag', device_url)
    # try:
    #     jtag_write_tms(jtag_controller, b'\x01\x01\x01')  # Example TMS sequence
    #     response = jtag_write_tdi(jtag_controller, b'\x12\x34\x56', should_read=True)
    #     print(f"JTAG response: {response}")
    # finally:
    #     close_ft2232_interface('jtag', jtag_controller)
