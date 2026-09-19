import logging
from pathlib import Path
from typing import Callable, Optional

from ..harnesses.base import HarnessResult
from .corpus import payload_id

logger = logging.getLogger("fuzzer.logger")


class TestLogger:
    """Logs test cases to disk for later analysis, keyed on content.

    Files were named ``case_{index}.bin``, which made a payload's identity its
    position in a campaign: every run overwrote the previous run's cases
    wherever the indices overlapped, ``case_500.bin`` and ``crash_500.bin``
    came from different runs, and nothing on disk was attributable. Naming by
    content hash instead makes a repeated payload one file and leaves earlier
    campaigns intact.

    ``keep`` lets a caller that has its own notion of interesting -- the
    parser loop, whose corpus is curated by signature -- stop routine cases
    reaching disk at all, without giving up the crash record.
    """

    def __init__(
        self,
        workdir: str = "artifacts",
        keep: Optional[Callable[[bytes, HarnessResult], bool]] = None,
    ):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.keep = keep
        self.total = 0
        self.crashes = 0

    def record(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        self.total += 1
        if result.crashed:
            self.crashes += 1
        if self.keep is not None and not self.keep(payload, result):
            return
        identity = payload_id(payload)
        self._write(f"case_{identity}.bin", payload)
        if result.crashed:
            self._write(f"crash_{identity}.bin", payload)

    def _write(self, name: str, payload: bytes) -> None:
        path = self.workdir / name
        if not path.exists():
            path.write_bytes(payload)

    def summary(self):
        logger.info("Cases: %d, crashes: %d", self.total, self.crashes)
