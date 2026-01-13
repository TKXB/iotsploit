"""
iotsploit_core.utils

说明：
- 该包必须保持“零 Django 依赖”，供 plugins / commands / MCP / CLI 直接使用
- 日志：使用 `iots_logger`（IotsLogger 单例）提供统一格式的 logger
"""

from __future__ import annotations

from .iots_logger import IotsLogger, get_logger, iots_logger
from .exceptions import (
    IotsErrorCode,
    IotsException,
    IotsUserException,
    IotsDeviceException,
    IotsNetworkException,
    IotsExecutionException,
    IotsConfigException,
    NotSupportedError,
    abort,
    fail,
    user_cancel,
    user_confirm,
)
from .result import IotsResult
from .helpers import sleep, format_duration

__all__ = [
    # error codes / exceptions (new)
    "IotsErrorCode",
    "IotsException",
    "IotsUserException",
    "IotsDeviceException",
    "IotsNetworkException",
    "IotsExecutionException",
    "IotsConfigException",
    "NotSupportedError",
    "abort",
    "fail",
    "user_cancel",
    "user_confirm",
    # result
    "IotsResult",
    # helpers
    "sleep",
    "format_duration",
    "IotsLogger",
    "iots_logger",
    "get_logger",
]


