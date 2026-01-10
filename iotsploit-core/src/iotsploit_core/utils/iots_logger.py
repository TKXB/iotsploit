from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

try:
    import colorlog  # type: ignore

    _HAS_COLORLOG = True
except Exception:
    _HAS_COLORLOG = False


class IotsLogger:
    """
    IoTSploit Core Logger（不依赖 Django）。

    - 默认输出格式：`YYYY-mm-dd HH:MM:SS | LEVEL | name | msg`
    - 若安装了 colorlog 且处于 TTY，则启用彩色输出
    """

    _instance: Optional["IotsLogger"] = None
    _lock = threading.Lock()

    LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    COLOR_FORMAT = "%(log_color)s%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    LOG_COLORS = {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    }

    def __new__(cls) -> "IotsLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_once()
        return cls._instance

    def _init_once(self) -> None:
        self._loggers: Dict[str, logging.Logger] = {}
        self._extra_handlers: List[logging.Handler] = []
        self._use_color = _HAS_COLORLOG and self._is_tty()
        self._default_level = self._get_env_level()

    @staticmethod
    def _is_tty() -> bool:
        try:
            return sys.stderr.isatty()
        except Exception:
            return False

    @staticmethod
    def _get_env_level() -> int:
        level_str = os.getenv("IOTSPLOIT_LOG_LEVEL", "INFO").upper()
        return getattr(logging, level_str, logging.INFO)

    def get_logger(self, name: str = "iotsploit", level: Optional[int] = None) -> logging.Logger:
        """
        获取（或创建）一个已配置好的 logger。

        约定：
        - name 会被统一加前缀 `iots.`，避免与外部项目 logger 冲突
        - logger.propagate = False，防止重复输出
        """
        with self._lock:
            if name not in self._loggers:
                logger = logging.getLogger(f"iots.{name}")
                logger.setLevel(level or self._default_level)
                logger.propagate = False

                for h in logger.handlers[:]:
                    logger.removeHandler(h)

                logger.addHandler(self._create_console_handler())

                for h in self._extra_handlers:
                    if h not in logger.handlers:
                        logger.addHandler(h)

                self._loggers[name] = logger

            return self._loggers[name]

    def _create_console_handler(self) -> logging.Handler:
        if self._use_color and _HAS_COLORLOG:
            handler = colorlog.StreamHandler(sys.stderr)  # type: ignore[name-defined]
            handler.setFormatter(
                colorlog.ColoredFormatter(  # type: ignore[name-defined]
                    self.COLOR_FORMAT,
                    datefmt=self.LOG_DATE_FORMAT,
                    log_colors=self.LOG_COLORS,
                )
            )
            return handler

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(self.LOG_FORMAT, datefmt=self.LOG_DATE_FORMAT))
        return handler

    def add_handler(self, handler: logging.Handler) -> None:
        """为所有已创建的 logger 注入额外 handler。"""
        with self._lock:
            if handler in self._extra_handlers:
                return
            self._extra_handlers.append(handler)
            for logger in self._loggers.values():
                if handler not in logger.handlers:
                    logger.addHandler(handler)

    def remove_handler(self, handler: logging.Handler) -> None:
        with self._lock:
            if handler not in self._extra_handlers:
                return
            self._extra_handlers.remove(handler)
            for logger in self._loggers.values():
                if handler in logger.handlers:
                    logger.removeHandler(handler)

    def set_level(self, level: str, name: Optional[str] = None) -> None:
        """设置日志级别：指定 name 仅影响单个 logger，否则设置全局默认并同步已创建 logger。"""
        level = level.upper()
        level_value = getattr(logging, level, None)
        if not isinstance(level_value, int):
            return

        with self._lock:
            if name:
                self.get_logger(name).setLevel(level_value)
            else:
                self._default_level = level_value
                for logger in self._loggers.values():
                    logger.setLevel(level_value)

    def debug(self, msg: str, name: str = "iotsploit", **kwargs: Any) -> None:
        self.get_logger(name).debug(msg, **kwargs)

    def info(self, msg: str, name: str = "iotsploit", **kwargs: Any) -> None:
        self.get_logger(name).info(msg, **kwargs)

    def warning(self, msg: str, name: str = "iotsploit", **kwargs: Any) -> None:
        self.get_logger(name).warning(msg, **kwargs)

    def error(self, msg: str, name: str = "iotsploit", **kwargs: Any) -> None:
        self.get_logger(name).error(msg, **kwargs)

    def critical(self, msg: str, name: str = "iotsploit", **kwargs: Any) -> None:
        self.get_logger(name).critical(msg, **kwargs)


iots_logger = IotsLogger()


def get_logger(name: str = "iotsploit") -> logging.Logger:
    """便捷函数：`get_logger("plugin_foo")` 等价于 `iots_logger.get_logger("plugin_foo")`。"""
    return iots_logger.get_logger(name)