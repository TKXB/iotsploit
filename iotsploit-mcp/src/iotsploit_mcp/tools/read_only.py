from typing import Any, Callable
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.adapters.django_http_client import DjangoHttpClient, DjangoHttpError
from iotsploit_mcp.tools.xlogger_mcp import xlog_mcp


logger = xlog_mcp.get_logger("iotsploit_mcp.tools.read_only")


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, DjangoHttpError):
        payload: dict[str, Any] = {
            "status": "error",
            "message": str(exc),
        }
        if exc.status_code is not None:
            payload["status_code"] = exc.status_code
        if exc.response_text:
            payload["response_text"] = exc.response_text
        return payload
    return {"status": "error", "message": str(exc)}


def _call(name: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    logger.info("MCP tool call: %s", name)
    try:
        result = _ok(func())
        logger.info("MCP tool result: %s status=%s", name, result.get("status", "ok"))
        return result
    except Exception as exc:
        logger.error("MCP tool error: %s: %s", name, exc)
        return _error(exc)


def register_read_only_tools(mcp: FastMCP, client_factory: Callable[[], DjangoHttpClient] = DjangoHttpClient.from_env) -> None:
    """Register the v1 read-only HTTP-backed tool surface."""

    def client() -> DjangoHttpClient:
        return client_factory()

    @mcp.tool()
    def system_status() -> dict[str, Any]:
        """Return MCP and Django backend status using the Django HTTP API as SSOT."""

        def run() -> dict[str, Any]:
            health = client().get("/api/system_health/")
            return {
                "status": health.get("status", "success"),
                "mcp": {"transport": "streamable-http", "mode": "read-only"},
                "django": health,
            }

        return _call("system_status", run)

    @mcp.tool()
    def system_health() -> dict[str, Any]:
        """Return the IoTSploit Django system health payload."""

        return _call("system_health", lambda: client().get("/api/system_health/"))

    @mcp.tool()
    def list_urls() -> dict[str, Any]:
        """List Django API URLs exposed by the backend."""

        return _call("list_urls", lambda: client().get("/api/list_urls/"))

    @mcp.tool()
    def list_plugins() -> dict[str, Any]:
        """List exploit plugin metadata known to the Django backend."""

        return _call("list_plugins", lambda: client().get("/api/list_plugin_info/"))

    @mcp.tool()
    def describe_plugin(plugin_name: str = "") -> dict[str, Any]:
        """Describe one plugin, including its self-described parameter schema when available."""

        def run() -> dict[str, Any]:
            payload = client().get("/api/list_plugin_info/")
            if not plugin_name:
                return payload
            plugins = payload.get("plugins", [])
            if isinstance(plugins, list):
                for plugin in plugins:
                    if isinstance(plugin, dict) and plugin.get("name") == plugin_name:
                        return {"status": "success", "plugin": plugin}
            return {"status": "error", "message": f"Plugin not found: {plugin_name}"}

        return _call("describe_plugin", run)

    @mcp.tool()
    def list_groups() -> dict[str, Any]:
        """List configured exploit plugin groups."""

        return _call("list_groups", lambda: client().get("/api/list_groups/"))

    @mcp.tool()
    def list_device_drivers() -> dict[str, Any]:
        """List available device drivers."""

        return _call("list_device_drivers", lambda: client().get("/api/list_device_drivers/"))

    @mcp.tool()
    def describe_driver(device_name: str) -> dict[str, Any]:
        """Describe a device driver by listing supported commands."""

        path = f"/api/list_device_commands/{quote(device_name, safe='')}/"
        return _call("describe_driver", lambda: client().get(path))

    @mcp.tool()
    def scan_devices(driver_name: str = "all") -> dict[str, Any]:
        """Scan devices through the Django HTTP execution plane."""

        def run() -> dict[str, Any]:
            if driver_name == "all":
                return client().get("/api/scan_all_devices/")
            return client().get(f"/api/scan_device/{quote(driver_name, safe='')}/")

        return _call("scan_devices", run)

    @mcp.tool()
    def list_devices() -> dict[str, Any]:
        """List devices known to the Django backend."""

        return _call("list_devices", lambda: client().get("/api/list_devices/"))

    @mcp.tool()
    def device_info() -> dict[str, Any]:
        """Return device information from the Django backend."""

        return _call("device_info", lambda: client().get("/api/device_info/"))

    @mcp.tool()
    def get_driver_states() -> dict[str, Any]:
        """Return enabled/disabled state for device drivers."""

        return _call("get_driver_states", lambda: client().get("/api/get_driver_states/"))

    @mcp.tool()
    def list_targets() -> dict[str, Any]:
        """List configured IoTSploit targets, one summary row each.

        Facet bulk (CAN frames and the like) is omitted and reported as counts.
        Call get_target for the whole object.
        """

        return _call("list_targets", lambda: client().get("/api/list_targets/"))

    @mcp.tool()
    def get_target(target_id: str) -> dict[str, Any]:
        """Return one IoTSploit target in full, including every facet payload."""

        return _call(
            "get_target",
            lambda: client().get(f"/api/get_target/{quote(target_id, safe='')}/"),
        )

    @mcp.tool()
    def get_current_target() -> dict[str, Any]:
        """Return the currently selected IoTSploit target."""

        return _call("get_current_target", lambda: client().get("/api/get_current_target/"))

    @mcp.tool()
    def firmware_list() -> dict[str, Any]:
        """List registered firmware entries."""

        return _call("firmware_list", lambda: client().get("/api/firmware/list/"))

    @mcp.tool()
    def firmware_info(name: str) -> dict[str, Any]:
        """Return metadata for one registered firmware entry."""

        return _call("firmware_info", lambda: client().get(f"/api/firmware/{quote(name, safe='')}/"))

    @mcp.tool()
    def fuzzer_campaign_status(campaign_id: str) -> dict[str, Any]:
        """Return IoT fuzzer campaign status."""

        return _call(
            "fuzzer_campaign_status",
            lambda: client().get("/api/iot-fuzzer/testing/campaign/status/", params={"campaign_id": campaign_id}),
        )

    @mcp.tool()
    def fuzzer_campaign_statistics(campaign_id: str) -> dict[str, Any]:
        """Return IoT fuzzer campaign statistics."""

        return _call(
            "fuzzer_campaign_statistics",
            lambda: client().get("/api/iot-fuzzer/testing/statistics/", params={"campaign_id": campaign_id}),
        )

    @mcp.tool()
    def fuzzer_results_summary(campaign_id: str) -> dict[str, Any]:
        """Return IoT fuzzer results summary."""

        return _call(
            "fuzzer_results_summary",
            lambda: client().get("/api/iot-fuzzer/results/analysis/summary/", params={"campaign_id": campaign_id}),
        )

    @mcp.tool()
    def fuzzer_artifacts(campaign_id: str) -> dict[str, Any]:
        """Return IoT fuzzer crash/anomaly artifacts."""

        return _call(
            "fuzzer_artifacts",
            lambda: client().get("/api/iot-fuzzer/results/artifacts/", params={"campaign_id": campaign_id}),
        )

    @mcp.tool()
    def get_tools_status() -> dict[str, Any]:
        """Return IoTSploit host tool installation/status information."""

        return _call("get_tools_status", lambda: client().get("/api/tools_status/"))

    @mcp.tool()
    def get_tool_details(tool_name: str) -> dict[str, Any]:
        """Return details for one IoTSploit host tool."""

        return _call("get_tool_details", lambda: client().get(f"/api/tools/{quote(tool_name, safe='')}/"))

    @mcp.tool()
    def list_files(category: str = "") -> dict[str, Any]:
        """List uploaded files in the Django-managed upload area."""

        params = {"category": category} if category else None
        return _call("list_files", lambda: client().get("/api/list_files/", params=params))
