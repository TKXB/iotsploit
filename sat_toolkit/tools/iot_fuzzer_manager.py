import logging
import threading
import time
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
import redis
from django.conf import settings
import json

logger = logging.getLogger(__name__)

class DependencyChecker:
    """Simple dependency checker for IoT Fuzzer components"""
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check if all required dependencies are available"""
        try:
            # Basic dependency checks
            import redis
            import json
            
            return {
                'status': True,
                'message': 'All dependencies available'
            }
        except ImportError as e:
            return {
                'status': False,
                'message': f'Missing dependency: {e}'
            }

class IoTFuzzerManager:
    """
    Main IoT Fuzzer Manager - Django service layer for managing fuzzing campaigns
    Uses Redis for cross-process state sharing between Django and Celery workers
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of IoTFuzzerManager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the IoT Fuzzer Manager"""
        if IoTFuzzerManager._instance is not None:
            raise Exception("This class is a singleton!")
        
        # In-memory storage for adapters (process-specific)
        self.orchestrator_adapters: Dict[str, Any] = {}
        self.monitor_adapters: Dict[str, Any] = {}
        self.protocol_adapter = None
        self.fuzzer_bridge = None
        
        # Initialize dependency checker
        self._dependency_checker = DependencyChecker()
        
        # Initialize Redis client using Django settings
        self._redis = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            db=getattr(settings, 'REDIS_DB', 0)
        )
        
        # Test Redis connection
        try:
            self._redis.ping()
            logger.info("IoT Fuzzer Manager initialized with Redis connection")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _get_protocol_adapter(self):
        """Lazy initialization of protocol adapter"""
        if self.protocol_adapter is None:
            from sat_toolkit.tools.iot_protocol_adapter import IoTProtocolAdapter
            self.protocol_adapter = IoTProtocolAdapter.get_instance()
        return self.protocol_adapter
    
    def _get_fuzzer_bridge(self):
        """Lazy initialization of fuzzer bridge"""
        if self.fuzzer_bridge is None:
            from sat_toolkit.tools.iot_fuzzer_bridge import IoTFuzzerBridge
            self.fuzzer_bridge = IoTFuzzerBridge.get_instance()
        return self.fuzzer_bridge

    def _get_campaign_key(self, campaign_id: str) -> str:
        """Get Redis key for campaign state"""
        return f"iot_fuzzer_campaign:{campaign_id}"
    
    def _get_active_campaigns_key(self) -> str:
        """Get Redis key for active campaigns set"""
        return "iot_fuzzer_active_campaigns"
    
    def _store_campaign_state(self, campaign_id: str, campaign_state: Dict[str, Any]) -> None:
        """Store campaign state in Redis with TTL"""
        campaign_key = self._get_campaign_key(campaign_id)
        
        # Convert datetime objects to ISO strings for JSON serialization
        serializable_state = campaign_state.copy()
        for key, value in serializable_state.items():
            if isinstance(value, datetime):
                serializable_state[key] = value.isoformat()
        
        # Store campaign state with 24-hour TTL
        self._redis.setex(campaign_key, 86400, json.dumps(serializable_state))
        
        # Add to active campaigns set
        self._redis.sadd(self._get_active_campaigns_key(), campaign_id)
        
        logger.debug(f"Stored campaign state for {campaign_id} in Redis")
    
    def _get_campaign_state(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get campaign state from Redis"""
        campaign_key = self._get_campaign_key(campaign_id)
        state_data = self._redis.get(campaign_key)
        
        if state_data:
            try:
                campaign_state = json.loads(state_data.decode('utf-8'))
                logger.debug(f"Retrieved campaign state for {campaign_id} from Redis")
                return campaign_state
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Failed to parse campaign state from Redis: {e}")
                return None
        else:
            logger.debug(f"No campaign state found for {campaign_id} in Redis")
            return None
    
    def _update_campaign_state(self, campaign_id: str, updates: Dict[str, Any]) -> None:
        """Update specific fields in campaign state"""
        campaign_state = self._get_campaign_state(campaign_id)
        if campaign_state:
            campaign_state.update(updates)
            self._store_campaign_state(campaign_id, campaign_state)
        else:
            logger.warning(f"Attempted to update non-existent campaign {campaign_id}")
    
    def _remove_campaign_state(self, campaign_id: str) -> None:
        """Remove campaign state from Redis"""
        campaign_key = self._get_campaign_key(campaign_id)
        
        # Remove campaign state
        self._redis.delete(campaign_key)
        
        # Remove from active campaigns set
        self._redis.srem(self._get_active_campaigns_key(), campaign_id)
        
        logger.debug(f"Removed campaign state for {campaign_id} from Redis")
    
    def get_active_campaigns(self) -> List[str]:
        """Get list of active campaign IDs"""
        return [campaign_id.decode('utf-8') for campaign_id in self._redis.smembers(self._get_active_campaigns_key())]

    def start_campaign(self, campaign_config: Dict[str, Any]) -> str:
        """
        Start a new fuzzing campaign
        
        Args:
            campaign_config: Campaign configuration dictionary
            
        Returns:
            str: Campaign ID
        """
        campaign_id = None
        try:
            # Validate configuration
            self._validate_campaign_config(campaign_config)
            
            # Check dependencies
            dependency_check = self._dependency_checker.check_dependencies()
            if not dependency_check['status']:
                raise Exception(f"Dependency check failed: {dependency_check['message']}")
            
            # Generate campaign ID
            campaign_id = str(uuid.uuid4())
            
            # Initialize campaign state
            campaign_state = {
                'id': campaign_id,
                'config': campaign_config,
                'status': 'starting',
                'created_at': datetime.now().isoformat(),
                'started_at': None,
                'iterations_total': campaign_config.get('iterations_total', 1000),
                'iterations_completed': 0,
                'crashes_found': 0,
                'timeouts_occurred': 0,
                'errors_encountered': 0
            }
            
            # Store campaign state in Redis
            self._store_campaign_state(campaign_id, campaign_state)
            
            # Create adapter instances
            protocol_adapter = self._get_protocol_adapter()
            
            # Add campaign_id to config for event emission
            campaign_config_with_id = campaign_config.copy()
            campaign_config_with_id['campaign_id'] = campaign_id
            
            orchestrator_adapter = protocol_adapter.create_orchestrator_adapter(campaign_config_with_id)
            monitor_adapter = protocol_adapter.create_monitor_adapter(campaign_config_with_id)
            
            # Store adapters in memory for this process
            self.orchestrator_adapters[campaign_id] = orchestrator_adapter
            self.monitor_adapters[campaign_id] = monitor_adapter
            
            # Initialize event bridge for this campaign
            fuzzer_bridge = self._get_fuzzer_bridge()
            fuzzer_bridge.initialize_campaign_bridge(campaign_id)
            
            # Start background campaign task
            self._start_campaign_task(campaign_id)
            
            # Update campaign state to running
            self._update_campaign_state(campaign_id, {
                'status': 'running',
                'started_at': datetime.now().isoformat()
            })
            
            logger.info(f"Campaign {campaign_id} started successfully")
            return campaign_id
            
        except Exception as e:
            logger.error(f"Error starting campaign: {str(e)}")
            # Cleanup on error
            if campaign_id is not None:
                self._remove_campaign_state(campaign_id)
                if campaign_id in self.orchestrator_adapters:
                    del self.orchestrator_adapters[campaign_id]
                if campaign_id in self.monitor_adapters:
                    del self.monitor_adapters[campaign_id]
            raise
    
    def stop_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Stop a running fuzzing campaign
        
        Args:
            campaign_id: Campaign ID to stop
            
        Returns:
            Dict: Campaign final statistics
        """
        try:
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Stop via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.stop()
            
            # Cleanup resources
            self._cleanup_campaign_resources(campaign_id)
            
            # Update campaign state in Redis
            self._update_campaign_state(campaign_id, {
                'status': 'stopped',
                'completed_at': datetime.now().isoformat()
            })
            
            # Calculate final statistics
            final_stats = self._calculate_final_statistics_from_redis(campaign_id)
            
            logger.info(f"Campaign {campaign_id} stopped successfully")
            return final_stats
            
        except Exception as e:
            logger.error(f"Error stopping campaign {campaign_id}: {str(e)}")
            raise
    
    def pause_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Pause a running fuzzing campaign
        
        Args:
            campaign_id: Campaign ID to pause
            
        Returns:
            Dict: Campaign current state
        """
        try:
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Pause via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.pause()
            
            # Update campaign state in Redis
            self._update_campaign_state(campaign_id, {
                'status': 'paused',
                'paused_at': datetime.now().isoformat()
            })
            
            # Get updated state
            updated_state = self._get_campaign_state(campaign_id)
            
            logger.info(f"Campaign {campaign_id} paused successfully")
            return updated_state
            
        except Exception as e:
            logger.error(f"Error pausing campaign {campaign_id}: {str(e)}")
            raise
    
    def reset_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Reset a fuzzing campaign state
        
        Args:
            campaign_id: Campaign ID to reset
            
        Returns:
            Dict: Reset campaign state
        """
        try:
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Reset via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.reset()
            
            # Reset campaign counters in Redis
            self._update_campaign_state(campaign_id, {
                'iterations_completed': 0,
                'crashes_found': 0,
                'timeouts_occurred': 0,
                'errors_encountered': 0,
                'status': 'reset',
                'reset_at': datetime.now().isoformat()
            })
            
            # Get updated state
            updated_state = self._get_campaign_state(campaign_id)
            
            logger.info(f"Campaign {campaign_id} reset successfully")
            return updated_state
            
        except Exception as e:
            logger.error(f"Error resetting campaign {campaign_id}: {str(e)}")
            raise
    
    def get_campaign_status(self, campaign_id: str) -> Dict[str, Any]:
        """
        Get current campaign status
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            Dict: Campaign status and progress
        """
        try:
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Get real-time status from adapter
            realtime_status = {}
            if campaign_id in self.monitor_adapters:
                monitor_adapter = self.monitor_adapters[campaign_id]
                realtime_status = monitor_adapter.get_status()
            
            # Calculate progress percentage
            progress_percentage = 0.0
            if campaign_state.get('iterations_total', 0) > 0:
                progress_percentage = (campaign_state.get('iterations_completed', 0) / campaign_state['iterations_total']) * 100
            
            # Merge Redis state with adapter status
            combined_status = {
                **campaign_state,
                **realtime_status,
                'progress_percentage': progress_percentage
            }
            
            return combined_status
            
        except Exception as e:
            logger.error(f"Error getting campaign status {campaign_id}: {str(e)}")
            raise
    
    def get_campaign_statistics(self, campaign_id: str) -> Dict[str, Any]:
        """
        Get detailed campaign statistics
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            Dict: Detailed statistics
        """
        try:
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Get statistics from adapter
            statistics = {}
            if campaign_id in self.monitor_adapters:
                monitor_adapter = self.monitor_adapters[campaign_id]
                statistics = monitor_adapter.get_statistics()
            
            # Add calculated metrics from Redis state
            statistics.update({
                'campaign_duration': self._calculate_campaign_duration_from_state(campaign_state),
                'average_iterations_per_second': self._calculate_average_iterations_per_second_from_state(campaign_state),
                'crash_rate': self._calculate_crash_rate_from_state(campaign_state),
                'timeout_rate': self._calculate_timeout_rate_from_state(campaign_state)
            })
            
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting campaign statistics {campaign_id}: {str(e)}")
            raise
    
    def update_campaign_progress(self, campaign_id: str, progress_data: Dict[str, Any]) -> None:
        """
        Update campaign progress from Celery task
        
        Args:
            campaign_id: Campaign ID
            progress_data: Progress data to update
        """
        try:
            self._update_campaign_state(campaign_id, progress_data)
            logger.debug(f"Updated campaign progress for {campaign_id}: {progress_data}")
        except Exception as e:
            logger.error(f"Error updating campaign progress for {campaign_id}: {e}")
    
    def _validate_campaign_config(self, config: Dict[str, Any]) -> None:
        """Validate campaign configuration"""
        required_fields = ['protocol_type', 'protocol_config', 'generator_config']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
    
    def _start_campaign_task(self, campaign_id: str) -> None:
        """Start background task for campaign execution"""
        try:
            # Import here to avoid circular imports
            from sat_toolkit.tasks import run_fuzzing_campaign
            
            # Get campaign state from Redis
            campaign_state = self._get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            campaign_config = campaign_state['config']
            
            # Start the Celery task
            task = run_fuzzing_campaign.delay(campaign_id, campaign_config)
            
            # Store task ID in Redis
            self._update_campaign_state(campaign_id, {'task_id': task.id})
            
            logger.info(f"Started background task for campaign {campaign_id}: {task.id}")
            
        except Exception as e:
            logger.error(f"Error starting background task for campaign {campaign_id}: {str(e)}")
            # Fallback to mock implementation if Celery is not available
            logger.info(f"Using mock background task for campaign {campaign_id}")
            self._update_campaign_state(campaign_id, {'task_id': f"mock_{campaign_id}"})
    
    def _cleanup_campaign_resources(self, campaign_id: str) -> None:
        """Cleanup campaign resources"""
        try:
            # Cleanup adapters
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.cleanup()
                del self.orchestrator_adapters[campaign_id]
            
            if campaign_id in self.monitor_adapters:
                monitor_adapter = self.monitor_adapters[campaign_id]
                monitor_adapter.cleanup()
                del self.monitor_adapters[campaign_id]
            
            # Cleanup bridge
            fuzzer_bridge = self._get_fuzzer_bridge()
            fuzzer_bridge.cleanup_campaign_bridge(campaign_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up campaign resources: {str(e)}")
    
    def _calculate_final_statistics_from_redis(self, campaign_id: str) -> Dict[str, Any]:
        """Calculate final campaign statistics from Redis"""
        campaign_state = self._get_campaign_state(campaign_id)
        if not campaign_state:
            return {'campaign_id': campaign_id, 'error': 'Campaign not found'}
        
        return {
            'campaign_id': campaign_id,
            'total_iterations': campaign_state.get('iterations_completed', 0),
            'crashes_found': campaign_state.get('crashes_found', 0),
            'timeouts_occurred': campaign_state.get('timeouts_occurred', 0),
            'errors_encountered': campaign_state.get('errors_encountered', 0),
            'duration': self._calculate_campaign_duration_from_state(campaign_state)
        }
    
    def _calculate_campaign_duration_from_state(self, campaign_state: Dict[str, Any]) -> float:
        """Calculate campaign duration in seconds from state"""
        if not campaign_state.get('started_at'):
            return 0.0
        
        try:
            started_at = datetime.fromisoformat(campaign_state['started_at'])
            end_time = datetime.now()
            
            if campaign_state.get('completed_at'):
                end_time = datetime.fromisoformat(campaign_state['completed_at'])
            
            return (end_time - started_at).total_seconds()
        except (ValueError, TypeError):
            return 0.0
    
    def _calculate_average_iterations_per_second_from_state(self, campaign_state: Dict[str, Any]) -> float:
        """Calculate average iterations per second from state"""
        duration = self._calculate_campaign_duration_from_state(campaign_state)
        
        if duration == 0:
            return 0.0
        
        iterations_completed = campaign_state.get('iterations_completed', 0)
        return iterations_completed / duration
    
    def _calculate_crash_rate_from_state(self, campaign_state: Dict[str, Any]) -> float:
        """Calculate crash rate percentage from state"""
        iterations_completed = campaign_state.get('iterations_completed', 0)
        if iterations_completed == 0:
            return 0.0
        
        crashes_found = campaign_state.get('crashes_found', 0)
        return (crashes_found / iterations_completed) * 100
    
    def _calculate_timeout_rate_from_state(self, campaign_state: Dict[str, Any]) -> float:
        """Calculate timeout rate percentage from state"""
        iterations_completed = campaign_state.get('iterations_completed', 0)
        if iterations_completed == 0:
            return 0.0
        
        timeouts_occurred = campaign_state.get('timeouts_occurred', 0)
        return (timeouts_occurred / iterations_completed) * 100


class DependencyChecker:
    """
    Dependency checker for IoT Protocol Fuzzer requirements
    """
    
    def check_dependencies(self) -> Dict[str, Any]:
        """
        Check if all required dependencies are available
        
        Returns:
            Dict: Dependency check result
        """
        try:
            missing_deps = []
            warnings = []
            
            # Check for iot_protocol_fuzzer module
            try:
                import iot_protocol_fuzzer
                logger.info("iot_protocol_fuzzer module found")
            except ImportError:
                missing_deps.append("iot_protocol_fuzzer")
            
            # Check for required system packages
            system_packages = {
                'python-can': self._check_python_can,
                'pyserial': self._check_pyserial,
                'spidev': self._check_spidev
            }
            
            for package, checker in system_packages.items():
                if not checker():
                    warnings.append(f"Optional package {package} not available")
            
            # Check for radamsa binary
            if not self._check_radamsa():
                warnings.append("Radamsa binary not found - some generators may not work")
            
            if missing_deps:
                return {
                    'status': False,
                    'message': f"Missing required dependencies: {', '.join(missing_deps)}",
                    'missing_dependencies': missing_deps,
                    'warnings': warnings
                }
            
            return {
                'status': True,
                'message': "All dependencies available",
                'missing_dependencies': [],
                'warnings': warnings
            }
            
        except Exception as e:
            logger.error(f"Error checking dependencies: {str(e)}")
            return {
                'status': False,
                'message': f"Error checking dependencies: {str(e)}",
                'missing_dependencies': [],
                'warnings': []
            }
    
    def _check_python_can(self) -> bool:
        """Check if python-can is available"""
        try:
            import can
            return True
        except ImportError:
            return False
    
    def _check_pyserial(self) -> bool:
        """Check if pyserial is available"""
        try:
            import serial
            return True
        except ImportError:
            return False
    
    def _check_spidev(self) -> bool:
        """Check if spidev is available"""
        try:
            import spidev
            return True
        except ImportError:
            return False
    
    def _check_radamsa(self) -> bool:
        """Check if radamsa binary is available"""
        try:
            import subprocess
            result = subprocess.run(['which', 'radamsa'], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False


# Global instance
_instance = None 