import logging

from iotsploit_core.core.tool_manager import PathResolver
from iotsploit_django.tools.frame_utils import frame_data_from_fields
import threading
from typing import Dict, Any, List
from datetime import datetime

from iotsploit_django.tools.iot_protocol_components import (
    CANInterfaceAdapter,
    DoIPInterfaceAdapter,
    EthernetInterfaceAdapter,
    ProtocolInterfaceAdapter,
    SPIInterfaceAdapter,
    UARTInterfaceAdapter,
)

from iotsploit_django.tools.iot_protocol_runtime import GeneratorAdapter, MonitorAdapter, OrchestratorAdapter

logger = logging.getLogger(__name__)

class IoTProtocolAdapter:
    """
    IoT Protocol Adapter - Adapter pattern implementation for iotsploit_fuzzer integration
    This class provides the bridge between Django services and the iotsploit_fuzzer components
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
        
        # Check if iotsploit_fuzzer is available
        self._fuzzer_available = self._check_fuzzer_availability()
        
        logger.info("IoT Protocol Adapter initialized")
    
    def _check_fuzzer_availability(self) -> bool:
        """Check if iotsploit_fuzzer module is available"""
        try:
            import iotsploit_fuzzer  # noqa: F401
            logger.info("iotsploit_fuzzer module found and available")
            return True
        except ImportError:
            logger.warning("iotsploit_fuzzer module not available, using mock implementations")
            return False
    
    def _check_radamsa_availability(self) -> bool:
        """Check if radamsa binary is available"""
        try:
            radamsa_path = PathResolver().resolve_tool_path("radamsa")
            if radamsa_path:
                logger.info(f"Radamsa found at: {radamsa_path}")
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
            
            # Try to import and discover protocols from iotsploit_fuzzer
            try:
                # This is where we would import from iotsploit_fuzzer
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
                logger.warning("iotsploit_fuzzer not available, returning mock protocols")
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
            from iotsploit_fuzzer import FuzzTestCase
            
            fuzz_test_cases = []
            for test_case in test_cases:
                # Create frame data from fields
                frame_data = frame_data_from_fields(test_case.get('frame_fields', []))
                
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
                    'port': {'type': 'string', 'required': True, 'default': ''},
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
                'parameters': {'port': '', 'baud_rate': 115200},
                'supported_features': ['mock_fuzzing']
            }
        ]




















# Mock implementations for when iotsploit_fuzzer is not available






# Global instance
_instance = None
