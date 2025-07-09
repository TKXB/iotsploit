import time
import logging
from typing import Iterable, Optional, Type

from ..generators.base import DataGenerator
from ..harnesses.base import ProtocolHarness, HarnessResult
from ..monitoring.monitor import Monitor
from ..analysis.logger import TestLogger

logger = logging.getLogger("fuzzer.orchestrator")


class CampaignConfig:
    """Minimal configuration object. Expand as needed."""

    def __init__(
        self,
        iterations: int = 100,
        delay: float = 0.0,
        save_crashes: bool = True,
    ):
        self.iterations = iterations
        self.delay = delay  # seconds between test cases
        self.save_crashes = save_crashes


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

    def run(self) -> None:
        logger.info("Starting fuzzing campaign: %s iterations", self.config.iterations)
        seeds: Iterable[bytes] = self.generator.seed_corpus()
        corpus_iter = self.generator.generate(seeds, self.config.iterations)

        for idx, payload in enumerate(corpus_iter, 1):
            logger.debug("[Case %d] sending %d bytes", idx, len(payload))

            result: HarnessResult = self.harness.execute(payload)
            self.logger_backend.record(idx, payload, result)
            self.monitor.process_case(idx, payload, result)

            if result.crashed and self.config.save_crashes:
                self.logger_backend.save_crash(idx, payload, result)

            if self.config.delay:
                time.sleep(self.config.delay)

        # Post-campaign summary
        self.logger_backend.summary()
        logger.info("Fuzzing campaign finished.") 