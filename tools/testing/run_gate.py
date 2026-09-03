#!/usr/bin/env python3
"""run_gate.py - the canonical Python quality gate, on every platform.

This owns the ordered list of checks. `test-python-full.sh` is a thin wrapper
around it so the documented bash entrypoint and the pre-commit hook keep
working, and CI calls it directly so Windows and macOS runners execute the same
steps a Linux developer does.

Usage:

    python tools/testing/run_gate.py
    python tools/testing/run_gate.py -- -m "unit or contract"

Everything after a lone `--` is forwarded to pytest, which is how the
cross-platform matrix narrows to the markers a runner without hardware or Redis
can honestly execute.

Exit codes:
  0 - all checks passed
  1 - at least one check failed (the first failure stops the run)

Test paths, import mode and markers live in the root pyproject; this script
deliberately does not duplicate that configuration.

Output is deliberately ASCII-only. A Windows console on a non-UTF-8 code
page (GBK on a Chinese install, for one) raises UnicodeEncodeError on box
drawing and emoji, which would fail the gate for the way it prints rather
than for anything it checked.

`test-wheel-installs.py` is not part of this gate. It builds ten wheels and
creates a virtualenv per package, which is minutes of work and needs the
network, so it stays a CI-only step.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTING_DIR = Path(__file__).resolve().parent


def _split_pytest_args(argv: list[str]) -> list[str]:
    """Everything after a lone `--` belongs to pytest."""
    if "--" not in argv:
        return []
    return argv[argv.index("--") + 1 :]


def _steps(pytest_args: list[str]) -> tuple[tuple[str, list[str]], ...]:
    python = sys.executable
    return (
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        # Before pytest: a module that will not import on this platform is a
        # collection error, which pytest reports far less clearly than this.
        ("import smoke", [python, str(TESTING_DIR / "import-all-packages.py")]),
        ("portability literals", [python, str(TESTING_DIR / "check-portability-literals.py")]),
        ("pytest", [python, "-m", "pytest", *pytest_args]),
    )


def main() -> int:
    pytest_args = _split_pytest_args(sys.argv[1:])

    for name, command in _steps(pytest_args):
        print(f"-- {name} ".ljust(66, "-"), flush=True)
        result = subprocess.run(command, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"\nFAILED: {name} (exit {result.returncode}).", flush=True)
            return 1
        print(flush=True)

    print("All checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
