"""Mutation by radamsa, when the binary is on the host.

radamsa reads the shape of its input rather than only its bytes, so a mutated
JSON document is usually still JSON and a mutated log line is usually still a
log line. That matters more than raw throughput here: a byte-level mutator
spends most of a campaign producing input the adapter throws away before the
parser sees it.

Two things this asks of radamsa that the obvious invocation does not:

* ``-s`` makes a campaign reproducible. Without it a finding cannot be re-run,
  and the manifest's record of the seed is a lie.
* ``-o`` with a pattern writes one file per mutant, which is what makes a
  batch readable -- ``-n`` alone concatenates them onto stdout with nothing in
  between -- and lets a batch come from one known parent, so the corpus can
  still tell which seed a mutant descends from.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from .base import DataGenerator

#: Mutants per radamsa invocation. Spawning costs a few milliseconds, which is
#: small next to a parse but not next to nothing at campaign scale.
DEFAULT_BATCH = 64


class RadamsaGenerator(DataGenerator):
    """Use radamsa binary to mutate input samples."""

    def __init__(
        self,
        radamsa_path: str = "radamsa",
        count_per_seed: int = 1,
        seed: Optional[int] = None,
        batch: int = DEFAULT_BATCH,
    ):
        self.radamsa_path = shutil.which(radamsa_path) or radamsa_path
        self.count_per_seed = count_per_seed
        #: Passed to ``-s``. ``None`` leaves radamsa to seed itself, which is
        #: faster to type and impossible to reproduce.
        self.seed = seed
        self.batch = max(1, batch)
        self._round = 0
        if not shutil.which(self.radamsa_path):
            raise RuntimeError("Radamsa binary not found: %s" % self.radamsa_path)

    def seed_corpus(self) -> Iterable[bytes]:
        # Caller should override; empty seed corpus by default.
        return []

    def mutate(self, parent: bytes, count: int) -> List[bytes]:
        """``count`` mutants of one known parent, in one invocation."""
        if count < 1:
            return []
        workspace = tempfile.mkdtemp(prefix="radamsa_")
        try:
            source = Path(workspace) / "seed.bin"
            source.write_bytes(parent)
            command = [self.radamsa_path, "-n", str(count)]
            if self.seed is not None:
                # Varied per round, or every batch of a campaign would be the
                # same batch.
                command += ["-s", str(self.seed + self._round)]
            command += ["-o", str(Path(workspace) / "out-%n.bin"), str(source)]
            self._round += 1
            subprocess.run(command, check=True, capture_output=True)
            return [
                path.read_bytes()
                for path in sorted(Path(workspace).glob("out-*.bin"))
            ]
        except (subprocess.CalledProcessError, OSError):
            return []
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def generate(self, seeds: Iterable[bytes], total: int) -> Iterator[bytes]:
        pool = [seed for seed in seeds] or [b""]
        produced = 0
        index = 0
        while produced < total:
            parent = pool[index % len(pool)]
            index += 1
            wanted = min(self.batch, total - produced)
            batch = self.mutate(parent, wanted)
            if not batch:
                return
            for mutant in batch:
                yield mutant
                produced += 1
                if produced >= total:
                    return
