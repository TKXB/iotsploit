import logging
import threading
import os
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
            campaign_config: Campaign configuration
            
        Returns:
            OrchestratorAdapter: Orchestrator adapter instance
        """
        try:
            adapter = OrchestratorAdapter(campaign_config, self._fuzzer_available)
            return adapter
            
        except Exception as e:
            logger.error(f"Error creating orchestrator adapter: {str(e)}")
            raise
    
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
            from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig
            from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
            from iot_protocol_fuzzer.harnesses.can_harness import CANHarness
            from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
            from iot_protocol_fuzzer.harnesses.spi_harness import SPIHarness
            from iot_protocol_fuzzer.monitoring.monitor import Monitor
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
            
            # Create monitor and logger
            self.monitor = Monitor()
            logger_backend = TestLogger()
            
            # Create campaign config
            campaign_config = CampaignConfig(
                iterations=self.campaign_config.get('iterations_total', 1000),
                delay=self.campaign_config.get('delay', 0.1),
                save_crashes=True
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
            self.orchestrator.run()
        except Exception as e:
            logger.error(f"Error during fuzzing campaign: {e}")
        finally:
            self.is_running = False
    
    def stop(self):
        """Stop fuzzing campaign"""
        if self.orchestrator:
            self.is_running = False
            # Note: The real orchestrator doesn't have a stop method,
            # so we just set the flag. The campaign will finish naturally.
            logger.info("Real orchestrator stop requested")
        elif self.fuzzer_instance:
            self.fuzzer_instance.stop()
            self.is_running = False
            logger.info("Mock orchestrator stopped")
    
    def pause(self):
        """Pause fuzzing campaign"""
        if self.orchestrator:
            # Real orchestrator doesn't have pause/resume
            logger.info("Real orchestrator pause requested (not implemented)")
        elif self.fuzzer_instance:
            self.fuzzer_instance.pause()
            logger.info("Mock orchestrator paused")
    
    def reset(self):
        """Reset fuzzing campaign"""
        if self.orchestrator:
            logger.info("Real orchestrator reset requested (not implemented)")
        elif self.fuzzer_instance:
            self.fuzzer_instance.reset()
            logger.info("Mock orchestrator reset")
    
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
            # Import real monitor component
            from iot_protocol_fuzzer.monitoring.monitor import Monitor
            
            logger.info("Initializing real monitor components")
            self.real_monitor = Monitor()
            
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