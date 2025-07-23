import logging
import time
from typing import Dict, Any, Optional, Iterable

from ..generators.base import DataGenerator
from ..harnesses.base import ProtocolHarness, HarnessResult
from ..monitoring.monitor import Monitor
from ..analysis.logger import TestLogger
from .config import CampaignConfig, EventType

logger = logging.getLogger("fuzzer.orchestrator")


class Orchestrator:
    """Single-threaded orchestrator that wires generator → harness → monitor."""

    def __init__(
        self,
        generator: DataGenerator,
        harness: ProtocolHarness,
        monitor: Optional[Monitor] = None,
        logger_backend: Optional[TestLogger] = None,
        config: Optional[CampaignConfig] = None,
    ) -> None:
        self.generator = generator
        self.harness = harness
        self.monitor = monitor or Monitor()
        self.logger_backend = logger_backend or TestLogger()
        self.config = config or CampaignConfig()
        
        # Campaign control
        self._is_running = False
        self._is_paused = False
        self._should_stop = False
        self._current_iteration = 0
        
        # Protocol information for enhanced events
        self._protocol_type = self._detect_protocol_type()
        self._test_groups = self._initialize_test_groups()
        self._base_seeds = None

    def _detect_protocol_type(self) -> str:
        """Detect the protocol type based on the harness"""
        harness_class = self.harness.__class__.__name__
        
        if 'CAN' in harness_class.upper():
            return 'CAN'
        elif 'UART' in harness_class.upper():
            return 'UART'
        elif 'SPI' in harness_class.upper():
            return 'SPI'
        elif 'I2C' in harness_class.upper():
            return 'I2C'
        elif 'ETHERNET' in harness_class.upper():
            return 'Ethernet'
        elif 'DOIP' in harness_class.upper():
            return 'DoIP'
        else:
            return 'Generic'

    def _initialize_test_groups(self) -> Dict[str, Dict[str, Any]]:
        """Initialize test groups based on protocol type"""
        protocol_groups = {
            'CAN': {
                'group-can-general': {
                    'sid': 'CAN',
                    'name': 'CAN Bus Testing',
                    'icon': '🚗',
                    'protocol': 'CAN',
                    'description': 'Controller Area Network fuzzing tests'
                }
            },
            'UART': {
                'group-uart-general': {
                    'sid': 'UART',
                    'name': 'UART/Serial Testing',
                    'icon': '📡',
                    'protocol': 'UART',
                    'description': 'Universal Asynchronous Receiver/Transmitter fuzzing tests'
                }
            },
            'UDS': {
                'group-0x10': {
                    'sid': '0x10',
                    'name': 'Diagnostic Session Control',
                    'icon': '📋',
                    'protocol': 'UDS',
                    'description': 'UDS Diagnostic Session Control service'
                },
                'group-0x11': {
                    'sid': '0x11',
                    'name': 'ECU Reset',
                    'icon': '🔄',
                    'protocol': 'UDS',
                    'description': 'UDS ECU Reset service'
                },
                'group-0x22': {
                    'sid': '0x22',
                    'name': 'Read Data By Identifier',
                    'icon': '📖',
                    'protocol': 'UDS',
                    'description': 'UDS Read Data By Identifier service'
                },
                'group-0x27': {
                    'sid': '0x27',
                    'name': 'Security Access',
                    'icon': '🔒',
                    'protocol': 'UDS',
                    'description': 'UDS Security Access service'
                }
            },
            'Generic': {
                'group-general': {
                    'sid': 'GEN',
                    'name': 'General Protocol Testing',
                    'icon': '🔧',
                    'protocol': 'Generic',
                    'description': 'General protocol fuzzing tests'
                }
            }
        }
        
        return protocol_groups.get(self._protocol_type, protocol_groups['Generic'])

    def _get_test_group_for_payload(self, payload: bytes) -> Dict[str, Any]:
        """Determine which test group this payload belongs to"""
        if self._protocol_type == 'UDS' and len(payload) > 0:
            # For UDS, try to extract service ID from payload
            service_id = payload[0]
            service_hex = f"0x{service_id:02X}"
            
            # Check if we have a specific group for this service
            group_key = f"group-{service_hex}"
            if group_key in self._test_groups:
                return self._test_groups[group_key]
        
        # Default to first available group
        return list(self._test_groups.values())[0]

    def _extract_protocol_frame_info(self, payload: bytes, test_case_id: int) -> Dict[str, Any]:
        """Extract protocol frame information from payload"""
        payload_hex = payload.hex().upper()
        
        if self._protocol_type == 'CAN':
            # For CAN, assume first 4 bytes are CAN ID if available
            if len(payload) >= 4:
                can_id = f"0x{payload[:4].hex().upper()}"
                data_bytes = payload[4:].hex().upper()
                return {
                    'name': f'CAN Frame {test_case_id}',
                    'subFunction': can_id,
                    'payload': data_bytes,
                    'description': f'CAN frame with ID {can_id}',
                    'protocol_frame': f'ID: {can_id} | Data: {data_bytes}'
                }
            else:
                return {
                    'name': f'CAN Frame {test_case_id}',
                    'subFunction': '0x123',
                    'payload': payload_hex,
                    'description': f'CAN frame with {len(payload)} bytes',
                    'protocol_frame': f'ID: 0x123 | Data: {payload_hex}'
                }
        
        elif self._protocol_type == 'UART':
            # For UART, check if it's AT command or binary data
            try:
                payload_str = payload.decode('ascii')
                if payload_str.startswith('AT'):
                    return {
                        'name': f'AT Command {test_case_id}',
                        'subFunction': 'AT',
                        'payload': payload_hex,
                        'description': f'AT command: {payload_str.strip()}',
                        'protocol_frame': f'Command: {payload_str.strip()}'
                    }
            except UnicodeDecodeError:
                pass
            
            return {
                'name': f'UART Data {test_case_id}',
                'subFunction': 'DATA',
                'payload': payload_hex,
                'description': f'UART data packet ({len(payload)} bytes)',
                'protocol_frame': f'Data: {payload_hex}'
            }
        
        elif self._protocol_type == 'UDS' and len(payload) > 0:
            # For UDS, extract service ID and sub-function
            service_id = f"0x{payload[0]:02X}"
            sub_function = f"0x{payload[1]:02X}" if len(payload) > 1 else "0x00"
            data_bytes = payload[2:].hex().upper() if len(payload) > 2 else ""
            
            # Map common UDS service IDs to names
            service_names = {
                '0x10': 'Diagnostic Session Control',
                '0x11': 'ECU Reset',
                '0x22': 'Read Data By Identifier',
                '0x27': 'Security Access',
                '0x28': 'Communication Control',
                '0x2E': 'Write Data By Identifier',
                '0x31': 'Routine Control',
                '0x34': 'Request Download',
                '0x36': 'Transfer Data',
                '0x37': 'Request Transfer Exit'
            }
            
            service_name = service_names.get(service_id, f'Service {service_id}')
            
            return {
                'name': f'{service_name} {test_case_id}',
                'subFunction': sub_function,
                'payload': data_bytes,
                'description': f'UDS {service_name} with sub-function {sub_function}',
                'protocol_frame': f'SID: {service_id} | Sub: {sub_function} | Data: {data_bytes}'
            }
        
        else:
            # Generic protocol handling
            return {
                'name': f'{self._protocol_type} Test {test_case_id}',
                'subFunction': payload_hex[:4] if len(payload_hex) >= 4 else '0x00',
                'payload': payload_hex[4:] if len(payload_hex) > 4 else payload_hex,
                'description': f'{self._protocol_type} protocol test case',
                'protocol_frame': f'Data: {payload_hex}'
            }

    def _emit_event(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event via the callback if configured"""
        if self.config.event_callback:
            event_data = data or {}
            event_data.update({
                'event_type': event_type.value,
                'timestamp': time.time(),
                'current_iteration': self._current_iteration,
                'total_iterations': self.config.iterations,
            })
            
            try:
                self.config.event_callback(event_type, event_data)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

    def run(self) -> None:
        """Run the fuzzing campaign with real-time event emission"""
        logger.info("Starting fuzzing campaign: %s iterations", self.config.iterations)
        self._is_running = True
        self._should_stop = False
        
        # Get base seeds for reference
        self._base_seeds = list(self.generator.seed_corpus())
        
        # Emit campaign started event
        self._emit_event(EventType.CAMPAIGN_STARTED, {
            'total_iterations': self.config.iterations,
            'protocol_type': self._protocol_type,
            'test_groups': self._test_groups,
            'config': {
                'delay': self.config.delay,
                'save_crashes': self.config.save_crashes,
            }
        })
        
        seeds: Iterable[bytes] = self.generator.seed_corpus()
        corpus_iter = self.generator.generate(seeds, self.config.iterations)

        try:
            for idx, payload in enumerate(corpus_iter, 1):
                if self._should_stop:
                    break
                
                # Handle pause
                while self._is_paused and not self._should_stop:
                    time.sleep(0.1)
                
                if self._should_stop:
                    break
                
                self._current_iteration = idx
                
                # Extract protocol frame information
                frame_info = self._extract_protocol_frame_info(payload, idx)
                test_group = self._get_test_group_for_payload(payload)
                
                # Emit test case started event with enhanced information
                self._emit_event(EventType.TEST_CASE_STARTED, {
                    'test_case_id': idx,
                    'payload_size': len(payload),
                    'payload_hex': payload.hex().upper(),
                    'protocol_type': self._protocol_type,
                    'test_group': test_group,
                    'frame_info': frame_info,
                    # Additional fields expected by Flutter table
                    'name': frame_info['name'],
                    'subFunction': frame_info['subFunction'],
                    'payload': frame_info['payload'],
                    'description': frame_info['description'],
                    'protocol_frame': frame_info['protocol_frame'],
                    'status': 'running',
                    'iterations': 1,
                    'progress': 0,
                    'pass': 0,
                    'fail': 0,
                    'check': 0
                })
                
                logger.debug("[Case %d] sending %d bytes", idx, len(payload))

                result: HarnessResult = self.harness.execute(payload)
                self.logger_backend.record(idx, payload, result)
                self.monitor.process_case(idx, payload, result)

                # Determine result status
                if result.crashed:
                    status = 'fail'
                    pass_count = 0
                    fail_count = 1
                    check_count = 0
                elif result.timeout:
                    status = 'check'
                    pass_count = 0
                    fail_count = 0
                    check_count = 1
                elif result.error:
                    status = 'fail'
                    pass_count = 0
                    fail_count = 1
                    check_count = 0
                else:
                    status = 'pass'
                    pass_count = 1
                    fail_count = 0
                    check_count = 0

                # Emit test case completed event with enhanced information
                self._emit_event(EventType.TEST_CASE_COMPLETED, {
                    'test_case_id': idx,
                    'protocol_type': self._protocol_type,
                    'test_group': test_group,
                    'frame_info': frame_info,
                    # Additional fields expected by Flutter table
                    'name': frame_info['name'],
                    'subFunction': frame_info['subFunction'],
                    'payload': frame_info['payload'],
                    'description': frame_info['description'],
                    'protocol_frame': frame_info['protocol_frame'],
                    'status': status,
                    'iterations': 1,
                    'progress': 100,
                    'pass': pass_count,
                    'fail': fail_count,
                    'check': check_count,
                    'result': {
                        'ok': result.ok,
                        'crashed': result.crashed,
                        'timeout': result.timeout,
                        'error': result.error,
                        'response': result.response.hex().upper() if result.response else None,
                        'info': result.info if hasattr(result, 'info') else None
                    }
                })

                if result.crashed and self.config.save_crashes:
                    self.logger_backend.save_crash(idx, payload, result)
                    
                    # Emit crash detected event with enhanced information
                    self._emit_event(EventType.CRASH_DETECTED, {
                        'test_case_id': idx,
                        'payload_size': len(payload),
                        'payload_hex': payload.hex().upper(),
                        'protocol_type': self._protocol_type,
                        'frame_info': frame_info,
                        'crash_info': result.info if hasattr(result, 'info') else 'Crash detected',
                    })

                # Emit statistics update every 10 iterations or on crashes
                if idx % 10 == 0 or result.crashed:
                    stats = self.monitor.get_stats()
                    self._emit_event(EventType.STATISTICS_UPDATE, {
                        'statistics': stats,
                        'protocol_type': self._protocol_type,
                    })

                # Emit progress update
                progress_percent = (idx / self.config.iterations) * 100
                self._emit_event(EventType.PROGRESS_UPDATE, {
                    'progress_percent': progress_percent,
                    'completed_iterations': idx,
                    'protocol_type': self._protocol_type,
                })

                if self.config.delay:
                    time.sleep(self.config.delay)

        except Exception as e:
            logger.error(f"Error during fuzzing campaign: {e}")
            self._emit_event(EventType.CAMPAIGN_STOPPED, {
                'error': str(e),
                'completed_iterations': self._current_iteration,
                'protocol_type': self._protocol_type,
            })
            raise
        finally:
            self._is_running = False

        # Post-campaign summary
        final_stats = self.monitor.get_stats()
        logger.info(f"Campaign completed: {final_stats}")
        
        # Emit campaign completed event
        self._emit_event(EventType.CAMPAIGN_COMPLETED, {
            'final_stats': final_stats,
            'total_iterations': self.config.iterations,
            'protocol_type': self._protocol_type,
        })

    def pause(self) -> None:
        """Pause the fuzzing campaign"""
        self._is_paused = True
        self._emit_event(EventType.CAMPAIGN_PAUSED, {
            'completed_iterations': self._current_iteration,
            'protocol_type': self._protocol_type,
        })

    def resume(self) -> None:
        """Resume the fuzzing campaign"""
        self._is_paused = False
        self._emit_event(EventType.CAMPAIGN_RESUMED, {
            'completed_iterations': self._current_iteration,
            'protocol_type': self._protocol_type,
        })

    def stop(self) -> None:
        """Stop the fuzzing campaign"""
        self._should_stop = True
        self._emit_event(EventType.CAMPAIGN_STOPPED, {
            'completed_iterations': self._current_iteration,
            'protocol_type': self._protocol_type,
        })

    def is_running(self) -> bool:
        """Check if the campaign is running"""
        return self._is_running

    def is_paused(self) -> bool:
        """Check if the campaign is paused"""
        return self._is_paused

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current campaign statistics"""
        stats = self.monitor.get_stats()
        return {
            'current_iteration': self._current_iteration,
            'total_iterations': self.config.iterations,
            'progress_percent': (self._current_iteration / self.config.iterations) * 100 if self.config.iterations > 0 else 0,
            'is_running': self._is_running,
            'is_paused': self._is_paused,
            'protocol_type': self._protocol_type,
            **stats
        } 