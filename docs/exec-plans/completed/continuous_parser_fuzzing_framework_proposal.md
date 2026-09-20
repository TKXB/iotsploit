# Continuous Parser Fuzzing — A Loop, Not A Campaign

## Status

- **State:** **Implemented** on 2026-09-19, branch `feat/parser-fuzzing-loop`.
  Section 9 records what shipped and where the design changed. The text below
  it is the proposal as written, kept unedited so the changes are legible
- **Superseded originally:** Proposal. Nothing implemented
- **Draft date:** 2026-09-18
- **Supersedes:** section 4 of `parser_robustness_fuzzing_proposal.md` (the
  one-shot harness). Sections 1–3 of that document — the surface map and the
  three defects it found — still stand and are the seed corpus for this one
- **Basis:** the existing `iotsploit-fuzzer` engine read at `dev` `e3d8c96`,
  plus the state of `artifacts/` after five real campaigns
- **Estimated effort:** ~3 days to a running loop; see section 7
- **Decision owner:** User
- **Blocked on:** three decisions in section 8

## 9. What shipped, and where the design changed

Five changes were made to the design before it was built, all of them
hardening. Each is here because the proposal's own evidence argued for it.

### 9.1 The parse runs in a process we are willing to lose

Section 4.1 claimed that running in-process gives `crashed` an honest meaning
"because the target is a function in the same process". That is backwards, and
the proposal disproves it three paragraphs later: its own
`parse_target_bits` example reaches `MemoryError` at 543 MB under a cap and
"tens of gigabytes" without one. `except MemoryError` runs only after the
allocation happened, a `SIGALRM` handler runs only at a bytecode boundary the
interpreter may never reach again, and a native crash takes the interpreter
with it. A wall-clock budget cannot recover any of those in-process.

So `ParserHarness` is a **controller**, and the parse happens in a subprocess
under wall-clock, memory (`RLIMIT_AS`), output (`RLIMIT_FSIZE`), CPU and
payload-size limits. Worker death is a result, not an error to recover from.
Verified against a target that allocates without bound, one that spins, one
that blocks in `sleep`, one that segfaults, one that calls `os._exit`, one that
writes without limit, and one that leaves a child process behind: all eight
classified, the controller survived each, and the process group took the
grandchild with it.

Workers are **batched and recycled** rather than forked per payload -- a spawn
costs more than the parsing, and per-payload forking would have made the
77,000-input campaign an hour of `fork`. Attribution survives because the
controller knows which payload is in flight, and anything that is not a plain
accept or reject is re-run solo in a fresh worker.

### 9.2 Retention keys on a behaviour signature, not an outcome class

Section 4.2's rule -- keep a payload when it produces "an outcome class this
target has never produced before" -- saturates at two entries per target,
which is not an error boundary. What is retained instead is a **signature**:
kind, exception, normalised reason, normalised result shape, metamorphic
result. Both sides of a mutation edge are kept when one mutation crosses the
accept/reject line, since a single payload does not locate a boundary.

Every retention path is capped: per signature, per edge pair, and an absolute
ceiling per signature because a signature reachable from many parents escapes
the first two. Measured on `fuzzer.parse_target_bits`: 6,400 inputs across
eight campaigns converge to 13 signatures and 63 payloads, with campaigns three
onward adding nothing.

### 9.3 The ledger is versioned, and messages are never compared

Raw exception messages carry offsets, hex, paths and quoted input. Worse, the
messages here *quote the fuzzer's own payload*, and a payload containing an
apostrophe shifts the quote pairing so that the wrong span is scrubbed: an
early build produced 690 distinct "reasons" for a parser with six error
messages, and a corpus of 1,166 payloads still growing. A reason code is now
the message's leading words with the payload's own words removed.

Each ledger entry carries the target, the payload's content hash, the
normalised signature, and the campaign that first saw it, under a
**fingerprint** of the oracle -- the adapter, its version, the declared
exception set, and the signature format version. A ledger recorded under a
different fingerprint is refused rather than diffed, and re-baselining is an
explicit flag that keeps the payloads and drops only the claims.

### 9.4 Nothing is promoted until it reproduces

Every non-routine outcome is replayed three times in fresh solo workers.
Disagreement is reported as `FLAKY` and never enters the corpus. Each campaign
writes a manifest: generator seed, mutator, code revision, Python version,
target fingerprint, declared set, and every worker limit.

### 9.5 Persistence is crash-safe

Ledger and payload writes are `fsync`-then-`os.replace`, under a per-target
lock. Verified by `SIGKILL`ing a campaign mid-run: the previous ledger stayed
valid, no partial files were left, and the next campaign ran against it. The
existing `artifacts/` was tarred once to `artifacts-legacy-2026-09-19.tar.gz`
and otherwise left alone.

### 9.6 Files

**New** (6 source, 6 test): `harnesses/parser_targets.py` (registry and
adapters), `harnesses/parser_worker.py`, `harnesses/parser_harness.py`,
`analysis/outcome.py`, `analysis/corpus.py`, `generators/corpus_generator.py`,
`monitoring/boundary_monitor.py`, `core/parser_campaign.py`; tests for outcome,
isolation, corpus, boundary, registry and the gate replay.

**Changed:** `analysis/logger.py` (content-addressed, optional retention
predicate), `core/config.py` (three `EventType` members), `harnesses/base.py`
(`HarnessResult.site`), `core/orchestrator.py` (dropped a no-op call),
`monitoring/monitor.py` (the generic monitor no longer decodes every payload as
CAN frames -- `CANMonitor` already did, and the duplicate buried findings under
ten thousand lines).

### 9.7 What it found

- **`canbus.codec_roundtrip`: an unbounded stall in the CAN codec.** Laying out
  a frame is quadratic in its payload length: `dlc=32768` takes ten seconds and
  `dlc=65536` does not finish in 400. A definition reaches `build_message`
  straight from an ARXML import or a hand edit, and `TargetCanCatalog` records
  an oversized frame as *unsupported* rather than raising, so nothing upstream
  bounded it. Fixed at the owner by bounding the payload and the signal
  positions before `cantools` prices the layout; two cases added to
  `test_canbus_codec.py`.
- **`fuzzer.parse_target_bits`: the `MemoryError` of section 4.1.** Fixed by
  bounding the span before the range is materialised.
- The defects in sections 3.1 and 3.2 of the previous proposal. Section 3.3 is
  **not** done -- see that document.

### 9.8 Answers to section 8

1. **Extended `iotsploit-fuzzer`**, as recommended. The `Orchestrator`,
   strategies, `RadamsaGenerator`, every wire harness, the Django adapter and
   the Flutter UI are untouched.
2. **`artifacts/` treated as disposable**, but archived rather than deleted.
   The loop writes to `iotsploit-fuzzer/corpus/`, which is *tracked in git* --
   `artifacts/` is ignored, so a corpus there would leave every clone replaying
   nothing while reporting success.
3. **Nightly trigger: still open.** The CLI exits non-zero on a violation, so
   either cron or an autopilot can drive it. Nothing was scheduled.

---

**Goal.** A fuzzing capability that is still producing information in month
six. Not a campaign that is run once, reported, and forgotten.

## Governing Standards

- `AGENTS.md` — **Search and reuse first; extend the existing owner rather
  than creating a parallel abstraction.** The loop already exists in
  `iotsploit_fuzzer.core.orchestrator`. This proposal adds one harness, one
  generator, and one ledger to it, and changes one file. It does not build a
  second fuzzer.
- `AGENTS.md` — **Solve at the owner.** The reason the current loop forgets
  everything is `TestLogger.record()`, and that is where the fix goes.
- `.agents/standards/testing.md` — the commit gate must stay fast and
  deterministic. Section 5 keeps generation out of it entirely.

## 1. What "loop philosophy" has to mean here

A fuzzer that runs the same generator against the same targets every night
finds its last bug in week two and becomes CI noise that somebody eventually
switches off. That is the default outcome and it has to be designed against.

The thing that keeps producing information is not more inputs. It is
**tracking where the boundary is, and noticing when it moves.**

Define it precisely. For one parse target and one input, exactly one of three
things happens:

| Outcome | Meaning |
|---------|---------|
| **Accept** | The parser returned a value |
| **Reject** | The parser raised an exception it *declares* — `CanLogError`, `CanDefinitionError`, `RequestError` |
| **Violate** | Anything else: an undeclared exception, a hang, a wrong round-trip |

The **error boundary** is the frontier between accept and reject. `Violate` is
a bug. But the boundary itself is the asset: it is the parser's real contract,
as opposed to the contract its docstring claims. Record the boundary and you
can diff it, and a boundary diff keeps paying out long after the crashes run
dry — because every refactor moves it, and almost every move is unintended.

That gives three nested loops:

- **Inner — the campaign.** Generate, execute, classify. Minutes. *Already
  built* (section 2).
- **Middle — the schedule.** Campaign N+1 starts from campaign N's corpus and
  ledger, not from zero. Nightly. *This is what is missing.*
- **Outer — triage.** A violation becomes a minimised regression case in the
  owning test module, then a fix. Human or agent, on demand.

## 2. What already exists

`iotsploit-fuzzer` is further along than the last proposal credited. The inner
loop is complete and wired to the UI:

| Part | File | Status for this use |
|------|------|---------------------|
| The loop itself | `core/orchestrator.py:244` `Orchestrator.run()` | Reusable as-is |
| Target seam | `harnesses/base.py` `ProtocolHarness.execute(payload) -> HarnessResult` | Reusable as-is — the seam a parser plugs into |
| Result classification | `monitoring/monitor.py` `Monitor`, `MonitorRegistry` | Reusable; needs one new outcome (section 4.3) |
| Byte mutation | `generators/radamsa_generator.py`, `core/bit_manipulator.py`, `core/strategies/` | Reusable as-is |
| Campaign control | `Orchestrator.pause/resume/stop`, `CampaignConfig` | Reusable as-is |
| Live reporting | `core/config.py` `EventType` + `event_callback` → Celery → Redis → WS → Flutter | Reusable — a parser campaign renders in the existing UI with no UI work |
| Persistence | `analysis/logger.py` `TestLogger` | **Must change** (section 3.1) |

So the question is not "what framework should we build". It is "what are the
four things that make this loop have a memory".

## 3. The four gaps, with evidence

### 3.1 The loop has no memory — this is the structural blocker

`TestLogger.record()` (`analysis/logger.py:18`) writes `case_{idx}.bin` keyed
on the **iteration index**, and writes every case unconditionally. Campaign
N+1 therefore overwrites campaign N wherever the indices overlap.

This is not theoretical. `artifacts/` today:

```
2025-10-27  case=0    crash=899
2025-10-31  case=898  crash=0
2025-12-22  case=43   crash=44
2026-01-07  case=28   crash=57
2026-02-21  case=31   crash=0
```

Five campaigns over four months, 8.6 MB, 2000 files, all sharing one
index-keyed namespace. The October 27 crashes survive only because no later
run happened to crash at those indices. `case_500.bin` and `crash_500.bin` are
from different campaigns and are not the same payload. Nothing here is
attributable to a run, nothing accumulates on purpose, and a 31-file February
run leaves a directory that looks like it holds two thousand results.

That directory is a graveyard, not a corpus. Until a payload's identity is its
content rather than its position, there is no loop — only a sequence of
unrelated campaigns.

*Fix, at the owner:* `TestLogger` names files by content hash
(`<sha256[:16]>.bin`) and writes only what the ledger says is interesting. The
existing `artifacts/` is left where it is and the loop writes to its own
directory; re-deriving those 2000 orphans is not worth a line of code.

### 3.2 Nothing decides what was interesting

`Monitor.get_stats()` counts crashes and returns them to the caller. No result
ever reaches the generator. `Orchestrator.run()` calls
`self.generator.seed_corpus()` at line 264 and then mutates from that fixed
set for the whole campaign.

The loop is therefore **open**. It cannot get better at its job, no matter how
long it runs — run it for a year and hour 8000 is exactly as informed as hour
one.

### 3.3 Every harness is a wire

`CANHarness`, `UARTHarness`, `SPIHarness` all reach for a physical interface.
There is no way to point this engine at a function.

That matters beyond convenience: a harness that needs the rig can only run
where the rig is, which rules out CI, rules out running per-commit, and makes
the loop depend on hardware being plugged in. A parser harness is pure CPU —
it runs anywhere, including in the commit gate.

It also fixes an oracle bug visible in the numbers above: on 2025-10-27 the
campaign recorded 899 crashes out of ~900 cases. A ~100% crash rate is a
harness that could not reach its interface, reported through
`HarnessResult(crashed=True)` (`harnesses/can_harness.py:23`) — the same field
that means "the target broke". In a continuous loop that conflation is fatal:
a rig with an unplugged cable reports a catastrophic finding every night until
everyone learns to ignore the report.

### 3.4 A crash-only oracle throws the boundary away

`HarnessResult` records `ok`, `crashed`, `timeout`, `error`. For a parser, the
interesting distinction — accepted, or rejected *in contract* — collapses into
`ok=True` either way, and is discarded.

Keeping it is the whole proposal. Last run's probe put ~77,000 inputs through
nine parsers and found three minor defects; a crash-only loop would now report
zero every night forever. The same 77,000 inputs also contain a complete map of
where each parser draws its accept/reject line, which nothing currently
records and which changes every time someone edits a parser.

## 4. The design

Three new classes, one changed file. Everything else is existing machinery.

### 4.1 `ParserHarness` — the target seam

One `ProtocolHarness` implementation. `execute(payload)` runs a registered
parse target under a wall-clock budget and maps the outcome:

| Parser did | `HarnessResult` |
|------------|-----------------|
| Returned | `ok=True, info="accept"` |
| Raised a **declared** exception | `ok=True, info="reject:<ExcName>"` |
| Raised anything else | `crashed=True, info="violate:<ExcName>@file:line"` |
| Exceeded the budget | `timeout=True` — the hang case |
| Broke a metamorphic property | `crashed=True, info="violate:roundtrip"` |

The declared-exception set is the oracle, and it is not invented — the
docstrings already state it (`decode_frame`: "Never raised, always returned";
`scan_log`: "never fatal"). It lives in a target registry, roughly ten lines
of data per target:

```
name            = "canbus.scan_log"
call            = lambda payload: scan_log(write_temp(payload, ".asc"))
declared        = (CanLogError,)
seeds           = tests/data/*.asc
budget_seconds  = 2.0
```

The nine surfaces in `parser_robustness_fuzzing_proposal.md` §1 are the initial
registry. Adding a tenth target later is a registry entry, not code.

Note this also gives `crashed` an honest meaning: the harness cannot fail to
reach its target, because the target is a function in the same process. The
3.3 conflation disappears rather than being worked around.

**The fuzzer is a legitimate target for its own registry**, and it should be in
the first batch. `iotsploit-fuzzer` parses operator input too, and one
ten-minute probe against `BitManipulator.parse_target_bits`
(`core/bit_manipulator.py:190`) found this:

```
'0-7'                      len= 3  returned 8 positions           peak=    0.0 MB  0.00s
'0-100000'                 len= 8  returned 100001 positions       peak=    8.6 MB  0.02s
'0-10000000'               len=10  !! MemoryError                  peak=  543.6 MB  1.68s
'0-999999999'              len=11  !! MemoryError                  peak=  543.6 MB  1.40s
```

`"start-end"` is expanded with `range(start, end + 1)` into a set, with no
bound on the span. Ten characters is enough, which fits the
`CharField(max_length=255)` the string is stored in
(`iot_fuzzer/models.py:320`) — a field carrying no validators, whose help text
invites exactly this syntax (`"e.g., '0,1,7' or '0-7'"`). Under a 1.2 GB cap it
dies at 543 MB; uncapped on the rig, `0-999999999` asks for tens of gigabytes
on a host also running Django, Celery and Redis, so the OOM killer chooses a
victim before anyone reads a log line. `_get_target_bits`
(`core/strategies/bit_strategies.py:177`) does catch the exception, but the
allocation has already happened by then.

The function's docstring declares `Raises: ValueError`, so `MemoryError` is
outside its stated contract — a `violate` by the section 1 classification, and
found by the oracle this proposal is built around. *Fix:* bound the span before
materialising the range, in `parse_target_bits`. One line.

The wider point for the registry: a target's `budget_seconds` is not a
convenience. It is what converts "allocates until the host dies" — which no
`except` can catch usefully — into a reportable `timeout`.

### 4.2 `CorpusStore` + `CorpusGenerator` — the memory

`CorpusStore` is a directory per target holding content-addressed payloads and
one `ledger.json`. `CorpusGenerator` is a `DataGenerator` whose `seed_corpus()`
reads that directory and whose `generate()` mutates from it, delegating the
byte-level work to the existing `RadamsaGenerator` when radamsa is on the host
and `RandomGenerator` when it is not.

**The retention rule is the fitness function**, and it must be strict or the
corpus becomes another graveyard. Keep a payload only when it produced an
**outcome class this target has never produced before** — a new exception type,
a new rejection reason string, a new violation site. Everything else is
discarded at the end of the campaign.

That is novelty search on observable outcomes, not coverage-guided fuzzing. It
is the honest choice for Python 3.10: real coverage feedback needs per-input
arc collection, and on 3.10 that means `sys.settrace` at roughly 10–30×
slowdown. `sys.monitoring` (3.12+) makes it cheap, so this is worth revisiting
if the project moves; the interface does not change when it does.

Expected steady state: tens to low hundreds of retained payloads per target,
not thousands. A corpus that grows without bound is a corpus with a broken
retention rule.

### 4.3 The boundary ledger — the part that keeps paying

`ledger.json`, one per target: for every retained payload, its outcome class
and the campaign that first produced it.

Each campaign diffs its outcomes against the ledger and emits exactly three
kinds of event:

- **`VIOLATION`** — a contract broke. A bug. Fails the nightly run.
- **`BOUNDARY_MOVED`** — a payload the ledger records as `accept` now
  `reject`s, or the reverse, or the rejection changed type. **Not necessarily a
  bug** — it is a behaviour change, and it wants a human to say whether it was
  intended. Reported, does not fail.
- **`NEW_REGION`** — a novel outcome class. The corpus grew. Informational.

`BOUNDARY_MOVED` is the reason this keeps working in month six. Nothing in the
current test suite can catch a refactor that quietly narrows what a parser
accepts — there is no assertion anywhere that says which ARXML files import or
which ASC lines parse. The ledger is that assertion, and it writes itself.

Implementation note: this is a new `Monitor` subclass, registered through the
existing `MonitorRegistry` (`monitoring/monitor.py:188`). The `EventType` enum
in `core/config.py:5` gains two members. Both are additive.

### 4.4 Where each loop runs

| Loop | Trigger | Does | Budget |
|------|---------|------|--------|
| Gate | every commit, inside `run_gate.py`'s pytest step | **Replays the retained corpus only. Generates nothing.** A violation fails the commit | seconds |
| Nightly | cron or CI on the rig | Full campaign: mutate, classify, update corpus and ledger, report the three event kinds | 10–30 min |
| Triage | on a `VIOLATION` or an unexplained `BOUNDARY_MOVED` | Minimise, add one `@example` case to the owning test module, fix | on demand |

The split is what makes it sustainable. Generation never runs in the gate, so
the gate stays deterministic and fast; the gate still replays every input the
loop has ever found interesting, which is the regression protection.

The nightly trigger is worth one sentence of platform thinking: this workspace
already runs Multica autopilots on a schedule, and a nightly parser campaign
that posts its three event kinds as an issue comment is a natural fit — the
triage loop then starts where the report lands, with no separate dashboard to
build. Plain cron works equally well and is the fallback.

### 4.5 What is new, what changes, what is untouched

**New** (3 files in `iotsploit-fuzzer`): `harnesses/parser_harness.py` with its
target registry; `generators/corpus_generator.py` with `CorpusStore`;
`monitoring/boundary_monitor.py`.

**Changed** (2 files): `analysis/logger.py` — content-addressed, interesting-only
(section 3.1). `core/config.py` — two `EventType` members.

**Untouched:** `Orchestrator`, the strategies, `BitManipulator`,
`RadamsaGenerator`, every wire harness, the Django adapter, the Flutter UI.

One caveat to be honest about: `Orchestrator._extract_protocol_frame_info`
(`:140`) and `_initialize_test_groups` (`:61`) switch on CAN/UART/SPI/UDS and
will label a parser campaign `Generic` in the UI. It renders and it is
readable; making it read well is a later, optional half-day.

## 5. One iteration, end to end

Night 12. `canbus.scan_log` has 41 retained payloads.

1. `CorpusGenerator.seed_corpus()` reads those 41. `generate()` mutates them
   into 5,000 candidates via radamsa.
2. `Orchestrator.run()` — unchanged code — drives them through
   `ParserHarness`, which writes each to a temp `.asc` and calls `scan_log`.
3. 4,988 come back `reject:CanLogError` or `accept`, matching the ledger.
   Discarded.
4. 11 produce `accept` with a frame count the ledger has never seen for that
   region → `NEW_REGION`. Retained; corpus is now 52.
5. 1 produces `violate:OverflowError@logfile.py:220` → `VIOLATION`. Retained,
   the run fails, the report names the file, the line, and the payload hash.
6. Triage minimises it to a 30-byte ASC line, adds one case to
   `test_canbus_logfile.py`, fixes `_parse_identifier`. The payload stays in
   the corpus forever, so the gate replays it on every commit from then on.

Night 13 starts from 52 payloads and a ledger that is one bug wiser.

## 6. Honest limits

- **It will find few crashes.** The evidence says these parsers are hard to
  break. If the case for this rests on crash count it will look like a failure
  by week three — the case rests on `BOUNDARY_MOVED`, which is a change
  detector and fires whenever the code changes.
- **Novelty-by-outcome is a weak fitness signal** next to coverage guidance.
  It will plateau. Section 4.2 says what makes it stronger and when.
- **The oracle is only as good as the declared-exception list.** A target
  whose registry entry declares too much will never report anything. Keeping
  those lists honest is ongoing work, not a one-time setup.
- **`iotsploit-fuzzer` has one test** (`tests/test_imports.py`, imports only).
  Extending an untested package means the three new classes carry their own
  minimal tests — that cost is in the estimate.

## 7. Sequencing

| Phase | Content | Effort |
|-------|---------|--------|
| A | The three Phase 0 defect fixes from the previous proposal. Independent | ~2 h |
| B | `ParserHarness` + registry for 3 targets (`scan_log`, `from_target`, `decode_frame`). Runs by hand, prints outcomes | ~1 day |
| C | `CorpusStore`/`CorpusGenerator` + content-addressed `TestLogger`. The loop now has memory | ~1 day |
| D | `BoundaryMonitor` + ledger diff + the three events. The loop now reports movement | ~0.5 day |
| E | Wire the gate replay and the nightly trigger. Extend the registry to the remaining six targets | ~0.5 day |

B is useful standing alone — it is the previous proposal's soak harness, built
on the existing engine instead of as a script. C is what makes it a loop.

## 8. Decisions needed

1. **Extend `iotsploit-fuzzer`, or keep parser fuzzing separate?** Recommend
   extending: the loop, the event plumbing, and the UI already exist there, and
   a second fuzzer in the same repository is the parallel abstraction
   `AGENTS.md` forbids. The cost is that an inbound-parser concept now lives in
   a package whose docstring says "IoT communication protocols" — the package
   docstring and README would need to say both.
2. **Is `artifacts/` disposable?** Section 3.1 assumes the 2000 orphaned files
   are not worth recovering and the loop starts a clean directory. Say so if
   any of those crash files still matter.
3. **Nightly trigger: Multica autopilot or plain cron?** Autopilot puts the
   report where triage happens; cron has no dependency on the platform being
   up. Recommend autopilot, given this workspace already runs them.
