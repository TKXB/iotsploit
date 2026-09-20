"""Content-addressed payloads and the boundary ledger that gives them meaning.

The fuzzer's existing ``artifacts/`` directory keys files on the iteration
index, so campaign N+1 overwrites campaign N wherever the indices overlap, and
``case_500.bin`` and ``crash_500.bin`` are usually from different runs. That is
a graveyard, not a corpus: nothing is attributable and nothing accumulates.

Here a payload's identity is its content, and the ledger records what each one
*did* -- its normalised outcome signature -- under the fingerprint of the
oracle that judged it. That is what makes a diff possible, and a diff is the
thing that keeps producing information after the crashes run dry.

Writes are atomic and locked per target. A nightly run that is killed halfway
leaves the previous ledger intact and readable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

from ..harnesses.parser_targets import ParseTarget
from .outcome import Outcome

logger = logging.getLogger("fuzzer.corpus")

try:  # POSIX advisory locking; elsewhere the lock is best-effort.
    import fcntl
except ImportError:  # pragma: no cover - exercised only off POSIX
    fcntl = None

#: Bumped when the on-disk shape changes. A ledger from an older version is
#: re-baselined rather than guessed at.
LEDGER_VERSION = 1

#: Payloads kept per distinct signature. Without a cap the corpus fills with
#: near-identical inputs that all prove the same point, and the gate replay
#: that has to run on every commit slows down for nothing.
MAX_EXEMPLARS = 3

#: Payloads kept per distinct accept/reject edge. Lower than the signature cap
#: because an edge is already a pair, and because crossing the line is the
#: common case for a mutator -- uncapped, this alone grows without bound.
MAX_EDGE_EXEMPLARS = 1

#: Absolute ceiling per signature, whatever the reason for keeping it. Edges
#: are capped per *pair*, so a signature reachable from many parents could
#: otherwise accumulate one exemplar per parent and escape both caps.
MAX_PER_SIGNATURE = 5

#: Distinct signatures one target may hold. The per-signature caps bound how
#: many payloads each behaviour keeps, but not how many behaviours there are,
#: and a result shape with six bucketed fields has a combinatorially large
#: space. Sized generously: reaching it means the shape is too fine-grained to
#: be a boundary, which is worth reporting rather than absorbing.
MAX_SIGNATURES = 200

#: Campaign manifests kept per target. Enough to compare a finding against the
#: runs around it; bounded so a nightly loop does not accumulate a manifest a
#: day for ever.
KEEP_MANIFESTS = 10


class CorpusDamagedError(RuntimeError):
    """The ledger and the archive do not agree, so replay coverage is unknown.

    Raised rather than worked around. A replay that silently skips the
    payloads it cannot find still reports success, and a green gate that
    checked fewer inputs than it claims to is worse than a red one.
    """


def payload_id(payload: bytes) -> str:
    """A payload's identity: what it is, never where it appeared."""
    return hashlib.sha256(payload).hexdigest()[:16]


@dataclass
class LedgerEntry:
    """One retained payload, and what it did the last time anyone looked."""

    signature: str
    kind: str
    first_seen: str
    #: The parent's signature, when this payload was retained because one
    #: mutation moved it across the accept/reject line. Empty otherwise. The
    #: pair is the point: one payload alone does not locate a boundary.
    edge_of: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "signature": self.signature,
            "kind": self.kind,
            "first_seen": self.first_seen,
            "edge_of": self.edge_of,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "LedgerEntry":
        return cls(
            signature=str(raw.get("signature", "")),
            kind=str(raw.get("kind", "")),
            first_seen=str(raw.get("first_seen", "")),
            edge_of=str(raw.get("edge_of", "")),
        )


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold the per-target lock for the duration of a write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:  # pragma: no cover - unlock of a dead fd
                pass
        os.close(handle)


def _write_atomic(path: Path, data: bytes) -> None:
    """Replace a file in one step, or not at all.

    The fsync matters more than it looks: without it a machine that loses
    power mid-campaign can leave a renamed but empty ledger, which reads as
    "this target has never been fuzzed" and silently discards months of
    boundary history.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class CorpusStore:
    """The retained payloads for one target, and the ledger over them."""

    def __init__(self, root: Path | str, target: ParseTarget) -> None:
        self.target = target
        self.root = Path(root) / target.name
        #: One archive per target rather than one file per payload. The
        #: corpus is a thousand-odd inputs of a hundred-odd bytes each, and
        #: as loose files it was 74% of the repository's tracked file count
        #: for 1% of its bytes -- plus a 4 KB block apiece, which turned
        #: 1.1 MB of payloads into 9.4 MB on disk.
        self.archive_path = self.root / "payloads.zip"
        #: Where payloads used to live, read once so an existing corpus
        #: migrates itself on the next save.
        self.legacy_dir = self.root / "payloads"
        self.ledger_path = self.root / "ledger.json"
        self.lock_path = self.root / ".lock"
        self.entries: Dict[str, LedgerEntry] = {}
        #: True when the ledger was written under a different oracle. Diffing
        #: is refused until a re-baseline: a changed declared-exception set
        #: moves the accept/reject line by definition, and reporting that as
        #: thousands of boundary movements teaches everyone to ignore reports.
        self.stale = False
        self.load()

    # -- reading -----------------------------------------------------------

    def load(self) -> None:
        self.entries = {}
        #: Set when the ledger and the archive disagree. Not raised here -- a
        #: caller may want to inspect a damaged corpus -- but anything that
        #: replays or extends it must refuse. Assigned before the payloads
        #: are read, because reading them is one of the things that can
        #: discover the damage.
        self.damaged = ""
        self._payloads: Dict[str, bytes] = self._read_payloads()
        self._counts: Dict[str, int] = {}
        self.stale = False
        #: Set when a new signature was turned away by MAX_SIGNATURES.
        self.saturated = False
        if not self.ledger_path.exists():
            return
        try:
            raw = json.loads(self.ledger_path.read_text())
        except (OSError, ValueError) as error:
            logger.warning("ledger for %s is unreadable (%s)", self.target.name, error)
            self.stale = True
            return
        if raw.get("ledger_version") != LEDGER_VERSION:
            logger.warning("ledger for %s was written by an older version", self.target.name)
            self.stale = True
        if raw.get("fingerprint") != self.target.fingerprint:
            logger.warning(
                "ledger for %s was recorded against oracle %s, now %s",
                self.target.name, raw.get("fingerprint"), self.target.fingerprint,
            )
            self.stale = True
        self.entries = {
            str(key): LedgerEntry.from_dict(value)
            for key, value in (raw.get("entries") or {}).items()
            if isinstance(value, dict)
        }
        for entry in self.entries.values():
            self._counts[entry.signature] = self._counts.get(entry.signature, 0) + 1
        self._check_archive_agrees()

    def _check_archive_agrees(self) -> None:
        """The ledger and the archive are two files, written one after the
        other under one lock -- which bounds the window but does not remove
        it. A process killed between the two renames leaves a mixed pair.

        A payload the ledger names and the archive does not have is the case
        that must fail: ``payloads()`` would skip it, the replay would check
        fewer inputs than the ledger claims, and it would still pass. The
        other direction is harmless -- an unreferenced payload costs space
        and nothing else -- so it is reported and ignored.
        """
        if self.damaged:
            return
        named = set(self.entries)
        held = set(self._payloads)
        missing = named - held
        if missing:
            self.damaged = (
                f"{len(missing)} payload(s) named by the ledger are not in the "
                f"archive, e.g. {sorted(missing)[0]}"
            )
            return
        orphaned = held - named
        if orphaned:
            logger.warning(
                "%s: %d payload(s) in the archive are not in the ledger; ignoring",
                self.target.name, len(orphaned),
            )

    def _read_payloads(self) -> Dict[str, bytes]:
        """Every retained payload, from the archive and any loose leftovers."""
        found: Dict[str, bytes] = {}
        if self.legacy_dir.is_dir():
            for path in self.legacy_dir.glob("*.bin"):
                found[path.stem] = path.read_bytes()
        if self.archive_path.exists():
            try:
                with zipfile.ZipFile(self.archive_path) as archive:
                    for name in archive.namelist():
                        found[Path(name).stem] = archive.read(name)
            except (OSError, zipfile.BadZipFile) as error:
                # An unreadable archive is not an empty corpus. Treating it as
                # one is how a replay reports success having checked nothing.
                self.damaged = f"payloads.zip cannot be read: {error}"
        return found

    def payload(self, identity: str) -> Optional[bytes]:
        return self._payloads.get(identity)

    def payloads(self) -> Iterator[Tuple[str, bytes]]:
        """Every retained payload, for a replay or a new campaign's seeds."""
        for identity in sorted(self.entries):
            data = self.payload(identity)
            if data is not None:
                yield identity, data

    def signature_counts(self) -> Dict[str, int]:
        return dict(self._counts)

    def known_signatures(self) -> set:
        """Every signature the ledger holds. Kept as a set, not rebuilt: this
        is asked once per case, and rebuilding it made the campaign quadratic
        in its own corpus."""
        return set(self._counts)

    # -- writing -----------------------------------------------------------

    def admit(
        self, payload: bytes, outcome: Outcome, campaign: str, *, edge_of: str = ""
    ) -> bool:
        """Retain a payload if this signature still has room, else discard it.

        Returns whether it was kept -- a payload already in the ledger is not
        kept again. What it used to do is left exactly as it is: that record
        is what a boundary diff is made against, and only the monitor that
        reported the movement may change it.
        """
        identity = payload_id(payload)
        entry = self.entries.get(identity)
        if entry is not None:
            if not entry.signature:
                # Blanked by a re-baseline: this is the campaign re-deriving
                # what the payload does under the new oracle. Without this the
                # ledger never recovers -- every case stays "novel" forever
                # because no signature is ever recorded again.
                entry.signature = outcome.signature
                entry.kind = outcome.kind
                self._counts[outcome.signature] = self._counts.get(outcome.signature, 0) + 1
            return False
        if self._counts.get(outcome.signature, 0) >= MAX_PER_SIGNATURE:
            return False
        if outcome.signature not in self._counts and len(self._counts) >= MAX_SIGNATURES:
            self.saturated = True
            return False
        if edge_of:
            held = sum(
                1 for entry in self.entries.values()
                if entry.edge_of == edge_of and entry.signature == outcome.signature
            )
            cap = MAX_EDGE_EXEMPLARS
        else:
            held = self._counts.get(outcome.signature, 0)
            cap = MAX_EXEMPLARS
        if held >= cap and not self._displace(payload, outcome, edge_of):
            return False
        self._payloads[identity] = payload
        self.entries[identity] = LedgerEntry(
            signature=outcome.signature,
            kind=outcome.kind,
            first_seen=campaign,
            edge_of=edge_of,
        )
        self._counts[outcome.signature] = self._counts.get(outcome.signature, 0) + 1
        return True

    def reclassify(self, identity: str, outcome: Outcome) -> None:
        """Record that a payload already held now does something else.

        The one way an entry's signature may change after it is admitted, and
        it lives here because the entry is not the only thing that has to
        move: ``_counts`` backs ``known_signatures()``, the per-signature cap
        and the saturation ceiling. The monitor used to assign to
        ``entry.signature`` directly, which left the ledger saying one thing
        and the counts another -- a payload recorded as rejected while the
        count that decides novelty still read accepted.
        """
        entry = self.entries.get(identity)
        if entry is None or entry.signature == outcome.signature:
            return
        if self._counts.get(entry.signature):
            self._counts[entry.signature] -= 1
            if not self._counts[entry.signature]:
                del self._counts[entry.signature]
        entry.signature = outcome.signature
        entry.kind = outcome.kind
        self._counts[outcome.signature] = self._counts.get(outcome.signature, 0) + 1

    def _payload_size(self, identity: str) -> int:
        return len(self._payloads.get(identity, b""))

    def _displace(self, payload: bytes, outcome: Outcome, edge_of: str) -> bool:
        """Make room by dropping a larger payload that proves the same point.

        Without this the corpus is bounded in entries but not in bytes, and
        radamsa's repetition mutations exploit exactly that: a mutant grows,
        is retained because its signature is new, becomes the next
        generation's parent, and grows again. Measured from a 61-byte seed it
        reached 567 KB in eight generations -- and radamsa's cost scales with
        input size, so the loop makes itself slower as it runs.

        Keeping the smallest example of each signature bounds the corpus in
        bytes, keeps the gate replay fast, and hands triage the smallest
        reproduction rather than whichever one happened to arrive first.
        """
        candidates = [
            identity for identity, entry in self.entries.items()
            if entry.signature == outcome.signature
            and (not edge_of or entry.edge_of == edge_of)
        ]
        if not candidates:
            return False
        largest = max(candidates, key=self._payload_size)
        if self._payload_size(largest) <= len(payload):
            return False
        self._drop(largest)
        return True

    def _drop(self, identity: str) -> None:
        """Remove one payload and the ledger's memory of it."""
        entry = self.entries.pop(identity, None)
        if entry is None:
            return
        if self._counts.get(entry.signature):
            self._counts[entry.signature] -= 1
            if not self._counts[entry.signature]:
                del self._counts[entry.signature]
        self._payloads.pop(identity, None)

    def rebaseline(self) -> None:
        """Adopt the current oracle, discarding recorded signatures.

        The payloads are kept -- they are the expensive part and are still
        interesting inputs. Only the claim about what they *do* is dropped,
        because it was made by a different oracle. The next campaign
        re-derives it.
        """
        for entry in self.entries.values():
            entry.signature = ""
            entry.kind = ""
        self._counts = {}
        self.stale = False

    def _write_archive(self) -> None:
        """Rewrite the archive in one atomic step, holding only what the
        ledger still names.

        Written whole rather than appended to, because a payload displaced by
        a smaller one has to leave.

        This and the ledger are two renames under one lock. The lock keeps
        two campaigns from interleaving; it does nothing about a kill between
        the two writes, which can still leave a mixed pair. That is not
        claimed to be transactional -- it is detected on load instead, by
        :meth:`_check_archive_agrees`.
        """
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for identity in sorted(self.entries):
                payload = self._payloads.get(identity)
                if payload is not None:
                    archive.writestr(f"{identity}.bin", payload)
        _write_atomic(self.archive_path, buffer.getvalue())
        if self.legacy_dir.is_dir():
            for path in self.legacy_dir.glob("*.bin"):
                path.unlink()
            self.legacy_dir.rmdir()

    def save(self, campaign: Optional[Dict[str, object]] = None) -> None:
        """Commit the ledger, and the manifest of the run that produced it."""
        document = {
            "ledger_version": LEDGER_VERSION,
            "target": self.target.name,
            "fingerprint": self.target.fingerprint,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entries": {k: v.to_dict() for k, v in sorted(self.entries.items())},
        }
        with _locked(self.lock_path):
            self._write_archive()
            _write_atomic(self.ledger_path, json.dumps(document, indent=2).encode())
            if campaign:
                manifests = self.root / "campaigns"
                _write_atomic(
                    manifests / f"{campaign['campaign']}.json",
                    json.dumps(campaign, indent=2).encode(),
                )
                for stale in sorted(manifests.glob("*.json"))[:-KEEP_MANIFESTS]:
                    stale.unlink(missing_ok=True)
