# Target Edit Code Review

**Date:** 2026-07-08
**Scope:** Target edit / create / update / select code across three layers:

- CLI: `iotsploit-cli/src/iotsploit_cli/commands/target_commands.py` (`do_edit_target`, `do_target_select`)
- Manager: `iotsploit-django/src/iotsploit_django/adapters/django/target_models.py` (`update_target`, `create_target_instance`, `save_target`, `get_all_targets`)
- HTTP: `iotsploit-django/src/iotsploit_django/view_handlers/target_views.py` (`edit_target`, `create_target`)

Overall the logic is sound — edits round-trip and persist correctly. The findings
below are real defects ranked by impact.

---

## 1. Wrong target selected on duplicate labels — CONFIRMED (most serious)

**File:** `iotsploit-cli/src/iotsploit_cli/commands/target_commands.py:68`

`do_target_select` renders targets as `"{name} ({type}) - {ip}"` and then maps the
user's pick back to a target with:

```python
selected_index = target_choices.index(selected_choice)
```

`list.index()` returns the **first** matching label. Two targets that share the
same name and type (with no IP or an identical IP) produce identical labels, so the
wrong target is selected. In a pentest tool this silently points every subsequent
plugin run at the wrong device.

- **Trigger:** two targets, e.g. both vehicles named `Test` with no IP → both render as `Test (vehicle)`.
- **Note:** `do_edit_target` is *not* affected here because it parses the unique `target_id`; this is specific to the select path.
- **Fix:** key selection off `target_id` (or a positional index built alongside the choices), not the display string.

---

## 2. Editing `properties` crashes when stored properties is NULL — PLAUSIBLE

**File:** `iotsploit-cli/src/iotsploit_cli/commands/target_commands.py:123`
(same None assumption at lines 135, 148, 158)

```python
for key, value in target['properties'].items():
```

The `properties` column is nullable (`Column(JSON)`, no `nullable=False`), and
`get_all_targets` returns it raw:

```python
"properties": t.properties,          # NOT coerced
"components": t.components or [],     # coerced
"interfaces": t.interfaces or [],     # coerced
```

For a row whose `properties` is `NULL` (legacy row, or any row not written through
`save_target`), selecting `field='properties'` raises
`AttributeError: 'NoneType' object has no attribute 'items'`. The outer `except`
swallows it as "Error editing target," so properties become uneditable on that target.

- **Fix:** coerce `properties` to `{}` in `get_all_targets` for consistency with `components`/`interfaces`.

---

## 3. HTTP `edit_target` does not validate components/interfaces — PLAUSIBLE

**File:** `iotsploit-django/src/iotsploit_django/view_handlers/target_views.py:190`

```python
if key in ['name', 'status', 'ip_address', 'location', 'components', 'interfaces']:
    target[key] = value
```

`components`/`interfaces` are accepted as arbitrary JSON with no type check.

- **Malformed input → 500 instead of 400:** a body like `{"updates": {"components": "oops"}}`
  sets `target['components'] = "oops"`. In `create_target_instance`,
  `raw_components = target_data.get("components") or []` treats the truthy string as
  iterable and walks it char-by-char; none are dicts, a bogus component list is built,
  pydantic raises, `update_target` returns `False` → HTTP 500 (should be 400).
- **Silent interface data loss:** every edit re-hydrates interfaces through the
  pydantic `Interface` model, which ignores unknown fields. Editing an unrelated field
  such as `name` silently strips any interface keys not in the `Interface` schema.
  (Components are safer because `ComponentFactory.create_component` stashes unknown keys
  into `properties` — an asymmetry worth making consistent.)
- **Fix:** validate that `components`/`interfaces` are lists of dicts at the boundary; preserve unknown interface fields (mirror the component catch-all).

---

## 4. Fragile `target_id` parsing from display label — PLAUSIBLE

**File:** `iotsploit-cli/src/iotsploit_cli/commands/target_commands.py:102`

```python
target_id = selected.split('(')[-1].split(')')[0]
target = next(t for t in targets if t['target_id'] == target_id)
```

The id is recovered by string-splitting the display label. A target name containing
parentheses after the last `(` — e.g. `Cam (front) unit)` — makes the parsed value no
longer equal the real `target_id`, so `next(...)` raises `StopIteration` (caught →
generic "Error editing target"), or in a collision edits the wrong target.

- **Fix:** carry `target_id` alongside the choice (positional index) instead of re-parsing the label.

---

## Theme

Findings **1, 3, and 4** share one root cause: **identity and structured data are
recovered by re-parsing display strings or trusting raw dicts**, rather than carried
explicitly. The durable fix is to pair each choice with its `target_id` and validate
structured fields once at the boundary, instead of round-tripping through formatted
text. Finding **2** is a simpler one-line consistency fix in `get_all_targets`.

## Suggested priority

1. **#1** — silent wrong-target selection (highest risk in a pentest tool).
2. **#2** — one-line fix, removes a crash.
3. **#3 / #4** — boundary validation and identity handling; address together.
