# Observation Interface Enrichment Proposal (`get_current_observations`)

- **Status**: Pending (Proposal)
- **Owner**: `iotsploit-core` / `iotsploit-django` (with additive consumer support in `iotsploit_ui`)
- **Date**: 2026-11-19
- **Context**: Companion backend proposal to the Scanopy-style Target Observation Diagram and unified `ObservationIndex` implemented in `iotsploit_ui` (`feat/observations-diagram-and-facts`).

---

## 1. Problem Statement

The Flutter Target Explorer now renders observations as Scanopy-style nested containers (**Scope -> Component / Unclaimed -> Subject**) driven by a single `ObservationIndex` with independent `RecordKind`, `Ownership`, and `Documentation` dimensions.

Auditing the actual Python backend and observation producers (`iotsploit-core`, `iotsploit-django`, `iotsploit-exploits`) revealed **five concrete backend/API gaps** that limit how accurately real scans render in the diagram:

| # | Severity | Current Backend Behavior | Impact on Diagram & Facts Organization |
|---|---|---|---|
| **1** | **P0** | `canbus/live_capture.py:916` emits `ObservationBatch(..., is_complete=False)` (a timed capture is a sample, not a full snapshot), while `ObservationRepository.current()` (`observation_repository.py:230`) filters `ScanRunDBModel.is_complete.is_(True)`. | **Real live CAN captures are completely invisible** in `GET /api/get_current_observations/`; only seeded or `is_complete=True` batches appear. |
| **2** | **P0** | `component_id` exists only at scan-run granularity (`ScanRunDBModel.component_id`), not per fact. Bus-wide and LAN-wide scanners (`canbus/live_capture.py`, `nmap_lan_scan.py`, `ip_scan.py`, `someip_discover.py`) emit `component_id=None`. | A bus capture of 19 ECUs or a LAN sweep of 10 hosts dumps **every discovered frame, host, and port into a single `Unclaimed` card**, even when the target's facets already know which component owns that CAN frame or IP address. |
| **3** | **P1** | `scope_key` serves two roles at once: scan-comparability fingerprint (`lan:192.168.10.0/24:ports=22,80,443`, `tcp:192.168.10.1:ports=1-1000`, `doip:config_dids`, `uds:can:b_can:0x7E0`) and diagram grouping key. | Running Nmap, SOME/IP discovery, and DoIP DID probing on the same Ethernet bus produces **3–4 fragmented Scope containers** instead of grouping under the target's `Diagnostic Ethernet` bus zone. |
| **4** | **P1** | Only CAN has a client-side config join (`canonicalFrameId` ↔ `can.messages` / `bus.properties.messages`). Python owns all facet Pydantic schemas (`can`, `doip`, `ethernet`, `someip`, `ssh`, etc.). | Non-CAN observations (`doip`, `someip`, `ethernet`, `tcp`, `lin`) cannot be reconciled as `documented` vs `undocumented` in Flutter without duplicating facet schema knowledge in Dart. |
| **5** | **P2** | `get_current_observations` (`observation_views.py:91-110`) returns only a flat `observations[]` list with no scan-run summary. | Empty complete scans (*"scanned ports 22,80,443 → 0 open"*) are invisible, and the UI cannot display scan freshness or distinguish `is_complete=True` snapshots from `is_complete=False` samples. |

---

## 2. Design Principles

1. **Zero breaking changes**: Existing fields on `GET /api/get_current_observations/` remain unchanged for CLI, MCP (`iotsploit-mcp`), and older UI clients. Every new field is strictly additive.
2. **Preserve truthful provenance**: Never overwrite stored `component_id` or `scope_key`. Keep `COMPARABLE_SCOPE_FIELDS = ("component_id", "source", "scope_key")` intact so snapshot replacement and disappearance semantics stay sound.
3. **Solve at the owner**: Facet-based reconciliation belongs in pure Python (`iotsploit-core`) where the facet schemas already live — not duplicated in Dart or inside individual scanner plugins.
4. **Zero DB schema migration required for Phase A**: All Phase A enrichments are computed at read time from existing `ScanRunDBModel`, `ObservationDBModel`, and the stored `Target` document.

---

## 3. Proposed API Contract (`GET /api/get_current_observations/`)

### Additive Response Shape

```json
{
  "status": "success",
  "target_id": "vw_mqb_bench",
  "scans": [
    {
      "scan_id": "a1b2c3d4...",
      "source": "can_live_capture",
      "scope_key": "can:b_can",
      "component_id": null,
      "bus_id": "b_can",
      "is_complete": false,
      "facts_count": 149,
      "completed_at": "2026-11-19T12:00:00"
    }
  ],
  "observations": [
    {
      "component_id": null,
      "resolved_component_id": "c_gw",
      "attribution": "inferred",
      "documentation": "documented",
      "bus_id": "b_can",
      "host_key": null,
      "is_complete": false,
      "source": "can_live_capture",
      "scope_key": "can:b_can",
      "protocol": "can",
      "subject_kind": "message",
      "subject_id": "300",
      "observed_property": "seen",
      "value": {"count": 600, "period_ms": 100, "dlc": 8},
      "display_key": "can.message.300.seen",
      "scan_id": "a1b2c3d4...",
      "observed_at": "2026-11-19T12:00:00"
    }
  ]
}
```

### Field Semantics

| Field | Location | Type | Semantics |
|---|---|---|---|
| `scans[]` | Top-level | `list[dict]` | Latest active scan runs contributing to this response (including empty complete scans with `facts_count: 0`). |
| `is_complete` | `scans[]` & `observations[]` | `bool` | `true` for a complete snapshot; `false` for an additive sample scan (e.g., `canbus/live_capture.py`). |
| `resolved_component_id` | `observations[]` | `str \| null` | Effective component ID: equals `component_id` when declared by the scan; otherwise inferred from the target's facets when an unambiguous match exists. |
| `attribution` | `observations[]` | `"declared" \| "inferred" \| "unclaimed"` | Distinguishes scan-declared ownership from facet-inferred attribution and truly unclaimed traffic. Raw `component_id` stays unchanged. |
| `documentation` | `observations[]` | `"documented" \| "undocumented" \| "unchecked"` | Backend-verified configuration match across all protocols whose facets define subject keys. `self` records and unknown protocols stay `"unchecked"`. |
| `bus_id` | `scans[]` & `observations[]` | `str \| null` | Configured target `bus_id` resolved from `scope_key` (e.g. `can:b_can` → `b_can`, `uds:can:b_can:0x7E0` → `b_can`, or CIDR/subnet match for `lan:<cidr>:...`). Keeps `scope_key` untouched for scan comparability. |
| `host_key` | `observations[]` | `str \| null` | Optional IP/host grouping key for LAN discoveries (e.g. `"192.168.10.50"` on `ip/host/192.168.10.50`, `tcp/port/192.168.10.50:22`, and `someip/service` endpoints) so unclaimed hosts group their ports into one host card. |

---

## 4. Detailed Backend Changes

### 4.1 Additive Sample Scans in `ObservationRepository.current()`
- **File**: `iotsploit-django/src/iotsploit_django/adapters/django/observation_repository.py`
- **Problem**: `current()` filters `is_complete.is_(True)`, hiding every `canbus/live_capture.py` run.
- **Change**:
  - Add `include_samples: bool = True` (default `True` on `get_current_observations`, or controllable via `?include_samples=false`).
  - Keep the latest `SUCCEEDED` `is_complete=True` scan per `COMPARABLE_SCOPE_FIELDS` as the baseline snapshot.
  - Merge facts from newer `SUCCEEDED` `is_complete=False` scans for the same `(component_id, source, scope_key)` **additively**: a sample scan can add new facts or refresh matching `(protocol, subject_kind, subject_id, observed_property)` facts, but **never** clears facts from the prior complete snapshot.
  - Carry `is_complete` on `ObservationRecord` (or return `(records, scans)` from a helper method) so callers know whether a fact came from a complete snapshot or a sample window.

### 4.2 Pure-Python Read-Time Reconciler in `iotsploit-core`
- **New module**: `iotsploit-core/src/iotsploit_core/domain/observation_reconcile.py` (pure Python over `Target` + `list[ObservationRecord]`, zero Django imports, fully unit-testable).
- **Resolution rules**:
  1. **Bus resolution (`bus_id`)**:
     - Direct match on `scope_key` segments against `target.buses` (`can:<bus_id>`, `lin:<bus_id>`, `uds:can:<bus_id>:...`).
     - Subnet/CIDR match for `lan:<cidr>:...` against Ethernet/VLAN bus properties when present.
  2. **Component attribution (`resolved_component_id`, `attribution`)**:
     - If `record.component_id` is set → `resolved_component_id = record.component_id`, `attribution = "declared"`.
     - Else if `protocol == "can"` and `subject_kind == "message"`:
       - Look up components on `bus_id` (or all components if `bus_id` is null) whose `facets["can"]["messages"]` defines `canonical_frame_id == subject_id`.
       - If **exactly one** component defines it → `resolved_component_id = comp.component_id`, `attribution = "inferred"`.
       - If defined on `bus.properties["messages"]` (bus-owned frame) or ambiguous → `resolved_component_id = None`, `attribution = "unclaimed"`.
     - Else if `protocol in {"ip", "tcp", "udp", "doip", "someip", "ethernet", "ssh"}`:
       - Extract host IP (`host_key`) from `subject_id` (e.g. `192.168.10.22` or `192.168.10.22:22`) or `value["endpoints"][0]["ip"]`.
       - Match `host_key` against component facet host/interface IPs (`doip.host`, `ssh.host`, `ethernet.interfaces[].ip`, `target` IP if single component).
       - If unambiguous single component matches → `resolved_component_id = comp.component_id`, `attribution = "inferred"`.
  3. **Documentation check (`documentation`)**:
     - `subject_kind == "self"` or empty `subject_id` → `"unchecked"`.
     - `can` / `message`: `"documented"` if present in `resolved_component_id`'s `can.messages` **or** `bus_id`'s `properties.messages`; else `"undocumented"`.
     - `doip` / `endpoint`: `"documented"` if `host`/`port` matches component's `doip` facet; else `"undocumented"`.
     - `tcp` / `udp` / `port`: `"documented"` if port is declared in the component's service facets (`ssh.port`, `doip.port`, etc.) when the component carries IP/service facets; otherwise `"unchecked"`.
     - All other protocols → `"unchecked"` until their facet defines a canonical subject join key.

### 4.3 View Handler Wiring
- **File**: `iotsploit-django/src/iotsploit_django/view_handlers/observation_views.py`
- Fetch the target (best-effort; if target lookup fails, fall back cleanly to raw records with `attribution = "declared" | "unclaimed"` and `documentation = "unchecked"`).
- Run `reconcile_observations(target, records, scans)` and serialize the additive fields into the JSON response.

---

## 5. Flutter UI Consumption (Follow-up in `iotsploit_ui`)

Once Phase A lands in `../iotsploit`, `ObservationIndex.build()` in `lib/screens/targets/explorer/explorer_model.dart` needs only a small, backwards-compatible update:
1. Prefer `record['resolved_component_id'] ?? record['component_id']` for owner placement, while displaying an **`Inferred`** chip in the Inspector when `attribution == 'inferred'`.
2. Prefer `record['documentation']` when present (falling back to the existing client CAN check for older backends).
3. Prefer `record['bus_id']` for Scope container grouping when present, while preserving raw `scope_key` in the Inspector and table.
4. When `attribution == 'unclaimed'` and `host_key` is non-empty, group unclaimed LAN subjects under a per-host card (e.g. `Host 192.168.10.50`) instead of one flat `Unclaimed` bucket.
5. Render `scans[]` freshness / `sampled` badges in the Observations summary inspector.

---

## 6. Phased Delivery Plan

- **Phase A (P0/P1 — Recommended Next)**:
  1. Additive sample-scan merge in `ObservationRepository.current()` + unit tests (`test_observation_lifecycle.py`).
  2. Pure-Python `observation_reconcile.py` in `iotsploit-core` + unit tests covering CAN live capture attribution, bus-owned DBC frames, LAN IP/port host grouping, and multi-protocol `bus_id` resolution.
  3. Wire into `get_current_observations` in `observation_views.py` + API tests.
  4. Update Flutter `ObservationIndex` to consume the additive fields with graceful fallback.
- **Phase B (Optional, Future)**:
  - Add `POST /api/promote_observation/` for Scanopy-style "resolve-first" promotion of undocumented CAN frames or unclaimed discovered hosts into the target model, validated by Django's Pydantic facet schemas.
