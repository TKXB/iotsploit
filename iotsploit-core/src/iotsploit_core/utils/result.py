from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar

from .exceptions import IotsErrorCode, IotsException

T = TypeVar("T")


@dataclass
class IotsResult(Generic[T]):
    """
    IoTSploit 操作结果封装（推荐替代“用异常表示成功/失败”的模式）。
    """

    success: bool
    message: str
    code: IotsErrorCode = IotsErrorCode.SUCCESS
    data: Optional[T] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "Success", data: Optional[T] = None, **details: Any) -> "IotsResult[T]":
        return cls(success=True, message=message, code=IotsErrorCode.SUCCESS, data=data, details=details)

    @classmethod
    def fail(
        cls,
        message: str,
        code: IotsErrorCode = IotsErrorCode.EXECUTION_FAILED,
        **details: Any,
    ) -> "IotsResult[T]":
        return cls(success=False, message=message, code=code, data=None, details=details)

    def raise_if_failed(self) -> T:
        if not self.success:
            raise IotsException(self.code, self.message, details=self.details, recoverable=False)
        return self.data  # type: ignore[return-value]


