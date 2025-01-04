import logging
import colorlog
from typing import Optional
from datetime import datetime

class XLogger:
    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is None:
            self._setup_logger()

    def _setup_logger(self):
        """Setup the custom logger with color formatting"""
        self._logger = logging.getLogger('xlogger')
        
        # Prevent log propagation to parent loggers
        self._logger.propagate = False
        
        # Remove any existing handlers
        if self._logger.handlers:
            for handler in self._logger.handlers:
                self._logger.removeHandler(handler)
        
        # Add new color handler with simplified format
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
        self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def debug(self, msg: str):
        formatted_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | DEBUG | {msg}"
        self._logger.debug(formatted_msg)

    def info(self, msg: str):
        formatted_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | INFO | {msg}"
        self._logger.info(formatted_msg)

    def warning(self, msg: str):
        formatted_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WARNING | {msg}"
        self._logger.warning(formatted_msg)

    def error(self, msg: str):
        formatted_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ERROR | {msg}"
        self._logger.error(formatted_msg)

    def critical(self, msg: str):
        formatted_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | CRITICAL | {msg}"
        self._logger.critical(formatted_msg)

    def set_level(self, level: str):
        """Set logging level"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            self._logger.setLevel(level_map[level.upper()])

# Global instance
xlog = XLogger()