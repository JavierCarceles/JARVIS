# -*- coding: utf-8 -*-
"""Tests unitarios de las unidades 3.8.5.1.4.7.1 y 3.8.5.1.4.7.3: clasificacion
de candidatos por tipo de lanzamiento propio de cada SO y diferenciacion de
subtipos de rol (GUI, CLI, servicio, controlador, biblioteca, instalador,
actualizador, desinstalador, componente auxiliar, desconocido).

Cubre `src.hands.application_launch_classifier`:
- `LaunchClassifier.classify_candidate` y `classify_candidates`.
- Deteccion de tipos: ejecutable, acceso directo, URI, paquete, bundle, lanzador.
- Subtipos de rol: GUI, CLI, servicio, controlador, biblioteca, instalador,
  actualizador, desinstalador, componente auxiliar, desconocido.
- Diferenciacion GUI vs CLI mediante subsistema PE del ejecutable (.7.3).
- Lanzabilidad basada en evidencia real (no solo extension .exe, requisito .7.4).
- Nombre comercial y aliases independientes del nombre del ejecutable (.7.5).
- Deduplicacion por destino real, no solo por nombre (.7.7).
- Integracion con ApplicationPreflight.validar_launch_destination (.7.10).

Los tests son de inspeccion: no lanzan aplicaciones, no modifican entities.json
ni el catalogo conocido.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    CONFIANZA_NINGUNA,
    IMAGE_SUBSYSTEM_CUI,
    IMAGE_SUBSYSTEM_GUI,
    LaunchClassifier,
    LaunchClassification,
    LaunchSubtype,
    leer_version_archivo_windows,
    _leer_subsistema_pe,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.system_inventory import EntryType, InventoryEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidato(name, destination, source="prueba", volume="C:", launch_type=None,
               last_checked_at=""):
    return {
        "candidate_id": destination or name,
        "name": name,
        "absolute_path": destination,
        "source": source,
        "volume": volume,
        "launch_type": launch_type,
        "last_checked_at": last_checked_at,
    }


def _es_windows() -> bool:
    return os.name == "nt"


# ---------------------------------------------------------------------------
# Lectura de version real de archivo (Windows)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _es_windows(), reason="Lectura de version de archivo solo en Windows")
class TestLeerVersionArchivoWindows:
    def test_python_exe_tiene_version(self):
        version = leer_version_archivo_windows(sys.executable)
        assert version is not None, f"sys.executable {sys.executable} deberia tener recursos de version"
        assert "ProductName" in version or "ProductVersion" in version

    def test_archivo_inexistente_retorna_none(self):
        assert leer_version_archivo_windows(r"C:\No\Existe\archivo.exe") is None

    def test_directorio_retorna_none(self):
        with tempfile.TemporaryDirectory() as d:
            assert leer_version_archivo_windows(d) is None


# ---------------------------------------------------------------------------
# LaunchClassification dataclass
# ---------------------------------------------------------------------------

class TestLaunchClassification:
    def valores_por_defecto(self):
        c = LaunchClassification(candidate_id="c1", name="App")
        assert c.candidate_id == "c1"
        assert c.name == "App"
        assert c.launch_type is None
        assert c.launch_subtype == LaunchSubtype.DESCONOCIDO
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_NINGUNA
        assert c.evidencia == []
        assert c.razon == ""
        assert c.ultima_comprobacion != ""

    def to_dict_contiene_campos(self):
        c = LaunchClassification(
            candidate_id="c1", name="MiApp", launch_type="ejecutable",
            launch_subtype=LaunchSubtype.GUI_APLICACION, es_lanzable=True,
            confianza=CONFIANZA_ALTA, evidencia=["archivo_ejecutable_existente"],
            nombre_comercial="Mi App Comercial", version="1.0.0",
        )
        d = c.to_dict()
        assert d["launch_type"] == "ejecutable"
        assert d["launch_subtype"] == "gui_aplicacion"
        assert d["es_lanzable"] is True
        assert d["nombre_comercial"] == "Mi App Comercial"
        assert d["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Clasificacion por tipo de lanzamiento
# ---------------------------------------------------------------------------

class TestTipoLanzamientoExecutable:
    def test_exe_real_con_version_es_ejecutable_lanzable(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("python", sys.executable))
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True
        assert c.confianza in (CONFIANZA_MEDIA, CONFIANZA_ALTA)
        assert "archivo_ejecutable_existente" in c.evidencia
        assert c.version is not None
        assert c.nombre_comercial is not None

    def test_exe_sin_evidencia_no_es_lanzable_requisito_74(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("falso", path))
            assert c.launch_type == "ejecutable"
            assert c.es_lanzable is False, f"{path} solo tiene extension, no es lanzable confirmado"
            assert c.confianza == CONFIANZA_BAJA
            assert any("solo_extension" in e or "sin_evidencia" in e for e in c.advertencias + c.evidencia)
        finally:
            os.unlink(path)

    def test_exe_inexistente_no_es_lanzable(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("fantasma", r"C:\No\Existe\fantasma.exe"))
        # Sin archivo en disco no hay evidencia de tipo: no se asume ejecutable (.7.4).
        assert c.launch_type is None
        assert c.launch_subtype == LaunchSubtype.DESCONOCIDO
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_NINGUNA

    def test_dll_es_biblioteca_no_lanzable(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("modulo", path))
            assert c.launch_subtype == LaunchSubtype.BIBLIOTECA
            assert c.es_lanzable is False
        finally:
            os.unlink(path)

    def test_sys_es_controlador_no_lanzable(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".sys", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("driver", path))
            assert c.launch_subtype == LaunchSubtype.CONTROLADOR
            assert c.es_lanzable is False
        finally:
            os.unlink(path)


class TestPEValidoComoEvidenciaLanzabilidad:
    """.7.4: un .exe con encabezado PE valido pero sin recursos de version
    es lanzable con confianza baja (evidencia de sistema, no solo extension).
    Un .exe que no es PE valido sigue sin ser lanzable."""

    @patch('src.hands.application_launch_classifier._leer_subsistema_pe')
    def test_exe_con_pe_valido_sin_version_es_lanzable_confianza_baja(self, mock_pe):
        mock_pe.return_value = IMAGE_SUBSYSTEM_GUI
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("peapp", path))
            assert c.launch_type == "ejecutable"
            assert c.es_lanzable is True, f"{path} con PE valido deberia ser lanzable"
            assert c.confianza == CONFIANZA_BAJA
            assert "encabezado_pel_valido" in c.evidencia
            assert c.version is None
        finally:
            os.unlink(path)

    @patch('src.hands.application_launch_classifier._leer_subsistema_pe')
    def test_exe_sin_pe_y_sin_version_no_es_lanzable(self, mock_pe):
        mock_pe.return_value = None
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("nope", path))
            assert c.es_lanzable is False, f"{path} sin PE valido no es lanzable"
            assert c.confianza == CONFIANZA_BAJA
            assert any(
                "solo_extension" in e for e in c.advertencias + c.evidencia
            )
        finally:
            os.unlink(path)


class TestTipoLanzamientoAccesoDirecto:
    def test_lnk_existente_tipo_acceso_directo(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".lnk", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("acceso", path))
            assert c.launch_type == "acceso_directo"
            # Un .lnk fabricado no es un acceso directo valido con target
            assert c.es_lanzable is False
            assert c.confianza == CONFIANZA_BAJA
        finally:
            os.unlink(path)

    def test_lnk_inexistente_no_tipo(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("acceso", r"C:\No\Existe\algo.lnk"))
        assert c.launch_type is None
        assert c.es_lanzable is False


class TestTipoLanzamientoURI:
    def test_uri_admitida_es_uri_aplicacion_lanzable(self):
        clasificador = LaunchClassifier()
        for uri in ("ms-settings:", "microsoft-edge:", "https://example.com", "mailto:a@b.c"):
            c = clasificador.classify_candidate(_candidato("uri", uri))
            assert c.launch_type == "uri_aplicacion", uri
            assert c.es_lanzable is True, uri
            assert c.confianza == CONFIANZA_ALTA, uri

    def test_uri_esquema_desconocido_no_es_lanzable(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("custom", "custom-app:algo"))
        assert c.launch_type is None
        assert c.es_lanzable is False

    def test_uri_lanzador_steam_clasificada_como_lanzador(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("steam", "steam://rungameid/12345"))
        assert c.launch_type == "lanzador"
        assert c.es_lanzable is False  # preflight no admite esquemas de lanzador como lanzamiento generico
        assert c.confianza == CONFIANZA_MEDIA


class TestTipoLanzamientoVacio:
    def test_destino_vacio_confianza_ninguna(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("vacio", ""))
        assert c.launch_type is None
        assert c.es_lanzable is False
        assert c.confianza == CONFIANZA_NINGUNA

    def test_destino_none_confianza_ninguna(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("none", None))
        assert c.confianza == CONFIANZA_NINGUNA
        assert c.es_lanzable is False


# ---------------------------------------------------------------------------
# Subtipos de rol
# ---------------------------------------------------------------------------

class TestSubtipoRol:
    def test_desinstalador_por_nombre(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("setup_uninstall", path))
            assert c.launch_subtype == LaunchSubtype.DESINSTALADOR
        finally:
            os.unlink(path)

    def test_instalador_por_nombre(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("program_setup", path))
            assert c.launch_subtype == LaunchSubtype.INSTALADOR
        finally:
            os.unlink(path)

    def test_actualizador_por_nombre(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("app_updater", path))
            assert c.launch_subtype == LaunchSubtype.ACTUALIZADOR
        finally:
            os.unlink(path)

    def test_herramienta_cli_por_nombre(self):
        clasificador = LaunchClassifier()
        # Archivo .exe llamado exactamente cmd.exe, sin recursos de version:
        # subtipo herramienta_cli por nombre, pero no lanzable por solo extension (.7.4).
        directorio = tempfile.mkdtemp(prefix="jarvis_clasificacion_prueba_")
        ruta = os.path.join(directorio, "cmd.exe")
        try:
            Path(ruta).touch()
            c = clasificador.classify_candidate(_candidato("cmd", ruta))
            assert c.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI
            assert c.es_lanzable is False
            assert c.confianza == CONFIANZA_BAJA
        finally:
            if os.path.exists(ruta):
                os.unlink(ruta)
            os.rmdir(directorio)

    def test_desconocido_por_defecto(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            c = clasificador.classify_candidate(_candidato("xyztool", path))
            assert c.launch_subtype == LaunchSubtype.DESCONOCIDO
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Nombre comercial y aliases independientes del ejecutable (.7.5)
# ---------------------------------------------------------------------------

class TestNombreComercialYAliases:
    def test_nombre_comercial_desde_version_recurso(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("python", sys.executable))
        assert c.nombre_comercial is not None
        assert c.version is not None

    def test_aliases_incluyen_nombre_y_comercial(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(_candidato("python", sys.executable))
        assert c.name in c.aliases
        if c.nombre_comercial:
            # El dedup es case-insensitive: el nombre comercial puede
            # aparecer con la caja del recurso de version.
            alias_casefold = {a.casefold() for a in c.aliases}
            assert c.nombre_comercial.casefold() in alias_casefold
        assert len(c.aliases) >= 1


# ---------------------------------------------------------------------------
# Deduplicacion por destino real (.7.7)
# ---------------------------------------------------------------------------

class TestDeduplicacion:
    def test_misma_ruta_dos_candidatos_queda_uno(self):
        clasificador = LaunchClassifier()
        camino = sys.executable
        candidatos = [
            _candidato("python_a", camino),
            _candidato("python_b", camino),
        ]
        resultado = clasificador.classify_candidates(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == camino

    def test_rutas_distintas_se_conservan_todas(self):
        clasificador = LaunchClassifier()
        caminos = [sys.executable]
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            caminos.append(f.name)
        try:
            candidatos = [_candidato("app_a", caminos[0]), _candidato("app_b", caminos[1])]
            resultado = clasificador.classify_candidates(candidatos)
            assert len(resultado) == 2
            destinos = {c.destination for c in resultado}
            assert destinos == set(caminos)
        finally:
            os.unlink(caminos[1])

    def test_ordenado_por_confianza(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            bare = f.name
        try:
            candidatos = [
                _candidato("bare", bare),
                _candidato("python", sys.executable),
            ]
            resultado = clasificador.classify_candidates(candidatos)
            assert len(resultado) == 2
            assert _puntos(resultado[0].confianza) >= _puntos(resultado[1].confianza)
        finally:
            os.unlink(bare)


def _puntos(confianza: str) -> int:
    return {"alta": 3, "media": 2, "baja": 1, "ninguna": 0}.get(confianza, 0)


# ---------------------------------------------------------------------------
# Entrada InventoryEntry
# ---------------------------------------------------------------------------

class TestEntradaInventoryEntry:
    def test_acepta_inventory_entry(self):
        clasificador = LaunchClassifier()
        entry = InventoryEntry(
            machine_id="maquina",
            volume="C:",
            absolute_path=sys.executable,
            relative_path="python.exe",
            name="python.exe",
            extension=".exe",
            entry_type=EntryType.FILE,
            size_bytes=0,
            modified_at="",
            created_at="",
            source="filesystem_scan",
        )
        c = clasificador.classify_candidate(entry)
        assert c.launch_type == "ejecutable"
        assert c.name == "python.exe"


# ---------------------------------------------------------------------------
# Lectura de subsistema PE (diferenciacion GUI vs CLI, unidad 3.8.5.1.4.7.3)
# ---------------------------------------------------------------------------

class TestLeerSubsistemaPe:
    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_subsistema_notepad_es_gui(self):
        subsistema = _leer_subsistema_pe(r"C:\Windows\System32\notepad.exe")
        assert subsistema == IMAGE_SUBSYSTEM_GUI

    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_subsistema_cmd_es_cli(self):
        subsistema = _leer_subsistema_pe(r"C:\Windows\System32\cmd.exe")
        assert subsistema == IMAGE_SUBSYSTEM_CUI

    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_subsistema_ping_es_cli(self):
        subsistema = _leer_subsistema_pe(r"C:\Windows\System32\ping.exe")
        assert subsistema == IMAGE_SUBSYSTEM_CUI

    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_archivo_no_pe_retorna_none(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta = f.name
        try:
            assert _leer_subsistema_pe(ruta) is None
        finally:
            os.unlink(ruta)

    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_archivo_inexistente_retorna_none(self):
        assert _leer_subsistema_pe(r"C:\No\Existe\archivo.exe") is None

    @pytest.mark.skipif(os.name != "nt", reason="Lectura de PE solo en Windows")
    def test_pe_directorio_retorna_none(self):
        with tempfile.TemporaryDirectory() as d:
            assert _leer_subsistema_pe(d) is None


class TestDiferenciacionGuiCliPorSubsistemaPe:
    """Diferenciacion de ejecutables GUI vs CLI mediante subsistema PE (.7.3)."""

    @pytest.mark.skipif(os.name != "nt", reason="Diferenciacion PE solo en Windows")
    def test_ejecutable_con_version_subsistema_gui_es_gui_aplicacion(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(
            {"name": "notepad", "absolute_path": r"C:\Windows\System32\notepad.exe"}
        )
        assert c.launch_subtype == LaunchSubtype.GUI_APLICACION

    @pytest.mark.skipif(os.name != "nt", reason="Diferenciacion PE solo en Windows")
    def test_ejecutable_con_version_subsistema_cli_es_herramienta_cli(self):
        clasificador = LaunchClassifier()
        c = clasificador.classify_candidate(
            {"name": "ping", "absolute_path": r"C:\Windows\System32\ping.exe"}
        )
        assert c.launch_subtype == LaunchSubtype.HERRAMIENTA_CLI

    @pytest.mark.skipif(os.name != "nt", reason="Diferenciacion PE solo en Windows")
    def test_ejecutivo_sin_version_sin_pe_es_desconocido(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta = f.name
        try:
            c = clasificador.classify_candidate(
                {"name": "vacio", "absolute_path": ruta}
            )
            assert c.launch_subtype == LaunchSubtype.DESCONOCIDO
        finally:
            os.unlink(ruta)


# ---------------------------------------------------------------------------
# Integracion con preflight (.7.10): no lanza nada
# ---------------------------------------------------------------------------

class TestIntegracionPreflight:
    def test_validar_destino_antes_de_lanzar_delega_en_preflight(self):
        clasificador = LaunchClassifier()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
        try:
            decision = clasificador.validar_destino_antes_de_lanzar(path)
            assert isinstance(decision, dict)
            assert "valid" in decision
            assert "launch_type" in decision
            assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE
        finally:
            os.unlink(path)

    def test_validar_uri_admitida(self):
        clasificador = LaunchClassifier()
        decision = clasificador.validar_destino_antes_de_lanzar("ms-settings:")
        assert decision["valid"] is True
        assert decision["launch_type"] == ApplicationPreflight.LAUNCH_TYPE_URI
