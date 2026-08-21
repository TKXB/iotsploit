# Env_Mgr 重构提案（面向当前架构：Django + 多进程 + Celery + Flutter UI + 插件化）

> **最终目标：完全删除 `iotsploit_django/tools/env_mgr.py` 文件**  
> 替换当前 `iotsploit_django/tools/env_mgr.py` 的"进程内全局字典"设计，使状态在 **多进程**、**多 worker**、**前后端分离** 场景下仍一致、可追踪、可测试，并与 SSOT（DB）对齐。所有 `Env_Mgr` 的使用点都将被新架构替代。

---

## 1. 背景：现状与痛点

### 1.1 `Env_Mgr` 当前做了什么

`Env_Mgr` 本质是一个 **进程内的线程安全 KV**，并额外支持：

- **key 命名空间**：自动加 `__SAT_ENV__` 前缀
- **子进程注入**：`fork_sat_env()` 把 KV 合并到 `os.environ.copy()`，用于 `subprocess`
- **脚本回传**：`read_sat_env_from_log()` 从日志中解析 `__SAT_ENV__EXPORT:__SAT_ENV__X=Y` 回灌 KV
- **车辆上下文切换**：`update_vehicle_env(vehicle)` 写入 `vehicle.export_env()`，并存一个 Python 对象 `VEHICLE_PROFILE`

### 1.2 为什么它不适合当前架构

| 问题 | 在你项目里会发生什么 |
|------|----------------------|
| **进程内存不共享** | Django 多 worker / Celery worker / 子进程脚本 各有一份状态，必然分叉 |
| **UI 无法对接** | Flutter 不能读写 Python 内存，`SAT_NEED_UI/SAT_UI_RESULT` 无真实跨进程通道 |
| **状态混杂** | 同一容器里既有长期配置（VIN、PIN），又有临时态（AUDIT_START_TIME），还塞对象（VEHICLE_PROFILE） |
| **不可治理** | 无 schema、无版本、无审计、无 TTL，定位问题困难 |

---

## 2. 重构目标（可验收，DB 重路线）

**最终目标：完全删除 `iotsploit_django/tools/env_mgr.py` 文件**

1. **SSOT 明确**：长期配置（车辆信息、插件启用、默认参数）以 **DB** 为单一事实来源
2. **运行态也可追踪**：关键运行态（审计会话、UI 交互、脚本执行记录、产物索引）尽量 **落库可审计**
3. **跨进程一致**：跨进程共享不再依赖进程内 dict；优先 DB，必要时可叠加 **Redis/Cache** 作为加速层（非权威）
4. **任务级上下文显式化**：插件/工具尽量通过入参（target dict 或 target_id）获取所需信息
5. **对外接口统一**：提供一个 `ContextStore` 抽象，调用方不关心底层是 DB/Cache
6. **完全移除 `Env_Mgr`**：所有 `Env_Mgr.Instance()` 调用替换为 Repository/Builder，最终删除 `env_mgr.py` 文件

### 2.1 过渡期依赖约束（已更新）

在 `env_mgr.py` 仍存在的过渡期内：

- **只能依赖 `iotsploit_core` 的 utils**（例如 `iotsploit_core.utils.exceptions`）
- **不得再依赖 `iotsploit_django.tools.sat_utils`**（该兼容层已基于 core utils 重构）

> 目的：确保剩余遗留代码即便暂时还在 Django 项目中，也遵循 “core 在内、Django 在外” 的依赖方向。

---

## 3. 推荐新架构（DB 重）：配置 + 运行态统一落库，缓存可选

### 3.1 状态分层（DB 优先）

| 状态类型 | 举例 | 推荐存储 | 特性 |
|---------|------|----------|------|
| **配置/长期状态（SSOT）** | 车辆 VIN/PIN、车型参数、热点信息、插件启用状态 | **DB** | 可审计、可回滚、可管理 |
| **运行态/会话状态（可审计）** | audit 会话、UI 输入请求/响应、脚本执行记录、当前 active vehicle（如需要） | **DB（首选）** | 可追踪、可重放、可恢复 |
| **缓存/加速层（可选）** | 热点密码缓存、UI request 的快速取回 | **Redis / Django cache（可选）** | TTL、降压、非权威 |
| **任务上下文（一次执行）** | 本次 execute 的 target/vehicle 参数 | **函数入参/Context 对象** | 可测试、无隐式依赖 |

### 3.2 新的抽象接口（建议，DB 重）

- **`TargetRepository`（DB）**：读写目标配置（车辆/设备的 VIN、PIN、型号、热点信息等）
- **`SessionRepository`（DB）**：审计/任务会话（task_id、log_dir、active_vehicle 等）
- **`UserInputRepository`（DB）**：UI 输入请求/响应（request_id、payload、status、created_at）
- **`ScriptRunRepository`（DB）**：脚本执行记录（cmd、env_snapshot、stdout/stderr 摘要、产物索引）
- **`ScriptEnvBuilder`**：从 DB（+ 可选 cache）组装“脚本需要的 env dict”

> 关键原则：不要再把 Python 对象（如 `VEHICLE_PROFILE`）塞进全局 store。

### 3.3 目录与文件路径清单（新增）

**core（接口与 builder）：**

- `iotsploit-core/src/iotsploit_core/ports/context_repositories.py`
  - TargetRepository / SessionRepository / UserInputRepository / ScriptRunRepository
- `iotsploit-core/src/iotsploit_core/ports/script_env_builder.py`

**Django adapter（实现）：**

- `iotsploit-django/src/iotsploit_django/adapters/context_repositories.py`
  - TargetRepository / SessionRepository / UserInputRepository / ScriptRunRepository
- `iotsploit-django/src/iotsploit_django/adapters/script_env_builder.py`

---

## 4. 结合现有 key 的“去向规划”（建议映射表）

下面是根据仓库检索到的常见 key，给出建议的归属与迁移优先级。

### 4.1 交互模式与 UI 交互

| key | 当前用途 | 建议替代 | 优先级 |
|-----|----------|----------|--------|
| `SAT_RUN_IN_SHELL` | 决定 `Input_Mgr` 走 CLI 还是 UI | **配置项/启动参数**（env var 或 Django settings），不要存 runtime KV | P0 |
| `SAT_NEED_UI` / `SAT_UI_RESULT` | 试图做 UI 请求/响应 | 改为 **WebSocket/HTTP + DB** 的 request/response（带 request_id，落库可审计；可选 Redis 缓存） | P0 |

### 4.2 车辆/车型参数

| key 前缀 | 当前用途 | 建议替代 | 优先级 |
|---------|----------|----------|--------|
| `__SAT_ENV__VehicleInfo_*` | VIN、PIN、设备标识等 | DB（VehicleInfo 表/字段）+ 执行时传 `target_id/target_dict` | P0 |
| `__SAT_ENV__VehicleModel_*` | 车型 IP、SSH 用户等 | DB（VehicleModel/VehicleProfile） | P0 |
| `VehicleInfo_TCAM_WIFI_SSID/PASSWD` 等 | 热点缓存、避免重复输入 | **DB（车辆配置）**（可选 Redis 作为读取缓存） | P1 |
| `VEHICLE_PROFILE`（Python 对象） | 运行时写入对象用于后续调用 `save_wifi_info` | 改为 `target_id` + repo 操作（或只存 dict） | P0 |

### 4.3 日志/审计运行态

| key | 当前用途 | 建议替代 | 优先级 |
|-----|----------|----------|--------|
| `__SAT_ENV__LOG_DIR` | 脚本/模块共享日志目录 | **DB（会话表：task_id -> log_dir）**；执行时也可作为上下文参数传递 | P1 |
| `AUDIT_START_TIME` / `AUDIT_STOP_TIME` | 报告/审计生命周期 | **DB（审计会话表）**（可选 Redis 缓存状态） | P1 |
| `__SAT_ENV__DHU_TMP_DIR` | 默认临时目录 | 配置项（settings/env） | P2 |
| `__SAT_ENV__TestResut_PNG` | 测试结果图片路径 | 归到报告产物管理（DB/文件服务） | P2 |

### 4.4 辅助方法与插件状态（审查补充）

| 方法/key | 当前用途 | 建议替代 | 优先级 |
|----------|----------|----------|--------|
| `explain_env_in_list()` | 把 `$VAR` 替换成 env 值（用于 pass_condition 校验） | 迁移到 `ScriptEnvBuilder.resolve_vars(var_list, ctx)` 从 DB/context 取值 | P1 |
| `save_to_file()` / `load_from_file()` | 把 env 持久化到 JSON 文件 | **删除**（DB 已持久化） | P2 |
| 插件临时状态（如 `TCAM_AP_SCAN_IP_LIST`、`DEL_ROUTES_CMDS`） | 插件运行时缓存 | 改为 **插件实例属性** 或 **SessionRepository（DB）** | P1 |

> ⚠️ **插件迁移提醒**：`ip_scan.py` 等插件直接 `self.env_mgr = Env_Mgr.Instance()`，迁移时需要改为通过 `execute(target, parameters, context)` 注入 `SessionContext`，插件不再直接访问全局 store。

---

## TODO List（可直接执行）

### 阶段 0：冻结规范（1 天）

- [ ] **冻结状态分类**：明确哪些是配置、哪些是运行态、哪些是任务上下文
- [ ] **冻结 key schema**：禁止继续随意新增 `Env_Mgr` key

### 阶段 1：建立替代组件（DB 优先，2~6 天）

- [ ] **新增 `ContextRepositories`**（单文件）：集中定义 Target/Session/UserInput/ScriptRun 四个 Repository
- [ ] **新增 `ScriptEnvBuilder`**：从 DB 生成脚本需要的 env dict（可选 cache 加速）

### 阶段 2：优先迁移 P0（3~7 天）

- [ ] **迁移 `SAT_RUN_IN_SHELL`**：改为启动参数（CLI/Django 入口设定）
- [ ] **迁移车辆 VIN/PIN/车型参数**：`doip_mgr.py`、`vehicle_utils.py` 改为从 repo/入参获取
- [ ] **移除 `VEHICLE_PROFILE` 全局对象**：改为 repo 更新（例如保存 WiFi 信息）

### 阶段 3：脚本执行链路迁移（3~7 天）

- [ ] **替换 `fork_sat_env()`**：`bash_script_engine.py` 改用 `ScriptEnvBuilder.build(task_ctx)` 输出 env
- [ ] **替换脚本回传机制**：回传写入 DB（`ScriptRun/Session`），并优先结构化 JSON（不靠日志解析）

### 阶段 4：完全移除 `env_mgr.py`（最终目标）

- [ ] **验证所有 `Env_Mgr` 依赖已移除**：使用 `grep -r "Env_Mgr\|env_mgr"` 确认无残留引用
- [ ] **删除 `iotsploit_django/tools/env_mgr.py` 文件**
- [ ] **删除所有 `from iotsploit_django.tools.env_mgr import Env_Mgr` 导入语句**

### MVP 补充：保留 `$VAR` 替换能力

- [ ] **迁移 `explain_env_in_list()`**：搬到 `ScriptEnvBuilder.resolve_vars(var_list, ctx)`，保留 `$VAR` 替换能力

---

## 5. 迁移策略（DB 重；你“不考虑兼容”时可直接破坏式切换）

### 5.1 阶段 0：冻结规范（1 天）

- 冻结“哪些数据算配置、哪些算运行态、哪些是任务上下文”
- 冻结 key schema：禁止随意新增 `Env_Mgr` key

### 5.2 阶段 1：建立替代组件（DB 优先，2~6 天）

- 新增 `ContextRepositories`（单文件）：集中定义 Target/Session/UserInput/ScriptRun 四个 Repository
- 新增 `ScriptEnvBuilder`（从 DB 生成 env dict；可选 cache 加速）

### 5.3 阶段 2：优先迁移 P0（3~7 天）

- **`SAT_RUN_IN_SHELL`**：改为启动参数（CLI 入口设定、Django 入口设定）
- **车辆 VIN/PIN/车型参数**：`doip_mgr.py` / `vehicle_utils.py` 改为从 repo 获取或从入参获取
- **移除 `VEHICLE_PROFILE` 全局对象**：改为 repo 更新（例如保存 WiFi 信息）

### 5.4 阶段 3：脚本执行链路迁移（DB 记录审计，3~7 天）

- `bash_script_engine.py` 不再使用 `Env_Mgr.fork_sat_env()`，改用 `ScriptEnvBuilder.build(task_ctx)` 输出 env
- 保留“脚本回传 env”的能力：但回传目标改为 **DB（ScriptRun/Session 记录）**，并优先使用结构化 JSON（不要靠日志解析）

### 5.5 阶段 4：完全移除 `env_mgr.py`（最终目标）

**目标：删除 `iotsploit_django/tools/env_mgr.py` 文件，所有功能由新架构替代**

#### 5.5.1 所有 `Env_Mgr` 使用点的替换清单

根据代码库扫描，以下文件需要替换 `Env_Mgr` 的使用：

| 文件 | 当前用法 | 替换方案 | 状态 |
|------|---------|---------|------|
| `input_mgr.py` | `Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")`<br>`Env_Mgr.Instance().set("SAT_NEED_UI")`<br>`Env_Mgr.Instance().query("SAT_UI_RESULT")` | 改为 Django settings/env var<br>改为 `UserInputRepository` | ⬜ |
| `bash_script_engine.py` | `Env_Mgr.Instance().fork_sat_env()`<br>`Env_Mgr.Instance().read_sat_env_from_log()`<br>`Env_Mgr.Instance().explain_env_in_list()` | 改为 `ScriptEnvBuilder.build(ctx)`<br>改为 `ScriptRunRepository`<br>改为 `ScriptEnvBuilder.resolve_vars()` | ⬜ |
| `python_submodule_engine.py` | `Env_Mgr.Instance().explain_env_in_list()` | 改为 `ScriptEnvBuilder.resolve_vars()` | ⬜ |
| `vehicle_utils.py` | `Env_Mgr.Instance().get("VehicleInfo_*")`<br>`Env_Mgr.Instance().get("VEHICLE_PROFILE")`<br>`Env_Mgr.Instance().update_vehicle_env()` | 改为 `TargetRepository.get_vehicle_pin()`<br>改为 `target_id` + Repository<br>改为 Repository 方法 | ⬜ |
| `doip_mgr.py` | `Env_Mgr.Instance().get("VehicleInfo_VIN")`<br>`Env_Mgr.Instance().get("VehicleInfo_DHU_PIN")` | 改为 `TargetRepository.get_vehicle_pin()` | ⬜ |
| `report_mgr.py` | `Env_Mgr.Instance().get("LOG_DIR")`<br>`Env_Mgr.Instance().set("AUDIT_START_TIME")` | 改为 `SessionRepository.get_session()`<br>改为 `SessionRepository.create_session()` | ⬜ |
| `device_views.py` | `Env_Mgr.Instance().set("SAT_RUN_IN_SHELL")` | 改为 Django settings | ⬜ |
| `console.py` | `Env_Mgr.Instance().set("SAT_RUN_IN_SHELL")` | 改为环境变量或启动参数 | ⬜ |
| `ip_scan.py` (插件) | `self.env_mgr = Env_Mgr.Instance()`<br>`self.env_mgr.set/get()` | 改为 `SessionContext` 注入 | ⬜ |
| `wifi_mgr.py` | 可能使用 `VEHICLE_PROFILE` | 改为 `TargetRepository.save_wifi_info()` | ⬜ |

#### 5.5.2 替换代码示例（确保完全移除依赖）

**示例 1：`input_mgr.py` - 移除所有 `Env_Mgr` 引用**

```python
# 旧代码（需要删除）
from iotsploit_django.tools.env_mgr import Env_Mgr  # ❌ 删除这行

def confirm(self, title: str):
    run_in_shell = Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")  # ❌ 删除
    if run_in_shell:
        # ...
    else:
        Env_Mgr.Instance().set("SAT_NEED_UI", json.dumps({...}))  # ❌ 删除

# 新代码（完全移除 Env_Mgr 依赖）
from django.conf import settings  # ✅ 新导入
from iotsploit_django.repositories.user_input_repository import UserInputRepository  # ✅ 新导入

def confirm(self, title: str, task_id: str):  # ✅ 显式传入 task_id
    run_in_shell = getattr(settings, 'SAT_RUN_IN_SHELL', os.getenv('SAT_RUN_IN_SHELL', 'false'))  # ✅ 从配置读取
    if run_in_shell == 'true':
        # ...
    else:
        user_input_repo = UserInputRepository()  # ✅ 使用 Repository
        request_id = user_input_repo.create_request(task_id, {"prompt": title})
```

**示例 2：`bash_script_engine.py` - 移除所有 `Env_Mgr` 引用**

```python
# 旧代码（需要删除）
from iotsploit_django.tools.env_mgr import Env_Mgr  # ❌ 删除这行

def exec(self, test_step):
    process = subprocess.Popen(
        cmd_list,
        env=Env_Mgr.Instance().fork_sat_env(),  # ❌ 删除
        encoding="utf-8"
    )
    exec_result = process.stdout.read()
    Env_Mgr.Instance().read_sat_env_from_log(exec_result)  # ❌ 删除
    predefined_list = Env_Mgr.Instance().explain_env_in_list(var_list)  # ❌ 删除

# 新代码（完全移除 Env_Mgr 依赖）
from iotsploit_django.tools.script_env_builder import ScriptEnvBuilder, TaskContext  # ✅ 新导入
from iotsploit_django.repositories.script_run_repository import ScriptRunRepository  # ✅ 新导入

def exec(self, test_step, task_id: str, target_id: Optional[str] = None):  # ✅ 显式参数
    ctx = TaskContext(task_id=task_id, target_id=target_id)
    env_builder = ScriptEnvBuilder()
    env_dict = env_builder.build(ctx)  # ✅ 替代 fork_sat_env()
    
    script_repo = ScriptRunRepository()
    run_record = script_repo.create_run(task_id, test_step.script_path, cmd, env_dict)
    
    process = subprocess.Popen(
        cmd_list,
        env=env_dict,  # ✅ 使用新方法
        encoding="utf-8"
    )
    exec_result = process.stdout.read()
    
    # ✅ 替代 read_sat_env_from_log()：解析并写入 DB
    exported_env = self._parse_script_output(exec_result)
    script_repo.update_run_result(run_record.id, return_code, stdout, stderr, exported_env)
    
    # ✅ 替代 explain_env_in_list()
    resolved_list = env_builder.resolve_vars(var_list, ctx)
```

**示例 3：`vehicle_utils.py` - 移除 `VEHICLE_PROFILE` 对象依赖**

```python
# 旧代码（需要删除）
from iotsploit_django.tools.env_mgr import Env_Mgr  # ❌ 删除这行

def get_current_vehicle():
    return Env_Mgr.Instance().get("VEHICLE_PROFILE")  # ❌ 删除（返回 Python 对象）

def save_wifi_info(ssid: str, password: str):
    vehicle = Env_Mgr.Instance().get("VEHICLE_PROFILE")  # ❌ 删除
    vehicle.save_wifi_info(ssid, password)  # ❌ 删除

# 新代码（完全移除 Env_Mgr 依赖）
from iotsploit_django.repositories.target_repository import TargetRepository  # ✅ 新导入

def get_current_vehicle(target_id: str):  # ✅ 显式传入 target_id
    target_repo = TargetRepository()
    return target_repo.get_vehicle_pin(target_id)  # ✅ 返回 DB Model

def save_wifi_info(target_id: str, ssid: str, password: str):  # ✅ 显式传入 target_id
    target_repo = TargetRepository()
    target_repo.save_wifi_info(target_id, ssid, password)  # ✅ 直接调用 Repository
```

#### 5.5.3 验证和删除步骤

**步骤 1：验证所有依赖已替换**

```bash
# 在项目根目录执行，确认无残留引用
grep -r "Env_Mgr\|env_mgr\|from.*env_mgr import" \
  --exclude-dir=__pycache__ \
  --exclude-dir=.git \
  --exclude="ENV_MGR_REFACTORING_PROPOSAL.md" \
  iotsploit-django/

# 预期输出：只有 env_mgr.py 文件本身，无其他引用
```

**步骤 2：运行测试确保功能正常**

```bash
# 运行所有测试，确保迁移后功能正常
python manage.py test
# 或
pytest tests/
```

**步骤 3：删除 `env_mgr.py` 文件**

```bash
# 确认无引用后，删除文件
rm iotsploit-django/src/iotsploit_django/tools/env_mgr.py
```

**步骤 4：最终验证**

```bash
# 再次检查，确认文件已删除且无引用
grep -r "env_mgr" --exclude-dir=__pycache__ --exclude-dir=.git iotsploit-django/
# 预期输出：无任何结果（或只有文档中的说明）
```

---

## 6. 代码审查验证结论

### 6.1 DB 重路线可行性证据

| 证据 | 来源 | 说明 |
|------|------|------|
| ✅ DB Model 已有 `export_env()` 模式 | `PassCondition_Model.py` | 已有从 DB 字段生成 `__SAT_ENV__PassCondition_*` 的能力 |
| ✅ 所有 `VehicleInfo_*`/`VehicleModel_*` 来源都是 DB | `vehicle_utils.py`, `doip_mgr.py` | 这些 key 本质上是 DB Model 字段的缓存，可直接查 DB |
| ✅ `VEHICLE_PROFILE` 是 DB Model 实例 | `vehicle_utils.py` | 迁移后改为 `VehicleProfile.objects.get(pk=id)` 即可 |

### 6.2 调用链覆盖检查

| 文件 | Env_Mgr 调用数 | 覆盖状态 |
|------|---------------|---------|
| `report_mgr.py` | 5 | ✅ 已覆盖（LOG_DIR、AUDIT_*、TestResut_PNG） |
| `vehicle_utils.py` | 20 | ✅ 已覆盖（VehicleInfo_*、VehicleModel_*、VEHICLE_PROFILE） |
| `doip_mgr.py` | 6 | ✅ 已覆盖（VIN、PIN） |
| `bash_script_engine.py` | 4 | ✅ 已覆盖（fork_sat_env、explain_env_in_list、read_sat_env_from_log） |
| `python_submodule_engine.py` | 2 | ✅ 已覆盖（explain_env_in_list） |
| `input_mgr.py` | 3 | ✅ 已覆盖（SAT_RUN_IN_SHELL、SAT_NEED_UI、SAT_UI_RESULT） |
| `device_views.py` | 1 | ✅ 已覆盖（SAT_RUN_IN_SHELL） |
| `console.py` | 1 | ✅ 已覆盖（SAT_RUN_IN_SHELL） |
| `ip_scan.py`（插件） | 4 | ✅ 已覆盖（4.4 节补充） |

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 迁移期间行为不一致 | 线上故障 | P0 先做"双写+校验"，一段时间后切主读 |
| DB 压力上升（DB 重） | 性能下降 | 关键表加索引（request_id/task_id/created_at），批量写入；热点读可用 cache（可选） |
| 脚本依赖环境变量太多 | 脚本执行失败 | ScriptEnvBuilder 先完全复刻现有 env 输出，再逐步减少 |
| 调用方依赖隐式全局状态 | 难定位 | 给每个入口补充 `task_id`/`target_id`/`target` 入参，逐步显式化 |
| 插件直接依赖 Env_Mgr | 插件迁移困难 | 修改插件 `execute()` 签名，注入 `SessionContext`；提供迁移指南 |

---

## 8. 最小落地（MVP）建议

如果你想最快看到收益，建议按这个顺序：

1. **把 `VEHICLE_PROFILE` 去掉**（改为 target_id + repo）  
2. **把 VIN/PIN 等 VehicleInfo 从 `Env_Mgr.get()` 改为 DB 查询**（DoIP/车辆相关逻辑立刻变稳定）  
3. **把 `SAT_RUN_IN_SHELL` 改为配置项**（避免运行时被覆盖）  
4. **替换 `fork_sat_env()`：用 ScriptEnvBuilder 从 DB 组装 env**（脚本链路跨进程一致，且可审计）  
5. **把 `explain_env_in_list()` 迁移到 ScriptEnvBuilder**（保留 `$VAR` 替换能力）

---

## 9. 新架构完整使用示例（替代 `Env_Mgr` 的所有功能）

### 9.1 功能映射表：`Env_Mgr` → 新架构

| `Env_Mgr` 方法/功能 | 新架构替代方案 | 代码示例 |
|---------------------|---------------|---------|
| `Env_Mgr.Instance().get("VehicleInfo_VIN")` | `TargetRepository().get_vehicle_pin(target_id).VIN` | 见下方 |
| `Env_Mgr.Instance().set("VEHICLE_PROFILE", obj)` | 不再需要，改为显式传入 `target_id` | 见下方 |
| `Env_Mgr.Instance().fork_sat_env()` | `ScriptEnvBuilder().build(ctx)` | 见下方 |
| `Env_Mgr.Instance().explain_env_in_list()` | `ScriptEnvBuilder().resolve_vars(var_list, ctx)` | 见下方 |
| `Env_Mgr.Instance().read_sat_env_from_log()` | `ScriptRunRepository().update_run_result()` | 见下方 |
| `Env_Mgr.Instance().update_vehicle_env(vehicle)` | `TargetRepository().get_vehicle_env_dict(target_id)` | 见下方 |
| `Env_Mgr.Instance().get("SAT_RUN_IN_SHELL")` | `settings.SAT_RUN_IN_SHELL` 或 `os.getenv()` | 见下方 |
| `Env_Mgr.Instance().set("SAT_NEED_UI")` | `UserInputRepository().create_request()` | 见下方 |

### 9.2 完整迁移示例：一个典型的脚本执行流程

**旧代码（使用 `Env_Mgr`，需要完全删除）：**

```python
# ❌ 旧代码 - 所有这些都是需要删除的
from iotsploit_django.tools.env_mgr import Env_Mgr

# 1. 设置车辆信息
vehicle = VehiclePIN.objects.get(VIN="xxx")
Env_Mgr.Instance().update_vehicle_env(vehicle)  # ❌ 删除

# 2. 获取车辆信息
vin = Env_Mgr.Instance().get("VehicleInfo_VIN")  # ❌ 删除
pin = Env_Mgr.Instance().get("VehicleInfo_DHU_PIN")  # ❌ 删除

# 3. 执行脚本
env_dict = Env_Mgr.Instance().fork_sat_env()  # ❌ 删除
process = subprocess.Popen(["bash", "script.sh"], env=env_dict)

# 4. 解析脚本输出
Env_Mgr.Instance().read_sat_env_from_log(output)  # ❌ 删除

# 5. 变量替换
resolved = Env_Mgr.Instance().explain_env_in_list(["$VehicleInfo_VIN"])  # ❌ 删除
```

**新代码（完全移除 `Env_Mgr` 依赖）：**

```python
# ✅ 新代码 - 完全不需要导入 env_mgr
from iotsploit_django.repositories.target_repository import TargetRepository
from iotsploit_django.tools.script_env_builder import ScriptEnvBuilder, TaskContext
from iotsploit_django.repositories.script_run_repository import ScriptRunRepository

# 1. 获取车辆信息（从 DB，不再需要"设置"步骤）
target_repo = TargetRepository()
vehicle_pin = target_repo.get_vehicle_pin("target_123")  # ✅ 直接从 DB 获取
vin = vehicle_pin.VIN  # ✅ 使用 DB Model 属性
pin = vehicle_pin.DHU_PIN

# 2. 创建任务上下文（显式传递）
ctx = TaskContext(task_id="task_456", target_id="target_123")  # ✅ 显式上下文

# 3. 构建环境变量（从 DB 组装）
env_builder = ScriptEnvBuilder()
env_dict = env_builder.build(ctx)  # ✅ 替代 fork_sat_env()
process = subprocess.Popen(["bash", "script.sh"], env=env_dict)

# 4. 记录脚本执行结果（写入 DB，不再从日志解析）
script_repo = ScriptRunRepository()
run_record = script_repo.create_run(
    task_id=ctx.task_id,
    script_path="script.sh",
    cmd="bash script.sh",
    env_snapshot=env_dict  # ✅ 保存环境变量快照
)
# 解析输出并更新记录
exported_env = parse_script_output(process.stdout)
script_repo.update_run_result(
    run_id=run_record.id,
    return_code=process.returncode,
    stdout=process.stdout,
    stderr=process.stderr,
    artifacts=exported_env.get("artifacts", [])
)

# 5. 变量替换（从 DB/context 获取）
resolved = env_builder.resolve_vars(["$__SAT_ENV__VehicleInfo_VIN"], ctx)  # ✅ 替代 explain_env_in_list()
# 输出: ["1HGCM82633A123456"]
```

### 9.3 验证清单：确保可以删除 `env_mgr.py`

在删除 `env_mgr.py` 之前，确认以下所有项已完成：

- [ ] ✅ 所有 `from iotsploit_django.tools.env_mgr import Env_Mgr` 已删除
- [ ] ✅ 所有 `Env_Mgr.Instance()` 调用已替换为 Repository/Builder
- [ ] ✅ 所有函数签名已添加显式参数（`task_id`, `target_id` 等）
- [ ] ✅ `grep -r "Env_Mgr\|env_mgr"` 只返回 `env_mgr.py` 文件本身
- [ ] ✅ 所有测试通过
- [ ] ✅ 功能验证：脚本执行、车辆信息获取、UI 交互均正常

**完成以上检查后，可以安全删除 `env_mgr.py` 文件。**

---

## 10. 下一步行动建议

基于代码审查，提案覆盖了**所有 10 个调用 Env_Mgr 的文件**和**全部关键方法**，DB 重路线可行。

---

## TODO（快速清单）

- [ ] 定义 ports 接口签名与核心数据结构（core）
- [ ] 完成 Django adapters 的最小可用实现
- [ ] 迁移 `input_mgr.py` 与 UI 交互链路（SAT_NEED_UI/SAT_UI_RESULT）
- [ ] 迁移脚本执行链路（env 构建 + 回传落库）
- [ ] 迁移车辆信息读写（VIN/PIN/车型参数）
- [ ] 移除所有 `Env_Mgr` 引用并删除 `env_mgr.py`

### 如需继续推进，请确认：

1. **车辆信息的 DB 模型名称**：`VehicleProfile`？`VehicleInfo`？（我可以直接生成 Repository 代码）
2. **UI 输入（Flutter）走 WebSocket 还是 HTTP？**（两者都能落库；WS 体验更好）
3. **是否需要我生成 ScriptEnvBuilder 的骨架代码？**（包含 `build()` 和 `resolve_vars()` 方法）  
