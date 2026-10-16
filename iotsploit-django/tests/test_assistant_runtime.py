"""Assistant turns must keep context, deny writes, and never replay execution."""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import django
from django.apps import apps
import pytest

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.agent_runtime import agents, providers, runtime as runtime_module, store
from iotsploit_django.adapters.django.assistant import AssistantEvent, AssistantSession

pytestmark = pytest.mark.unit


def test_private_conversations_have_ordered_unique_events(db):
    first = AssistantSession.objects.create(client_key="first")
    second = AssistantSession.objects.create(client_key="second")
    turn = uuid.uuid4()

    event = store.append.func(first.id, turn, "user.message", {"text": "List devices"})
    store.append.func(first.id, turn, "text.delta", {"text": "Two devices"})

    assert event["seq"] == 1
    assert list(first.events.values_list("seq", flat=True)) == [1, 2]
    assert not second.events.exists()
    assert store.sessions.func("second")[0]["id"] == str(second.id)
    with pytest.raises(AssistantSession.DoesNotExist):
        store.load.func("second", first.id)
    AssistantEvent.objects.filter(session=first).delete()


@pytest.mark.parametrize("engine", ["claude", "codex", "opencode"])
def test_cli_configuration_excludes_shell_and_inherited_tools(tmp_path, monkeypatch, engine):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "user-codex"))
    monkeypatch.setenv("OPENCODE_CONFIG", "untrusted-project.json")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "user-data"))
    folder = tmp_path / "conversation"

    args, env = agents.prepare(engine, folder, "http://127.0.0.1:9901/mcp", "session-123")

    if engine == "claude":
        assert args[args.index("--tools") + 1] == ""
        assert "--restricted" in args and "--strict-mcp-config" in args and "--bare" in args
        assert args[args.index("--resume") + 1] == "session-123"
        assert json.loads((folder / "mcp.json").read_text())["mcpServers"]["iotsploit"]["url"].endswith("9901/mcp")
    elif engine == "codex":
        config = (folder / "codex" / "config.toml").read_text()
        assert 'sandbox_mode = "read-only"' in config
        assert "shell_tool = false" in config and "apps = false" in config
        assert env["CODEX_HOME"] != str(tmp_path / "user-codex")
    else:
        config = json.loads((folder / "opencode.json").read_text())
        assert config["permission"] == {"*": "deny", "iotsploit_*": "allow"}
        assert env["OPENCODE_CONFIG"] != "untrusted-project.json"
        assert env["XDG_CONFIG_HOME"].startswith(str(folder))
        assert "--session" in args


def test_discovery_lists_shadowed_binaries_in_version_order(tmp_path, monkeypatch):
    dirs = [tmp_path / "old", tmp_path / "new"]
    for folder in dirs:
        folder.mkdir()
        (folder / "codex").touch(mode=0o755)
    monkeypatch.setattr(os, "get_exec_path", lambda: [str(p) for p in dirs])

    async def spawn(path, *args, **kwargs):
        assert args == ("--version",)
        version = b"codex-cli 0.76.0" if "old" in path else b"codex-cli 0.160.0"
        return SimpleNamespace(communicate=AsyncMock(return_value=(version, b"")), returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    result = asyncio.run(agents.discover())

    codex = [r for r in result if r["engine"] == "codex"]
    assert [r["state"] for r in codex] == ["ready", "unsupported_version"]
    assert len({r["path"] for r in codex}) == 2


def test_api_tool_results_feed_back_into_the_model(monkeypatch):
    import openai

    async def scenario():
        calls = []
        responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-device", function=SimpleNamespace(name="list_devices", arguments="{}")
                                )
                            ],
                            model_dump=lambda **kw: {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "call-device",
                                        "type": "function",
                                        "function": {"name": "list_devices", "arguments": "{}"},
                                    }
                                ],
                            },
                        ),
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(
                            content="The device is an ESP32.",
                            tool_calls=[],
                            model_dump=lambda **kw: {"role": "assistant", "content": "The device is an ESP32."},
                        ),
                    )
                ]
            ),
        ]

        async def completion(**kwargs):
            calls.append(kwargs)
            response = responses.pop(0)
            message = response.choices[0].message

            async def chunks():
                tool_calls = [SimpleNamespace(index=0, id=c.id, function=c.function) for c in message.tool_calls]
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason=None, delta=SimpleNamespace(content=message.content, tool_calls=tool_calls)
                        )
                    ]
                )
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason=response.choices[0].finish_reason,
                            delta=SimpleNamespace(content=None, tool_calls=None),
                        )
                    ]
                )

            return chunks()

        class Client:
            chat = SimpleNamespace(completions=SimpleNamespace(create=completion))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: Client())
        tools = SimpleNamespace(tools=[], call=AsyncMock(return_value=('{"devices":["ESP32"]}', False)))
        session = SimpleNamespace(history=[{"role": "user", "content": "List devices"}])
        config = SimpleNamespace(
            provider="openai",
            model_name="model",
            api_url="https://example.test/v1",
            extra_config={},
            get_api_key=lambda: "test-key",
        )

        await providers.api_turn(session, config, tools, AsyncMock())

        assert calls[1]["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "call-device",
            "content": '{"devices":["ESP32"]}',
        }
        assert session.history[-1]["content"] == "The device is an ESP32."
        assert session.history[0]["content"] == "List devices"

    asyncio.run(scenario())


def test_runtime_cancels_and_replayed_turn_ids_do_not_execute(monkeypatch):
    async def scenario():
        events = []
        started = asyncio.Event()
        runtime = runtime_module.AssistantRuntime()
        session = SimpleNamespace(id=uuid.uuid4(), mode="api", history=[], title="New conversation", config_id=None)

        async def append(session_id, turn_id, kind, payload):
            event = {"session_id": session_id, "turn_id": turn_id, "type": kind, "seq": len(events) + 1, **payload}
            events.append(event)
            return event

        async def execute(*args):
            started.set()
            await asyncio.Event().wait()

        class Tools:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(store, "append", append)
        monkeypatch.setattr(
            store, "has_turn", AsyncMock(side_effect=lambda sid, tid: any(e["turn_id"] == tid for e in events))
        )
        monkeypatch.setattr(store, "save_context", AsyncMock())
        monkeypatch.setattr(store, "config", AsyncMock())
        monkeypatch.setattr(runtime_module, "McpTools", Tools)
        monkeypatch.setattr(runtime_module, "api_turn", execute)
        command = {"type": "turn.send", "turn_id": str(uuid.uuid4()), "text": "List devices"}

        await runtime.start(session, command)
        await started.wait()
        with pytest.raises(ValueError, match="already running"):
            await runtime.start(session, {**command, "turn_id": str(uuid.uuid4())})
        await runtime.cancel(session.id)
        assert events[-1]["type"] == "turn.cancelled"
        assert not runtime.active
        await runtime.start(session, command)
        assert not runtime.active

    asyncio.run(scenario())


def test_scan_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(store, "has_turn", AsyncMock(return_value=False))
    runtime = runtime_module.AssistantRuntime()
    session = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(ValueError, match="Confirm device scanning"):
        asyncio.run(
            runtime.start(session, {"type": "quick_action.run", "action": "scan_devices", "turn_id": str(uuid.uuid4())})
        )


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_codex_protocol_resumes_and_never_grants_permissions(status):
    async def scenario():
        requests = []
        messages = [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "native-thread"}}},
            {"id": 99, "method": "item/commandExecution/requestApproval", "params": {}},
            {"id": 3, "result": {}},
            {"method": "item/agentMessage/delta", "params": {"delta": "Found ESP32"}},
            {"method": "turn/completed", "params": {"turn": {"status": status}}},
        ]
        process = SimpleNamespace(
            stdin=SimpleNamespace(write=lambda data: requests.append(json.loads(data)), drain=AsyncMock()),
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=[(json.dumps(m) + "\n").encode() for m in messages])),
        )
        session = SimpleNamespace(id=uuid.uuid4(), native_session_id="native-thread")
        emit = AsyncMock()

        if status == "failed":
            with pytest.raises(ValueError, match="failed or was interrupted"):
                await agents.codex_turn(process, session, "List devices", emit)
        else:
            await agents.codex_turn(process, session, "List devices", emit)

        resume = next(r for r in requests if r.get("method") == "thread/resume")
        assert resume["params"]["sandbox"] == "read-only"
        assert resume["params"]["approvalPolicy"] == "never"
        assert next(r for r in requests if r.get("id") == 99)["error"]["code"] == -32601
        emit.assert_awaited_with("text.delta", {"text": "Found ESP32"})

    asyncio.run(scenario())


def test_anthropic_tool_result_is_a_user_content_block(monkeypatch):
    import anthropic

    async def scenario():
        requests = []
        tool = SimpleNamespace(
            type="tool_use",
            id="call-1",
            name="list_devices",
            input={},
            model_dump=lambda **kwargs: {"type": "tool_use", "id": "call-1", "name": "list_devices", "input": {}},
        )
        text = SimpleNamespace(
            type="text", text="ESP32 found", model_dump=lambda **kwargs: {"type": "text", "text": "ESP32 found"}
        )

        class Stream:
            def __init__(self, block):
                self.block = block

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            @property
            def text_stream(self):
                async def chunks():
                    if self.block.type == "text":
                        yield self.block.text

                return chunks()

            async def get_final_message(self):
                return SimpleNamespace(
                    content=[self.block], stop_reason="tool_use" if self.block is tool else "end_turn"
                )

        def stream(**kwargs):
            requests.append(kwargs)
            return Stream(tool if len(requests) == 1 else text)

        class Client:
            messages = SimpleNamespace(stream=stream)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda **kwargs: Client())
        tools = SimpleNamespace(tools=[], call=AsyncMock(return_value=("ESP32", False)))
        session = SimpleNamespace(history=[{"role": "user", "content": "List devices"}])
        config = SimpleNamespace(
            provider="anthropic",
            model_name="model",
            api_url="https://example.test",
            extra_config={},
            get_api_key=lambda: "test-key",
        )

        await providers.api_turn(session, config, tools, AsyncMock())

        assert session.history[2] == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": "ESP32", "is_error": False}],
        }
        assert len(requests) == 2

    asyncio.run(scenario())


def test_api_tool_loop_has_a_hard_round_limit(monkeypatch):
    import openai

    async def scenario():
        async def chunks():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0, id="call", function=SimpleNamespace(name="list_devices", arguments="{}")
                                )
                            ],
                        ),
                    )
                ]
            )

        completion = AsyncMock(side_effect=lambda **kwargs: chunks())

        class Client:
            chat = SimpleNamespace(completions=SimpleNamespace(create=completion))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: Client())
        tools = SimpleNamespace(tools=[], call=AsyncMock(return_value=("ESP32", False)))
        config = SimpleNamespace(
            provider="openai",
            model_name="model",
            api_url="https://example.test/v1",
            extra_config={},
            get_api_key=lambda: "test-key",
        )

        with pytest.raises(ValueError, match="8 model/tool rounds"):
            await providers.api_turn(SimpleNamespace(history=[]), config, tools, AsyncMock())

        assert completion.await_count == tools.call.await_count == 8

    asyncio.run(scenario())


def test_cancelling_a_queued_turn_releases_the_session(monkeypatch):
    async def scenario():
        runtime = runtime_module.AssistantRuntime()
        session = SimpleNamespace(id=uuid.uuid4())
        monkeypatch.setattr(store, "has_turn", AsyncMock(return_value=False))
        append = AsyncMock(return_value={})
        monkeypatch.setattr(store, "append", append)
        command = {"type": "turn.send", "turn_id": str(uuid.uuid4()), "text": "List devices"}

        await runtime.start(session, command)
        await runtime.cancel(session.id)

        assert not runtime.active
        assert append.await_args.args[2] == "turn.cancelled"

    asyncio.run(scenario())


def test_api_conversations_pin_the_default_configuration(monkeypatch):
    monkeypatch.setattr(store, "config", AsyncMock(return_value=SimpleNamespace(id=7, provider="openai")))
    create = AsyncMock(return_value={"id": "conversation"})
    monkeypatch.setattr(store, "create", create)

    asyncio.run(runtime_module.AssistantRuntime().create("private-client", {"mode": "api"}))

    create.assert_awaited_once_with("private-client", mode="api", config_id=7)


def test_api_conversation_can_be_created_for_tools_without_a_model_key(monkeypatch):
    monkeypatch.setattr(store, "config", AsyncMock(return_value=None))
    create = AsyncMock(return_value={"id": "conversation"})
    monkeypatch.setattr(store, "create", create)

    asyncio.run(runtime_module.AssistantRuntime().create("private-client", {"mode": "api"}))

    create.assert_awaited_once_with("private-client", mode="api")
