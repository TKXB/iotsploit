# Direct `plugins/` Dependencies

This note lists repository functionality that still depends directly on the legacy `plugins/` directory and is not merely using it as a fallback discovery path.

## Runtime hard dependencies

- Django plugin source read API `get_plugin_code()` forces the requested path into `plugins/...` and then reads the file directly.
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:1326`
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:1351`

- Django plugin source save API `save_plugin_code()` also forces the path into `plugins/...`, writes the file there, and stores backups under that directory.
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:1375`
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:1405`

- Django plugin listing API `list_plugin_info()` returns file-style paths derived from plugin metadata, which feeds the code viewing/editing flow above.
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:498`
  - Reference: `iotsploit-django/src/iotsploit_django/web/views.py:517`

## Build and install hard dependencies

- Poetry dev dependencies still install packages directly from legacy `plugins/...` paths.
  - Reference: `pyproject.toml:72`

- Docker image build runs `poetry install`, so the image build also depends on those path-based dev dependencies resolving successfully.
  - Reference: `Dockerfile:69`

## Direct path and import dependencies inside legacy plugins

- `plugins/devices/greatfet/drv_greatfet.py` imports from the legacy package path `plugins.devices...`.
  - Reference: `plugins/devices/greatfet/drv_greatfet.py:10`

- `plugins/devices/logic/drv_logic.py` imports from the legacy package path `plugins.devices.logic...`.
  - Reference: `plugins/devices/logic/drv_logic.py:21`

- `plugins/exploits/greatfet_rubber_duck.py` hardcodes script file paths under `plugins/exploits/rubber_duck_scripts/...`.
  - Reference: `plugins/exploits/greatfet_rubber_duck.py:74`

- `plugins/exploits/hydra_ssh_attack.py` hardcodes the default wordlist path under `plugins/exploits/hydra_cracker/...`.
  - Reference: `plugins/exploits/hydra_ssh_attack.py:44`

## Not counted as direct hard dependencies

These still reference `plugins/...`, but they are part of the current legacy fallback/discovery path rather than a unique hard dependency:

- `iotsploit-core/src/iotsploit_core/core/exploit_manager.py`
- `iotsploit-core/src/iotsploit_core/core/device_manager.py`
- `iotsploit-cli/src/iotsploit_cli/commands/django_commands.py`
- `iotsploit-django/src/iotsploit_django/config.py`

## Practical conclusion

Removing or renaming `plugins/` right now would break at least:

- Django plugin source viewing/editing APIs
- Poetry-based local installs that still use path dependencies
- Docker builds that run `poetry install`
- Any remaining legacy plugin modules that import from `plugins.*` or open files from `plugins/...`

## Actionable cleanup checklist

### Phase 1: Remove direct runtime dependency on `plugins/` in the Django UI and API

- Update plugin code read API to stop forcing paths into `plugins/...`.
  - File: `iotsploit-django/src/iotsploit_django/web/views.py:1326`
  - Goal: accept plugin source locations derived from package metadata or a safe resolved source map, not a hardcoded legacy prefix.

- Update plugin code save API to stop writing into `plugins/...`.
  - File: `iotsploit-django/src/iotsploit_django/web/views.py:1375`
  - Goal: either disable editing for packaged plugins, or write to a supported editable workspace location with explicit rules.

- Fix plugin list API so returned paths are valid for packaged plugins.
  - File: `iotsploit-django/src/iotsploit_django/web/views.py:498`
  - Goal: stop converting dotted module paths into fake file paths blindly.
  - Goal: return either a real filesystem path when available, or structured metadata such as `module`, `source_type`, and `editable`.

- Decide product behavior for packaged plugins.
  - Goal: define whether packaged plugins are read-only in UI, editable only in editable installs, or exportable to a workspace copy before editing.

### Phase 2: Remove build and install dependency on legacy path packages

- Replace dev path dependencies that still point into `plugins/...`.
  - File: `pyproject.toml:72`
  - Goal: move these to packaged equivalents or remove them if obsolete.

- Regenerate `poetry.lock` after dependency cleanup.
  - File: `poetry.lock`
  - Goal: remove any `url = "plugins/..."` entries.

- Verify Docker build assumptions after dependency cleanup.
  - File: `Dockerfile:69`
  - Goal: ensure `poetry install` succeeds without the legacy directory.

### Phase 3: Remove direct imports and file path assumptions inside legacy plugin modules

- Replace legacy absolute imports in device plugins.
  - Files:
    - `plugins/devices/greatfet/drv_greatfet.py:10`
    - `plugins/devices/logic/drv_logic.py:21`
  - Goal: import from `iotsploit_drivers...` or use local package-relative imports as appropriate.

- Replace hardcoded resource file paths in exploit plugins.
  - Files:
    - `plugins/exploits/greatfet_rubber_duck.py:74`
    - `plugins/exploits/hydra_ssh_attack.py:44`
  - Goal: load packaged resources via `importlib.resources` or another package-safe resource loader.

- Audit the packaged versions for equivalent fixes.
  - Targets:
    - `iotsploit-drivers/src/...`
    - `iotsploit-exploits/src/...`
  - Goal: ensure packaged plugins are fully self-contained and do not depend on legacy paths.

### Phase 4: Remove operational reliance on legacy discovery

- Remove or rework any UI and CLI wording that assumes “plugins directory” is the source of truth.
  - File: `iotsploit-cli/src/iotsploit_cli/commands/plugin_commands.py:209`
  - Goal: make refresh and discovery wording package-aware.

- Stop passing legacy plugin directories as default startup environment if packaged plugins are sufficient.
  - File: `iotsploit-cli/src/iotsploit_cli/commands/django_commands.py:138`
  - Goal: only set these environment variables when explicitly requested for legacy mode.

- Remove default config values that point to `plugins/...` once legacy mode is retired.
  - Files:
    - `iotsploit-django/src/iotsploit_django/config.py:13`
    - `iotsploit-core/src/iotsploit_core/core/device_manager.py:73`
    - `iotsploit-core/src/iotsploit_core/core/exploit_manager.py:52`
  - Goal: make entry points the default and legacy directories opt-in only.

### Phase 5: Validation before moving `plugins/`

- Verify exploit discovery works with only entry points installed.
  - Goal: plugin list, metadata, enable and disable, and execution all work without `plugins/exploits`.

- Verify device driver discovery works with only `iotsploit-drivers`.
  - Goal: driver list and initialization work without `plugins/devices`.

- Verify Django plugin list and any plugin source UI behavior still work.
  - Goal: either valid read-only behavior or explicit unsupported or edit-disabled behavior.

- Verify `poetry install` succeeds with no `plugins/...` path dependencies.

- Verify Docker build succeeds.

### Phase 6: Final removal

- Move `plugins/` to `plugins_bak/`.
  - Goal: test in a reversible way before deletion.

- Run the validation suite again with `plugins_bak/` in place.

- If all checks pass, remove remaining legacy environment variables, docs, and comments that mention `plugins/` as an active runtime mechanism.

## Suggested execution order

1. Phase 2
2. Phase 3
3. Phase 1
4. Phase 4
5. Phase 5
6. Phase 6

This order reduces risk by making packaging self-sufficient first, then fixing UI and API behavior, and only then removing legacy defaults.
