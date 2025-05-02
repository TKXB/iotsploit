import logging
import colorlog
from typing import Optional
from datetime import datetime

class _ConsoleBufferWSHandler(logging.Handler):
    """Push log records to console_log_buffer and broadcast to WebSocket."""
    def emit(self, record: logging.LogRecord):  # type: ignore[override]
        try:
            # Lazy imports to avoid early Django initialisation issues
            from sat_toolkit.consumers import console_log_buffer, log_buffer_lock
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

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._ensure_root_handler()

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
            handler.setFormatter(colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s | %(levelname)s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            ))
            
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