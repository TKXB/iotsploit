from __future__ import annotations

from typing import Any

from iotsploit_core.ports.task_runner import TaskRunner


class LocalTaskRunner(TaskRunner):
    """最小可用 TaskRunner：用于 MCP 进程内满足依赖。

    当前 MCP 主要走 `execute_plugin_async`（直接 await），不会依赖 Celery。
    这里实现 submit 仅用于兼容 `ExploitPluginManager` 的构造函数签名与返回结构。
    """

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "execution_type": "in_process",
            "plugin_name": plugin_name,
            "target": target,
            "parameters": parameters,
            "context": context,
        }


