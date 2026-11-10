# -*- coding: utf-8 -*-
"""Verificacion en entorno real de la unidad 3.8.5.1.4.7.1.

Ejecuta `LaunchClassifier` (src.hands.application_launch_classifier) sobre
elementos REALES del equipo Windows: ejecutables del sistema, herramientas CLI,
URI de aplicación, accesos directos rotos y archivos con extensión engañosa.

No lanza ninguna aplicación, no instala ni modifica nada del usuario. Solo
clasifica y valida destinos mediante ApplicationPreflight (sin lanzar).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    CONFIANZA_NINGUNA,
    LaunchClassifier,
    LaunchSubtype,
)
from src.hands.application_preflight import ApplicationPreflight


def _existe(ruta: str) -> bool:
    return bool(ruta) and os.path.exists(ruta)


@pytest.fixture
def clasificador():
    return LaunchClassifier()


class TestClasificacionEntornoRealEjecutablesSistema:
    """Ejecutables reales de Windows (no mocks)."""

    def test_python_ejecutable_real_lanzable(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "python", "absolute_path": sys.executable, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True
        assert c.confianza in (CONFIANZA_MEDIA, CONFIANZA_ALTA)
        assert c.version is not None
        assert c.nombre_comercial is not None
        assert "archivo_ejecutable_existente" in c.evidencia
        assert c.requiere_preflight is True

    def test_cmd_herramienta_cli_real(self, clasificador):
        ruta = r"C:\Windows\System32\cmd.exe"
        if not _existe(ruta):
            pytest.skip("cmd.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "cmd", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI
        assert c.es_lanzable is True

    def test_notepad_gui_real_si_existe(self, clasificador):
        ruta = r"C:\Windows\System32\notepad.exe"
        if not _existe(ruta):
            pytest.skip("notepad.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True

    def test_archivo_solo_extension_exe_no_asume_gui(self, clasificador):
        # Falso positivo: archivo vacio con extension .exe, sin version ni
        # evidencia de instalacion. No debe considerarse aplicacion GUI
        # lanzable (requisito .7.4).
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta = f.name
        try:
            c = clasificador.classify_candidate(
                {"name": "falso", "absolute_path": ruta, "source": "temporal_prueba"}
            )
            assert c.launch_type == "ejecutable"
            assert c.es_lanzable is False
            assert c.confianza == CONFIANZA_BAJA
            assert any(
                "solo_extension" in e for e in c.evidencia + c.advertencias
            )
        finally:
            os.unlink(ruta)

    def test_dll_biblioteca_no_lanzable(self, clasificador):
        ruta = r"C:\Windows\System32\kernel32.dll"
        if not _existe(ruta):
            pytest.skip("kernel32.dll no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "kernel32", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.launch_subtype == LaunchSubtype.BIBLIOTECA
        assert c.es_lanzable is False


class TestClasificacionEntornoRealURI:
    def test_uri_ms_settings_admitida(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "Configuracion", "absolute_path": "ms-settings:", "source": "sistema_real"}
        )
        assert c.launch_type == "uri_aplicacion"
        assert c.es_lanzable is True
        assert c.confianza == CONFIANZA_ALTA

    def test_uri_esquema_desconocido_no_lanzable(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "desconocida", "absolute_path": "custom-app:algo", "source": "sistema_real"}
        )
        assert c.launch_type is None
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_NINGUNA

    def test_lanzador_uri_steem_clasificado_sin_lanzar(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "steam", "absolute_path": "steam://rungameid/12345", "source": "sistema_real"}
        )
        assert c.launch_type == "lanzador"
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_MEDIA


class TestClasificacionEntornoRealAccesosDirectos:
    def test_acceso_directo_roto_tipo_pero_no_lanzable(self, clasificador):
        with tempfile.NamedTemporaryFile(suffix=".lnk", delete=False) as f:
            ruta = f.name
        try:
            c = clasificador.classify_candidate(
                {"name": "acceso_roto", "absolute_path": ruta, "source": "temporal_prueba"}
            )
            assert c.launch_type == "acceso_directo"
            assert c.es_lanzable is False  # target no resuelve a ejecutable real
        finally:
            os.unlink(ruta)

    def test_inexistente_no_tipo(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "fantasma", "absolute_path": r"C:\No\Existe\fantasma.exe", "source": "sistema_real"}
        )
        assert c.launch_type is None
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_NINGUNA


class TestPreflightSinLanzarEntornoReal:
    """Integracion .7.10: todo candidato a abrir pasa por preflight real; no se lanza nada."""

    def test_validar_ejecutable_real(self, clasificador):
        decision = clasificador.validar_destino_antes_de_lanzar(sys.executable)
        assert isinstance(decision, dict)
        assert decision["valid"] is True
        assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE
        assert decision["destination"] == os.path.abspath(sys.executable)

    def test_validar_uri_admitida(self, clasificador):
        decision = clasificador.validar_destino_antes_de_lanzar("ms-settings:")
        assert decision["valid"] is True
        assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_URI

    def test_validar_archivo_txt_no_admitido(self, clasificador):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            ruta = f.name
        try:
            decision = clasificador.validar_destino_antes_de_lanzar(ruta)
            assert decision["valid"] is False
            assert decision["launch_type"] is None
        finally:
            os.unlink(ruta)
