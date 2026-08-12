# Target Data Model — Consolidated Design & Implementation Plan

> **Decision:** relational storage is the source of truth, split into three planes by cardinality and
> provenance. A property graph is a derived, in-memory projection — never a persistence format.
>
> **Problem this solves:** a component can have thousands of attributes of one kind — UDS DIDs, CAN
> IDs, SOME/IP services, TCP ports, VLANs. None of them belong in `Target.properties`.
>
> **Supersedes (removed):** `target_graph_model_proposal.md`, `target_observations_plan.md`,
> `target_data_model_design.md` — fully absorbed here.
>
> **Overlaps (still live):** `target_model_optimization_plan.md` — its Phase 0 dedup steps and its
> Flutter typed-model work are restated here as Phase 0 and Phase 9. Its LOC-reduction tracking and
> the remaining `TargetManager`/widget refactoring stay in that document; see §14 for the structural
> items deliberately deferred to it.

---

## 1. The model

```text
Plane A — CONFIGURATION            authored, small, mutable, closed-world
  targets / components / facets    → JSON column on the targets row (correct for this plane)
        │
        │ canonical join key (protocol + address)
        ▼
Plane B — REFERENCE CATALOG        imported, large, immutable per release
  dsa_release → Endpoint → DecodeSpec   → normalized tables (Django ORM)
        │
        │ set operations
        ▼
Plane C — OBSERVATIONS             measured, unbounded, append-only, open-world
  scan_runs ──1:N── observations   → normalized tables (SQLAlchemy)

Plane T — TOPOLOGY                 authored edges between A's entities
  edges(source, target, relation, properties)
        │
        └──▶ nx.MultiDiGraph       derived, cached, rebuildable, never written back
```

### 1.1 Ownership rules (non-negotiable)

1. A plane never writes into another plane.
2. Plane B is never written by a scan. Discovered endpoints do **not** get inserted into the catalog.
3. Plane C is never read as configuration. A measured value never overwrites an authored one.
4. Cross-plane relationships are resolved at **query time**, never denormalized into storage.
5. The graph is always rebuildable from A + B + C. Graph mutations are never persisted.

Rule 2 is the one that will be tempting to break and the most valuable to keep — see §7.

### 1.2 Why the current model fails

`Component.properties` holding N endpoints is a repeating group inside a row. Concretely:

| Failure | Mechanism |
|---|---|
| Write amplification | `target_models.py:118` re-serializes *all* components on every save. Renaming a target rewrites the whole blob. |
| Lost updates | Two concurrent scans read → append → write. Last writer wins, silently. |
| No access path | "Which targets expose `0xF190`?" cannot be expressed in SQL over an opaque JSON blob. |
| No history | Which scan found it? Was it there last week? Overwritten. |
| Wrong EAV plane | `Dict[str, Any]` is EAV. Correct for open-world Plane C, wrong for closed-world Plane A, where it discards validation and any schema the UI could render. |
| Reference/instance mixing | A DID definition belongs to the ECU *model*, not to your unit. Copying it per target breaks versioning. |

---

## 2. Routing rule

When any new attribute appears, ask in order:

```text
1. Measured off a device, or entered by a human?
      measured → Plane C. Stop.

2. A property of THIS unit, or of the model/protocol in general?
      of the model → Plane B. Stop.

3. How many per component?
      one (or a fixed handful) → Plane A, as a typed facet field.
      many                     → it is a collection: it gets a table.

4. Will anything filter/sort/join/aggregate on it in SQL?
      yes → it needs a column, never a JSON blob key.
      no  → a JSON leaf inside the facet is fine.
```

`properties: Dict[str, Any]` survives only for step-3 leftovers that failed every test. It should
shrink over time, not grow.

### 2.1 The rule holds across protocols

| Protocol | Plane A (settings) | Plane B (vendor description) | Plane C (measured) |
|---|---|---|---|
| DoIP / UDS | logical addr, tester addr, port, PIN | DSA XML → DIDs | which DIDs answered, NRCs |
| Ethernet / IP | IP, netmask, VLAN id, MAC | network architecture / VLAN plan | live hosts, open ports, banners |
| CAN | bus name, bitrate, channel, ISO-TP addressing | DBC / ARXML → messages + signals | observed CAN IDs, rates, payloads |
| SOME/IP | unicast addr, SD multicast group, port | ARXML / FIBEX → service + instance + methods | services actually offered via SD |
| WiFi / BLE | — | — | scanned APs, GATT services |

Every protocol has the same triple: a few settings, a vendor description file, live discovery.

---

## 3. Plane A — configuration as facets

### 3.1 Why not more subclasses

Capabilities are currently expressed by single inheritance (`ECUComponent`, `NetworkComponent`,
`ADBDevice`). A DoIP ECU is simultaneously an ECU and a network node. Single inheritance cannot say
that, so the workaround is already in the code — `target.py:35-36`:

```python
ip = comp.properties.get("ip_address") if isinstance(comp.properties, dict) else None
return ip or getattr(comp, "ip_address", None)
```

Three lookup paths for one attribute. Extending by subclass is combinatorial. Use composition.

### 3.2 Core defines the mechanism, not the protocols

**Core ships zero protocol facets.** A fixed set of `DoipFacet`/`CanFacet`/`SomeipFacet` classes in
`iotsploit-core` would just replace seven `Component` subclasses with four `Facet` subclasses: adding
a protocol would still mean editing and releasing core. That is the design being replaced, not the
replacement.

The governing rule:

> **A facet ships with the code that consumes it.**

`DoipFacet` lives beside the DoIP driver, `CanFacet` beside the CAN driver. Core contains only:

```python
# iotsploit-core/src/iotsploit_core/domain/facet.py
class Facet(BaseModel):
    model_config = ConfigDict(extra="allow")     # never lose an unknown key

class RawFacet(Facet):
    """Fallback for a facet key with no registered type. Preserves the payload verbatim."""

class FacetRegistry:
    @classmethod
    def register(cls, key: str, facet_cls: type[Facet]) -> None: ...
    @classmethod
    def resolve(cls, key: str, raw: dict) -> Facet: ...      # registered class, else spec, else RawFacet
    @classmethod
    def schemas(cls) -> dict[str, dict]: ...                 # feeds GET /api/targets/facet-schemas

class Component(BaseModel):
    component_id: str
    name: str
    type: str
    status: str = "active"
    facets: Dict[str, Facet] = Field(default_factory=dict)
    properties: Dict[str, Any] = Field(default_factory=dict)   # unstructured leftovers only
```

Identity fields (`component_id`, `name`, `type`, `status`) stay closed by design. Everything
protocol-specific is open.

A plugin registers its own facet at load time, next to the code that reads it:

```python
# iotsploit-drivers/.../doip/facets.py — ships WITH the driver
@register_facet("doip")
class DoipFacet(Facet):
    logical_address: int                       # canonical Plane B join key
    tester_address: int = 0x0E80
    host: Optional[str] = None                 # falls back to the "net" facet
    port: int = 13400
    security_pin: Optional[SecretStr] = None
```

Adding SOME/IP is then a new plugin, not a core release.

### 3.3 Three tiers of openness

A facet only has value when some code consumes it: `logical_address` matters because `doip_mgr`
opens a socket to it. Code that does not exist yet cannot read a field invented at runtime. So
"fully dynamic facet types" buys a validated form, not a capability — and the tiers must be chosen
accordingly.

| Tier | Defined by | Adding one costs | Typed | Use for |
|---|---|---|---|---|
| 1 — core class | core devs | a core release | ✅ | nothing: **do not use** |
| 2 — plugin class | plugin author | shipping a plugin | ✅ | anything a driver/plugin acts on |
| 3 — `FacetSpec` row | a user, at runtime | inserting a row | ❌ | pure inventory/annotation data |

Tier 3 exists so recording "asset tag", "owner", "bench position" needs no code at all:

```python
class FacetSpec(Base):            # a row, not a class
    key         = Column(String, primary_key=True)   # "asset"
    title       = Column(String)
    json_schema = Column(JSON)                       # JSON Schema, validated on write
    source      = Column(String)                     # "plugin" | "user"
    version     = Column(Integer, default=1)
```

**Resolution order** (`FacetRegistry.resolve`): registered class → `FacetSpec` row → `RawFacet`.
Both of the first two yield a JSON Schema, so `GET /api/targets/facet-schemas` and the Flutter dialog
treat them identically — the UI cannot tell tier 2 from tier 3, and does not need to.

### 3.4 Unknown facets must round-trip losslessly

If a plugin is uninstalled, not yet loaded, or newer than this backend, its facet key is unknown.
An unknown key must be **stored and returned verbatim** — never dropped, never rejected.

Otherwise uninstalling a plugin silently destroys configuration for every target that used it, and a
round-trip through an older backend quietly deletes fields. This is why `Facet` sets `extra="allow"`
and why `RawFacet` exists rather than raising.

| Situation | Behavior |
|---|---|
| Key registered (tier 2/3) | validate on write; typed access; schema published |
| Key unknown | wrap in `RawFacet`; store as-is; UI shows a read-only JSON block |
| Registered later | existing rows validate on next load; no migration needed |
| Registration removed | rows degrade to `RawFacet`; data intact |

Validation is therefore **schema-on-write for registered facets, schema-on-read for the rest** — the
same split as Planes A and C overall.

### 3.5 What this buys

- **Schema-on-write where it counts.** `logical_address: int` means `0x1011` and `"0x1011"` cannot
  both be stored. That is what makes the Plane B join reliable.
- **A schema the UI can render.** `model_json_schema()` is free for tier 2, and tier 3 is a JSON
  Schema already. The Flutter dialog renders typed, labeled, validated fields instead of the
  hand-rolled string key/value editors in `target_edit_dialog.dart` (`:291`, `:669-728`).
- **New protocols without touching core** — see `PLUGIN_PACKAGING_PLAN.md`.
- **Secret handling.** `security_pin: SecretStr` stops `export_targets_to_json()` leaking PINs.

`get_ecu_ip` collapses to one path: `comp.facet("net").ip_address` (typed when the net facet is
registered, `None` when it is not).

### 3.6 Storage

Plane A stays a JSON column on the `targets` row. That is **correct here**: the payload is small,
bounded, always read whole, never filtered on in SQL. JSON columns are only wrong for the unbounded
collections of Planes B and C. No persistence change is needed beyond existing serialization.

### 3.7 Config currently hardcoded in Python (delete as part of this work)

| Location | Value | Moves to |
|---|---|---|
| `doip_mgr.py:21-22` | `DHU_Addr = 0x1201`, `TCAM_Addr = 0x1011` | `DoipFacet.logical_address` |
| `doip_mgr.py:146` | `__SAT_ENV__VehicleInfo_DHU_PIN` | `DoipFacet.security_pin` |
| `vehicle_utils.py:60` | `doip_addr=0x1001` + `ECU_REGISTRY` | `DoipFacet.logical_address` |
| `Vehicle_Model.py:52-70` | per-ECU `can_id` on `ECUBase`/`DHU`/`TBOX` | `CanFacet` / Plane B |

After this, adding a vehicle is a target edit, not a code edit. Do all four together or you will fix
the same class of problem twice.

### 3.8 Backward compatibility

A model validator promotes legacy shapes on load: typed subclass fields (`ADBDevice.adb_serial_id`)
and known `properties` keys migrate into the matching facet. Existing DB rows and `conf/target.json`
keep working untouched. Keep `ADBDevice`/`NetworkComponent`/`ECUComponent` as deprecated shims for
one release, then delete.

---

## 4. Plane B — the reference catalog

The existing DoIP catalog hierarchy is correct and stays:

```
ECU → SW → Service → DataIdentifier → ResponseItem(Offset, Size, Formula, Unit, ...)
```

It has four defects that silently corrupt joins, plus one generalization.

### 4.1 Defect 1 — no versioning root

`ECU` is one global table. Import two vendors' DSA XML and `address="0x1011"` matches two unrelated
ECUs; `dids_for()` returns a union of two vehicles.

```python
class DsaRelease(models.Model):
    vehicle_model = models.CharField(max_length=128)    # "zeekr_001x"
    version       = models.CharField(max_length=64)
    source_file   = models.CharField(max_length=512)
    imported_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["vehicle_model", "version"],
                                        name="uq_dsa_release")]

class ECU(models.Model):
    bind_release = models.ForeignKey(DsaRelease, on_delete=models.CASCADE)   # NEW
```

Reference data is immutable per release: a new XML creates a new `DsaRelease`, never mutates rows.
Old scan results stay interpretable against the catalog version they were taken with.

### 4.2 Defect 2 — non-canonical join key

`ECU.address = CharField(max_length=16)` is written straight from the XML attribute
(`DoIP_Diagnostic_Database_Model.py:56`). `0x1011`, `1011`, `0X1011` are three distinct strings and
none equals `DoipFacet.logical_address: int`.

```python
class ECU(models.Model):
    address_raw = models.CharField(max_length=16)               # as authored, provenance
    address     = models.PositiveIntegerField(db_index=True)    # canonical join key
```

Convert once at import. A join key must have exactly one representation.

### 4.3 Defect 3 — no import idempotency

No unique constraints anywhere, so re-running an import duplicates every row.

```text
ECU:             (bind_release, address)
SW:              (bind_ECU, DiagnosticPartNumber)
Service:         (bind_SW, Service_ID)
DataIdentifier:  (bind_Service, DataIdentifier_ID)
```

Make `Parse_DSA_XML` transactional and upsert-based (`update_or_create` on the natural key) so a
partial failure leaves no half-imported release.

### 4.4 Defect 4 — the catalog is unreachable

`Parse_DSA_XML` has no caller anywhere in the repository. Wire it to a management command/endpoint
taking an XML path plus the `vehicle_model`/`version` it belongs to, returning the created release.

### 4.5 Generalization — the `Endpoint` spine

With five protocols, a naive design means five schemas and five reconcilers. Two observations
collapse that:

**They share a decode spec.** `ResponseItem(Offset, Size, Formula, Unit, ...)` *is* a CAN signal.
Same concept, different vendor vocabulary. One `DecodeSpec` table serves both.

**They share an identity.** A DID, a CAN message, a SOME/IP service and a TCP port are all
*addressable*: a canonical id, scoped to an anchor, that a tool can probe for and record a result
against. That shared identity is what makes one set-difference reconciler possible (§7).

**`Endpoint` means addressable — nothing weaker.** An earlier draft also listed VLANs here. That was
wrong: a VLAN is not something you query by id, it is a *segment that other endpoints live in*.
VLANs and buses are **scopes**, and scopes belong in Plane T as nodes, not in the catalog as
endpoints (§4.6). Keeping `Endpoint` narrow is deliberate — a vaguer `CatalogObject` would admit
anything and lose the property the reconciler depends on.

```python
class Endpoint(models.Model):
    bind_release = models.ForeignKey(DsaRelease, on_delete=models.CASCADE)
    protocol     = models.CharField(max_length=32)      # "uds" | "can" | "someip" | "tcp"
    address      = models.CharField(max_length=64)      # canonical, protocol-specific
    name         = models.CharField(max_length=255)
    interaction  = models.CharField(max_length=16)      # see below
    anchor_kind  = models.CharField(max_length=16)      # "component" | "bus" | "network"
    anchor_ref   = models.CharField(max_length=128)     # component id | bus id | segment id
    attrs        = models.JSONField(default=dict)       # protocol detail not worth a column

    class Meta:
        constraints = [UniqueConstraint(
            fields=["bind_release", "protocol", "address", "anchor_ref"],
            name="uq_endpoint")]
        indexes = [models.Index(fields=["bind_release", "protocol", "anchor_ref"])]

class DecodeSpec(models.Model):
    bind_endpoint = models.ForeignKey(Endpoint, on_delete=models.CASCADE)
    name, offset, size, formula, unit, ...
```

**`interaction` is required, because "did it respond?" is not one question.** These protocols differ
in how presence is even established, and a single reconciler must not assume UDS semantics:

| `interaction` | Protocols | "Present" means | Observed as |
|---|---|---|---|
| `request_response` | UDS/DoIP | answered without an NRC | `observed_property="response"` |
| `broadcast` | CAN | frame seen on the bus, often periodic | `observed_property="presence"` |
| `offered` | SOME/IP | announced via service discovery | `observed_property="offered"` |
| `listening` | TCP/UDP | socket accepted a connection | `observed_property="state"` |

Keep the existing typed DoIP tables; the spine is a thin identity layer over them
(supertype/subtype). §7's set difference then works for every protocol, while anything semantic
(security requirements, NRC meanings) stays protocol-specific and is looked up through the subtype.

### 4.6 Anchors and scopes: why topology comes first

| Catalog object | Anchors to | Which is a… |
|---|---|---|
| DID | a **component** (one ECU) | node |
| SOME/IP service | a **component**, reachable over a network | node |
| TCP port | an **IP endpoint** on a component | node |
| **CAN message** | a **bus** — shared medium, one sender, many receivers | **scope** |
| *VLAN, CAN bus, Ethernet segment* | — *these are the scopes themselves* | **node in Plane T** |

DIDs anchor to components, which already exist. CAN messages anchor to **buses**, which do not.
`anchor_ref` for a CAN message is meaningless until a bus is a real entity with a stable id — a
string like `"CAN-B"` invented by the importer would need migrating the moment topology lands.

**Therefore the topology primitives must land before the multi-protocol importers**, not after them.
See §8: Phase 7 creates bus/segment entities and the `Edge` model; Phase 8 imports DBC/ARXML against
them. Full topology editing and graph projection stay late.

### 4.7 Two ORMs, one database

Plane A is SQLAlchemy, Plane B is the Django ORM, and `sqlalchemy_database.py:16-17` points both at
`settings.DATABASES["default"]["NAME"]` — the same SQLite file, so the join is physically possible.

**Do not declare a DB-level foreign key across that boundary.** Neither ORM can migrate or enforce it
coherently. Use a canonical key plus one explicit resolver service, with the "release exists" check in
the resolver. This is the standard bounded-context pattern.

---

## 5. Plane C — observations

Two tables. Facts are append-only; a scan row exists even when it finds nothing.

```text
scan_runs(scan_id, run_id, target_id, component_id, source, scope_key,
          status, is_complete, facts_count, started_at, completed_at, error_summary)

observations(id, scan_id, protocol, subject_kind, subject_id, observed_property,
             value, observed_at)
```

### 5.1 Why one table is insufficient

A fact-only table cannot represent a *successful scan that returned nothing*. This matters
immediately: `ip_scan` returns an empty dict when no internal IPs are exposed. Without a `scan_runs`
row, that successful empty snapshot cannot be listed, diffed, or used to remove previously-current
hosts. `scan_runs` also distinguishes a failed scan, a partial scan, two scans with different scopes,
and several plugin scans grouped into one user-visible run.

### 5.2 Identity and semantics

- `run_id` groups a user-visible workflow ("full vehicle scan"); `scan_id` is one plugin scope.
- `source` is the stable plugin name (`ip_scan`, `doip_did_enum`).
- `component_id` is NULL for target-level facts.
- `scope_key` identifies the comparable population within a source (`tcam_ap_forward:fast`,
  `did:default_session`). It must never contain credentials.

Two scans are diffable only when `(target_id, component_id, source, scope_key)` match. This stops a
fast port scan from reporting everything outside its range as disappeared.

`status ∈ {running, succeeded, failed, persistence_failed, abandoned}`. `is_complete=True` means the
facts are the complete snapshot for the declared scope. **Only `succeeded AND is_complete` may define
current state or disappearance.** A startup sweep marks stale `running` rows `abandoned`.

`current()` selects, per `(target_id, component_id, source, scope_key)`, the latest successful
complete scan and returns exactly its observations — as **records, not a lossy dict**. If two sources
report the same fact identity, both stay visible; conflict resolution is a presentation policy, never
hidden last-writer-wins.

### 5.3 Fact identity is columns, not a packed string

An earlier draft encoded identity inside a dotted key (`doip.did.F190`). That is rejected: it
violates §2 rule 4 — anything joined or filtered on needs a column. A packed key forces
`key.rsplit(".", 1)` to recover a DID id and `LIKE 'doip.did.%'` to select a population, which is the
same unqueryability that disqualified JSON blobs in the first place.

Identity decomposes into four columns, named after the ISO 19156 / SOSA observation vocabulary:

| Column | Meaning | Examples |
|---|---|---|
| `protocol` | wire protocol | `uds`, `can`, `someip`, `tcp`, `ip`, `adb` |
| `subject_kind` | what type of thing was observed | `did`, `message`, `service`, `port`, `host`, `self` |
| `subject_id` | canonical id of that thing; NULL for `self` | `F190`, `0x123`, `1234:0001`, `22` |
| `observed_property` | which property of it | `response`, `presence`, `offered`, `state`, `alive` |

```text
protocol  subject_kind  subject_id     observed_property  value
────────────────────────────────────────────────────────────────────────────────────────
uds       did           F190           response           {"nrc": null, "len": 17, "session": "default"}
uds       did           F1C4           response           {"nrc": "0x33", "len": 0}
can       message       0x123          presence           {"dlc": 8, "period_ms": 100}
someip    service       1234:0001      offered            {"methods": [1, 2, 5]}
tcp       port          22             state              "open"
ip        host          198.18.34.1    alive              true
adb       self          NULL           serial             "MB2023DHU123456"
```

`subject_kind = "self"` with `subject_id = NULL` carries scalar facts about the target or component
itself, so the open-world property is preserved: a new tool inventing a new `observed_property` still
needs no schema change.

**A display key remains, but is derived and never parsed:**
`f"{protocol}.{subject_kind}.{subject_id}.{observed_property}"`, for UI and logs only.

`subject_id` must be canonical per protocol (the same normalization Plane B applies at import,
§4.2). That is what makes §7 a column join instead of string surgery.

Validated at the boundary: known `protocol`/`subject_kind` shape, non-empty `observed_property`,
JSON-serializable value, max id length, max serialized value size. A full vocabulary registry is
deferred until observed drift justifies it.

### 5.4 SQLAlchemy models

`iotsploit-django/src/iotsploit_django/adapters/django/observation_models.py`, both models sharing
one `_db` instance:

```python
class ScanRunDBModel(Base):
    __tablename__ = "scan_runs"
    scan_id       = Column(String, primary_key=True)
    run_id        = Column(String, nullable=False, index=True)
    target_id     = Column(String, nullable=False)
    component_id  = Column(String, nullable=True)
    source        = Column(String, nullable=False)
    scope_key     = Column(String, nullable=False)
    status        = Column(String, nullable=False)
    is_complete   = Column(Boolean, default=False, nullable=False)
    facts_count   = Column(Integer, default=0, nullable=False)
    started_at    = Column(DateTime, nullable=False)
    completed_at  = Column(DateTime, nullable=True)
    error_summary = Column(String, nullable=True)
    __table_args__ = (
        Index("ix_scan_current", "target_id", "component_id", "source", "scope_key",
              "status", "is_complete", "completed_at"),
        Index("ix_scan_run", "target_id", "run_id"),
    )

class ObservationDBModel(Base):
    __tablename__ = "observations"
    id                = Column(Integer, primary_key=True, autoincrement=True)
    scan_id           = Column(String, ForeignKey("scan_runs.scan_id", ondelete="CASCADE"),
                               nullable=False)
    protocol          = Column(String, nullable=False)
    subject_kind      = Column(String, nullable=False)
    subject_id        = Column(String, nullable=True)     # NULL when subject_kind == "self"
    observed_property = Column(String, nullable=False)
    value             = Column(JSON, nullable=False)
    observed_at       = Column(DateTime, nullable=False)
    __table_args__ = (
        UniqueConstraint("scan_id", "protocol", "subject_kind", "subject_id", "observed_property",
                         name="uq_observation_identity"),
        Index("ix_observation_scan", "scan_id"),
        # cross-target queries: "which targets expose 0xF190?"
        Index("ix_observation_subject", "protocol", "subject_kind", "subject_id"),
    )
```

Enable `PRAGMA foreign_keys=ON` for this engine and test cascade deletion.

**Do not assume `get_default_sqlalchemy_db()` returns the same declarative `Base` as
`target_models.py`** — it creates a fresh engine/session/Base on every call. Add an idempotent
`initialize_observation_schema()` using this module's own metadata and call it explicitly from Django
startup (`IoTSploitDjangoConfig.ready()`), with an integration test proving both tables exist.

### 5.5 Domain contracts

`iotsploit-core/src/iotsploit_core/domain/observation.py` — no repository or Django imports:

```python
class Fact(BaseModel):
    """One observation's identity plus its value. Identity is fields, never a packed string."""
    protocol: str
    subject_kind: str
    subject_id: str | None = None          # None when subject_kind == "self"
    observed_property: str
    value: JsonValue

class ObservationScope(BaseModel):     component_id: str | None = None; scope_key: str
class ObservationBatch(BaseModel):     scope: ObservationScope; facts: list[Fact]; is_complete: bool = True
class StartedScan(BaseModel):          scan_id: str; scope: ObservationScope
class ObservationRecord(Fact):         scan_id, target_id, component_id, source, scope_key, observed_at
class ObservationIdentity(BaseModel):  component_id, source, scope_key, protocol, subject_kind, subject_id, observed_property
class ObservationDiff(BaseModel):      appeared: list[...]; disappeared: list[...]; changed: list[...]
```

`facts` is a `list[Fact]`, not a `dict` — a dict would force identity back into a string key, which
is what §5.3 rejects. Use a JSON value type, not `Any`, so unsupported values fail before a
transaction opens.

Two ports, deliberately separate responsibilities:

```python
class ObservationProducer(Protocol):
    def observation_scopes(self, target, parameters) -> list[ObservationScope]: ...
    def observation_batches(self, result) -> list[ObservationBatch]: ...

class ObservationSink(Protocol):
    def start_scans(self, *, run_id, target_id, source, scopes) -> list[StartedScan]: ...
    def complete_scan(self, scan_id, facts, *, is_complete) -> None: ...
    def fail_scan(self, scan_id, error_summary) -> None: ...
```

Plugins that do not implement `ObservationProducer` produce no observations. This is separate from
`ExploitResult.data`, which stays the execution-response contract and may hold raw output and timing.

### 5.6 Repository API

```python
start_scans(*, run_id, target_id, source, scopes) -> list[StartedScan]
complete_scan(scan_id, facts, *, is_complete) -> int
fail_scan(scan_id, error_summary=None) -> None
current(target_id, *, component_id=None, source=None,
        protocol=None, subject_kind=None, subject_id=None) -> list[CurrentObservation]
find_targets_exposing(*, protocol, subject_kind, subject_id) -> list[str]   # cross-target, indexed
list_runs(target_id, *, limit=20, cursor=None)
list_scans(target_id, *, run_id=None, limit=50)
diff_scans(scan_a, scan_b) -> ObservationDiff
history(target_id, identity: ObservationIdentity, *, limit=50)
purge_target(target_id) -> int
```

Return `StartedScan` records rather than using Pydantic scopes as dict keys — they are not hashable
by default. `complete_scan()` inserts all facts and transitions status in **one transaction**;
a batch is all-or-nothing. `diff_scans()` rejects failed, incomplete, or incomparable scans rather
than producing a misleading diff.

---

## 6. Plane T — topology and the derived graph

The typed edge model *is* a property graph — labeled nodes, labeled edges, properties on both:

```python
class Edge(BaseModel):
    source: str                     # component_id | interface_id | bus_id | target_id
    target: str
    relation: str                   # "connects" | "hosts" | "bus_member" | "reachable_from"
    properties: Dict[str, Any] = Field(default_factory=dict)
```

One more JSON column on `targets`, mirroring `components`/`interfaces`. A model validator checks both
endpoints resolve to known ids.

The graph is **projected**, never stored:

```python
def build_current_graph(target_id) -> nx.MultiDiGraph:   """Authored structure + current observations."""
def build_scan_graph(target_id, scan_id) -> nx.MultiDiGraph:   """One completed scan."""
```

Use `MultiDiGraph` (parallel relationships from different tools). Stable node ids:

```text
target:<id>   component:<id>   bus:<name>   service:tcp:<port>   did:<canonical>   interface:<id>
```

Projected edges carry provenance (`source`, `scope_key`, `scan_id`, `observed_at`). Scalar facts with
no graph meaning stay relational — do not create a node per timestamp or JSON leaf. Projection rules
are explicit per domain; never infer security relationships from arbitrary dotted keys.

**Why the graph is a view, not storage:** property-graph node properties are untyped key-value pairs
(Neo4j forbids nested maps outright), so it re-introduces the `Dict[str, Any]` we are escaping;
48k observations on one target node is a textbook supernode; and PGM has no native bitemporality, so
history becomes a time-tree hack. Constraints: NetworkX is an **optional, lazily imported** dependency
(`iotsploit-core` ships to PyPI); the graph is cacheable by latest completed scan ids; reachability
claims require real typed edges — containment alone is not enough.

---

## 7. Cross-plane reconciliation — the payoff

```python
def endpoints_for(component, release, protocol) -> QuerySet[Endpoint]:
    """Resolve documented endpoints. Nothing is copied into the target."""
    addr = component.facet(DoipFacet).logical_address
    return Endpoint.objects.filter(bind_release=release, protocol=protocol, anchor_ref=str(addr))
```

Because §5.3 made `subject_id` a column holding the same canonical form as `Endpoint.address`, both
sides are plain sets of ids — no key parsing anywhere:

```python
PRESENT = {                      # what "present" means, per §4.5 interaction model
    "request_response": lambda v: v.get("nrc") is None,
    "broadcast":        lambda v: v.get("count", 0) > 0,
    "offered":          lambda v: v is not None,
    "listening":        lambda v: v == "open",
}

def reconcile(component, release, protocol, subject_kind, interaction):
    documented = {e.address for e in endpoints_for(component, release, protocol)}
    observed   = current_observations(target_id, component.component_id,
                                      protocol=protocol, subject_kind=subject_kind)
    present    = {r.subject_id for r in observed if PRESENT[interaction](r.value)}

    return {
        "undocumented": present - documented,     # hidden/debug endpoints → a finding
        "missing":      documented - present,     # config drift
    }
```

**Scope of the claim:** the *set difference* is one engine for every protocol — undocumented CAN
messages, undocumented SOME/IP services, unexpected open ports all fall out of the same code. What is
**not** shared is semantics: `unprotected` (an endpoint that answered without the security access its
catalog entry requires) is UDS-specific and is computed through the DoIP subtype, not the spine.
Do not generalize protocol semantics just because identity generalized.

`undocumented` and `unprotected` are plausibly the most valuable output of the whole scan, and
neither is computable if the two sets are merged or if the last scan's results were overwritten.
The separation *is* the feature.

**Sizing:** 800 DIDs × 3 ECUs × 20 scans ≈ 48k rows — negligible for indexed SQLite. The same data as
a JSON blob is a ~500KB row rewritten on every unrelated edit. Verify query latency rather than
assuming it.

---

## 8. Phases

Each phase is independently shippable and revertible. One phase = one commit = one re-measurement.
Run `tools/testing/test-python-full.sh` before every commit; enable hooks once with
`git config core.hooksPath tools/git-hooks`.

| # | Phase | Plane | Touches existing code | Est. | Prereq |
|---|---|---|---|---|---|
| 0 | Serialization dedup | A | yes | ~0.5d | — |
| 1 | Observation contracts, tables, repository, tests | C | yes | ~1d | — |
| 2 | Execution lifecycle + `ip_scan` conversion | C | yes | ~1d | 1 |
| 3 | **Hardware validation checkpoint** | C | no | ~2h | 2 |
| 4 | Catalog integrity: release, canonical address, constraints, importer | B | yes | ~1d | — |
| 5 | `Facet` + `FacetRegistry` + legacy promotion | A | yes | ~1–2d | 0 |
| 6 | Protocol facets in their driver packages; delete hardcoded config (§3.7) | A | yes | ~1d | 5 |
| 7 | **Topology primitives**: bus/segment entities + `Edge` model + validation | T | yes | ~1d | 5 |
| 8 | `Endpoint`/`DecodeSpec` spine + DBC/ARXML importers | B | yes | ~2d | 4, 7 |
| 9 | Facet schema endpoint + Flutter typed model & schema-driven dialog | A | yes | ~2–3d | 5 |
| 10 | Convert remaining discovery tools | C | per plugin | incremental | 3 |
| 11 | Observation HTTP endpoints | C | yes | ~1d | 3 |
| 12 | Flutter observation views | C | yes | ~1–2d | 11 |
| 13 | Endpoint enumeration plugins (DID / CAN / SOME/IP) + reconciliation report | B×C | new | ~2–3d | 3, 8 |
| 14 | Derived NetworkX projection | T | new | ~1d | 7 |
| 15 | Retention and target-deletion lifecycle | C | yes | ~0.5d | 3 |

**Phases 1–3 are the initial commitment.** Stop after 3 and inspect real output before converting
more tools.

**Phase 4 has a deadline attached:** it must land before a second vendor DSA XML is imported, or the
catalog is corrupted in a way only a full re-import repairs.

**Phase 7 precedes Phase 8 deliberately.** CAN messages anchor to buses (§4.6). Importing a DBC
before bus entities exist would force the importer to invent string anchors that every later row
must be migrated off. Phase 7 is only the primitives — bus/segment entities, the `Edge` model, and
endpoint-resolution validation. Graph projection (14) and any topology editing UI stay late.

**Ordering note for DIDs only.** If you want the DID reconciliation before touching CAN at all,
Phase 8 can import DoIP-only endpoints without Phase 7, since DIDs anchor to components that already
exist. Take that shortcut only if CAN/Ethernet is genuinely out of scope for the release — otherwise
the anchor migration lands on you later.

### Phase 1 minimal — start here

This plan describes a destination. **Do not build the destination first.** The slice below is the
smallest thing that proves the model against real hardware. Everything else in §8 waits until it has.

Skip Phase 0 for now — it is a prerequisite for *facets* (Phase 5), not for observations.

#### Files

| File | Status | Approx. |
|---|---|---|
| `iotsploit-core/.../domain/observation.py` | new | ~40 LOC |
| `iotsploit-django/.../adapters/django/observation_models.py` | new | ~60 LOC |
| `iotsploit-django/.../adapters/django/observation_repository.py` | new | ~120 LOC |
| `iotsploit-django/tests/test_observation_repository.py` | new | ~150 LOC |
| `iotsploit-django/.../apps.py` | **modified** | +5 LOC (no `ready()` exists yet) |
| `iotsploit-exploits/.../ip_scan/ip_scan.py` | **modified** | ~30 LOC changed |

Two existing files touched. Everything else is new — that is the point.

#### Scope

```python
# domain/observation.py — data shapes only, no ports yet
class Fact(BaseModel):
    protocol: str; subject_kind: str; subject_id: str | None = None
    observed_property: str; value: JsonValue

class ObservationBatch(BaseModel):
    scope_key: str; component_id: str | None = None
    facts: list[Fact]; is_complete: bool = True
```

Repository — **four methods, nothing more**:

```python
start_scan(*, run_id, target_id, source, scope_key, component_id=None) -> str   # returns scan_id
complete_scan(scan_id, facts: list[Fact], *, is_complete=True) -> int           # one transaction
fail_scan(scan_id, error_summary=None) -> None
current(target_id, *, component_id=None, source=None) -> list[ObservationRecord]
```

Both tables ship with their **final column shape** (§5.4), including `status` and `is_complete`.
Only `succeeded` and `failed` are produced at this stage; the other states are columns waiting for
Phase 2 logic.

#### Wiring: call the repository directly from `ip_scan`

No `ObservationSink` port, no `ObservationProducer`, no changes to `ExploitPluginManager` yet.
`ip_scan` calls the repository itself, wrapping its own scan lifecycle.

This is acceptable **only** because `ip_scan.py:6` already imports `iotsploit_django.tools.env_mgr`,
so the dependency it creates already exists. It is deliberate temporary coupling, lifted in Phase 2
when the port and the shared execution wrapper arrive. It does not apply to any plugin in
`iotsploit-core`.

#### Do not defer these

Each is cheap now and expensive later, because deferring means migrating data rather than adding code:

| Item | Cost of deferring |
|---|---|
| The five-column identity (§5.3) | schema migration + rewriting every stored fact |
| `status` / `is_complete` columns | backfill with values nobody can reconstruct |
| `uq_observation_identity` | duplicate rows to dedupe by hand |
| FK + `ondelete="CASCADE"` + `PRAGMA foreign_keys=ON` | orphaned observation rows |
| Canonical `subject_id` at the producer | permanently dirty ids; `0x123` and `123` never reconcile |
| Append-only discipline (never `UPDATE` a fact) | history that silently has holes |

#### Deliberately excluded

`diff_scans`, `history`, `list_runs`, `list_scans`, `purge_target`, `find_targets_exposing`, the
`ObservationProducer`/`ObservationSink` ports, the shared execution wrapper, all Celery paths, HTTP
endpoints, Flutter views, retention — plus all of Planes A, B and T.

Compute the first diff by hand in a test or a shell. If the data supports a hand-written diff, the
model is right; if it doesn't, better to learn that before building nine more methods on it.

#### Tests — six, not thirteen

| Test | Assertion |
|---|---|
| successful empty scan | scan row exists, complete, `facts_count=0` |
| empty snapshot replaces previous | previously-current host is absent from `current()` |
| failed scan | does not replace the last successful snapshot |
| atomic batch | one invalid fact rolls back the whole batch |
| cascade | deleting a scan deletes its observations |
| startup | both tables exist after Django initialization |

#### Definition of done

- [ ] Both tables created via `initialize_observation_schema()` from `apps.py::ready()`.
- [ ] `ip_scan` writes facts and no longer reads or writes `TCAM_AP_SCAN_IP_LIST`
      (`ip_scan.py:131,141`).

> **This is a deliberate behavior change, not a pure refactor.** The read at `ip_scan.py:131` is a
> cache-hit guard (`iplist = env_mgr.query(...)` followed by `if iplist is None:`), so today a second
> run reuses the first run's list and never re-scans. Removing it makes every run actually scan:
> slower, and the only way a diff can ever detect change. Say so in the commit message — someone will
> notice the runtime increase and file it as a regression.
- [ ] Two real scans against hardware; the second, with zero facts, clears the first from `current()`.
- [ ] A hand-written diff over `current()` output names the intended change and little else.
- [ ] `targets.updated_at` is unchanged by scan persistence.
- [ ] `tools/testing/test-python-full.sh` passes.

**Then stop and look at the output** before starting Phase 2.

### Phase 0 — serialization dedup

Prerequisite for facets: it removes duplication that would otherwise have to change three times.

1. Collapse `get_info()` — base `Target.get_info()` returns `self.model_dump()`; keep overrides only
   where a subclass genuinely adds fields (currently neither does). Verify `assert old == new` on a
   vehicle and a generic fixture.
2. One `_apply_target(model, target)` helper used by both `TargetDBModel.__init__` and the update
   branch of `save_target` (they repeat the same seven-field copy).
3. Unify component hydration between `create_target_instance` and `parse_and_set_target_from_json`.
   **Preserve the class-selection difference:** the JSON path uses `self.targets.get(type, Vehicle)`;
   the request path maps only `"vehicle"` → `Vehicle`, everything else → `GenericTarget`. Extract
   only the shared hydration, or give the helper an explicit fallback mode.

Expected: −65 to −95 LOC. Record the delta in `OPTIMIZATION_GUIDE.md`.

### Phase 2 — execution lifecycle

Extend `ExploitPluginManager` with an injected `ObservationSink`; core must never lazily import
`iotsploit-django` — the Django composition root supplies it. The common in-process wrapper:

1. normalize target, require `target_id` for an observation-producing plugin;
2. ask the plugin for declared scopes;
3. generate `run_id`/`scan_id`, insert `running` rows;
4. execute;
5. collect opt-in batches;
6. atomically complete each declared scope, **including empty batches**;
7. mark failed when execution raises or a declared scope produced no batch;
8. return `run_id` and `scan_ids` in the response.

**Do not derive scan status from `ExploitResult.success`** — plugins use it as an assessment verdict
(`ip_scan` returns `success=False` when it *successfully* finds exposed IPs). A returned batch means
the scope ran; `is_complete` decides whether it may define current state.

Observation persistence is best-effort: a failure must not change or mask the plugin's result — emit
a structured warning and a `persistence_failed` state.

**Fix async coverage.** The Celery task calls `plugin_instance.execute_async()` directly, bypassing
manager post-processing. Route it through the same wrapper (scheduling disabled so it cannot enqueue
itself). Cover: sync `execute_plugin`, manager-scheduled Celery, explicit async endpoint, direct
`execute_plugin_async` fallback, sudo runner. Test that exactly one lifecycle is recorded per scope
in both paths.

**Convert `ip_scan`.** Delete both the read and write of `TCAM_AP_SCAN_IP_LIST` — observations are
evidence, not a cache; using `current()` as a cache would stop a new scan detecting change.

```python
ObservationBatch(
    scope=ObservationScope(scope_key=f"tcam_ap_forward:{scan_mode}"),
    facts=[
        Fact(protocol="ip", subject_kind="host", subject_id=ip,
             observed_property="alive", value=True)
        for ip in iplist
    ],
    is_complete=True,
)
```

### Phase 3 — validation checkpoint (do not skip)

1. Scan a real target → `scan_id_a`. 2. Change something observable. 3. Identical scope → `scan_id_b`.
4. `diff_scans(a, b)`. 5. Inspect `current(...)`. 6. Force a failure and confirm current state still
comes from the last successful complete scan.

Success: the diff names the intended change and little else; disappearance works with a zero-fact
second scan; failed/incomplete scans do not erase current state; provenance identifies target,
source, scope, and both scan ids.

| Symptom | Diagnosis | Fix before continuing |
|---|---|---|
| huge noisy diff | volatile facts included | exclude them or narrow the scope |
| empty diff after a real change | fact not emitted, or scope differs | fix producer output/scope |
| false disappearances | incomplete scan or scope mismatch | correct completeness handling |
| duplicate facts | `subject_id` not canonical | normalize at the producer while one exists |
| current shows absent hosts | latest-snapshot query wrong | fix the query before adding tools |

### Phase 9 — Flutter

The UI has no target model: targets flow as `Map<String, dynamic>` with field names as bare string
literals — **118 occurrences**, concentrated in `targets_page.dart` (84) and `target_edit_dialog.dart`
(34). `target_card.dart` has none. 2941 LOC across the three.

Type registries are **already served from the backend** and consumed by the dialog
(`target_edit_dialog.dart:78-110` → `get_target_types/`, `get_component_types/`), so that work is
done; the literals at `:35`/`:44` are offline fallbacks, not a second source of truth.

1. Add `ui/lib/models/target.dart` (`Target`/`Component`/`Interface`, `fromJson`/`toJson`, identical
   JSON keys). Parse at the boundary; a `toJson()` bridge keeps existing widgets compiling.
2. Migrate the two files off raw map access, one at a time (dialog is smaller — start there).
3. Add `get_facet_schemas/` **following the existing type-endpoint pattern** in `target_views.py`
   and `targets_urls.py` — do not invent a new convention.
4. Render the edit dialog's property tab (`:291`) and its key/value editors (`:669-728`) from the
   facet schemas, then extract the repeated form builders into reusable widgets.

Per step: `flutter analyze` clean + create/edit/delete round-trip against the running backend.

### Phase 10 — tool conversion

One plugin per commit. Each must declare comparable scopes, emit explicit batches, keep unrelated
detail in `ExploitResult.data` only, remove `Env_Mgr` discovery caches, and test empty/failed/
successful results. Order: `ip_scan → DoIP alive → ADB enumeration → WiFi scan → fuzzer summaries`.

Never persist raw stdout/stderr, commands, credentials, PINs, keys, or captures. Fuzzer detail stays
in its existing tables; observations carry only summary facts (verdict, crash count).

### Phase 11 — observation endpoints

| Route | Returns |
|---|---|
| `get_current_observations/` | current records with source, scope, component, scan, timestamp |
| `list_scan_runs/` | paginated user-visible runs |
| `list_scans/` | scan scopes and lifecycle state |
| `get_scan_diff/` | validated diff of two comparable scans |
| `get_observation_history/` | history for a full observation identity |

Validate target existence; reject incomparable diffs with HTTP 400; paginate; return typed shapes not
raw ORM dicts; keep `get_all_targets()` unchanged; update `docs/contracts/http_routes.json`; add
`@pytest.mark.contract` tests.

### Phase 15 — retention

Per comparable scope `(target_id, component_id, source, scope_key)`, not merely per target:

- keep the last 10 completed scans per scope;
- always keep the current-defining scan regardless of age;
- prune failed/abandoned scans after a separately configurable age;
- cascade observation deletion via `scan_id`;
- invalidate derived graph caches after pruning.

Target deletion must **explicitly** purge scan runs and observations — the target and observation
metadata are separate, so no ORM foreign key does this for you. Add an application-level deletion
service and tests so reusing a target id cannot expose stale findings.

### Affected code — full-plan inventory

Verified against the tree, not inherited from earlier drafts.

#### Python

| File | Phase | Change |
|---|---|---|
| `iotsploit-core/.../domain/observation.py` | 1 | new: `Fact`, batches, records |
| `iotsploit-django/.../adapters/django/observation_models.py` | 1 | new: 2 tables + schema init |
| `iotsploit-django/.../adapters/django/observation_repository.py` | 1 | new: repository |
| `iotsploit-django/.../apps.py` | 1 | **has no `ready()` at all** — add one to call the schema initializer |
| `iotsploit-exploits/.../ip_scan/ip_scan.py` (197 LOC) | 1–2 | emit facts; delete `TCAM_AP_SCAN_IP_LIST` read (`:131`) and write (`:141`) |
| `iotsploit-core/.../core/exploit_manager.py` | 2 | lifecycle wrapper in `execute_plugin` (`:382`), `execute_plugin_async` (`:360`), `execute_plugin_group` (`:521`) |
| `iotsploit-django/.../tasks/plugin_tasks.py` (`:75`) | 2 | calls `plugin_instance.execute_async()` directly, bypassing the manager |
| `iotsploit-django/.../tasks/legacy_tasks_impl.py` (`:26`) | 2 | **a second copy of the same bypass** — both must route through the wrapper or coverage is silently partial |
| `iotsploit-django/.../view_handlers/plugin_views.py` (`:263`, `:683`) | 2 | sync + async HTTP entry points |
| `iotsploit-core/.../domain/target.py` | 0, 5 | `get_info()` dedup; then `Facet`/`FacetRegistry`, `Component.facets` |
| `iotsploit-django/.../adapters/django/target_models.py` | 0 | `_apply_target()` helper; unify hydration |
| `iotsploit-django/.../tools/doip_mgr.py` (`:21-22`, `:146`) | 6 | delete address constants + PIN env read |
| `iotsploit-django/.../tools/vehicle_utils.py` (`:60`) | 6 | delete `ECU_REGISTRY.doip_addr` |
| `iotsploit-django/.../models/Vehicle_Model.py` (`:52-70`) | 6 | delete per-ECU `can_id` from `ECUBase`/`DHU`/`TBOX` |
| `iotsploit-django/.../models/DoIP_Diagnostic_Database_Model.py` | 4, 8 | `DsaRelease`, canonical `address`, unique constraints, reachable importer |
| `iotsploit-django/.../view_handlers/target_views.py` (`:361`, `:376`) | 9 | add `get_facet_schemas` beside the existing type endpoints |
| `iotsploit-django/.../web/api/targets_urls.py` (`:22-23`) | 9 | register the new route |
| `iotsploit-django/.../view_handlers/observation_views.py` | 11 | new |

**Two Celery bypasses, not one.** `plugin_tasks.py:75` and `legacy_tasks_impl.py:26` each call
`execute_async()` directly. Fixing only one produces observations that appear or vanish depending on
which task path ran — the worst possible failure mode, because it looks like real change.

#### Flutter (`ui/`)

Actual sizes: `target_edit_dialog.dart` **1277**, `targets_page.dart` **1206**, `target_card.dart`
**458** — **2941 LOC** total.

| File | Bracket-string map access | Phase | Change |
|---|---|---|---|
| `ui/lib/screens/targets/targets_page.dart` | **84** | 9 | parse into a typed model at the fetch boundary |
| `ui/lib/screens/targets/target_edit_dialog.dart` | **34** | 9 | schema-driven facet fields replace hand-rolled key/value pairs (`:291`, `:669-728`) |
| `ui/lib/widgets/cards/target_card.dart` | **0** | 9 | already receives typed values; little to do |
| `ui/lib/models/target.dart` | — | 9 | **new** — `ui/lib/models/` exists but has no target model |
| observation views | — | 12 | new |

**Correction to earlier drafts:** the type registries are **not** hard-coded and drifted. The dialog
already fetches them from the backend — `_fetchTargetTypes` / `_fetchComponentTypes`
(`target_edit_dialog.dart:78-110`) consume `get_target_types/` and `get_component_types/`
(`targets_urls.py:22-23`), with the literals at `:35`/`:44` serving only as offline fallbacks.

Two consequences: the "single source of truth for types" work is **already done**, so Phase 9 is
smaller than estimated; and `get_facet_schemas/` should follow that established pattern rather than
inventing a new one.

`target_card.dart` having zero raw map access means the typed-model migration is concentrated in two
files, not three.

---

## 9. Tests

| Test | Assertion |
|---|---|
| successful empty scan | listed, complete, zero facts |
| empty snapshot replaces previous | disappeared fact absent from `current()` |
| failed scan | does not replace last successful snapshot |
| incomplete scan | history retained, current state unchanged |
| component identity | same fact identity on two ECUs stays two records |
| source identity | conflicting tools stay distinguishable |
| cross-target subject query | `find_targets_exposing(protocol="uds", subject_kind="did", subject_id="F190")` uses the index, no table scan |
| canonical subject id | `0x123`/`123`/`0X123` from different producers collapse to one `subject_id` |
| reconciliation per interaction | `presence` for CAN and `response` for UDS both produce correct `undocumented` sets |
| anchor resolution | a CAN endpoint cannot be imported against a non-existent bus |
| scope validation | fast and full scans cannot be diffed |
| atomic batch | invalid fact rolls back the whole batch |
| large batch | 1,000 facts in one transaction |
| stable ordering | timestamps tie-break with scan/row ids |
| cascade | deleting a scan deletes its observations |
| startup | both tables exist after Django init |
| target purge | purges exactly one target |
| catalog idempotency | re-importing the same XML creates no duplicate rows |
| catalog scoping | two releases with the same ECU address stay separate |
| facet promotion | legacy `properties`/subclass fields migrate; round-trip is stable |
| facet round-trip | create → save → reload → `assert` equality |
| unknown facet preserved | a facet key with no registered type survives save/reload byte-for-byte |
| plugin unload | unregistering a facet type degrades rows to `RawFacet` without data loss |
| late registration | rows written before a plugin was installed validate once it registers |
| graph rebuild | projection is deterministic and reconstructible after cache loss |

```bash
poetry run pytest iotsploit-django/tests/test_observation_repository.py -v
tools/testing/test-python-full.sh
```

---

## 10. Security and reliability rules

- Observation emission is opt-in; never auto-persist all `ExploitResult.data`.
- Reject non-JSON values before opening the write transaction.
- Bound key length, facts per batch, serialized value size, and HTTP page sizes.
- Never store credentials, PINs, private keys, tokens, command lines containing secrets, or
  unredacted environment data. `security_pin` is `SecretStr` and excluded from JSON export.
- Error summaries are bounded and sanitized; full tracebacks stay in logs.
- Persistence failure never changes plugin success/failure semantics.
- Failed/incomplete scans never define current state or disappearance.
- Structured logging with `run_id`, `scan_id`, target, source, scope.
- No mutating MCP tools; the read-only safety/auth gate stays.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Empty scans vanish | durable `scan_runs` row written before execution |
| Failed scan looks like mass disappearance | only successful complete scans define snapshots |
| Same key from multiple ECUs/tools collides | preserve component, source, and scope identity |
| Async runs bypass recording | one execution wrapper shared by Celery and sync paths |
| Core imports Django | inject `ObservationSink` from the composition root |
| Secrets captured in results | explicit producer opt-in, validation, bounds, redaction |
| Fast/full scans produce false diffs | canonical `scope_key`; reject incomparable diffs |
| SQLAlchemy tables not created | explicit startup initializer; no shared-`Base` assumption |
| Target deletion leaves stale observations | application-level purge with tests |
| Second DSA import corrupts the catalog | Phase 4 lands first (release scoping + unique constraints) |
| Cross-ORM join breaks on format drift | canonical integer address; one resolver service |
| NetworkX becomes a second model | derived read-only projection, always rebuildable |
| Graph disconnected or misleading | require real typed edges before reachability claims |
| Storage grows indefinitely | per-scope retention preserving current-defining scans |
| Facet migration loses data | `extra="allow"`; legacy promotion validator; shims for one release |

---

## 12. Definition of done — phases 0–4

- [ ] Phase 0 dedup landed; LOC delta recorded in `OPTIMIZATION_GUIDE.md`.
- [ ] `scan_runs` and `observations` created explicitly at startup.
- [ ] Successful-empty, failed, incomplete, and populated scans all represented correctly.
- [ ] `current`, `diff_scans`, `history`, run/scan listing unit-tested.
- [ ] Identity includes target, component, source, scope, and key.
- [ ] Plugins opt in via `ObservationProducer`; raw result data is not auto-persisted.
- [ ] Sync and Celery paths share one observation lifecycle wrapper.
- [ ] `ip_scan` no longer reads or writes `TCAM_AP_SCAN_IP_LIST`.
- [ ] Execution responses expose `run_id` and `scan_ids`.
- [ ] Two real comparable scans produce a useful diff, including the zero-fact case.
- [ ] `targets.updated_at` unchanged by scan persistence.
- [ ] `DsaRelease` exists; `ECU.address` is canonical; import is idempotent and transactional.
- [ ] `Parse_DSA_XML` is reachable from a command/endpoint.
- [ ] `tools/testing/test-python-full.sh` passes.

---

## 13. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Endpoints in `Component.properties` | Repeating group: write amplification, lost updates, unqueryable, no history (§1.2). |
| Wide table, one column per DID | Thousands of sparse columns; schema change per endpoint; hits SQLite limits. |
| More `Component` subclasses | Combinatorial (§3.1); does not address cardinality at all. |
| Fixed protocol facet classes in core | Replaces seven `Component` subclasses with four `Facet` subclasses; adding a protocol still requires a core release. Facets ship with their consuming plugin (§3.2). |
| Fully data-driven facet types only | A facet field is inert unless Python reads it; runtime-declared types cannot drive behavior. Tier 3 is for inventory data only (§3.3). |
| Dropping/rejecting unknown facet keys | Uninstalling a plugin would silently destroy config on every target using it (§3.4). |
| Packed dotted observation keys (`doip.did.F190`) | Forces `rsplit` and `LIKE` to recover identity — the same unqueryability that disqualified JSON blobs. Identity is columns (§5.3). |
| A generic `CatalogObject` covering VLANs and buses too | Broader than `Endpoint` while the critique was that the types differ; it would admit non-addressable scopes and break the reconciler's one shared property. Scopes are Plane T nodes (§4.5, §4.6). |
| One reconciler with UDS semantics for all protocols | "Present" differs per interaction model; only the set difference generalizes (§7). |
| Copy catalog rows onto each target | Duplicates reference data per unit; breaks versioning; makes §7 uncomputable. |
| Write discovered endpoints into the catalog | Poisons vendor reference data; destroys the `undocumented`/`missing` diff. |
| Property graph / NetworkX as storage | Untyped node properties (nested maps forbidden in Neo4j), supernodes, no bitemporality; breaks the Pydantic contract, the HTTP/WS contract, and the Flutter client. Correct as a derived view (§6). |
| Graph database | Orders of magnitude below where it pays off; re-adds an operational service, against `redis_removal_proposal.md`. |
| Update properties in place after each scan | Destroys the diff, which is the most valuable question in security testing. |

## 14. Deferred decisions

| Item | Revisit when |
|---|---|
| Controlled vocabulary registry for `protocol`/`subject_kind`/`observed_property` | drift survives producer tests and review |
| Generic topology editor in the UI | users need to author or correct connectivity |
| NetworkX as a hard dependency | derived graph queries prove broadly required |
| Graph database | persistent graph-scale query needs exceed SQLite + projection |
| Promoting JSON subfields to columns | cross-target SQL filtering on subfields is a measured bottleneck |
| Alembic / real migrations | the hand-rolled `_migrate_schema` ALTER-by-string becomes a problem |
| Extracting `__settings__` pseudo-target out of `targets` | Phase 5 touches `TargetManager` anyway |
| Splitting `TargetManager` into repository/registry/façade | after phases 0 and 5 have shrunk its surface |
| Graph write-back | do not implement; update relational sources explicitly |
