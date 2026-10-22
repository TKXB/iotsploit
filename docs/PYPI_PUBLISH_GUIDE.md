# PyPI 发布指南

本文档记录当前仓库的 PyPI 发布状态，以及后续子包的标准发布流程。

---

## 当前状态

截至本次 packaging refactor：

| 包名 | 路径 | 状态 | 说明 |
|------|------|------|------|
| `iotsploit-core` | `iotsploit-core/` | ✅ 已发布 | 已存在于 PyPI，后续只做版本更新 |
| `iotsploit-django` | `iotsploit-django/` | ✅ 已发布 | 已存在于 PyPI，后续只做版本更新 |
| `iotsploit-cli` | `iotsploit-cli/` | 可按需发布 | CLI 包，提供 `iotsploit` console script |
| `iotsploit-drivers` | `iotsploit-drivers/` | ⏳ 待发布 | 新增官方驱动合集包 |
| `iotsploit-exploits` | `iotsploit-exploits/` | ⏳ 待发布 | 新增官方 exploit 合集包 |
| `iotsploit-platforms` | `iotsploit-platforms/` | 可按需发布 | 非本次 refactor 主目标 |
| `iotsploit-mcp` | `iotsploit-mcp/` | 可按需发布 | 非本次 refactor 主目标 |
| `sat-toolkit`（主包） | 仓库根目录 | ❌ 不发布 | `package-mode = false` |

当前发布重点不再是 `iotsploit-core` / `iotsploit-django` 首发，而是：

1. 发布 `iotsploit-drivers`
2. 发布 `iotsploit-exploits`
3. 如有 CLI 分发需求，发布 `iotsploit-cli`
4. 如后续有改动，再对 `iotsploit-core` / `iotsploit-django` 做版本升级发布

---

## 推荐发布顺序

由于 `iotsploit-drivers` 和 `iotsploit-exploits` 都依赖：

- `iotsploit-core`
- `iotsploit-django`

而 `iotsploit-cli` 也依赖：

- `iotsploit-core`
- `iotsploit-django`

而这两个基础包已经发布，所以当前推荐顺序为：

1. 确认 `iotsploit-core` 当前 PyPI 版本满足依赖
2. 确认 `iotsploit-django` 当前 PyPI 版本满足依赖
3. 发布 `iotsploit-drivers`
4. 发布 `iotsploit-exploits`
5. 如需要 PyPI 安装 CLI，再发布 `iotsploit-cli`

`iotsploit-drivers` 与 `iotsploit-exploits` 之间没有直接依赖，可以先后任意，但通常建议先发 `drivers`，再发 `exploits`。`iotsploit-cli` 也不依赖这两个包本身，所以可以独立发布。

---

## Step 1：确认 PyPI 账号与 Token

- 正式环境：<https://pypi.org/account/register/>
- 测试环境：<https://test.pypi.org/account/register/>

创建 API Token：

- 首次可选 `Entire account`
- 后续更推荐按包名单独建 token

Poetry 配置示例：

```bash
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry config pypi-token.testpypi pypi-xxxxxxxxxxxxxxxx
poetry config pypi-token.pypi pypi-xxxxxxxxxxxxxxxx
```

---

## Step 2：发布前检查

以待发布包目录为工作目录，例如：

```bash
cd iotsploit-drivers
```

或：

```bash
cd iotsploit-exploits
```

或：

```bash
cd iotsploit-cli
```

发布前至少检查以下内容：

1. `pyproject.toml` 中 `name` / `version` / `readme` / `license` 正确
2. 依赖都已经能从 PyPI 安装
3. `entry_points` 配置完整
4. wheel/sdist 包含必要源码与数据文件
5. README 中写清系统级依赖要求

对本次 refactor，尤其要确认：

- `iotsploit-drivers` 依赖 `iotsploit-core` 和 `iotsploit-django`
- `iotsploit-exploits` 依赖 `iotsploit-core` 和 `iotsploit-django`
- `iotsploit-cli` 依赖 `iotsploit-core` 和 `iotsploit-django`
- `iotsploit-cli` 的 console script 已配置：
  - `iotsploit = "iotsploit_cli.console:main"`
- `iotsploit-exploits` 的数据文件已打入包：
  - `rubber_duck_scripts/*.txt`
  - `hydra_cracker/*.txt`

---

## Step 3：确认包名与版本

检查包名是否已存在、当前版本是否需要提升：

```bash
pip index versions iotsploit-drivers
pip index versions iotsploit-exploits
pip index versions iotsploit-cli
pip index versions iotsploit-core
pip index versions iotsploit-django
```

如果是首次发布 `iotsploit-drivers` / `iotsploit-exploits` / `iotsploit-cli`，重点看包名是否冲突。

如果是更新 `iotsploit-core` / `iotsploit-django`，重点看版本号是否已经存在。

版本升级示例：

```bash
poetry version patch
poetry version minor
poetry version major
```

---

## Step 4：本地构建

在目标包目录内执行：

```bash
poetry build
```

构建后应生成：

```text
dist/
├── <package>-<version>.tar.gz
└── <package>-<version>-py3-none-any.whl
```

建议每次发布前先清一次旧产物：

```bash
rm -rf dist/
poetry build
```

---

## Step 5：本地安装验证

发布前至少验证 wheel 可以安装，并且关键导入正常。

推荐在干净虚拟环境中：

```bash
python -m venv .venv-publish-test
source .venv-publish-test/bin/activate
pip install --upgrade pip
```

然后安装构建产物：

```bash
pip install dist/*.whl
```

对本次 packaging refactor，推荐最少执行：

```bash
poetry run python smoke_test_drivers.py
poetry run python smoke_test_exploits.py
poetry run python smoke_test_data_files.py
```

如果发布 `iotsploit-cli`，额外验证：

```bash
cd iotsploit-cli
poetry build
pip install dist/*.whl
iotsploit --help
```

如果要验证真正的已安装 entry points，建议在干净环境中执行：

```bash
pip install ./iotsploit-core ./iotsploit-django ./iotsploit-drivers ./iotsploit-exploits ./iotsploit-cli
python smoke_test_drivers.py
python smoke_test_exploits.py
python smoke_test_data_files.py
iotsploit --help
```

---

## Step 6：先发 TestPyPI

以 `iotsploit-drivers` 为例：

```bash
cd iotsploit-drivers
poetry publish -r testpypi
```

`iotsploit-exploits` 同理：

```bash
cd iotsploit-exploits
poetry publish -r testpypi
```

`iotsploit-cli` 同理：

```bash
cd iotsploit-cli
poetry publish -r testpypi
```

从 TestPyPI 安装 `iotsploit-cli`（依赖仍从正式 PyPI 解析）：

```bash
pip install \
  --index-url https://pypi.org/simple/ \
  --extra-index-url https://test.pypi.org/simple/ \
  iotsploit-cli==0.0.4
```

如果使用 `twine`：

```bash
pip install twine
twine upload --repository testpypi dist/*
```

发布后验证：

- 包页面是否可访问
- 元数据是否正确
- 安装是否成功
- entry points 是否能被发现

---

## Step 7：发布正式 PyPI

TestPyPI 验证通过后，在对应包目录执行：

```bash
poetry publish
```

或：

```bash
twine upload dist/*
```

对本次 refactor，建议分别发布：

```bash
cd iotsploit-drivers
poetry publish

cd ../iotsploit-exploits
poetry publish

cd ../iotsploit-cli
poetry publish
```

---

## Step 8：发布后验证

建议在新的干净环境中验证正式安装：

```bash
python -m venv .venv-install-check
source .venv-install-check/bin/activate
pip install --upgrade pip
pip install iotsploit-core iotsploit-django iotsploit-drivers iotsploit-exploits iotsploit-cli
```

然后验证：

```bash
python -c "import iotsploit_core; print('core ok')"
python -c "import iotsploit_django; print('django ok')"
python -c "import iotsploit_drivers; print('drivers ok')"
python -c "import iotsploit_exploits; print('exploits ok')"
python -c "import iotsploit_cli; print('cli ok')"
iotsploit --help
```

如需验证 entry points：

```bash
python -c "from importlib import metadata; print([ep.name for ep in metadata.entry_points().select(group='iotsploit.device_drivers')])"
python -c "from importlib import metadata; print([ep.name for ep in metadata.entry_points().select(group='iotsploit.exploit_plugins')])"
```

---

## 已发布包的后续更新

因为 `iotsploit-core` 和 `iotsploit-django` 已经发布，后续更新流程是：

1. 修改代码
2. 提升版本号
3. `poetry build`
4. `poetry publish`

例如：

```bash
cd iotsploit-core
poetry version patch
poetry build
poetry publish
```

```bash
cd iotsploit-django
poetry version patch
poetry build
poetry publish
```

如果 `iotsploit-drivers` / `iotsploit-exploits` / `iotsploit-cli` 对 `core` 或 `django` 的最低版本有要求，也要同步更新依赖约束。

---

## 常见问题

| 错误信息 | 原因 | 解决方法 |
|----------|------|---------|
| `400 File already exists` | 同版本已上传 | 提升版本号后重新构建发布 |
| `403 Forbidden` | Token 权限或仓库配置错误 | 检查 `poetry config pypi-token.*` |
| `Package name already exists` | 首发包名被占用 | 更换包名 |
| 安装后发现不了 entry points | wheel 元数据未正确打包 | 检查 `pyproject.toml` 中 `plugins` 配置并重新 build |
| 安装后数据文件缺失 | wheel 未包含 package data | 检查 `include` 配置并重建 |
| 运行时报依赖缺失 | 依赖未发布到 PyPI 或版本约束不正确 | 检查 `pyproject.toml` 依赖闭包 |
| 某些 exploit 导入即失败 | 顶层 import 触发环境/权限依赖 | 将高风险依赖改为 lazy import，再重新发布 |

---

## 当前建议

当前仓库如果继续推进发布，建议直接按下面流程执行：

1. 更新并确认 `iotsploit-drivers/pyproject.toml`
2. 更新并确认 `iotsploit-exploits/pyproject.toml`
3. 如需要发布 CLI，同时确认 `iotsploit-cli/pyproject.toml`
4. 在干净环境验证 smoke tests 与 CLI console script
5. 先发布 `iotsploit-drivers`
6. 再发布 `iotsploit-exploits`
7. 如需要，再发布 `iotsploit-cli`
8. 只有当 `core` 或 `django` 再发生 API / 依赖变化时，才单独 bump 并发布它们
