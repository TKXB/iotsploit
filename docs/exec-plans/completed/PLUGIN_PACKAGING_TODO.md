# Plugin Packaging Migration TODO

Based on [PLUGIN_PACKAGING_PLAN.md](./PLUGIN_PACKAGING_PLAN.md)

---

## Phase 1 — Package Setup

- [ ] **1. Create iotsploit-drivers package scaffold**
  Create `iotsploit-drivers/` directory with `pyproject.toml`, `README.md`, and `src/iotsploit_drivers/` layout. Include all driver subpackages: esp32, socketcan, ft2232, greatfet, logic, jlink, ubertooth, iotsploit_func_fpga.

- [ ] **2. Create iotsploit-exploits package scaffold**
  Create `iotsploit-exploits/` directory with `pyproject.toml`, `README.md`, and `src/iotsploit_exploits/` layout. Include all exploit subpackages: flood_attack, wifi_scan, ip_scan, nmap_scan, adb_check, serial, demo, rubber_duck_scripts, hydra_cracker, and standalone modules (greatfet_echo.py, greatfet_rubber_duck.py, simple_rubber_duck.py, hydra_ssh_attack.py, plugin_ssh.py).

- [ ] **3. Add missing `__init__.py` files for all subpackages** ← blocked by 1, 2
  - Drivers: esp32, socketcan, ft2232, greatfet, jlink, iotsploit_func_fpga (logic and ubertooth already have them)
  - Exploits: flood_attack, wifi_scan, ip_scan, nmap_scan, adb_check, serial, demo
  - Skip data dirs: rubber_duck_scripts, hydra_cracker

- [ ] **4. Migrate driver source code into iotsploit-drivers package** ← blocked by 1, 3
  Copy/move all driver source files from `plugins/devices/` into `src/iotsploit_drivers/` subpackages. Ensure each driver module plus `protocol.py` files are in correct locations.

- [ ] **5. Migrate exploit source code into iotsploit-exploits package** ← blocked by 2, 3
  Copy/move all exploit source files from `plugins/exploits/` into `src/iotsploit_exploits/` subpackages. Include data directories `rubber_duck_scripts/` and `hydra_cracker/` with their data files.

- [ ] **6. Fix import paths in driver code** ← blocked by 4
  Update all relative/legacy imports to use new package paths. E.g.:
  - `drv_greatfet.py`: `from plugins.devices.greatfet.protocol` → `from iotsploit_drivers.greatfet.protocol`
  - Same for `drv_logic.py` and any other cross-module imports within drivers.

- [ ] **7. Fix import paths in exploit code** ← blocked by 5
  Update all relative/legacy imports in exploit modules to use new `iotsploit_exploits` package paths.

- [ ] **8. Migrate data file access to `importlib.resources`** ← blocked by 5
  Update `greatfet_rubber_duck.py` and `hydra_ssh_attack.py` to use `importlib.resources.files()` instead of hardcoded/relative paths for `rubber_duck_scripts/` and `hydra_cracker/` data files.

- [ ] **9. Declare full runtime dependency closure in both package `pyproject.toml` files** ← blocked by 1, 2
  Make both packages true fat packages.
  - `iotsploit-drivers` must include all driver runtime deps, including `iotsploit-django` because `drv_esp32.py` imports Django SCPI modules at import time.
  - `iotsploit-exploits` must include all exploit Python deps (`scapy`, `paramiko`, `pyserial`, `facedancer`, `iotsploit-django`, etc.).
  - Do not use plugin-level `extras` to split official plugin dependencies.

- [ ] **10. Include exploit data files in wheel/sdist packaging** ← blocked by 2, 5
  Add package data configuration so these files are present after installation:
  - `rubber_duck_scripts/*.txt`
  - `hydra_cracker/*.txt`

- [ ] **11. Configure entry_points in both `pyproject.toml` files** ← blocked by 1, 2, 9
  Register all 8 driver entry_points under `iotsploit.device_drivers` group and all 14 exploit entry_points under `iotsploit.exploit_plugins` group.

---

## Phase 1 — Manager Refactor

- [ ] **12. Add entry_points discovery to DeviceDriverManager** ← blocked by 11
  Add `_load_entry_point_drivers()` method that loads from `iotsploit.device_drivers` entry_points. Update `load_plugins()` to call entry_points first, then legacy filesystem scan. Same-name drivers: entry_point takes priority.

- [ ] **13. Add entry_points discovery to ExploitPluginManager** ← blocked by 11
  Add `_discover_entry_point_plugins()` method. Update discovery to scan legacy first, then entry_points. Union both results into `discovered_plugins` before calling `disable_missing()`. Write `module_path` as dotted path format. Keep pluggy registration in `_load_plugin_instance()` unchanged.

- [ ] **14. Fix `DjangoPluginMetaRepository.upsert()` to preserve enabled state** ← blocked by 13
  Change `upsert()` to use `get_or_create`: new plugins default `enabled=True`, existing plugins only update metadata (`module_path`, `description`, `license`, `author`, `parameters`) without overwriting `enabled` field.

- [ ] **15. Align `/api/plugins/exploits/discovered/` behavior with repository upsert semantics** ← blocked by 14
  Update Django discovery reporting endpoint so it does not reintroduce conflicting enable/disable behavior.
  - Preserve existing `enabled` state for existing plugins.
  - New plugins should follow the same default-enable policy as `DjangoPluginMetaRepository.upsert()`.
  - Keep Django DB as the single source of truth for exploit enable/disable state.

- [ ] **16. Fix plugin-group creation fallback that synthesizes legacy `module_path` values** ← blocked by 13, 14
  Current group creation code can create placeholder plugin records with `module_path = "plugins.exploits.<name>"`, which is invalid for the new packaging model.
  Update this flow so it does not invent fake module paths.
  Acceptable approaches:
  - Require the plugin to have been discovered before it can be added to a group, or
  - Resolve the actual dotted path from discovered metadata before creating the group linkage.

- [ ] **17. Update root `pyproject.toml` dependencies** ← blocked by 1, 2
  Replace legacy path deps (`flood_attack`, `esp32_driver`, `socketcan_driver`, etc.) with:
  ```toml
  iotsploit-drivers = { path = "iotsploit-drivers", develop = true }
  iotsploit-exploits = { path = "iotsploit-exploits", develop = true }
  ```

---

## Validation

- [ ] **18. Create smoke test scripts** ← blocked by 6, 7, 8, 10, 11
  Create `smoke_test_drivers.py`, `smoke_test_exploits.py`, and `smoke_test_data_files.py` verification scripts.

- [ ] **19. Run smoke tests and validate in clean venv** ← blocked by 12, 13, 14, 15, 17, 18
  Install packages in clean venv and run all smoke tests. Verify:
  - All 8 drivers discoverable via entry_points
  - All 14 exploits discoverable via entry_points
  - Data files present in wheel
  - DB integrity after discovery

- [ ] **20. Validate Django and MCP integration paths after discovery migration** ← blocked by 13, 14, 15, 16, 19
  Verify end-to-end behavior that is not covered by entry-point smoke tests alone:
  - Django `/api/plugins/exploits/enabled/` returns correct dotted `module_path` values
  - MCP discovery reporting does not incorrectly disable or hide new plugins
  - Existing `PluginGroup` / `PluginSequence` records still execute successfully
  - Creating or editing groups after migration does not generate invalid placeholder plugin metadata

---

## Phase 2 — Legacy Removal

- [ ] **21. Remove legacy filesystem discovery** ← blocked by 20
  1. Remove legacy filesystem scan from `device_manager.py`
  2. Remove legacy filesystem scan from `exploit_manager.py`
  3. Remove `plugins_dir` parameter and default path logic
  4. Remove `plugins/` directory related env vars
  5. Delete `plugins/` directory

- [ ] **22. Repo-wide cleanup** ← blocked by 21
  Clean up references to old `plugins/` paths in:
  - Root `pyproject.toml`
  - `iotsploit-core/src/iotsploit_core/core/device_manager.py`
  - `iotsploit-core/src/iotsploit_core/core/exploit_manager.py`
  - `iotsploit-django/src/iotsploit_django/config.py`
  - `iotsploit-cli/src/iotsploit_cli/commands/django_commands.py`
  - `iotsploit-mcp/src/iotsploit_mcp/composition_root.py`
  - `README.md`, `CONTRIBUTING.md`, `iotsploit-core/README.md`, `iotsploit-mcp/README.md`

- [ ] **23. Document system tool dependencies in iotsploit-exploits README** ← blocked by 2
  Document that `nmap_scan` requires system `nmap`, `hydra_ssh_attack` requires system `hydra`, and `adb_check` requires system `adb` as optional runtime dependencies.
