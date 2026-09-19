# iotsploit-fuzzer

Standalone fuzzer library extracted from `zeekr_sat_main`.

- **Package name (PyPI)**: `iotsploit-fuzzer`
- **Import name (Python)**: `iotsploit_fuzzer`

## Install (editable)

```bash
pip install -e iotsploit-fuzzer
```

## Notes

This package is being introduced to replace (and later deprecate) the in-repo `iot_protocol_fuzzer` module.



## Two things this package fuzzes

They are not the same job, and conflating them is how a fuzzing effort ends up
measuring the wrong thing.

**Outbound — the device under test.** CAN/UART/SPI payloads sent through a
wire harness at whatever is on the other end. Needs the rig. This is what
`CANHarness`, `UARTHarness` and `SPIHarness` do, driven from the Django UI.

**Inbound — our own parsers.** The same `Orchestrator`, pointed at a function
instead of an interface. Needs nothing but CPU, so it runs in CI and in the
commit gate. That is what follows.

## The parser loop

A campaign that is run once, reported and forgotten finds its last bug in week
two. What keeps producing information is the **error boundary** -- the line
between the inputs a parser accepts and the ones it rejects -- because every
refactor moves it and almost every move is unintended. Nothing in the test
suite asserts which ARXML files import or which ASC lines parse. The ledger is
that assertion, and it writes itself.

```bash
# What is in the registry
poetry run python -m iotsploit_fuzzer.core.parser_campaign --list

# One target, one campaign
poetry run python -m iotsploit_fuzzer.core.parser_campaign \
    --target canbus.scan_log --iterations 2000

# Everything, as a nightly run. Exits non-zero on a violation.
poetry run python -m iotsploit_fuzzer.core.parser_campaign --iterations 2000

# Replay the retained corpus and generate nothing. This is what the commit
# gate runs, via tests/test_parser_corpus_replay.py.
poetry run python -m iotsploit_fuzzer.core.parser_campaign --replay
```

A campaign reports exactly three things:

| Event | Means | Nightly |
|-------|-------|---------|
| `VIOLATION` | A contract broke: an undeclared exception, a hang, a resource limit, a broken round trip | Fails |
| `BOUNDARY_MOVED` | A payload the ledger knows now does something else. **Not necessarily a bug** -- a behaviour change somebody should confirm was intended | Reports |
| `NEW_REGION` | A signature this target has never produced. The corpus grew | Informational |

### Each parse runs in a process we are willing to lose

`ParserHarness` is a controller; the parse happens in a subprocess under
wall-clock, memory, output-size and payload-size limits. This is not
defensiveness. A parser that allocates until the host swaps cannot be
recovered from in-process -- `except MemoryError` runs only after the
allocation happened -- and a signal handler only runs at a bytecode boundary
the interpreter may never reach again. Worker death *is* the result.

Workers are batched and recycled rather than forked per payload, because a
spawn costs more than the parsing does. Anything that is not a plain accept or
reject is re-run alone in a fresh worker, three times, before it is believed:
an outcome that does not reproduce is reported as flaky and never enters the
corpus.

### The ledger is a contract, and it is versioned

`corpus/<target>/ledger.json` is tracked in git on purpose -- it is the loop's
memory, the gate's regression corpus, and a boundary movement arrives as a
JSON diff in the pull request that caused it. Each entry carries the payload's
content hash, its normalised outcome signature, and the campaign that first
saw it.

Signatures never contain a raw exception message: messages carry offsets, hex,
paths and quoted input, and comparing them would report thousands of movements
nobody caused. They also never contain a line number, for the same reason.

Changing a target's declared exception set, its adapter, or the signature
format changes its **fingerprint**, and a ledger recorded under a different
fingerprint is refused rather than diffed:

```bash
poetry run python -m iotsploit_fuzzer.core.parser_campaign \
    --target canbus.scan_log --rebaseline
```

Re-baselining keeps the payloads -- they are the expensive part -- and drops
only the claim about what they do, which the next campaign re-derives.

### The nightly run

`tools/testing/nightly-parser-fuzz.sh` runs one campaign against every target
and exits non-zero on a violation. Driven by cron rather than by the platform,
so that a night when Django or Redis is down is still a night the loop runs:

```cron
17 3 * * *  /path/to/repo/tools/testing/nightly-parser-fuzz.sh
```

The seed is the day of the year, so each night explores a different corner and
any night can be reproduced exactly. Logs land in
`artifacts/parser-fuzz-logs/`, which is git-ignored; the corpus it grows is
not, and committing that change is what carries the night's learning to
everyone else and puts it in the commit gate.

`--iterations` is the mutation budget. The retained corpus is replayed on top
of it rather than out of it -- a boundary movement is defined on a payload the
ledger already holds, so a corpus larger than the budget would otherwise stop
the campaign mutating at all.

Triage, when it fails: the log names the target, the payload hash and the
source line. `corpus/<target>/payloads/<hash>.bin` is the input. Fix the owner,
then `--replay` that target to confirm; the payload stays in the corpus, so
every commit from then on checks it.

### Adding a target

A registry entry in `harnesses/parser_targets.py`: the adapter that turns
bytes into a call, the exceptions the target's own docstring declares, and its
budget. `declared=()` means "never raises", which several of these promise.

Keeping those lists honest is ongoing work: a target that declares too much can
never report anything again.

### Known limits

- **Mutation is byte-level.** For the JSON-shaped targets (`canbus.from_target`,
  `canbus.decode_frame`) roughly 90% of mutants are not valid JSON and are
  skipped. Structure-aware mutation would fix it and has not been written.
- **`someip.sd_parse` has almost no observable boundary** from random bytes: it
  catches everything and returns a list, so nearly every input looks the same.
  It needs seeds that are valid SD datagrams to say anything.
- **Novelty by outcome is a weak fitness signal** next to coverage guidance. It
  plateaus. Real coverage feedback needs `sys.monitoring` (3.12+); on 3.10 it
  would cost a 10-30x slowdown.
