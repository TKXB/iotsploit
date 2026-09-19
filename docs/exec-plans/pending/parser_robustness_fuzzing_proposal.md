# Parser Robustness Through Fuzzing — Proposal

## Status

- **State:** **Partly implemented** on 2026-09-19, branch
  `feat/parser-fuzzing-loop`.
  - **3.1 done** -- `classify_error_frame` coerces totally, and its docstring
    now states the "never raises" contract the oracle holds it to. An `int`
    `data` is excluded rather than coerced: `bytes(n)` allocates `n` zero
    bytes, which is both a wrong reading and a way to exhaust a long-running
    capture from one malformed message.
  - **3.2 done** -- the DTD guard sniffs the byte-order mark and scans decoded
    text, keeping its streaming shape. The UTF-16 bomb that previously walked
    past it is now refused by this repository rather than by libexpat.
  - **3.3 NOT done, and it needs a decision** -- see the note below.
  - **Section 4 superseded** by
    `../completed/continuous_parser_fuzzing_framework_proposal.md`, which is
    implemented. `hypothesis` was not added: the corpus and ledger provide the
    `@example` regression habit it was wanted for.
- **Blocked on:** decision 2 in section 7, restated below

### Why 3.3 stopped

The proposal says to extend `_coerce_parameters` to honour declared `int` and
`float`, then "delete the four `_integer` copies and the one `_as_bool` copy".
The first half is straightforward. The second half is not, and the proposal
misses why: **those four copies also range-check**, and the declared parameter
specs carry no `min`/`max`:

```python
"method_id": _integer(parameters.get("method_id"), "method_id", 0, 0xFFFF)
```

Deleting them as written drops the bound silently. Landing 3.3 honestly means
either (a) adding `min`/`max` to the declared spec so `_coerce_parameters` can
enforce it and the copies delete cleanly -- which is the "solve at the owner"
answer and is what I would do -- or (b) keeping a two-line range check at each
of the four call sites, which is net-positive but less of a deletion than the
proposal claims.

Either way it changes what plugins receive, which is decision 2 in section 7
and was never answered. It is independent of the fuzzing loop, so it was left
for that answer rather than guessed at.

- **Probe scripts:** `parser-robustness-probes/` remains throwaway evidence,
  untracked and excluded from lint. The permanent equivalent is the target
  registry in `iotsploit_fuzzer.harnesses.parser_targets`
- **Draft date:** 2026-09-18
- **Basis:** ~77,000 malformed inputs driven through nine parse entry points on
  `dev` at `e3d8c96`, using the Poetry environment in `.agents/local.md`
- **Estimated effort:** Phase 0 ~2 h, Phase 1 ~1 day. Phase 2 unsized
- **Decision owner:** User
- **Blocked on:** two decisions in section 7

**Goal.** Establish, with evidence, where IoTSploit's own parsers break on
input a vehicle or an operator can actually produce — and propose the smallest
amount of permanent test code that keeps them from breaking again.

## Governing Standards

- `AGENTS.md` — **Keep scope minimal.** "Tests are out of scope by default …
  only an uncovered, high-risk regression path justifies minimal new test
  code." Section 4 names exactly which paths qualify and why; section 6 names
  what is deliberately left alone.
- `AGENTS.md` — **Delete > Replace > Add.** Two of the three fixes in section 3
  remove code. The test additions in section 4 go into test modules that
  already exist rather than into new files.
- `.agents/standards/testing.md` — the Writing Tests section already asks every
  test to cover "wrong types, `None`, empty `str`/`list`/`dict`, and boundary
  values". This proposal is that rule applied systematically to the parse
  boundary, not a new discipline.
- `docs/architecture.md` — the parse owners live in the inner rings
  (`iotsploit-protocols`, `iotsploit-core`), so their harnesses need no Django,
  no hardware, and no network.

## 1. What "the exploit parsing project" actually parses

Ranked by exposure — how far the input travels before anything in this
repository has vetted it.

| # | Surface | Owner | Input comes from |
|---|---------|-------|------------------|
| 1 | ARXML vehicle description | `iotsploit_protocols.autosar.arxml` + `cantools` | An **uploaded file**, over HTTP (`arxml_views.py:71`) |
| 2 | CAN log replay (ASC native; BLF/candump/TRC via `python-can`) | `iotsploit_protocols.canbus.logfile` | A **recorded file**, often from someone else's tooling |
| 3 | Stored target → frame definitions | `iotsploit_protocols.canbus.catalog` | Whatever the ARXML/DBC import wrote, plus hand edits |
| 4 | Signal values → CAN bytes, and back | `iotsploit_protocols.canbus.codec` | **Operator** form input |
| 5 | Frame-composer request | `iotsploit_exploits.canbus.frame_composer` | Operator JSON, from the UI or a CLI text field |
| 6 | SOME/IP SD datagrams | `iotsploit_protocols.someip.sd` | **The vehicle**, unauthenticated, multicast |
| 7 | SOME/IP and DoIP framed responses | `someip.client`, `doip.client` | The vehicle, length-prefixed |
| 8 | UDS responses | `iotsploit_protocols.doip.uds` | The vehicle, one byte of which selects the whole parse |
| 9 | Plugin parameters | `iotsploit_core.core.exploit_manager` | Operator, through HTTP/CLI JSON, as **strings** |

Two of these are "hostile by construction": 1 and 2 are files a tester accepts
from a supplier, and 6–8 are bytes from a device that is, by the nature of the
product, frequently broken or lying. Surface 9 is the one the operator hits
first every day.

**Not the same thing as `iotsploit-fuzzer`.** That package fuzzes the *device
under test* — CAN/UART/SPI payloads out through a harness, results in
`artifacts/case_*.bin`. This proposal fuzzes *our own parsers*, inbound. They
share generators (section 4.3) but nothing else, and conflating them is how a
fuzzing effort ends up measuring the wrong thing.

## 2. What the probe found

Every entry point was run against inputs that violate its assumptions, with
each target's own documented contract as the oracle — the docstrings state
these, which is what makes the check possible at all:

- `scan_log` — "A line this reader cannot parse is counted and skipped, never
  guessed at and never fatal." Oracle: nothing but `CanLogError` escapes.
- `TargetCanCatalog.from_target` — oracle: nothing but `CanDefinitionError`.
- `decode_frame` — "Never raised, always returned." Oracle: **no** exception.
- `encode_frame` — oracle: `CanValueError` / `CanDefinitionError` only.
- `UdsClient._parse`, `ServiceDiscovery._parse`, `normalize_request`,
  `build_preview`, `classify_error_frame` — same shape.

| Probe | Inputs | Escapes |
|-------|--------|---------|
| `fuzz_can.py` — ASC/BLF/TRC files, catalog, codec, UDS, error frames | ~34,900 | **2** |
| `roundtrip.py` — `decode(encode(v)) == v`, `encode(decode(b)) == b` | 1,792 round trips | 0 |
| `fuzz_composer.py` — composer requests, object and JSON-string form | 20,000 | 0 |
| `fuzz_sd.py` — SOME/IP SD datagrams (996 reached offer construction) | 20,000 | 0 |
| `xml_bomb*.py`, `xxe.py` — entity expansion, XXE, quadratic blowup | 5 crafted | 1 guard bypass |

**The headline is that this codebase is already hard to break.** 77,000 hostile
inputs produced three defects, all minor, and zero silent wrong values in the
one place a silent wrong value would be worst (the codec round trip). That
finding is itself the argument for what follows: the invariants above are real,
they hold today, and **nothing in the test suite pins them**. The value of this
work is not finding crashes — it is that the next refactor of a 400-line codec
cannot quietly turn "never raises" into "usually does not raise".

## 3. The three defects, and the fix for each

### 3.1 `classify_error_frame` trusts its caller's types — low

`canbus/errorframes.py:110` and `:116`:

```python
classes = tuple(_flag_names(ERROR_CLASSES, int(arbitration_id or 0)))   # ValueError on 'x'
payload = bytes(data or b"")                                            # TypeError on 'abc'
```

Reached from `live_capture.py:289`, which forwards
`getattr(message, "arbitration_id", 0)` and `getattr(message, "data", None)`
straight through. With `python-can` and with `ReplayMessage` both are always
`int`/`bytes`, so **this is not reachable today**; it becomes reachable the
moment a driver or an adapter yields a message-shaped object that is not one —
which is exactly what a driver author does first. A live capture is a long-
running loop, so the cost of being wrong is the whole capture, not one frame.

*Fix:* the function already coerces (`int(...)`, `bytes(...)`); make the
coercion total instead of partial. Three lines in the owner, no new file.

### 3.2 The ARXML DTD guard does not see a UTF-16 file — low, defense in depth

`autosar/arxml.py:193-204` scans raw bytes for `<!doctype` / `<!entity` before
either `ET.parse` (`:211`) or `cantools` (`:81`) reads the file. Both are
ElementTree underneath, and neither is safe against entity expansion, so that
scan is the only protection there is.

It is a byte-level substring match, so a UTF-16-encoded ARXML — where the
bytes are `<\x00!\x00d\x00…` — walks past it. Measured:

```
--- levels=8  on-disk 1278 bytes  (expands to ~10^9 chars)
    _inspect_file: DTD scan did NOT fire (guard bypassed)
    ArxmlImportError: … limit on input amplification factor … breached
    peak heap 39.0 MB, elapsed 0.2s
```

The bomb was stopped — by **libexpat 2.4.7's** built-in amplification limit,
not by anything in this repository. Two things follow: the file-read XXE
variant is also refused (`undefined entity &xxe;`, because ElementTree resolves
no external entities), so there is no data-exfiltration path; and the DoS
protection is a property of the host's expat build, on a path whose input is an
HTTP upload.

*Fix:* sniff the BOM in the first chunk and scan the decoded text, keeping the
streaming shape. The guard stays where it is, because it is what protects the
`cantools` pass as well — moving it onto our own `XMLParser` would leave
`cantools` unguarded.

### 3.3 Declared parameter types are half-owned — medium, and the interesting one

`ExploitPluginManager._coerce_parameters` (`exploit_manager.py:78`) exists
precisely because "parameters arrive as JSON strings from the web and CLI
layers" and it was wrong for each plugin to solve that alone. It then coerces
**only** declared `bool`, and `test_parameter_coercion.py:42` pins the
pass-through of everything else as intended behaviour.

The consequence, across `iotsploit-exploits`:

- **28** parameters in **16** files declare `'type': 'int'` or `'float'`, and
  every one of them reaches its plugin as whatever the transport sent.
- **Four** plugins re-implement a byte-identical guard —
  `uds/probe.py:538`, `someip/someip_call.py:184`, `doip/authentication.py:185`,
  `doip/configuration_dids.py:253` — and one re-implements `_as_bool`
  (`uds/probe.py:522`) that `iotsploit_core.utils.as_bool` already owns.
- The plugins that did not write a guard either crash on a typo —
  `greatfet_rubber_duck.py:205`, `int(parameters.get('delay_before_typing', …))`
  — or hand the string onward: `flood_attack/syn_flood_attack.py:100-101` takes
  `port` and `count` from the request and passes them down unparsed.

This is the fuzzing finding that matters, and it is not a crash report: it is
that the boundary owns half a job, so sixteen files own the other half with
varying diligence. The gap is also why no amount of parser hardening below it
helps — bad input never reaches the parser, it stops in the plugin.

*Fix, in the owner:* extend `_coerce_parameters` to honour declared `int` and
`float` the same way it honours `bool`, raising the one error the four copies
already agree on. Then delete the four `_integer` copies and the one `_as_bool`
copy and let their call sites read the coerced value. Net-negative, and it
makes `'type': 'int'` mean something for the twelve plugins that never wrote a
guard at all.

## 4. What to build

### 4.1 Where it goes

No new test files. Every parse owner named in section 1 already has a test
module — `test_canbus_logfile.py`, `test_canbus_catalog.py`,
`test_canbus_codec.py`, `test_doip_uds.py`, `test_someip_sd.py`,
`test_arxml_import.py`, `test_can_frame_composer.py`,
`test_parameter_coercion.py` — and the contract cases belong next to the
behaviour cases they qualify. Budget: **two to four cases per module**, in the
style `.agents/standards/testing.md` already prescribes.

### 4.2 What each case pins

One property per owner, phrased as the docstring already phrases it:

| Owner | Property to pin |
|-------|-----------------|
| `logfile.scan_log` | Any file contents; only `CanLogError` escapes; skipped lines are counted, not fatal |
| `catalog.from_target` | Any target mapping; only `CanDefinitionError` escapes |
| `codec.decode_frame` | Any definition and any bytes; **never** raises |
| `codec.encode_frame` / `decode_frame` | `decode(encode(v)) == v` for raw-representable `v` |
| `uds.UdsClient._parse` | Any response bytes; only `ProtocolError` escapes |
| `sd.ServiceDiscovery._parse` | Any datagram; returns a list |
| `frame_composer.normalize_request` | Any JSON; only `RequestError` escapes, with `field_errors` populated |
| `arxml._inspect_file` | A DTD is refused in every encoding ElementTree accepts |
| `_coerce_parameters` | A declared `int` parameter is an `int` or a clean error — never a string |

### 4.3 Methodology, in the order it pays

1. **Contract fuzzing** — random and adversarial input against a declared
   exception set. Cheapest, and it found 3.1.
2. **Metamorphic** — `decode(encode(v)) == v`. The only technique that catches a
   *silently wrong value*, which on a live CAN bus is worse than a crash.
3. **Differential** — the native ASC reader against `python-can`'s `ASCReader`
   on the same file. `logfile.py`'s own header warns that three ASC subtleties
   "silently produce plausible wrong numbers rather than an error"; a
   differential oracle is the only cheap way to keep watching them. Worth its
   own step because `python-can` is already a dependency.
4. **Mutation from a seed corpus** — for the binary and file formats. Reuse
   `iotsploit_fuzzer.generators.RadamsaGenerator` when radamsa is on the host
   and `RandomGenerator` when it is not; both already implement the same
   `DataGenerator` interface. No new generator.

### 4.4 Tool: `hypothesis`

Recommended. It is already resident in the Poetry venv (6.167.1) but is **not**
in `poetry.lock`, so it needs one line in
`[tool.poetry.group.dev.dependencies]` to be honest about the dependency.

What it buys over a seeded `random.Random` loop, which is the zero-dependency
alternative: shrinking (a 40-field failing target collapses to the one field
that matters), and `@example(...)`, which makes "every crash we ever found
becomes a permanent regression case" a one-line habit instead of a corpus
directory somebody has to curate. Run with `derandomize=True` so the gate
cannot go red for a reason the previous run did not have.

If the answer is no new dev dependency, the fallback is a seeded loop in the
same test modules; it costs the shrinking and makes each regression case a
hand-minimised literal. The plan survives either way.

### 4.5 Gate integration

- **In the commit gate:** the bounded property cases from 4.1, `max_examples`
  around 50, derandomised. Target: a few seconds total. No new pytest marker,
  no change to `run_gate.py` — they are ordinary `unit` tests in modules the
  gate already collects.
- **Not in the commit gate:** the long soak (the `parser-robustness-probes/`
  scripts, cleaned up into one `tools/testing/fuzz_parsers.py`). It runs for
  minutes and its input set is deliberately unbounded, which is the opposite of
  what a pre-commit gate needs. Run it by hand before a release, or nightly in
  CI, the same way `test-wheel-installs.py` is already CI-only.
- **The loop that makes it worth having:** a soak failure is minimised, added
  to the owning test module as one case, and fixed. The soak finds; the gate
  remembers.

## 5. Sequencing

| Phase | Content | Effort |
|-------|---------|--------|
| 0 | The three fixes in section 3. Independent of everything else; 3.3 is worth doing on its own merits | ~2 h |
| 1 | The cases in 4.1/4.2, plus `tools/testing/fuzz_parsers.py` | ~1 day |
| 2 | Surfaces the probe did not reach (section 6) | unsized |

Phase 0 does not depend on Phase 1, and 3.3 is a net-negative change that
stands alone.

## 6. Deliberately not proposed

- **A corpus directory.** `@example` in the owning test file is the same thing
  without a directory to curate. `artifacts/` belongs to the target fuzzer.
- **Coverage-guided fuzzing (Atheris/libFuzzer).** The parse surfaces here are
  shallow branch-wise and the interesting bugs are semantic, not memory-safety;
  coverage feedback earns its complexity against C code, not against
  ElementTree wrappers.
- **Hardening `cantools`, `python-can`, or `scapy`.** They are the authority on
  their formats, by explicit design in `canbus/__init__.py` and
  `definitions.py`. Fuzzing finds *our* wrappers; a crash inside a dependency
  is an upstream report, not a local guard.
- **Anything about the surfaces below** until Phase 1 is landed and the three
  Phase 0 fixes are in. Listed so the next pass has a starting point, ranked:
  BLF/TRC binary readers (`python-can` does the parsing — differential only);
  the ARXML path *through* `cantools` at depth; the Django upload view
  (`arxml_views.py:71`) for size, filename, and content-type handling; MCP tool
  arguments; device-driver response parsing; the CLI's own argument coercion.

## 7. Decisions needed

1. **`hypothesis` as a dev dependency — yes or no?** Recommendation: yes; the
   shrinking and `@example` regression habit are what turn this from a one-off
   audit into a standing property. Fallback in 4.4 if the answer is no.
2. **Does 3.3 land as proposed — coercion moves into `_coerce_parameters` and
   the five duplicate helpers are deleted?** It changes what plugins receive:
   a plugin currently reading `parameters['count']` as a string would start
   receiving an `int`. Every in-repo call site is listed in section 3.3 and all
   of them want the `int`, but an out-of-tree plugin is the user's call.

## Appendix: reproducing the probe

`parser-robustness-probes/` holds the scripts exactly as run. They are
throwaway evidence — not proposed code, not wired into anything:

```bash
poetry run python docs/exec-plans/pending/parser-robustness-probes/fuzz_can.py
poetry run python docs/exec-plans/pending/parser-robustness-probes/roundtrip.py
poetry run python docs/exec-plans/pending/parser-robustness-probes/fuzz_composer.py
poetry run python docs/exec-plans/pending/parser-robustness-probes/fuzz_sd.py
poetry run python docs/exec-plans/pending/parser-robustness-probes/xml_bomb16.py
```

Each prints the escaping exception, the file and line it escaped from, and the
input that caused it. `xml_bomb16.py` and `xxe.py` cap their own address space
with `RLIMIT_AS`; run them on the rig without that cap only on purpose.
