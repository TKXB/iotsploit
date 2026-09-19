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

### Two mutators, and when to use which

The built-in mutator is byte-level and seeded: bit flips, span deletes and
duplicates, splices between seeds, and a digit-run replacement aimed at the
"0-7 becomes 0-10000000" class of defect. It is the default because it is
deterministic and costs about 0.01 ms per mutant.

`--radamsa` uses [radamsa](https://gitlab.com/akihe/radamsa) instead, when the
binary is on `PATH`:

```bash
poetry run python -m iotsploit_fuzzer.core.parser_campaign --radamsa --iterations 2000
```

radamsa reads the *shape* of its input, so a mutated JSON document is usually
still JSON. Measured on this registry, at 2000 mutants per target:

| Target | built-in skip rate | radamsa skip rate |
|--------|-------------------|-------------------|
| `canbus.decode_frame` | 92.8% | **54.5%** |
| `canbus.from_target` | 90.0% | **76.2%** |
| `django.parse_dbc` | **7.5%** | 23.4% |
| `exploits.nmap_grepable` | **7.0%** | 21.6% |

Skipped means the adapter could not build an input at all, so the parser never
ran. radamsa is far better on the structured targets and *worse* on the text
ones, where it injects invalid UTF-8 more freely than the byte mutator does.
It also found more distinct behaviours on the text targets anyway.

They are complementary, and the reason to keep both is not hedging: the two
found different defects. radamsa builds deep nesting and long repetitions that
a byte mutator reaches only by accident, which is how the `RecursionError` in
the frame composer's JSON entry point was found. The built-in mutator's
`_bump_number` targets a class radamsa spreads its effort over.

The cost is real. radamsa spawns a process per batch and its cost scales with
input size, which on a grown corpus is **~75 ms per mutant against 0.01 ms**.
Its mutants also inflate: left alone they grow until they hit
`payload_max_bytes`. Run it with a smaller `--iterations` than the built-in,
and expect a nightly radamsa pass to take minutes rather than seconds.

`--seed` is passed to radamsa's own `-s`, so a radamsa campaign reproduces
exactly and the manifest's `mutator: radamsa/<seed>` is a real record. Lineage
is preserved too -- the generator drives one parent at a time rather than
handing radamsa the whole pool, so edge retention still works.

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

### Pointing it at something yourself

**Try a function now, without editing anything.** Write an adapter -- one
function taking `bytes` and calling the thing you want to test -- put it
anywhere on `PYTHONPATH`, and name it with `--adapter`:

```python
# ~/mytargets/mine.py
import os, tempfile

def logic_capture(payload: bytes):
    """One surface, one adapter. Raise nothing yourself; just make the call."""
    from iotsploit_drivers.logic.protocol import read_logic_analyzer_data_from_file

    handle, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(handle, "wb") as fh:
        fh.write(payload)
    try:
        return read_logic_analyzer_data_from_file(path)
    finally:
        os.unlink(path)
```

```bash
PYTHONPATH=~/mytargets poetry run python -m iotsploit_fuzzer.core.parser_campaign \
    --adapter mine:logic_capture \
    --declared "builtins:ValueError,builtins:TypeError" \
    --seed-file ~/good_capture.json \
    --iterations 500
```

The corpus goes to a temporary directory and is thrown away, so an experiment
leaves no ledger for the gate to replay. Pass `--root ~/my-corpus` to keep it.

**`--declared` is the whole experiment.** It is the contract you are holding
the function to, and getting it wrong is the usual reason a run is useless:

| You declare | You are asking |
|-------------|----------------|
| `--declared ""` | "this never raises" -- right for a decoder that returns a failure object, wrong for a validator |
| `--declared "builtins:ValueError"` | "it rejects bad input by raising ValueError, and nothing else escapes" |
| everything it might raise | nothing. A target that declares too much can never report anything again |

Run the example above with `--declared ""` and it reports 33 violations in 151
seconds; with the line shown, 0 in half a second. Same code, same inputs. Start
from what the function's own docstring promises -- and if it promises nothing,
deciding what it *should* promise is the useful half of the exercise.

**Seeds matter as much.** `--seed-file` should be a real, valid input. Mutating
a good capture finds things; mutating `b""` explores the first ten bytes of the
parser and stops.

### Making it permanent

When a scratch target earns its place, move it into
`harnesses/parser_targets.py` -- the adapter next to the others, and a
`ParseTarget` entry in the registry list:

```python
ParseTarget(
    name="drivers.logic_capture",
    adapter=f"{_HERE}:logic_capture",
    declared=("builtins:ValueError", "builtins:TypeError"),
    seeds=(_CAPTURE_SEED,),
    budget_seconds=5.0,
),
```

`tests/test_parser_targets.py` then checks it on every commit: that the adapter
and every declared name resolve, and that at least one seed actually reaches
the target instead of being skipped. Once it has a corpus, the gate replays it.

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
