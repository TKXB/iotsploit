#!/usr/bin/env bash
#
# nightly-parser-fuzz.sh — one parser fuzzing campaign against every target
#
# Driven by cron rather than by the platform, so that a night when Django or
# Redis is down is still a night the loop runs. Install with:
#
#   crontab -e
#   17 3 * * *  /home/tkxb/HDD/Projects/zeekr_sat_main-master/tools/testing/nightly-parser-fuzz.sh
#
# Exit codes:
#   0 — no violations. The ledger and corpus may still have grown
#   1 — at least one contract broke. The log names the payload hash, and the
#       payload itself is in iotsploit-fuzzer/corpus/<target>/payloads/
#
# A BOUNDARY_MOVED line does not fail the run. It means a payload the ledger
# knows now does something else, which wants a human to say whether it was
# intended -- not a machine to decide it was wrong.
#
# The corpus this writes is tracked in git. Review and commit the change; that
# is what carries the night's learning to everyone else, and what makes the
# commit gate replay it.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POETRY="${POETRY:-/home/tkxb/.local/bin/poetry}"
ITERATIONS="${ITERATIONS:-5000}"
SEED="${SEED:-$(date +%j)}"          # day of year: a different corner each night
LOG_DIR="${LOG_DIR:-$REPO_ROOT/artifacts/parser-fuzz-logs}"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

# radamsa is the mutator and is not installed by default. Checked here so a
# cron failure names the cause in the first line of the log.
if ! command -v radamsa >/dev/null 2>&1; then
    echo "$(date -Is) radamsa is not on PATH; campaigns cannot run." | tee -a "$LOG"
    echo "  git clone --depth 1 https://gitlab.com/akihe/radamsa" | tee -a "$LOG"
    echo "  cd radamsa && make && make install PREFIX=\$HOME/.local" | tee -a "$LOG"
    exit 1
fi

{
    echo "=== $(date -Is) rev $(git rev-parse --short HEAD) seed $SEED iterations $ITERATIONS"
    "$POETRY" run python -m iotsploit_fuzzer.core.parser_campaign \
        --iterations "$ITERATIONS" --seed "$SEED"
    status=$?
    echo "=== exit $status"
    exit $status
} 2>&1 | tee -a "$LOG"

exit "${PIPESTATUS[0]}"
