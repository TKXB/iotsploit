import logging

from typing import Dict, Any
import time

from iotsploit_django.tools.iot_protocol_components import (
    MockGeneratorInstance,
    MockMonitorInstance,
    MockOrchestratorInstance,
)

logger = logging.getLogger(__name__)


class OrchestratorAdapter:
    """
    Adapter for iotsploit_fuzzer orchestrator component
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
            logger.warning("iotsploit_fuzzer not available, using mock implementation")
            self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)
            return

        try:
            # Import real fuzzer components
            from iotsploit_fuzzer.core.orchestrator import Orchestrator, CampaignConfig
            from iotsploit_fuzzer.generators.radamsa_generator import RadamsaGenerator
            from iotsploit_fuzzer.harnesses.can_harness import CANHarness
            from iotsploit_fuzzer.harnesses.uart_harness import UARTHarness
            from iotsploit_fuzzer.harnesses.spi_harness import SPIHarness
            from iotsploit_fuzzer.monitoring.monitor import create_monitor
            from iotsploit_fuzzer.analysis.logger import TestLogger

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
                from iotsploit_fuzzer.interfaces.can_interface import SocketCANInterface
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
                # Use the actual UARTInterface implementation
                from iotsploit_fuzzer.interfaces.uart_interface import UARTInterface
                # Accept multiple possible keys from the incoming config
                device = (
                    protocol_config.get('port')
                    or protocol_config.get('device')
                    or protocol_config.get('device_path')
                    or '/dev/ttyUSB0'
                )
                baudrate = protocol_config.get('baud_rate', 115200)
                timeout_ms = protocol_config.get('timeout', 1000)
                try:
                    timeout_s = float(timeout_ms) / 1000.0
                except Exception:
                    timeout_s = 0.1
                interface = UARTInterface(device=device, baudrate=baudrate, timeout=timeout_s)
                harness = UARTHarness(interface)
            elif protocol_type == 'spi':
                from iotsploit_fuzzer.interfaces.spi_interface import SPIInterface
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
            logger.warning(f"Failed to import fuzzer module: {e}, using mock implementation")
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
            from iotsploit_django.tools.iot_fuzzer_bridge import IoTFuzzerBridge

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
    Adapter for iotsploit_fuzzer monitor component
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
            logger.warning("iotsploit_fuzzer not available, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
            return

        try:
            # Import monitor factory
            from iotsploit_fuzzer.monitoring.monitor import create_monitor

            logger.info("Initializing real monitor components")
            # Determine protocol type from campaign config
            protocol_type = (self.campaign_config.get('protocol_config', {}) or {}).get('protocol_type')
            self.real_monitor = create_monitor(protocol_type, self.campaign_config.get('monitoring'))

        except ImportError as e:
            logger.warning(f"Failed to import iotsploit_fuzzer monitor: {e}, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)
        except Exception as e:
            logger.error(f"Error initializing monitor components: {e}, using mock implementation")
            self.monitor_instance = MockMonitorInstance(self.campaign_config)

    def get_status(self) -> Dict[str, Any]:
        """Get real-time campaign status (AFL++ aligned minimal fields)"""
        if self.real_monitor:
            stats = self.real_monitor.get_stats()
            return {
                'cycles_done': stats.get('current_iteration', 0) or 0,
                'execs_done': stats.get('total_cases', 0) or 0,
                'saved_crashes': stats.get('crash_count', 0) or 0,
                'is_running': getattr(self.orchestrator_adapter, 'is_running', False)
            }
        elif self.monitor_instance:
            status = self.monitor_instance.get_status()
            return {
                'cycles_done': status.get('current_iteration', 0) or 0,
                'execs_done':  status.get('current_iteration', 0) or 0,
                'saved_crashes': 0,
                'is_running': getattr(self.orchestrator_adapter, 'is_running', False)
            }
        return {
            'cycles_done': 0,
            'execs_done': 0,
            'saved_crashes': 0,
            'is_running': False
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed campaign statistics (AFL++ naming)"""
        if self.real_monitor:
            stats = self.real_monitor.get_stats()
            return {
                'execs_done': stats.get('total_cases', 0),
                'execs_per_sec': stats.get('cases_per_second', 0.0),
                'cycles_done': stats.get('current_iteration', 0),
                'corpus_count': stats.get('corpus_count', 0),
                'corpus_favored': stats.get('corpus_favored', 0),
                'corpus_found': stats.get('corpus_found', 0),
                'pending_total': stats.get('pending_total', 0),
                'pending_favs': stats.get('pending_favs', 0),
                'bitmap_cvg': stats.get('bitmap_cvg', 0.0),
                'saved_crashes': stats.get('crash_count', 0),
                'saved_hangs': stats.get('hang_count', 0),
                'total_tmout': stats.get('timeout_count', 0),
                'run_time': stats.get('run_time', 0),
            }
        elif self.monitor_instance:
            # Provide AFL++-aligned default/mocked statistics
            mock = self.monitor_instance.get_statistics()
            return {
                'execs_done': mock.get('total_iterations', 0),
                'execs_per_sec': 0.0,
                'cycles_done': mock.get('total_iterations', 0),
                'corpus_count': 0,
                'corpus_favored': 0,
                'corpus_found': 0,
                'pending_total': 0,
                'pending_favs': 0,
                'bitmap_cvg': 0.0,
                'saved_crashes': mock.get('crashes_detected', 0),
                'saved_hangs': 0,
                'total_tmout': mock.get('timeouts', 0),
                'run_time': 0,
            }
        return {
            'execs_done': 0,
            'execs_per_sec': 0.0,
            'cycles_done': 0,
            'corpus_count': 0,
            'corpus_favored': 0,
            'corpus_found': 0,
            'pending_total': 0,
            'pending_favs': 0,
            'bitmap_cvg': 0.0,
            'saved_crashes': 0,
            'saved_hangs': 0,
            'total_tmout': 0,
            'run_time': 0,
        }

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
    Adapter for iotsploit_fuzzer generator component
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
            logger.warning("iotsploit_fuzzer not available, using mock implementation")
            self.generator_instance = MockGeneratorInstance(self.generator_config)
            return

        try:
            # Import real generator component
            from iotsploit_fuzzer.generators.radamsa_generator import RadamsaGenerator

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
            logger.warning(f"Failed to import iotsploit_fuzzer generator: {e}, using mock implementation")
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
