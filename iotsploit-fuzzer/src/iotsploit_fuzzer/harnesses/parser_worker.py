"""The disposable half of the parser harness: one process that may not survive.

Run as ``python -m iotsploit_fuzzer.harnesses.parser_worker --target NAME``.

Everything a parse can do to a process it does to *this* process. A parser
that allocates until the host swaps, blocks in a C call no signal reaches, or
takes a native library down with it cannot be recovered from in-process: an
``except MemoryError`` runs only after the allocation already happened, and a
``SIGALRM`` handler only runs at a bytecode boundary the interpreter may never
reach again. So the parse runs here, behind the kernel's own limits, and the
controller in :mod:`.parser_harness` treats this process's death as a result.

The protocol is one JSON object per line in each direction, over stdin and a
private result descriptor. stdout is redirected to stderr on the way in, so a
target that prints cannot corrupt the channel.
"""

from __future__ import annotations

import argparse
import base64
import faulthandler
import importlib
import json
import os
import sys
import traceback
from typing import Any, Callable, Tuple

from ..analysis.outcome import (
    ACCEPT,
    LIMIT,
    REJECT,
    SKIP,
    VIOLATE,
    Outcome,
    describe_shape,
    normalize_reason,
)
from .parser_targets import MetamorphicError, Skip

try:  # POSIX only; on Windows the controller's wall clock is the only limit.
    import resource
except ImportError:  # pragma: no cover - exercised only off POSIX
    resource = None

_MAX_DETAIL = 400


def resolve(dotted: str) -> Any:
    """Import ``module:attribute``. Deliberately late, and in this process."""
    module, _, attribute = dotted.partition(":")
    return getattr(importlib.import_module(module), attribute)


def apply_limits(memory_mb: int, scratch_kb: int, cpu_seconds: int) -> None:
    """Hand the kernel the budget, after the imports the setup needs.

    Applied after resolution on purpose: the limit is on the parse, not on
    loading cantools. The CPU ceiling is cumulative and generous -- it exists
    for the orphaned case, where the controller died and nothing else will
    ever stop this process.

    ``scratch_kb`` bounds files rather than the reply channel, and the two are
    not the same number. An adapter that hands its target a path has to write
    the payload down first, so sizing this from the reply cap made a large
    payload fail inside the adapter with ``[Errno 27] File too large`` --
    reported as the target violating its contract, which it had not.
    """
    if resource is None:
        return
    for name, limit in (
        ("RLIMIT_AS", memory_mb * 1024 * 1024),
        ("RLIMIT_FSIZE", scratch_kb * 1024),
        ("RLIMIT_CPU", cpu_seconds),
        ("RLIMIT_CORE", 0),
    ):
        attribute = getattr(resource, name, None)
        if attribute is None:
            continue
        try:
            soft, hard = resource.getrlimit(attribute)
            ceiling = limit if hard in (resource.RLIM_INFINITY, -1) else min(limit, hard)
            resource.setrlimit(attribute, (ceiling, hard))
        except (ValueError, OSError):
            continue


def classify(adapter: Callable[[bytes], Any], declared: Tuple[type, ...], payload: bytes) -> Outcome:
    """Run one parse and say which side of the contract it landed on."""
    try:
        result = adapter(payload)
    except Skip as error:
        return Outcome(kind=SKIP, detail=str(error)[:_MAX_DETAIL])
    except MetamorphicError as error:
        return Outcome(
            kind=VIOLATE,
            exception=type(error).__name__,
            reason=normalize_reason(str(error), payload),
            metamorphic="broken",
            detail=str(error)[:_MAX_DETAIL],
            site=_site(),
        )
    except declared as error:
        return Outcome(
            kind=REJECT,
            exception=type(error).__name__,
            reason=normalize_reason(str(error), payload),
            detail=str(error)[:_MAX_DETAIL],
        )
    except MemoryError as error:
        # Reported rather than raised, but the process is not trustworthy
        # afterwards -- the controller retires the worker on any finding.
        return Outcome(
            kind=LIMIT,
            exception="MemoryError",
            reason="memory",
            detail=str(error)[:_MAX_DETAIL],
            site=_site(),
        )
    except BaseException as error:  # noqa: BLE001 - the whole point of the oracle
        return Outcome(
            kind=VIOLATE,
            exception=type(error).__name__,
            reason=normalize_reason(str(error), payload),
            detail=str(error)[:_MAX_DETAIL],
            site=_site(),
        )
    return Outcome(kind=ACCEPT, shape=describe_shape(result))


def _site() -> str:
    """Where it escaped from, for the report. Never part of a signature: a
    line number moves under any edit, and a ledger that compared it would call
    every reformat a boundary movement."""
    frames = traceback.extract_tb(sys.exc_info()[2])
    if not frames:
        return ""
    last = frames[-1]
    return f"{os.path.basename(last.filename)}:{last.lineno}"


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, help="module:function")
    parser.add_argument("--declared", default="", help="comma-separated module:Exception")
    parser.add_argument("--memory-mb", type=int, default=768)
    parser.add_argument("--scratch-kb", type=int, default=4096)
    parser.add_argument("--cpu-seconds", type=int, default=600)
    args = parser.parse_args(argv)

    # Claim the channel before anything the target can reach runs, then point
    # fd 1 at stderr: a target that prints is noisy, not corrupting.
    results = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    faulthandler.enable()

    adapter = resolve(args.adapter)
    declared = tuple(resolve(name) for name in args.declared.split(",") if name)
    apply_limits(args.memory_mb, args.scratch_kb, args.cpu_seconds)

    # The handshake separates a broken registry entry from a broken parser.
    # Without it, a target naming an exception that does not exist kills every
    # worker at startup and the campaign reports one violation per payload --
    # a configuration error wearing the costume of a finding.
    results.write(json.dumps({"ready": True}) + "\n")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        payload = base64.b64decode(request["payload"])
        outcome = classify(adapter, declared, payload)
        results.write(json.dumps(outcome.to_dict()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
