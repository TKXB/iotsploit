import logging
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class IoTProtocolAdapter:
    """
    IoT Protocol Adapter - Adapter pattern implementation for iot_protocol_fuzzer integration
    This class provides the bridge between Django services and the iot_protocol_fuzzer components
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of IoTProtocolAdapter"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the IoT Protocol Adapter"""
        if IoTProtocolAdapter._instance is not None:
            raise Exception("This class is a singleton!")
        
        self.protocol_interfaces: Dict[str, Any] = {}
        self.generator_adapters: Dict[str, Any] = {}
        self.orchestrator_adapters: Dict[str, Any] = {}
        self.monitor_adapters: Dict[str, Any] = {}
        
        # Initialize supported protocols
        self._initialize_supported_protocols()
        
        logger.info("IoT Protocol Adapter initialized")
    
    def get_supported_protocols(self) -> List[Dict[str, Any]]:
        """
        Get list of supported protocol types and their parameters
        
        Returns:
            List[Dict]: List of supported protocols with metadata
        """
        try:
            protocols = []
            
            # Try to import and discover protocols from iot_protocol_fuzzer
            try:
                # This is where we would import from iot_protocol_fuzzer
                # For now, we'll return a hardcoded list of known protocols
                supported_protocols = self._get_hardcoded_protocols()
                
                for protocol_type, protocol_info in supported_protocols.items():
                    protocols.append({
                        'type': protocol_type,
                        'name': protocol_info['name'],
                        'description': protocol_info['description'],
                        'parameters': protocol_info['parameters'],
                        'supported_features': protocol_info['features']
                    })
                
            except ImportError:
                logger.warning("iot_protocol_fuzzer not available, returning mock protocols")
                protocols = self._get_mock_protocols()
            
            return protocols
            
        except Exception as e:
            logger.error(f"Error getting supported protocols: {str(e)}")
            raise
    
    def create_orchestrator_adapter(self, campaign_config: Dict[str, Any]) -> 'OrchestratorAdapter':
        """
        Create an orchestrator adapter for a campaign
        
        Args:
            campaign_config: Campaign configuration
            
        Returns:
            OrchestratorAdapter: Orchestrator adapter instance
        """
        try:
            adapter = OrchestratorAdapter(campaign_config)
            return adapter
            
        except Exception as e:
            logger.error(f"Error creating orchestrator adapter: {str(e)}")
            raise
    
    def create_monitor_adapter(self, campaign_config: Dict[str, Any]) -> 'MonitorAdapter':
        """
        Create a monitor adapter for a campaign
        
        Args:
            campaign_config: Campaign configuration
            
        Returns:
            MonitorAdapter: Monitor adapter instance
        """
        try:
            adapter = MonitorAdapter(campaign_config)
            return adapter
            
        except Exception as e:
            logger.error(f"Error creating monitor adapter: {str(e)}")
            raise
    
    def create_generator_adapter(self, generator_config: Dict[str, Any]) -> 'GeneratorAdapter':
        """
        Create a generator adapter
        
        Args:
            generator_config: Generator configuration
            
        Returns:
            GeneratorAdapter: Generator adapter instance
        """
        try:
            adapter = GeneratorAdapter(generator_config)
            return adapter
            
        except Exception as e:
            logger.error(f"Error creating generator adapter: {str(e)}")
            raise
    
    def create_protocol_interface_adapter(self, protocol_config: Dict[str, Any]) -> 'ProtocolInterfaceAdapter':
        """
        Create a protocol interface adapter
        
        Args:
            protocol_config: Protocol configuration
            
        Returns:
            ProtocolInterfaceAdapter: Protocol interface adapter instance
        """
        try:
            protocol_type = protocol_config.get('protocol_type', 'unknown')
            
            if protocol_type == 'can':
                return CANInterfaceAdapter(protocol_config)
            elif protocol_type == 'uart':
                return UARTInterfaceAdapter(protocol_config)
            elif protocol_type == 'spi':
                return SPIInterfaceAdapter(protocol_config)
            elif protocol_type == 'ethernet':
                return EthernetInterfaceAdapter(protocol_config)
            elif protocol_type == 'doip':
                return DoIPInterfaceAdapter(protocol_config)
            else:
                raise ValueError(f"Unsupported protocol type: {protocol_type}")
            
        except Exception as e:
            logger.error(f"Error creating protocol interface adapter: {str(e)}")
            raise
    
    def test_connection(self, protocol_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test protocol connection
        
        Args:
            protocol_config: Protocol configuration
            
        Returns:
            Dict: Connection test result
        """
        try:
            # Create protocol interface adapter
            interface_adapter = self.create_protocol_interface_adapter(protocol_config)
            
            # Test connection
            result = interface_adapter.test_connection()
            
            return {
                'status': 'success' if result else 'failure',
                'protocol_type': protocol_config.get('protocol_type'),
                'connection_result': result,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            return {
                'status': 'error',
                'protocol_type': protocol_config.get('protocol_type'),
                'error_message': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _initialize_supported_protocols(self):
        """Initialize supported protocol configurations"""
        self.supported_protocols = {
            'can': {
                'name': 'Controller Area Network',
                'description': 'Automotive CAN protocol support',
                'parameters': {
                    'interface': {'type': 'string', 'required': True, 'default': 'can0'},
                    'bitrate': {'type': 'integer', 'required': True, 'default': 500000},
                    'extended_id': {'type': 'boolean', 'required': False, 'default': False}
                },
                'features': ['fuzzing', 'monitoring', 'replay']
            },
            'uart': {
                'name': 'Universal Asynchronous Receiver-Transmitter',
                'description': 'Serial UART protocol support',
                'parameters': {
                    'port': {'type': 'string', 'required': True, 'default': '/dev/ttyUSB0'},
                    'baud_rate': {'type': 'integer', 'required': True, 'default': 115200},
                    'data_bits': {'type': 'integer', 'required': False, 'default': 8},
                    'stop_bits': {'type': 'integer', 'required': False, 'default': 1},
                    'parity': {'type': 'string', 'required': False, 'default': 'none'}
                },
                'features': ['fuzzing', 'monitoring', 'replay']
            },
            'spi': {
                'name': 'Serial Peripheral Interface',
                'description': 'SPI protocol support',
                'parameters': {
                    'bus': {'type': 'integer', 'required': True, 'default': 0},
                    'device': {'type': 'integer', 'required': True, 'default': 0},
                    'speed': {'type': 'integer', 'required': False, 'default': 1000000},
                    'mode': {'type': 'integer', 'required': False, 'default': 0}
                },
                'features': ['fuzzing', 'monitoring']
            },
            'ethernet': {
                'name': 'Ethernet',
                'description': 'Ethernet protocol support',
                'parameters': {
                    'interface': {'type': 'string', 'required': True, 'default': 'eth0'},
                    'target_ip': {'type': 'string', 'required': True},
                    'target_port': {'type': 'integer', 'required': True},
                    'protocol': {'type': 'string', 'required': False, 'default': 'tcp'}
                },
                'features': ['fuzzing', 'monitoring', 'replay']
            },
            'doip': {
                'name': 'Diagnostics over Internet Protocol',
                'description': 'DoIP protocol support',
                'parameters': {
                    'target_ip': {'type': 'string', 'required': True, 'default': '192.168.1.100'},
                    'target_port': {'type': 'integer', 'required': True, 'default': 13400},
                    'source_address': {'type': 'integer', 'required': False, 'default': 0x0E80},
                    'target_address': {'type': 'integer', 'required': True}
                },
                'features': ['fuzzing', 'monitoring', 'diagnostics']
            }
        }
    
    def _get_hardcoded_protocols(self) -> Dict[str, Any]:
        """Get hardcoded protocol definitions"""
        return self.supported_protocols
    
    def _get_mock_protocols(self) -> List[Dict[str, Any]]:
        """Get mock protocol list when fuzzer is not available"""
        return [
            {
                'type': 'can',
                'name': 'Controller Area Network (Mock)',
                'description': 'Mock CAN protocol for testing',
                'parameters': {'interface': 'can0', 'bitrate': 500000},
                'supported_features': ['mock_fuzzing']
            },
            {
                'type': 'uart',
                'name': 'UART (Mock)',
                'description': 'Mock UART protocol for testing',
                'parameters': {'port': '/dev/ttyUSB0', 'baud_rate': 115200},
                'supported_features': ['mock_fuzzing']
            }
        ]


class OrchestratorAdapter:
    """
    Adapter for iot_protocol_fuzzer orchestrator component
    """
    
    def __init__(self, campaign_config: Dict[str, Any]):
        """Initialize orchestrator adapter"""
        self.campaign_config = campaign_config
        self.fuzzer_instance = None
        self.is_running = False
        
        # Try to initialize fuzzer components
        self._initialize_fuzzer_components()
    
    def _initialize_fuzzer_components(self):
        """Initialize fuzzer components"""
        try:
            # This is where we would import and initialize iot_protocol_fuzzer components
            # For now, we'll create a mock implementation
            logger.info("Initializing fuzzer components (mock implementation)")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
            
        except ImportError:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
    
    def start(self):
        """Start fuzzing campaign"""
        if self.fuzzer_instance:
            self.fuzzer_instance.start()
            self.is_running = True
            logger.info("Orchestrator started")
    
    def stop(self):
        """Stop fuzzing campaign"""
        if self.fuzzer_instance:
            self.fuzzer_instance.stop()
            self.is_running = False
            logger.info("Orchestrator stopped")
    
    def pause(self):
        """Pause fuzzing campaign"""
        if self.fuzzer_instance:
            self.fuzzer_instance.pause()
            logger.info("Orchestrator paused")
    
    def reset(self):
        """Reset fuzzing campaign"""
        if self.fuzzer_instance:
            self.fuzzer_instance.reset()
            logger.info("Orchestrator reset")
    
    def cleanup(self):
        """Cleanup orchestrator resources"""
        if self.fuzzer_instance:
            self.fuzzer_instance.cleanup()
            logger.info("Orchestrator cleaned up")


class MonitorAdapter:
    """
    Adapter for iot_protocol_fuzzer monitor component
    """
    
    def __init__(self, campaign_config: Dict[str, Any]):
        """Initialize monitor adapter"""
        self.campaign_config = campaign_config
        self.monitor_instance = None
        
        # Try to initialize monitor components
        self._initialize_monitor_components()
    
    def _initialize_monitor_components(self):
        """Initialize monitor components"""
        try:
            # This is where we would import and initialize iot_protocol_fuzzer monitor
            logger.info("Initializing monitor components (mock implementation)")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
            
        except ImportError:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
    
    def get_status(self) -> Dict[str, Any]:
        """Get real-time campaign status"""
        if self.monitor_instance:
            return self.monitor_instance.get_status()
        return {}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed campaign statistics"""
        if self.monitor_instance:
            return self.monitor_instance.get_statistics()
        return {}
    
    def cleanup(self):
        """Cleanup monitor resources"""
        if self.monitor_instance:
            self.monitor_instance.cleanup()
            logger.info("Monitor cleaned up")


class GeneratorAdapter:
    """
    Adapter for iot_protocol_fuzzer generator component
    """
    
    def __init__(self, generator_config: Dict[str, Any]):
        """Initialize generator adapter"""
        self.generator_config = generator_config
        self.generator_instance = None
        
        # Try to initialize generator components
        self._initialize_generator_components()
    
    def _initialize_generator_components(self):
        """Initialize generator components"""
        try:
            # This is where we would import and initialize iot_protocol_fuzzer generators
            logger.info("Initializing generator components (mock implementation)")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
            
        except ImportError:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
    
    def generate(self, seed_data: bytes) -> bytes:
        """Generate mutated data"""
        if self.generator_instance:
            return self.generator_instance.generate(seed_data)
        return seed_data


class ProtocolInterfaceAdapter:
    """
    Base class for protocol interface adapters
    """
    
    def __init__(self, protocol_config: Dict[str, Any]):
        """Initialize protocol interface adapter"""
        self.protocol_config = protocol_config
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
    
    def test_connection(self) -> bool:
        """Test CAN connection"""
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


# Mock implementations for when iot_protocol_fuzzer is not available
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


# Global instance
_instance = None 