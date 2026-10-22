import abc
from typing import Iterable


class DataGenerator(abc.ABC):
    """Interface for data generators."""

    @abc.abstractmethod
    def seed_corpus(self) -> Iterable[bytes]:
        """Return an initial iterable of seed samples."""

    @abc.abstractmethod
    def generate(self, seeds: Iterable[bytes], total: int) -> Iterable[bytes]:
        """Generate *total* mutated samples based on *seeds*."""
