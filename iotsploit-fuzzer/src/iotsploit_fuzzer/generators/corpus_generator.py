"""A generator that starts from what the last campaign learned.

The existing loop calls ``seed_corpus()`` once and mutates from that fixed set
for the whole run, so hour 8000 of a campaign is exactly as informed as hour
one. This one seeds from the retained corpus, which means campaign N+1 begins
where campaign N stopped.

Mutation is radamsa's. It reads the shape of its input, so a mutated JSON
document is usually still JSON and far more mutants survive to reach the
parser than a byte-level mutator produces.

This class owns everything around that: which payload is chosen as a parent,
what the seed corpus is, and the lineage that edge retention needs. radamsa
is given one parent at a time for that last reason -- handed the whole pool it
picks among them and does not say which it chose.

Seeded through radamsa's own ``-s``, so a campaign can be re-run and a finding
re-examined rather than argued about.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Iterable, Iterator, List, Optional

from ..analysis.corpus import CorpusStore, payload_id
from .base import DataGenerator

logger = logging.getLogger("fuzzer.corpus_generator")

class CorpusGenerator(DataGenerator):
    """Mutate the retained corpus, remembering what each child came from."""

    def __init__(
        self,
        store: CorpusStore,
        radamsa: "RadamsaGenerator",
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
        if total > 0:
            yield from self._radamsa(pool, total)

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
