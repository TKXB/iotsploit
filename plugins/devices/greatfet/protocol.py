import struct
import usb.util
import logging
from sat_toolkit.models.Device_Model import Device, USBDevice

logger = logging.getLogger(__name__)

# Define constants
LIBGREAT_REQUEST_NUMBER = 0x65
LIBGREAT_VALUE_EXECUTE = 0
GREATFET_CLASS_CORE = 0x000
CORE_VERB_READ_VERSION = 0x1
CORE_MAX_STRING_LENGTH = 128
LOGIC_DEFAULT_TIMEOUT = 1000


def get_version_number(device: USBDevice):
    if not device or 'usb_device' not in device.attributes:
        logger.error("USB device object not found. Please provide a valid device.")
        return None

    usb_dev = device.attributes['usb_device']

    try:
        # Prepare the control transfer request
        request_type = usb.util.build_request_type(
            usb.util.CTRL_TYPE_VENDOR,
            usb.util.CTRL_RECIPIENT_ENDPOINT,
            usb.util.CTRL_OUT
        )
        
        # Prepare the request data
        request_data = struct.pack('<II', GREATFET_CLASS_CORE, CORE_VERB_READ_VERSION)
        
        # Send the request
        usb_dev.ctrl_transfer(
            request_type,
            LIBGREAT_REQUEST_NUMBER,
            LIBGREAT_VALUE_EXECUTE,
            0,  # wIndex
            request_data,
            LOGIC_DEFAULT_TIMEOUT
        )
        
        # Prepare to receive the response
        response_type = usb.util.build_request_type(
            usb.util.CTRL_TYPE_VENDOR,
            usb.util.CTRL_RECIPIENT_ENDPOINT,
            usb.util.CTRL_IN
        )
        
        # Receive the response
        response = usb_dev.ctrl_transfer(
            response_type,
            LIBGREAT_REQUEST_NUMBER,
            LIBGREAT_VALUE_EXECUTE,
            0,  # wIndex
            CORE_MAX_STRING_LENGTH,
            LOGIC_DEFAULT_TIMEOUT
        )
        
        # Convert the response to a string and remove null terminators
        version = response.tostring().decode('utf-8').rstrip('\x00')
        logger.info(f"GreatFET firmware version: {version}")
        return version
    
    except usb.core.USBError as e:
        logger.error(f"Failed to get GreatFET version: {e}")
        return None
