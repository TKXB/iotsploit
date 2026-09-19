"""The surviving half of the parser harness: a controller over disposable workers.

One :class:`ParserHarness` drives one target through a subprocess that it is
willing to lose. The worker enforces memory, output and CPU ceilings on
itself; the controller enforces the wall clock, because a process stuck in a
call no signal reaches can only be ended from outside. A worker that dies for
any reason is a result -- ``violate`` -- rather than an error the campaign has
to recover from.

Workers are batched and recycled rather than forked per payload: a spawn costs
tens of milliseconds, which at campaign scale is more time than the parsing.
Attribution survives batching because the controller knows which payload is in
flight, and anything that is not a plain accept or reject is re-run **solo** in
a fresh worker before it is believed.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from typing import List, Optional, Tuple

from ..analysis.outcome import ACCEPT, LIMIT, REJECT, SKIP, TIMEOUT, VIOLATE, Outcome
from .base import HarnessResult, ProtocolHarness
from .parser_targets import ParseTarget

logger = logging.getLogger("fuzzer.parser_harness")

#: Payloads one worker handles before it is retired. Bounds the blast radius
#: of a leak: without it, payload 500 pays for payload 3's allocation and the
#: ledger records the boundary in the wrong place.
DEFAULT_QUOTA = 200

#: How many times a candidate is replayed before it is believed. An outcome
#: that does not reproduce is reported as flaky rather than promoted -- a
#: corpus built from one-off results is a corpus of noise.
DEFAULT_REPEATS = 3

#: How long a worker gets to import its target and say it is ready. Generous
#: because a target pulling in scapy or cantools pays for it here, once per
#: worker rather than once per payload.
STARTUP_SECONDS = 60.0


class WorkerStartupError(RuntimeError):
    """A worker could not reach its target at all.

    A registry entry naming an adapter or an exception that does not exist is
    a configuration error, and has to read as one. Left undetected it kills
    every worker before the first payload, and the campaign reports one
    violation per payload against a parser it never ran.
    """


class _Worker:
    """One subprocess, and the thread that keeps its output bounded."""

    def __init__(self, target: ParseTarget, python: str, cpu_seconds: int) -> None:
        self.target = target
        self.stderr = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            [
                python,
                "-m",
                "iotsploit_fuzzer.harnesses.parser_worker",
                "--adapter", target.adapter,
                "--declared", ",".join(target.declared),
                "--memory-mb", str(target.memory_mb),
                "--output-kb", str(target.output_kb),
                "--cpu-seconds", str(cpu_seconds),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            **({"start_new_session": True} if os.name == "posix" else {}),
        )
        self.served = 0
        self._queue: "queue.Queue[Tuple[str, bytes]]" = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self._await_ready()

    def _await_ready(self) -> None:
        try:
            status, line = self._queue.get(timeout=STARTUP_SECONDS)
        except queue.Empty:
            status, line = ("timeout", b"")
        if status == "line" and json.loads(line or b"{}").get("ready"):
            return
        detail = self.stderr_tail(600) or status
        self.kill()
        raise WorkerStartupError(f"{self.target.name}: worker did not start\n{detail}")

    def _pump(self) -> None:
        """Read replies in bounded chunks.

        A blocking ``readline`` would buffer a target that emits megabytes
        without a newline straight into the controller, which is the one
        process that must not run out of memory.
        """
        cap = self.target.output_kb * 1024
        buffer = bytearray()
        try:
            while True:
                chunk = self.proc.stdout.read1(65536)
                if not chunk:
                    break
                buffer += chunk
                if b"\n" in buffer:
                    line, _, rest = bytes(buffer).partition(b"\n")
                    buffer = bytearray(rest)
                    self._queue.put(("line", line))
                elif len(buffer) > cap:
                    self._queue.put(("oversize", b""))
                    break
        except (OSError, ValueError):
            pass
        finally:
            self._queue.put(("eof", b""))

    def ask(self, payload: bytes, budget: float) -> Tuple[str, bytes]:
        """Send one payload and wait out its budget. Never raises."""
        try:
            self.proc.stdin.write(
                json.dumps({"payload": base64.b64encode(payload).decode()}).encode() + b"\n"
            )
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            return ("eof", b"")
        self.served += 1
        try:
            return self._queue.get(timeout=budget)
        except queue.Empty:
            return ("timeout", b"")

    def stderr_tail(self, limit: int = 300) -> str:
        try:
            self.stderr.seek(0)
            return self.stderr.read()[-limit:].decode("utf-8", "replace").strip()
        except (OSError, ValueError):
            return ""

    def kill(self) -> None:
        """End the worker and anything it started."""
        if self.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                else:  # pragma: no cover - Windows has no process group kill here
                    self.proc.kill()
            except (OSError, ProcessLookupError):
                pass
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL is not refused
            pass
        try:
            self.stderr.close()
        except OSError:
            pass


class ParserHarness(ProtocolHarness):
    """Drive one parse target, one payload at a time, and outlive it."""

    def __init__(
        self,
        target: ParseTarget,
        *,
        python: Optional[str] = None,
        quota: int = DEFAULT_QUOTA,
        repeats: int = DEFAULT_REPEATS,
    ) -> None:
        self.target = target
        self.python = python or sys.executable
        self.quota = max(1, quota)
        self.repeats = max(1, repeats)
        self._worker: Optional[_Worker] = None
        #: Set by :meth:`evaluate` when a finding did not reproduce.
        self.flaky: List[Tuple[bytes, List[str]]] = []

    # -- lifecycle ---------------------------------------------------------

    def _spawn(self) -> _Worker:
        cpu = int(self.target.budget_seconds * self.quota) + 60
        return _Worker(self.target, self.python, cpu)

    def _retire(self) -> None:
        if self._worker is not None:
            self._worker.kill()
            self._worker = None

    def close(self) -> None:
        self._retire()

    def __enter__(self) -> "ParserHarness":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- one parse ---------------------------------------------------------

    def _run_once(self, payload: bytes, worker: _Worker) -> Outcome:
        """One payload through one worker, with every failure mode named."""
        status, line = worker.ask(payload, self.target.budget_seconds)
        if status == "line":
            try:
                return Outcome.from_dict(json.loads(line))
            except (ValueError, TypeError) as error:
                return Outcome(
                    kind=VIOLATE, exception="ProtocolError",
                    reason="unreadable worker reply", detail=str(error)[:200],
                )
        if status == "timeout":
            return Outcome(
                kind=TIMEOUT, reason="wall clock",
                detail=f"no reply within {self.target.budget_seconds}s",
            )
        if status == "oversize":
            return Outcome(
                kind=LIMIT, reason="output", detail=f"over {self.target.output_kb} KB",
            )
        # EOF: the worker is gone. Its exit status says how.
        worker.proc.wait(timeout=5)
        code = worker.proc.returncode
        named = f"signal {signal.Signals(-code).name}" if code and code < 0 else f"exit {code}"
        tail = worker.stderr_tail()
        return Outcome(
            kind=VIOLATE, exception="WorkerDied", reason=f"worker died, {named}",
            detail=(tail or named)[:400],
        )

    def evaluate(self, payload: bytes) -> Outcome:
        """Classify one payload, confirming anything that is not routine.

        A plain accept or reject is taken at its word. Everything else -- a
        violation, a timeout, a resource limit -- is re-run in a fresh solo
        worker :attr:`repeats` times, so that a result caused by the payload
        before it, or by the host being briefly busy, cannot enter the ledger.
        """
        if len(payload) > self.target.payload_max_bytes:
            return Outcome(
                kind=SKIP, reason="payload over limit",
                detail=f"{len(payload)} bytes > {self.target.payload_max_bytes}",
            )

        if self._worker is None or self._worker.served >= self.quota:
            self._retire()
            self._worker = self._spawn()

        outcome = self._run_once(payload, self._worker)
        if outcome.kind in (ACCEPT, REJECT, SKIP):
            return outcome

        # The worker is no longer trustworthy: it either died or was left
        # holding whatever the parse allocated.
        self._retire()
        return self.confirm(payload, outcome)

    def confirm(self, payload: bytes, first: Optional[Outcome] = None) -> Outcome:
        """Replay a payload alone until its signature is believable.

        Returns the majority outcome. When the replays disagree the result is
        reported as flaky and is deliberately *not* a finding: an intermittent
        result says something about the host, and calling it a boundary
        movement would poison every future diff.
        """
        seen: List[Outcome] = [first] if first is not None else []
        for _ in range(self.repeats):
            worker = self._spawn()
            try:
                seen.append(self._run_once(payload, worker))
            finally:
                worker.kill()

        tally = Counter(outcome.signature for outcome in seen)
        signature, count = tally.most_common(1)[0]
        winner = next(o for o in seen if o.signature == signature)
        if count < self.repeats:
            self.flaky.append((payload, [o.signature for o in seen]))
            logger.warning(
                "flaky outcome for %s: %s", self.target.name, dict(tally)
            )
            return Outcome(
                kind=SKIP, reason="flaky",
                detail="; ".join(f"{sig} x{n}" for sig, n in tally.items())[:400],
            )
        return winner

    # -- ProtocolHarness ---------------------------------------------------

    def execute(self, payload: bytes) -> HarnessResult:
        """The seam the existing Orchestrator drives."""
        outcome = self.evaluate(payload)
        return HarnessResult(
            ok=outcome.kind in (ACCEPT, REJECT, SKIP),
            crashed=outcome.kind in (VIOLATE, LIMIT),
            timeout=outcome.kind == TIMEOUT,
            info=outcome.signature,
            # Only a finding is an error. A declared rejection is the parser
            # working, and reporting it as an error made a campaign against a
            # strict parser look like a campaign against a broken one.
            error=outcome.detail if outcome.is_finding else None,
            site=outcome.site or None,
            response=None,
        )
