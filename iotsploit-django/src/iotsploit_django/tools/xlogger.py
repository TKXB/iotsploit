import logging
import os
import colorlog
from typing import Optional
from datetime import datetime

class _ConsoleBufferWSHandler(logging.Handler):
    """Push log records to console_log_buffer and broadcast to WebSocket."""
    def emit(self, record: logging.LogRecord):  # type: ignore[override]
        try:
            # Lazy imports to avoid early Django initialisation issues
            from iotsploit_django.consumers import console_log_buffer, log_buffer_lock
            from channels.layers import get_channel_layer  # pylint: disable=import-error
            from asgiref.sync import async_to_sync           # pylint: disable=import-error

            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
            formatted = f"{timestamp} | {record.levelname} | {record.name} | {record.getMessage()}"

            with log_buffer_lock:
                console_log_buffer.append(formatted)

            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "console_logs",
                    {"type": "console_log", "message": formatted},
                )
        except Exception:
            # Never break the logging chain
            pass


class XLogger:
    _instance = None
    _loggers = {}  # 存储不同模块的logger
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    LOG_FORMATS = {
        "standard": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "compact": "%(levelname)s | %(message)s",
        "plain": "%(message)s",
    }
    COLOR_LOG_FORMATS = {
        "standard": "%(log_color)s%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "compact": "%(log_color)s%(levelname)s | %(message)s",
        "plain": "%(log_color)s%(message)s",
    }
    LOG_COLORS = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._default_format = self._get_env_format()
            self._ensure_root_handler()
            self._set_existing_stream_formatters()

    @classmethod
    def _get_env_format(cls):
        fmt = os.getenv("IOTSPLOIT_LOG_FORMAT", "standard").strip().lower()
        if fmt not in cls.COLOR_LOG_FORMATS:
            return "standard"
        return fmt

    def _ensure_root_handler(self):
        root = logging.getLogger()
        if not any(isinstance(h, _ConsoleBufferWSHandler) for h in root.handlers):
            root.addHandler(_ConsoleBufferWSHandler())

    def get_logger(self, name: str = 'console'):
        """Get or create a logger for the specified name"""
        if name not in self._loggers:
            # 创建新的logger
            logger = logging.getLogger(name)
            logger.setLevel(logging.INFO)
            
            # 确保没有重复的handler
            if logger.handlers:
                for handler in logger.handlers:
                    logger.removeHandler(handler)
            
            # 创建并配置handler
            handler = colorlog.StreamHandler()
            setattr(handler, "_xlog_stream", True)
            self._set_stream_formatter(handler)
            
            # 添加handler到logger
            logger.addHandler(handler)
            # Attach WS handler once
            if not any(isinstance(h, _ConsoleBufferWSHandler) for h in logger.handlers):
                logger.addHandler(_ConsoleBufferWSHandler())
            logger.propagate = False
            
            # 存储logger
            self._loggers[name] = logger
        
        return self._loggers[name]

    def debug(self, msg: str, name: str = 'console', **kwargs):
        """Log a debug message with optional kwargs (exc_info, stack_info, stacklevel, extra)"""
        self.get_logger(name).debug(msg, **kwargs)

    def info(self, msg: str, name: str = 'console', **kwargs):
        """Log an info message with optional kwargs (exc_info, stack_info, stacklevel, extra)"""
        self.get_logger(name).info(msg, **kwargs)

    def warning(self, msg: str, name: str = 'console', **kwargs):
        """Log a warning message with optional kwargs (exc_info, stack_info, stacklevel, extra)"""
        self.get_logger(name).warning(msg, **kwargs)

    def error(self, msg: str, name: str = 'console', **kwargs):
        """Log an error message with optional kwargs (exc_info, stack_info, stacklevel, extra)"""
        self.get_logger(name).error(msg, **kwargs)

    def critical(self, msg: str, name: str = 'console', **kwargs):
        """Log a critical message with optional kwargs (exc_info, stack_info, stacklevel, extra)"""
        self.get_logger(name).critical(msg, **kwargs)

    def _set_stream_formatter(self, handler):
        handler.setFormatter(colorlog.ColoredFormatter(
            self.COLOR_LOG_FORMATS[self._default_format],
            datefmt=self.LOG_DATE_FORMAT,
            log_colors=self.LOG_COLORS
        ))

    def _set_plain_stream_formatter(self, handler):
        handler.setFormatter(logging.Formatter(
            self.LOG_FORMATS[self._default_format],
            datefmt=self.LOG_DATE_FORMAT
        ))

    def _iter_existing_handlers(self):
        yield from logging.getLogger().handlers
        for logger_obj in logging.Logger.manager.loggerDict.values():
            if isinstance(logger_obj, logging.Logger):
                yield from logger_obj.handlers

    def _set_existing_stream_formatters(self):
        for handler in self._iter_existing_handlers():
            if isinstance(handler, _ConsoleBufferWSHandler):
                continue
            if isinstance(handler, logging.FileHandler):
                continue
            if getattr(handler, "_xlog_stream", False):
                self._set_stream_formatter(handler)
            elif isinstance(handler, logging.StreamHandler):
                self._set_plain_stream_formatter(handler)

    def set_format(self, fmt: str):
        """Set terminal logging format without changing the WebSocket console handler."""
        fmt = fmt.strip().lower()
        if fmt not in self.COLOR_LOG_FORMATS:
            return

        self._default_format = fmt
        self._set_existing_stream_formatters()

    def set_level(self, level: str, name: str = 'console'):
        """Set logging level"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            self.get_logger(name).setLevel(level_map[level.upper()])

# Global instance
xlog = XLogger()
