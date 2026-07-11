import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ProtocolInterfaceAdapter:
    """
    Base class for protocol interface adapters
    """

    def __init__(self, protocol_config: Dict[str, Any], fuzzer_available: bool = True):
        """Initialize protocol interface adapter"""
        self.protocol_config = protocol_config
        self.fuzzer_available = fuzzer_available
        self.interface_instance = None

    def test_connection(self) -> bool:
        """Test protocol connection"""
        return False

    def send_data(self, data: bytes) -> bytes:
        """Send data through protocol interface"""
        return b''

    def receive_data(self, timeout: float = 1.0) -> bytes:
        """Receive data from protocol interface"""
        return b''

class CANInterfaceAdapter(ProtocolInterfaceAdapter):
    """CAN protocol interface adapter"""

    def __init__(self, protocol_config: Dict[str, Any], fuzzer_available: bool = True):
        super().__init__(protocol_config, fuzzer_available)
        self.real_interface = None
        self._initialize_interface()

    def _initialize_interface(self):
        """Initialize CAN interface"""
        if not self.fuzzer_available:
            logger.info("Testing CAN connection (mock)")
            return

        try:
            from iotsploit_fuzzer.interfaces.can_interface import SocketCANInterface

            # CAN interfaces are network interfaces (can0), not device files (/dev/can0)
            channel = self.protocol_config.get('device_path', 'can0')
            if channel.startswith('/dev/'):
                channel = channel[5:]  # Remove '/dev/' prefix
            bitrate = self.protocol_config.get('bitrate', 500000)

            self.real_interface = SocketCANInterface(channel=channel, bitrate=bitrate)
            logger.info(f"Real CAN interface initialized: {channel} @ {bitrate}")

        except ImportError as e:
            logger.warning(f"Failed to import CAN interface: {e}")
        except Exception as e:
            logger.error(f"Error initializing CAN interface: {e}")

    def test_connection(self) -> bool:
        """Test CAN connection"""
        if self.real_interface:
            try:
                # Try to send a test message
                test_data = b'\x00\x01\x02\x03'
                self.real_interface.send(test_data)
                logger.info("Real CAN connection test successful")
                return True
            except Exception as e:
                logger.error(f"Real CAN connection test failed: {e}")
                return False
        else:
            logger.info("Testing CAN connection (mock)")
            return True  # Mock implementation always succeeds

class UARTInterfaceAdapter(ProtocolInterfaceAdapter):
    """UART protocol interface adapter"""

    def test_connection(self) -> bool:
        """Test UART connection"""
        logger.info("Testing UART connection (mock)")
        return True  # Mock implementation always succeeds

class SPIInterfaceAdapter(ProtocolInterfaceAdapter):
    """SPI protocol interface adapter"""

    def test_connection(self) -> bool:
        """Test SPI connection"""
        logger.info("Testing SPI connection (mock)")
        return True  # Mock implementation always succeeds

class EthernetInterfaceAdapter(ProtocolInterfaceAdapter):
    """Ethernet protocol interface adapter"""

    def test_connection(self) -> bool:
        """Test Ethernet connection"""
        logger.info("Testing Ethernet connection (mock)")
        return True  # Mock implementation always succeeds

class DoIPInterfaceAdapter(ProtocolInterfaceAdapter):
    """DoIP protocol interface adapter"""

    def test_connection(self) -> bool:
        """Test DoIP connection"""
        logger.info("Testing DoIP connection (mock)")
        return True  # Mock implementation always succeeds

class MockOrchestratorInstance:
    """Mock orchestrator instance"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.running = False

    def start(self):
        self.running = True
        logger.info("Mock orchestrator started")

    def stop(self):
        self.running = False
        logger.info("Mock orchestrator stopped")

    def pause(self):
        logger.info("Mock orchestrator paused")

    def resume(self):
        logger.info("Mock orchestrator resumed")

    def reset(self):
        logger.info("Mock orchestrator reset")

    def cleanup(self):
        logger.info("Mock orchestrator cleanup")

class MockMonitorInstance:
    """Mock monitor instance"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get_status(self) -> Dict[str, Any]:
        return {
            'iterations_per_second': 10.5,
            'current_iteration': 150,
            'last_crash_time': None,
            'active_generators': 1
        }

    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_iterations': 1000,
            'crashes_detected': 2,
            'timeouts': 5,
            'average_response_time': 0.25,
            'unique_crashes': 2
        }

    def cleanup(self):
        logger.info("Mock monitor cleanup")

class MockGeneratorInstance:
    """Mock generator instance"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def generate(self, seed_data: bytes) -> bytes:
        # Simple mock mutation - flip a random bit
        if seed_data:
            data = bytearray(seed_data)
            if len(data) > 0:
                data[0] = data[0] ^ 0x01
            return bytes(data)
        return b'\x00\x01\x02\x03'  # Default mock data
