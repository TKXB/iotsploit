"""A generator that starts from what the last campaign learned.

The existing loop calls ``seed_corpus()`` once and mutates from that fixed set
for the whole run, so hour 8000 of a campaign is exactly as informed as hour
one. This one seeds from the retained corpus, which means campaign N+1 begins
where campaign N stopped.

Two mutators, and the default is the one with no dependency. The built-in is
eight byte-level operations on a seeded PRNG: it needs nothing installed, and
measured against radamsa on this registry it produced roughly nineteen times
as many signatures per second and found five of the six product defects the
loop has turned up.

``--radamsa`` selects the other one, which reads the shape of its input, so a
mutated JSON document is usually still JSON and far more mutants survive to
reach the parser. It costs an external binary that is not a Python package,
which is why it is a choice rather than a requirement -- a campaign has to be
able to run on a machine nobody has prepared.

This class owns what is common to both: the seed corpus, which payload is
chosen as a parent, and the lineage edge retention needs. radamsa is given
one parent at a time for that last reason -- handed the whole pool it picks
among them and does not say which it chose.

Both modes are seeded and reproducible, and the manifest records which ran.
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
        radamsa: Optional[DataGenerator] = None,
        *,
        seed: int = 0,
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
        """Replay what is retained, then mutate from it.

        The replay is not a formality. A boundary movement is *defined* on a
        payload the ledger already holds, so a campaign that only mutates
        detects one when the mutator happens to reproduce a retained payload
        byte for byte -- which is to say, almost never. Running the corpus
        first is what makes ``BOUNDARY_MOVED`` a property of the run rather
        than of luck.
        """
        pool = [s for s in seeds] or [b""]
        self._seed_bytes.update({payload_id(s): s for s in pool})
        for retained in pool[:total]:
            yield retained
        total -= min(len(pool), total)
        if total <= 0:
            return
        if self.radamsa is not None:
            yield from self._radamsa(pool, total)
            return
        for _ in range(total):
            parent = self._random.choice(pool)
            child = self._mutate(parent, pool)[: self.max_payload]
            self._parents[payload_id(child)] = payload_id(parent)
            yield child

    def _radamsa(self, pool: List[bytes], total: int) -> Iterator[bytes]:
        """Mutate, one known parent at a time, recording the lineage."""
        produced = 0
        while produced < total:
            parent = self._random.choice(pool)
            batch = self.radamsa.mutate(parent, min(self.radamsa.batch, total - produced))
            if not batch:
                return
            for child in batch:
                child = child[: self.max_payload]
                self._parents[payload_id(child)] = payload_id(parent)
                yield child
                produced += 1
                if produced >= total:
                    return

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
