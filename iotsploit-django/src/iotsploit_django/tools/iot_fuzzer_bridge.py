import logging
import threading
from typing import Dict, Any, List, Callable
from datetime import datetime
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

class IoTFuzzerBridge:
    """
    IoT Fuzzer Bridge - Event bridge system for converting fuzzer events to Django events
    Handles WebSocket communication and event propagation
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of IoTFuzzerBridge"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the IoT Fuzzer Bridge"""
        if IoTFuzzerBridge._instance is not None:
            raise Exception("This class is a singleton!")
        
        self.campaign_bridges: Dict[str, 'CampaignBridge'] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.channel_layer = get_channel_layer()
        
        # Initialize event handlers
        self._initialize_event_handlers()
        
        logger.info("IoT Fuzzer Bridge initialized")
    
    def initialize_campaign_bridge(self, campaign_id: str) -> 'CampaignBridge':
        """
        Initialize event bridge for a specific campaign
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            CampaignBridge: Campaign-specific bridge instance
        """
        try:
            campaign_bridge = CampaignBridge(campaign_id, self)
            self.campaign_bridges[campaign_id] = campaign_bridge
            
            logger.info(f"Campaign bridge initialized for {campaign_id}")
            return campaign_bridge
            
        except Exception as e:
            logger.error(f"Error initializing campaign bridge: {str(e)}")
            raise
    
    def cleanup_campaign_bridge(self, campaign_id: str) -> None:
        """
        Cleanup event bridge for a specific campaign
        
        Args:
            campaign_id: Campaign ID
        """
        try:
            if campaign_id in self.campaign_bridges:
                campaign_bridge = self.campaign_bridges[campaign_id]
                campaign_bridge.cleanup()
                del self.campaign_bridges[campaign_id]
                
                logger.info(f"Campaign bridge cleaned up for {campaign_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up campaign bridge: {str(e)}")
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """
        Register an event handler for a specific event type
        
        Args:
            event_type: Type of event to handle
            handler: Handler function
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        
        self.event_handlers[event_type].append(handler)
        logger.info(f"Event handler registered for {event_type}")
    
    def emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Emit an event to all registered handlers
        
        Args:
            event_type: Type of event
            event_data: Event data
        """
        try:
            # Add timestamp
            event_data['timestamp'] = datetime.now().isoformat()
            
            # Normalize statistics payload to AFL++ schema when needed
            try:
                if event_type == 'statistics_update' and isinstance(event_data, dict):
                    stats = event_data.get('statistics')
                    if isinstance(stats, dict):
                        ui_stats = {
                            'execs_done': int(stats.get('execs_done', 0)),
                            'execs_per_sec': float(stats.get('execs_per_sec', 0.0)),
                            'execs_ps_last_min': float(stats.get('execs_ps_last_min', 0.0)),
                            'cycles_done': int(stats.get('cycles_done', 0)),
                            'cycles_wo_finds': int(stats.get('cycles_wo_finds', 0)),
                            'time_wo_finds': int(stats.get('time_wo_finds', 0)),
                            'corpus_count': int(stats.get('corpus_count', 0)),
                            'corpus_favored': int(stats.get('corpus_favored', 0)),
                            'corpus_found': int(stats.get('corpus_found', 0)),
                            'pending_total': int(stats.get('pending_total', 0)),
                            'pending_favs': int(stats.get('pending_favs', 0)),
                            'bitmap_cvg': float(stats.get('bitmap_cvg', 0.0)),
                            'stability': float(stats.get('stability', 0.0)),
                            'saved_crashes': int(stats.get('saved_crashes', 0)),
                            'saved_hangs': int(stats.get('saved_hangs', 0)),
                            'total_tmout': int(stats.get('total_tmout', 0)),
                            'run_time': int(stats.get('run_time', 0)),
                            'fuzz_time': int(stats.get('fuzz_time', 0)),
                            'last_update': int(stats.get('last_update', 0)),
                        }
                        # Warn if keys missing
                        missing = [k for k in ui_stats.keys() if k not in stats]
                        if missing:
                            logger.warning(
                                "[WS.statistics_update] Missing keys in stats: %s", missing
                            )
                        event_data['statistics'] = ui_stats
            except Exception as e:
                logger.error(f"Error normalizing statistics event: {e}")

            # Call registered handlers
            if event_type in self.event_handlers:
                for handler in self.event_handlers[event_type]:
                    try:
                        handler(event_data)
                    except Exception as e:
                        logger.error(f"Error in event handler: {str(e)}")
            
            # Broadcast to WebSocket consumers
            self._broadcast_to_websocket(event_type, event_data)
            
        except Exception as e:
            logger.error(f"Error emitting event: {str(e)}")
    
    def _initialize_event_handlers(self) -> None:
        """Initialize default event handlers"""
        # Register default handlers
        self.register_event_handler('campaign_status', self._handle_campaign_status)
        self.register_event_handler('test_result', self._handle_test_result)
        self.register_event_handler('crash_detected', self._handle_crash_detected)
        self.register_event_handler('log_message', self._handle_log_message)
        self.register_event_handler('statistics_update', self._handle_statistics_update)
    
    def _handle_campaign_status(self, event_data: Dict[str, Any]) -> None:
        """Handle campaign status events"""
        logger.info(f"Campaign status event: {event_data}")
        # Additional processing can be added here
    
    def _handle_test_result(self, event_data: Dict[str, Any]) -> None:
        """Handle test result events"""
        logger.info(f"Test result event: {event_data}")
        # Additional processing can be added here
    
    def _handle_crash_detected(self, event_data: Dict[str, Any]) -> None:
        """Handle crash detection events"""
        logger.warning(f"Crash detected: {event_data}")
        # Additional processing can be added here
    
    def _handle_log_message(self, event_data: Dict[str, Any]) -> None:
        """Handle log message events"""
        logger.info(f"Log message: {event_data}")
        # Additional processing can be added here
    
    def _handle_statistics_update(self, event_data: Dict[str, Any]) -> None:
        """Handle statistics update events"""
        logger.info(f"Statistics update: {event_data}")
        # Additional processing can be added here
    
    def _broadcast_to_websocket(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Broadcast event to WebSocket consumers
        
        Args:
            event_type: Type of event
            event_data: Event data
        """
        try:
            if self.channel_layer:
                campaign_id = event_data.get('campaign_id')
                
                # Broadcast to campaign-specific group
                if campaign_id:
                    group_name = f"iot_fuzzer_campaign_{campaign_id}"
                    message = {
                        'type': 'fuzzer_event',
                        'event_type': event_type,
                        'data': event_data
                    }
                    
                    async_to_sync(self.channel_layer.group_send)(group_name, message)
                
                # Broadcast to general IoT fuzzer group
                general_group = "iot_fuzzer_general"
                message = {
                    'type': 'fuzzer_event',
                    'event_type': event_type,
                    'data': event_data
                }
                
                async_to_sync(self.channel_layer.group_send)(general_group, message)
                
        except Exception as e:
            logger.error(f"Error broadcasting to WebSocket: {str(e)}")


class CampaignBridge:
    """
    Campaign-specific event bridge
    """
    
    def __init__(self, campaign_id: str, main_bridge: IoTFuzzerBridge):
        """
        Initialize campaign bridge
        
        Args:
            campaign_id: Campaign ID
            main_bridge: Main bridge instance
        """
        self.campaign_id = campaign_id
        self.main_bridge = main_bridge
        self.status_bridge = CampaignStatusBridge(campaign_id, main_bridge)
        self.result_bridge = ResultEventBridge(campaign_id, main_bridge)
        self.log_bridge = LogEventBridge(campaign_id, main_bridge)
        
        logger.info(f"Campaign bridge created for {campaign_id}")
    
    def emit_status_update(self, status_data: Dict[str, Any]) -> None:
        """
        Emit campaign status update
        
        Args:
            status_data: Status data
        """
        self.status_bridge.emit_status_update(status_data)
    
    def emit_test_result(self, result_data: Dict[str, Any]) -> None:
        """
        Emit test result
        
        Args:
            result_data: Test result data
        """
        self.result_bridge.emit_test_result(result_data)
    
    def emit_log_message(self, log_data: Dict[str, Any]) -> None:
        """
        Emit log message
        
        Args:
            log_data: Log data
        """
        self.log_bridge.emit_log_message(log_data)
    
    def emit_crash_alert(self, crash_data: Dict[str, Any]) -> None:
        """
        Emit crash alert
        
        Args:
            crash_data: Crash data
        """
        crash_event = {
            'campaign_id': self.campaign_id,
            'crash_type': crash_data.get('crash_type', 'unknown'),
            'crash_info': crash_data.get('crash_info', ''),
            'test_case_id': crash_data.get('test_case_id'),
            'payload': crash_data.get('payload', ''),
            'severity': crash_data.get('severity', 'high')
        }
        
        self.main_bridge.emit_event('crash_detected', crash_event)
    
    def emit_statistics_update(self, stats_data: Dict[str, Any]) -> None:
        """
        Emit statistics update
        
        Args:
            stats_data: Statistics data
        """
        # Strict schema: require fixed keys; warn if missing; fill zeros for missing to keep schema
        try:
            expected_keys = [
                'total_iterations',
                'total_exec',
                'total_pass',
                'total_fail',
                'total_check',
                'speed',
                'test_time_seconds',
                'running_time_seconds',
                'estimated_time_seconds',
            ]
            # Start with zeros or existing fixed keys
            ui_stats = {k: stats_data.get(k, 0) for k in expected_keys}

            # Deterministic remap from legacy WS keys (no多方案容错，仅按已知键映射)
            if 'successes' in stats_data:
                ui_stats['total_pass'] = int(stats_data['successes'] or 0)
            if 'crashes' in stats_data or 'timeouts' in stats_data or 'errors' in stats_data:
                crashes = int(stats_data.get('crashes', 0) or 0)
                timeouts = int(stats_data.get('timeouts', 0) or 0)
                errors = int(stats_data.get('errors', 0) or 0)
                ui_stats['total_fail'] = crashes + timeouts + errors
            if 'total_cases' in stats_data:
                ui_stats['total_exec'] = int(stats_data['total_cases'] or 0)
            # total_check 暂无明确来源，保持默认或已有值

            # Warn if still missing required keys
            missing = [k for k in expected_keys if k not in stats_data and ui_stats.get(k, 0) == 0]
            if missing:
                logger.warning(
                    "[WS.statistics_update] filled defaults for keys=%s; available_keys=%s",
                    missing,
                    list(stats_data.keys())
                )
            # keep optional total_cases
            if 'total_cases' in stats_data:
                ui_stats['total_cases'] = int(stats_data['total_cases'] or 0)
        except Exception as e:
            logger.error(f"Error normalizing statistics payload: {e}")
            ui_stats = stats_data

        stats_event = {
            'campaign_id': self.campaign_id,
            'statistics': ui_stats
        }
        
        self.main_bridge.emit_event('statistics_update', stats_event)
    
    def cleanup(self) -> None:
        """Cleanup campaign bridge"""
        self.status_bridge.cleanup()
        self.result_bridge.cleanup()
        self.log_bridge.cleanup()
        
        logger.info(f"Campaign bridge cleaned up for {self.campaign_id}")


class CampaignStatusBridge:
    """
    Campaign status event bridge
    """
    
    def __init__(self, campaign_id: str, main_bridge: IoTFuzzerBridge):
        """
        Initialize campaign status bridge
        
        Args:
            campaign_id: Campaign ID
            main_bridge: Main bridge instance
        """
        self.campaign_id = campaign_id
        self.main_bridge = main_bridge
        self.last_status = {}
    
    def emit_status_update(self, status_data: Dict[str, Any]) -> None:
        """
        Emit campaign status update
        
        Args:
            status_data: Status data
        """
        # Only emit if status has changed
        if status_data != self.last_status:
            status_event = {
                'campaign_id': self.campaign_id,
                'status': status_data.get('status', 'unknown'),
                'progress': status_data.get('progress', 0),
                'iterations_completed': status_data.get('iterations_completed', 0),
                'iterations_total': status_data.get('iterations_total', 0),
                'crashes_found': status_data.get('crashes_found', 0),
                'timeouts_occurred': status_data.get('timeouts_occurred', 0),
                'errors_encountered': status_data.get('errors_encountered', 0)
            }
            
            self.main_bridge.emit_event('campaign_status', status_event)
            self.last_status = status_data.copy()
    
    def cleanup(self) -> None:
        """Cleanup status bridge"""
        self.last_status = {}


class ResultEventBridge:
    """
    Test result event bridge
    """
    
    def __init__(self, campaign_id: str, main_bridge: IoTFuzzerBridge):
        """
        Initialize result event bridge
        
        Args:
            campaign_id: Campaign ID
            main_bridge: Main bridge instance
        """
        self.campaign_id = campaign_id
        self.main_bridge = main_bridge
        self.result_count = 0
    
    def emit_test_result(self, result_data: Dict[str, Any]) -> None:
        """
        Emit test result
        
        Args:
            result_data: Test result data
        """
        self.result_count += 1
        
        result_event = {
            'campaign_id': self.campaign_id,
            'result_id': self.result_count,
            'test_case_id': result_data.get('test_case_id'),
            'iteration_number': result_data.get('iteration_number', 0),
            'status': result_data.get('status', 'unknown'),
            'payload': result_data.get('payload', ''),
            'response': result_data.get('response', ''),
            'response_time': result_data.get('response_time', 0.0),
            'crashed': result_data.get('crashed', False),
            'timeout': result_data.get('timeout', False),
            'error': result_data.get('error', False)
        }
        
        self.main_bridge.emit_event('test_result', result_event)
    
    def cleanup(self) -> None:
        """Cleanup result bridge"""
        self.result_count = 0


class LogEventBridge:
    """
    Log event bridge
    """
    
    def __init__(self, campaign_id: str, main_bridge: IoTFuzzerBridge):
        """
        Initialize log event bridge
        
        Args:
            campaign_id: Campaign ID
            main_bridge: Main bridge instance
        """
        self.campaign_id = campaign_id
        self.main_bridge = main_bridge
        self.log_buffer = []
        self.max_buffer_size = 1000
    
    def emit_log_message(self, log_data: Dict[str, Any]) -> None:
        """
        Emit log message
        
        Args:
            log_data: Log data
        """
        log_event = {
            'campaign_id': self.campaign_id,
            'log_level': log_data.get('log_level', 'info'),
            'message': log_data.get('message', ''),
            'category': log_data.get('category', 'general'),
            'source': log_data.get('source', 'fuzzer'),
            'extra_data': log_data.get('extra_data', {})
        }
        
        # Add to buffer
        self.log_buffer.append(log_event)
        
        # Maintain buffer size
        if len(self.log_buffer) > self.max_buffer_size:
            self.log_buffer.pop(0)
        
        self.main_bridge.emit_event('log_message', log_event)
    
    def get_log_buffer(self) -> List[Dict[str, Any]]:
        """
        Get current log buffer
        
        Returns:
            List[Dict]: Log messages
        """
        return self.log_buffer.copy()
    
    def clear_log_buffer(self) -> None:
        """Clear log buffer"""
        self.log_buffer.clear()
    
    def cleanup(self) -> None:
        """Cleanup log bridge"""
        self.log_buffer.clear()


class FuzzerEventHandler:
    """
    Generic fuzzer event handler
    """
    
    def __init__(self, bridge: IoTFuzzerBridge):
        """
        Initialize event handler
        
        Args:
            bridge: Bridge instance
        """
        self.bridge = bridge
    
    def handle_fuzzer_event(self, event_type: str, event_data: Any) -> None:
        """
        Handle fuzzer event
        
        Args:
            event_type: Type of event
            event_data: Event data
        """
        try:
            # Convert fuzzer event to Django event format
            django_event = self._convert_fuzzer_event(event_type, event_data)
            
            # Emit through bridge
            self.bridge.emit_event(event_type, django_event)
            
        except Exception as e:
            logger.error(f"Error handling fuzzer event: {str(e)}")
    
    def _convert_fuzzer_event(self, event_type: str, event_data: Any) -> Dict[str, Any]:
        """
        Convert fuzzer event to Django event format
        
        Args:
            event_type: Type of event
            event_data: Event data
            
        Returns:
            Dict: Django event format
        """
        # This is where we would convert from fuzzer-specific event format
        # to Django event format. For now, we'll assume it's already in dict format
        if isinstance(event_data, dict):
            return event_data
        else:
            return {'data': str(event_data)}


# Global instance
_instance = None 