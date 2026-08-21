# Plugin 打包方案 V3

## 结论

本项目最终采用严格的“两包制”：

- `iotsploit-drivers`
- `iotsploit-exploits`

这两个包都是真实插件包，不是元包，不拆成多个子发行包。

插件发现机制最终统一为 `entry_points`。

但要让“两包制”真正可落地，必须同时接受以下前提：

1. 不再使用 `extras` 做插件级依赖拆分
2. 每个包都必须声明自己包含的全部插件所需的完整依赖
3. exploit 体系继续保持 Django DB 为 SSOT
4. 迁移分阶段进行，先兼容双发现，再切到 `entry_points-only`

如果不接受这四条，两包制在当前代码结构下会持续出现 discovery/import/依赖缺失问题。

---

## 为什么这次选“两包制”

相比“每个插件单独发包”或“按依赖域拆成很多包”，两包制更适合当前仓库阶段：

- 当前插件主要是官方内置插件，不是开放市场
- `exploit_manager`、Django DB、CLI、MCP 已经与现有插件体系深度耦合
- 发布、CI、版本管理、文档维护成本应尽量低
- 用户与团队都更容易理解 `drivers` / `exploits` 两个安装入口

所以本次方案优先选择：

- 发布简单
- 迁移成本低
- 能兼容现有系统

而不是追求最细粒度的包边界。

---

## 必须放弃的旧思路

两包制下，以下思路必须明确放弃：

- `iotsploit-drivers[esp32]`、`iotsploit-drivers[socketcan]` 这种按插件装依赖的玩法
- `iotsploit-exploits[flood,ssh]` 这种按功能 extras 选择依赖
- discovery 阶段完全不 import 插件，只靠占位 metadata 写入 DB

原因很简单：

- 一个包只要注册了某个 entry_point，这个插件就被“公开存在”
- 当前很多插件在模块顶层就 import 自己依赖
- 如果包里包含插件代码，但没有同时安装依赖，manager 一旦 import 就会炸

因此，两包制必须是：

**两个 fat packages，分别带齐自己需要的依赖。**

---

## 目标架构

```text
                    ┌──────────────────┐
                    │  iotsploit-core  │
                    └────────▲─────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────┴─────────┐ ┌──────┴─────────┐ ┌──────┴─────────┐
│ iotsploit-drivers │ │ iotsploit-     │ │ iotsploit-cli  │
│ 所有 driver 代码   │ │ exploits       │ │ 依赖 django     │
│ 所有 driver 依赖   │ │ 所有 exploit 代码│ │                 │
│ 注册 driver EPs    │ │ 所有 exploit 依赖│ │                 │
└─────────▲─────────┘ │ 注册 exploit EPs│ └────────────────┘
          │           └────────▲────────┘
          └────────────────────┼────────────────────┐
                               │                    │
                    DeviceDriverManager   ExploitPluginManager
```

说明：

- `iotsploit-drivers` 内包含全部 driver 源码并注册所有 driver entry_points
- `iotsploit-exploits` 内包含全部 exploit 源码并注册所有 exploit entry_points
- `ExploitPluginManager` 仍通过 DB 维护插件启用状态和 group 编排

---

## 关键约束

## 1. `iotsploit-drivers` 不再因 `esp32` 拉上 Django 依赖

当前 `drv_esp32.py` 已改为模块内本地 import：

- `iotsploit_drivers.esp32.scpi_client`

因此，`ESP32Driver` 仍然留在 `iotsploit-drivers` 包内也不会再引入 `iotsploit-django` 运行时依赖。

当前更合理的边界是：

- `iotsploit-drivers` 仅保留设备驱动所需依赖
- `esp32` 私有的 SCPI helper 跟随驱动一起发布

如果未来出现第二个以上设备复用 SCPI，再考虑抽成共享包更合适。
- 再让 `drv_esp32.py` 改为依赖该独立库

本方案不把这项解耦作为前置条件。

## 2. exploit 的 DB key 继续沿用当前插件 `Name`

当前 exploit 体系里，真正稳定参与业务逻辑的是插件显示名，例如：

- `Hydra SSH Attack`
- `Rubber Duck`
- `IP Network Scanner`

这些名字已经进入：

- Django Plugin 表
- PluginGroup / PluginSequence
- CLI 选择与展示
- HTTP API 返回内容

因此本次迁移不引入新的 `plugin_id` 字段。

规则保持为：

- discovery 时实例化插件
- 使用 `plugin.get_info()["Name"]` 作为 DB 中的 `name`
- `module_path` 记录新的 dotted path

这样才能保持现有 group 和 UI 行为兼容。

## 3. discovery 阶段允许 import 插件

因为现在两个包都是 fat packages，自身依赖是完整的，所以 discovery 阶段可以安全 import 插件：

- driver discovery 可以 `ep.load()`
- exploit discovery 可以 `ep.load()` 并实例化来提取 metadata

这和旧版“合集包 + extras”不同。

---

## 包内容设计

## `iotsploit-drivers`

包含以下代码：

- `esp32`
- `socketcan`
- `ft2232`
- `greatfet`
- `logic`
- `jlink`
- `ubertooth`
- `iotsploit_func_fpga`

建议源码布局：

```text
iotsploit-drivers/
├── pyproject.toml
├── README.md
└── src/
    └── iotsploit_drivers/
        ├── __init__.py
        ├── esp32/
        │   ├── __init__.py
        │   └── drv_esp32.py
        ├── socketcan/
        │   ├── __init__.py
        │   └── drv_socketcan.py
        ├── ft2232/
        │   ├── __init__.py
        │   ├── drv_ft2232.py
        │   └── protocol.py
        ├── greatfet/
        │   ├── __init__.py
        │   ├── drv_greatfet.py
        │   └── protocol.py
        ├── logic/
        │   ├── __init__.py
        │   ├── drv_logic.py
        │   └── protocol.py
        ├── jlink/
        │   ├── __init__.py
        │   └── drv_jlink.py
        ├── ubertooth/
        │   ├── __init__.py
        │   └── drv_ubertooth.py
        └── iotsploit_func_fpga/
            ├── __init__.py
            └── drv_iotsploit_fpga.py
```

每个子目录都必须包含 `__init__.py`，否则无法作为 Python 子包被 import。
当前仓库中 `greatfet/`、`ft2232/`、`esp32/`、`socketcan/`、`jlink/`、`iotsploit_func_fpga/` 均缺少 `__init__.py`，迁移时必须补全。

建议 `pyproject.toml`：

```toml
[tool.poetry]
name = "iotsploit-drivers"
version = "0.0.1"
description = "Official IoTSploit device driver package"
authors = ["IoTSploit Team <support@iotsploit.org>"]
license = "GPL-3.0-or-later"
readme = "README.md"
packages = [{ include = "iotsploit_drivers", from = "src" }]

[tool.poetry.dependencies]
python = ">=3.10,<4.0"
iotsploit-core = "^0.0.1"
iotsploit-django = "^0.0.1"
pyusb = ">=1.2"
python-can = ">=4.5"
pyserial = ">=3.5"
pyftdi = ">=0.55"
pylink-square = ">=2.0"
pyudev = ">=0.24"
esptool = ">=4.8"

[tool.poetry.plugins."iotsploit.device_drivers"]
drv_esp32 = "iotsploit_drivers.esp32.drv_esp32:ESP32Driver"
drv_socketcan = "iotsploit_drivers.socketcan.drv_socketcan:SocketCANDriver"
drv_ft2232 = "iotsploit_drivers.ft2232.drv_ft2232:FT2232Driver"
drv_greatfet = "iotsploit_drivers.greatfet.drv_greatfet:GreatFETDriver"
drv_jlink = "iotsploit_drivers.jlink.drv_jlink:JLinkAbility"
drv_ubertooth = "iotsploit_drivers.ubertooth.drv_ubertooth:UbertoothDriver"
drv_logic = "iotsploit_drivers.logic.drv_logic:EnxorLogicAnalyzerDriver"
drv_iotsploit_fpga = "iotsploit_drivers.iotsploit_func_fpga.drv_iotsploit_fpga:ECP5FPGADriver"

[build-system]
requires = ["poetry-core>=1.8.0"]
build-backend = "poetry.core.masonry.api"
```

## `iotsploit-exploits`

包含以下代码：

- `flood_attack`
- `wifi_scan`
- `ip_scan`
- `nmap_scan`
- `adb_check`
- `serial`
- `demo`
- `greatfet_echo.py`
- `greatfet_rubber_duck.py`
- `simple_rubber_duck.py`
- `hydra_ssh_attack.py`
- `plugin_ssh.py`
- `rubber_duck_scripts/`
- `hydra_cracker/`

建议源码布局：

```text
iotsploit-exploits/
├── pyproject.toml
├── README.md
└── src/
    └── iotsploit_exploits/
        ├── __init__.py
        ├── flood_attack/
        ├── wifi_scan/
        ├── ip_scan/
        ├── nmap_scan/
        ├── adb_check/
        ├── serial/
        ├── demo/
        ├── rubber_duck_scripts/
        ├── hydra_cracker/
        ├── greatfet_echo.py
        ├── greatfet_rubber_duck.py
        ├── simple_rubber_duck.py
        ├── hydra_ssh_attack.py
        └── plugin_ssh.py
```

建议 `pyproject.toml`：

```toml
[tool.poetry]
name = "iotsploit-exploits"
version = "0.0.1"
description = "Official IoTSploit exploit plugin package"
authors = ["IoTSploit Team <support@iotsploit.org>"]
license = "GPL-3.0-or-later"
readme = "README.md"
packages = [{ include = "iotsploit_exploits", from = "src" }]
include = [
    { path = "src/iotsploit_exploits/rubber_duck_scripts/*.txt", format = ["sdist", "wheel"] },
    { path = "src/iotsploit_exploits/hydra_cracker/*.txt", format = ["sdist", "wheel"] },
]

[tool.poetry.dependencies]
python = ">=3.10,<4.0"
iotsploit-core = "^0.0.1"
iotsploit-django = "^0.0.1"
scapy = ">=2.5"
paramiko = ">=3.0"
pyserial = ">=3.5"
facedancer = ">=3.0"

[tool.poetry.plugins."iotsploit.exploit_plugins"]
flood_attack = "iotsploit_exploits.flood_attack.flood_attack:FloodAttackPlugin"
syn_flood_attack = "iotsploit_exploits.flood_attack.syn_flood_attack:SynFloodAttackPlugin"
wifi_scan = "iotsploit_exploits.wifi_scan.wifi_scan:WifiScanPlugin"
ip_scan = "iotsploit_exploits.ip_scan.ip_scan:IPScanPlugin"
nmap_scan = "iotsploit_exploits.nmap_scan.nmap_scan:NmapScanPlugin"
adb_check = "iotsploit_exploits.adb_check.adb_check:AdbSecurityCheckPlugin"
hydra_ssh_attack = "iotsploit_exploits.hydra_ssh_attack:HydraSSHAttackPlugin"
plugin_ssh = "iotsploit_exploits.plugin_ssh:SSHPlugin"
picocom_serial_reader = "iotsploit_exploits.serial.picocom_serial_reader:PicocomSerialReaderPlugin"
greatfet_echo = "iotsploit_exploits.greatfet_echo:FTDIEchoPlugin"
greatfet_rubber_duck = "iotsploit_exploits.greatfet_rubber_duck:RubberDuckPlugin"
simple_rubber_duck = "iotsploit_exploits.simple_rubber_duck:SimpleRubberDuckPlugin"
async_sleep_attack = "iotsploit_exploits.demo.async_sleep_attack:AsyncSleepAttackPlugin"
stream_data_attack = "iotsploit_exploits.demo.stream_data_attack:StreamDataAttackPlugin"

[build-system]
requires = ["poetry-core>=1.8.0"]
build-backend = "poetry.core.masonry.api"
```

---

## 插件依赖审计

以下是根据源码实际 import 审计的完整依赖映射，确保 fat package 策略的依赖闭包正确。

### `iotsploit-drivers` 依赖映射

| 插件 | Python 依赖 | 说明 |
|------|-------------|------|
| `esp32` | `esptool`, `pyserial` | 顶层 import 本地 `scpi_client` helper |
| `socketcan` | `python-can` | `import can` |
| `ft2232` | `pyusb`, `pyftdi`, `pyudev`, `pyserial` | 顶层 import 全部 |
| `greatfet` | `pyusb` | `import usb.core, usb.util` |
| `logic` | `pyserial` | `import serial, serial.tools.list_ports` |
| `jlink` | `pylink-square` | `import pylink` |
| `ubertooth` | `pyusb` | `import usb.core, usb.util` |
| `iotsploit_func_fpga` | _(仅 iotsploit-core)_ | 无额外第三方依赖 |

### `iotsploit-exploits` 依赖映射

| 插件 | Python 依赖 | 系统工具依赖 | 说明 |
|------|-------------|-------------|------|
| `flood_attack` | `iotsploit-django` | — | 顶层 import `iotsploit_django.tools.*` |
| `syn_flood_attack` | `scapy`, `iotsploit-django` | — | 顶层 import `scapy.all`, `iotsploit_django.adapters.*` |
| `wifi_scan` | _(仅 iotsploit-core)_ | — | 通过 PluginContext 后端注入 |
| `ip_scan` | `iotsploit-django` | — | 重度依赖 `iotsploit_django.tools.*`（5 个子模块） |
| `nmap_scan` | _(仅 iotsploit-core)_ | `nmap` | 通过 `tool_manager` 调用系统 nmap |
| `adb_check` | `iotsploit-django` | `adb` | 顶层 import `iotsploit_django.tools.adb_mgr` |
| `hydra_ssh_attack` | _(仅 iotsploit-core)_ | `hydra` | 通过 `tool_service` 调用系统 hydra |
| `plugin_ssh` | `paramiko` | — | `from paramiko import SSHClient` (replaces pwntools) |
| `picocom_serial_reader` | `pyserial` | — | `import serial, serial.tools.list_ports` |
| `greatfet_echo` | `facedancer` | — | `from facedancer.devices.ftdi import FTDIDevice` |
| `greatfet_rubber_duck` | `facedancer` | — | 使用 `facedancer.devices.keyboard`；需要迁移硬编码路径 |
| `simple_rubber_duck` | `facedancer` | — | `from facedancer.devices.keyboard import USBKeyboardDevice` |
| `async_sleep_attack` | _(仅 iotsploit-core)_ | — | demo 插件 |
| `stream_data_attack` | _(仅 iotsploit-core)_ | — | demo 插件 |

### 系统工具依赖说明

`nmap_scan`、`hydra_ssh_attack`、`adb_check` 依赖系统级工具（`nmap`、`hydra`、`adb`），
这些不是 Python 包依赖，无法在 pyproject.toml 中声明。
应在 `iotsploit-exploits` 的 README 中说明这些系统工具为可选运行时依赖。

---

## 代码迁移规则

## 0. 补全所有子包的 `__init__.py`

当前仓库中大多数 driver 子目录缺少 `__init__.py`（仅 `logic/` 和 `ubertooth/` 已有）。
迁移时必须为每个子包创建 `__init__.py`，否则 `from iotsploit_drivers.xxx import ...` 会失败。

需要创建 `__init__.py` 的目录：

- `iotsploit_drivers/esp32/__init__.py`
- `iotsploit_drivers/socketcan/__init__.py`
- `iotsploit_drivers/ft2232/__init__.py`
- `iotsploit_drivers/greatfet/__init__.py`
- `iotsploit_drivers/jlink/__init__.py`
- `iotsploit_drivers/iotsploit_func_fpga/__init__.py`

exploit 侧同理，所有子目录（`flood_attack/`、`wifi_scan/`、`ip_scan/`、`nmap_scan/`、
`adb_check/`、`serial/`、`demo/`）都需要 `__init__.py`。
`rubber_duck_scripts/` 和 `hydra_cracker/` 是纯数据目录，不需要 `__init__.py`。

## 1. import 路径统一改为包内路径

必须修改的具体文件：

- `drv_greatfet.py` 当前使用：
  `from plugins.devices.greatfet.protocol import get_version_number`
  改为：
  `from iotsploit_drivers.greatfet.protocol import get_version_number`

- 其他使用相对路径的 import 同理：
  `from plugins.devices.logic.protocol import ...`
  改为
  `from iotsploit_drivers.logic.protocol import ...`

## 2. 运行时数据文件统一改为 `importlib.resources`

必须修改：

- `greatfet_rubber_duck.py`
- `hydra_ssh_attack.py`

禁止继续使用：

- `plugins/exploits/...`
- 仓库相对路径
- `cwd` 推导路径

标准写法：

```python
from importlib.resources import files

script_path = files("iotsploit_exploits") / "rubber_duck_scripts" / "windows_payload.txt"
weak_pass_path = files("iotsploit_exploits") / "hydra_cracker" / "weak_pass.txt"
```

---

## Discovery 与 Manager 改造

## Phase 1：兼容阶段

目标：

- 新包可以工作
- 旧 `plugins/` 目录仍然可工作
- 现有环境不会因为一次性切换而中断

## DeviceDriverManager

兼容阶段采用双发现：

1. 先加载 `entry_points`
2. 再扫描 legacy `plugins/devices`
3. 同名驱动以 `entry_point` 为准

建议 `load_plugins()` 逻辑：

```python
def load_plugins(self):
    self._load_entry_point_drivers()
    self._load_legacy_filesystem_drivers()

def _load_entry_point_drivers(self):
    from importlib.metadata import entry_points

    for ep in entry_points(group="iotsploit.device_drivers"):
        if ep.name in self.drivers:
            continue
        try:
            driver_cls = ep.load()
            if isinstance(driver_cls, type) and issubclass(driver_cls, BaseDeviceDriver):
                self.plugins[ep.name] = None
                self.drivers[ep.name] = driver_cls()
                logger.info("Loaded driver from entry_point: %s", ep.name)
        except Exception as e:
            logger.error("Failed to load driver entry_point %s: %s", ep.name, str(e))
```

说明：

- 这里允许 `ep.load()`
- 因为两包制下，`iotsploit-drivers` 已经携带完整依赖闭包
- 当前 `self.drivers`、`driver_states`、`initialize_all_devices()` 等逻辑都依赖 eager-loaded driver 实例，没必要引入额外懒加载复杂度

## ExploitPluginManager

compat 阶段保持 DB 为 SSOT，但 discovery 来源改为“legacy + entry_points 并存”。

建议逻辑：

1. 先扫描 legacy `plugins/exploits`
2. 再扫描 `entry_points`
3. 两边发现的插件名并集写入 `discovered_plugins`
4. 最后 `disable_missing(discovered_plugins)`

entry_point discovery 建议如下：

```python
def _discover_entry_point_plugins(self) -> set[str]:
    from importlib.metadata import entry_points

    found = set()
    for ep in entry_points(group="iotsploit.exploit_plugins"):
        try:
            plugin_cls = ep.load()
            if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, BasePlugin):
                continue

            plugin = plugin_cls()
            info = plugin.get_info() or {}
            module_str, class_name = ep.value.split(":")

            meta = PluginMeta(
                name=str(info.get("Name") or ep.name),
                module_path=f"{module_str}.{class_name}",
                enabled=True,
                description=str(info.get("Description", "") or ""),
                author=str(info.get("Author", "") or ""),
                license=str(info.get("License", "") or ""),
                parameters=info.get("Parameters") if isinstance(info.get("Parameters"), dict) else None,
            )
            self._plugin_repo.upsert(meta)
            found.add(meta.name)
        except Exception as e:
            logger.error("Failed to discover exploit entry_point %s: %s", ep.name, str(e))
    return found
```

关键点：

- DB 中的 `name` 继续使用 `plugin.get_info()["Name"]`
- `module_path` 改写为新的 dotted path
- 这样 `_load_plugin_instance()` 无需新增新的 registry 结构
- pluggy 注册仍在 `_load_plugin_instance()` 的 lazy load 阶段完成（`pm.register()`），discovery 阶段不涉及 pluggy，无需改动

### `module_path` 格式迁移说明

当前 DB 中存储的 `module_path` 格式为 `file:///abs/path/to/plugin.py::ClassName`。
entry_point discovery 写入的新格式为 dotted path，例如 `iotsploit_exploits.flood_attack.flood_attack.FloodAttackPlugin`。

Phase 1 兼容阶段的处理策略：

1. 如果一个插件同时被 legacy 和 entry_point 发现，两次 `upsert()` 都会执行
2. 由于方案建议 **先 legacy 再 entry_points**，最终 DB 中的 `module_path` 会被更新为 dotted path 格式
3. `_load_plugin_instance()` 已有两种格式的分支处理（`file://` 路径 vs dotted import），所以旧记录不会出错
4. 随着 entry_point discovery 覆盖更多插件，DB 记录会逐步迁移到 dotted path 格式，无需额外的 migration 脚本

### 双发现阶段的 `disable_missing()` 注意事项

`disable_missing(discovered_plugins)` 会将 **不在** `discovered_plugins` 集合中的所有插件标记为 disabled。
Phase 1 阶段必须确保 legacy 和 entry_points 两边的发现结果都加入 `discovered_plugins`，否则会误禁插件。

具体风险：如果某环境只安装了 `iotsploit-exploits` 而没有 `plugins/` 目录，
legacy 扫描不到任何插件，entry_point 扫描正常，此时 `discovered_plugins` 只包含 entry_point 发现的插件。
这是正确行为——但如果 entry_point 包尚未包含全部插件，历史遗留的 DB 记录会被 disable。
因此 Phase 1 期间应保留 `plugins/` 目录直到 entry_point 包覆盖完整。

### `module_path` 格式迁移说明

当前 DB 中 exploit 的 `module_path` 使用 `file://` 格式：

```
file:///abs/path/to/plugins/exploits/flood_attack/flood_attack.py::FloodAttackPlugin
```

entry_point discovery 会将其更新为 dotted path 格式：

```
iotsploit_exploits.flood_attack.flood_attack.FloodAttackPlugin
```

Phase 1 阶段无需手动迁移：当 `_discover_entry_point_plugins()` 调用 `upsert()` 时，
会自动按 `name` 匹配已有记录，并将 `module_path` 更新为新格式。
旧格式记录在下次 discovery 时自然被覆盖。

注意：如果同一个插件同时被 legacy 和 entry_point 发现，因为 entry_point 在 legacy 之后执行，
最终 `module_path` 会是 dotted path。这是期望行为，因为 `_load_plugin_instance()` 已经
对两种格式都有分支处理（`file://` 走文件路径 import，dotted 走 `importlib` import）。

### pluggy 集成保持不变

当前 `ExploitPluginManager` 深度使用 `pluggy`（`HookimplMarker`、`pm.register()`、`pm.hook.cleanup()`）。
本次迁移 **不改动 pluggy 集成**。

entry_point discovery 阶段只做 `upsert()` 写入 DB，不调用 `pm.register()`。
pluggy 注册仍在 `_load_plugin_instance()` 懒加载阶段完成，
即当插件被实际执行时才 `pm.register(plugin_instance)`，现有逻辑无需改动。

## DjangoPluginMetaRepository

这是必改项。

当前 `upsert()` 会覆盖用户手动设置的 `enabled` 状态，这与 DB 作为 SSOT 冲突。

目标行为：

- 新插件首次发现：默认 `enabled=True`
- 已存在插件再次发现：只更新 metadata，不覆盖 `enabled`

建议改成：

```python
class DjangoPluginMetaRepository:
    def upsert(self, meta: PluginMeta) -> None:
        try:
            obj, created = Plugin.objects.get_or_create(
                name=meta.name,
                defaults={
                    "description": meta.description or "",
                    "enabled": bool(meta.enabled),
                    "module_path": meta.module_path,
                    "license": meta.license or "",
                    "author": meta.author or "",
                    "parameters": json.dumps(meta.parameters or {}),
                },
            )
            if not created:
                obj.module_path = meta.module_path
                obj.description = meta.description or ""
                obj.license = meta.license or ""
                obj.author = meta.author or ""
                obj.parameters = json.dumps(meta.parameters or {})
                obj.save(update_fields=["module_path", "description", "license", "author", "parameters"])
        except OperationalError:
            return
```

---

## Phase 2：切换为 `entry_points-only`

当以下条件全部满足后，才能切换：

- `iotsploit-drivers` 已包含全部官方 driver
- `iotsploit-exploits` 已包含全部官方 exploit
- root/dev/CI 环境都已通过安装新包使用插件
- Django DB 中 plugin metadata 已完成迁移

切换动作：

1. 删除 `device_manager.py` 中 legacy 文件系统扫描
2. 删除 `exploit_manager.py` 中 legacy 文件系统扫描
3. 删除 `plugins_dir` 参数与默认路径逻辑
4. 删除 `plugins/` 目录约定相关环境变量
5. 删除仓库中的 `plugins/` 目录

---

## Repo-wide 清理项

在删除 `plugins/` 目录前，必须完成以下清理：

- root [`pyproject.toml`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/pyproject.toml)
- [`iotsploit-core/src/iotsploit_core/core/device_manager.py`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/iotsploit-core/src/iotsploit_core/core/device_manager.py)
- [`iotsploit-core/src/iotsploit_core/core/exploit_manager.py`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/iotsploit-core/src/iotsploit_core/core/exploit_manager.py)
- [`iotsploit-django/src/iotsploit_django/config.py`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/iotsploit-django/src/iotsploit_django/config.py)
- [`iotsploit-cli/src/iotsploit_cli/commands/django_commands.py`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/iotsploit-cli/src/iotsploit_cli/commands/django_commands.py)
- [`iotsploit-mcp/src/iotsploit_mcp/composition_root.py`](/home/tkxb/HDD/Projects/zeekr_sat_main-master/iotsploit-mcp/src/iotsploit_mcp/composition_root.py)
- `README.md`
- `CONTRIBUTING.md`
- `iotsploit-core/README.md`
- `iotsploit-mcp/README.md`

root `pyproject.toml` 里 legacy path deps 也要删掉，例如：

```toml
flood_attack = {path = "plugins/exploits/flood_attack", develop = true}
esp32_driver = {path = "plugins/devices/esp32", develop = true}
socketcan_driver = {path = "plugins/devices/socketcan", develop = true}
```

开发环境改为：

```toml
iotsploit-drivers = { path = "iotsploit-drivers", develop = true }
iotsploit-exploits = { path = "iotsploit-exploits", develop = true }
```

---

## 用户安装方式

安装全部官方驱动：

```bash
pip install iotsploit-drivers
```

安装全部官方 exploit：

```bash
pip install iotsploit-exploits
```

安装 CLI：

```bash
pip install iotsploit-cli
```

本地开发：

```bash
pip install -e ./iotsploit-drivers
pip install -e ./iotsploit-exploits
```

说明：

- `iotsploit-cli` 当前仍然硬依赖 `iotsploit-django`
- `iotsploit-drivers` 在当前阶段也建议直接依赖 `iotsploit-django`
- 本方案不尝试在同一轮里把 CLI 或 ESP32 driver 做完全去 Django 化

---

## 发布顺序

1. `iotsploit-core`
2. `iotsploit-django`
3. `iotsploit-platforms`
4. `iotsploit-mcp`
5. `iotsploit-cli`
6. `iotsploit-drivers`
7. `iotsploit-exploits`

---

## 验收标准

## 驱动

- 安装 `iotsploit-drivers` 后，所有官方 driver 都能通过 `entry_points` 被发现
- `DeviceDriverManager.list_drivers()` 返回完整官方 driver 列表
- driver enable/disable 状态在重启后保持
- `initialize_all_devices()` 行为与迁移前一致

## exploit

- 安装 `iotsploit-exploits` 后，所有官方 exploit 都能进入 Django Plugin 表
- 现有 `PluginGroup` / `PluginSequence` 不需要重建即可工作
- 用户禁用某插件后，重启 discovery 不会被重新启用
- API 返回的插件 metadata 仍然完整

## 清理

- 最终代码中不再依赖 `plugins/devices` / `plugins/exploits` 运行时路径
- 删除 `plugins/` 目录后，CLI、Django、MCP 仍能正常运行

---

## 验证步骤

### 冒烟测试脚本

以下脚本应在 clean venv 中执行，验证 entry_points discovery 是否正常工作。

**驱动包验证：**

```python
"""smoke_test_drivers.py — 在 clean venv 中运行"""
from importlib.metadata import entry_points

eps = entry_points(group="iotsploit.device_drivers")
expected = {
    "drv_esp32", "drv_socketcan", "drv_ft2232", "drv_greatfet",
    "drv_jlink", "drv_ubertooth", "drv_logic", "drv_iotsploit_fpga",
}
found = {ep.name for ep in eps}
missing = expected - found
assert not missing, f"Missing driver entry_points: {missing}"

for ep in eps:
    cls = ep.load()
    assert hasattr(cls, 'scan'), f"{ep.name}: loaded class missing scan() method"
    print(f"  OK: {ep.name} -> {ep.value}")

print(f"All {len(expected)} driver entry_points verified.")
```

**Exploit 包验证：**

```python
"""smoke_test_exploits.py — 在 clean venv 中运行"""
from importlib.metadata import entry_points

eps = entry_points(group="iotsploit.exploit_plugins")
expected = {
    "flood_attack", "syn_flood_attack", "wifi_scan", "ip_scan",
    "nmap_scan", "adb_check", "hydra_ssh_attack", "plugin_ssh",
    "picocom_serial_reader", "greatfet_echo", "greatfet_rubber_duck",
    "simple_rubber_duck", "async_sleep_attack", "stream_data_attack",
}
found = {ep.name for ep in eps}
missing = expected - found
assert not missing, f"Missing exploit entry_points: {missing}"

for ep in eps:
    cls = ep.load()
    instance = cls()
    info = instance.get_info()
    assert info and info.get("Name"), f"{ep.name}: get_info() missing Name"
    print(f"  OK: {ep.name} -> {info['Name']}")

print(f"All {len(expected)} exploit entry_points verified.")
```

**数据文件验证：**

```python
"""smoke_test_data_files.py — 验证 wheel 中包含的数据文件"""
from importlib.resources import files

rubber_duck_dir = files("iotsploit_exploits") / "rubber_duck_scripts"
assert (rubber_duck_dir / "windows_payload.txt").is_file(), "windows_payload.txt not found in wheel"
assert (rubber_duck_dir / "linux_infogather.txt").is_file(), "linux_infogather.txt not found in wheel"

hydra_dir = files("iotsploit_exploits") / "hydra_cracker"
assert (hydra_dir / "weak_pass.txt").is_file(), "weak_pass.txt not found in wheel"

print("All data files verified.")
```

### CI 建议

1. **clean venv 安装测试**：在 CI 中创建干净的 virtualenv，仅安装 `iotsploit-core` + `iotsploit-django` + `iotsploit-drivers`，运行 `smoke_test_drivers.py`
2. **exploit 同理**：干净 venv 安装 `iotsploit-core` + `iotsploit-django` + `iotsploit-exploits`，运行 `smoke_test_exploits.py` + `smoke_test_data_files.py`
3. **DB 完整性检查**：启动 Django 后执行 `ExploitPluginManager.load_plugins()`，对比 `Plugin.objects.filter(enabled=True)` 的数量与 entry_points 数量是否一致
4. **PluginGroup 回归**：如有已配置的 PluginGroup，验证 `execute_plugin_group()` 仍能正常编排执行

---

## 最终建议

这次迁移应明确坚持：

**两包制 + 完整依赖闭包 + 分阶段切换到 entry_points**

不要再回到：

- 两包制 + extras
- 两包制 + discovery 禁止 import
- 两包制 + 用占位 metadata 代替真实插件信息

这些做法在当前仓库里都会把复杂度转移到 manager 层，长期成本更高。
