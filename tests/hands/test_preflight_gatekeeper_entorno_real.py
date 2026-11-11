# -*- coding: utf-8 -*-
"""
Verificacion en entorno real de la unidad 3.8.5.1.4.7.10.

Valida que todo candidato que se pretenda abrir pase por ApplicationPreflight
y las politicas existentes, rechazando:
- ejecutables desconocidos (no resueltos),
- destinos ambiguos,
- rutas manipuladas (directorios, rutas inexistentes, archivos no ejecutables).

Ademas verifica que destinos reales del sistema (URIs admitidas, ejecutables
reales via validate_launch_destination) pasan el preflight.

No lanza ninguna aplicacion. Solo valida destinos estaticamente.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from src.hands.application_preflight import ApplicationPreflight


def _existe(ruta: str) -> bool:
    return bool(ruta) and os.path.exists(ruta)


class TestPreflightGatekeeperEntornoReal:
    """ApplicationPreflight.check como gatekeeper contra candidatos reales."""

    def setup_method(self, _method=None):
        self.preflight = ApplicationPreflight()

    # ------------------------------------------------------------------
    # URIs admitidas: pasan el preflight (no requieren archivo en disco)
    # ------------------------------------------------------------------

    def test_uri_ms_settings_es_admitida(self):
        """Una URI de esquema admitido (ms-settings) es un destino valido."""
        app = {"name": "Configuracion", "executable": None, "url": "ms-settings:"}
        decision = self.preflight.check(app)
        assert decision["allowed"] is True
        assert decision["blocked_by"] is None

    def test_uri_https_es_admitida(self):
        """Una URI https es un destino de lanzamiento valido."""
        app = {"name": "WebApp", "executable": None, "url": "https://example.com"}
        decision = self.preflight.check(app)
        assert decision["allowed"] is True
        assert decision["blocked_by"] is None

    # ------------------------------------------------------------------
    # Ejecutables desconocidos: deben ser rechazados
    # ------------------------------------------------------------------

    def test_ejecutable_inexistente_es_rechazado(self):
        """Un ejecutable que no existe en disco es rechazado por preflight."""
        app = {"name": "AppFantasma", "executable": None, "url": None}
        decision = self.preflight.check(app)
        assert decision["allowed"] is False
        assert decision["blocked_by"] == "executable_not_resolved"

    def test_nombre_bloqueado_es_rechazado(self):
        """Una aplicacion con nombre administrativo/bloqueado es rechazada."""
        app = {"name": "Task Scheduler", "executable": None, "url": None}
        decision = self.preflight.check(app)
        assert decision["allowed"] is False
        assert decision["blocked_by"] == "blocked_name"

    # ------------------------------------------------------------------
    # Rutas manipuladas / destinos invalidos: deben ser rechazados
    # validate_launch_destination valida rutas directamente
    # ------------------------------------------------------------------

    def test_directorio_no_es_lanzable(self):
        """Una ruta que es un directorio no es un destino de lanzamiento valido."""
        ruta = r"C:\Windows"
        validacion = self.preflight.validate_launch_destination(ruta)
        assert validacion["valid"] is False
        assert "directorio" in validacion["reason"]

    def test_ruta_inexistente_no_es_lanzable(self):
        """Una ruta que no existe en disco es rechazada."""
        ruta = r"C:\No\Existe\ruta_manipulada.exe"
        validacion = self.preflight.validate_launch_destination(ruta)
        assert validacion["valid"] is False
        assert "no existe" in validacion["reason"]

    def test_archivo_txt_no_es_lanzable(self):
        """Un archivo .txt no es un ejecutable valido para lanzamiento."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
            f.write(b"contenido de prueba")
        try:
            validacion = self.preflight.validate_launch_destination(tmp_path)
            assert validacion["valid"] is False
            assert validacion["launch_type"] is None
        finally:
            os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Ejecutables reales del sistema: validos via validate_launch_destination
    # ------------------------------------------------------------------

    def test_notepad_real_es_lanzable(self):
        """notepad.exe es un ejecutable real valido para lanzamiento."""
        ruta = shutil.which("notepad.exe") or r"C:\Windows\System32\notepad.exe"
        if not _existe(ruta):
            pytest.skip("notepad.exe no disponible en este equipo")
        validacion = self.preflight.validate_launch_destination(ruta)
        assert validacion["valid"] is True
        assert validacion["launch_type"] == "ejecutable"

    def test_calc_real_es_lanzable(self):
        """calc.exe es un ejecutable real valido para lanzamiento."""
        ruta = shutil.which("calc.exe") or r"C:\Windows\System32\calc.exe"
        if not _existe(ruta):
            pytest.skip("calc.exe no disponible en este equipo")
        validacion = self.preflight.validate_launch_destination(ruta)
        assert validacion["valid"] is True
        assert validacion["launch_type"] == "ejecutable"


class TestAppKnowledgeToPreflightDictEntornoReal:
    """Verifica que la conversion de ApplicationKnowledge a dict de preflight
    funciona con datos reales de aplicaciones registradas."""

    def setup_method(self, _method=None):
        from src.hands.applications_core import (
            ApplicationKnowledge,
            get_application_manager,
            _app_knowledge_to_preflight_dict,
        )
        self._app_knowledge_to_preflight_dict = _app_knowledge_to_preflight_dict
        self.ApplicationKnowledge = ApplicationKnowledge
        self.get_application_manager = get_application_manager

    def test_conversion_app_conocida(self):
        """Una aplicacion registrada (notepad) se convierte correctamente a dict de preflight."""
        manager = self.get_application_manager()
        app = manager.get_application("notepad")
        if app is None:
            pytest.skip("notepad no registrado en ApplicationManager")
        d = self._app_knowledge_to_preflight_dict(app)
        assert d["name"] == app.name
        assert "url" in d
        assert "login_required" in d

    def test_conversion_app_inesistente(self):
        """Una app con nombre vacio produce dict con nombre vacio."""
        app = self.ApplicationKnowledge(name="", type="utility")
        d = self._app_knowledge_to_preflight_dict(app)
        assert d["name"] == ""
