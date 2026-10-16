"""Provider tool loops using the existing encrypted AIModelConfig owner."""

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


WRITE_TOOLS = {"scan_devices", "create_target", "edit_target", "select_target", "execute_plugin", "record_observations"}
SYSTEM = "You are the IoTSploit inspection assistant. Use the supplied tools for real data. Never invent results."


class McpTools:
    def __init__(self, url, *, inspection=True):
        self.url = url
        self.inspection = inspection

    async def __aenter__(self):
        from contextlib import AsyncExitStack

        self.stack = AsyncExitStack()
        try:
            read, write, _ = await self.stack.enter_async_context(streamablehttp_client(self.url))
            self.session = await self.stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            self.tools = (await self.session.list_tools()).tools
            if self.inspection and WRITE_TOOLS.intersection(t.name for t in self.tools):
                raise ValueError("Assistant requires the read-only MCP instance on port 9901. See setup instructions.")
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *exc):
        return await self.stack.__aexit__(*exc)

    async def call(self, name, arguments, emit, call_id):
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            raise ValueError(f"Unknown or unavailable tool: {name}")
        await emit("tool.start", {"name": name, "arguments": arguments, "call_id": call_id})
        result = await self.session.call_tool(name, arguments)
        output = "\n".join(getattr(c, "text", str(c)) for c in result.content)
        error = bool(result.isError)
        for item in result.content:
            try:
                payload = json.loads(getattr(item, "text", ""))
            except (ValueError, TypeError):
                continue
            error |= isinstance(payload, dict) and (payload.get("status") == "error" or payload.get("success") is False)
        await emit(
            "tool.error" if error else "tool.result",
            {"name": name, "output": output, "call_id": call_id, "is_error": error},
        )
        return output, error


async def api_turn(session, config, tools, emit):
    """Persist complete provider-native context only after a successful turn."""
    provider = config.provider
    history = json.loads(json.dumps(session.history))
    options = config.extra_config or {}
    max_tokens = options.get("max_tokens", 4096)
    if provider == "anthropic":
        from anthropic import AsyncAnthropic

        async with AsyncAnthropic(api_key=config.get_api_key(), base_url=config.api_url.rstrip("/")) as client:
            for _ in range(8):
                async with client.messages.stream(
                    model=config.model_name,
                    max_tokens=max_tokens,
                    system=SYSTEM,
                    messages=history,
                    tools=[
                        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
                        for t in tools.tools
                    ],
                ) as stream:
                    async for text in stream.text_stream:
                        await emit("text.delta", {"text": text})
                    response = await stream.get_final_message()
                content = [b.model_dump(exclude_none=True) for b in response.content]
                history.append({"role": "assistant", "content": content})
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        output, error = await tools.call(block.name, block.input, emit, block.id)
                        results.append(
                            {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": error}
                        )
                if not results:
                    if response.stop_reason == "max_tokens":
                        raise ValueError("Model output limit reached. Start a new chat or increase max_tokens.")
                    session.history = history
                    return
                history.append({"role": "user", "content": results})
    elif provider in {"openai", "custom", "azure_openai", "ollama"}:
        from openai import AsyncAzureOpenAI, AsyncOpenAI

        url = config.api_url.rstrip("/")
        if provider == "ollama" and url.endswith("/api"):
            url = url[:-4] + "/v1"
        if provider == "azure_openai":
            client = AsyncAzureOpenAI(
                api_key=config.get_api_key(),
                azure_endpoint=url.split("/openai/")[0],
                api_version=options.get("api_version", "2024-10-21"),
            )
        else:
            client = AsyncOpenAI(api_key=config.get_api_key() or "ollama", base_url=url)
        async with client:
            for _ in range(8):
                stream = await client.chat.completions.create(
                    model=options.get("deployment_name", config.model_name),
                    messages=[{"role": "system", "content": SYSTEM}, *history],
                    max_tokens=max_tokens,
                    stream=True,
                    **(
                        {
                            "tools": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": t.name,
                                        "description": t.description or "",
                                        "parameters": t.inputSchema,
                                    },
                                }
                                for t in tools.tools
                            ]
                        }
                        if tools.tools
                        else {}
                    ),
                )
                content, calls, finish = "", {}, None
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    finish = choice.finish_reason or finish
                    delta = choice.delta
                    if delta.content:
                        content += delta.content
                        await emit("text.delta", {"text": delta.content})
                    for part in delta.tool_calls or []:
                        call = calls.setdefault(
                            part.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                        )
                        if part.id:
                            call["id"] = part.id
                        if part.function:
                            call["function"]["name"] += part.function.name or ""
                            call["function"]["arguments"] += part.function.arguments or ""
                if finish is None:
                    raise ValueError("Provider stream ended before completing the response.")
                message = {"role": "assistant", "content": content or None}
                if calls:
                    message["tool_calls"] = list(calls.values())
                history.append(message)
                if not calls:
                    if finish == "length":
                        raise ValueError("Model output limit reached. Start a new chat or increase max_tokens.")
                    session.history = history
                    return
                for call in calls.values():
                    output, _ = await tools.call(
                        call["function"]["name"], json.loads(call["function"]["arguments"]), emit, call["id"]
                    )
                    history.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    else:
        raise ValueError(f"{provider} does not support assistant tools yet. Choose OpenAI-compatible or Anthropic.")
    raise ValueError("Stopped after 8 model/tool rounds. Start a new chat to continue.")
