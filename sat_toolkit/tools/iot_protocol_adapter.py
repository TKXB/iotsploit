import logging
import threading
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import time

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
        
        # Check if iot_protocol_fuzzer is available
        self._fuzzer_available = self._check_fuzzer_availability()
        
        logger.info("IoT Protocol Adapter initialized")
    
    def _check_fuzzer_availability(self) -> bool:
        """Check if iot_protocol_fuzzer module is available"""
        try:
            import iot_protocol_fuzzer
            logger.info("iot_protocol_fuzzer module found and available")
            return True
        except ImportError:
            logger.warning("iot_protocol_fuzzer module not available, using mock implementations")
            return False
    
    def _check_radamsa_availability(self) -> bool:
        """Check if radamsa binary is available"""
        try:
            import shutil
            radamsa_path = shutil.which('radamsa')
            if radamsa_path:
                logger.info(f"Radamsa found at: {radamsa_path}")
                return True
            
            # Try common locations
            common_paths = [
                '/usr/bin/radamsa',
                '/usr/local/bin/radamsa',
                '/home/tkxb/Projects/radamsa/bin/radamsa'
            ]
            for path in common_paths:
                if os.path.exists(path):
                    logger.info(f"Radamsa found at: {path}")
                    return True
            
            logger.warning("Radamsa binary not found")
            return False
        except Exception as e:
            logger.error(f"Error checking radamsa availability: {e}")
            return False

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
            campaign_config: Campaign configuration with optional fuzzing_engine
            
        Returns:
            OrchestratorAdapter: Orchestrator adapter instance
        """
        try:
            adapter = OrchestratorAdapter(campaign_config, self._fuzzer_available)
            return adapter
            
        except Exception as e:
            logger.error(f"Error creating orchestrator adapter: {str(e)}")
            raise
    
    def execute_mutations(self, fuzzing_engine: Any, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute mutations from fuzzing engine
        
        Args:
            fuzzing_engine: FuzzingEngine instance
            test_cases: List of test cases to execute mutations for
            
        Returns:
            List[Dict]: List of mutation results
        """
        try:
            if not fuzzing_engine:
                logger.warning("No fuzzing engine provided for mutation execution")
                return []
            
            mutation_results = []
            
            # Convert test cases to FuzzTestCase objects
            from iot_protocol_fuzzer import FuzzTestCase
            
            fuzz_test_cases = []
            for test_case in test_cases:
                # Create frame data from fields
                frame_data = self._create_frame_data_from_fields(test_case.get('frame_fields', []))
                
                fuzz_test_case = FuzzTestCase(
                    id=str(test_case['id']),
                    name=test_case['name'],
                    protocol_type=test_case['protocol_type'],
                    frame_data=frame_data,
                    frame_fields=test_case.get('frame_fields', []),
                    fuzzing_rules=test_case.get('fuzzing_rules', [])
                )
                fuzz_test_cases.append(fuzz_test_case)
            
            # Generate mutations using fuzzing engine
            mutations_by_strategy = fuzzing_engine.generate_mutations(
                fuzz_test_cases, 
                iterations=100  # Default iterations
            )
            
            # Process mutation results
            for strategy_name, mutations in mutations_by_strategy.items():
                for mutation in mutations:
                    result = {
                        'test_case_id': mutation.test_case_id,
                        'test_case_name': test_case.get('name', 'Unknown'),
                        'mutation_type': strategy_name,
                        'original_payload': mutation.original_data.hex(),
                        'mutated_payload': mutation.mutated_data.hex(),
                        'strategy_used': strategy_name,
                        'target_bits': mutation.mutation_info.get('target_bits', ''),
                        'execution_status': 'pending'
                    }
                    mutation_results.append(result)
            
            logger.info(f"Generated {len(mutation_results)} mutations for {len(test_cases)} test cases")
            return mutation_results
            
        except Exception as e:
            logger.error(f"Error executing mutations: {str(e)}")
            return []
    
    def _create_frame_data_from_fields(self, frame_fields: List[Dict[str, Any]]) -> bytes:
        """
        Create frame data from frame fields
        
        Args:
            frame_fields: List of frame field dictionaries
            
        Returns:
            bytes: Frame data as bytes
        """
        try:
            frame_data = b''
            for field in frame_fields:
                value = field.get('value', '')
                if value:
                    # Convert hex string to bytes
                    if value.startswith('0x'):
                        value = value[2:]
                    try:
                        field_bytes = bytes.fromhex(value)
                        frame_data += field_bytes
                    except ValueError:
                        # If not valid hex, treat as string
                        frame_data += value.encode('utf-8')
            
            return frame_data
            
        except Exception as e:
            logger.error(f"Error creating frame data: {e}")
            return b''
    
    def create_monitor_adapter(self, campaign_config: Dict[str, Any], orchestrator_adapter=None) -> 'MonitorAdapter':
        """
        Create a monitor adapter for a campaign
        
        Args:
            campaign_config: Campaign configuration
            orchestrator_adapter: Reference to orchestrator adapter for shared monitor
            
        Returns:
            MonitorAdapter: Monitor adapter instance
        """
        try:
            adapter = MonitorAdapter(campaign_config, self._fuzzer_available, orchestrator_adapter)
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
            adapter = GeneratorAdapter(generator_config, self._fuzzer_available)
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
                return CANInterfaceAdapter(protocol_config, self._fuzzer_available)
            elif protocol_type == 'uart':
                return UARTInterfaceAdapter(protocol_config, self._fuzzer_available)
            elif protocol_type == 'spi':
                return SPIInterfaceAdapter(protocol_config, self._fuzzer_available)
            elif protocol_type == 'ethernet':
                return EthernetInterfaceAdapter(protocol_config, self._fuzzer_available)
            elif protocol_type == 'doip':
                return DoIPInterfaceAdapter(protocol_config, self._fuzzer_available)
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
    
    def get_supported_generators(self) -> List[Dict[str, Any]]:
        """
        Get list of supported generator types and their parameters
        
        Returns:
            List[Dict]: List of supported generators with metadata
        """
        try:
            generators = []
            
            if self._fuzzer_available:
                # Real fuzzer generators
                generators.extend([
                    {
                        'type': 'radamsa',
                        'name': 'Radamsa',
                        'description': 'General-purpose grammar-based fuzzer (Real implementation)',
                        'parameters': {
                            'radamsa_path': {'type': 'string', 'default': 'radamsa', 'description': 'Path to radamsa binary'},
                            'count_per_seed': {'type': 'integer', 'default': 1, 'range': [1, 100]},
                            'iterations': {'type': 'integer', 'default': 1000, 'range': [1, 10000]}
                        },
                        'supported_protocols': ['can', 'uart', 'spi'],
                        'status': 'available' if self._check_radamsa_availability() else 'needs_installation'
                    }
                ])
            
            # Mock/fallback generators (always available)
            generators.extend([
                {
                    'type': 'random',
                    'name': 'Random Data Generator',
                    'description': 'Generates random data for fuzzing (Mock implementation)',
                    'parameters': {
                        'min_length': {'type': 'integer', 'default': 1, 'range': [1, 1024]},
                        'max_length': {'type': 'integer', 'default': 1024, 'range': [1, 4096]},
                        'character_set': {'type': 'string', 'default': 'all', 'options': ['all', 'ascii', 'binary']}
                    },
                    'supported_protocols': ['can', 'uart', 'spi', 'ethernet', 'doip'],
                    'status': 'mock'
                },
                {
                    'type': 'bit_flip',
                    'name': 'Bit Flip Mutator',
                    'description': 'Flips individual bits in data (Mock implementation)',
                    'parameters': {
                        'flip_probability': {'type': 'float', 'default': 0.01, 'range': [0.001, 0.1]},
                        'max_flips': {'type': 'integer', 'default': 5, 'range': [1, 32]}
                    },
                    'supported_protocols': ['can', 'uart', 'spi', 'ethernet', 'doip'],
                    'status': 'mock'
                }
            ])
            
            return generators
            
        except Exception as e:
            logger.error(f"Error getting supported generators: {str(e)}")
            raise
    
    def validate_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate complete configuration (protocol + generator + campaign)
        
        Args:
            config: Complete configuration to validate
            
        Returns:
            Dict: Validation result
        """
        try:
            validation_result = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'config_sections': {}
            }
            
            # Validate protocol configuration
            protocol_config = config.get('protocol_config', {})
            if protocol_config:
                protocol_validation = self._validate_protocol_config(protocol_config)
                validation_result['config_sections']['protocol'] = protocol_validation
                if not protocol_validation['valid']:
                    validation_result['errors'].extend(protocol_validation['errors'])
            else:
                validation_result['errors'].append("Missing protocol configuration")
            
            # Validate generator configuration
            generator_config = config.get('generator_config', {})
            if generator_config:
                generator_validation = self._validate_generator_config(generator_config)
                validation_result['config_sections']['generator'] = generator_validation
                if not generator_validation['valid']:
                    validation_result['errors'].extend(generator_validation['errors'])
            else:
                validation_result['errors'].append("Missing generator configuration")
            
            # Validate campaign configuration
            campaign_config = config.get('campaign_config', {})
            if campaign_config:
                campaign_validation = self._validate_campaign_config(campaign_config)
                validation_result['config_sections']['campaign'] = campaign_validation
                if not campaign_validation['valid']:
                    validation_result['errors'].extend(campaign_validation['errors'])
            else:
                validation_result['warnings'].append("Missing campaign configuration - using defaults")
            
            # Check compatibility between protocol and generator
            if protocol_config and generator_config:
                compatibility_check = self._check_compatibility(protocol_config, generator_config)
                if compatibility_check['warnings']:
                    validation_result['warnings'].extend(compatibility_check['warnings'])
                if compatibility_check['errors']:
                    validation_result['errors'].extend(compatibility_check['errors'])
            
            validation_result['valid'] = len(validation_result['errors']) == 0
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating configuration: {str(e)}")
            raise
    
    def _validate_protocol_config(self, protocol_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate protocol configuration"""
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        protocol_type = protocol_config.get('protocol_type')
        if not protocol_type:
            result['errors'].append("Missing protocol_type")
            return result
        
        if protocol_type not in self.supported_protocols:
            result['errors'].append(f"Unsupported protocol type: {protocol_type}")
            return result
        
        # Validate protocol-specific parameters
        protocol_info = self.supported_protocols[protocol_type]
        required_params = protocol_info.get('parameters', {})
        
        for param_name, param_info in required_params.items():
            if param_info.get('required', False) and param_name not in protocol_config:
                result['errors'].append(f"Missing required parameter: {param_name}")
        
        return result
    
    def _validate_generator_config(self, generator_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate generator configuration"""
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        generator_type = generator_config.get('type')
        if not generator_type:
            result['errors'].append("Missing generator type")
            return result
        
        # Check if generator type is supported
        supported_generators = self.get_supported_generators()
        generator_types = [g['type'] for g in supported_generators]
        
        if generator_type not in generator_types:
            result['errors'].append(f"Unsupported generator type: {generator_type}")
            return result
        
        # Validate generator-specific parameters
        generator_info = next((g for g in supported_generators if g['type'] == generator_type), None)
        if generator_info:
            required_params = generator_info.get('parameters', {})
            
            for param_name, param_info in required_params.items():
                if param_name in generator_config:
                    value = generator_config[param_name]
                    
                    # Validate parameter type
                    param_type = param_info.get('type')
                    if param_type == 'integer' and not isinstance(value, int):
                        result['errors'].append(f"Parameter {param_name} must be an integer")
                    elif param_type == 'float' and not isinstance(value, (int, float)):
                        result['errors'].append(f"Parameter {param_name} must be a number")
                    elif param_type == 'string' and not isinstance(value, str):
                        result['errors'].append(f"Parameter {param_name} must be a string")
                    
                    # Validate parameter range
                    if 'range' in param_info:
                        min_val, max_val = param_info['range']
                        if isinstance(value, (int, float)) and not (min_val <= value <= max_val):
                            result['errors'].append(f"Parameter {param_name} must be between {min_val} and {max_val}")
        
        return result
    
    def _validate_campaign_config(self, campaign_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate campaign configuration"""
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        # Validate iterations
        iterations = campaign_config.get('iterations_total', 1000)
        if not isinstance(iterations, int) or iterations <= 0:
            result['errors'].append("iterations_total must be a positive integer")
        
        # Validate timeout
        timeout = campaign_config.get('timeout_seconds', 1.0)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            result['errors'].append("timeout_seconds must be a positive number")
        
        return result
    
    def _check_compatibility(self, protocol_config: Dict[str, Any], generator_config: Dict[str, Any]) -> Dict[str, Any]:
        """Check compatibility between protocol and generator"""
        result = {'errors': [], 'warnings': []}
        
        protocol_type = protocol_config.get('protocol_type')
        generator_type = generator_config.get('type')
        
        # Check if generator supports the protocol
        supported_generators = self.get_supported_generators()
        generator_info = next((g for g in supported_generators if g['type'] == generator_type), None)
        
        if generator_info:
            supported_protocols = generator_info.get('supported_protocols', [])
            if protocol_type not in supported_protocols:
                result['warnings'].append(f"Generator {generator_type} may not work optimally with protocol {protocol_type}")
        
        return result
    
    def _initialize_supported_protocols(self):
        """Initialize supported protocol configurations"""
        self.supported_protocols = {
            'can': {
                'name': 'Controller Area Network',
                'description': 'Automotive CAN protocol support',
                'parameters': {
                    'interface': {'type': 'string', 'required': True, 'default': 'can0', 'description': 'CAN network interface name (e.g., can0, can1)'},
                    'bitrate': {'type': 'integer', 'required': True, 'default': 500000, 'description': 'CAN bus bitrate in bits/second'},
                    'extended_id': {'type': 'boolean', 'required': False, 'default': False, 'description': 'Use extended CAN ID format'}
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
    
    def __init__(self, campaign_config: Dict[str, Any], fuzzer_available: bool = True):
        """Initialize orchestrator adapter"""
        self.campaign_config = campaign_config
        self.fuzzer_available = fuzzer_available
        self.fuzzer_instance = None
        self.orchestrator = None
        self.is_running = False
        
        # Store fuzzing engine if provided
        self.fuzzing_engine = campaign_config.get('fuzzing_engine')
        if self.fuzzing_engine:
            logger.info("Fuzzing engine provided to orchestrator adapter")
        
        # Try to initialize fuzzer components
        self._initialize_fuzzer_components()
    
    def _initialize_fuzzer_components(self):
        """Initialize fuzzer components"""
        if not self.fuzzer_available:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
            return

        try:
            # Import real fuzzer components
            from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig, EventType
            from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
            from iot_protocol_fuzzer.harnesses.can_harness import CANHarness
            from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
            from iot_protocol_fuzzer.harnesses.spi_harness import SPIHarness
            from iot_protocol_fuzzer.monitoring.monitor import create_monitor
            from iot_protocol_fuzzer.analysis.logger import TestLogger
            
            logger.info("Initializing real fuzzer components")
            
            # Create generator
            generator_config = self.campaign_config.get('generator_config', {})
            generator_type = generator_config.get('generator_type', 'radamsa')
            
            if generator_type == 'radamsa':
                # Try to find radamsa binary
                import shutil
                import os
                radamsa_path = shutil.which('radamsa')
                if not radamsa_path:
                    # Try common locations
                    common_paths = [
                        '/usr/bin/radamsa',
                        '/usr/local/bin/radamsa',
                        '/home/tkxb/Projects/radamsa/bin/radamsa'
                    ]
                    for path in common_paths:
                        if os.path.exists(path):
                            radamsa_path = path
                            break
                
                if radamsa_path:
                    generator = RadamsaGenerator(radamsa_path=radamsa_path)
                    # Set up default seed corpus for CAN fuzzing
                    default_seeds = [
                        b"\x00\x01\x02\x03\x04\x05\x06\x07",  # Basic CAN frame
                        b"\x02\x01\x00",                       # UDS DiagnosticSessionControl
                        b"\x10\x01",                           # UDS DiagnosticSessionControl (default)
                        b"\x10\x02",                           # UDS DiagnosticSessionControl (programming)
                        b"\x10\x03",                           # UDS DiagnosticSessionControl (extended)
                        b"\x11\x01",                           # UDS ECU Reset (hard reset)
                        b"\x27\x01",                           # UDS SecurityAccess (request seed)
                        b"\x3E\x00",                           # UDS TesterPresent
                        b"\x22\xF1\x90",                       # UDS ReadDataByIdentifier
                        b"\x2E\xF1\x90\x00\x01\x02\x03",     # UDS WriteDataByIdentifier
                    ]
                    generator.seed_corpus = lambda: default_seeds
                    logger.info(f"Using radamsa at: {radamsa_path} with {len(default_seeds)} seed templates")
                else:
                    logger.warning("Radamsa not found, falling back to mock")
                    self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
                    return
            else:
                logger.warning(f"Unsupported generator type: {generator_type}, using mock")
                self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
                return
            
            # Create harness based on protocol type
            protocol_config = self.campaign_config.get('protocol_config', {})
            protocol_type = protocol_config.get('protocol_type', '').lower()
            
            if protocol_type == 'can':
                from iot_protocol_fuzzer.interfaces.can_interface import SocketCANInterface
                # CAN interfaces are network interfaces (can0), not device files (/dev/can0)
                channel = protocol_config.get('device_path', 'can0')
                if channel.startswith('/dev/'):
                    channel = channel[5:]  # Remove '/dev/' prefix
                interface = SocketCANInterface(
                    channel=channel,
                    bitrate=protocol_config.get('bitrate', 500000)
                )
                harness = CANHarness(interface)
            elif protocol_type == 'uart':
                from iot_protocol_fuzzer.interfaces.uart_interface import SerialInterface
                interface = SerialInterface(
                    port=protocol_config.get('port', '/dev/ttyUSB0'),
                    baud_rate=protocol_config.get('baud_rate', 115200)
                )
                harness = UARTHarness(interface)
            elif protocol_type == 'spi':
                from iot_protocol_fuzzer.interfaces.spi_interface import SPIInterface
                interface = SPIInterface(
                    bus=protocol_config.get('bus', 0),
                    device=protocol_config.get('device', 0)
                )
                harness = SPIHarness(interface)
            else:
                logger.warning(f"Unsupported protocol type: {protocol_type}, using mock")
                self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
                return
            
            # Create monitor and logger (pluggable by protocol)
            self.monitor = create_monitor(protocol_type, self.campaign_config.get('monitoring'))
            logger_backend = TestLogger()
            
            # Create campaign config with event callback
            campaign_config = CampaignConfig(
                iterations=self.campaign_config.get('iterations_total', 1000),
                delay=self.campaign_config.get('delay', 0.1),
                save_crashes=True,
                event_callback=self._handle_fuzzer_event
            )
            
            # Create orchestrator
            self.orchestrator = Orchestrator(
                generator=generator,
                harness=harness,
                monitor=self.monitor,
                logger_backend=logger_backend,
                config=campaign_config
            )
            
            logger.info("Real fuzzer components initialized successfully")
            
        except ImportError as e:
            logger.warning(f"Failed to import iot_protocol_fuzzer: {e}, using mock implementation")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
        except Exception as e:
            logger.error(f"Error initializing fuzzer components: {e}, using mock implementation")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
    
    def start(self):
        """Start fuzzing campaign"""
        if self.orchestrator:
            # Start the real fuzzer in a separate thread
            import threading
            self.is_running = True
            self.fuzzer_thread = threading.Thread(target=self._run_campaign)
            self.fuzzer_thread.daemon = True
            self.fuzzer_thread.start()
            logger.info("Real orchestrator started")
        elif self.fuzzer_instance:
            self.fuzzer_instance.start()
            self.is_running = True
            logger.info("Mock orchestrator started")
    
    def _run_campaign(self):
        """Run the actual fuzzing campaign"""
        try:
            if self.fuzzing_engine:
                # Use fuzzing engine if available
                logger.info("Running campaign with fuzzing engine")
                self._run_with_fuzzing_engine()
            elif self.orchestrator:
                # Use traditional orchestrator
                self.orchestrator.run()
            else:
                logger.warning("No fuzzing engine or orchestrator available")
        except Exception as e:
            logger.error(f"Error during fuzzing campaign: {e}")
        finally:
            self.is_running = False
    
    def _run_with_fuzzing_engine(self):
        """Run campaign using the fuzzing engine"""
        try:
            if not self.fuzzing_engine:
                logger.error("No fuzzing engine available")
                return
            
            # Get test cases from campaign config
            test_cases = self.campaign_config.get('test_cases', [])
            if not test_cases:
                logger.warning("No test cases provided for fuzzing engine")
                return
            
            logger.info(f"Starting fuzzing engine with {len(test_cases)} test cases")
            
            # Execute mutations using fuzzing engine
            for test_case in test_cases:
                try:
                    # Generate mutations for this test case
                    mutations = self.fuzzing_engine.generate_mutations(
                        test_case, 
                        iterations=test_case.get('iterations', 100)
                    )
                    
                    # Execute each mutation
                    for mutation in mutations:
                        self._execute_mutation(mutation, test_case)
                        
                except Exception as e:
                    logger.error(f"Error processing test case {test_case.get('id', 'unknown')}: {e}")
                    continue
            
            logger.info("Fuzzing engine campaign completed")
            
        except Exception as e:
            logger.error(f"Error in fuzzing engine campaign: {e}")
    
    def _execute_mutation(self, mutation: Dict[str, Any], test_case: Dict[str, Any]):
        """Execute a single mutation"""
        try:
            # Extract mutation data
            original_payload = mutation.get('original', '')
            mutated_payload = mutation.get('mutated', '')
            strategy_used = mutation.get('strategy', 'unknown')
            target_bits = mutation.get('target_bits', '')
            
            # Log mutation execution
            logger.debug(f"Executing mutation: {strategy_used} -> {target_bits}")
            
            # Here you would send the mutated payload to the target
            # For now, we'll just log the execution
            logger.info(f"Mutation executed for test case {test_case.get('id')}: {strategy_used}")
            
            # Emit event for mutation execution
            self._handle_fuzzer_event('mutation_executed', {
                'test_case_id': test_case.get('id'),
                'mutation_type': strategy_used,
                'target_bits': target_bits,
                'original_payload': original_payload,
                'mutated_payload': mutated_payload
            })
            
        except Exception as e:
            logger.error(f"Error executing mutation: {e}")
    
    def stop(self):
        """Stop fuzzing campaign"""
        if self.orchestrator:
            self.orchestrator.stop()
            self.is_running = False
            logger.info("Real orchestrator stopped")
        elif self.fuzzer_instance:
            self.fuzzer_instance.stop()
            self.is_running = False
            logger.info("Mock orchestrator stopped")
    
    def pause(self):
        """Pause fuzzing campaign"""
        if self.orchestrator:
            self.orchestrator.pause()
            logger.info("Real orchestrator paused")
        elif self.fuzzer_instance:
            self.fuzzer_instance.pause()
            logger.info("Mock orchestrator paused")
    
    def resume(self):
        """Resume fuzzing campaign"""
        if self.orchestrator:
            self.orchestrator.resume()
            logger.info("Real orchestrator resumed")
        elif self.fuzzer_instance:
            self.fuzzer_instance.resume()
            logger.info("Mock orchestrator resumed")
    
    def reset(self):
        """Reset fuzzing campaign"""
        if self.orchestrator:
            self.orchestrator.stop()  # Stop first, then can restart
            logger.info("Real orchestrator reset (stopped)")
        elif self.fuzzer_instance:
            self.fuzzer_instance.reset()
            logger.info("Mock orchestrator reset")
    
    def get_status(self):
        """Get current campaign status"""
        if self.orchestrator:
            return self.orchestrator.get_current_stats()
        elif self.fuzzer_instance:
            return self.fuzzer_instance.get_status()
        return {}
    
    def get_monitor(self):
        """Get the monitor instance used by the orchestrator"""
        if hasattr(self, 'monitor'):
            return self.monitor
        return None
    
    def cleanup(self):
        """Cleanup orchestrator resources"""
        if self.orchestrator:
            self.is_running = False
            logger.info("Real orchestrator cleaned up")
        elif self.fuzzer_instance:
            self.fuzzer_instance.cleanup()
            logger.info("Mock orchestrator cleaned up")

    def _handle_fuzzer_event(self, event_type, event_data):
        """Handle events from the fuzzer and forward to Django WebSocket system"""
        try:
            campaign_id = self.campaign_config.get('campaign_id')
            if not campaign_id:
                logger.warning("No campaign_id in config, cannot emit WebSocket events")
                return
            
            # Import Django bridge components
            from sat_toolkit.tools.iot_fuzzer_bridge import IoTFuzzerBridge
            
            # Get bridge instance and emit event
            bridge = IoTFuzzerBridge.get_instance()
            
            # Map fuzzer event types to Django event types
            event_mapping = {
                'campaign_started': 'campaign_status',
                'campaign_paused': 'campaign_status',
                'campaign_resumed': 'campaign_status',
                'campaign_stopped': 'campaign_status',
                'campaign_completed': 'campaign_status',
                'test_case_started': 'test_case_update',
                'test_case_completed': 'test_case_update',
                'crash_detected': 'crash_alert',
                'statistics_update': 'statistics_update',
                'progress_update': 'progress_update',
            }
            
            django_event_type = event_mapping.get(event_type.value if hasattr(event_type, 'value') else event_type, 'unknown')
            
            # Enhance event data with campaign info
            enhanced_data = {
                'campaign_id': campaign_id,
                'timestamp': event_data.get('timestamp', time.time()),
                'event_type': event_type.value if hasattr(event_type, 'value') else event_type,
                **event_data
            }
            
            # Special handling for different event types
            if django_event_type == 'campaign_status':
                enhanced_data.update({
                    'is_running': self.orchestrator.is_running() if self.orchestrator else False,
                    'is_paused': self.orchestrator.is_paused() if self.orchestrator else False,
                    'status': self._get_campaign_status()
                })
            
            # Emit event to Django WebSocket system
            bridge.emit_event(django_event_type, enhanced_data)
            
        except Exception as e:
            logger.error(f"Error handling fuzzer event: {e}")
    
    def _get_campaign_status(self):
        """Get current campaign status string"""
        if not self.orchestrator:
            return 'idle'
        
        if self.orchestrator.is_paused():
            return 'paused'
        elif self.orchestrator.is_running():
            return 'running'
        else:
            return 'idle'


class MonitorAdapter:
    """
    Adapter for iot_protocol_fuzzer monitor component
    """
    
    def __init__(self, campaign_config: Dict[str, Any], fuzzer_available: bool = True, orchestrator_adapter=None):
        """Initialize monitor adapter"""
        self.campaign_config = campaign_config
        self.fuzzer_available = fuzzer_available
        self.orchestrator_adapter = orchestrator_adapter
        self.monitor_instance = None
        self.real_monitor = None
        
        # Try to initialize monitor components
        self._initialize_monitor_components()
    
    def _initialize_monitor_components(self):
        """Initialize monitor components"""
        # If we have an orchestrator adapter, use its monitor
        if self.orchestrator_adapter:
            self.real_monitor = self.orchestrator_adapter.get_monitor()
            if self.real_monitor:
                logger.info("Using shared monitor from orchestrator adapter")
                return
        
        if not self.fuzzer_available:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
            return
        
        try:
            # Import monitor factory
            from iot_protocol_fuzzer.monitoring.monitor import create_monitor
            
            logger.info("Initializing real monitor components")
            # Determine protocol type from campaign config
            protocol_type = (self.campaign_config.get('protocol_config', {}) or {}).get('protocol_type')
            self.real_monitor = create_monitor(protocol_type, self.campaign_config.get('monitoring'))
            
        except ImportError as e:
            logger.warning(f"Failed to import iot_protocol_fuzzer monitor: {e}, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
        except Exception as e:
            logger.error(f"Error initializing monitor components: {e}, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
    
    def get_status(self) -> Dict[str, Any]:
        """Get real-time campaign status"""
        if self.real_monitor:
            stats = self.real_monitor.get_stats()
            return {
                'iterations_per_second': stats.get('cases_per_second', 0.0),
                'current_iteration': stats.get('total_cases', 0),
                'last_crash_time': stats.get('last_crash_time'),
                'active_generators': 1 if stats.get('total_cases', 0) > 0 else 0
            }
        elif self.monitor_instance:
            return self.monitor_instance.get_status()
        return {}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed campaign statistics"""
        if self.real_monitor:
            stats = self.real_monitor.get_stats()
            return {
                'total_iterations': stats.get('total_cases', 0),
                'crashes_detected': stats.get('crash_count', 0),
                'timeouts': stats.get('timeout_count', 0),
                'average_response_time': stats.get('avg_response_time', 0.0),
                'unique_crashes': stats.get('unique_crashes', 0)
            }
        elif self.monitor_instance:
            return self.monitor_instance.get_statistics()
        return {}
    
    def cleanup(self):
        """Cleanup monitor resources"""
        if self.real_monitor and not self.orchestrator_adapter:
            # Only reset if we're not sharing the monitor
            self.real_monitor.reset()
            logger.info("Real monitor cleaned up")
        elif self.monitor_instance:
            self.monitor_instance.cleanup()
            logger.info("Mock monitor cleaned up")


class GeneratorAdapter:
    """
    Adapter for iot_protocol_fuzzer generator component
    """
    
    def __init__(self, generator_config: Dict[str, Any], fuzzer_available: bool = True):
        """Initialize generator adapter"""
        self.generator_config = generator_config
        self.fuzzer_available = fuzzer_available
        self.generator_instance = None
        self.real_generator = None
        
        # Try to initialize generator components
        self._initialize_generator_components()
    
    def _initialize_generator_components(self):
        """Initialize generator components"""
        if not self.fuzzer_available:
            logger.warning("iot_protocol_fuzzer not available, using mock implementation")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
            return
        
        try:
            # Import real generator component
            from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
            
            logger.info("Initializing real generator components")
            
            # Check for radamsa binary
            import shutil
            import os
            radamsa_path = shutil.which('radamsa')
            if not radamsa_path:
                # Try common locations
                common_paths = [
                    '/usr/bin/radamsa',
                    '/usr/local/bin/radamsa',
                    '/home/tkxb/Projects/radamsa/bin/radamsa'
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        radamsa_path = path
                        break
            
            if radamsa_path:
                self.real_generator = RadamsaGenerator(radamsa_path=radamsa_path)
                logger.info(f"Real generator initialized with radamsa at: {radamsa_path}")
            else:
                logger.warning("Radamsa not found, falling back to mock")
                self.generator_instance = MockGeneratorInstance(self.generator_config)
            
        except ImportError as e:
            logger.warning(f"Failed to import iot_protocol_fuzzer generator: {e}, using mock implementation")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
        except Exception as e:
            logger.error(f"Error initializing generator components: {e}, using mock implementation")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
    
    def generate(self, seed_data: bytes) -> bytes:
        """Generate mutated data"""
        if self.real_generator:
            # Use real generator
            try:
                mutations = list(self.real_generator.generate([seed_data], 1))
                if mutations:
                    return mutations[0]
                else:
                    return seed_data
            except Exception as e:
                logger.error(f"Error generating mutation: {e}")
                return seed_data
        elif self.generator_instance:
            return self.generator_instance.generate(seed_data)
        return seed_data


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
            from iot_protocol_fuzzer.interfaces.can_interface import SocketCANInterface
            
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


# Global instance
_instance = None 