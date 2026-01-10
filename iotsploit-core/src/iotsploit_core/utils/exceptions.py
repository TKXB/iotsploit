from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, Optional


class IotsErrorCode(IntEnum):
    """IoTSploit 统一错误码枚举（给新代码使用）。"""

    # 成功 (1-99)
    SUCCESS = 1

    # 用户操作 (100-199)
    USER_CANCELLED = 100
    USER_CONFIRMED = 101
    USER_TIMEOUT = 102

    # 配置/参数错误 (200-299)
    INVALID_PARAMETER = 200
    MISSING_PARAMETER = 201
    INVALID_CONFIG = 202

    # 设备错误 (300-399)
    DEVICE_NOT_FOUND = 300
    DEVICE_NOT_CONNECTED = 301
    DEVICE_BUSY = 302
    DEVICE_TIMEOUT = 303
    DEVICE_ERROR = 304

    # 网络错误 (400-499)
    NETWORK_ERROR = 400
    CONNECTION_REFUSED = 401
    CONNECTION_TIMEOUT = 402
    HOST_UNREACHABLE = 403

    # 执行错误 (500-599)
    EXECUTION_FAILED = 500
    COMMAND_FAILED = 501
    PERMISSION_DENIED = 502
    RESOURCE_NOT_FOUND = 503

    # 系统错误 (900-999)
    INTERNAL_ERROR = 900
    NOT_IMPLEMENTED = 901
    DEPENDENCY_MISSING = 902


class IotsException(Exception):
    """
    IoTSploit 统一异常基类（给新代码使用）。

    为了兼容历史代码，也提供 err_code/err_msg 属性：
    - err_code == code.value
    - err_msg == message
    """

    def __init__(
        self,
        code: IotsErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: Dict[str, Any] = details or {}
        self.recoverable = recoverable

    @property
    def err_code(self) -> int:
        return int(self.code.value)

    @property
    def err_msg(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": int(self.code.value),
            "error_name": self.code.name,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}(code={self.code.name}, message={self.message!r})"


class IotsUserException(IotsException):
    """用户交互相关异常（取消、超时等）"""


class IotsDeviceException(IotsException):
    """设备操作相关异常"""


class IotsNetworkException(IotsException):
    """网络操作相关异常"""


class IotsExecutionException(IotsException):
    """执行/命令相关异常"""


class IotsConfigException(IotsException):
    """配置/参数相关异常"""


def abort(message: str, code: IotsErrorCode = IotsErrorCode.EXECUTION_FAILED, **details: Any) -> None:
    """中止当前操作（抛出不可恢复异常）。"""

    raise IotsException(code, message, details=details, recoverable=False)


def fail(message: str, code: IotsErrorCode = IotsErrorCode.EXECUTION_FAILED, **details: Any) -> None:
    """标记操作失败（抛出可恢复异常，上层可选择重试）。"""

    raise IotsException(code, message, details=details, recoverable=True)


def user_cancel(message: str = "Operation cancelled by user") -> None:
    raise IotsUserException(IotsErrorCode.USER_CANCELLED, message, recoverable=False)


def user_confirm(message: str = "User confirmed") -> None:
    """
    兼容用途：用异常跳出“确认流程”。
    新代码更推荐用返回值（IotsResult）表达成功。
    """

    raise IotsUserException(IotsErrorCode.USER_CONFIRMED, message, recoverable=False)


