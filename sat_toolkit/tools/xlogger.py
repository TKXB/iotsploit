import logging
import colorlog
from typing import Optional
from datetime import datetime

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
            logger.propagate = False
            
            # 存储logger
            self._loggers[name] = logger
        
        return self._loggers[name]

    def debug(self, msg: str, name: str = 'console'):
        self.get_logger(name).debug(msg)

    def info(self, msg: str, name: str = 'console'):
        self.get_logger(name).info(msg)

    def warning(self, msg: str, name: str = 'console'):
        self.get_logger(name).warning(msg)

    def error(self, msg: str, name: str = 'console'):
        self.get_logger(name).error(msg)

    def critical(self, msg: str, name: str = 'console'):
        self.get_logger(name).critical(msg)

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