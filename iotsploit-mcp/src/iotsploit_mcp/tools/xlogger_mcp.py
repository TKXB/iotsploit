from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


LOG_FORMATS = {
    "standard": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    "compact": "%(levelname)s | %(message)s",
    "plain": "%(message)s",
}


@dataclass(frozen=True)
class _MCPLogConfig:
    fmt: str = LOG_FORMATS["standard"]
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    default_level: int = logging.INFO
    default_log_dir: str = "/tmp/sat_logs"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_level(default: int) -> int:
    v = (os.getenv("IOTSPLOIT_MCP_LOG_LEVEL") or "").strip().upper()
    if not v:
        return default
    return getattr(logging, v, default)


def _env_format(default: str = "standard") -> str:
    v = (os.getenv("IOTSPLOIT_MCP_LOG_FORMAT") or "").strip().lower()
    if not v:
        return default
    if v not in LOG_FORMATS:
        return default
    return v


def _safe_filename(name: str) -> str:
    # Keep it deterministic and filesystem-safe.
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in name).replace(".", "_")


class XLoggerMCP:
    """
    MCP 组件专用 logger：
    - 不依赖 Django/Channels
    - 不调用 logging.basicConfig（避免污染宿主进程）
    - 默认格式：YYYY-mm-dd HH:MM:SS | LEVEL | name | message
    - 支持按需写文件（可通过参数或 env 开关）
    """

    _instance: Optional["XLoggerMCP"] = None

    def __new__(cls) -> "XLoggerMCP":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._cfg = _MCPLogConfig(
            fmt=LOG_FORMATS[_env_format()],
            default_level=_env_level(_MCPLogConfig.default_level),
        )
        self._loggers: Dict[str, logging.Logger] = {}

    def get_logger(
        self,
        name: str = "iotsploit_mcp",
        *,
        level: Optional[int] = None,
        to_file: Optional[bool] = None,
        file_path: Optional[str] = None,
    ) -> logging.Logger:
        lvl = self._cfg.default_level if level is None else level
        want_file = _env_bool("IOTSPLOIT_MCP_LOG_TO_FILE", False) if to_file is None else bool(to_file)

        # Global override: send all MCP logs to a single file if provided.
        env_log_file = (os.getenv("IOTSPLOIT_MCP_LOG_FILE") or "").strip() or None
        env_log_dir = (os.getenv("IOTSPLOIT_MCP_LOG_DIR") or "").strip() or None

        logger = self._loggers.get(name) or logging.getLogger(name)
        logger.setLevel(lvl)

        stream_formatter = logging.Formatter(self._cfg.fmt, datefmt=self._cfg.datefmt)
        file_formatter = logging.Formatter(LOG_FORMATS["standard"], datefmt=self._cfg.datefmt)

        # Ensure stream handler exists (stderr).
        if not any(getattr(h, "_mcp_stream", False) for h in logger.handlers):
            sh = logging.StreamHandler(sys.stderr)
            sh.setLevel(lvl)
            sh.setFormatter(stream_formatter)
            setattr(sh, "_mcp_stream", True)
            logger.addHandler(sh)

        # File handler is optional and can be enabled later.
        if want_file:
            target_file = (
                file_path
                or env_log_file
                or str(Path(env_log_dir or self._cfg.default_log_dir) / f"{_safe_filename(name)}.log")
            )

            if not any(getattr(h, "_mcp_file", None) == target_file for h in logger.handlers):
                Path(target_file).parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(target_file)
                fh.setLevel(logging.DEBUG)
                fh.setFormatter(file_formatter)
                setattr(fh, "_mcp_file", target_file)
                logger.addHandler(fh)

        logger.propagate = False
        self._loggers[name] = logger
        return logger

    # Convenience wrappers (optional, mirrors iotsploit_django.tools.xlogger)
    def debug(self, msg: str, name: str = "iotsploit_mcp", **kwargs) -> None:
        self.get_logger(name).debug(msg, **kwargs)

    def info(self, msg: str, name: str = "iotsploit_mcp", **kwargs) -> None:
        self.get_logger(name).info(msg, **kwargs)

    def warning(self, msg: str, name: str = "iotsploit_mcp", **kwargs) -> None:
        self.get_logger(name).warning(msg, **kwargs)

    def error(self, msg: str, name: str = "iotsploit_mcp", **kwargs) -> None:
        self.get_logger(name).error(msg, **kwargs)

    def critical(self, msg: str, name: str = "iotsploit_mcp", **kwargs) -> None:
        self.get_logger(name).critical(msg, **kwargs)


# Global instance
xlog_mcp = XLoggerMCP()

