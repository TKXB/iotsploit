import logging

from iotsploit_django.tools.frame_utils import frame_data_from_fields
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
import uuid
import importlib.util
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

_local_fuzzer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iotsploit-fuzzer")

class IoTFuzzerManager:
    """
    Main IoT Fuzzer Manager - Django service layer for managing fuzzing campaigns
    Uses the Django database for state shared by web and background workers.
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
        
        logger.info("IoT Fuzzer Manager initialized with database-backed state")
    
    def _get_protocol_adapter(self):
        """Lazy initialization of protocol adapter"""
        if self.protocol_adapter is None:
            from iotsploit_django.tools.iot_protocol_adapter import IoTProtocolAdapter
            self.protocol_adapter = IoTProtocolAdapter.get_instance()
        return self.protocol_adapter
    
    def _get_fuzzer_bridge(self):
        """Lazy initialization of fuzzer bridge"""
        if self.fuzzer_bridge is None:
            from iotsploit_django.tools.iot_fuzzer_bridge import IoTFuzzerBridge
            self.fuzzer_bridge = IoTFuzzerBridge.get_instance()
        return self.fuzzer_bridge

    @staticmethod
    def _campaign_model():
        from iotsploit_django.adapters.django.iot_fuzzer.models import FuzzingCampaign

        return FuzzingCampaign

    @staticmethod
    def _as_datetime(value):
        if not value or isinstance(value, datetime):
            return value
        return parse_datetime(value)

    def store_campaign_state(self, campaign_id: str, campaign_state: Dict[str, Any]) -> None:
        """Create the durable row for one campaign run."""
        model = self._campaign_model()
        config = campaign_state.get("config", {})
        runtime_state = {
            key: value
            for key, value in campaign_state.items()
            if key not in {"id", "status", "created_at", "started_at", "completed_at"}
        }
        model.objects.create(
            campaign_uuid=campaign_id,
            name=config.get("campaign_name") or f"{config.get('protocol_type', 'unknown').upper()} Campaign",
            description=config.get("description", "Auto-created by start_campaign"),
            status=campaign_state.get("status", "idle"),
            protocol_type=config.get("protocol_type", "unknown"),
            protocol_config=config.get("protocol_config", {}),
            generator_config=config.get("generator_config", {}),
            monitoring_config=config.get("monitoring_config", {}),
            started_at=self._as_datetime(campaign_state.get("started_at")),
            completed_at=self._as_datetime(campaign_state.get("completed_at")),
            runtime_state=runtime_state,
        )

    def get_campaign_state(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Return the durable state for a campaign run."""
        campaign = self._campaign_model().objects.filter(campaign_uuid=campaign_id).first()
        if campaign is None:
            return None
        return {
            "id": campaign_id,
            **campaign.runtime_state,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat(),
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        }

    def update_campaign_state(self, campaign_id: str, updates: Dict[str, Any]) -> None:
        """Atomically update lifecycle fields and runtime counters."""
        model = self._campaign_model()
        with transaction.atomic():
            try:
                campaign = model.objects.select_for_update().get(campaign_uuid=campaign_id)
            except model.DoesNotExist:
                logger.warning("Attempted to update non-existent campaign %s", campaign_id)
                return

            runtime_updates = dict(updates)
            if "status" in runtime_updates:
                campaign.status = runtime_updates.pop("status")
            if "started_at" in runtime_updates:
                campaign.started_at = self._as_datetime(runtime_updates.pop("started_at"))
            if "completed_at" in runtime_updates:
                campaign.completed_at = self._as_datetime(runtime_updates.pop("completed_at"))
            campaign.runtime_state = {**campaign.runtime_state, **runtime_updates}
            campaign.save(update_fields=["status", "started_at", "completed_at", "runtime_state"])

    def remove_campaign_state(self, campaign_id: str) -> None:
        """Delete a campaign row when startup did not complete."""
        self._campaign_model().objects.filter(campaign_uuid=campaign_id).delete()

    def get_active_campaigns(self) -> List[str]:
        """Get campaign IDs that may still have a running worker."""
        return list(
            self._campaign_model()
            .objects.filter(status__in=["starting", "running", "paused"])
            .values_list("campaign_uuid", flat=True)
        )

    def start_campaign(self, campaign_config: Dict[str, Any]) -> str:
        """
        Start a new fuzzing campaign
        
        Args:
            campaign_config: Campaign configuration dictionary with optional test_group_ids
            
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
            
            # Process test group IDs if provided
            test_group_ids = campaign_config.get('test_group_ids', [])
            test_cases_data = []
            fuzzing_engine = None
            
            # Always validate test groups if provided (including empty list)
            if test_group_ids is not None:
                # Validate test groups (empty list should fail validation)
                if not self._validate_test_groups(test_group_ids):
                    raise ValueError(f"Invalid or disabled test groups: {test_group_ids}")
                
                # Load test cases from selected groups
                test_cases_data = self._load_selected_test_cases(test_group_ids)
                if not test_cases_data:
                    raise ValueError(f"No enabled test cases found in groups: {test_group_ids}")
                
                # Ensure protocol_type consistency between campaign and selected test cases
                campaign_protocol_type = str(campaign_config.get('protocol_type', '')).lower()
                test_case_protocols = {str(tc.get('protocol_type', '')).lower() for tc in test_cases_data}
                # Remove empty markers
                test_case_protocols.discard('')

                if len(test_case_protocols) > 1:
                    raise ValueError(
                        f"Selected groups contain mixed protocol types: {sorted(test_case_protocols)}. "
                        f"Please select groups with the same protocol or run separate campaigns."
                    )

                if len(test_case_protocols) == 1:
                    only_protocol = next(iter(test_case_protocols))
                    if campaign_protocol_type and campaign_protocol_type != only_protocol:
                        logger.warning(
                            f"Campaign protocol_type '{campaign_protocol_type}' does not match test cases '{only_protocol}'. "
                            f"Overriding campaign to '{only_protocol}'."
                        )
                    # Force campaign protocol to match test cases
                    campaign_config['protocol_type'] = only_protocol

                    # Normalize/complete protocol_config according to protocol type
                    protocol_config = campaign_config.get('protocol_config') or {}
                    protocol_config['protocol_type'] = only_protocol
                    if only_protocol == 'can':
                        # Prefer 'device_path' and 'bitrate' keys consumed by orchestrator
                        if 'device_path' not in protocol_config:
                            # Accept possible aliases
                            alias = protocol_config.get('interface') or protocol_config.get('channel')
                            protocol_config['device_path'] = alias or 'can0'
                        if 'bitrate' not in protocol_config:
                            # Accept baud_rate as alias for legacy data
                            protocol_config['bitrate'] = protocol_config.get('baud_rate', 500000)
                    elif only_protocol == 'uart':
                        if 'port' not in protocol_config:
                            alias = protocol_config.get('device') or protocol_config.get('device_path')
                            protocol_config['port'] = alias or '/dev/ttyUSB0'
                        if 'baud_rate' not in protocol_config:
                            protocol_config['baud_rate'] = 115200
                        if 'timeout' not in protocol_config:
                            protocol_config['timeout'] = 1000
                    campaign_config['protocol_config'] = protocol_config

                # Prepare fuzzing engine with loaded test cases
                fuzzing_engine = self._prepare_fuzzing_engine(test_cases_data)
            
            # Generate campaign ID
            campaign_id = str(uuid.uuid4())
            
            # Initialize campaign state (AFL++ naming for runtime statistics)
            campaign_state = {
                'id': campaign_id,
                'config': campaign_config,
                'status': 'starting',
                'created_at': datetime.now().isoformat(),
                'started_at': None,
                # AFL++ runtime statistics (all zero-initialized)
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
                'fuzz_time': 0,
                'last_update': int(time.time()),
                # Business/static info for UI/context
                'test_group_ids': test_group_ids,
                'total_test_cases': len(test_cases_data),
                'fuzzing_engine_available': fuzzing_engine is not None,
                'strategy_distribution': self._calculate_strategy_distribution(test_cases_data),
            }
            
            self.store_campaign_state(campaign_id, campaign_state)
            
            # Initialize event bridge for this campaign
            fuzzer_bridge = self._get_fuzzer_bridge()
            fuzzer_bridge.initialize_campaign_bridge(campaign_id)
            
            # Start background campaign task
            self._start_campaign_task(campaign_id)
            
            logger.info(f"Campaign {campaign_id} scheduled with {len(test_cases_data)} test cases from {len(test_group_ids)} groups")
            return campaign_id
            
        except Exception as e:
            logger.error(f"Error starting campaign: {str(e)}")
            # Cleanup on error
            if campaign_id is not None:
                self.remove_campaign_state(campaign_id)
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
            campaign_state = self.get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Stop via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.stop()
            
            # Cleanup resources
            self._cleanup_campaign_resources(campaign_id)
            
            self.update_campaign_state(campaign_id, {
                'status': 'stopped',
                'completed_at': datetime.now().isoformat()
            })
            
            # Calculate final statistics
            final_stats = self._calculate_final_statistics(campaign_id)
            
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
            campaign_state = self.get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Pause via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.pause()
            
            self.update_campaign_state(campaign_id, {
                'status': 'paused',
                'paused_at': datetime.now().isoformat()
            })
            
            # Get updated state
            updated_state = self.get_campaign_state(campaign_id)
            
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
            campaign_state = self.get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Reset via adapter
            if campaign_id in self.orchestrator_adapters:
                orchestrator_adapter = self.orchestrator_adapters[campaign_id]
                orchestrator_adapter.reset()
            
            self.update_campaign_state(campaign_id, {
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
                'fuzz_time': 0,
                'last_update': int(time.time()),
                'status': 'reset',
                'reset_at': datetime.now().isoformat()
            })
            
            # Get updated state
            updated_state = self.get_campaign_state(campaign_id)
            
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
            campaign_state = self.get_campaign_state(campaign_id)
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
            
            # Merge durable state with adapter status
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
            campaign_state = self.get_campaign_state(campaign_id)
            if not campaign_state:
                raise Exception(f"Campaign {campaign_id} not found")
            
            # Get statistics from adapter
            statistics = {}
            if campaign_id in self.monitor_adapters:
                monitor_adapter = self.monitor_adapters[campaign_id]
                statistics = monitor_adapter.get_statistics()
            
            # Add calculated metrics from durable state
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
            self.update_campaign_state(campaign_id, progress_data)
            logger.debug(f"Updated campaign progress for {campaign_id}: {progress_data}")
        except Exception as e:
            logger.error(f"Error updating campaign progress for {campaign_id}: {e}")
    
    def _validate_campaign_config(self, config: Dict[str, Any]) -> None:
        """Validate campaign configuration"""
        required_fields = ['protocol_type', 'protocol_config', 'generator_config']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate test_group_ids if provided
        test_group_ids = config.get('test_group_ids', [])
        if test_group_ids:
            if not isinstance(test_group_ids, list):
                raise ValueError("test_group_ids must be a list")
            if not all(isinstance(group_id, (str, int)) for group_id in test_group_ids):
                raise ValueError("test_group_ids must contain valid group IDs")
    
    def _calculate_strategy_distribution(self, test_cases_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate strategy distribution from test cases data
        
        Args:
            test_cases_data: List of test cases with fuzzing rules
            
        Returns:
            Dict: Strategy distribution statistics
        """
        strategy_counts = {
            'bit_level': 0,
            'field_level': 0,
            'total_rules': 0,
            'total_test_cases': len(test_cases_data)
        }
        
        for test_case in test_cases_data:
            for rule in test_case.get('fuzzing_rules', []):
                strategy_counts['total_rules'] += 1
                
                if rule.get('target_type') == 'bit':
                    strategy_counts['bit_level'] += 1
                elif rule.get('target_type') == 'field':
                    strategy_counts['field_level'] += 1
        
        return strategy_counts
    
    def run_campaign(self, campaign_id: str, campaign_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run one campaign; local threads and Celery workers share this owner."""
        close_old_connections()
        orchestrator_adapter = None
        try:
            campaign_state = self.get_campaign_state(campaign_id)
            if campaign_state is None:
                raise Exception(f"Campaign {campaign_id} not found")

            protocol_adapter = self._get_protocol_adapter()
            campaign_config_with_id = campaign_config.copy()
            campaign_config_with_id["campaign_id"] = campaign_id
            test_group_ids = campaign_config.get("test_group_ids", [])
            if test_group_ids:
                test_cases = self._load_selected_test_cases(test_group_ids)
                campaign_config_with_id["test_cases"] = test_cases
                campaign_config_with_id["fuzzing_engine"] = self._prepare_fuzzing_engine(test_cases)

            orchestrator_adapter = protocol_adapter.create_orchestrator_adapter(campaign_config_with_id)
            monitor_adapter = protocol_adapter.create_monitor_adapter(
                campaign_config_with_id, orchestrator_adapter
            )
            self.orchestrator_adapters[campaign_id] = orchestrator_adapter
            self.monitor_adapters[campaign_id] = monitor_adapter

            orchestrator_adapter.start()
            self.update_campaign_state(
                campaign_id,
                {"status": "running", "started_at": timezone.now().isoformat()},
            )

            report_threshold = int(os.getenv("FUZZER_REPORT_THRESHOLD_EXECS", "50"))
            execs_done = 0
            last_reported_execs = 0
            while getattr(orchestrator_adapter, "is_running", False):
                current_state = self.get_campaign_state(campaign_id)
                if current_state is None or current_state.get("status") != "running":
                    orchestrator_adapter.stop()
                    break

                detail = monitor_adapter.get_statistics() or {}
                execs_done = max(execs_done, int(detail.get("execs_done", 0) or 0))
                if execs_done - last_reported_execs >= report_threshold:
                    updates = {
                        "execs_done": execs_done,
                        "execs_per_sec": float(detail.get("execs_per_sec", 0.0) or 0.0),
                        "cycles_done": int(detail.get("cycles_done", 0) or 0),
                        "corpus_count": int(detail.get("corpus_count", 0) or 0),
                        "corpus_favored": int(detail.get("corpus_favored", 0) or 0),
                        "corpus_found": int(detail.get("corpus_found", 0) or 0),
                        "pending_total": int(detail.get("pending_total", 0) or 0),
                        "pending_favs": int(detail.get("pending_favs", 0) or 0),
                        "bitmap_cvg": float(detail.get("bitmap_cvg", 0.0) or 0.0),
                        "saved_crashes": int(detail.get("saved_crashes", 0) or 0),
                        "saved_hangs": int(detail.get("saved_hangs", 0) or 0),
                        "total_tmout": int(detail.get("total_tmout", 0) or 0),
                        "run_time": int(detail.get("run_time", 0) or 0),
                        "last_update": int(time.time()),
                    }
                    self.update_campaign_state(campaign_id, updates)
                    self._send_campaign_event(campaign_id, "statistics_update", {"statistics": updates})
                    last_reported_execs = execs_done
                time.sleep(0.1)

            orchestrator_adapter.stop()
            self.update_campaign_state(
                campaign_id,
                {
                    "status": "stopped",
                    "completed_at": timezone.now().isoformat(),
                    "last_update": int(time.time()),
                },
            )
            final_state = self.get_campaign_state(campaign_id)
            self._send_campaign_event(campaign_id, "campaign_status", {"status": final_state})
            return {"status": "success", "campaign_id": campaign_id, "final_status": "stopped"}
        except Exception as exc:
            logger.exception("Fuzzing campaign %s failed", campaign_id)
            self.update_campaign_state(
                campaign_id,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "failed_at": timezone.now().isoformat(),
                },
            )
            self._send_campaign_event(
                campaign_id,
                "campaign_status",
                {"status": self.get_campaign_state(campaign_id)},
            )
            return {"status": "error", "campaign_id": campaign_id, "error_message": str(exc)}
        finally:
            if orchestrator_adapter is not None:
                self._cleanup_campaign_resources(campaign_id)
            close_old_connections()

    @staticmethod
    def _send_campaign_event(campaign_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Best-effort notification; database state remains authoritative."""
        try:
            from channels.layers import get_channel_layer
            from iotsploit_django.adapters.django.threadsafe_channel_layer import send_group

            channel_layer = get_channel_layer()
            if channel_layer:
                send_group(
                    channel_layer,
                    f"iot_fuzzer_campaign_{campaign_id}",
                    {"type": "fuzzer_event", "event_type": event_type, "data": {"campaign_id": campaign_id, **data}},
                )
        except Exception:
            logger.exception("Unable to publish fuzzer event for %s", campaign_id)

    def _start_campaign_task(self, campaign_id: str) -> None:
        """Dispatch the shared campaign loop through the selected runtime."""
        campaign_state = self.get_campaign_state(campaign_id)
        if campaign_state is None:
            raise Exception(f"Campaign {campaign_id} not found")
        campaign_config = campaign_state["config"]

        if settings.IOTSPLOIT_RUNTIME == "distributed":
            from iotsploit_django.tasks.fuzzer_tasks import run_fuzzing_campaign

            task = run_fuzzing_campaign.delay(campaign_id, campaign_config)
            task_id = task.id
        else:
            _local_fuzzer_executor.submit(self.run_campaign, campaign_id, campaign_config)
            task_id = f"local:{campaign_id}"

        self.update_campaign_state(campaign_id, {"task_id": task_id})
        logger.info("Started background campaign %s as %s", campaign_id, task_id)
    
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
    
    def _calculate_final_statistics(self, campaign_id: str) -> Dict[str, Any]:
        """Calculate final campaign statistics from durable state."""
        campaign_state = self.get_campaign_state(campaign_id)
        if not campaign_state:
            return {'campaign_id': campaign_id, 'error': 'Campaign not found'}

        return {
            'campaign_id': campaign_id,
            'execs_done': campaign_state.get('execs_done', 0),
            'saved_crashes': campaign_state.get('saved_crashes', 0),
            'saved_hangs': campaign_state.get('saved_hangs', 0),
            'total_tmout': campaign_state.get('total_tmout', 0),
            'bitmap_cvg': campaign_state.get('bitmap_cvg', 0.0),
            'run_time': campaign_state.get('run_time', 0),
            'fuzz_time': campaign_state.get('fuzz_time', 0),
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

    def _validate_test_groups(self, group_ids: List[str]) -> bool:
        """
        Validate that the provided test group IDs exist and are enabled
        
        Args:
            group_ids: List of test group IDs to validate
            
        Returns:
            bool: True if all groups are valid and enabled
        """
        try:
            from iotsploit_django.adapters.django.iot_fuzzer.models import TestGroup
            
            if not group_ids:
                logger.warning("No test group IDs provided")
                return False
            
            # Check if all groups exist and are enabled
            groups = TestGroup.objects.filter(
                id__in=group_ids,
                enabled=True
            )
            
            found_count = groups.count()
            if found_count != len(group_ids):
                missing_count = len(group_ids) - found_count
                logger.warning(f"Found {found_count} valid groups, {missing_count} groups missing or disabled")
                return False
            
            logger.info(f"Validated {found_count} test groups successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error validating test groups: {str(e)}")
            return False
    
    def _load_selected_test_cases(self, group_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Load test cases from the specified test groups with their fuzzing rules
        
        Args:
            group_ids: List of test group IDs to load
            
        Returns:
            List[Dict]: List of test cases with their frame fields and fuzzing rules
        """
        try:
            from iotsploit_django.adapters.django.iot_fuzzer.models import TestCase
            
            # Load test cases with related data using select_related and prefetch_related
            test_cases = TestCase.objects.filter(
                group_id__in=group_ids,
                enabled=True
            ).select_related(
                'group',
                'protocol_config'
            ).prefetch_related(
                'frame_fields',
                'fuzzing_rules__target_field'
            )
            
            test_cases_data = []
            for test_case in test_cases:
                # Get frame fields ordered by field_order
                frame_fields = test_case.frame_fields.all().order_by('field_order')
                
                # Get fuzzing rules
                fuzzing_rules = test_case.fuzzing_rules.filter(enabled=True)
                
                test_case_data = {
                    'id': test_case.id,
                    'name': test_case.name,
                    'description': test_case.description,
                    'priority': test_case.priority,
                    'group_id': test_case.group.id,
                    'group_name': test_case.group.name,
                    'protocol_type': test_case.protocol_config.protocol_type,
                    'protocol_config': test_case.protocol_config.settings,
                    'frame_name': test_case.frame_name,
                    'frame_description': test_case.frame_description,
                    'timeout_seconds': test_case.timeout_seconds,
                    'iterations': test_case.iterations,
                    'frame_fields': [
                        {
                            'id': field.id,
                            'field_name': field.field_name,
                            'field_id': field.field_id,
                            'field_type': field.field_type,
                            'value': field.value,
                            'default_value': field.default_value,
                            'field_order': field.field_order,
                            'bit_offset': field.bit_offset,
                            'bit_length': field.bit_length,
                            'target_bits': field.target_bits,
                            'is_required': field.is_required
                        }
                        for field in frame_fields
                    ],
                    'fuzzing_rules': [
                        {
                            'id': rule.id,
                            'rule_name': rule.rule_name,
                            'description': rule.description,
                            'target_type': rule.target_type,
                            'target_bits': rule.target_bits,
                            'strategy': rule.strategy,
                            'strategy_config': rule.strategy_config,
                            'iterations_per_rule': rule.iterations_per_rule,
                            'priority': rule.priority,
                            'target_field_id': rule.target_field.id if rule.target_field else None
                        }
                        for rule in fuzzing_rules
                    ]
                }
                
                test_cases_data.append(test_case_data)
            
            logger.info(f"Loaded {len(test_cases_data)} test cases from {len(group_ids)} groups")
            return test_cases_data
            
        except Exception as e:
            logger.error(f"Error loading test cases: {str(e)}")
            return []
    
    def _prepare_fuzzing_engine(self, test_cases: List[Dict[str, Any]]) -> Any:
        """
        Prepare fuzzing engine with loaded test cases
        
        Args:
            test_cases: List of test cases with frame fields and fuzzing rules
            
        Returns:
            FuzzingEngine: Configured fuzzing engine instance
        """
        try:
            # Import fuzzing engine components
            from iotsploit_fuzzer import FuzzingEngine, FuzzTestCase
            
            # Create fuzzing engine
            engine = FuzzingEngine()
            
            # Convert test cases to FuzzTestCase objects
            fuzz_test_cases = []
            for test_case_data in test_cases:
                # Create frame data from fields
                frame_data = frame_data_from_fields(test_case_data['frame_fields'])
                
                # Create FuzzTestCase from test case data
                fuzz_test_case = FuzzTestCase(
                    id=str(test_case_data['id']),
                    name=test_case_data['name'],
                    protocol_type=test_case_data['protocol_type'],
                    frame_data=frame_data,
                    frame_fields=test_case_data['frame_fields'],
                    fuzzing_rules=test_case_data['fuzzing_rules']
                )
                fuzz_test_cases.append(fuzz_test_case)
            
            # Store test cases in engine for later use
            engine.test_cases = fuzz_test_cases
            
            logger.info(f"Prepared fuzzing engine with {len(fuzz_test_cases)} test cases")
            return engine
            
        except ImportError as e:
            logger.warning(f"iotsploit_fuzzer not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error preparing fuzzing engine: {str(e)}")
            return None
    

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
            
            # Check for fuzzer module
            try:
                import iotsploit_fuzzer  # noqa: F401
                logger.info("iotsploit_fuzzer module found")
            except ImportError:
                missing_deps.append("iotsploit_fuzzer")
            
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
        return importlib.util.find_spec("can") is not None
    
    def _check_pyserial(self) -> bool:
        """Check if pyserial is available"""
        return importlib.util.find_spec("serial") is not None
    
    def _check_spidev(self) -> bool:
        """Check if spidev is available"""
        return importlib.util.find_spec("spidev") is not None
    
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
