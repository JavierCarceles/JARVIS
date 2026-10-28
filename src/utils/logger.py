"""
Nuevo sistema de logging estructurado para Jarvis.
Basado en mejores prácticas de Python 2024.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Union


# Atributos reservados de logging.LogRecord: no pueden enviarse en `extra`.
_RESERVED_LOG_RECORD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class StructuredLogger:
    """Logger estructurado con soporte para JSON y mejores prácticas."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Evitar duplicados de handlers
        if not self.logger.handlers:
            # Console handler con formato JSON
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            
            # Formateador JSON
            json_formatter = JsonFormatter()
            console_handler.setFormatter(json_formatter)
            
            self.logger.addHandler(console_handler)
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log de nivel DEBUG."""
        self._log(logging.DEBUG, message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Log de nivel INFO."""
        self._log(logging.INFO, message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log de nivel WARNING."""
        self._log(logging.WARNING, message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Log de nivel ERROR."""
        self._log(logging.ERROR, message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs) -> None:
        """Log de nivel CRITICAL."""
        self._log(logging.CRITICAL, message, *args, **kwargs)
    
    # Alias en mayúsculas: el logging estándar de Python expone los niveles
    # como constantes (logging.ERROR) y el código legacy los usa como método
    # (logger.ERROR(...)). Sin estos alias, esas llamadas lanzan AttributeError.
    DEBUG = debug
    INFO = info
    WARNING = warning
    ERROR = error
    CRITICAL = critical
    
    def _log(self, level: int, message: str, *args, **kwargs) -> None:
        """Log interno con contexto."""
        exc_info = kwargs.pop("exc_info", None)
        extra = {
            key: value
            for key, value in kwargs.items()
            if key not in _RESERVED_LOG_RECORD_ATTRIBUTES
        }
        extra['logger_name'] = self.name
        
        self.logger.log(level, message, *args, exc_info=exc_info, extra=extra)
    
    def _print_log(self, level: str, message: str, file_name: str = None, method_name: str = None, method_start_line: str = None) -> None:
        """Método de compatibilidad para logs antiguos."""
        # Formatear mensaje con contexto
        if file_name and method_name and method_start_line:
            context_message = f"{file_name}:{method_name} (linea {method_start_line}): {message}"
        else:
            context_message = message
        
        # Mapear niveles de log
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "SUCCESS": logging.INFO,  # SUCCESS se mapea a INFO
        }
        
        log_level = level_map.get(level.upper() if isinstance(level, str) else level, logging.INFO)
        self._log(log_level, context_message)
    
    def _print_log(self, level: str, message: str, file_name: str = None, method_name: str = None, method_start_line: str = None) -> None:
        """Método compatible con el antiguo logger."""
        # Mapear niveles de string a niveles de logging
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "SUCCESS": logging.INFO  # SUCCESS se mapea a INFO
        }
        
        log_level = level_map.get(level.upper() if isinstance(level, str) else level, logging.INFO)
        
        # Formatear mensaje con contexto
        if file_name or method_name or method_start_line:
            context = f"{file_name}:{method_name} (linea {method_start_line})"
            full_message = f"{message} [{context}]"
        else:
            full_message = message
        
        self._log(log_level, full_message)


class JsonFormatter(logging.Formatter):
    """Formateador que convierte logs a JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Formatear un log record como JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Añadir campos extra
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Añadir contexto adicional si existe
        if hasattr(record, 'exc_info') and record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def get_logger(name: str, level: int = logging.INFO) -> StructuredLogger:
    """Obtener un logger estructurado."""
    return StructuredLogger(name, level)


# Logger predeterminado
logger = get_logger("Jarvis")