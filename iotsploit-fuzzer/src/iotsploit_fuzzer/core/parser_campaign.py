"""One campaign against one parse target, and the record it leaves behind.

This is the middle loop: the inner loop (generate, execute, classify) is the
existing :class:`~iotsploit_fuzzer.core.orchestrator.Orchestrator`, and the
outer loop is a human triaging what this reports. What it adds is memory --
campaign N+1 starts from campaign N's corpus and ledger rather than from zero.

Two modes:

``run``
    Mutate, classify, diff against the ledger, update the corpus. Minutes.
    Nightly.
``replay``
    Drive the retained corpus through the harness and generate nothing. Fast
    and deterministic, which is what lets it sit in the commit gate: every
    input the loop has ever found interesting is checked on every commit,
    while the generation that would make the gate flaky stays out of it.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..analysis.corpus import CorpusStore
from ..analysis.logger import TestLogger
from ..generators.corpus_generator import CorpusGenerator
from ..harnesses.parser_harness import ParserHarness, WorkerStartupError
from ..harnesses.parser_targets import REGISTRY, ParseTarget
from ..monitoring.boundary_monitor import BoundaryMonitor
from .config import CampaignConfig, EventType
from .orchestrator import Orchestrator

logger = logging.getLogger("fuzzer.parser_campaign")

#: Tracked in git on purpose. ``artifacts/`` is ignored, so a corpus there
#: would be per-machine: the gate would replay nothing on a fresh clone and
#: the loop would have no memory across the people who run it. Kept here, the
#: ledger also diffs in review -- a boundary movement arrives as a JSON change
#: in the pull request that caused it.
DEFAULT_CORPUS_ROOT = Path(__file__).resolve().parents[3] / "corpus"


class StaleLedgerError(RuntimeError):
    """The ledger was recorded against a different oracle.

    Raised rather than worked around. Re-baselining silently would erase the
    history that makes a boundary diff worth anything, and diffing anyway
    would report every entry as a movement nobody caused.
    """


def code_revision() -> str:
    """The commit a campaign ran against, so a finding can be located in time."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def campaign_id(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def manifest(
    target: ParseTarget, harness: ParserHarness, *, campaign: str, seed: int,
    mutator: str, iterations: int,
) -> Dict[str, Any]:
    """Everything needed to run this campaign again and get this answer again."""
    return {
        "campaign": campaign,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": target.name,
        "adapter": target.adapter,
        "adapter_version": target.adapter_version,
        "fingerprint": target.fingerprint,
        "declared": list(target.declared),
        "code_revision": code_revision(),
        "python": sys.version.split()[0],
        "generator_seed": seed,
        "mutator": mutator,
        "iterations": iterations,
        "limits": {
            "budget_seconds": target.budget_seconds,
            "memory_mb": target.memory_mb,
            "output_kb": target.output_kb,
            "payload_max_bytes": target.payload_max_bytes,
            "worker_quota": harness.quota,
            "confirm_repeats": harness.repeats,
        },
    }


def replay(target: ParseTarget, *, root: Path | str = DEFAULT_CORPUS_ROOT) -> List[Dict[str, Any]]:
    """Re-run every retained payload. Returns the findings, newest first.

    Generation is deliberately absent: the gate has to be deterministic, and
    the regression protection comes from the corpus, not from new inputs.
    """
    store = CorpusStore(root, target)
    findings: List[Dict[str, Any]] = []
    with ParserHarness(target) as harness:
        for identity, payload in store.payloads():
            outcome = harness.evaluate(payload)
            if outcome.is_finding:
                findings.append(
                    {
                        "target": target.name,
                        "payload": identity,
                        "signature": outcome.signature,
                        "detail": outcome.detail,
                        "site": outcome.site,
                    }
                )
    return findings


def run(
    target: ParseTarget,
    *,
    iterations: int = 500,
    root: Path | str = DEFAULT_CORPUS_ROOT,
    seed: int = 0,
    radamsa: Any = None,
    rebaseline: bool = False,
    event_callback: Optional[Callable[[EventType, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Run one campaign and commit what it learned."""
    store = CorpusStore(root, target)
    if store.stale:
        if not rebaseline:
            raise StaleLedgerError(
                f"{target.name}: ledger was recorded against a different oracle "
                f"(now {target.fingerprint}). Re-run with rebaseline=True to adopt "
                f"the current one; the payloads are kept either way."
            )
        store.rebaseline()

    identity = campaign_id()
    generator = CorpusGenerator(store, seed=seed, radamsa=radamsa)
    harness = ParserHarness(target)
    monitor = BoundaryMonitor(store, identity, generator=generator, emit=event_callback)
    record = manifest(
        target, harness, campaign=identity, seed=seed,
        mutator="radamsa" if radamsa is not None else f"builtin/{seed}",
        iterations=iterations,
    )

    started = time.time()
    try:
        Orchestrator(
            generator=generator,
            harness=harness,
            monitor=monitor,
            # The corpus store owns retention; a second copy of every payload
            # under artifacts/ is the graveyard this loop exists to replace.
            logger_backend=TestLogger(str(Path(root) / target.name / "cases"),
                                      keep=lambda payload, result: False),
            config=CampaignConfig(iterations=iterations, event_callback=event_callback),
        ).run()
    finally:
        harness.close()
        record.update(
            {
                "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "elapsed_seconds": round(time.time() - started, 1),
                "stats": monitor.get_stats(),
                "violations": monitor.violations,
                "boundary_moves": monitor.boundary_moves,
                "new_regions": monitor.new_regions[:50],
                "flaky": monitor.flaky,
            }
        )
        store.save(record)
    return record


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a parser fuzzing campaign.")
    parser.add_argument("--target", action="append", help="registry name; repeatable")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--root", default=str(DEFAULT_CORPUS_ROOT))
    parser.add_argument("--replay", action="store_true", help="corpus only, no generation")
    parser.add_argument("--rebaseline", action="store_true", help="adopt a changed oracle")
    parser.add_argument("--list", action="store_true", help="print the registry and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.list:
        for name, target in REGISTRY.items():
            print(f"{name:32} {target.fingerprint}  {target.adapter}")
        return 0

    names = args.target or list(REGISTRY)
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        parser.error(f"unknown target(s): {', '.join(unknown)}")

    failed = False
    for name in names:
        target = REGISTRY[name]
        if args.replay:
            findings = replay(target, root=args.root)
            print(f"{name:32} replay: {len(findings)} finding(s)")
            for finding in findings:
                print(f"    {finding['signature']}  {finding['payload']}  {finding['detail'][:80]}")
            failed = failed or bool(findings)
            continue
        try:
            report = run(
                target, iterations=args.iterations, root=args.root,
                seed=args.seed, rebaseline=args.rebaseline,
            )
        except (StaleLedgerError, WorkerStartupError) as error:
            print(f"{name:32} SKIPPED: {error}")
            failed = True
            continue
        stats = report["stats"]
        print(
            f"{name:32} {report['elapsed_seconds']:6.1f}s  "
            f"violations={stats['violations']} moved={stats['boundary_moves']} "
            f"new={stats['new_regions']} flaky={stats['flaky']} "
            f"corpus={stats['corpus_size']}"
            + ("  SATURATED: the result shape is too fine-grained" if stats["saturated"] else "")
        )
        for finding in report["violations"]:
            print(f"    VIOLATION {finding['signature']}  {finding['site']}  {finding['detail'][:80]}")
        for move in report["boundary_moves"]:
            print(f"    MOVED     {move['was']}  ->  {move['signature']}")
        failed = failed or bool(report["violations"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
