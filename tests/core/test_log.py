"""Tests del sistema unico de logs (src/core/log.py).

Comprueban con el modulo logging real:
- get_logger devuelve un logging.Logger estandar con el nombre pedido;
- setup_logging escribe en consola y en el fichero indicado, con el nombre del
  logger sin el prefijo "src.";
- el fichero recibe tambien DEBUG aunque la consola tenga un nivel mayor;
- llamar varias veces no duplica los handlers;
- un nivel no valido no rompe la configuracion.

El fichero de log se crea en una carpeta temporal.
"""

import logging

import pytest

from src.core.log import get_logger, setup_logging


@pytest.fixture(autouse=True)
def _restaurar_logging(logging_habilitado):
    # logging_habilitado (tests/conftest.py): otros modulos de la suite dejan
    # logging.disable(CRITICAL) activo; aqui se comprueba el logging real.
    raiz = logging.getLogger()
    handlers, nivel = list(raiz.handlers), raiz.level
    yield
    for handler in list(raiz.handlers):
        if handler not in handlers:
            raiz.removeHandler(handler)
            handler.close()
    raiz.setLevel(nivel)


def _handlers_propios():
    return [h for h in logging.getLogger().handlers if getattr(h, "_jarvis_handler", False)]


def test_get_logger_es_logger_estandar():
    logger = get_logger("src.hands.apps.prueba")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "src.hands.apps.prueba"


def test_setup_escribe_en_fichero_con_nombre_corto(tmp_path, capsys):
    destino = tmp_path / "logs" / "jarvis.log"
    ruta = setup_logging(level="INFO", log_file=destino)
    assert ruta == destino

    logger = get_logger("src.hands.apps.prueba_fichero")
    logger.info("Abriendo %s", "chrome")
    logger.debug("detalle interno")
    for handler in _handlers_propios():
        handler.flush()

    contenido = destino.read_text(encoding="utf-8")
    assert "hands.apps.prueba_fichero" in contenido
    assert "src.hands.apps.prueba_fichero" not in contenido
    assert "Abriendo chrome" in contenido
    assert "detalle interno" in contenido  # el fichero guarda DEBUG

    salida = capsys.readouterr().out
    assert "Abriendo chrome" in salida
    assert "detalle interno" not in salida  # la consola respeta el nivel INFO


def test_setup_repetido_no_duplica_handlers(tmp_path):
    setup_logging(level="INFO", log_file=tmp_path / "a.log")
    setup_logging(level="INFO", log_file=tmp_path / "b.log")
    assert len(_handlers_propios()) == 2  # consola + fichero


def test_sin_fichero_y_nivel_invalido(tmp_path):
    assert setup_logging(level="NO_EXISTE", log_file="") is None
    consola = [h for h in _handlers_propios() if not isinstance(h, logging.FileHandler)]
    assert len(consola) == 1
    assert consola[0].level == logging.INFO
