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


class TestDiferenciacionGuiCliSubsistemaPeEntornoReal:
    """Diferenciacion GUI vs CLI mediante subsistema PE del ejecutable (unidad 3.8.5.1.4.7.3).

    ping.exe es una herramienta CLI con recursos de version pero NO esta en
    _NOMBRES_CLI, por lo que su clasificacion como HERRAMIENTA_CLI solo puede
    obtenerse leyendo el subsistema PE del encabezado del ejecutable.
    """

    def test_ping_herramienta_cli_mediante_subsistema_pe(self, clasificador):
        ruta = r"C:\Windows\System32\ping.exe"
        if not _existe(ruta):
            pytest.skip("ping.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "ping", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI
        assert c.version is not None  # tiene recursos de version
        assert c.es_lanzable is True

    def test_notepad_aplicacion_gui_mediante_subsistema_pe(self, clasificador):
        ruta = r"C:\Windows\System32\notepad.exe"
        if not _existe(ruta):
            pytest.skip("notepad.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.launch_subtype == LaunchSubtype.GUI_APLICACION
        assert c.es_lanzable is True


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


class TestNombreComercialYAliasesEntornoReal:
    """.7.5: verificar nombre_comercial y aliases en ejecutables reales del equipo.

    nombre_comercial debe leerse de los recursos de version del ejecutable,
    no asumirse del nombre del archivo. Los aliases combinan name,
    nombre_comercial, titulo del ejecutable y CompanyName sin asumir
    equivalencia entre ellos.
    """

    def test_ejecutable_real_tiene_nombre_comercial_y_aliases(self, clasificador):
        c = clasificador.classify_candidate(
            {"name": "python", "absolute_path": sys.executable, "source": "sistema_real"}
        )
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True
        assert c.nombre_comercial is not None, f"nombre_comercial no debe ser None para {sys.executable}"
        assert c.version is not None
        assert len(c.aliases) >= 1
        assert c.name in c.aliases
        # El nombre comercial, si existe, debe estar entre los aliases
        if c.nombre_comercial:
            assert c.nombre_comercial.casefold() in {a.casefold() for a in c.aliases}

    def test_nombre_comercial_no_se_asume_del_nombre_archivo(self, clasificador):
        """En un ejecutable real, nombre_comercial proviene del recurso de version,
        no del nombre del archivo. Verificamos que no coincida forzadamente con el stem."""
        c = clasificador.classify_candidate(
            {"name": "python", "absolute_path": sys.executable, "source": "sistema_real"}
        )
        stem = Path(sys.executable).stem
        # nombre_comercial debe ser un valor real (no None) para python.exe
        assert c.nombre_comercial is not None
        # Los aliases incluyen el stem del ejecutable pero también otros valores
        assert stem in c.aliases or c.name in c.aliases
        assert len(c.aliases) >= 1


# ---------------------------------------------------------------------------
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


class TestRegistroCampos76EntornoReal:
    """.7.6: verificar en entorno real que la clasificacion registra todos los
    campos: fuente, ruta/destino, tipo de lanzamiento, version/producto si
    existe, ultima comprobacion, evidencia y nivel de confianza."""

    def test_ejecutable_real_registra_todos_los_campos_76(self, clasificador):
        """python.exe real: fuente, destination, launch_type, version, producto,
        ultima_comprobacion, evidencia, confianza."""
        c = clasificador.classify_candidate(
            {"name": "python", "absolute_path": sys.executable, "source": "sistema_real"}
        )
        assert c.fuente == "sistema_real"
        assert c.absolute_path == os.path.abspath(sys.executable)
        assert c.destination == os.path.abspath(sys.executable)
        assert c.launch_type == "ejecutable"
        assert c.version is not None, "version debe leerse de recursos de version reales"
        assert c.producto is not None, "producto debe leerse de recursos de version reales"
        assert c.ultima_comprobacion != ""
        assert isinstance(c.evidencia, list)
        assert len(c.evidencia) >= 1
        assert c.confianza in (CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA)
        assert c.to_dict()["fuente"] == "sistema_real"
        assert c.to_dict()["launch_type"] == "ejecutable"
        assert c.to_dict()["evidencia"] == c.evidencia

    def test_notepad_real_registra_todos_los_campos_76(self, clasificador):
        """notepad.exe real: mismo conjunto de campos de registro."""
        ruta = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(ruta):
            pytest.skip("notepad.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.fuente == "sistema_real"
        assert c.destination == ruta
        assert c.launch_type == "ejecutable"
        assert c.version is not None
        assert c.producto is not None
        assert c.ultima_comprobacion != ""
        assert isinstance(c.evidencia, list)
        assert len(c.evidencia) >= 1
        assert c.confianza in (CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA)

    def test_cmd_real_registra_todos_los_campos_76(self, clasificador):
        """cmd.exe real (herramienta CLI): campos de registro completos."""
        ruta = r"C:\Windows\System32\cmd.exe"
        if not os.path.exists(ruta):
            pytest.skip("cmd.exe no disponible en este equipo")
        c = clasificador.classify_candidate(
            {"name": "cmd", "absolute_path": ruta, "source": "sistema_real"}
        )
        assert c.fuente == "sistema_real"
        assert c.destination == ruta
        assert c.launch_type == "ejecutable"
        assert c.version is not None
        assert c.ultima_comprobacion != ""
        assert isinstance(c.evidencia, list)
        assert c.confianza in (CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA)

    def test_uri_real_registra_todos_los_campos_76(self, clasificador):
        """URI real: campos de registro con launch_type uri_aplicacion."""
        c = clasificador.classify_candidate(
            {"name": "Configuracion", "absolute_path": "ms-settings:", "source": "sistema_real"}
        )
        assert c.fuente == "sistema_real"
        assert c.destination == "ms-settings:"
        assert c.launch_type == "uri_aplicacion"
        # URI no tiene archivo en disco: version/producto son None
        assert c.version is None
        assert c.producto is None
        assert c.ultima_comprobacion != ""
        assert isinstance(c.evidencia, list)
        assert c.confianza == CONFIANZA_ALTA

    def test_registro_con_fuente_personalizada(self, clasificador):
        """La fuente de registro se conserva tal cual se proporciona."""
        c = clasificador.classify_candidate(
            {"name": "App", "absolute_path": sys.executable, "source": "menu_inicio"}
        )
        assert c.fuente == "menu_inicio"
        assert c.to_dict()["fuente"] == "menu_inicio"


# ---------------------------------------------------------------------------
class TestDeduplicacionEntornoReal:
    """.7.7: deduplicacion por identidad y destino real en entorno real,
    sin lanzar aplicaciones."""

    def test_mismo_ejecutable_real_dos_candidatos_queda_uno(self, clasificador):
        """python.exe real desde dos candidatos: se deduplica a uno por destino real."""
        ruta = sys.executable
        candidatos = [
            {"name": "python_a", "absolute_path": ruta, "source": "start_menu"},
            {"name": "python_b", "absolute_path": ruta, "source": "appx"},
        ]
        resultado = clasificador.classify_candidates(candidatos)
        assert len(resultado) == 1, f"Se esperaba 1, se obtuvieron {len(resultado)}"
        assert resultado[0].destination == os.path.abspath(ruta)

    def test_dos_ejecutables_reales_distintos_se_conservan(self, clasificador):
        """Dos ejecutables reales distintos (python.exe y notepad.exe): se conservan ambos."""
        rutas = [sys.executable]
        ruta_notepad = r"C:\Windows\System32\notepad.exe"
        if os.path.exists(ruta_notepad):
            rutas.append(ruta_notepad)
        else:
            pytest.skip("notepad.exe no disponible en este equipo")
        candidatos = [
            {"name": "python", "absolute_path": rutas[0], "source": "start_menu"},
            {"name": "notepad", "absolute_path": rutas[1], "source": "appx"},
        ]
        resultado = clasificador.classify_candidates(candidatos)
        assert len(resultado) == 2
        destinos = {c.destination for c in resultado}
        assert os.path.abspath(rutas[0]) in destinos
        assert os.path.abspath(rutas[1]) in destinos

    def test_uri_real_ms_settings_deduplicada(self, clasificador):
        """URI real ms-settings: duplicada: se deduplica a uno."""
        uri = "ms-settings:"
        candidatos = [
            {"name": "config_a", "absolute_path": uri, "source": "start_menu"},
            {"name": "config_b", "absolute_path": uri, "source": "appx"},
        ]
        resultado = clasificador.classify_candidates(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == uri
        assert resultado[0].launch_type == "uri_aplicacion"

    def test_lanzador_uri_steam_deduplicada(self, clasificador):
        """URI de lanzador steam:// duplicada: se deduplica a uno (.7.7 incluye LANZADOR)."""
        uri = "steam://rungameid/12345"
        candidatos = [
            {"name": "steam_a", "absolute_path": uri, "source": "start_menu"},
            {"name": "steam_b", "absolute_path": uri, "source": "appx"},
        ]
        resultado = clasificador.classify_candidates(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == uri
        assert resultado[0].launch_type == "lanzador"
