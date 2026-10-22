"""Single-ASGI-process execution owner; no dependency on Channels consumers."""

import asyncio
import os
from pathlib import Path
import socket
import uuid

from . import agents, store
from .providers import McpTools, api_turn


QUICK_ACTIONS = {"list_devices", "get_current_target", "list_plugins", "system_health", "scan_devices"}


class AssistantRuntime:
    def __init__(self):
        self.active = {}
        self.listeners = {}
        self.discovery = []

    @property
    def local_enabled(self):
        return not (Path("/.dockerenv").exists() or os.getenv("IOTSPLOIT_ASSISTANT_LOCAL_AGENTS", "1") == "0")

    @property
    def read_url(self):
        return os.getenv("IOTSPLOIT_MCP_READONLY_URL", "http://127.0.0.1:9901/mcp")

    async def discover(self, manual=None, *, refresh=False):
        if not self.discovery or refresh:
            self.discovery = await agents.discover(manual) if self.local_enabled else []
        return {
            "type": "discovery",
            "host": socket.gethostname(),
            "local_enabled": self.local_enabled,
            "agents": self.discovery,
            "configs": await store.configs(),
        }

    async def create(self, client_key, data):
        mode = data.get("mode", "api")
        if mode not in {"api", "local"}:
            raise ValueError("Unknown assistant mode")
        fields = {"mode": mode}
        if mode == "local":
            if not self.local_enabled:
                raise ValueError("Local agents are unavailable in Docker. Use API mode.")
            candidate = next(
                (
                    a
                    for a in self.discovery
                    if a["path"] == data.get("binary_path")
                    and a["engine"] == data.get("engine")
                    and a["state"] == "ready"
                ),
                None,
            )
            if candidate is None:
                raise ValueError("Select a detected, supported agent. Refresh detection if it moved.")
            fields.update(engine=candidate["engine"], binary_path=candidate["path"])
        else:
            config = await store.config(data.get("config_id"), required=bool(data.get("config_id")))
            if config:
                if data.get("config_id") and config.provider not in {
                    "openai",
                    "custom",
                    "azure_openai",
                    "ollama",
                    "anthropic",
                }:
                    raise ValueError("This provider does not support assistant tools yet.")
                fields["config_id"] = config.id
        return await store.create(client_key, **fields)

    async def emit(self, session_id, turn_id, kind, payload):
        event = await store.append(session_id, turn_id, kind, payload)
        for listener in tuple(self.listeners.get(str(session_id), set())):
            try:
                await listener(event)
            except (OSError, RuntimeError):
                self.listeners.get(str(session_id), set()).discard(listener)

    async def start(self, session, data):
        session_id = str(session.id)
        turn_id = str(uuid.UUID(str(data["turn_id"])))
        if await store.has_turn(session.id, turn_id):
            return
        if session_id in self.active:
            raise ValueError("A turn is already running in this conversation.")
        action = data.get("action") if data["type"] == "quick_action.run" else None
        text = data.get("text", "")
        if not isinstance(text, str):
            raise ValueError("Message text must be a string")
        prompt = text.strip()
        if action:
            if action not in QUICK_ACTIONS:
                raise ValueError("Unknown quick action")
            if action == "scan_devices" and data.get("confirmed") is not True:
                raise ValueError("Confirm device scanning before running it.")
        elif not prompt or len(prompt) > 32000:
            raise ValueError("Enter a message of 1–32000 characters.")
        task = asyncio.create_task(self._run(session, turn_id, prompt, action), name=turn_id)
        self.active[session_id] = task

    async def _run(self, session, turn_id, prompt, action):
        session_id = str(session.id)

        async def emit(kind, payload):
            if kind in {"turn.done", "turn.cancelled", "turn.error"}:
                self.release(session_id, asyncio.current_task())
            await self.emit(session_id, turn_id, kind, payload)

        async def execute():
            await emit("turn.started", {})
            await emit("user.message", {"text": action or prompt})
            if session.title == "New conversation":
                session.title = (action or prompt)[:120]
            if action:
                url = (
                    os.getenv("IOTSPLOIT_MCP_URL", "http://127.0.0.1:9900/mcp")
                    if action == "scan_devices"
                    else self.read_url
                )
                async with McpTools(url, inspection=action != "scan_devices") as tools:
                    output, _ = await tools.call(action, {}, emit, turn_id)
                    session.history.append(
                        {"role": "user", "content": f"Direct IoTSploit action {action} returned:\n{output}"}
                    )
            elif session.mode == "api":
                session.history.append({"role": "user", "content": prompt})
                async with McpTools(self.read_url) as tools:
                    config = await store.config(session.config_id)
                    session.config_id = config.id
                    await api_turn(session, config, tools, emit)
                    await store.record_usage(config.id)
            else:
                async with McpTools(self.read_url):
                    pass
                context = "\n".join(m["content"] for m in session.history[-4:])
                await agents.cli_turn(session, f"{context}\n\n{prompt}" if context else prompt, self.read_url, emit)
                session.history = []

        try:
            await asyncio.wait_for(execute(), 300)
            await store.save_context(session)
            await emit("turn.done", {})
        except asyncio.CancelledError:
            await store.save_context(session)
            await emit("turn.cancelled", {})
        except Exception as exc:
            await store.save_context(session)
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else (
                    "Turn timed out after 5 minutes."
                    if isinstance(exc, asyncio.TimeoutError)
                    else "Execution failed. Check provider sign-in/model access and the MCP connection."
                )
            )
            await emit("turn.error", {"message": message})
        finally:
            self.release(session_id, asyncio.current_task())

    def release(self, session_id, task):
        if self.active.get(str(session_id)) is task:
            self.active.pop(str(session_id), None)

    async def cancel(self, session_id):
        task = self.active.get(str(session_id))
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.release(session_id, task)
            if task.cancelled():
                await self.emit(session_id, task.get_name(), "turn.cancelled", {})

    async def close(self):
        tasks = tuple(self.active.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


runtime = AssistantRuntime()
