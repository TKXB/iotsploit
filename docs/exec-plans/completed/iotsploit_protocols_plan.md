# `iotsploit-protocols` — a SOME/IP helper, and a home for DoIP

Proposal only. No implementation code has been written.

Two asks, one design: plugins need a SOME/IP helper they can call, and `doip_mgr.py` needs
to stop containing a specific vehicle's IP addresses and a specific USB NIC. Both are the
same problem — wire protocol code that has grown a lab bench inside it — so both get the
same answer: a small protocol package with no environment in it, and a thin binding layer
in Django that resolves configuration from the current target.

This revision has been cut back once already. §2 lists what was removed and why; read it
before adding anything back.

---

## 1. Shape

```
iotsploit-core          domain: Facet, Fact                        (no I/O)
      ▲
iotsploit-protocols     scapy codecs, SOME/IP + DoIP clients,      (no Django,
      ▲                 the facets that configure them              no Env_Mgr, no sudo)
      │
iotsploit-django        protocol_binding: current target → config;
      ▲                 doip_link: NIC setup. No OEM content at all.
      │
iotsploit-exploits      plugins call either layer;
                        oem/zeekr/: platform procedures (§6)
```

`iotsploit-protocols` depends on `iotsploit-core`, `scapy` and `pydantic`, and never
imports Django — which is what makes it testable without a database and usable by anyone
writing a plugin.

Facets follow the rule already written down in `docs/target_data_model_plan.md:120` — *a
facet ships with the code that consumes it*. Once the DoIP client lives here, so does
`DoipFacet`; `SomeipFacet` is born here.

### Files, in full

```
iotsploit-protocols/
  pyproject.toml
  README.md                              # the usage doc; there is no separate guide
  src/iotsploit_protocols/
    __init__.py
    errors.py                            # ProtocolError, NotConfigured, NegativeResponse
    someip/
      __init__.py
      facet.py                           # SomeipFacet, canonical_service_id
      client.py                          # SomeIpConfig, SomeIpClient, SomeIpResponse
      sd.py                              # ServiceDiscovery.listen() → [ServiceOffer]
    doip/
      __init__.py
      facet.py                           # DoipFacet, moved out of iotsploit-django
      client.py                          # DoipConfig, DoipClient
      uds.py                             # UdsClient, UdsResponse
  tests/
    test_someip_client.py  test_someip_sd.py  test_someip_facet.py
    test_doip_client.py    test_doip_uds.py
```

Six source modules for SOME/IP and DoIP together. Root `pyproject.toml` gets the package
as a path/develop dependency and its `tests/` in `testpaths`, so
`tools/testing/test-python-full.sh` covers it unchanged.

---

## 2. What was cut, and why

Every item below was in an earlier draft of this plan. None of it is coming back without a
caller that needs it.

| cut | why |
|---|---|
| `transport.py` — a `Transport` protocol with `TcpTransport`/`UdpTransport` | one consumer. SOME/IP over TCP vs UDP is a `SOCK_STREAM`/`SOCK_DGRAM` argument, not an abstraction |
| `services.py` — `UdsService` and `Nrc` enums | scapy already ships them: 55 service names and 61 NRC names, `0x78` included. Verified, not assumed |
| `seedkey.py` — a named algorithm registry, `register_seed_key`, `NotRegistered`, and a `DoipFacet.seed_key_algorithm` field | replaced by passing the function: `security_access(level, pin, key_fn)`. One algorithm exists. A global name registry to reach one function is indirection, and dependency injection is both smaller and easier to test |
| `someip/observe.py` — facts builder module | ~20 lines used by one plugin. `canonical_service_id` lives in `facet.py` next to the facet, exactly where `canonical_frame_id` sits in `can_facet.py:95`; the plugin builds its own `Fact`s |
| `SomeipFacet.services` / `SomeipMethod` catalogue | nothing reads it yet. `target_data_model_plan.md` §3.3 is explicit: "Code that does not exist yet cannot read a field invented at runtime." Add it with the plugin that consumes it |
| `ServiceDiscovery.find()` — active wildcard FindService | ECUs announce OfferService on the multicast group anyway. Ship `listen()`; add `find()` if listening proves insufficient |
| `listen_events()` / event-group subscription | SubscribeEventgroup is a sub-protocol of its own. Nobody asked for events |
| real `DoIPInterfaceAdapter` + `SomeIpInterfaceAdapter` for the fuzzer | the seam is real (`iot_protocol_components.py:100-105` is a `return True` stub) and backing it is an obvious follow-up — but it is a different subsystem and was scope creep |
| `doip/config.py` as its own module | a six-field frozen dataclass belongs in `client.py` |
| `UdsResponse.raise_for_status()` | `.ok` and `.nrc` are enough. Two ways to check one thing is one too many |
| `docs/someip_helper_usage.md` | a three-method API is documented by its README and docstrings |
| `someip_probe` plugin | it enumerated methods out of the facet catalogue that is also cut |
| `oem/zeekr/ecus.py` — moving `ECU_REGISTRY` | it works where it is. Only the import of `DoIP_Mgr` for two integers needs removing, by inlining `0x1011` / `0x1201` |

Net effect on the deliverable: phase 2 drops from eleven new source files to six.

Two things deliberately kept despite looking like extras: **session correlation** in the
SOME/IP client (mandatory over UDP, where responses interleave) and **NRC 0x78 retry** in
the UDS client (a busy ECU currently reads as a failure — `doip_mgr.py:116-119` has it
commented out).

---

## 3. Why scapy, and how far

Use scapy as a **codec, not as a socket**. `scapy.contrib.automotive.someip` gives the
`SOMEIP` header, `SD`, `SDEntry_Service` and the IPv4 endpoint options; parsing an SD offer
by hand is a week of bugs. But scapy's sending paths (`sr1`, L2 sockets) generally want
root and a live interface, which would make a SOME/IP method call a privileged operation
for no reason. So the clients build and parse with scapy and do I/O on plain sockets. SD
multicast still works unprivileged — joining a group needs no root.

DoIP is the exception: `scapy.contrib.automotive.doip.DoIPSocket` is an ordinary TCP stream
socket that already does length-prefixed framing and routing activation. We use it as-is,
because it fixes a real bug (§5.1).

Verified in this workspace: scapy 2.6.1, both contrib modules import. Pin
`scapy = ">=2.6,<3"`. `iotsploit-exploits` already depends on scapy, so plugin users gain
no new heavy dependency.

Every scapy import sits inside the module or function that needs it — importing scapy costs
hundreds of milliseconds and reads host network config, and `import iotsploit_protocols`
must stay cheap for CLI startup.

---

## 4. The SOME/IP helper

### 4.1 What a plugin writes

```python
from iotsploit_django.adapters.django.protocol_binding import someip_client_for

with someip_client_for("TCAM") as c:            # host/port from the facet
    r = c.call(service=0x1234, instance=0x0001, method=0x0002, payload=b"\x01")
    if r.ok:
        logger.info("payload %s", r.payload.hex())
```

Unbound — a parameter-driven plugin, or a bench with no target configured:

```python
from iotsploit_protocols.someip import SomeIpClient, SomeIpConfig

with SomeIpClient(SomeIpConfig(host=params["host"], port=int(params["port"]))) as c:
    ...
```

Discovery:

```python
from iotsploit_protocols.someip import ServiceDiscovery, SdConfig

# interface and group come from plugin parameters, not from a facet -- see 4.4
sd = ServiceDiscovery(SdConfig(interface=params["iface"], group=params["sd_group"]))
offers = sd.listen(timeout=10.0)     # [ServiceOffer(service_id, instance_id, major,
                                     #               minor, ttl, endpoints)]
```

An endpoint is a plain `(ip, port, "tcp"|"udp")`, so callers never import scapy to read a
result.

### 4.2 The client

- **`call()`** (REQUEST → RESPONSE/ERROR) and **`notify()`** (fire-and-forget). That is the
  whole message-type surface.
- **`SomeIpResponse(message_type, return_code, payload)`** with `.ok` — no plugin indexes
  into a byte offset to learn whether something worked.
- **Session correlation**: `session_id` increments per request, responses match on
  `(client_id, session_id)`.
- **Timeouts from config**, never unbounded.

No default host anywhere. `SomeIpConfig` requires `host`; only the standard SD port (30490)
is defaulted, because that is an IANA registration rather than a description of one
vehicle. An unconfigured target therefore fails loudly instead of quietly probing whatever
`169.254.x.x` used to be right.

### 4.3 The facet

```python
@register_facet("someip")
class SomeipFacet(Facet):
    port: Optional[int] = None
    transport: str = "tcp"                                       # "tcp" | "udp"
    client_id: Optional[int] = Field(default=None, json_schema_extra=HEX)
```

Three fields, all read by code that exists, and all genuinely per-component. It still gets
the Flutter facet editor and MCP target editing for free through `FacetRegistry.schemas()`,
which is what `target_details_ui_redesign_plan.md:362` asks for.

Two fields an earlier draft had here are gone for target-model reasons rather than
YAGNI — see §4.4: `host` (the component already carries an address; a second place to
write one creates the "which wins" problem facets exist to kill) and `sd_group` (a property
of an Ethernet segment, not of each component on it).

`canonical_service_id(service_id, instance_id) -> "1234:0001"` lives here, fixed in one
place for the reason `can_facet.py:95` gives: reconciliation joins on the string, and a
mismatch matches nothing silently.

Registration is one more name in the `apps.py:18` import line.

### 4.4 Fit with the target model

Checked against `docs/target_data_model_plan.md` and the shipped
`iotsploit_core/domain/{target,observation}.py`.

**What lines up already.** The observation shape is not merely compatible with the spec —
it *is* the spec's worked example. `target_data_model_plan.md:472` reads:

```text
someip    service       1234:0001      offered            {"methods": [1, 2, 5]}
```

`canonical_service_id` produces exactly that `subject_id`, `service` is in the documented
`subject_kind` vocabulary (`:461`), and `offered` is the documented property for SOME/IP
(`:374`). The discovery plugin implements `ObservationProducer` and returns
`ObservationBatch`es; nothing new is needed in core.

**Mismatch 1 — `host` on the facet would be a fourth lookup path.** `target.py:63-72`
already resolves a component address three ways, and §3.1 of the model plan quotes exactly
that code as "three lookup paths for one attribute… the workaround already in the code" —
the wart facets exist to remove. Adding `SomeipFacet.host` makes it four. The model's own
sketch annotates `DoipFacet.host` with *"falls back to the `net` facet"*, so the intended
end state is one address on a `net` facet that protocol facets override — and no `net`
facet exists yet.

So the address is not a facet field. `protocol_binding` owns the order, written once:

1. an explicit argument from the caller,
2. the component's `ip_address` (typed field or `properties`),
3. otherwise `NotConfigured` — never a default.

When the `net` facet lands, `protocol_binding` is the only file that changes. (`DoipFacet`
keeps its existing `host` for compatibility, but the binding resolves it through the same
function, and it should follow the same path later.)

**Mismatch 2 — `sd_group` belongs to a segment, not a component.** Every component on an
Ethernet segment repeats the same SD multicast group. That is precisely the distinction
`doip_facet.py:31-36` draws between a `unique` field that identifies one ECU and a shared
reference like `bus_id`. `Bus` already exists with `type: "ethernet" | "vlan"`, so that is
where the group belongs — except `Bus` carries only `properties`, not facets, and giving it
facets is a core change well outside this plan. For v1 the SD group is a plugin parameter,
supplied by the caller. When Ethernet segments are modeled properly it moves to the bus,
and no facet has to be migrated because none ever held it.

**Mismatch 3 — which component owns a discovered offer.** SD is bus-wide: one listen hears
offers from many ECUs. The tempting shape is one batch per component, but
`ObservationBatch.is_complete` means "these facts are the whole snapshot for this scope"
and a complete batch clears prior state. A silent ECU is indistinguishable from an absent
one over SD, so per-component complete batches would assert "this ECU offers nothing" about
an ECU that simply did not speak, and wipe its history.

So an SD sweep records at **target scope**: `component_id=None`, `is_complete=True`,
`scope_key="someip:sd:<group>"`. That is a true statement — this is everything the segment
announced — and `ObservationScope.component_id` is `Optional` precisely for this. Attaching
offers to specific components can come later from endpoint-IP matching, as a separate
non-complete batch.

**A service does not become a `Component`.** §4.6 lists a SOME/IP service as anchoring to a
component and being a *node*, the same as a DID — and DIDs are plainly not components.
Discovered services are observation subjects anchored to a component, never rows in
`Target.components`.

**And a note on the cut catalogue.** Dropping `SomeipFacet.services`/`methods` (§2) turns
out to be doubly right. It was not only unread — it was the wrong plane. `can_facet.py:5-17`
states the rule for its own protocol: a facet holds "the curated slice… not a place to park
a two-thousand-signal production DBC", because a vendor description belongs in the Plane B
reference catalog. An ARXML/FIBEX SOME/IP service catalogue is the same object, and Plane B
does not exist yet.

---

## 5. The DoIP refactor

### 5.1 What is wrong now

| `doip_mgr.py` | problem |
|---|---|
| `connect(ip="169.254.19.1", port=13400)` (:454) | one vehicle's gateway address as a function default |
| `sudo ifconfig {} 169.254.58.58 netmask 255.255.0.0` (:463, :477) | tester IP and subnet hardcoded, and a protocol client shelling out to sudo |
| `DeviceInfo.doip_eth_name = "enx68da73a73741"` (`device_info.py:7`) | one specific USB NIC, by its MAC, as a class constant |
| `recv(13)` → `sleep(0.5)` → `recv(2048)` (:52-57) | assumes one `recv` is one message and the ack is exactly 13 bytes. TCP guarantees neither; a split or coalesced segment desynchronizes the stream silently |
| `resp_buf[12]`, `resp_buf[-3]`, `resp_buf[-5]` (:166, :182, :242, …) | response parsing by magic offset, different at each call site |
| NRC 0x78 handling commented out (:116-119) | responsePending is a protocol requirement; a busy ECU reads as failure |
| `_instance = DoIP_Mgr()` (:509) | one socket per process: two ECUs cannot be addressed concurrently |
| `Input_Mgr.Instance().confirm(...)` (:476) | a wire-protocol client blocking on interactive UI |
| `struct.pack(">H", 0x0e80)` (:106) | tester address hardcoded although `DoipFacet.tester_address` exists |
| `resetvgm` (:85-98) | hardcodes 0x1011 despite `addr_of()`, and loops `while True` forever on a dead ECU |
| `vehicle_utils.py:39,51` | imports a socket client to read two integers |

### 5.2 Target design

```
iotsploit_protocols/doip/client.py     DoipConfig + DoipClient   connection, framing
iotsploit_protocols/doip/uds.py        UdsClient + UdsResponse   UDS semantics
iotsploit_protocols/doip/facet.py      DoipFacet

iotsploit_django/adapters/django/protocol_binding.py   target + secrets → config
iotsploit_django/tools/doip_link.py                    NIC bring-up (the only sudo)
iotsploit_exploits/oem/zeekr/                          platform procedures (§6)
```

**Config is a frozen value object built by the caller.**

```python
@dataclass(frozen=True)
class DoipConfig:
    host: str                       # required — no default. An unconfigured target
    logical_address: int            # must fail loudly, not probe 169.254.19.1
    port: int = 13400               # IANA, not one vehicle
    tester_address: int = 0x0E80
    timeout: float = 5.0
```

**One client is one connection to one ECU.** No `Instance()`, no module-level socket; a
context manager that connects on enter and always closes on exit. Two ECUs means two
clients, which the current singleton makes impossible.

**UDS is a separate layer** that talks to a `DoipClient` but knows nothing about DoIP
framing, so it can later sit on ISO-TP:

```python
class UdsClient:
    def session(self, kind: int) -> UdsResponse: ...
    def read_did(self, did: int) -> UdsResponse: ...
    def routine(self, control: int, rid: int) -> UdsResponse: ...
    def tester_present(self) -> UdsResponse: ...
    def security_access(self, level: int, pin: bytes,
                        key_fn: Callable[[bytes, bytes], bytes]) -> bool: ...
```

Those five are exactly what the surviving call sites need — no more. `UdsResponse` carries
`service`, `data`, `nrc` and `.ok`, so `resp_buf[-3] != 0x6e` becomes `resp.ok` and the
magic offsets disappear: one layer parses the header, once. Service and NRC names come from
scapy.

`security_access` takes the key derivation **as an argument**. That is what keeps the
algorithm out of this package (§6) without a registry.

Other rules the rewrite follows: no `time.sleep` pacing anywhere — waiting is a timeout,
because a sleep is a guess about someone else's latency; bounded retries only for NRC 0x78;
`resetvgm`'s `while True` becomes a bounded wait that raises; typed errors
(`NegativeResponse(nrc)`, `NotConfigured`) instead of `raise_err(str)`; no prompts and no
sudo in the client — `Input_Mgr.confirm("请连接odb线")` moves to the caller, because a
library that blocks on stdin cannot run under Celery, MCP, or a test.

### 5.3 Both files are deleted, not wrapped

An earlier draft kept `DoIP_Mgr` as a compatibility façade. The whole caller surface is two
behavioural call sites and four import lines:

| call site | uses |
|---|---|
| `vehicle_utils.py:39,51` | `DoIP_Mgr.TCAM_Addr`, `DHU_Addr` — two integers |
| `vehicle_utils.py:102` | `DoIP_Mgr.Instance().check_mcu_alive(addr)` |
| `vehicle_utils.py:74` | `doip_facet.logical_address_for` |
| `adb_check.py:6,317` | `DoIP_Mgr.Instance().closedebug("dhu")` |
| `apps.py:18` | imports `doip_facet` for its registration side effect |
| 2 django test files | import `DoipFacet` |

A façade is not buying compatibility for a large surface — it is buying it for two calls.
And it preserves the wrong half: it keeps the *signature*, which was never the risk, while
also keeping `Instance()`, so the "two ECUs concurrently" fix is built but never delivered.
The new stack would run under an old name, hiding the rewrite instead of flagging it.

**What moves rather than vanishing:** socket/framing and UDS are rewritten in
`iotsploit_protocols/doip/`; `__compute_seed_key`, `opendebug`/`closedebug`/`read_vin`/
`resetvgm` and the Env_Mgr PIN reads move to `iotsploit_exploits/oem/zeekr/` (§6.3); the
`ifconfig`/route calls move to `doip_link.py`; `DHU_Addr`/`TCAM_Addr` become literals in
`ECU_REGISTRY`, which deletes the `vehicle_utils → doip_mgr` import.

**`check_mcu_alive` is not OEM code and does not move to `oem/`.** An earlier draft sent it
there by association. Reading it (`:383-393`), it sends `10 01` — DiagnosticSessionControl,
default session — and returns True if any bytes came back. That is plain UDS with nothing
platform-specific in it: it *is* `UdsClient.session(0x01)` plus a truthiness check, so it
disappears into the protocol package rather than moving anywhere.

Consequently `check_ecu_alive` (`vehicle_utils.py:96-104`) stays where it is; its DoIP
branch becomes `doip_client_for(ecu)` + `uds.session(0x01).ok`. `flood_attack.py` is not
touched at all. Only `adb_check.py` needs the guarded OEM import.

From `doip_facet.py` the split is forced by the dependency rule: `DoipFacet` is pure and
moves to the package, but `doip_facet_for()` and `logical_address_for()` read the current
target through `TargetManager` and cannot follow it into a Django-free package — they go to
`protocol_binding.py`. The existing `test_doip_facet.py` splits the same way.

**Do this before deleting anything.** The seed/key routine has no specification and no
second implementation; once `doip_mgr.py` is gone there is no oracle. The first commit of
phase 3 freezes characterization vectors captured from the running code. They already
exist — ten vectors, including the all-zero and all-`ff` extremes — and are waiting in the
scratchpad as a ready-to-commit test.

**Cost of no façade:** phase 3 stops being splittable. Package and callers land together
and the bench must be available then. That is a scheduling constraint, not a design flaw.

---

## 6. OEM-specific code

### 6.1 What it is

The string "zeekr" barely appears in the codebase — only README provenance and test
fixtures. The OEM content is unlabelled, which is why it spreads:

| where | what |
|---|---|
| `doip_mgr.py:123-150` | `__compute_seed_key` — a proprietary security-access algorithm |
| `doip_mgr.py:165,181,187,208,225,231` | debug on/off sequences: `2E C0 3E 01`, routines `31 01 02 32` / `31 01 DC 01` |
| `doip_mgr.py:23-24,156,173,…` | ECU addresses, `__SAT_ENV__VehicleInfo_{DHU,TCAM}_PIN` |
| `doip_mgr.py:310-317` | VIN via DID `F190`, cross-checked between two named ECUs |
| `device_info.py:7-16` | one bench's NIC MACs and admin SSID/password |

None of it is DoIP. DoIP is `02 FD`, message types, routing activation, length prefixes.

### 6.2 The exposure that already exists

**The repository is public.** `origin` is `https://github.com/TKXB/iotsploit.git`, and the
GitHub API answers anonymously with `"private": false`. `doip_mgr.py` is present on
`origin/main` (commits `20d8240`, `0394086`). So `__compute_seed_key`, the debug routine
ids and the bench NIC MAC are already published source, readable by anyone, today.

This bounds what the rest of this section can achieve. Everything below — the `.gitignore`
entry, the packaging `exclude`, deleting `doip_mgr.py` — stops *new* exposure. None of it
retracts the old one:

- Deleting `doip_mgr.py` in phase 3 removes it from `HEAD`, not from history. Every past
  commit still contains it, and `git log -p` still prints it.
- Actually removing it means rewriting history (`git filter-repo`), force-pushing, and
  accepting that forks, clones, and GitHub's own caches of unreferenced objects persist
  regardless.
- The published PyPI wheels are a separate copy again (§6.2 continued below).

Whether to attempt retraction is the repository owner's call, not a code decision, and it
should be made with whoever owns the relationship with the OEM. The engineering work in
this plan is worth doing either way — it stops the next commit from adding to the pile —
but it should not be mistaken for a fix to what is already out.

`iotsploit-django` is published to PyPI (`PYPI_PUBLISH_GUIDE.md:14`) and its packaging
includes `tools/` wholesale. The built wheel in `iotsploit-django/dist/` confirms it:

```
iotsploit_django/tools/doip_mgr.py       20037 bytes   ← includes __compute_seed_key
iotsploit_django/tools/device_info.py      563 bytes   ← includes enx68da73a73741
```

This plan did not create that, but phase 3 rewrites those files, so it is the moment it
gets fixed or cemented.

### 6.3 It goes in `iotsploit-exploits`, not `iotsploit-django`

No new distribution: keeping code out of a published wheel needs one named directory and an
`exclude`, not a package. The question is which existing package holds it.

**`iotsploit-exploits`**, for three reasons:

1. **Every consumer is a plugin.** The one caller of what actually remains OEM —
   `closedebug` — is `adb_check.py:317`. Nothing inside `iotsploit-django` uses any of it;
   Django is holding OEM attack procedures on behalf of plugins.
2. **It matches what the packages claim to be.** `iotsploit-django` is the "Django ring
   package (HTTP/WS/ORM/Celery + composition root)". Unlocking an ECU with a seed/key and
   flipping debug mode is not that. `iotsploit-exploits` is the "Official IoTSploit exploit
   plugin package", which is exactly what this is.
3. **The dependency direction permits it.** `iotsploit-exploits` already depends on
   `iotsploit-django`, so `vehicle_debug` still reaches `Env_Mgr` and `protocol_binding`.
   The reverse — Django importing exploits — would be circular, and is the one thing that
   could have blocked this.

```
iotsploit-exploits/src/iotsploit_exploits/oem/zeekr/
    __init__.py
    seedkey.py         zeekr_gen1(seed, pin) -> key
    vehicle_debug.py   open/close debug, read_vin, VIN match, resetvgm
```

```toml
# iotsploit-exploits/pyproject.toml
[tool.poetry]
exclude = ["src/iotsploit_exploits/oem/**"]
```

This costs the bench nothing: the running system is the repo checkout, not a PyPI install —
root `pyproject.toml` is `package-mode = false` with every sub-package a `develop = true`
path dependency. The wheel is for external users.

Tested on a throwaway poetry project with this repo's build backend before being written
down: `exclude` removed the directory from **both** wheel and sdist while leaving sibling
modules untouched. Verify in place, and keep it as a check in `tools/testing/` so a
packaging change cannot silently re-include it:

```bash
poetry build -C iotsploit-exploits && unzip -l iotsploit-exploits/dist/*.whl | grep oem/
# must print nothing
```

**Write that check in the same commit as the `exclude`.** `iotsploit-exploits` is the
package queued to be published *first* (`PYPI_PUBLISH_GUIDE.md:17,25` — ⏳ 待发布), so this
is precisely the distribution where an overlooked `exclude` does damage on its debut push.

**Consumers must import it defensively.** This applies wherever `oem/` lives, but it
becomes load-bearing here: entry-point discovery imports every plugin module, `adb_check`
imports at module scope (`:6`), and `oem/` is absent from the wheel — so a PyPI user's
plugin scan would raise `ImportError` and take the whole scan with it.

```python
try:
    from iotsploit_exploits.oem.zeekr.vehicle_debug import close_debug
except ImportError:            # OEM profile not shipped in this distribution
    close_debug = None
```

with the plugin degrading rather than failing.

There is no registry and no entry point for the algorithm. `vehicle_debug.py` imports it
directly and passes it to `security_access(level, pin, key_fn)`. Nothing else needs to know
it exists, so an install without the directory simply has no `vehicle_debug`.

The result is that `iotsploit-django` ends up holding **no OEM content at all** — only
`protocol_binding.py` and `doip_link.py`, both generic.

### 6.4 The directory is also untracked

`oem/` is not committed. Already added to `.gitignore`:

```gitignore
# OEM platform profiles: seed/key algorithms, ECU unlock procedures, PIN key names.
# Fails closed: the whole oem/ tree is ignored, so a new vendor profile is private by
# default rather than by remembering to add a line here.
iotsploit-exploits/src/iotsploit_exploits/oem/
```

**Both mechanisms are needed, and they cover different paths.** `.gitignore` stops it
reaching the public repo; `exclude` stops it reaching a wheel. Neither implies the other:
`poetry build` packages from the filesystem, not from git, so a build on the bench machine
— where the directory exists on disk — would happily ship an untracked file without the
`exclude`.

Three consequences to plan for:

- **A fresh clone has no `oem/`.** That makes the guarded import above the *normal* path,
  not an edge case: on any machine but the bench, `vehicle_debug` is simply absent and
  `adb_check` must still load and run its other checks.
- **The characterization vectors go with it.** `test_seedkey.py` imports the algorithm, so
  a tracked test plus an untracked module breaks `tools/testing/test-python-full.sh` on
  every fresh clone. It also *is* a small oracle for the algorithm — ten (seed, pin, key)
  triples — so publishing it while hiding the code would be self-defeating. It belongs at
  `oem/zeekr/tests/test_seedkey.py`, inside the ignored tree, and runs on the bench.
- **Untracked means one copy, with no history and no backup.** This is the real cost. The
  recommendation is a separate **private** git repository cloned into that path (it is
  already ignored, so it nests cleanly), which restores version control and review for the
  algorithm without putting it in the public one. A tarball on a shared drive works too and
  is worse in every way except effort.

### 6.4 Two fixes the move must make

Both measured against the running code:

- **It answers instead of failing on malformed input.** A 4-byte seed silently drops its
  top byte and returns a plausible key; an *empty* seed returns a key too; a short PIN
  raises `IndexError`. At the call site a wrong key is indistinguishable from a wrong PIN,
  so the failure gets debugged as "bad PIN". Wrap the body in a length guard — the body
  itself stays byte-identical, or the characterization vectors mean nothing.
- **It logs the derived key.** `doip_mgr.py:266` and `:295` emit `"Seed:{} And Seed_Key:{}"`
  at INFO. Collected (seed, key) pairs are the raw material for recovering the algorithm.
  (`sat_logs/` is gitignored and no log file is tracked, so there is no git exposure — but
  the lines belong at DEBUG, redacted.)

### 6.5 Most of `oem/` should eventually be data

Addresses are already facet fields; `2E C0 3E 01` could be; the PIN is already in
`ClassifiedInfo`/`Env_Mgr`; ECU names are already components. What is irreducibly code is
the algorithm alone. Phase 3 moves everything as-is, and the follow-up then has an obvious
scope: whatever is still in `oem/`.

A further step, once the procedures are data: `open_debug` / `close_debug` become an
ordinary exploit plugin with `ecu` and `action` parameters, discovered by entry point like
everything else, and `adb_check` stops importing it as a library. That is the natural end
state now that the code lives in the exploit package — but it is a separate change, and
plugin-calling-plugin needs a story first.

---

## 7. Fit with the ports-and-adapters layout

- **Dependency direction** matches what `ports/observations.py` states for
  `ObservationSink`: the pure package never imports Django; the Django ring builds its
  config. `iotsploit-core` gains nothing.
- **The binding layer is an adapter, not a tool.** `protocol_binding.py` goes in
  `adapters/django/`, not `tools/` — `tools/` is the legacy drawer (`Env_Mgr`,
  `Bash_Script_Mgr`, `DeviceInfo`, everything with `Instance()`) that this work moves away
  from. Note the neighbouring convention: `ports_impl/` is for implementations of a *core
  port*; `protocol_binding` implements none, so `adapters/django/` is right. `doip_link.py`
  genuinely is bench tooling and stays in `tools/`.
- **No new core port, deliberately.** A port lets the *inner* ring call outward — that is
  why `WifiBackend` and `ObservationSink` are ports. Nothing in `iotsploit-core` speaks
  SOME/IP; the flow is entirely outer-to-inner. A port with one implementation and no
  inner-ring caller makes every future protocol cost a file in core, which is the failure
  `facet.py:8` was written to prevent.
- **Plugin access** stays a direct import, matching `ip_scan.py:6-9`. Routing it through
  `PluginContext` was considered and rejected: `build_context()` lives in
  `iotsploit-platforms` and reads env vars, whereas a SOME/IP endpoint comes from the
  current target in the Django ring — wiring it through would make `iotsploit-platforms`
  depend on target state, a worse violation than the one it fixes.
- **Known compromise:** facet registration is still a hardcoded import in `apps.py:18`. An
  `iotsploit.facets` entry-point group would make facets extensible by people who cannot
  edit `apps.py`. Out of scope, not forgotten.

---

## 8. Tests

No hardware, no database:

- **Loopback SOME/IP server** — a thread on `127.0.0.1` answering TCP and UDP: session
  correlation, interleaved UDP responses, timeout, error return codes.
- **SD** — offer parsing including IPv4 endpoint options, multicast join, ttl.
- **Facets** — schema publication, hex metadata, `FacetRegistry.resolve` round trip,
  RawFacet degradation.
- **Loopback DoIP server** — routing activation, a **split TCP segment** (the bug the
  current code has), an NRC 0x78 followed by a positive response.
- **Seed-key characterization vectors** — committed before `doip_mgr.py` is deleted.
- **Binding** — `someip_client_for("TCAM")` on a target with no facet raises
  `NotConfigured` and never invents a host.

Not tested: scapy's own codecs. Round-tripping `SOMEIP`/`SD` through scapy tests scapy.

---

## 9. Phases

| # | scope | independently useful? |
|---|---|---|
| 1 | Package scaffold, `errors.py`, wiring into root pyproject + testpaths | no |
| 2 | **SOME/IP: client, SD listen, facet, binding adapter, tests** | **yes — this is the ask, and it ships alone** |
| 3 | DoIP: characterization vectors first, then `DoipClient`/`UdsClient`, facet move, `doip_link`, `iotsploit_exploits/oem/zeekr/` + `exclude` + build check, **delete `doip_mgr.py` + `doip_facet.py`**, migrate all three call sites | yes — but atomic, and needs bench access |
| 4 | `someip_discover` plugin (SD sweep → observations) | optional |

Phase 2 needs nothing from phase 3. If you want SOME/IP soonest, 1 → 2 → stop is a complete
deliverable.

---

## 10. Settled during review

Recorded so they are not reopened: the façade is not kept (§5.3); there is no new OEM
distribution and `oem/` lives in `iotsploit-exploits`, gitignored and excluded from the
wheel (§6.3–6.4); plugins reach the helpers by direct import rather than `PluginContext`
(§7); no new core port (§7); `can_facet.py` stays in `iotsploit_django.tools` until a CAN
client exists; the seed-key registry is replaced by passing `key_fn` (§2); `check_mcu_alive`
is plain UDS and stays in the protocol package (§5.3).

One fact worth recording: the working-copy `db.sqlite3` holds **zero targets**, so no stored
facet payload is at risk from any facet change here. The bench database may differ — worth a
glance before phase 3, not a blocker.

## 11. Open questions

1. **Where the SD group and interface come from long-term** — §4.4 puts both in plugin
   parameters for v1, because they describe an Ethernet segment and `Bus` cannot carry a
   facet. Is adding `facets` to `Bus` worth doing in core, or do segment-level settings
   stay parameters until Plane T lands?
2. **SD listening as a stream** — a long listen is really a driver/stream, not a one-shot
   call. Phase 2 exposes it as a blocking call with a timeout; wiring it to `StreamManager`
   for live UI updates could follow.
3. **Retraction, or forward fix only** — §6.2. The GitHub repo is public and
   `doip_mgr.py` is on `origin/main`; the published `iotsploit-django` wheel contains it
   too. Everything in this plan stops *new* exposure and none of it retracts the old.
   Whether to rewrite history, force-push and yank releases is a call for the repository
   owner together with whoever owns the OEM relationship — not a code decision, and not
   one this plan blocks on.
4. **Bench availability** — phase 3 deletes `doip_mgr.py` outright, so `check_mcu_alive`
   and `closedebug` need verifying against a real vehicle when it lands. Phase 2 is
   unaffected.
