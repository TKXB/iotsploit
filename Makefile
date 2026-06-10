MCP_URL ?= http://127.0.0.1:9900/mcp

.PHONY: mcp-smoke
mcp-smoke:
	@test -n "$$IOTSPLOIT_MCP_TOKEN" || (echo "IOTSPLOIT_MCP_TOKEN is required" >&2; exit 1)
	curl -fsS \
		-H "Authorization: Bearer $$IOTSPLOIT_MCP_TOKEN" \
		-H "Content-Type: application/json" \
		-H "Accept: application/json, text/event-stream" \
		-d '{"jsonrpc":"2.0","id":"smoke","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"iotsploit-mcp-smoke","version":"0.1"}}}' \
		"$(MCP_URL)"
