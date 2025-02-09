"""SCPI device driver integration with device manager framework."""

from sat_toolkit.core.base_plugin import BasePlugin
from ..client import ScpiClient
from ..transport import ScpiTcpTransport, ScpiSerialTransport


class ScpiDeviceDriver(BasePlugin):
    """Driver for SCPI-compatible instruments."""

    def __init__(self, device_id: str, config: dict):
        """Initialize SCPI device driver.
        
        Args:
            device_id: Unique device identifier
            config: Device configuration dictionary containing:
                   - transport_type: 'tcp' or 'serial'
                   - For TCP: host, port
                   - For Serial: port, baudrate
        """
        super().__init__(device_id)
        self.config = config
        self._client = None
        self._setup_client()

    def _setup_client(self):
        """Set up SCPI client based on configuration."""
        transport_type = self.config.get('transport_type', 'tcp')
        
        if transport_type == 'tcp':
            transport = ScpiTcpTransport(
                host=self.config['host'],
                port=self.config['port']
            )
        elif transport_type == 'serial':
            transport = ScpiSerialTransport(
                port=self.config['port'],
                baudrate=self.config.get('baudrate', 9600)
            )
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")
        
        self._client = ScpiClient(transport)

    def connect(self):
        """Connect to the SCPI device."""
        try:
            self._client.connect()
            device_info = self._client.identify()
            self.logger.info(f"Connected to SCPI device: {device_info}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to SCPI device: {e}")
            return False

    def disconnect(self):
        """Disconnect from the SCPI device."""
        try:
            self._client.disconnect()
            self.logger.info("Disconnected from SCPI device")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from SCPI device: {e}")
            return False

    def send_command(self, command: str):
        """Send SCPI command to device.
        
        Args:
            command: SCPI command string
        """
        return self._client.send_command(command)

    def query(self, command: str) -> str:
        """Send query and get response from device.
        
        Args:
            command: SCPI query command
            
        Returns:
            Device response string
        """
        return self._client.query(command) 