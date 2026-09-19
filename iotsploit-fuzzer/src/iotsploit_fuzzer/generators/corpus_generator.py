"""A generator that starts from what the last campaign learned.

The existing loop calls ``seed_corpus()`` once and mutates from that fixed set
for the whole run, so hour 8000 of a campaign is exactly as informed as hour
one. This one seeds from the retained corpus, which means campaign N+1 begins
where campaign N stopped.

Mutation is seeded and deterministic on purpose. A campaign that cannot be
re-run is a campaign whose findings cannot be re-examined, and the manifest
records the seed precisely so that a boundary movement can be reproduced
rather than argued about. ``radamsa`` is stronger and is used when asked for,
at the cost of that reproducibility, which the manifest then says out loud.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Iterable, Iterator, List, Optional

from ..analysis.corpus import CorpusStore, payload_id
from .base import DataGenerator

logger = logging.getLogger("fuzzer.corpus_generator")

#: Values that sit on the boundaries parsers get wrong.
_INTERESTING = (
    b"\x00", b"\xff", b"\x7f", b"\x80", b"\x01",
    b"-1", b"0", b"2147483648", b"4294967296", b"99999999999999999999",
    b"NaN", b"null", b"true", b"[]", b"{}", b"\"\"",
    b"0x", b"..", b"%s", b"\r\n",
)


class CorpusGenerator(DataGenerator):
    """Mutate the retained corpus, remembering what each child came from."""

    def __init__(
        self,
        store: CorpusStore,
        *,
        seed: int = 0,
        radamsa: Optional[DataGenerator] = None,
        max_payload: Optional[int] = None,
    ) -> None:
        self.store = store
        self.seed = seed
        self.radamsa = radamsa
        self.max_payload = max_payload or store.target.payload_max_bytes
        self._random = random.Random(seed)
        #: child id -> parent id, for the campaign's edge detection. Bounded
        #: by the campaign length, and holds ids rather than payloads.
        self._parents: Dict[str, str] = {}
        #: id -> bytes for this generation's seeds only, so a parent can be
        #: re-classified without reading it back off disk.
        self._seed_bytes: Dict[str, bytes] = {}

    # -- DataGenerator -----------------------------------------------------

    def seed_corpus(self) -> List[bytes]:
        """The retained payloads, falling back to the target's own seeds.

        The registry seeds are always included: they are the known-good inputs
        that keep a corpus of rejections from drifting away from the accept
        side of the boundary entirely.
        """
        seeds: List[bytes] = [payload for _, payload in self.store.payloads()]
        for seed in self.store.target.seeds:
            if seed not in seeds:
                seeds.append(seed)
        self._seed_bytes = {payload_id(s): s for s in seeds}
        return seeds

    def generate(self, seeds: Iterable[bytes], total: int) -> Iterator[bytes]:
        pool = [s for s in seeds] or [b""]
        self._seed_bytes.update({payload_id(s): s for s in pool})
        if self.radamsa is not None:
            yield from self._radamsa(pool, total)
            return
        for _ in range(total):
            parent = self._random.choice(pool)
            child = self._mutate(parent, pool)[: self.max_payload]
            self._parents[payload_id(child)] = payload_id(parent)
            yield child

    def _radamsa(self, pool: List[bytes], total: int) -> Iterator[bytes]:
        """Delegate the bytes, keep the bookkeeping.

        radamsa does not say which seed a mutant came from, so the parent link
        -- and with it edge retention -- is not available in this mode.
        """
        for child in self.radamsa.generate(pool, total):
            yield child[: self.max_payload]

    # -- lineage -----------------------------------------------------------

    def parent_of(self, payload: bytes) -> Optional[bytes]:
        """The seed a payload was mutated from, when the mutator recorded one."""
        parent_id = self._parents.get(payload_id(payload))
        if parent_id is None:
            return None
        return self._seed_bytes.get(parent_id) or self.store.payload(parent_id)

    # -- mutation ----------------------------------------------------------

    def _mutate(self, payload: bytes, pool: List[bytes]) -> bytes:
        rng = self._random
        operations = (
            self._flip_bit, self._set_interesting, self._delete_span,
            self._duplicate_span, self._insert, self._splice,
            self._repeat_span, self._bump_number,
        )
        data = payload
        for _ in range(rng.randint(1, 3)):
            data = rng.choice(operations)(data, pool)
        return data

    def _flip_bit(self, data: bytes, _pool: List[bytes]) -> bytes:
        if not data:
            return b"\x00"
        out = bytearray(data)
        index = self._random.randrange(len(out))
        out[index] ^= 1 << self._random.randrange(8)
        return bytes(out)

    def _set_interesting(self, data: bytes, _pool: List[bytes]) -> bytes:
        if not data:
            return self._random.choice(_INTERESTING)
        out = bytearray(data)
        index = self._random.randrange(len(out))
        chosen = self._random.choice(_INTERESTING)
        return bytes(out[:index]) + chosen + bytes(out[index + 1:])

    def _delete_span(self, data: bytes, _pool: List[bytes]) -> bytes:
        if len(data) < 2:
            return data
        start = self._random.randrange(len(data))
        end = min(len(data), start + self._random.randint(1, max(1, len(data) // 4)))
        return data[:start] + data[end:]

    def _duplicate_span(self, data: bytes, _pool: List[bytes]) -> bytes:
        if not data:
            return data
        start = self._random.randrange(len(data))
        end = min(len(data), start + self._random.randint(1, 32))
        return data[:end] + data[start:end] + data[end:]

    def _insert(self, data: bytes, _pool: List[bytes]) -> bytes:
        index = self._random.randrange(len(data) + 1)
        blob = self._random.choice(_INTERESTING) * self._random.randint(1, 8)
        return data[:index] + blob + data[index:]

    def _splice(self, data: bytes, pool: List[bytes]) -> bytes:
        other = self._random.choice(pool)
        if not data or not other:
            return data + other
        cut = self._random.randrange(len(data))
        return data[:cut] + other[self._random.randrange(len(other)):]

    def _repeat_span(self, data: bytes, _pool: List[bytes]) -> bytes:
        """Grow a structure rather than a buffer -- the shape of a blowup."""
        if not data:
            return data
        start = self._random.randrange(len(data))
        end = min(len(data), start + self._random.randint(1, 16))
        return data[:end] + data[start:end] * self._random.choice((8, 64, 512)) + data[end:]

    def _bump_number(self, data: bytes, _pool: List[bytes]) -> bytes:
        """Replace a digit run with a number nobody sized a buffer for.

        Worth its own operation because the fuzzer's own ``0-10000000``
        MemoryError is exactly this mutation applied to ``0-7``, and a bit
        flip reaches it only by accident.
        """
        digits = [i for i, byte in enumerate(data) if 0x30 <= byte <= 0x39]
        if not digits:
            return data
        start = self._random.choice(digits)
        end = start
        while end < len(data) and 0x30 <= data[end] <= 0x39:
            end += 1
        replacement = str(self._random.choice(
            (0, 1, -1, 255, 65536, 2 ** 31, 2 ** 32, 10 ** 7, 10 ** 9, 10 ** 18)
        )).encode()
        return data[:start] + replacement + data[end:]
