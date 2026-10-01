import logging

from typing import Dict, Any
import time

from iotsploit_core.core.tool_manager import PathResolver
from iotsploit_django.tools.iot_protocol_components import (
    MockGeneratorInstance,
    MockMonitorInstance,
    MockOrchestratorInstance,
)

logger = logging.getLogger(__name__)


class MonitorObservationRecorder:
    """Own one optional target-history scan for one monitor of a campaign.

    ``mcu_core`` keeps the source, scope and fact names it had before monitors
    were generalised, and stores the flat legacy observation as the value, so
    new scans still compare against earlier ones.
    """

    def __init__(self, sink, *, campaign_id: str, entry):
        from iotsploit_core.domain.monitoring import parse_usb_resource
        from iotsploit_core.domain.observation import ObservationScope

        self.sink = sink
        self.kind = entry.kind
        self.latest = None
        self.finished = False
        if entry.kind == "mcu_core":
            _, serial, _ = parse_usb_resource(entry.resource)
            source, scope = "iot-fuzzer-jtag-core-monitor", f"jtag-core:{entry.target}:{serial}"
        else:
            source, scope = "iot-fuzzer-monitor", f"{entry.kind}:{entry.target}:{entry.resource}"
        started = sink.start_scans(
            run_id=campaign_id,
            target_id=entry.target_id,
            source=source,
            scopes=[ObservationScope(scope_key=scope)],
        )
        self.scan_id = started[0].scan_id

    def observe(self, verdict: dict) -> None:
        """Keep the latest verdict; close the scan at the first failure."""
        self.latest = self._value(verdict)
        detected_failure = verdict.get("stop_reason") or (
            verdict.get("detected_reason") and verdict.get("verdict") != "expected_reset"
        )
        if detected_failure and not self.finished:
            self.finish()

    def observe_sample(self, observation: dict) -> None:
        """A manual check: one observation with no campaign verdict."""
        from iotsploit_django.tools.monitor_compat import flatten_mcu_core

        self.latest = flatten_mcu_core(observation) if self.kind == "mcu_core" else observation

    def finish(self, error: str | None = None) -> None:
        if self.finished:
            return
        self.finished = True
        if error:
            self.sink.fail_scan(self.scan_id, error)
            return
        from iotsploit_core.domain.observation import Fact

        facts = []
        if self.latest is not None:
            if self.kind == "mcu_core":
                fact = Fact(protocol="jtag", subject_kind="self", observed_property="core_state",
                            value=self.latest)
            else:
                fact = Fact(protocol=self.kind, subject_kind="self", observed_property="health",
                            value=self.latest)
            facts.append(fact)
        self.sink.complete_scan(self.scan_id, facts, is_complete=False)

    def _value(self, verdict: dict):
        if self.kind == "mcu_core":
            from iotsploit_django.tools.monitor_compat import legacy_core_observation

            return legacy_core_observation(verdict)
        return verdict


def build_target_monitor(service, source):
    """The campaign policy for one open source: its kind's own, else judged by health."""
    policy = service.policy(source)
    if policy is not None:
        return policy
    from iotsploit_fuzzer.monitors import HealthMonitor

    return HealthMonitor(source.entry.name, source.entry.kind, source.end, source.settle_ms)


def campaign_monitor_plan(campaign_config: Dict[str, Any]):
    """The raw ``monitors`` plan of a campaign, translating ``core_monitor``; None if unmonitored."""
    plan = campaign_config.get("monitors")
    if plan is not None:
        return plan
    core_monitor = campaign_config.get("core_monitor")
    if core_monitor is not None:
        from iotsploit_django.tools.monitor_compat import legacy_plan

        return legacy_plan(core_monitor)
    return None


class SelectedCaseGenerator:
    """Feed selected case mutations into the single protocol execution loop.

    A case with a batch saved in Management runs exactly those payloads;
    the engine generates only for cases without one.
    """
    def __init__(self, engine, cases, replay=None, saved=None):
        from iotsploit_fuzzer.core.fuzzing_engine import FuzzTestCase
        from iotsploit_django.tools.frame_utils import frame_data_from_fields
        self.payloads = []
        self.case_settings = []
        self.on_case = None
        if replay is not None:
            self.payloads = [bytes.fromhex(replay["payload_hex"])]
            self.case_settings = [replay.get("config", {})]
        saved = saved or {}
        for case in cases:
            if str(case["id"]) in saved:
                payloads = [bytes.fromhex(p) for p in saved[str(case["id"])]]
            else:
                source = FuzzTestCase(str(case["id"]), case["name"], case["protocol_type"],
                                     frame_data_from_fields(case.get("frame_fields", [])),
                                     case.get("frame_fields", []), case.get("fuzzing_rules", []),
                                     case.get("target_bits"))
                mutations = engine.generate_mutations([source], iterations=int(case.get("iterations", 100)))
                payloads = [m.mutated_data for batch in mutations.values() for m in batch]
            self.payloads.extend(payloads)
            self.case_settings.extend([case.get("protocol_config", {})] * len(payloads))
        if not self.payloads:
            raise ValueError("Selected cases generated no executable payloads")
        self.total = len(self.payloads)

    def seed_corpus(self):
        return self.payloads[:1]

    def generate(self, seeds, total):
        for payload, settings in zip(self.payloads[:total], self.case_settings[:total]):
            if self.on_case is not None:
                self.on_case(settings)
            yield payload


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

        self.protocol_interface = None
        self.monitor_session = None
        self.monitor_recorders = {}
        self.failure = None
        # A monitored campaign must never silently fall back to the mock.
        self._monitored = (
            campaign_config.get("monitors") is not None or campaign_config.get("core_monitor") is not None
        )

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
            self._use_mock()
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

            replay = self.campaign_config.get("replay")
            if replay is not None:
                generator = SelectedCaseGenerator(None, [], replay=replay)
            elif self.fuzzing_engine:
                generator = SelectedCaseGenerator(
                    self.fuzzing_engine, self.campaign_config["test_cases"],
                    saved=self.campaign_config.get("case_payloads"),
                )
            else:
                # Create generator
                generator_config = self.campaign_config.get('generator_config', {})
                generator_type = generator_config.get('generator_type', 'radamsa')

                if generator_type == 'radamsa':
                    radamsa_path = PathResolver().resolve_tool_path("radamsa")

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
                        if self.campaign_config.get("protocol_config", {}).get("protocol_type") == "usbtmc":
                            default_seeds = [b"*IDN?\n", b"SYST:ERR?\n", b"LED:ALL?\n", b":DATA:WRITE #14test\n"]
                        generator.seed_corpus = lambda: default_seeds
                        logger.info(f"Using radamsa at: {radamsa_path} with {len(default_seeds)} seed templates")
                    else:
                        logger.warning("Radamsa not found, falling back to mock")
                        self._use_mock()
                        return
                else:
                    logger.warning(f"Unsupported generator type: {generator_type}, using mock")
                    self._use_mock()
                    return

            # Create harness based on protocol type
            protocol_config = self.campaign_config.get('protocol_config', {})
            protocol_type = protocol_config.get('protocol_type', '').lower()

            if protocol_type == 'usbtmc':
                from iotsploit_django.composition_root.fuzzer_container import open_usbtmc
                interface, harness = open_usbtmc(protocol_config, f"campaign {self.campaign_config.get('campaign_id', '')}")
                if replay is not None:
                    harness.tag = replay['tag_before']
                    harness.last_out_tag = replay['out_tag_before']
                    harness.last_in_tag = replay['in_tag_before']
                    if replay.get('baseline_hex') != harness.baseline.hex():
                        interface.close()
                        raise ValueError('Replay device identity does not match the saved baseline')
                if isinstance(generator, SelectedCaseGenerator):
                    generator.on_case = harness.use_case
            elif protocol_type == 'can':
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
                    or ''
                )
                if not device:
                    raise ValueError("A serial port from device discovery is required")
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
                self._use_mock()
                return

            self.protocol_interface = interface
            if self._monitored:
                harness = self._open_target_monitors(harness)

            # Create monitor and logger (pluggable by protocol)
            self.monitor = create_monitor(protocol_type, self.campaign_config.get('monitoring'))
            logger_backend = TestLogger()
            if self.campaign_config.get("campaign_id"):
                logger_backend.campaign_id = self.campaign_config["campaign_id"]
            if protocol_type == "usbtmc":
                import json
                manifest = {'protocol_config': protocol_config, 'device': interface.identity,
                            'baseline_hex': getattr(harness, 'inner', harness).baseline.hex(),
                            'monitors': campaign_monitor_plan(self.campaign_config),
                            'generator_config': self.campaign_config.get('generator_config', {})}
                path = logger_backend.workdir / f'campaign_{logger_backend.campaign_id}_manifest.json'
                path.write_text(json.dumps(manifest, indent=2))

            # Create campaign config with event callback
            campaign_config = CampaignConfig(
                iterations=generator.total if isinstance(generator, SelectedCaseGenerator) else self.campaign_config.get('iterations_total', 1000),
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
            if protocol_type == "usbtmc":
                # The hardware harness checks cancellation between bounded transfers.
                getattr(harness, "inner", harness).cancelled = lambda: self.orchestrator._should_stop

            logger.info("Real fuzzer components initialized successfully")

        except ImportError as e:
            self._close_resources()
            if self._monitored or self.campaign_config.get("protocol_config", {}).get("protocol_type") == "usbtmc":
                raise
            logger.warning(f"Failed to import fuzzer module: {e}, using mock implementation")
            self._use_mock()
        except Exception as e:
            self._close_resources()
            if self._monitored or self.campaign_config.get("protocol_config", {}).get("protocol_type") == "usbtmc":
                raise
            logger.error(f"Error initializing fuzzer components: {e}, using mock implementation")
            self._use_mock()

    def _use_mock(self):
        if self.campaign_config.get("protocol_config", {}).get("protocol_type") == "usbtmc":
            raise RuntimeError("USBTMC campaigns require real USB hardware; mock fallback disabled")
        if self._monitored:
            raise RuntimeError("Monitored campaigns require real generator and protocol hardware; mock fallback disabled")
        self.fuzzer_instance = MockOrchestratorInstance(self.campaign_config)

    def _open_target_monitors(self, harness):
        """Open the campaign's monitor plan and wrap ``harness`` with its policies."""
        from iotsploit_django.composition_root.wiring import get_monitor_service
        from iotsploit_fuzzer.harnesses.monitor_set_harness import MonitorSetHarness

        service = get_monitor_service()
        entries = service.plan(campaign_monitor_plan(self.campaign_config))
        campaign_id = self.campaign_config["campaign_id"]
        self.monitor_session = service.open(entries, owner=f"campaign {campaign_id}")
        harness = MonitorSetHarness(harness, [build_target_monitor(service, source)
                                              for source in self.monitor_session.sources])
        for entry in entries:
            if not entry.target_id:
                continue
            try:
                from iotsploit_django.adapters.django.observation_repository import ObservationRepository

                self.monitor_recorders[entry.name] = MonitorObservationRecorder(
                    ObservationRepository(), campaign_id=campaign_id, entry=entry,
                )
            except Exception as exc:
                logger.warning("Target-history recording unavailable for %s: %s", entry.name, exc)
        verdicts = harness.preflight()
        self._handle_fuzzer_event("monitor_status", {"monitor_verdicts": [v.to_dict() for v in verdicts]})
        blocked = next((verdict for verdict in verdicts if verdict.decisive and verdict.stop_reason), None)
        if blocked is not None:
            prefix = "MCU preflight failed" if blocked.kind == "mcu_core" else f"{blocked.monitor} preflight failed"
            raise RuntimeError(f"{prefix}: {blocked.stop_reason}")
        return harness

    def _close_resources(self):
        try:
            if self.monitor_session is not None:
                self.monitor_session.close()
                self.monitor_session = None
        finally:
            for name, recorder in self.monitor_recorders.items():
                try:
                    recorder.finish(self.failure)
                except Exception as exc:
                    logger.warning("Could not finish observation scan for %s: %s", name, exc)
            self.monitor_recorders = {}
            if self.protocol_interface is not None:
                self.protocol_interface.close()
                self.protocol_interface = None

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
            if self.orchestrator:
                self.orchestrator.run()
        except Exception as e:
            self.failure = str(e)
            logger.error(f"Error during fuzzing campaign: {e}")
        finally:
            try:
                self._close_resources()
            finally:
                self.is_running = False

    def stop(self):
        """Stop fuzzing campaign"""
        if self.orchestrator:
            self.orchestrator.stop()
            if hasattr(self, "fuzzer_thread"):
                self.fuzzer_thread.join(timeout=5)
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
                'monitor_status': 'monitor_status',
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

            if enhanced_data["event_type"] in ("campaign_stopped", "campaign_completed"):
                enhanced_data["is_running"] = False

            verdicts = enhanced_data.get("monitor_verdicts")
            if verdicts:
                self._record_verdicts(campaign_id, verdicts, enhanced_data)

            # Emit event to Django WebSocket system
            bridge.emit_event(django_event_type, enhanced_data)

        except Exception as e:
            logger.error(f"Error handling fuzzer event: {e}")

    def _record_verdicts(self, campaign_id, verdicts, enhanced_data):
        from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
        from iotsploit_django.tools.monitor_compat import first_mcu_core, legacy_core_observation

        for verdict in verdicts:
            recorder = self.monitor_recorders.get(verdict.get("monitor"))
            if recorder is not None:
                try:
                    recorder.observe(verdict)
                except Exception as exc:
                    logger.warning("Could not record %s observation: %s", verdict.get("monitor"), exc)
        update = {"monitor_verdicts": verdicts}
        core = first_mcu_core(verdicts)
        if core is not None:
            # Clients built before monitor plans read this flat dict.
            enhanced_data["core_observation"] = update["core_observation"] = legacy_core_observation(core)
        IoTFuzzerManager.get_instance().update_campaign_state(campaign_id, update)

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
                'saved_crashes': stats.get('crashes', 0) or 0,
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
                'saved_crashes': stats.get('crashes', 0),
                'saved_hangs': stats.get('hang_count', 0),
                'total_tmout': stats.get('timeouts', 0),
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

            radamsa_path = PathResolver().resolve_tool_path("radamsa")

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
