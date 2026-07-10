import logging
from pathlib import Path

from ..harnesses.base import HarnessResult

logger = logging.getLogger("fuzzer.logger")


class TestLogger:
    """Logs each test case to disk for later analysis."""

    def __init__(self, workdir: str = "artifacts"):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.total = 0
        self.crashes = 0

    def record(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        self.total += 1
        case_file = self.workdir / f"case_{idx}.bin"
        case_file.write_bytes(payload)
        if result.crashed:
            self.crashes += 1
            crash_file = self.workdir / f"crash_{idx}.bin"
            crash_file.write_bytes(payload)

    def save_crash(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        # Already stored in record; placeholder for extra actions.
        pass

    def summary(self):
        logger.info("Cases: %d, crashes: %d", self.total, self.crashes) 