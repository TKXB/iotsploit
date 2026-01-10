from __future__ import annotations

import time
from datetime import timedelta
from typing import Union


def sleep(seconds: float) -> None:
    """休眠指定秒数（保留用于未来可测试/可中断封装）。"""

    time.sleep(seconds)


def format_duration(duration: Union[timedelta, float, int], style: str = "compact") -> str:
    """
    格式化时间间隔。

    Args:
        duration: timedelta 或秒数
        style:
            - "compact": "2h 30m 15s"
            - "full": "2 hours 30 minutes 15 seconds"
            - "chinese": "2小时30分15秒"
    """

    if isinstance(duration, (int, float)):
        duration = timedelta(seconds=float(duration))

    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if style == "compact":
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    if style == "full":
        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        return " ".join(parts)

    if style == "chinese":
        parts = []
        if hours:
            parts.append(f"{hours}小时")
        if minutes:
            parts.append(f"{minutes}分")
        if seconds or not parts:
            parts.append(f"{seconds}秒")
        return "".join(parts)

    raise ValueError(f"Unknown style: {style}")


