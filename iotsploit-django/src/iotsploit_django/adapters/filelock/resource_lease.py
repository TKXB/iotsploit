"""`ResourceLeasePort` over OS file locks, shared with the Rust boundary-scan bridge.

One lock file per resource key, in a fixed per-user directory. The Flutter app's
Rust bridge (``ui/rust/src/probe_lock.rs``) derives the same directory and
file name, so a boundary scan and a campaign monitor on the same host refuse
each other instead of interleaving traffic on one probe.

The operating system drops a lock when its process dies, so a crashed holder
never leaves a stale lease behind. Who holds it goes in a separate ``.owner``
note beside the lock file, read only to explain a refusal. It cannot live in
the lock file itself: Windows locks are mandatory, so a second process could
not read a note under the lock it is being refused.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import IO, Optional

from iotsploit_core.ports.resource_lease import ResourceBusyError

if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
    import msvcrt

    def _try_lock(handle: IO) -> bool:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(handle: IO) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle: IO) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(handle: IO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_lock_dir() -> Path:
    override = os.environ.get("IOTSPLOIT_LOCK_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":  # pragma: no cover
        return Path(os.environ["LOCALAPPDATA"]) / "iotsploit" / "locks"
    return Path("/tmp") / f"iotsploit-{os.getuid()}" / "locks"


def owner_note_name(resource: str) -> str:
    """``usb:1366-1050298903/debug`` -> ``usb_1366-1050298903_debug.owner``."""
    return lock_file_name(resource)[:-len(".lock")] + ".owner"


def lock_file_name(resource: str) -> str:
    """``usb:1366-1050298903/debug`` -> ``usb_1366-1050298903_debug.lock``."""
    safe = "".join(char if char.isalnum() or char in "-." else "_" for char in resource)
    return f"{safe}.lock"


class FileResourceLease:
    def __init__(self, lock_dir: Optional[Path] = None, *, process: str = "iotsploit-python"):
        self._lock_dir = Path(lock_dir) if lock_dir is not None else default_lock_dir()
        self._process = process
        self._held: dict[str, tuple[str, IO]] = {}
        self._mutex = threading.Lock()

    @property
    def lock_dir(self) -> Path:
        return self._lock_dir

    def acquire(self, resource: str, owner: str) -> None:
        with self._mutex:
            held = self._held.get(resource)
            if held is not None:
                raise ResourceBusyError(resource, held[0])
            self._lock_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform != "win32":
                os.chmod(self._lock_dir, 0o700)
            note = self._lock_dir / owner_note_name(resource)
            handle = open(self._lock_dir / lock_file_name(resource), "a+")
            if not _try_lock(handle):
                handle.close()
                raise ResourceBusyError(resource, self._read_holder(note))
            try:
                note.write_text(json.dumps({
                    "resource": resource, "owner": owner, "pid": os.getpid(),
                    "process": self._process, "since": time.time(),
                }))
            except OSError:
                pass  # The lock is what matters; the note only explains refusals.
            self._held[resource] = (owner, handle)

    def release(self, resource: str, owner: str) -> None:
        with self._mutex:
            held = self._held.get(resource)
            if held is None or held[0] != owner:
                return
            del self._held[resource]
            handle = held[1]
            # Before unlocking: once unlocked, the note may be the next holder's.
            try:
                (self._lock_dir / owner_note_name(resource)).unlink(missing_ok=True)
            except OSError:
                pass  # A stale note is overwritten by the next holder.
            try:
                _unlock(handle)
            finally:
                handle.close()

    @staticmethod
    def _read_holder(note_path: Path) -> str:
        try:
            note = json.loads(note_path.read_text() or "{}")
        except (OSError, ValueError):
            note = {}
        owner = note.get("owner")
        if not owner:
            return "another process"
        process = note.get("process", "another process")
        return f"{owner} ({process}, pid {note.get('pid', '?')})"
