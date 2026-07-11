# Code Optimization Guide & Tracker

> **Purpose:** A long-term, iterative ("circular") effort to reduce code size by **at least 20%**,
> and to improve logic, data models, and UX/UI across the Python backend and the Flutter UI.
>
> **This file is both the playbook and the live progress tracker.** Every LLM session that works on
> this effort MUST read this file first, do one small unit of work, update the tracker, and commit.
>
> **Branch:** `refactor/code-optimization`

---

## 0. How to use this document (read this first, every session)

1. Read **§1 Baseline**, **§2 Principles**, and **§3 Method**.
2. Go to **§7 "You Are Here"** — it tells you the current state and the *next* step.
3. Pick the next unchecked item in the **§6 TODO list** (respect ordering: low-risk first).
4. **Report first, then implement** — for any non-trivial unit, run the **`coding-decision-plan`
   skill** and produce a decision report (§4a): analysis → options → comparison table →
   recommendation → get the user's decision. Do NOT jump straight to editing files.
5. Do **one small unit** of work (one file / one duplication / one dead-code sweep). Do NOT batch
   many unrelated refactors into one change.
6. **Verify** (§4) before you commit. Safety is the top priority — no behavior regressions.
7. **Re-measure** (§3.2) and record the delta.
8. Update **§6** (check the box, note LOC delta) and **§7** ("You Are Here").
9. Commit with a clear message (§5). Then stop, or continue with the next unit.

**Golden rules**
- Safety first: never sacrifice correctness for line count. A working 100-line function beats a
  broken 60-line one.
- Low-risk first: delete dead code, dedupe, and simplify UI before touching core logic/data models.
- Small steps: one reviewable change at a time, each independently verifiable and revertible.
- Never edit generated files (see §1). They do not count toward the target.
- `20%` is a **floor, not a cap.** Keep improving past it where it stays safe and sensible.

---

## 1. Baseline metrics (locked)

Captured on `refactor/code-optimization` at branch creation. These are the fixed denominators for
the 20% target. **Do not recompute the baseline** — only recompute *current* LOC to measure progress.

| Area | Baseline LOC | 20% reduction (floor) | Target (≤) |
|------|-------------:|----------------------:|-----------:|
| **Python source** | 57,924 | 11,585 | **46,339** |
| **Flutter (hand-written Dart)** | 84,119 | 16,824 | **67,295** |
| Flutter generated (excluded) | 6,780 | — | (do not touch) |

### Exact measurement commands

Python source (excludes virtualenvs, caches, DB migrations):
```bash
find iotsploit-cli iotsploit-core iotsploit-django iotsploit-drivers iotsploit-exploits \
     iotsploit-fuzzer iotsploit-mcp iotsploit-platforms libiotsploit plugins \
     -name '*.py' -not -path '*/__pycache__/*' -not -path '*/migrations/*' -not -path '*/env3.8/*' \
  | xargs wc -l | tail -1
```

Flutter hand-written Dart (excludes generated code — these files DO NOT count and MUST NOT be edited):
```bash
find ui/lib -name '*.dart' \
     -not -name 'frb_generated.dart' -not -name '*.freezed.dart' -not -name '*.g.dart' \
     -not -name '*.gr.dart' -not -name '*.config.dart' -not -name '*.mocks.dart' \
  | xargs wc -l | tail -1
```

> **Generated files are off-limits:** `frb_generated.dart`, `*.freezed.dart`, `*.g.dart`,
> `*.gr.dart`, `*.config.dart`, `*.mocks.dart`. To shrink these, change the *source* (the Rust
> bridge, the `@freezed`/`json_serializable` model) and regenerate — never hand-edit output.

---

## 2. Principles — what "optimize" means here

Optimization is measured in **four dimensions**, not just line count:

1. **Code size (−20% floor).** Achieved by, in priority order:
   - **Delete dead code** — unused functions, imports, commented-out blocks, orphan files, unused assets.
   - **De-duplicate** — extract repeated blocks into shared helpers/mixins/base classes/widgets.
   - **Simplify** — collapse needless abstraction, replace boilerplate with idiomatic constructs
     (comprehensions, `dataclass`, Dart collection-if/spread, const constructors).
   - **Decompose god-files** — split 1,000+ line files; this may not reduce total LOC by itself, but
     it exposes duplication and dead code that then can be removed.

2. **Logic.** Reduce cyclomatic complexity, flatten nesting, remove redundant state, unify error
   handling, kill race conditions, replace polling with events where already available.

3. **Data model.** Consolidate duplicated/parallel type definitions, introduce typed models where
   raw dicts/maps are passed around, align backend serializers with frontend models, remove fields
   that are never read. (Flutter `lib/models` is only ~560 LOC vs. 49k of screens — much data shape
   currently lives inline in the UI. Pulling it into typed models is a major win.)

4. **UX/UI.** Consistent components, shared theme tokens, remove one-off styling, unify dialogs and
   list/table patterns, accessibility and responsive fixes. Never regress existing behavior.

### What is OFF-LIMITS
- Behavior changes visible to users, unless explicitly requested and covered by a test.
- Editing generated code (§1).
- Public API / route / DB schema changes without an explicit note and migration.
- "Big bang" rewrites. Everything is incremental.

---

## 3. Method — the per-unit loop

### 3.1 Pick a target
Follow the TODO ordering (§6). Within a phase, prefer the **largest file** or the **most-duplicated
pattern** — biggest safe win first.

### 3.2 Measure before & after
```bash
# before
wc -l <file(s)>
# ...do the work...
# after
wc -l <file(s)>
```
Record `before → after (−N)` in the TODO item.

### 3.3 Find duplication (helpers)
```bash
# Python: find near-duplicate function bodies / repeated literals
grep -rn "def " iotsploit-django/src | sort | ...    # eyeball repeats
# Dart: repeated widget trees
grep -rn "Widget build" ui/lib | wc -l
```
Consider tools if available: `jscpd` (copy-paste detector), `vulture` (dead Python), `flutter analyze`
(dead Dart / unused imports), `ruff --select F401` for unused imports.

### 3.4 Decompose safely
- Extract a widget/function/class, keep the public signature identical.
- Move, don't rewrite. Then delete what's now unused.
- Keep each extraction in its own commit so it's easy to review and revert.

---

## 4a. Reporting before implementation — the `coding-decision-plan` skill

**Every non-trivial optimization unit MUST be reported as a decision plan before any file is edited.**
This effort is architect-first: understand, present options, let the user decide, *then* code.

Use the project skill at `/home/tkxb/skills/skills/coding-decision-plan` (invoke the
**`coding-decision-plan`** skill). It enforces an analysis-first workflow and separates **facts** from
**recommendations** from **decision**.

### What "non-trivial" means here
- **Trivial (no report needed):** mechanical dead-code/unused-import removal caught by a linter,
  pure formatting, a one-line dedupe. Just do it, verify, and log it.
- **Non-trivial (report required):** decomposing a god-file, extracting shared components/base
  classes, changing a data model, merging duplicated managers, anything touching backend logic or
  public shapes. Report first.

### The report format (produce this, then wait for the user's decision)

1. **Repository analysis (facts only)** — current implementation of the target, its dependencies,
   who references it, existing tests, and limitations. No patches yet.
2. **Problem understanding** — what specifically is bloated/duplicated/over-complex, with the LOC
   and reference counts to back it.
3. **Implementation options** — usually drawn from the skill's catalog:
   - Option A – Minimal change
   - Option B – Optimization (dedupe / simplify)
   - Option C – Refactor / redesign
   - Option D – Remove code
4. **Comparison table** — required whenever more than one option is viable:

   | Criteria | Option A | Option B | Option C |
   |---|---|---|---|
   | Approach | | | |
   | Main Goal | | | |
   | Code Impact | Low/Med/High | Low/Med/High | Low/Med/High |
   | Files Changed | | | |
   | Est. LOC delta | | | |
   | Development Effort | Low/Med/High | Low/Med/High | Low/Med/High |
   | Implementation Risk | Low/Med/High | Low/Med/High | Low/Med/High |
   | Compatibility Impact | | | |
   | Testing Requirement | | | |
   | Maintenance / Future Extension | | | |
   | Recommended When | | | |

5. **Recommendation** — the preferred option, reasons, and the trade-off you accept.
6. **User decision gate** — end with the checklist and **wait for the user to pick** before editing:
   ```
   Please select:
   [ ] Option A - Minimal Change
   [ ] Option B - Optimization
   [ ] Option C - Refactor
   [ ] Option D - Remove Code
   [ ] Need more investigation
   After confirmation, implementation can start.
   ```

### After the user decides
Implement only the chosen option, one small unit, then go to §4 (Verify) → §3.2 (Re-measure) →
§6/§7 (update tracker) → §5 (commit). Record the chosen option in the §7 session log so the decision
trail is auditable.

> **Why this matters for a −20% effort:** most regressions come from silent, unreviewed refactors of
> shared logic. The decision report makes the blast radius explicit *before* the edit and keeps the
> user owning every meaningful architectural call.

---

## 4. Verification (safety-first — mandatory before every commit)

A change is not done until it is verified. Minimum bar per change:

**Python**
```bash
# Per affected module (each has its own pyproject/pytest):
cd iotsploit-<module> && python -m pytest -q
# Import smoke check for touched modules:
python -c "import <module.path>"
```
Modules with test dirs: `iotsploit-cli`, `iotsploit-core`, `iotsploit-django`, `iotsploit-fuzzer`,
`iotsploit-mcp`, `iotsploit-platforms`. If a touched area has **no** test, add a minimal one or do a
manual smoke run and note it in the commit.

**Flutter**
```bash
cd ui
flutter analyze            # must not add new warnings/errors
flutter test               # existing widget/unit tests must pass
dart format --output=none --set-exit-if-changed lib   # formatting sanity (optional)
```

**Rule:** if you cannot verify a change, reduce its scope until you can. Never commit an unverified
refactor of core logic or data models.

---

## 5. Commit convention

- One logical change per commit. Reference this effort.
- Format: `refactor(<area>): <what> (−N LOC)` — e.g. `refactor(ui/showcase): split component demos into files (−1200 LOC)`.
- **Do NOT add a Co-Authored-By / Claude trailer** (project rule).
- Update this file (§6 + §7) in the *same* commit as the code change, or in an immediately following
  tracker commit — never let the tracker drift from reality.

---

## 6. TODO list (ordering: low-risk → high-risk)

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · record `(−N LOC)` when done.

### Phase 0 — Setup & instrumentation  *(low risk)*
- [x] Create branch `refactor/code-optimization`
- [x] Write this guide + baseline
- [x] Adopt the `coding-decision-plan` reporting workflow (§4a) as mandatory for non-trivial units
- [x] Add/confirm tooling availability: `vulture`, `ruff`, `jscpd`, `flutter analyze` (note which exist in §7)
- [x] Run a full baseline verification pass (all pytest suites + `flutter analyze` + `flutter test`) and record the starting green/red state in §7

### Phase 1 — Dead code & hygiene sweep  *(low risk, high reward)*
Delete-only pass. No logic changes. Target: unused imports, unreachable code, commented-out blocks,
orphan files, unused assets.
- [x] Python: `ruff --select F401,F811,F841` (or `vulture`) across all modules; remove unused imports/vars (−220 LOC)
- [x] Python: find & remove dead functions/classes (grep for zero references) (−71 LOC)
- [x] Python: delete obviously stale scripts/`obd_test.py`-style scratch files after confirming they're unused (−795 LOC)
- [~] Flutter: `flutter analyze` → remove unused imports, dead code, unused fields
- [ ] Flutter: remove unused assets/widgets (cross-check `pubspec.yaml` asset list vs. references)
- [ ] Remove stale root-level docs/plans that are already completed (coordinate; don't delete active ones)

### Phase 2 — Flutter UI de-duplication & decomposition  *(low–medium risk)*
Biggest LOC concentration. Start with the largest files.
- [ ] `screens/component_showcase/component_showcase_page.dart` (5,947) — split per-component demos into files; this is a demo page, low risk
- [ ] `screens/utils/utils_page.dart` (3,363) — extract sub-tools into widgets
- [ ] `screens/utils/usbtmc/usbtmc_control_panel.dart` (2,885) — decompose, extract shared instrument-control widgets
- [ ] `screens/tasks/components/ssh_client_screen.dart` (2,227) & `ft2232_uart_screen.dart` (1,974) — extract shared terminal/console widget
- [ ] `screens/plugins/plugins_page.dart` (1,996) — extract list/detail widgets
- [ ] `screens/iot_fuzzer/**` (management_controller 1,501, configuration_page 1,218) — dedupe controller/page logic
- [ ] `screens/targets/targets_page.dart` (1,285) + `target_edit_dialog.dart` (1,146) — unify with shared form/table components
- [ ] `widgets/tab_grid.dart` (1,082) and `widgets/` broadly — build a shared component library; replace one-off styling with theme tokens

### Phase 3 — Flutter data model & state  *(medium risk)*
- [ ] Inventory inline data shapes (Maps/dynamic) passed through screens; promote to typed models in `lib/models`
- [ ] Align models with backend serializers (see §Phase 5); one source of truth per entity
- [ ] Consolidate duplicated provider/service state; remove redundant state mirrors

### Phase 4 — Python backend view de-duplication & decomposition  *(medium risk)*

**Approved approach:** Option B — incremental, contract-first decomposition and de-duplication.
Preserve public URLs, route names, import locations, status codes, response shapes, and hardware
behavior. Implement one independently verifiable resource or responsibility at a time.

- [x] Pin all 43 IoT Fuzzer HTTP route names and paths with an exact contract test (−0 production LOC)
- [~] Add response characterization tests and isolate external services/hardware (campaign contracts added)
- [ ] Extract shared request parsing, method validation, and response helpers without changing API envelopes
- [ ] `iot_fuzzer/views.py` (2,380) — split campaign, configuration, management, and results resources
- [ ] `web/views.py` (1,999) — finish migration into existing `web/api` resource modules; retain only required compatibility exports
- [ ] `tools/iot_protocol_adapter.py` (1,415) — split registry, validation, orchestration, monitoring, generation, interfaces, and mocks
- [ ] `tools/iot_fuzzer_service.py` (1,198) and `iot_fuzzer_manager.py` (967) — separate stored-data operations from live campaign lifecycle and remove concrete overlap
- [ ] `tools/adb_mgr.py` (870) — locally consolidate permission scans and command/result handling
- [ ] `tools/report_mgr.py` (724) — locally consolidate report-tree and before/after record handling
- [ ] Run the full Python test gate, re-measure Python LOC, update §7, and close Phase 4

> Current Phase 4 target footprint: 9,553 production LOC. Do not introduce a shared base for
> `ADB_Mgr` and `Report_Mgr`; their singleton construction is insufficient common behavior to
> justify coupling them.

### Phase 5 — Python core managers & data model  *(higher risk — most verification)*
- [ ] `iotsploit-core`: unify `tool_service.py` (1,036) / `tool_manager.py` (903) / `device_manager.py` (942) / `exploit_manager.py` (728) — extract a common manager base class for shared lifecycle/registry logic
- [ ] `libiotsploit/host/pyiotsploit/comms.py` (1,322) — decompose transport layers; remove duplication
- [ ] Consolidate duplicated data models across Django adapters (`adapters/django/iot_fuzzer/models.py` 821) and core; align with Flutter models (Phase 3)
- [ ] Replace raw dict passing with dataclasses/typed structures in core APIs

### Phase 6 — Logic & UX polish  *(ongoing)*
- [ ] Flatten deep nesting / reduce complexity in hottest functions (measure with `radon cc` if available)
- [ ] Unify error handling and logging patterns
- [ ] UX consistency pass: dialogs, tables, spacing/theme tokens, responsive behavior
- [ ] Accessibility pass on primary screens

### Phase 7 — Re-baseline & continue  *(circular)*
- [ ] When both targets hit 20%, re-measure, update §7, and set the next floor (30%?) — the work is circular; keep going.

---

## 7. You Are Here  📍  (update every session)

**Current status:** Phase 1 Python stale script cleanup is complete. Phase 1 Flutter analyzer
hygiene is in decision-plan state; no Flutter source files have been edited in this session.
Starting verification state remains partly red: only the root-run `iotsploit-core`,
`iotsploit-fuzzer`, and `iotsploit-mcp` pytest slices pass; Django still has its known
import-without-settings failure, and some package test dirs collect no tests from the root
environment. Flutter baseline remains red.

### Progress dashboard

| Area | Baseline | Current | Reduced | % | Target (≤) | Hit 20%? |
|------|---------:|--------:|--------:|--:|-----------:|:--------:|
| Python source | 57,924 | 56,838 | 1,086 | 1.9% | 46,339 | ❌ |
| Flutter (hand-written) | 84,119 | 84,119 | 0 | 0.0% | 67,295 | ❌ |

**Last completed step:** Phase 1 — Python stale script cleanup removed the confirmed unused
`iotsploit_django/tools/obd_test.py` scratch diagnostic helper (−795 LOC).

**Next step:** Waiting for user choice on the Phase 1 Flutter analyzer hygiene decision plan below.
After approval, implement only the selected option and keep the first source-edit unit small.

### Pending decision plan — Phase 1 Flutter analyzer hygiene

#### 1. Repository analysis (facts only)

- `ui/.fvm/flutter_sdk/bin/flutter analyze --no-pub` currently reports **484 diagnostics**.
- Analyzer breakdown: **151 errors**, **44 warnings**, **289 infos**.
- Top diagnostic families:
  - `deprecated_member_use`: 288
  - `undefined_identifier`: 47
  - `undefined_method`: 40
  - `uri_does_not_exist`: 24
  - `unused_import`: 21
  - `unused_element`: 13
  - `unused_field`: 5
  - `unused_local_variable`: 1
  - `unnecessary_import`: 1
- Directly mechanical Phase 1 cleanup slice: **41 diagnostics** across unused imports,
  unnecessary imports, unused private declarations, unused fields, and one unused local variable.
- Analyzer infrastructure/build blockers are separate from the cleanup slice:
  - `analysis_options.yaml` includes `package:flutter_lints/flutter.yaml`, but `flutter_lints`
    is not listed in `dev_dependencies`.
  - Code references packages not declared in `pubspec.yaml`, including Syncfusion chart/gauge
    packages, `github`, `version`, and `titlebar_buttons`.
  - `rust_builder/cargokit/build_tool/**` is currently analyzed and reports missing build-tool
    package dependencies.
  - `test/widget_test.dart` still references missing `MyApp`.
  - Some widget code also has package/API drift, for example `searchable_listview` parameter names
    in `robot_preferences.dart`.
- Largest deprecated-use clusters are in `component_showcase_page.dart` (50),
  `ssh_client_screen.dart` (36), `ft2232_uart_screen.dart` (25), and `utils_page.dart` (14).

#### 2. Problem understanding

The next TODO asks for Flutter analyzer cleanup of unused imports, dead code, and unused fields.
That cleanup can reduce warning noise and remove a small amount of dead UI code, but it will **not**
make `flutter analyze` green by itself because the analyzer is also failing on missing dependencies,
analyzed vendored/build-tool code, stale test entry points, and package API drift. The source-edit
risk is low for unused imports, but medium for deleting private methods/fields because some are in
large stateful screens where stale declarations may reveal abandoned UX paths.

#### 3. Implementation options

| Criteria | Option A | Option B | Option C | Option D |
|---|---|---|---|---|
| Approach | Remove unused/unnecessary imports only | Full focused Phase 1 analyzer hygiene: imports, unused private elements, unused fields, one unused local | Fix analyzer/build foundations first: lint dependency, package declarations/exclusions, stale test target, API drift | Remove larger stale UI widgets/assets after a separate reference audit |
| Main Goal | Smallest safe cleanup | Complete the current TODO's intended cleanup scope | Make analyzer capable of becoming green before source hygiene | Bigger dead-code reduction beyond analyzer-only findings |
| Code Impact | Low | Low-Medium | Medium-High | Medium |
| Files Changed | ~16 Dart files | ~25 Dart files | `pubspec.yaml`, `analysis_options.yaml`, tests, and affected widgets/build-tool config | Unknown until asset/widget reference audit |
| Est. LOC delta | Small, likely −20 to −30 | Small-Medium, likely −80 to −180 | Near zero or positive | Potentially larger, unknown |
| Development Effort | Low | Medium | High | Medium-High |
| Implementation Risk | Low | Low-Medium | Medium-High | Medium |
| Compatibility Impact | None expected | None expected if private unused references are verified | Possible dependency/license/build impact | Possible UI navigation/asset impact |
| Testing Requirement | Rerun analyzer and format touched files | Rerun analyzer, format touched files, smoke high-touch screens if feasible | Rerun analyzer, `flutter test`, and dependency resolution | Reference audit, analyzer, asset load smoke checks |
| Maintenance / Future Extension | Leaves most analyzer hygiene debt | Clears the current TODO's mechanical cleanup slice while keeping scope bounded | Establishes a better verification baseline for later cleanup | Best for LOC reduction, but belongs to the next TODO |
| Recommended When | User wants the safest first edit | User wants to complete the current TODO efficiently | User wants analyzer green as the priority before LOC reduction | User wants to move to unused assets/widgets cleanup |

#### 4. Recommendation

Recommended option: **Option B — Full focused Phase 1 analyzer hygiene**.

Reasons:
- It matches the current unchecked TODO more closely than imports-only cleanup.
- The scope is still bounded to analyzer-confirmed unused code and should not alter user-visible
  behavior.
- It avoids mixing hygiene cleanup with dependency/package decisions that need separate review.

Trade-off:
- `flutter analyze` will remain red after Option B because the existing dependency/config/test/API
  blockers are outside this TODO.
- LOC reduction will be modest; this is primarily a safety/noise-reduction step before larger UI
  decomposition.

#### 5. User decision gate

Please select:

```
[ ] Option A - Minimal Change
[ ] Option B - Optimization
[ ] Option C - Refactor
[ ] Option D - Remove Code
[ ] Need more investigation

After confirmation, implementation can start.
```

**Tooling notes:**
- Python: use Poetry (`poetry` 2.0.1). `poetry run python --version` reports Python 3.10.12, and
  `poetry run python -m pytest --version` reports pytest 7.4.4 from `iotsploit-core`.
- Flutter: prefer `fvm flutter analyze` / `fvm flutter test` per project workflow. In this shell,
  `fvm` is not on PATH, but `ui/.fvm/flutter_sdk/bin/flutter --version` works and reports Flutter
  3.27.4 / Dart 3.6.2. Raw system `flutter --version` reports Flutter 3.32.5 and should not be the
  default for project verification.
- Dead-code / dup detectors: `ruff` is now available via `poetry run ruff` and is pinned in the root
  dev dependency group. `vulture`, `jscpd`, and `radon` are not on PATH in this shell.

**Baseline verification state (2026-07-10):**
- Python pytest via `poetry run python -m pytest -q`:
  - `iotsploit-core`: PASS (`4 passed`)
  - `iotsploit-cli`, `iotsploit-django`, `iotsploit-fuzzer`, `iotsploit-mcp`,
    `iotsploit-platforms`: FAIL before test collection (`No module named pytest` in each Poetry env)
- Flutter via `ui/.fvm/flutter_sdk/bin/flutter`:
  - `flutter analyze`: FAIL (`487 issues found`), including missing `flutter_lints` include,
    unused imports, many `withOpacity` deprecations, missing cargokit build-tool dependencies, and
    `test/widget_test.dart` referencing missing `MyApp`
  - `flutter test`: FAIL (`test/widget_test.dart` does not compile because `MyApp` is undefined);
    other listed widget tests continued running around that failure

**Session log** (newest first — one line per work session):
- 2026-07-11: Phase 4 response characterization started with campaign control/status contracts:
  method rejection, malformed JSON, required IDs, success envelopes, and manager delegation are
  pinned behind mocks. Five focused tests pass; no production code changed.
- 2026-07-11: Phase 4 Option B safety-net unit pinned all 43 IoT Fuzzer HTTP route names and
  paths with an exact contract assertion. Focused Ruff and contract tests passed; no production
  code changed. Response characterization remains the next Phase 4 unit.
- 2026-07-11: Phase 4 Option B approved. Restored and refined the missing Phase 4 tracker using
  current LOC (9,553 across seven target files) and a contract-first, resource-by-resource
  sequence. No production code changed; Phase 1 remains the tracker-ordered implementation step.
- 2026-07-10: Phase 1 Flutter analyzer hygiene decision plan revalidated; no Flutter source edits
  yet. Current analyzer state from `ui/.fvm/flutter_sdk/bin/flutter analyze --no-pub`: 484
  diagnostics (151 errors, 44 warnings, 289 infos). The mechanical cleanup slice is 41 diagnostics,
  but analyzer remains blocked by separate missing dependency/config/test/API issues.
- 2026-07-10: Phase 1 Flutter analyzer hygiene decision plan posted; no Flutter source edits yet.
  Current analyzer state from `ui/.fvm/flutter_sdk/bin/flutter analyze --no-pub`: 487 diagnostics
  (151 errors, 44 warnings, 292 infos). The mechanical cleanup slice is 41 diagnostics, but
  analyzer remains blocked by separate missing dependency/config/test/API issues.
- 2026-07-10: Option B implemented for Phase 1 Python stale scripts: removed confirmed unused
  `iotsploit-django/src/iotsploit_django/tools/obd_test.py` after a focused reference audit found no
  imports, package metadata, docs, UI/API, or tooling references outside this tracker. Re-measured
  Python LOC 57,633 → 56,838 (−795). Verification: `poetry run ruff check --no-cache --select
  F401,F811,F841 ...` passed; Django package import smoke passed for `iotsploit_django.tools` with
  `PYTHONDONTWRITEBYTECODE=1`; full Django tests were not rerun because the tracker baseline already
  records the known Django settings failure in this environment.
- 2026-07-10: Option A implemented for Phase 1 Python dead functions/classes: removed confirmed
  zero-reference private helpers from `adb_mgr.py` and `web/views.py`, including one unreachable
  block nested after a returned helper. Re-measured Python LOC 57,704 → 57,633 (−71). Verification:
  `poetry run ruff check --no-cache --select F401,F811,F841 ...` passed; in-memory syntax compile
  of touched files passed. `py_compile` was not usable because the existing package `__pycache__`
  path is read-only in this shell.
- 2026-07-10: Option A implemented for Phase 1 Python hygiene: added root dev `ruff`, cleaned
  `F401/F811/F841` across Python source roots, re-measured Python LOC 57,924 → 57,704 (−220).
  Verification: `poetry run ruff check --no-cache --select F401,F811,F841 ...` passed;
  `poetry check --lock` passed with deprecation warnings; syntax-only compile of changed Python
  files passed; root pytest slices passed for `iotsploit-core`, `iotsploit-fuzzer`, and
  `iotsploit-mcp`; `iotsploit-cli`/`iotsploit-platforms` collected no tests; `iotsploit-django`
  still fails `test_import_urls_without_django_setup` on missing Django settings.
- 2026-07-10: Phase 1 Python hygiene decision plan posted for `F401/F811/F841` cleanup; no source
  edits yet, waiting for user option.
- 2026-07-10: Option A baseline verification pass completed and recorded; no source changes.
- 2026-07-10: Option A minimal tooling confirmation only; recorded Poetry/FVM command notes, no
  source changes and no full baseline verification yet.
- _(init)_ Branch + guide created; baseline Python 57,924 / Dart 84,119 locked.

---

## 8. Quick reference — one-liners

```bash
# Re-measure Python
find iotsploit-cli iotsploit-core iotsploit-django iotsploit-drivers iotsploit-exploits \
     iotsploit-fuzzer iotsploit-mcp iotsploit-platforms libiotsploit plugins \
     -name '*.py' -not -path '*/__pycache__/*' -not -path '*/migrations/*' -not -path '*/env3.8/*' \
  | xargs wc -l | tail -1

# Re-measure Flutter (hand-written)
find ui/lib -name '*.dart' -not -name 'frb_generated.dart' -not -name '*.freezed.dart' \
     -not -name '*.g.dart' -not -name '*.gr.dart' -not -name '*.config.dart' -not -name '*.mocks.dart' \
  | xargs wc -l | tail -1

# Largest hand-written Dart files
find ui/lib -name '*.dart' -not -name 'frb_generated.dart' -not -name '*.freezed.dart' \
     -not -name '*.g.dart' | xargs wc -l | sort -rn | head -20

# Largest Python source files
find iotsploit-* libiotsploit -name '*.py' -not -path '*/__pycache__/*' -not -path '*/migrations/*' \
  | xargs wc -l | sort -rn | head -20

# Verify
cd ui && fvm flutter analyze && fvm flutter test
cd iotsploit-core && poetry run python -m pytest -q
```
