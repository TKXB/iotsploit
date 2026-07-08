import importlib
import logging

import iotsploit_mcp.tools.xlogger_mcp as xlogger_mcp


def test_mcp_log_format_env_changes_stream_only(monkeypatch, tmp_path):
    monkeypatch.setenv("IOTSPLOIT_MCP_LOG_FORMAT", "plain")
    module = importlib.reload(xlogger_mcp)

    logger = module.XLoggerMCP().get_logger(
        "test_mcp_log_format_env_changes_stream_only",
        to_file=True,
        file_path=str(tmp_path / "mcp.log"),
    )

    stream_handlers = [handler for handler in logger.handlers if getattr(handler, "_mcp_stream", False)]
    file_handlers = [handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)]

    assert stream_handlers
    assert file_handlers
    assert stream_handlers[0].formatter._fmt == "%(message)s"
    assert file_handlers[0].formatter._fmt == "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    monkeypatch.delenv("IOTSPLOIT_MCP_LOG_FORMAT")
    importlib.reload(module)
