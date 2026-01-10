"""
Deprecated: 请使用 iotsploit_core.utils

此模块保留用于向后兼容（Django 内部及部分插件仍在 import）。
新代码建议直接使用：
    from iotsploit_core.utils import IotsException, IotsErrorCode, IotsResult, abort, fail
"""

from __future__ import annotations

import logging
import time
import warnings
from typing import Any

from iotsploit_core.utils.exceptions import (
    IotsErrorCode,
    IotsException,
    abort,
    fail,
    user_cancel,
    user_confirm,
)

logger = logging.getLogger(__name__)


class SAT_Exception(Exception):
    """
    Legacy SAT 异常（仅用于兼容旧代码）。

    说明：历史代码会依赖 err_code/err_msg，以及 err_code 的区间判断：
    - FAIL__ERRORCODE__START = -10000
    - ERROR__ERRORCODE__START = 0
    - ok: err_code = 1
    """

    ERROR__ERRORCODE__START = 0
    FAIL__ERRORCODE__START = -10000

    def __init__(self, err_code: int, err_msg: str) -> None:
        super().__init__(err_msg)
        self.err_code = err_code
        self.err_msg = err_msg
        logger.error(err_msg)

# 兼容别名（旧代码可能引用）
ErrorCode = IotsErrorCode


def raise_err(err_msg: str) -> None:
    """Deprecated: 请使用 abort() 或抛出 IotsException。"""

    warnings.warn("raise_err is deprecated, use abort() instead", DeprecationWarning, stacklevel=2)
    raise SAT_Exception(SAT_Exception.ERROR__ERRORCODE__START - 1, err_msg)


def raise_ok(err_msg: str) -> None:
    """
    Deprecated: 推荐用返回值表示成功（IotsResult.ok）。
    兼容：仍保留“抛异常表示成功/确认”的历史行为。
    """

    warnings.warn("raise_ok is deprecated, use IotsResult.ok() instead", DeprecationWarning, stacklevel=2)
    raise SAT_Exception(1, err_msg)


def raise_no(err_msg: str) -> None:
    """Deprecated: 请使用 fail()。"""

    warnings.warn("raise_no is deprecated, use fail() instead", DeprecationWarning, stacklevel=2)
    raise SAT_Exception(SAT_Exception.FAIL__ERRORCODE__START - 1, err_msg)


def sat_sleep(second: float) -> None:
    """Deprecated: 请直接使用 time.sleep() 或 iotsploit_core.utils.sleep()。"""

    warnings.warn("sat_sleep is deprecated, use iotsploit_core.utils.sleep() instead", DeprecationWarning, stacklevel=2)
    time.sleep(second)


def calculate_time_difference(before: Any, after: Any) -> str:
    """Deprecated: 推荐用 iotsploit_core.utils.format_duration()。"""

    warnings.warn(
        "calculate_time_difference is deprecated, use iotsploit_core.utils.format_duration() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    diff = after - before
    hours = diff.seconds // 3600
    minutes = (diff.seconds // 60) % 60
    seconds = diff.seconds % 60
    return "{}小时{}分{}秒".format(hours, minutes, seconds)


__all__ = [
    # legacy SAT API
    "SAT_Exception",
    "raise_err",
    "raise_ok",
    "raise_no",
    "sat_sleep",
    "calculate_time_difference",
    # new API exposure (convenience)
    "IotsException",
    "IotsErrorCode",
    "ErrorCode",
    "abort",
    "fail",
    "user_cancel",
    "user_confirm",
]