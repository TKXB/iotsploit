# iotsploit-mcp

`iotsploit-mcp` 是 IoTSploit 的 MCP 运行时组件（execution plane / outer ring），包含：

- FastMCP **stdio server**（提供 MCP tools）
- WebSocket **bridge**（给上层 UI/Django consumer 通过 `ws://host:9998` 访问）

## 命令

- 默认启动 WebSocket bridge（等价于 `ws`）：

```bash
iotsploit-mcp
```

- 显式启动 WebSocket bridge：

```bash
iotsploit-mcp ws --host 0.0.0.0 --port 9998
```

- 只启动 stdio FastMCP server（一般由 bridge 拉起）：

```bash
iotsploit-mcp stdio
```

## 环境变量

- `IOTSPLOIT_DJANGO_API_BASE_URL`：Django HTTP API base URL（默认 `http://127.0.0.1:8888`）
- `IOTSPLOIT_DJANGO_API_TOKEN`：可选 Bearer token
- `IOTSPLOIT_DJANGO_API_TIMEOUT_S`：可选超时（秒）
- `IOTSPLOIT_DEVICE_PLUGINS_DIR`：device driver 插件目录
- `IOTSPLOIT_EXPLOIT_PLUGINS_DIR`：exploit 插件目录


