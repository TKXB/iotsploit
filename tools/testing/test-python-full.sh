#!/usr/bin/env bash
#
# test-python-full.sh — commit-time Python quality gate
#
# Runs every deterministic, non-interactive check in order and exits with a
# non-zero status on the first failure. This is the canonical command that AI
# agents and developers must run before committing Python code.
#
# Usage:
#   tools/testing/test-python-full.sh
#
# Exit codes:
#   0 — all checks passed
#   1 — at least one check failed
#
# The exact test paths, import mode, markers, and exclusions live in root
# pytest configuration (pyproject.toml [tool.pytest.ini_options]). This
# script deliberately does not duplicate that configuration.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POETRY="${POETRY:-poetry}"

# ── Step 1: Ruff lint ──────────────────────────────────────────────────
echo "── ruff check ──────────────────────────────────────────────────"
$POETRY run ruff check .
echo

# ── Step 2: pytest ─────────────────────────────────────────────────────
echo "── pytest ─────────────────────────────────────────────────────"
$POETRY run pytest
echo

echo "✅ All checks passed."
