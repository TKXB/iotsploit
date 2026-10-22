# Target Model Optimization Plan

> **Scope:** The Target model end-to-end — Python domain + persistence, and the Flutter UI.
> **Files:**
> - **Backend**
>   - `iotsploit-core/src/iotsploit_core/domain/target.py` (domain / Pydantic)
>   - `iotsploit-django/src/iotsploit_django/adapters/django/target_models.py` (SQLAlchemy adapter + `TargetManager`)
> - **Flutter UI (`ui/`)**
>   - `ui/lib/screens/targets/targets_page.dart` (1285 LOC — list, fetch, filter)
>   - `ui/lib/screens/targets/target_edit_dialog.dart` (1146 LOC — create/edit form)
>   - `ui/lib/widgets/cards/target_card.dart` (423 LOC — card rendering)
>
> **Goal:** Reduce duplication, tighten the persistence layer, split the overloaded
> `TargetManager`, and give the Flutter side a real typed model — without changing external
> behavior. Aligns with the repo-wide effort in `OPTIMIZATION_GUIDE.md`
> (≥20% LOC reduction, safety-first, low-risk-first).
>
> **Current design score:** Backend ~6.5/10 (domain 8/10, manager/persistence drags it down).
> Flutter ~4/10 — no model class at all; targets flow as untyped `Map<String, dynamic>`.
>
> This plan has two parts: **Part A — Backend** and **Part B — Flutter UI**.
> They are independent and can proceed in parallel. The one shared concern (the type registries
> duplicated across both sides) is called out in the cross-cutting section at the end.

---

# Part A — Backend

---

## 1. Summary of findings

| # | Issue | Severity | Effort | Risk |
|---|-------|----------|--------|------|
| 1 | Serialization (`[x.model_dump() for x in ...]`) duplicated across `TargetDBModel.__init__`, `save_target`, and every `get_info()` | High | Low | Low |
| 2 | `Vehicle.get_info` and `GenericTarget.get_info` are near-duplicates; likely redundant re-dump on top of `model_dump()` | Medium | Low | Low |
| 3 | Two independent component re-hydration paths (`create_target_instance` vs `parse_and_set_target_from_json`) | Medium | Low | Low |
| 4 | `TargetManager` is overloaded: registry + repository + session mgr + JSON import/export + current-selection store | Medium | Medium | Medium |
| 5 | `__settings__` pseudo-target + raw SQL smuggles config into the `targets` domain table | Medium | Medium | Medium |
| 6 | Stringly-typed `Target.type`; `TARGET_TYPES` implies an enum but isn't enforced | Low | Low | Low |
| 7 | Hand-rolled `_migrate_schema` (ALTER TABLE by string) is fragile | Low | Medium | Medium |

---

## 2. Ordered plan (low-risk first)

Each step is an independently verifiable, revertible unit. Do one, verify, commit, re-measure.

### Step 1 — Collapse `get_info()` duplication *(issue 2)*
- **What:** Move the shared component/interface serialization into `Target.get_info()` (base class),
  or delete the manual re-dump entirely if `model_dump()` already serializes nested Pydantic models
  correctly. Verify whether `Vehicle`/`GenericTarget` overrides are needed at all.
- **Change:** Base `Target.get_info()` returns `self.model_dump()`; keep an override only where a
  subclass genuinely adds fields (currently neither seems to).
- **Verify:** Compare `get_info()` output before/after for a vehicle and a generic target fixture —
  dicts must be byte-for-byte equal (`assert old == new`).
- **Expected LOC:** −15 to −25.

### Step 2 — Single serialization helper in the adapter *(issue 1)*
- **What:** Introduce one private helper (e.g. `_apply_target(model, target)`) used by both
  `TargetDBModel.__init__` and the update branch of `save_target`. Both currently repeat the same
  seven-field copy plus the two `model_dump()` comprehensions.
- **Verify:** Round-trip test — create → save → reload → assert equality. Confirm insert and update
  paths both go through the helper.
- **Expected LOC:** −15 to −20.

### Step 3 — Unify component/interface hydration *(issue 3)*
- **What:** Extract a `_hydrate_components(raw)` / `_hydrate_target(dict)` helper and call it from both
  `create_target_instance` and `parse_and_set_target_from_json`. They currently diverge slightly
  (the JSON path skips the "already a pydantic model" guard).
- **Compatibility requirement:** Do **not** silently change class-selection semantics while unifying
  hydration. Today `parse_and_set_target_from_json` uses `self.targets.get(target_type, Vehicle)`,
  so unknown JSON target types default to `Vehicle`; `create_target_instance` maps only `"vehicle"`
  to `Vehicle` and all other types to `GenericTarget`. The fix is to extract only the shared
  component/interface hydration first, or to make the new helper accept an explicit mode/fallback
  so each caller keeps its current behavior:
  - JSON import path: registry lookup, default `Vehicle`.
  - request/get-all path: `"vehicle"` -> `Vehicle`, otherwise `GenericTarget`.
- **Verify:** Import a known JSON fixture and diff resulting targets against the `create_target_instance`
  path for component/interface hydration only; separately assert class fallback behavior for unknown
  target types remains unchanged in both callers.
- **Expected LOC:** −20 to −30.

### Step 4 — Introduce a `TargetType` enum *(issue 6)*
- **What:** Replace the free `type: str` with a `str`-backed `Enum` (or `Literal`) derived from
  `TARGET_TYPES`. Keep the field wire-compatible (still serializes to the same strings). Class
  selection (`Vehicle` vs `GenericTarget`) reads the enum.
- **Verify:** Existing stored strings still deserialize; an unknown type still falls back to
  `GenericTarget` (or raises deliberately — decide in the decision report).
- **Risk note:** Touches validation behavior — run the decision-plan skill first.
- **Expected LOC:** neutral (net clarity gain, not a size win).

### Step 5 — Extract settings out of the `targets` table *(issue 5)*
- **What:** Replace the `__settings__` pseudo-row + raw SQL (`_persist_current_target`,
  `_restore_current_target`) with a small dedicated key-value store (separate table or app config).
  Removes the `filter(target_id != "__settings__")` guard scattered in `get_all_targets`.
- **Verify:** Current-target selection persists across a `TargetManager` re-init; migration path for
  any existing `__settings__` row is handled.
- **Risk note:** Data migration — decision report required.
- **Expected LOC:** roughly neutral; correctness/clarity win.

### Step 6 — Split `TargetManager` responsibilities *(issue 4)*
- **What:** Separate concerns into e.g. `TargetRepository` (DB CRUD), `TargetRegistry` (type
  registration + hydration), and keep `TargetManager` as a thin façade / current-selection holder.
  Largest change; do last, after 1–5 have shrunk the surface.
- **Verify:** Full round-trip of every public method (`create/save/get_all/update/add/delete/
  export/import/current`) against pre-refactor behavior.
- **Risk note:** Broadest blast radius — decision report + careful call-site sweep required.
- **Expected LOC:** neutral to slightly negative; maintainability win.

### Step 7 (optional) — Migration strategy *(issue 7)*
- **What:** Replace hand-rolled `_migrate_schema` with a real migration tool (Alembic) or, if that's
  out of scope, at least centralize and document the column-add list. Lowest priority; behavior is
  currently working.

---

## 3. Sequencing rationale (backend)

Steps 1–3 are pure dedup: low risk, no behavior change, immediate LOC wins — do these first and they
also shrink the code Steps 4–6 have to touch. Steps 4–6 change behavior/structure and each need a
decision report per `OPTIMIZATION_GUIDE.md` §4a. Step 7 is optional cleanup.

**Do not batch.** One step = one commit = one re-measurement.

---

# Part B — Flutter UI (`ui/`)

## 4. Summary of findings (Flutter)

The Flutter side has **no target model class**. Targets are fetched as `List<dynamic>` and passed
around as `Map<String, dynamic>`; every field is read by string literal. This is the root cause of
most issues below.

| # | Issue | Severity | Effort | Risk |
|---|-------|----------|--------|------|
| F1 | No typed model — `targets = data['targets']` with zero parsing; targets are raw `Map<String, dynamic>` throughout | High | Medium | Medium |
| F2 | Field names as bare string literals (`target['type']`, `target['status']`, …) repeated ~100+ times across 3 files; a backend rename fails silently at runtime | High | Medium | Low |
| F3 | Type registries hand-copied from backend and **already drifted**: `targetTypes = {'generic','vehicle'}` in the dialog vs backend `TARGET_TYPES` (7 entries: vehicle/ecu/iot/phone/router/camera/generic) | Medium | Low | Low |
| F4 | Component-type list (`['generic','adb_device','camera','sensor','network','ecu','infotainment']`) duplicated client-side, mirroring `ComponentFactory._component_types` | Medium | Low | Low |
| F5 | Component/interface editing works on untyped `List<dynamic>` + `comp['component_id']` map access; no per-type field awareness (backend has `ADBDevice`, `CameraComponent`, etc.) | Medium | Medium | Medium |
| F6 | Large widget files (2854 LOC across 3) mixing fetch, filter, form state, and rendering; little reuse | Medium | Medium | Medium |

## 5. Ordered plan (Flutter, low-risk first)

### Step F1 — Introduce `Target` / `Component` / `Interface` model classes
- **What:** Add `ui/lib/models/target.dart` with `Target`, `Component`, `Interface` classes plus
  `fromJson` / `toJson`, mirroring the backend fields (`target_id, name, type, status, properties,
  ip_address, location, components, interfaces`). Keep JSON keys identical to the API.
- **Change:** Parse at the boundary — `targets = (data['targets'] as List).map(Target.fromJson)` in
  `targets_page.dart`. Leave the rest of the widgets on maps for now (a `toJson()` bridge keeps them
  compiling); migrate call sites incrementally in F2.
- **Verify:** List renders identically; create/edit/delete round-trip unchanged against the running
  backend. `flutter analyze` clean.
- **Risk note:** New file, additive — low risk. Fixes F1/F2 at the source.

### Step F2 — Migrate widgets off raw map access onto the model
- **What:** Replace `target['field']` reads in `targets_page.dart`, `target_card.dart`, and
  `target_edit_dialog.dart` with typed getters (`target.name`, `target.type`, …). Do it one file at a
  time (card → page → dialog, simplest first).
- **Verify:** Per file, `flutter analyze` clean + visual smoke test of that screen.
- **Expected LOC:** modest reduction + large readability/safety gain.

### Step F3 — Single source for target & component types *(pairs with F4 and §9)*
- **What:** Collapse the two drifted registries into one client-side constant (e.g.
  `TargetTypes` / `ComponentTypes` in the model file), and — critically — reconcile it with the
  backend so the dialog offers all real target types, not just `generic`/`vehicle`. See §9 for the
  preferred fix (serve the registry from the API rather than hard-code it twice).
- **Verify:** Type dropdowns list the same options the backend accepts; creating each type persists
  and reloads correctly.
- **Risk note:** F3 changes user-visible dropdown options — confirm intended list before shipping.

### Step F4 — Extract reusable pieces from the widget files *(issue F6)*
- **What:** Pull repeated form-field builders, the component/interface editors, and the property
  key-value editor out of `target_edit_dialog.dart` into small reusable widgets; separate fetch/filter
  logic from rendering in `targets_page.dart`. Do last, after the model migration has simplified them.
- **Verify:** Screens behave identically; `flutter analyze` clean.
- **Expected LOC:** meaningful reduction across the 2854-LOC trio.

---

# Cross-cutting

## 6. Shared concern: duplicated type registries

The set of valid **target types** and **component types** currently lives in **three** places that
must be kept in sync by hand: `TARGET_TYPES` + `ComponentFactory._component_types` (backend), and the
`targetTypes` / `componentTypes` lists (Flutter dialog). They have **already drifted** (Flutter lists
2 target types; backend defines 7).

**Preferred fix:** expose the registries from the backend (a small `GET /api/target-types` +
`/api/component-types`, or include them in an existing bootstrap/config endpoint) and have the Flutter
UI consume that instead of hard-coding. This removes the drift class entirely. Do this as part of
backend Step 4 (enum) + Flutter Step F3 so both sides land together.

---

## 7. Verification checklist

**Backend (every step):**
- [ ] Round-trip: create → save → reload → `assert` equality.
- [ ] `get_info()` / `get_all_targets()` output unchanged for vehicle + generic fixtures.
- [ ] Current-target selection survives `TargetManager` re-init.
- [ ] JSON export → import → export is idempotent.
- [ ] No new import cycles; domain layer stays free of SQLAlchemy.

**Flutter (every step):**
- [ ] `flutter analyze` clean (no new warnings).
- [ ] Targets list, card, and edit dialog render and behave identically against the running backend.
- [ ] Create / edit / delete / set-current round-trips succeed for vehicle + a non-vehicle type.

**Both:**
- [ ] LOC delta recorded in `OPTIMIZATION_GUIDE.md` tracker.

---

## 8. Expected outcome

- **Backend LOC:** ~−65 to −95 across the two files (Steps 1–3 alone), before the structural steps.
- **Flutter LOC:** net reduction across the 2854-LOC trio (largest from F2 + F4), plus a new ~small
  model file; the real win is type safety, not raw line count.
- **Design score:** Backend ~6.5 → ~8; Flutter ~4 → ~7.
- **Drift risk eliminated** once §6 lands (one source of truth for types).
- **No external behavior change** — refactor-only, except the intentional §6/F3 dropdown reconciliation.
