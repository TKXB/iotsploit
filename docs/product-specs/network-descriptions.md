# Local network descriptions

Open **Toolkit → Network Descriptions → Open file** to read an ARXML or DBC
without starting Django, uploading a file, or creating/selecting a target.
The tool is available in desktop Dev, Prod, and Offline builds. Mobile and web
are not enabled for this tool.

The Rust document owner reads one UTF-8 source up to 32 MiB. This conservative
input bound is separate from the legacy backend's 256 MiB upload limit; the
public sample measurements do not establish large OEM-file compatibility.
Closing the document releases its opaque Rust owner. Documents are session
local, with no library/database or automatic source retention.

Use the category outline to browse networks, nodes, frames, PDUs, signals and
other named elements. Search matches names, kinds, source paths and summary
fields (including ARXML identifiers). Tables page through at most 50 entries;
the Rust API caps requests at 100. Select an entry for source properties,
parent/child navigation and references. Resolved references open their source
definition; unresolved references are labelled and are never fetched from
the network or filesystem automatically. Narrow windows alternate between the
list and inspector. Diagnostics expose coverage and source/schema warnings.

## Coverage

DBC uses the existing `can-core::parse_dbc` owner: nodes including empty nodes,
node comments, frames, standard/extended IDs, signal bit placement, signedness,
byte order, linear scaling/ranges, units, simple multiplexing and value labels.
Unsupported float-type records, extended multiplexing, attributes and other
meaningful metadata are reported. This is not a comprehensive DBC editor;
receivers and frame/signal comments are not interpreted. Invalid numeric CAN
identifiers are reported instead of becoming frame zero, and standard/extended
value tables are kept distinct.

The same standard/extended value-table identity correction is applied to the
legacy Python DBC parser, with regression checks in both implementations.

ARXML uses `autosar-data = 0.23.0` to load AUTOSAR 4.x source definitions,
physical channels, ECUs, frame definitions/triggerings, PDUs, I/system signals,
placement mappings, encoding/scaling definitions, containers and references.
It preserves positional source paths for repeated coefficients/scale entries.
The first viewer does **not** flatten complex PDUs, multiplexers or containers
into CAN codec layouts, and does not claim full Python/cantools semantic parity.
Follow references to inspect those source definitions. Counts deliberately
include definitions and placements: they differ from flattened message/signal
counts in cantools or a vehicle target. Detail traversal is bounded to 4,096
elements and 512 properties/references, and values to 4,096 characters; the
inspector warns when a result is truncated. DTD/entity declarations are refused.

Multi-file ARXML, editing, target conversion, and source release merging are
follow-on work. The existing target import dialog/HTTP endpoint and Python
CLI importers retain their current behavior. Python's DBC parser remains the
legacy CLI/`apply_dbc` owner; Rust is the local viewer owner. The unused
`can_parse_dbc` bridge and `TargetCanIndex.fromDbc` were replaced by the document
API rather than retained alongside it.

## Samples and checks

Public MIT-licensed cantools samples live in
`ui/can/fixtures/network-descriptions/`. Its manifest records upstream revision,
URLs, hashes and coverage; `LICENSE-cantools` retains the upstream license.
Private OEM files must not be added to the public corpus, logs or artifacts.

```bash
cargo test --manifest-path ui/can/Cargo.toml
poetry run pytest tools/testing/test_network_descriptions.py
cargo run --manifest-path ui/can/Cargo.toml -p network-description \
  --example inspect -- ui/can/fixtures/network-descriptions/system-4.2.arxml Frames
```

The explicit cross-repository check compares both DBC sample files against
the live Python parser on all supported signal/frame fields. For ARXML it
compares all eight frame triggerings' identifiers and payload lengths against
cantools, and Rust tests verify native reference links and repeated numerator
values. This is a precise, limited agreement check, not full ARXML parity.

The native fuzz probe is an opt-in build feature; it is absent from the app's
production API. Its adapter runs inside the existing isolated parser worker,
using the same budgets, mutation engine, archive/ledger and replay. The pack is
explicit so Python-only installs do not require Cargo or the UI checkout.

```bash
cargo build --manifest-path ui/can/Cargo.toml -p network-description --features parser-probe
export IOTSPLOIT_RUST_PARSER_LIBRARY="$PWD/ui/can/target/debug/libnetwork_description.so"
poetry run python -m iotsploit_fuzzer.core.parser_campaign \
  --targets iotsploit_fuzzer.targets.rust \
  --target rust.parse_dbc --target rust.parse_arxml --iterations 2000
poetry run python -m iotsploit_fuzzer.core.parser_campaign \
  --targets iotsploit_fuzzer.targets.rust \
  --target rust.parse_dbc --target rust.parse_arxml --replay
```

Run those commands after rebuilding the probe for parser changes. The adapter
fingerprint includes Rust sources and the CAN dependency lockfile, so a changed
oracle requires the framework's explicit `--rebaseline` review. Use the platform's
native library name on macOS/Windows; Linux is the validated platform here.

`ui/tools/testing/test-flutter-full.sh` covers the new Rust workspace crate and
real-FFI viewer widget tests alongside existing checks. Native fuzz replay and
the cross-repository comparison are explicit additional gates, not silently
included in a Python-only installation's gate.

## Validation record (2026-11-11)

Validated on Linux with Rust 1.92.0, Flutter 3.35.7 / Dart 3.9.2, and cantools
42.0.3. The full Flutter gate passed 950 widget/unit tests with zero analyzer
issues, alongside its Rust checks. The full Python gate passed 2,064 tests,
with 5 skips and 47 warnings. The additional cross-repository
comparison passed all 3 cases; all 6 document integration tests passed.

Native fuzz campaigns ran 2,000 new mutations per format plus retained inputs:
no crashes, timeouts, resource failures or contract violations. The resulting
10 DBC and 34 ARXML retained cases replayed with zero findings. A full Linux
debug app build succeeded. Desktop/narrow viewer renders were inspected using
the actual Rust bridge and downloaded files; artifacts are under
`ui/build/network-descriptions/` (not source-controlled).

For these small public inputs, the debug CLI including indexed detail output
measured 0.04 s / 7,436 KiB peak RSS for the 71,059-byte ARXML, and 0.03 s /
7,820 KiB for the 822-byte DBC using `/usr/bin/time`. These are sample checks,
not a large-file benchmark or an OEM compatibility claim. No private OEM
sample was supplied. Other desktop platforms have not been validated here.
