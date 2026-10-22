#!/usr/bin/env bash
#
# test-python-full.sh — commit-time Python quality gate
#
# This is the canonical command that AI agents and developers run before
# committing Python code, and what tools/git-hooks/pre-commit executes.
#
# Usage:
#   tools/testing/test-python-full.sh
#   tools/testing/test-python-full.sh -- -m "unit or contract"
#
# Exit codes:
#   0 — all checks passed
#   1 — at least one check failed
#
# The checks themselves live in tools/testing/run_gate.py, which is a single
# owner that also runs on Windows, where this script cannot. This file stays
# because it is the entrypoint referenced by AGENTS.md and the git hook; it
# forwards its arguments and its exit code and does nothing else.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POETRY="${POETRY:-poetry}"

exec $POETRY run python tools/testing/run_gate.py "$@"
