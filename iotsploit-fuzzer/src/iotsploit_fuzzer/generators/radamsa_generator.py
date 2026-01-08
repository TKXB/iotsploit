import subprocess
import tempfile
import shutil
import os
from pathlib import Path
from typing import Iterable, List

from .base import DataGenerator


class RadamsaGenerator(DataGenerator):
    """Use radamsa binary to mutate input samples."""

    def __init__(self, radamsa_path: str = "radamsa", count_per_seed: int = 1):
        self.radamsa_path = shutil.which(radamsa_path) or radamsa_path
        self.count_per_seed = count_per_seed
        if not shutil.which(self.radamsa_path):
            raise RuntimeError("Radamsa binary not found: %s" % self.radamsa_path)

    def seed_corpus(self) -> Iterable[bytes]:
        # Caller should override; empty seed corpus by default.
        return []

    def generate(self, seeds: Iterable[bytes], total: int) -> Iterable[bytes]:
        tmp_dir = tempfile.mkdtemp(prefix="radamsa_seed_")
        try:
            seed_files: List[Path] = []
            for idx, seed in enumerate(seeds):
                p = Path(tmp_dir) / f"seed_{idx}.bin"
                p.write_bytes(seed)
                seed_files.append(p)

            generated = 0
            while generated < total:
                # Radamsa can read from seed files and output to stdout
                cmd = [self.radamsa_path, "-n", "1"]
                if seed_files:
                    cmd.extend(str(p) for p in seed_files)
                out = subprocess.check_output(cmd)
                yield out
                generated += 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True) 