# IoTSploit CLI Command Standardization Plan

Status: proposed; awaiting an implementation-option decision.

Date: 2026-07-14

Related plan: [`iotsploit_cli_e_command_palette_plan.md`](iotsploit_cli_e_command_palette_plan.md)

## 1. Objective

Replace the current flat, inconsistent command surface with a predictable and easy-to-discover command model while preserving existing scripts during a documented migration period.

The desired result is:

- one obvious canonical name for each operation;
- resource-oriented command namespaces such as `device list` and `plugin run`;
- consistent action verbs, arguments, options, help text, and confirmation behavior;
- short legacy names treated as compatibility aliases rather than first-class commands;
- default help and command-palette results that show canonical commands only;
- advanced cmd2 shell facilities available without overwhelming normal IoTSploit workflows;
- a staged migration with warnings and tests instead of an immediate breaking rename.

This document analyzes the command interface and proposes a plan. It does not implement or rename commands.

## 2. Repository facts

The command surface is assembled dynamically in [`iotsploit-cli/src/iotsploit_cli/console.py`](../iotsploit-cli/src/iotsploit_cli/console.py) from command mixins under [`iotsploit-cli/src/iotsploit_cli/commands/`](../iotsploit-cli/src/iotsploit_cli/commands/), plus commands inherited from cmd2 2.4.3.

### 2.1 Runtime inventory

A lightweight runtime inventory of the mixins and `cmd2.Cmd` reports **69 visible commands**:

| Source | Count | Description |
|---|---:|---|
| IoTSploit operation implementations | 35 | Long-form application commands such as `list_devices`, `execute_plugin`, and `flash_firmware`. |
| IoTSploit abbreviation methods | 23 | Duplicate `do_*` methods such as `lsdev`, `exec`, `fp`, `et`, and `sll`. |
| Inherited cmd2 commands | 11 | `alias`, `edit`, `help`, `history`, `macro`, `quit`, `run_pyscript`, `run_script`, `set`, `shell`, and `shortcuts`. |
| **Total visible** | **69** | The current palette can expose all of these as peers. |

cmd2 also supplies symbol shortcuts:

- `?` -> `help`
- `!` -> `shell`
- `@` -> `run_script`
- `@@` -> relative `run_script`

### 2.2 Current application commands

| Area | Long-form commands | Abbreviation methods |
|---|---|---|
| Device | `device_info`, `list_devices`, `execute_device_command`, `select_device`, `switch_device`, `scan_devices`, `initialize_devices`, `device_import` | `lsdev`, `dc`, `sd`, `scan`, `initdev`, `dimport` |
| Driver | `list_device_drivers`, `list_device_commands`, `get_driver_states`, `enable_driver`, `disable_driver` | `lsdrv`, `lscmd`, `gds`, `ed`, `dd` |
| Firmware | `list_firmware`, `add_firmware`, `flash_firmware`, `remove_firmware`, `download_firmware` | `lsfw`, `addfw`, `flashfw`, `rmfw`, `dlfw` |
| Plugin | `list_plugins`, `execute_plugin`, `flash_plugins` | `lsp`, `exec`, `fp` |
| Target | `list_targets`, `target_select`, `edit_target`, `target_import`, `target_export` | `lst`, `et` |
| Services | `runserver`, `stop_server` | None |
| Network | `connect_wifi` | None |
| System/configuration | `exploit`, `exit`, `set_log_level`, `set_log_format` | `sll`, `slf` |
| Linux passthrough | `ls`, `lsusb` | None |

### 2.3 Help is structurally incorrect

The command mixins correctly use `@cmd2.with_category(...)`. cmd2 stores that value on the command function as `help_category`.

The custom `get_all_commands_by_category()` implementation checks for `cmd_func.category` instead. As a result:

- category decorators are not read;
- a manual `_cmd_to_category` map classifies only 33 names;
- all mapped names are placed under the generic `Shell Commands` heading;
- remaining commands become `Uncategorized`;
- the custom help renderer explicitly skips `Uncategorized`, hiding those commands;
- raw `dir(self)` discovery is used instead of `get_visible_commands()`, so the implementation does not consistently honor cmd2 hidden/disabled state.

This means help output and palette output do not describe the same command surface.

### 2.4 Palette aliases are not recognized as aliases

Most abbreviations are declared by assigning another `do_*` method:

```text
do_lsdev = do_list_devices
do_exec = do_execute_plugin
do_fp = do_flash_plugins
```

cmd2 therefore sees each abbreviation as an independent command. They are not present in `shell.aliases`, so the current command palette cannot exclude them using its alias filtering rule. This is why short and long forms appear as equal suggestions.

### 2.5 Argument and help contracts are inconsistent

- All IoTSploit commands accept a raw `arg` string; none currently use cmd2 argparse decorators.
- Some commands call `.split()`, which cannot safely preserve quoted paths or values.
- Some missing arguments open interactive selectors, while others print a usage line and return.
- Usage is sometimes embedded in a one-line docstring, sometimes printed only after an error, and sometimes absent.
- `execute_device_command` documents `device_command [command_string]`, but `device_command` is not its actual command name.
- There is no uniform `--help`, option completion, validation, or machine-readable result contract for application commands.
- Destructive/state-changing operations use different confirmation mechanisms, including direct `input()`, `Input_Mgr`, or no confirmation.

### 2.6 Names do not follow one grammar

Examples:

- verb first: `list_devices`, `execute_plugin`, `connect_wifi`;
- resource first: `target_select`, `target_import`;
- verb in the middle: `edit_target`;
- implementation name: `runserver` and the category `Django Commands`, although the command starts Django, Daphne, MCP, and Celery;
- ambiguous verb: `flash_plugins` refreshes plugin discovery, while `flash_firmware` actually flashes hardware;
- incorrect resource: `device_info` displays host information;
- overlapping actions: `select_device` and `switch_device` both establish a current device;
- inconsistent abbreviations: `lsdev`, `gds`, `ed`, `dimport`, `flashfw`, `fp`, and `et` use unrelated abbreviation schemes.

### 2.7 Documentation is stale

The root [`README.md`](../README.md) lists commands that are no longer present, including `connect_lab_wifi`, plugin-group commands, and test commands. It also omits many current device, firmware, import/export, and configuration commands.

The package [`iotsploit-cli/README.md`](../iotsploit-cli/README.md) describes palette examples that omit many actual prefix matches because method-level abbreviations are exposed.

## 3. Problems to solve

### 3.1 Discoverability

Users must guess whether an operation starts with `list_`, ends in `_select`, or has a short form. A live palette makes the inconsistency more visible because it presents every implementation detail at once.

### 3.2 Memorability

There is no reusable grammar. Learning `list_devices` does not reliably predict `target_select`, `edit_target`, or `runserver`.

### 3.3 Ambiguity

Several commands do not communicate their effect accurately:

- `flash_plugins` means refresh/reload.
- `exploit` means execute every plugin.
- `device_info` means host information.
- `runserver` means start a suite of four services.
- `exec` could reasonably mean an OS command, a plugin, or a device command.

### 3.4 Automation

Raw strings and implicit interactive prompts make commands hard to script, validate, complete, and document.

### 3.5 Compatibility

The root README and likely user scripts already use the current names. Removing them immediately would break workflows even though the package is pre-1.0.

### 3.6 Single source of truth

Names, categories, aliases, docstrings, usage text, palette descriptions, README tables, and risk behavior currently come from different places. They drift independently.

## 4. Command design standard

The proposed standard applies to every new canonical application command.

### 4.1 Grammar

```text
<singular-resource> <action> [positional arguments] [options]
```

Examples:

```text
device list
device select usb-001
driver enable greatfet
plugin run wifi_scan --target vehicle-1
firmware flash esp32-build --device esp32
service start
```

Rules:

- Use a singular resource namespace: `device`, `driver`, `firmware`, `plugin`, `target`, `service`, `wifi`, `host`, or `config`.
- Use a small, shared action vocabulary: `list`, `show`, `select`, `scan`, `initialize`, `run`, `run-all`, `add`, `import`, `export`, `download`, `flash`, `remove`, `refresh`, `status`, `enable`, `disable`, `start`, `stop`, and `set`.
- Use lowercase kebab-case for multiword user-facing tokens, such as `run-all`, `log-level`, and `output-path`.
- Do not expose underscores in new canonical names. Python handler names may still use underscores internally.
- Prefer direct nouns and verbs over implementation terms such as Django or Celery.
- Use exactly one canonical path for each behavior.
- Treat short names as compatibility aliases, not separate commands.

### 4.2 Arguments and options

- Use cmd2 `Cmd2ArgumentParser` and `@with_argparser` for canonical commands.
- Required identity values are positional when there is only one obvious resource, for example `driver enable <name>`.
- Optional behavior uses kebab-case flags, for example `--output-path`, `--target`, and `--reason`.
- Support quoted paths and values; do not parse user input with plain `.split()`.
- Every namespace and action supports `--help` without initializing hardware or calling a backend.
- In a TTY, omitting an optional resource identifier may open a selector.
- In non-TTY/script mode, missing required input must return a clear parser error instead of blocking on a prompt.
- Repeated actions should use repeatable options or documented JSON input rather than an undocumented trailing string.

### 4.3 Help and descriptions

Each canonical action must provide:

- a one-sentence summary beginning with an imperative verb;
- generated usage;
- positional and option descriptions;
- at least one example for non-trivial commands;
- category/resource metadata;
- compatibility aliases, if any;
- state/risk classification.

Default `help` should show only canonical IoTSploit resources and essential shell commands. `help <resource>` should show resource actions. `help --all` should include advanced cmd2 commands and deprecated aliases.

### 4.4 Visibility levels

Define three visibility levels:

| Level | Default help | Palette | Direct execution | Purpose |
|---|---|---|---|---|
| Canonical | Yes | Yes | Yes | Recommended user-facing interface. |
| Advanced | No; shown with `--all` | Optional advanced mode | Yes | cmd2 facilities such as macros, scripts, shell escape, and editor. |
| Deprecated alias | No; shown with `--all` | No by default | Yes during migration | Compatibility with old commands and scripts. |

Essential shell commands are `help`, `history`, and `exit`. Keep `?` and `!` documented as shortcuts. Treat `alias`, `edit`, `macro`, `run_pyscript`, `run_script`, `set`, `shell`, and `shortcuts` as advanced.

### 4.5 Safety classification

Attach one of these classifications to each canonical action:

- `read-only`: lists or displays state;
- `state-changing`: selects, initializes, enables, disables, starts, stops, imports, downloads, or refreshes;
- `execution`: runs plugins, device commands, exploits, or firmware flashing;
- `destructive`: removes data or overwrites existing records.

Help and palette metadata may display this classification. Destructive operations must use one confirmation mechanism and support `--yes` for deliberate non-interactive execution. Merely browsing or completing commands must never call a backend.

### 4.6 Output behavior

- Use `self.poutput()`/`self.perror()` for user-facing command results.
- Use the logger for diagnostic/internal events.
- Set `self.last_result` consistently for scripts and tests.
- Avoid mixing `print()`, logger output, and cmd2 output in one command path.
- Plan a later `--output table|json` convention for list/show commands; it need not block the naming migration.

## 5. Proposed canonical command map

### 5.1 Host and device operations

| Proposed canonical command | Current names | Decision |
|---|---|---|
| `host show` | `device_info` | Correct the resource name: this displays the IoTSploit host. |
| `device list` | `list_devices`, `lsdev` | One predictable resource/action path. |
| `device scan` | `scan_devices`, `scan` | Keep `scan` as the shared discovery verb. |
| `device initialize` | `initialize_devices`, `initdev` | Use the full verb in the canonical path. |
| `device select [device]` | `select_device`, `sd`, `switch_device` | Merge selection and switching into one idempotent operation. |
| `device run [command]` | `execute_device_command`, `dc` | Short, explicit execution action under the device resource. |
| `device import <file>` | `device_import`, `dimport` | Standardize import placement and parser behavior. |

### 5.2 Driver operations

| Proposed canonical command | Current names | Decision |
|---|---|---|
| `driver list` | `list_device_drivers`, `lsdrv` | Stop calling drivers “device plugins” in user-facing text. |
| `driver commands [driver]` | `list_device_commands`, `lscmd` | Commands belong to a driver definition. |
| `driver status` | `get_driver_states`, `gds` | Use `status` rather than implementation-oriented `get_*`. |
| `driver enable [driver]` | `enable_driver`, `ed` | Standard action. |
| `driver disable [driver]` | `disable_driver`, `dd` | Standard action. |

### 5.3 Firmware operations

| Proposed canonical command | Current names |
|---|---|
| `firmware list` | `list_firmware`, `lsfw` |
| `firmware add <name> <path>` | `add_firmware`, `addfw` |
| `firmware download <url>` | `download_firmware`, `dlfw` |
| `firmware flash <name> --device <device>` | `flash_firmware`, `flashfw` |
| `firmware remove <name>` | `remove_firmware`, `rmfw` |

The implementation must resolve the current mismatch where `flash_firmware` requires a `device_name` in usage but does not visibly pass that value to `flash_registered_firmware` before declaring the new contract stable.

### 5.4 Plugin operations

| Proposed canonical command | Current names | Decision |
|---|---|---|
| `plugin list` | `list_plugins`, `lsp` | Standard list action. |
| `plugin run [plugin]` | `execute_plugin`, `exec` | Avoid the ambiguous global name `exec`. |
| `plugin run-all` | `exploit` | State the actual scope of the operation. |
| `plugin refresh` | `flash_plugins`, `fp` | Replace the misleading word `flash`. |

### 5.5 Target operations

| Proposed canonical command | Current names |
|---|---|
| `target list` | `list_targets`, `lst` |
| `target select [target]` | `target_select` |
| `target edit [target]` | `edit_target`, `et` |
| `target import <file>` | `target_import` |
| `target export <file>` | `target_export` |

### 5.6 Services, networking, and configuration

| Proposed canonical command | Current names | Decision |
|---|---|---|
| `service start` | `runserver` | Describe the multi-service suite rather than only Django. |
| `service stop` | `stop_server` | Pair with `service start`. |
| `service status` | No direct equivalent | Add a read-only status view because start/stop without status is difficult to operate. |
| `wifi connect [ssid]` | `connect_wifi` | Use the resource/action grammar. Password remains a secure prompt or option designed not to leak through history. |
| `config set [--log-level LEVEL] [--log-format FORMAT]` | `set_log_level`, `sll`, `set_log_format`, `slf` | Merge related logging configuration under one explicit command. With no flags, show current values or help. |
| `exit` | `exit`, inherited `quit` | Keep one displayed command; retain `quit` as a hidden compatibility alias. |

### 5.7 Linux passthrough commands

Deprecate `ls` and `lsusb` as IoTSploit canonical commands:

- `ls` duplicates cmd2’s existing `!ls`/`shell ls` mechanism.
- `lsusb` is Linux-specific while the CLI package advertises broader platform support.
- If USB enumeration is a real IoTSploit feature, replace it with a platform-backed `host usb-list` or `device scan --type usb` action rather than shelling out to `lsusb`.

During migration, keep direct execution available but hide both names from default help and the palette.

## 6. Interaction with the command palette

The current palette completes any first-token prefix, not only `e`. A namespaced command model changes the desired completion behavior:

1. At an empty prompt, typing `d` should suggest the canonical resource `device` and `driver`, not every old `do_d*` abbreviation.
2. After `device `, the palette should suggest `list`, `scan`, `initialize`, `select`, `run`, and `import`, with explanations.
3. Deprecated aliases should remain executable but should not appear unless an advanced/deprecated visibility mode is requested.
4. Selecting a namespace alone should insert it and continue completion, not dispatch an incomplete command.
5. Palette data should come from the same parser/command metadata used by help.

This standardization therefore supersedes the flat “show every `e*` method” mental model. Under the proposed canonical model, `e` primarily suggests `exit`; old `edit_target`, `execute_plugin`, `exec`, `et`, and similar names remain temporarily executable but hidden.

If preserving a rich `e*` list is a hard requirement, select Option B in Section 7 instead of the recommended namespaced Option C.

## 7. Implementation options

| Criteria | Option A: presentation cleanup | Option B: standardized flat commands | Option C: resource namespaces | Option D: immediate replacement |
|---|---|---|---|---|
| Approach | Fix categories/help and hide abbreviation methods from the palette; keep long names. | Rename canonical commands to one flat verb-noun convention, retaining legacy aliases. | Introduce `resource action` commands, metadata-driven help/palette, and staged compatibility aliases. | Remove old names and expose only the new namespace model in one release. |
| Main goal | Make the current list readable quickly. | Improve consistency while preserving first-token-only completion and many `e*` commands. | Establish a reusable, predictable command language. | Reach the final model fastest. |
| Code impact | Low | Medium | Medium/High | Medium/High |
| Files changed | Help, palette, tests, docs | Command methods, help, palette, tests, docs | Command parsers/modules, help, palette, compatibility layer, tests, docs | Same as C without compatibility layer |
| Development effort | Low | Medium | High | Medium |
| Implementation risk | Low | Medium | Medium | High |
| Performance impact | Negligible | Negligible | Negligible | Negligible |
| Compatibility impact | Very low | Low/Medium with aliases | Low during migration; breaking only after alias removal | High immediately |
| Testing requirement | Help and palette snapshots | Naming, alias, parser, and docs tests | Namespace parser, subcommand palette, alias migration, help, safety, and regression tests | Full migration tests plus downstream breakage handling |
| Maintenance impact | Existing naming debt remains | Better, but the flat namespace grows indefinitely | Best long-term separation and discoverability | Same final state as C but higher user-support cost |
| Future extension | Limited | Moderate | Strong: new actions fit existing resources | Strong |
| Recommended when | A quick cosmetic fix is enough. | The original flat `e*` behavior is more important than namespace structure. | Long-term usability and extensibility are the priority. | All downstream scripts can be changed atomically. |

## 8. Recommendation

Recommended option: **Option C — resource namespaces with staged compatibility aliases**.

Reasons:

- Users learn one grammar and can predict commands they have never used.
- The palette becomes smaller at the first token and more useful after the resource token.
- Related operations share generated help and argument conventions.
- Misleading names such as `flash_plugins`, `exploit`, `device_info`, and `runserver` are corrected.
- Legacy scripts continue to work during an explicit migration window.
- Future operations such as `service status` or `target delete` have an obvious home.

Trade-offs:

- The palette must gain subcommand completion rather than only first-token completion.
- Command handlers need argparse-backed adapters and contract tests.
- Documentation and examples must be updated together.
- The first release contains both canonical commands and compatibility aliases internally, even though only canonical commands are displayed.

## 9. Proposed architecture

### 9.1 Command metadata as the shared contract

Create one metadata model for canonical commands and compatibility aliases. At minimum it should represent:

- canonical path, for example `plugin run`;
- summary;
- resource/category;
- parser or parser-builder reference;
- handler reference;
- deprecated aliases;
- visibility level;
- safety classification;
- availability predicate, if a command is platform- or state-dependent;
- replacement text used in deprecation warnings.

Use cmd2 argparse parsers as the detailed source of positional/option help. Do not duplicate full usage strings in the metadata registry.

The help renderer and command palette must consume the same canonical metadata. A command added without summary, parser help, category, or risk classification should fail a contract test.

### 9.2 Resource command handlers

Implement one top-level cmd2 command per resource namespace, backed by subparsers:

- `do_device`
- `do_driver`
- `do_firmware`
- `do_plugin`
- `do_target`
- `do_service`
- `do_wifi`
- `do_host`
- `do_config`

Subparser handlers should call extracted operation methods. Do not make new canonical handlers invoke old `do_*` methods with reconstructed raw strings; both canonical and legacy paths should call the same typed operation function.

Example responsibility split:

```text
parser/adapter -> validate arguments -> operation method -> manager/service -> result formatter
legacy alias ------------------------^          
```

This prevents parser differences from creating different business behavior.

### 9.3 Compatibility aliases

Do not implement compatibility aliases as direct `do_short = do_long` assignments.

Instead, define explicit legacy adapters that:

1. recognize the old command;
2. emit one concise deprecation warning containing the replacement;
3. parse the legacy arguments according to the old contract;
4. call the shared typed operation;
5. remain hidden from normal help and palette results.

Track alias usage only locally and without sensitive argument values if telemetry/logging is desired. The feature does not require external telemetry.

### 9.4 Help modes

Replace the current custom category discovery with one of these safe approaches:

- preferred: rely on cmd2’s `help_category` and argparse help, adding a thin canonical-resource overview;
- acceptable: use the new metadata registry directly.

Do not continue using raw `dir(self)` and `func.category`.

Proposed behavior:

- `help`: canonical resource overview plus `help`, `history`, and `exit`;
- `help device`: device actions and summaries;
- `device --help`: parser-generated equivalent;
- `device select --help`: arguments, options, and examples;
- `help --all`: advanced cmd2 commands and deprecated aliases in separate sections;
- unknown command: nearest canonical suggestions, followed by a legacy replacement when applicable.

### 9.5 Palette modes

Extend `CommandCatalog` and `CommandPaletteCompleter` to understand a token path:

- token 1 completes canonical resources and essential shell commands;
- token 2 completes actions for the selected resource;
- later tokens delegate to argparse/cmd2 argument completion;
- deprecated aliases are recognized for execution but omitted from automatic suggestions;
- advanced commands are available through an explicit setting or `help --all`, not mixed into default discovery.

The palette should display the complete canonical path and summary, and may display safety/category tags when space allows.

## 10. Migration policy

Use a staged migration even though the package is pre-1.0.

### Stage 0: inventory freeze

- Add an executable snapshot test of the 69-command current surface.
- Classify each current name as canonical behavior, abbreviation, inherited advanced command, or removal candidate.
- Record representative legacy argument behavior before refactoring.

### Stage 1: presentation repair

- Fix category lookup and use visible commands.
- Hide method-level abbreviations from the default palette/help through explicit metadata.
- Correct README command tables and palette examples.
- Do not rename behavior yet.

This stage gives users an immediate readability improvement with minimal compatibility risk.

### Stage 2: introduce canonical namespaces

- Add argparse-backed resource commands and shared typed operations.
- Keep all legacy commands executable.
- Add `service status` only after its read-only process-state contract is specified and tested.
- Extend the palette to complete subcommands.

### Stage 3: deprecation release

- Emit replacement warnings for legacy names.
- Hide legacy names from default help/palette.
- Publish a migration table in release notes and README.
- Update all repository examples and scripts to canonical commands.

Recommended compatibility window: at least two published CLI releases or one documented minor-release cycle, whichever is longer.

### Stage 4: removal decision

- Review repository references, user feedback, and any local alias-usage evidence.
- Remove deprecated names only after explicit approval.
- Keep harmless familiar shell aliases such as `quit` only if they do not create divergent cleanup behavior.

## 11. File-level plan

| File or area | Planned change |
|---|---|
| `iotsploit-cli/src/iotsploit_cli/command_registry.py` | New canonical metadata, visibility, safety class, alias mapping, and lookup helpers. |
| `iotsploit-cli/src/iotsploit_cli/commands/*.py` | Add resource parsers, extract typed operation methods, and add explicit legacy adapters. Split files only where a current module would become harder to navigate. |
| `iotsploit-cli/src/iotsploit_cli/console.py` | Remove the hard-coded category map and broken category discovery; build canonical help from registry/cmd2 metadata. |
| `iotsploit-cli/src/iotsploit_cli/command_palette.py` | Complete resource/action paths and filter deprecated/advanced names. |
| `iotsploit-cli/tests/test_command_contract.py` | Enforce name grammar, unique canonical paths, summaries, parser help, visibility, safety class, and alias targets. |
| `iotsploit-cli/tests/test_command_migration.py` | Verify old and new commands call the same typed operations and warnings name the correct replacements. |
| Existing palette tests | Replace flat-prefix assumptions with canonical resource and subcommand completion tests. |
| `README.md` | Replace stale command lists and examples with generated/verified canonical tables and migration notes. |
| `iotsploit-cli/README.md` | Document command grammar, help, palette, advanced mode, aliases, and examples. |
| Release notes/changelog | Publish the deprecation window and full old-to-new map. Add a changelog if the project does not yet have one. |

## 12. Detailed implementation sequence

### Phase 1: contract tests and help repair

1. Add a test fixture that constructs a lightweight shell without Django managers or hardware.
2. Snapshot the current visible names and alias groups.
3. Add tests demonstrating the `category` versus `help_category` defect.
4. Replace custom category discovery with visible canonical metadata.
5. Separate canonical, advanced, and deprecated visibility in help and palette.
6. Update documentation to match the actual transitional surface.

Success gate: no command execution behavior changes; help and palette display a clean canonical subset.

### Phase 2: registry and parser foundation

1. Add `CommandSpec`, alias, visibility, and safety types.
2. Add contract validation with actionable startup/test errors.
3. Build one pilot namespace, recommended `target`, because its five actions demonstrate list/select/edit/import/export without hardware execution.
4. Add parser help, direct arguments, and TTY selector fallback.
5. Prove legacy and canonical paths call the same operations.

Success gate: `target list`, `target select`, `target edit`, `target import`, and `target export` pass unit tests while every old target name still works.

### Phase 3: migrate remaining read-only/state commands

1. Migrate `device` and `driver` discovery/status operations.
2. Migrate firmware registry list/add/download/remove operations.
3. Migrate service, host, wifi, and configuration operations.
4. Standardize user-facing output and `last_result` during each touched operation, without unrelated business-logic rewrites.

Success gate: all non-execution canonical namespaces have parser/help/palette coverage.

### Phase 4: migrate execution commands

1. Migrate `device run`.
2. Migrate `plugin run` and `plugin run-all`.
3. Migrate `firmware flash` after resolving its device argument contract.
4. Add uniform safety/confirmation and non-TTY behavior.

Success gate: execution and destructive paths have explicit argument and confirmation tests and no backend runs during help/completion.

### Phase 5: deprecation and documentation release

1. Add one-warning-per-invocation legacy adapters.
2. Hide deprecated names from default discovery.
3. Update every repository command reference.
4. Publish the complete migration matrix.
5. Run targeted CLI tests and the full Python gate.

## 13. Test plan

### 13.1 Static command-contract tests

- Canonical paths match the naming grammar.
- Resource namespaces are singular and drawn from an approved vocabulary.
- Actions are drawn from the shared vocabulary or explicitly reviewed.
- Canonical paths and aliases are globally unique.
- No alias points to another alias.
- Every command has summary, category, parser, visibility, and safety metadata.
- Deprecated aliases name a valid canonical replacement.
- No method-level assignment creates an unregistered visible alias.
- Help and completion do not execute managers, Django queries, subprocesses, network calls, or hardware calls.

### 13.2 Help tests

- Default help contains canonical resources and essential shell commands only.
- Resource help contains every canonical action exactly once.
- `--help` works at resource and action levels.
- `help --all` separates advanced commands and deprecated aliases.
- Disabled/platform-unavailable commands are labeled or omitted consistently.
- Help descriptions match palette descriptions.
- Root and package README command tables match the registry, ideally through a generated-doc check.

### 13.3 Parser tests

- Quoted paths and values are preserved.
- Required values fail clearly in non-TTY mode.
- TTY omission invokes a selector only where documented.
- Invalid choices are rejected before a backend call.
- Options use kebab-case and produce completion metadata.
- Destructive commands require confirmation or `--yes` according to policy.
- Passwords and secrets are not echoed into history or warnings.

### 13.4 Migration tests

- Each old long name and abbreviation routes to the expected canonical operation.
- Legacy argument behavior is preserved during the compatibility window.
- Each legacy invocation emits the correct replacement warning.
- Legacy aliases are absent from default help and palette.
- Repository scripts and examples no longer use deprecated names after Stage 3.

### 13.5 Palette tests

- First-token completion shows only canonical resources and essential shell commands.
- Second-token completion shows actions for the selected resource.
- Later-token Tab completion delegates to the relevant argparse/cmd2 completer.
- Deprecated and advanced names follow their visibility setting.
- Selection inserts the correct token/path without executing it.
- Safety and availability metadata do not cause backend calls.

### 13.6 Regression and quality gates

Run through Poetry:

```bash
poetry run pytest iotsploit-cli/tests
tools/testing/test-python-full.sh
```

Also run manual PTY checks for command completion, nested selectors, Ctrl+C, Ctrl+D, terminal resizing, and background service output. Report pass/fail/skip/warning counts as required by the repository testing policy.

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Existing scripts break after renaming | High | Compatibility aliases, warnings, repository reference scan, and a two-release window. |
| Canonical and legacy paths diverge | High | Both adapters call the same typed operation; equivalence tests. |
| Registry duplicates parser/help information | Medium | Store only shared metadata in the registry and keep detailed arguments in argparse. |
| Namespace completion regresses argument completion | High | Extend palette by token position and retain cmd2 adapter regression tests. |
| Refactor accidentally initializes hardware during help/tests | High | Lightweight shell fixtures and explicit no-side-effect help/completion tests. |
| Cleanup expands into business-logic rewrites | Medium | Extract only what is required for typed operations; track unrelated defects separately unless they block a stable contract. |
| Stale docs recur | Medium | Generate or validate command tables against the registry in tests. |
| Advanced cmd2 users lose functionality | Medium | Keep advanced commands executable and expose them through `help --all`/advanced palette mode. |
| `quit` and `exit` cleanup differ | High | Route both through one cleanup operation before hiding or retaining `quit`. |
| Platform-specific commands mislead users | Medium | Remove Linux passthrough from canonical IoTSploit commands and use platform adapters for real product features. |

## 15. Acceptance criteria

The command-standardization work is complete when:

- default help and palette show one canonical path per operation;
- the canonical interface follows the resource/action grammar;
- all 35 existing application behaviors have an explicit keep, merge, rename, or deprecate decision;
- abbreviations are compatibility aliases rather than independent visible `do_*` commands;
- resource and action help is parser-generated and accurate;
- canonical commands accept deterministic arguments for scripting and documented TTY fallbacks;
- help, palette, and README data come from or are checked against one metadata source;
- advanced cmd2 commands remain accessible without dominating default discovery;
- legacy names work and warn during the approved compatibility window;
- no command executes a backend during help or completion;
- targeted CLI tests and the full Python test gate pass;
- removal of deprecated aliases occurs only after a separate explicit decision.

## 16. Decision required

Please select an implementation direction:

- [ ] Option A — Presentation cleanup only.
- [ ] Option B — Standardized flat command names; preserves a richer flat `e*` palette.
- [x] Option C — Recommended: resource namespaces with staged compatibility aliases.
- [ ] Option D — Immediate replacement without a compatibility window.
- [ ] Need more investigation or a command UX mockup.

After confirmation, implementation should begin with Stage 0/Phase 1: freeze the current contract, fix help/category visibility, and clean default palette presentation before renaming behavior.

Decision recorded: Option C was selected. Implementation is tracked on
`feat/cli-command-standardization`.
