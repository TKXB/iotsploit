#!/usr/bin/env python3
"""Reject host-specific paths outside the adapters that own them."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "iotsploit-django/src/iotsploit_django/tools/adb_mgr.py": ("/data/local/tmp/",),
    "iotsploit-exploits/src/iotsploit_exploits/adb_check/adb_check.py": (
        "/dev/",
        "/sys/",
    ),
    "iotsploit-protocols/src/iotsploit_protocols/canbus/socketcan.py": (
        "/sys/class/net",
    ),
}
FORBIDDEN = ("/tmp/", "/dev/tty", "/sys/")


def main() -> None:
    violations = []
    for path in ROOT.glob("iotsploit-*/src/**/*.py"):
        if "tests" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        for literal in FORBIDDEN:
            if literal not in source:
                continue
            allowed = ALLOWED.get(relative, ())
            if not any(literal in value for value in allowed):
                violations.append(f"{relative}: contains {literal!r}")
    if violations:
        raise SystemExit("\n".join(violations))


if __name__ == "__main__":
    main()
