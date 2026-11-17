"""Tests del formato de mensajes de las funciones log_jarvis_*.

Comprueban que log_jarvis_info/warning/error/performance aceptan argumentos
posicionales al estilo de logging ("%s" % args), como hace main.py, y que un
formato que no encaja con los argumentos no lanza excepcion.

Se sustituye solo el destino final (el sistema de logging global) para leer el
mensaje formateado; la funcion de formato y los envoltorios son los reales.
"""

import pytest

from src.experimental import jarvis_logging_system as jls


class _Recolector:
    def __init__(self):
        self.mensajes = []

    def _guardar(self, message, **kwargs):
        self.mensajes.append(message)

    log_info = log_warning = log_error = log_performance = _guardar


@pytest.fixture
def recolector(monkeypatch):
    destino = _Recolector()
    monkeypatch.setattr(jls, "jarvis_logging_system", destino)
    return destino


class TestFormatoMensaje:
    def test_sin_argumentos_no_formatea(self):
        assert jls._format_log_message("100% listo", ()) == "100% listo"

    def test_formato_con_argumentos(self):
        assert jls._format_log_message("%d volumen(es) (%s)", (2, "Windows")) == "2 volumen(es) (Windows)"

    def test_formato_incorrecto_no_lanza(self):
        assert jls._format_log_message("faltan %s %s", ("a",)) == "faltan %s %s a"

    def test_excepcion_como_argumento(self):
        assert jls._format_log_message("error: %s", (ValueError("x"),)) == "error: x"


class TestEnvoltorios:
    def test_info_con_argumentos_posicionales(self, recolector):
        jls.log_jarvis_info("Progreso: %.1f%% (%d entradas)", 12.5, 300)
        assert recolector.mensajes == ["Progreso: 12.5% (300 entradas)"]

    def test_warning_con_excepcion(self, recolector):
        jls.log_jarvis_warning("No se pudo programar: %s", RuntimeError("fallo"))
        assert recolector.mensajes == ["No se pudo programar: fallo"]

    def test_error_y_performance_sin_argumentos(self, recolector):
        jls.log_jarvis_error("error simple")
        jls.log_jarvis_performance("medida")
        assert recolector.mensajes == ["error simple", "medida"]
