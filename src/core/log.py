"""
Logs de JARVIS: un unico sistema basado en el modulo estandar ``logging``.

Uso en cualquier modulo::

    from src.core.log import get_logger

    logger = get_logger(__name__)
    logger.info("Abriendo %s", nombre)
    logger.warning("No se encontro %s", ruta)
    logger.exception("Fallo al calibrar")   # dentro de un except: incluye la traza

Configuracion (una sola vez, al arrancar; la hace ``main.py``)::

    from src.core.log import setup_logging

    setup_logging()

``setup_logging`` lee la seccion ``logging`` de ``config/config.json``:

- ``level``: nivel minimo que se muestra en la consola (DEBUG, INFO, WARNING...).
- ``log_file``: fichero donde se guarda todo desde DEBUG (por defecto
  ``logs/jarvis.log``, relativo a la raiz del proyecto). Rota al llegar a 5 MB
  y conserva 5 copias.
- ``format`` y ``datefmt``: formato de las lineas del fichero.

Si nadie llama a ``setup_logging`` (por ejemplo, en los tests), los mensajes
siguen el comportamiento por defecto de ``logging``: solo se muestran los de
nivel WARNING o superior por la salida de errores.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Union

CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
CONSOLE_DATEFMT = "%H:%M:%S"
DEFAULT_FILE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"
MAX_FILE_BYTES = 5 * 1024 * 1024
FILE_BACKUPS = 5

# Librerias externas que solo deben aparecer cuando avisan de algo.
NOISY_LIBRARIES = (
    "asyncio", "httpcore", "httpx", "urllib3", "PIL", "matplotlib",
    "faster_whisper", "ctranslate2", "huggingface_hub", "filelock",
    "comtypes", "pywinauto", "werkzeug", "engineio", "socketio",
)

_HANDLER_MARK = "_jarvis_handler"


class _ShortNameFilter(logging.Filter):
    """Quita el prefijo ``src.`` del nombre del logger para que se lea mejor."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("src."):
            record.name = record.name[4:]
        return True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Devuelve el logger de un modulo. Usar siempre ``get_logger(__name__)``."""
    return logging.getLogger(name)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_level(level: Union[str, int, None], default: int) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str) and level.strip():
        value = logging.getLevelName(level.strip().upper())
        if isinstance(value, int):
            return value
    return default


def setup_logging(
    level: Union[str, int, None] = None,
    log_file: Union[str, Path, None] = None,
    console: bool = True,
) -> Optional[Path]:
    """Configura la salida de logs de todo JARVIS. Se puede llamar varias veces.

    Args:
        level: nivel de la consola. Si es ``None`` se usa ``config.json``.
        log_file: fichero de log. Si es ``None`` se usa ``config.json``; una
            cadena vacia desactiva el fichero.
        console: si es ``False`` no se escribe en la consola.

    Returns:
        Ruta absoluta del fichero de log, o ``None`` si no hay fichero.
    """
    from src.core.config import get_logging_config  # import local: config usa este modulo

    cfg = get_logging_config()
    console_level = _parse_level(level if level is not None else cfg.level, logging.INFO)
    file_setting = cfg.log_file if log_file is None else log_file

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(logging.DEBUG)

    short_names = _ShortNameFilter()
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, CONSOLE_DATEFMT))
        console_handler.addFilter(short_names)
        setattr(console_handler, _HANDLER_MARK, True)
        root.addHandler(console_handler)

    log_path: Optional[Path] = None
    if file_setting:
        log_path = Path(file_setting)
        if not log_path.is_absolute():
            log_path = _project_root() / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=MAX_FILE_BYTES, backupCount=FILE_BACKUPS, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(cfg.format or DEFAULT_FILE_FORMAT, cfg.datefmt or DEFAULT_FILE_DATEFMT)
        )
        file_handler.addFilter(short_names)
        setattr(file_handler, _HANDLER_MARK, True)
        root.addHandler(file_handler)

    for name in NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_path
