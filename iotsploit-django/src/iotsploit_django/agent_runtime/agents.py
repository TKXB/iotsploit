"""Known CLI discovery and structured, owned subprocess adapters."""

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import signal


MINIMUM = {"claude": (2, 1, 248), "codex": (0, 160, 0), "opencode": (1, 17, 18)}


def agent_error(details):
    if any(
        word in str(details).lower()
        for word in ("login", "log in", "sign in", "unauthorized", "authentication", "oauth")
    ):
        return "needs_login: Sign in using the agent's CLI on the runtime host, then start a new chat."
    return "Agent failed. Check its model access and MCP connection, then start a new chat."


def version_tuple(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


async def terminate(process):
    if process.returncode is None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
        except ProcessLookupError:
            await process.wait()


async def discover(manual=None):
    results = []
    for engine, minimum in MINIMUM.items():
        paths = {
            str(Path(p, engine).absolute())
            for p in os.get_exec_path()
            if Path(p, engine).is_file() and os.access(Path(p, engine), os.X_OK)
        }
        if manual and manual.get("engine") == engine:
            paths.add(str(Path(manual["path"]).expanduser().absolute()))
        found = []
        for path in sorted(paths):
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    path,
                    "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=os.name == "posix",
                    limit=65536,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), 5)
                version = stdout.decode(errors="replace").strip()[:200]
                state = (
                    "ready" if process.returncode == 0 and version_tuple(version) >= minimum else "unsupported_version"
                )
            except (OSError, asyncio.TimeoutError, ValueError):
                version, state = "", "probe_error"
            finally:
                if process:
                    await terminate(process)
            found.append({"engine": engine, "path": path, "version": version, "state": state})
        found.sort(key=lambda item: version_tuple(item["version"]), reverse=True)
        results.extend(found or [{"engine": engine, "path": "", "version": "", "state": "missing"}])
    return results


def prepare(engine, folder, mcp_url, native_id):
    """Only credentials are reused. User/project hooks and MCP configs are not."""
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("CODEX_", "CLAUDE_", "OPENCODE_")):
            env.pop(key)
    if engine == "claude":
        config = folder / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"iotsploit": {"type": "http", "url": mcp_url}}}))
        args = [
            "--bare",
            "--restricted",
            "-p",
            "--output-format",
            "stream-json",
            "--input-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--tools",
            "",
            "--allowedTools",
            "mcp__iotsploit__*",
            "--strict-mcp-config",
            "--mcp-config",
            str(config),
            "--setting-sources",
            "",
        ]
        if native_id:
            args += ["--resume", native_id]
        return args, env
    if engine == "opencode":
        # Isolate merged user and project configuration, but preserve provider
        # sign-in by copying only the credential file into the private data dir.
        env.update(
            XDG_CONFIG_HOME=str(folder / "config"),
            XDG_DATA_HOME=str(folder / "data"),
            OPENCODE_DISABLE_PROJECT_CONFIG="true",
        )
        auth = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "opencode" / "auth.json"
        destination = folder / "data" / "opencode" / "auth.json"
        if auth.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(auth, destination)
            destination.chmod(0o600)
        config = folder / "opencode.json"
        config.write_text(
            json.dumps(
                {
                    "permission": {"*": "deny", "iotsploit_*": "allow"},
                    "mcp": {"iotsploit": {"type": "remote", "url": mcp_url, "oauth": False}},
                }
            )
        )
        env["OPENCODE_CONFIG"] = str(config)
        return ["run", "--format", "json", *(["--session", native_id] if native_id else [])], env
    home = folder / "codex"
    home.mkdir(exist_ok=True, mode=0o700)
    auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if auth.is_file() and not (home / "auth.json").exists():
        shutil.copyfile(auth, home / "auth.json")
        (home / "auth.json").chmod(0o600)
    # An isolated CODEX_HOME plus a private cwd prevents inherited MCP servers,
    # plugins, hooks and project configuration from expanding the tool surface.
    (home / "config.toml").write_text(
        'approval_policy = "never"\nsandbox_mode = "read-only"\nweb_search = "disabled"\n'
        "[features]\nshell_tool = false\nunified_exec = false\napps = false\nplugins = false\n"
        "multi_agent = false\ncode_mode = false\nbrowser_use = false\ncomputer_use = false\n"
        "image_generation = false\n"
        "[mcp_servers.iotsploit]\nurl = " + json.dumps(mcp_url) + "\n"
    )
    env["CODEX_HOME"] = str(home)
    return ["app-server", "--strict-config"], env


async def cli_turn(session, prompt, url, emit):
    root = Path(
        os.getenv("IOTSPLOIT_ASSISTANT_STATE_DIR", str(Path.home() / ".local" / "state" / "iotsploit" / "assistant"))
    )
    folder = root / str(session.id)
    args, env = prepare(session.engine, folder, url, session.native_session_id)
    process = await asyncio.create_subprocess_exec(
        session.binary_path,
        *args,
        cwd=folder,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
        limit=4 * 1024 * 1024,
    )

    # Drain stderr concurrently so a verbose CLI cannot block on a full pipe.
    async def drain():
        tail = b""
        while chunk := await process.stderr.read(4096):
            tail = (tail + chunk)[-8192:]
        return tail.decode(errors="replace")

    stderr = asyncio.create_task(drain())
    try:
        if session.engine == "codex":
            await codex_turn(process, session, prompt, emit)
        else:
            if session.engine == "claude":
                message = json.dumps({"type": "user", "message": {"role": "user", "content": prompt}})
                process.stdin.write((message + "\n").encode())
            else:
                process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()
            completed = False
            async for line in process.stdout:
                event = json.loads(line)
                native = event.get("session_id") or event.get("sessionID")
                if native:
                    session.native_session_id = native
                kind = event.get("type")
                if kind == "stream_event":
                    delta = event.get("event", {}).get("delta", {})
                    if delta.get("type") == "text_delta":
                        await emit("text.delta", {"text": delta["text"]})
                elif kind == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use":
                            await emit(
                                "tool.start",
                                {"name": block["name"], "arguments": block["input"], "call_id": block["id"]},
                            )
                elif kind == "user":
                    for block in event.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            await emit(
                                "tool.error" if block.get("is_error") else "tool.result",
                                {
                                    "name": "IoTSploit",
                                    "output": str(block.get("content", "")),
                                    "call_id": block["tool_use_id"],
                                },
                            )
                elif kind == "text":
                    await emit("text.delta", {"text": event.get("part", {}).get("text", "")})
                elif kind == "tool_use":
                    part = event.get("part", {})
                    state = part.get("state", {})
                    await emit(
                        "tool.error" if state.get("status") == "error" else "tool.result",
                        {
                            "name": part.get("tool", "IoTSploit"),
                            "output": str(state.get("error") or state.get("output", "")),
                            "arguments": state.get("input", {}),
                            "call_id": part.get("callID", ""),
                        },
                    )
                elif kind == "result":
                    if event.get("is_error"):
                        raise ValueError(agent_error(event.get("result", event.get("errors", ""))))
                    completed = True
                elif kind == "step_finish":
                    completed = event.get("part", {}).get("reason") == "stop"
                elif kind == "error":
                    raise ValueError(agent_error(event.get("error", "")))
            await process.wait()
            if not completed or process.returncode:
                error = await stderr
                raise ValueError(agent_error(error))
    finally:
        await terminate(process)
        await stderr


async def codex_turn(process, session, prompt, emit):
    sequence = 0
    completed_status = None

    async def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()

    async def notification(event):
        nonlocal completed_status
        method, params = event.get("method"), event.get("params", {})
        if "id" in event and "method" in event:
            # Never approve a shell, file, or MCP elicitation request.
            await send({"id": event["id"], "error": {"code": -32601, "message": "Interactive actions unavailable"}})
        elif method == "item/agentMessage/delta":
            await emit("text.delta", {"text": params.get("delta", "")})
        elif method == "turn/completed":
            completed_status = params["turn"]["status"]
        elif method in {"item/started", "item/completed"}:
            item = params.get("item", {})
            if item.get("type") == "mcpToolCall":
                kind = (
                    "tool.start" if method.endswith("started") else "tool.error" if item.get("error") else "tool.result"
                )
                await emit(
                    kind,
                    {
                        "name": item.get("tool", "IoTSploit"),
                        "arguments": item.get("arguments", {}),
                        "output": json.dumps(item.get("error") or item.get("result", {})),
                        "call_id": item.get("id", ""),
                    },
                )

    async def rpc(method, params):
        nonlocal sequence
        sequence += 1
        request_id = sequence
        await send({"id": request_id, "method": method, "params": params})
        while line := await process.stdout.readline():
            event = json.loads(line)
            if event.get("id") == request_id and "method" not in event:
                if "error" in event:
                    raise ValueError(agent_error(event["error"].get("message", "")))
                return event.get("result", {})
            await notification(event)
        raise ValueError("Codex disconnected before completing the request.")

    await rpc("initialize", {"clientInfo": {"name": "iotsploit", "version": "1.0.0"}})
    await send({"method": "initialized"})
    params = {"approvalPolicy": "never", "sandbox": "read-only"}
    # Keep cwd private; never let a thread load project configuration from a repo.
    params["cwd"] = str(
        Path(
            os.getenv(
                "IOTSPLOIT_ASSISTANT_STATE_DIR", str(Path.home() / ".local" / "state" / "iotsploit" / "assistant")
            )
        )
        / str(session.id)
    )
    if session.native_session_id:
        params["threadId"] = session.native_session_id
    thread = await rpc("thread/resume" if session.native_session_id else "thread/start", params)
    session.native_session_id = thread["thread"]["id"]
    started = await rpc(
        "turn/start", {"threadId": session.native_session_id, "input": [{"type": "text", "text": prompt}]}
    )
    try:
        while completed_status is None and (line := await process.stdout.readline()):
            event = json.loads(line)
            await notification(event)
    except asyncio.CancelledError:
        turn_id = started.get("turn", {}).get("id")
        if turn_id:
            try:
                await asyncio.wait_for(
                    rpc("turn/interrupt", {"threadId": session.native_session_id, "turnId": turn_id}), 2
                )
            except (asyncio.TimeoutError, ValueError, OSError):
                pass
        raise
    if completed_status == "completed":
        return
    if completed_status:
        raise ValueError("Codex turn failed or was interrupted. Check sign-in and model access.")
    raise ValueError("Codex exited without completing the turn.")
