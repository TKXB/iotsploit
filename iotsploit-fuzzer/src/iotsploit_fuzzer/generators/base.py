import abc
import random
from typing import Iterable


class DataGenerator(abc.ABC):
    """Interface for data generators."""

    @abc.abstractmethod
    def seed_corpus(self) -> Iterable[bytes]:
        """Return an initial iterable of seed samples."""

    @abc.abstractmethod
    def generate(self, seeds: Iterable[bytes], total: int) -> Iterable[bytes]:
        """Generate *total* mutated samples based on *seeds*."""


class RandomGenerator(DataGenerator):
    """Very simple random bytes generator (fallback)."""

    def __init__(self, min_len: int = 1, max_len: int = 32):
        self.min_len = min_len
        self.max_len = max_len

    def seed_corpus(self) -> Iterable[bytes]:
        yield b""

    def generate(self, seeds: Iterable[bytes], total: int) -> Iterable[bytes]:
        for _ in range(total):
            size = random.randint(self.min_len, self.max_len)
            yield random.randbytes(size) 