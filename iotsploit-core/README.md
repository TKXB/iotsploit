# iotsploit-core

Minimal, standalone **core** library extracted from `zeekr_sat_main`.

- **What it is**: domain models + ports (interfaces) + core orchestration.
- **What it is not**: Django/ORM/Celery/Channels integrations (those are application-layer adapters).

## Install

Poetry (recommended):

```bash
cd iotsploit-core
poetry install
```

Pip editable:

```bash
pip install -e iotsploit-core
```

## Use (quick start)

Verify it imports:

```python
import iotsploit_core
print(iotsploit_core.__version__)
```

### Exploit plugins (manager)

You wire this manager with **your own adapters** that implement `iotsploit_core.ports`.

```python
from iotsploit_core.core.exploit_manager import ExploitPluginManager

mgr = ExploitPluginManager(
    plugin_repo=...,   # implements PluginMetaRepository
    group_repo=...,    # implements PluginGroupRepository
    task_runner=...,   # implements TaskRunner (optional async delegation)
)

print(mgr.list_plugins())
# mgr.execute_plugin("SomePlugin", target=..., parameters={...})
```

Default exploit plugin dir:
- `IOTSPLOIT_EXPLOIT_PLUGINS_DIR` (or legacy `SAT_EXPLOIT_PLUGINS_DIR`)
- fallback: `./plugins/exploits`

### Device drivers (manager)

```python
from iotsploit_core.core.device_manager import DeviceDriverManager

dm = DeviceDriverManager(
    driver_state_repo=...,  # implements DriverStateRepository
)

print(dm.list_drivers())
# dm.scan_devices("drv_xxx")
```

Default device plugin dir:
- `IOTSPLOIT_DEVICE_PLUGINS_DIR` (or legacy `SAT_DEVICE_PLUGINS_DIR`)
- fallback: `<repo_root>/plugins/devices`

### Streaming (optional)

Core uses a safe **Noop** backend by default. In a web runtime, inject a real backend:

```python
from iotsploit_core.core.stream_manager import StreamManager

# StreamManager.configure_backend(MyBackend())
```

## Package layout

- `iotsploit_core.domain`: pure dataclasses/enums (no I/O)
- `iotsploit_core.ports`: interfaces to be implemented by adapters
- `iotsploit_core.core`: orchestration (plugin/device/tool managers)

## Notes

- `iotsploit_core.core.device_config` is **deprecated** (device config should live in DB via app-layer adapters).

