"""Service startup uses one endpoint selection for listeners and their clients."""

from __future__ import annotations

from types import SimpleNamespace

import cmd2
import pytest

from iotsploit_cli.commands import django_commands
from iotsploit_cli.commands.django_commands import DjangoCommands


pytestmark = pytest.mark.unit


class Process:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True


class ServiceHarness(DjangoCommands):
    def __init__(self):
        self.django_server_process = None
        self.daphne_server_process = None
        self.mcp_bridge_process = None
        self.celery_worker_process = None
        self.interactive_worker_process = None
        self.streaming_worker_process = None
        self.errors = []

    def poutput(self, _message):
        return None

    def perror(self, message):
        self.errors.append(message)

    def _check_redis_available(self):
        return True, "Redis is available"


class LegacyShell(cmd2.Cmd, DjangoCommands):
    def __init__(self):
        super().__init__()
        self.options = None

    def _start_services(self, **options):
        self.options = options


@pytest.fixture
def launched(monkeypatch):
    processes = []
    posts = []

    def popen(command, **kwargs):
        process = Process(command, **kwargs)
        processes.append(process)
        return process

    def post(url):
        posts.append(url)
        return SimpleNamespace(status_code=200, text="")

    monkeypatch.setattr(django_commands.subprocess, "Popen", popen)
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setenv("IOTSPLOIT_SERVICE_LOG_TO_CONSOLE", "1")
    monkeypatch.setenv("IOTSPLOIT_DJANGO_API_BASE_URL", "original-api")
    monkeypatch.setenv("IOTSPLOIT_DJANGO_WS_BASE_URL", "original-ws")
    monkeypatch.setenv("IOTSPLOIT_MCP_URL", "original-mcp")
    return processes, posts


def test_local_runtime_applies_custom_listener_and_client_endpoints(monkeypatch, launched):
    processes, posts = launched
    monkeypatch.setattr(django_commands, "settings", SimpleNamespace(IOTSPLOIT_RUNTIME="local"))
    shell = ServiceHarness()

    result = shell._start_services(
        host="0.0.0.0",
        api_port=8080,
        ws_port=8081,
        mcp_host="0.0.0.0",
        mcp_port=9901,
    )

    assert result is None
    assert [process.command for process in processes] == [
        [
            django_commands.sys.executable,
            "-m",
            "daphne",
            "-e",
            "tcp:8080:interface=0.0.0.0",
            "-e",
            "tcp:8081:interface=0.0.0.0",
            "iotsploit_django.asgi:application",
        ],
        [
            django_commands.sys.executable,
            "-m",
            "iotsploit_mcp.cli",
            "http",
            "--host",
            "0.0.0.0",
            "--port",
            "9901",
        ],
    ]
    assert posts == ["http://127.0.0.1:8080/api/initialize_devices/"]
    assert processes[0].kwargs["env"]["IOTSPLOIT_MCP_URL"] == "http://127.0.0.1:9901/mcp"
    assert processes[1].kwargs["env"]["IOTSPLOIT_DJANGO_API_BASE_URL"] == "http://127.0.0.1:8080"


def test_distributed_runtime_applies_custom_api_and_websocket_endpoints(monkeypatch, launched):
    processes, _posts = launched
    monkeypatch.setattr(django_commands, "settings", SimpleNamespace(IOTSPLOIT_RUNTIME="distributed"))
    shell = ServiceHarness()

    result = shell._start_services(
        host="192.0.2.20",
        api_port=8080,
        ws_port=8081,
        mcp_host="127.0.0.1",
        mcp_port=9901,
    )

    assert result is None
    assert processes[0].command[-1] == "192.0.2.20:8080"
    assert processes[1].command == [
        django_commands.sys.executable,
        "-m",
        "daphne",
        "-b",
        "192.0.2.20",
        "-p",
        "8081",
        "iotsploit_django.asgi:application",
    ]


def test_duplicate_ports_fail_before_processes_start(launched):
    processes, _posts = launched
    shell = ServiceHarness()

    result = shell._start_services(
        host="127.0.0.1",
        api_port=8888,
        ws_port=8888,
        mcp_host="127.0.0.1",
        mcp_port=9900,
    )

    assert result is False
    assert processes == []
    assert shell.errors == ["--api-port, --ws-port, and --mcp-port must use distinct ports"]


def test_legacy_runserver_accepts_the_shared_endpoint_options():
    shell = LegacyShell()

    shell.onecmd_plus_hooks("runserver --host 192.0.2.20 --api-port 8080 --ws-port 8081 --mcp-port 9901")

    assert shell.options == {
        "host": "192.0.2.20",
        "api_port": 8080,
        "ws_port": 8081,
        "mcp_host": "127.0.0.1",
        "mcp_port": 9901,
    }


def test_stop_uses_the_selected_api_endpoint(launched):
    _processes, posts = launched
    shell = ServiceHarness()
    shell.daphne_server_process = Process([])
    shell._service_api_base_url = "http://192.0.2.20:8080"

    shell.do_stop_server("")

    assert posts == ["http://192.0.2.20:8080/api/cleanup_devices/"]
