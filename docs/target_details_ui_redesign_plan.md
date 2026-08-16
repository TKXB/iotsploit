# Target Details UI — Redesign Proposal

**Status:** implemented (phases 0–4). See §9 for what changed on the way.
**Scope:** `ui/lib/screens/targets/` + a small number of read endpoints in `iotsploit-django`
**Companion doc:** [`target_data_model_plan.md`](target_data_model_plan.md) — this proposal is the
Plane T / Plane C *view layer* that plan assumes but never specifies.

---

## 1. The problem, measured

The Details action (`targets_page.dart:745` → `_openDetailsDrawer`) opens a 500 px end-drawer that
renders the target as one flat `SingleChildScrollView`: Basic Information, Properties, Components,
Topology, Observations, each fully expanded into the same column
(`targets_page.dart:799-886`).

That shape was designed for a target with three components and no buses. It is now the smaller half
of the page's own vocabulary — the *editor* was already rebuilt as an inspector with a 250 px outline
rail and a detail pane (`target_edit_dialog.dart:16-23`, `:335-341`), while the read-only view still
uses the old flat drawer. Two mental models for the same object.

Here is what `conf/vw_golf_mqb_target.json` actually contains, counted:

| | |
|---|---|
| components | 19 (all `type: ecu`) |
| buses | 1 (`bus_powertrain_can`) |
| edges | 19, all `bus_member`, all pointing at that one bus |
| CAN frames | 112 across components, plus 1 anchored on the bus |
| CAN signals | 1321 |
| worst single component | `c_gateway_mqb` — 35 frames, 619 signals |
| JSON size | 673 kB as stored (indented); ~254 kB compact on the wire |

Six concrete failures follow from putting that through the current drawer.

**1.1 Structure is flattened into a scroll.** 19 `ExpansionTile`s in a 500 px column, in list order,
with no grouping by bus, no sort by address, no search. Finding the gateway means scrolling past
thirteen ECUs whose names are `c_l`, `c_c`, `c_i`, `c_xxx`.

**1.2 The interesting content is replaced by a count.** `formatFacetValue` collapses any list or map
to `"N entries"` (`facet_schema.dart:95-110`), so opening `c_gateway_mqb` in the drawer prints
`messages: 35 entries`. The 619 signals — the reason the target exists — are unreachable from the
details view. There is no drill-down.

**1.3 Topology is printed as raw ids.** `_buildTopology` emits one text line per edge
(`targets_page.dart:1291-1304`):

```
c_airbag_mqb  —bus_member→  Powertrain CAN
c_bap_tester_mqb  —bus_member→  Powertrain CAN
...17 more identical lines
```

Component ids are never resolved to names (only bus ids are, via `busNames`). Nineteen lines that say
one thing: "everything is on the one bus." A reader cannot see that at a glance, and when a second
bus and a gateway appear, this format cannot show that either.

**1.4 The DoIP case has no representation at all.** A target with many DoIP services is, in this
model, many components each carrying a `doip` facet (`logical_address`, `tester_address`, `host`,
`port` — `doip_facet.py:32-45`). The drawer renders each one inside its own collapsed tile. There is
no address table, no sort by logical address, no "which ECUs answer on which host", no way to see
duplicates or gaps. The single most useful DoIP view — a sorted address map — is exactly what a flat
list of tiles cannot produce.

**1.5 The payload is fetched whole, repeatedly.** `list_targets` returns every target in full
(`target_views.py:10-30`) — including every MQB frame and signal, ~254 kB compact on the wire — and
the page calls it on `initState` **and again on every `didUpdateWidget`** (`targets_page.dart:386-389`). There is no
`get_target/<id>` endpoint and no summary projection. The table only ever shows name, type, status,
component count, IP, location.

**1.6 Observations float free of the structure.** `_buildObservations` groups by
`"component_id · source"` (`targets_page.dart:1153-1162`) as a separate section at the bottom. An
observation about frame `0x3D5` on the gateway is not shown near the gateway, and never near the
frame — even though `ObservationRecord` carries `component_id`, `subject_kind` and `subject_id`
(`observation.py:118-131`) and the reconciliation payoff described in the plan doc (§7) is entirely
about lining observed subjects up against configured ones.

---

## 2. Design principle: three representations, one selection

A target is a graph of a few dozen nodes whose leaves hold thousands of rows. No single widget serves
both ends of that. The proposal is **one tree as the spine, with two interchangeable detail surfaces
hanging off the current selection**:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  VW Golf (MQB powertrain)      vehicle · active · 19 components · 1 bus   [⋯] │
├──────────────┬───────────────────────────────────────────────────────────────┤
│ ▼ Target     │  ┌ Graph │ Table │ Raw ─────────────────────────────────────┐  │
│   Identity   │  │                                                          │  │
│   Properties │  │            ┌──────────────┐                              │  │
│ ▼ Buses      │  │      ┌─────┤ Powertrain   ├─────┐                        │  │
│   ▼ Powertr. │  │      │     │ CAN · 19     │     │                        │  │
│     Airbag   │  │  ┌───┴──┐  └──────┬───────┘  ┌──┴────┐                   │  │
│     BMS      │  │  │Airbag│         │          │Gateway│ ◀ selected        │  │
│   ▶ Gateway  │  │  │6 f   │    ┌────┴───┐      │35 f   │                   │  │
│     ▼ can    │  │  └──────┘    │ BMS    │      └───────┘                   │  │
│       0x3D5  │  │              │3 f     │                                  │  │
│       0x585  │  │              └────────┘                                  │  │
│       …33    │  └──────────────────────────────────────────────────────────┘  │
│   ▶ Motor…   ├───────────────────────────────────────────────────────────────┤
│ ▶ Links (19) │  Gateway  ·  c_gateway_mqb  ·  ecu  ·  active                  │
│ ▶ Observ.(0) │  can  bus_id bus_powertrain_can  node Gateway_MQB  35 frames   │
└──────────────┴───────────────────────────────────────────────────────────────┘
```

- **Tree (left)** — the authoritative outline. Always visible, searchable, lazy. It is the only
  widget that can address every level from target down to an individual signal.
- **Graph (centre, default)** — the topology overview. Answers "what is connected to what" in one
  glance. Deliberately bounded: it renders target, buses and components only.
- **Table (centre, alternate)** — the bulk detail. Virtualized rows for the 1321 signals, the DoIP
  address map, the observation list. Answers "what exactly is in here".
- **Inspector (bottom or right)** — fields of the selected node, rendered from the published facet
  schema, plus the observations whose `component_id`/`subject_id` match that node.

Selection is shared: clicking a graph node selects it in the tree and repaints the inspector, and
vice versa. That single rule is what makes three surfaces feel like one screen rather than three tabs.

### 2.1 The scale rule (non-negotiable)

**Frames and signals never become graph nodes.** The graph is capped at
`1 target + buses + components ≈ 25 nodes` for the Golf, and would stay under ~150 for any plausible
vehicle. A frame count becomes a *badge on a component*, not 112 more nodes. This is the same
supernode objection the data model plan already raises against storing the graph
(`target_data_model_plan.md` §6: *"48k observations on one target node is a textbook supernode"*) —
it applies with equal force to drawing it.

Bulk goes in the table, which virtualizes. The tree lazily materializes frame/signal children only
when a node is expanded, so 1321 signals cost nothing until asked for.

---

## 3. Views in detail

### 3.1 Graph view

Nodes, by kind, each with a distinct shape/colour from the existing `AppColors` tokens:

| kind | id form | label | badges |
|---|---|---|---|
| target | `target:<id>` | target name | type, status |
| bus | `bus:<bus_id>` | bus name | `can` / `ethernet` / `vlan`, member count |
| component | `component:<id>` | component name | one chip per facet key (`can`, `doip`, …), frame count, DoIP logical address |

Edges come straight from `Target.edges` (`target.py:232-244`), styled per `relation`:
`bus_member` plain, `connects` solid arrow, `hosts` dashed, `reachable_from` dotted + provenance
tooltip.

Layout: **Sugiyama (layered)**, target at the top, buses in the middle, components at the leaves.
For the current star topology this produces exactly the picture that the 19 identical text lines were
trying to convey. When a real gateway topology appears (two buses, one component bridging them), the
same layout shows the bridge without any change to the view code.

Interactions: pan/zoom, click to select, hover for the id, double-click to focus the subtree,
"fit to view" button. Optional overlay toggle: colour nodes by observation state (see §3.4).

### 3.2 Table view

The table is context-sensitive to the selected tree node — one widget, several column sets:

- **component selected, `can` facet** — frames: `Frame ID (hex)`, `Name`, `DLC`, `Ext`, `Signals`.
  Expand a row for its signals: `Name`, `Start`, `Len`, `Order`, `Signed`, `Factor`, `Offset`,
  `Min`, `Max`, `Unit`, `Mux`. Hex rendering already exists — `CanMessage.frame_id` declares
  `{"format": "hex"}` (`can_facet.py:78`) and `formatFacetValue` honours it.
- **target or bus selected, DoIP present** — the address map the drawer cannot produce: one row per
  component carrying a `doip` facet, columns `Logical Address (hex)`, `Component`, `Tester Address`,
  `Host`, `Port`, `Status`, sorted by address. Duplicate addresses flagged inline.
- **`Links` selected** — edges as a real table: `Source (name)`, `Relation`, `Target (name)`,
  `Properties`, with ids resolved to names and both columns sortable.
- **`Observations` selected** — `Subject`, `Property`, `Value`, `Source`, `Scope`, `Observed at`,
  filterable by component and protocol.

Reuse `AppTable` (`lib/components/app_table.dart`) — it already handles the responsive
table→card collapse the targets list depends on. It needs a virtualized/paged mode before it is
pointed at 619 signals; see §6 risks.

### 3.3 Raw view

Pretty-printed JSON of the selected subtree, with the existing 400-line cap and "N lines hidden"
notice (`facet_schema.dart:132-154`). Kept because it is the only thing that shows an unrecognised
facet's payload verbatim, which the round-trip guarantee in `RawFacet` (`facet.py:41-47`) exists to
protect. Cheap to keep, and the escape hatch when a plugin isn't loaded.

### 3.4 Observations, attached rather than appended

Instead of one bottom section, observations are joined to the structure by the fields they already
carry:

- `component_id` → the component node. Node badge shows the count; the inspector lists the facts.
- `subject_kind` + `subject_id` → the leaf. A `can`/`message`/`3D5` observation attaches to frame
  `0x3D5` in the tree and the table, because `canonical_frame_id` (`can_facet.py:96-110`) produces
  exactly the string the observation stores.
- Nodes with no matching subject in the configuration are shown as **undocumented** — the set
  difference the plan doc calls "plausibly the most valuable output of the whole scan"
  (`target_data_model_plan.md` §7), rendered rather than merely computable.

This is the payoff that justifies the redesign beyond aesthetics: it is not reachable from a flat
drawer at all, and it falls out naturally once configured and observed subjects share a tree.

---

## 4. Third-party libraries

### 4.1 Tree — `flutter_fancy_tree_view` (recommended; **already a dependency**)

Declared in `ui/pubspec.yaml` as `^1.1.1` and resolved to **1.6.0** in `pubspec.lock`, yet
`grep -rn "TreeView" lib/` returns nothing — it is paid for and unused. Its only dependency is the
Flutter SDK itself, so there is no new transitive surface and no platform channels; every platform
the repo already builds (linux, windows, macos, android, ios, web) is covered.

It provides what a hand-rolled `ExpansionTile` nest does not: lazy child materialization,
`SliverTreeView` virtualization, indent guides, and controller-driven expand/collapse/reveal — the
last being what makes "click a graph node, tree scrolls to and expands it" a two-line call rather
than a state-management project.

**Zero-new-dependency fallback:** a `ListView.builder` over a flattened node list. Perfectly viable,
maybe 200 lines, and you own the expansion state. Recommended only if the dependency is rejected;
otherwise using the package that is already in the lockfile is strictly cheaper.

### 4.2 Graph — `graphview` (proposed; **not adopted** — see §9.2)

`graphview` 1.5.1. Dependencies: `flutter` + `collection ^1.15.0` (already transitively present).
No native platform code; pub.dev lists Android, iOS, Linux, macOS, web and Windows. Ships eight
layout algorithms; the two that matter here are **Sugiyama (layered)** for bus/component topology and
**Buchheim-Walker (tree)** if a strict hierarchy is ever wanted.

Why this one:

- It computes *layout only* and lets you supply arbitrary Flutter widgets as nodes. Node chrome is
  therefore ordinary `M3Card`/chip composition from the existing design system, not a bespoke theme
  fighting the app's tokens.
- Sugiyama is the right algorithm for this data. Vehicle topology is layered by nature
  (target → bus → ECU); force-directed layouts would jitter between refreshes and produce a different
  picture each time you open the page.
- It is deterministic, which matters for screenshots and for the docs pipeline in `ui/docs/blog/`.

**Alternatives considered:**

| option | verdict |
|---|---|
| `flutter_graph_view` | Force-directed and animation-oriented; non-deterministic layout, heavier, styling is its own system. Rejected. |
| Custom `CustomPainter` | Full control, no dependency, but you implement Sugiyama yourself — layer assignment, crossing reduction, coordinate assignment. Weeks, not days, and you own the bugs. Rejected unless dependency policy forbids `graphview`. |
| Mermaid / Graphviz via webview | `flutter_inappwebview` is already a dependency, so technically available. Rejected: no click-to-select into Flutter state, no theme integration, and a browser engine per panel on desktop. |
| `fl_chart` (already present) | Not a graph library. Not applicable. |

### 4.3 Large tables — decide at implementation time

`AppTable` today builds all rows. For 619 signals that is survivable but not free; for a
future 5000-signal DBC it is not. Two paths: add a `builder`-based virtualized mode to `AppTable`
(preferred — one component, and every other table benefits), or use the Flutter team's
`two_dimensional_scrollables` `TableView` for this screen only. Recommend the former; measure first.

---

## 5. Backend changes

Three of these are worth doing on their own merits, independent of any UI work.

**5.1 `get_target/<target_id>` — new.** One target, in full. Today the UI can only obtain a target by
downloading all of them. Small handler beside `get_current_target` in `target_views.py`.

**5.2 `list_targets` returns a summary projection — change.** Drop `facets.*.messages` and
`facets.*.signals` from the listing and add counts (`component_count`, `bus_count`, `frame_count`,
`facet_keys`). The Golf listing goes from ~254 kB to ~6 kB — a factor of about 40 — and the targets
table gains the columns it wants. Callers that need the whole thing call 5.1. **This is a breaking response-shape change**
for any other consumer of `list_targets`; audit CLI and MCP callers first.

**5.3 `get_target_graph/<target_id>` — new, optional but recommended.** Returns the projected graph
the plan doc already specifies (`build_current_graph`, §6):

```json
{
  "nodes": [
    {"id": "bus:bus_powertrain_can", "kind": "bus", "label": "Powertrain CAN",
     "badges": {"type": "can", "members": 19}},
    {"id": "component:c_gateway_mqb", "kind": "component", "label": "Gateway",
     "badges": {"facets": ["can"], "frames": 35, "observations": 0}}
  ],
  "edges": [
    {"source": "component:c_gateway_mqb", "target": "bus:bus_powertrain_can",
     "relation": "bus_member", "provenance": null}
  ]
}
```

Keeps node-id construction and observation folding in one place instead of duplicating the rules in
Dart, and is where `reachable_from` edges derived from scans will appear. The UI can ship phase 3
without it by projecting client-side from `components`/`buses`/`edges`; the endpoint becomes
necessary once observations join the graph.

**5.4 `get_component_facet/<target_id>/<component_id>/<key>` — new, paged.** So the gateway's 619
signals arrive when the tree node is expanded, not on page load. Straightforward given 5.2.

**5.5 Filter params on `get_current_observations`.** Add `component_id`, `protocol`, `subject_kind`,
`subject_id`. The fields are already columns (`observation.py` §5.3 identity-as-columns), so this is
a queryset filter, and it is what lets the inspector ask for one subject instead of pulling
everything and filtering in Dart.

---

## 6. Phasing

Each phase is independently shippable and leaves the app better than it found it.

**Phase 0 — payload (backend only).** 5.1 + 5.2. No UI change beyond pointing the drawer at
`get_target`. Fixes the quarter-megabyte-per-refresh problem immediately. Also delete the
`didUpdateWidget` refetch (`targets_page.dart:386-389`), which re-downloads everything on any parent
rebuild.

**Phase 1 — the shell and the tree.** New route `/targets/:id` (`route_names.dart` + `app_router.dart`
child route), three-pane scaffold, tree view, inspector, Raw view. The Details action navigates here
instead of opening the drawer. **No new dependency** (`flutter_fancy_tree_view` is already locked).
This alone resolves failures 1.1, 1.3 and 1.4 — the tree groups components under their bus and
resolves ids to names — and is the phase to stop at if the graph is judged unnecessary.

**Phase 2 — the table.** Frames/signals table, DoIP address map, links table, observations table.
Resolves 1.2. Needs the `AppTable` virtualization decision from §4.3.

**Phase 3 — the graph.** Add `graphview`, Sugiyama layout, shared selection with the tree. Resolves
1.3 properly. Optionally add 5.3 here.

**Phase 4 — observations on the structure.** 5.5 + the join described in §3.4, plus the
documented/observed set difference. Resolves 1.6, and is the phase that makes this screen worth more
than a prettier drawer.

**Mobile:** below `ResponsiveConfig.tabletBreakpoint` the three panes cannot coexist. Recommend
tree-then-inspector as a drill-down stack (tap a node, push the inspector), with Graph hidden and
Table falling back to `AppTable`'s existing card-list mode. The current end-drawer stays as the mobile
path until phase 1 lands there.

---

## 7. Risks and open questions

1. **Two new dependencies.** `graphview` last published ~10 months ago. It is stable and small
   (layout math, no platform code), but it is not the Flutter team's. Mitigation: keep the graph
   behind a thin `TargetGraphView` widget so swapping it for a `CustomPainter` later touches one file.
2. **`AppTable` at 619 rows** is unmeasured. Measure before choosing between virtualizing it and
   adopting `two_dimensional_scrollables`.
3. **`list_targets` shape change** (5.2) breaks any consumer expecting full targets. Audit
   `iotsploit-cli` and `iotsploit-mcp` (`list_targets` is an exposed MCP tool) before shipping.
4. **Layout stability.** Sugiyama is deterministic given a stable node *order*; component list order
   must be preserved (it is — `components` is an ordered JSON list) or the picture will reshuffle
   between refreshes.
5. **Topology is currently a star.** All 19 edges point at one bus, so the graph's value is partly
   anticipatory. It pays off the moment a second bus or a gateway appears — which is the realistic
   next target, not a hypothetical.
6. **Editor convergence.** Once the read-only explorer exists, `TargetEditDialog`'s rail is a subset
   of the explorer's tree. Worth considering — later, not now — whether editing becomes a mode of the
   explorer rather than a separate 1977-line dialog. Explicitly out of scope for this proposal.

---

## 8. What this does not propose

- No change to the domain model. `Target`, `Component`, `Facet`, `Bus`, `Edge` and `ObservationRecord`
  are all sufficient as they stand; every id and count above was read straight off them.
- No stored graph. Projection only, per `target_data_model_plan.md` §6.
- No protocol knowledge in the UI. DoIP and CAN appear in this document as *examples of what the
  published facet schemas will describe*; the views read `get_facet_schemas` exactly as the drawer
  does today (`facet_schema.dart:1-7`). Adding SOME/IP must stay a backend change.


---

## 9. What changed during implementation

The proposal survived contact largely intact. Three things did not, and the
reasons are worth keeping.

### 9.1 The payload figures were overstated

673 kB is the fixture *file*, which is indented. Compact on the wire the same
target is ~254 kB, and the summary row is ~6 kB — a factor of about 40, not the
"two orders of magnitude" the first draft implied. The numbers above have been
corrected in place; `test_target_listing_endpoint.py` asserts the real ratio
against the real fixture so it cannot drift back into optimism.

### 9.2 `graphview` was not added

The proposal recommended it for Sugiyama layering. Building the prototype
showed Sugiyama is the part that does not fit: one rank per layer puts all
nineteen MQB components in a single row roughly two thousand pixels wide.
Clustering them by *which set of buses they are on* is what makes them
readable — and once that pass is hand-written, the library is left holding a
`Stack` of positioned children and a `CustomPaint` for edges, both of which
Flutter already ships. `InteractiveViewer` covers pan and zoom.

So the graph has no third-party dependency. `explorer_graph_layout.dart` is
pure geometry with no widget imports, which buys something a library would not
have: *"no two of the twenty-one nodes on the real MQB target overlap"* is an
assertion in `explorer_graph_layout_test.dart` rather than a screenshot someone
has to squint at.

`flutter_fancy_tree_view` **was** used, as proposed, and cost nothing — it was
already in `pubspec.lock` at 1.6.0 and unreferenced.

### 9.3 A component on two buses appears twice in the outline

Thirteen MQB ECUs sit on both the CAN segment and the diagnostic Ethernet.
Grouping the outline by bus therefore lists each of them under both. This is
deliberate — the alternative is picking one bus and quietly hiding the other
membership — but it is a real design decision that the proposal did not
anticipate, and worth revisiting if it reads as duplication in use.

Related: components that no edge attaches to any bus get their own **Not on any
bus** group, because a component missing from the topology is a gap in the
target, not a gap in the view.

### 9.4 `AppTable` virtualizes more than §4.3 assumed

It already lays rows out through a `ListView.builder` with a fixed
`itemExtent`, so off-screen rows cost no layout. What it does *not* do is defer
building the cell widgets: every row's cells are constructed to build the list,
which at 1321 signals × 11 columns is ~15k widget objects per rebuild.

That is affordable once and wasteful per keystroke, so the explorer caps the
table at 600 rows and says what it hid. Making `AppTable` take a row *builder*
remains the better fix and is now the only outstanding item from this document.

### 9.5 Endpoints, as built

| endpoint | status |
|---|---|
| `GET /api/list_targets/` | summary projection, `summary: true`, `facet_sizes` |
| `GET /api/get_target/<id>/` | new — one target in full |
| `GET /api/get_current_observations/` | gained `component_id`, `source`, `protocol`, `subject_kind` |
| `get_target_graph` (§5.3) | **not built** — the client projects from `components`/`buses`/`edges`, which is enough until observations need folding in server-side |
| `get_component_facet` (§5.4) | **not built** — `get_target` is fast enough at 254 kB for one target |

The projection rule lives in `iotsploit-core/src/iotsploit_core/domain/summary.py`
and is protocol-agnostic: core does not know what a `messages` list is, so it
does not name one. A facet field holding a list or a mapping is bulk.
