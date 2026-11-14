# -*- coding: utf-8 -*-
"""Tests unitarios de la unidad 3.8.5.1.4.7.2: descubrimiento de aplicaciones
reutilizando primero las fuentes existentes del SO y el inventario como fuente
complementaria para localizar destinos faltantes.

Cubre `src.hands.application_discovery`:
- `ApplicationDiscovery.descubrir_todos`
- `ApplicationDiscovery.buscar_por_nombre`
- `ApplicationDiscovery.candidatos_lanzables`
- `DiscoveredCandidate.from_classification` / `to_dict`
- Prioridad de fuentes primarias (menu de aplicaciones, paquetes, registro,
  accesos directos, PATH, App Paths)
- Fallback al inventario solo para destinos faltantes (no buscados en primarias)
- Deduplicacion por destino real, no solo por nombre
- Clasificacion y validacion con preflight (sin lanzar ninguna aplicacion)
- Registro y persistencia de candidatos (`registrar_candidatos`) con todos
  los campos de registro .7.6 en `application_candidates`.

Estrategia de mocks: solo se mockean las fuentes de DATOS
(`CalibrationManager.discover_applications` y `SystemInventoryStorage`). La
clasificacion y el preflight son REALES (`LaunchClassifier` +
`ApplicationPreflight` sobre archivos reales del equipo), por lo que ningún mock
decide el resultado de clasificación ni de validación. No se lanza ninguna
aplicación y no se modifica `entities.json`.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.hands.application_discovery import (
    ApplicationDiscovery,
    CandidatoConCatalogo,
    DiscoveredCandidate,
    FUENTE_APP_PATHS,
    FUENTE_APPX,
    FUENTE_APLICACION_ABIERTA,
    FUENTE_CATALOGO,
    FUENTE_INVENTARIO,
    FUENTE_PATH,
    FUENTE_START_MENU,
    FUENTE_UNINSTALL_REGISTRY,
    FUENTES_PRIMARIAS,
    IdentidadGlobalEstable,
    RegistroMinimoAplicacion,
    ResultadoResolucionCandidatos,
    _CAMPOS_REQUERIDOS_REGISTRO_MINIMO,
    construir_registro_minimo_aplicacion,
    destino_observable,
    validar_registro_minimo_aplicacion,
    calcular_identidad_estable,
    _CAMPOS_REQUERIDOS_REGISTRO_MINIMO,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
)
from src.memory.storage import Entity, MemoryManager
from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    CONFIANZA_NINGUNA,
    LaunchClassifier,
    LaunchSubtype,
    LaunchType,
    leer_version_archivo_windows,
)
from src.hands.system_inventory import EntryType, generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _existe(ruta=None) -> bool:
    return bool(ruta) and os.path.exists(ruta)


def _windows() -> bool:
    return os.name == "nt"


def _notepad() -> Optional[str]:
    ruta = r"C:\Windows\System32\notepad.exe"
    return ruta if _existe(ruta) else None


def _cmd() -> Optional[str]:
    ruta = r"C:\Windows\System32\cmd.exe"
    return ruta if _existe(ruta) else None


def _discovery_con_mocks(
    calib_apps: Optional[list] = None,
    storage_entries: Optional[list] = None,
    machine_id: str = "maquina-prueba",
):
    """Crea un ApplicationDiscovery con clasificador/preflight REALES y las
    fuentes de datos mockeadas (calib y storage)."""
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    calib = MagicMock()
    calib.discover_applications.return_value = calib_apps or []
    storage = MagicMock()
    storage.connect.return_value = None
    storage.close.return_value = None
    storage.search.return_value = storage_entries or []
    discovery = ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=storage,
        calibration=calib,
        machine_id=machine_id,
    )
    return discovery, calib, storage


def _app(name, path, fuente):
    return {
        "name": name,
        "path": path,
        "source": fuente,
        "app_id": "",
        "arguments": "",
    }


# ---------------------------------------------------------------------------
# DiscoveredCandidate
# ---------------------------------------------------------------------------

class TestDiscoveredCandidate:
    def test_from_classification_mapea_campos(self):
        clasificador = LaunchClassifier(ApplicationPreflight())
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        c = clasificador.classify_candidate({"name": "Notepad", "absolute_path": ruta, "source": "start_menu"})
        dc = DiscoveredCandidate.from_classification(
            c, fuente=FUENTE_START_MENU, destino_original=ruta,
            preflight_decision={"valid": True, "launch_type": "ejecutable"},
            fuentes_consultadas=[FUENTE_START_MENU],
            esta_en_inventario=False,
        )
        assert dc.name == "Notepad"
        assert dc.fuente == FUENTE_START_MENU
        assert dc.destino_original == ruta
        assert dc.esta_en_inventario is False
        assert dc.preflight_decision == {"valid": True, "launch_type": "ejecutable"}
        assert dc.fuentes_consultadas == [FUENTE_START_MENU]

    def test_to_dict_contiene_metadatos_descubrimiento(self):
        dc = DiscoveredCandidate(
            candidate_id="c1", name="App", fuente=FUENTE_INVENTARIO,
            esta_en_inventario=True,
            fuentes_consultadas=[FUENTE_START_MENU, FUENTE_INVENTARIO],
            preflight_decision={"valid": False},
        )
        d = dc.to_dict()
        assert d["fuente"] == FUENTE_INVENTARIO
        assert d["esta_en_inventario"] is True
        assert d["fuentes_consultadas"] == [FUENTE_START_MENU, FUENTE_INVENTARIO]
        assert d["preflight_decision"] == {"valid": False}


class TestDiscoveredCandidateCampos76:
    """.7.6: verificar que DiscoveredCandidate registra todos los campos de
    registro: fuente, ruta/destino, tipo de lanzamiento, version/producto si
    existe, ultima comprobacion, evidencia y nivel de confianza."""

    def test_from_classification_mapea_todos_los_campos_76(self):
        clasificador = LaunchClassifier(ApplicationPreflight())
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        c = clasificador.classify_candidate({"name": "Notepad", "absolute_path": ruta, "source": "start_menu"})
        dc = DiscoveredCandidate.from_classification(
            c, fuente=FUENTE_START_MENU, destino_original=ruta,
            preflight_decision={"valid": True, "launch_type": "ejecutable"},
            fuentes_consultadas=[FUENTE_START_MENU],
            esta_en_inventario=False,
        )
        # Fuente de registro
        assert dc.fuente == FUENTE_START_MENU
        # Ruta/destino
        assert dc.absolute_path == ruta
        assert dc.destination == ruta
        # Tipo de lanzamiento
        assert dc.launch_type == c.launch_type
        # Version/producto si existen
        assert dc.version == c.version
        assert dc.producto == c.producto
        # Ultima comprobacion
        assert dc.ultima_comprobacion != ""
        assert dc.ultima_comprobacion == c.ultima_comprobacion
        # Evidencia
        assert isinstance(dc.evidencia, list)
        assert dc.evidencia == c.evidencia
        # Nivel de confianza
        assert dc.confianza == c.confianza
        assert dc.confianza in (CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA)

    def test_to_dict_serializa_todos_los_campos_76(self):
        dc = DiscoveredCandidate(
            candidate_id="c1", name="App", fuente=FUENTE_START_MENU,
            absolute_path=r"C:\Windows\notepad.exe",
            destination=r"C:\Windows\notepad.exe",
            launch_type="ejecutable",
            confianza=CONFIANZA_ALTA,
            evidencia=["archivo_ejecutable_existente"],
            version="10.0.19041",
            producto="Microsoft Windows",
            ultima_comprobacion="2024-01-03T00:00:00+00:00",
        )
        d = dc.to_dict()
        assert d["fuente"] == FUENTE_START_MENU
        assert d["absolute_path"] == r"C:\Windows\notepad.exe"
        assert d["destination"] == r"C:\Windows\notepad.exe"
        assert d["launch_type"] == "ejecutable"
        assert d["version"] == "10.0.19041"
        assert d["producto"] == "Microsoft Windows"
        assert d["ultima_comprobacion"] == "2024-01-03T00:00:00+00:00"
        assert d["evidencia"] == ["archivo_ejecutable_existente"]
        assert d["confianza"] == CONFIANZA_ALTA


class TestRegistrarCandidatos:
    """.7.6: verificar que `registrar_candidatos` persiste todos los campos de
    registro en `application_candidates` y que `buscar_candidatos_registrados`
    los recupera."""

    def test_registra_y_recupera_candidatos(self, tmp_path):
        db_path = tmp_path / "test_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize()
        discovery = ApplicationDiscovery(storage=storage, machine_id="maquina-test")

        candidatos = [
            DiscoveredCandidate(
                candidate_id="c-1", name="Chrome",
                absolute_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
                destination="C:/Program Files/Google/Chrome/Application/chrome.exe",
                launch_type="ejecutable",
                confianza=CONFIANZA_ALTA,
                evidencia=["archivo_ejecutable_existente", "version_recurso_leida"],
                version="120.0.0.0",
                producto="Google Chrome",
                fuente=FUENTE_START_MENU,
                ultima_comprobacion="2024-01-03T00:00:00+00:00",
            ),
            DiscoveredCandidate(
                candidate_id="c-2", name="Settings",
                absolute_path="ms-settings:",
                destination="ms-settings:",
                launch_type="uri_aplicacion",
                confianza=CONFIANZA_ALTA,
                evidencia=["uri_admitida_validada"],
                version=None,
                producto=None,
                fuente=FUENTE_INVENTARIO,
                ultima_comprobacion="2024-01-03T01:00:00+00:00",
            ),
        ]

        insertados = discovery.registrar_candidatos(candidatos, volume="C:")
        assert insertados == 2

        # Recuperar y verificar todos los campos de registro .7.6
        recuperados = storage.buscar_candidatos_registrados("maquina-test")
        assert len(recuperados) == 2

        chrome = [r for r in recuperados if r["candidate_id"] == "c-1"][0]
        assert chrome["fuente"] == FUENTE_START_MENU
        assert chrome["absolute_path"] == "C:/Program Files/Google/Chrome/Application/chrome.exe"
        assert chrome["launch_type"] == "ejecutable"
        assert chrome["version"] == "120.0.0.0"
        assert chrome["producto"] == "Google Chrome"
        assert isinstance(chrome["evidencia"], list)
        assert "archivo_ejecutable_existente" in chrome["evidencia"]
        assert chrome["confianza"] == CONFIANZA_ALTA
        assert chrome["ultima_comprobacion"] == "2024-01-03T00:00:00+00:00"

        settings = [r for r in recuperados if r["candidate_id"] == "c-2"][0]
        assert settings["fuente"] == FUENTE_INVENTARIO
        assert settings["launch_type"] == "uri_aplicacion"
        assert settings["version"] is None
        assert settings["producto"] is None


# ---------------------------------------------------------------------------
# Inicializacion
# ---------------------------------------------------------------------------

class TestApplicationDiscoveryInit:
    def test_crea_instancias_reales_por_defecto(self):
        d = ApplicationDiscovery(machine_id="maquina-prueba")
        assert isinstance(d.preflight, ApplicationPreflight)
        assert isinstance(d.clasificador, LaunchClassifier)
        assert isinstance(d.storage, type(d.storage))  # SystemInventoryStorage real
        assert isinstance(d.calibration, type(d.calibration))  # CalibrationManager real
        assert d.machine_id == "maquina-prueba"

    def test_acepta_dependencias_inyectadas(self):
        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        storage = MagicMock()
        d = ApplicationDiscovery(
            preflight=preflight, clasificador=clasificador,
            storage=storage, calibration=calib, machine_id="m",
        )
        assert d.preflight is preflight
        assert d.clasificador is clasificador
        assert d.storage is storage
        assert d.calibration is calib
        assert d.machine_id == "m"


# ---------------------------------------------------------------------------
# Fuentes primarias y prioridad
# ---------------------------------------------------------------------------

class TestFuentesPrimarias:
    def test_menu_aplicaciones_start_menu(self):
        descub, calib, _ = _discovery_con_mocks(
            calib_apps=[
                {"name": "Notepad", "app_id": "", "path": _notepad() or r"C:\Windows\System32\notepad.exe",
                 "arguments": "", "source": "start_menu"},
            ]
        )
        primarios = descub._fuentes_primarias(limite_por_fuente=10)
        assert any(p["source"] == FUENTE_START_MENU for p in primarios)
        assert calib.discover_applications.call_count == 1

    def test_paquetes_appx(self):
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("MiAppX", r"C:\Program Files\WindowsApps\appx", FUENTE_APPX)]
        )
        primarios = descub._fuentes_primarias(limite_por_fuente=10)
        assert any(p["source"] == FUENTE_APPX for p in primarios)

    def test_registro_desinstaladores(self):
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("AppRegistro", r"C:\Program Files\AppRegistro\app.exe", FUENTE_UNINSTALL_REGISTRY)]
        )
        primarios = descub._fuentes_primarias(limite_por_fuente=10)
        assert any(p["source"] == FUENTE_UNINSTALL_REGISTRY for p in primarios)

    def test_fuentes_primarias_tiene_orden_esperado(self):
        assert FUENTES_PRIMARIAS == (
            FUENTE_START_MENU, FUENTE_APPX, FUENTE_UNINSTALL_REGISTRY,
            FUENTE_PATH, FUENTE_APP_PATHS,
        )

    def test_fallo_fuente_calibration_no_interrumpe(self):
        calib = MagicMock()
        calib.discover_applications.side_effect = RuntimeError("PowerShell fallo")
        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        storage = MagicMock()
        storage.connect.return_value = None
        storage.close.return_value = None
        storage.search.return_value = []
        d = ApplicationDiscovery(
            preflight=preflight, clasificador=clasificador,
            storage=storage, calibration=calib, machine_id="m",
        )
        # No debe lanzar: devuelve lista (posiblemente vacia o solo de PATH/app_paths).
        primarios = d._fuentes_primarias(limite_por_fuente=10)
        assert isinstance(primarios, list)


# ---------------------------------------------------------------------------
# Prioridad y fallback al inventario
# ---------------------------------------------------------------------------

class TestPrioridadFallback:
    def test_descubrir_todos_incluir_inventario_false_no_consulta_inventario(self):
        descub, _, storage = _discovery_con_mocks(
            calib_apps=[_app("Notepad", _notepad() or r"C:\Windows\System32\notepad.exe", FUENTE_START_MENU)]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        assert storage.search.call_count == 0
        assert storage.connect.call_count == 0
        assert len(resultado) >= 1

    def test_buscar_por_nombre_encontrado_en_primarias_no_consulta_inventario(self):
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, storage = _discovery_con_mocks(
            calib_apps=[_app("Notepad", ruta, FUENTE_START_MENU)]
        )
        resultado = descub.buscar_por_nombre("notepad", incluir_inventario=True)
        assert storage.search.call_count == 0
        assert len(resultado) >= 1
        # El catálogo conocido tiene precedencia (unidad 3.8.5.1.4.9.2) y
        # devuelve el nombre canónico de la aplicación ("Bloc de notas"),
        # mientras que las primarias devolverían el nombre consultado ("notepad").
        assert any(
            c.name.casefold() in ("notepad", "bloc de notas")
            for c in resultado
        )

    def test_buscar_por_nombre_faltante_consulta_inventario(self):
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        # .9.4: las entradas de inventario cuyo destino ya no es accesible se
        # excluyen de la resolucion, por eso la entrada apunta a un archivo
        # real existente del equipo. Se usa notepad.exe (y no sys.executable,
        # cuyo proceso Python esta en ejecucion durante pytest y elevaria la
        # fuente a aplicacion_abierta por _elevar_si_abierta).
        storage.search.return_value = [
            {"absolute_path": _notepad(), "name": "miapp.exe",
             "volume": "C:", "entry_type": "file", "last_checked_at": ""}
        ]
        resultado = descub.buscar_por_nombre("miapp", incluir_inventario=True)
        assert storage.search.call_count == 1
        assert len(resultado) == 1
        c = resultado[0]
        assert c.name.casefold() == "miapp.exe"
        assert c.fuente == FUENTE_INVENTARIO
        assert c.esta_en_inventario is True
        assert FUENTE_INVENTARIO in c.fuentes_consultadas
        assert c.disponible is True

    def test_buscar_por_nombre_faltante_sin_inventario_retorna_vacio(self):
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        resultado = descub.buscar_por_nombre("miapp", incluir_inventario=False)
        assert storage.search.call_count == 0
        assert resultado == []

    def test_buscar_por_nombre_vacio_retorna_vacio(self):
        descub, _, storage = _discovery_con_mocks()
        assert descub.buscar_por_nombre("") == []
        assert descub.buscar_por_nombre("   ") == []
        assert descub.buscar_por_nombre(None) == []  # type: ignore[arg-type]
        assert storage.search.call_count == 0


# ---------------------------------------------------------------------------
# Clasificacion y validacion (reales, sin lanzar)
# ---------------------------------------------------------------------------

class TestClasificacionValidacion:
    def test_clasifica_ejecutivo_real_lanzable(self):
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("Notepad", ruta, FUENTE_START_MENU)]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        c = next((x for x in resultado if x.name.casefold() == "notepad"), None)
        assert c is not None
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True
        assert c.confianza in (CONFIANZA_MEDIA, CONFIANZA_ALTA)
        assert c.preflight_decision is not None
        assert c.preflight_decision["valid"] is True
        assert c.preflight_decision["launch_type"] == "ejecutable"

    def test_clasifica_herramienta_cli_real(self):
        ruta = sys.executable
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("python", ruta, FUENTE_START_MENU)]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        c = next((x for x in resultado if x.name.casefold() == "python"), None)
        assert c is not None
        assert c.launch_type == "ejecutable"
        assert c.es_lanzable is True

    def test_uri_aplicacion_admitida_sin_lanzar(self):
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[{"name": "Configuracion", "app_id": "", "path": "ms-settings:",
                         "arguments": "", "source": "start_menu"}]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        c = next((x for x in resultado if x.name.casefold() == "configuracion"), None)
        assert c is not None
        assert c.launch_type == "uri_aplicacion"
        assert c.es_lanzable is True
        assert c.preflight_decision["valid"] is True

    def test_solo_extension_exe_no_asume_lanzable(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta = f.name
        try:
            descub, _, _ = _discovery_con_mocks(
                calib_apps=[_app("falso", ruta, FUENTE_START_MENU)]
            )
            resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
            c = next((x for x in resultado if x.name.casefold() == "falso"), None)
            assert c is not None
            assert c.launch_type == "ejecutable"
            assert c.es_lanzable is False
            assert c.confianza == CONFIANZA_BAJA
        finally:
            os.unlink(ruta)

    def test_todo_candidato_con_destino_tiene_preflight_decision(self):
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("Notepad", ruta, FUENTE_START_MENU)]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        for c in resultado:
            if c.destination:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision


# ---------------------------------------------------------------------------
# Deduplicacion por destino real
# ---------------------------------------------------------------------------

class TestDeduplicacion:
    def test_mismo_destino_dos_fuentes_queda_uno_con_mayor_prioridad(self):
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[
                _app("Notepad", ruta, FUENTE_APPX),            # menor prioridad
                _app("Notepad", ruta, FUENTE_START_MENU),      # mayor prioridad
            ]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        notepads = [c for c in resultado if c.name.casefold() == "notepad"]
        assert len(notepads) == 1
        assert notepads[0].fuente == FUENTE_START_MENU

    def test_rutas_distintas_se_conservan_todas(self):
        ruta1 = _notepad()
        if not ruta1:
            pytest.skip("notepad.exe no disponible en este equipo")
        ruta2 = sys.executable
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("Notepad", ruta1, FUENTE_START_MENU),
                      _app("Python", ruta2, FUENTE_START_MENU)]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        destinos = {c.destination for c in resultado if c.destination}
        assert ruta1 in destinos
        assert ruta2 in destinos


# ---------------------------------------------------------------------------
# Candidatos lanzables
# ---------------------------------------------------------------------------

class TestCandidatosLanzables:
    def test_solo_retorna_lanzables(self):
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_no_lanzable = f.name
        try:
            descub, _, _ = _discovery_con_mocks(
                calib_apps=[
                    _app("Notepad", ruta, FUENTE_START_MENU),
                    _app("Falso", ruta_no_lanzable, FUENTE_START_MENU),
                ]
            )
            lanzables = descub.candidatos_lanzables(limite_por_fuente=10, incluir_inventario=False)
            nombres = {c.name for c in lanzables}
            assert "Notepad" in nombres
            assert "Falso" not in nombres
            assert all(c.es_lanzable is True for c in lanzables)
        finally:
            os.unlink(ruta_no_lanzable)


# ---------------------------------------------------------------------------
# Ambigüedad y desambiguación (unidad 3.8.5.1.4.9.3)
# ---------------------------------------------------------------------------

class TestAmbiguedadDesambiguacion:
    """3.8.5.1.4.9.3: varias coincidencias plausibles para un mismo nombre no
    se eligen silenciosamente; se conservan alternativas y se solicita
    desambiguación cuando la evidencia no permite decidir.

    Estrategia de mocks: solo se mockean las fuentes de datos
    (CalibrationManager / SystemInventoryStorage). La clasificación y el
    preflight son reales (LaunchClassifier + ApplicationPreflight sobre
    archivos reales del equipo). No se lanza ninguna aplicación y no se
    modifica entities.json.
    """

    def test_varios_candidatos_plausibles_no_se_elige_silenciosamente(self):
        """Dos aplicaciones reales que coinciden con el nombre buscado (y que
        NO están en el catálogo conocido): ambiguo=True,
        requiere_desambiguacion=True, alternativas con ambas, preflight real
        sobre cada una, sin lanzar nada."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 1024)
        try:
            descub, _, _ = _discovery_con_mocks(
                calib_apps=[
                    _app("SondaApp", notepad, FUENTE_START_MENU),
                    _app("SondaAppDos", ruta_sonda, FUENTE_START_MENU),
                ]
            )
            resultado = descub.buscar_por_nombre_con_desambiguacion("sondaapp")

            assert resultado.ambiguo is True
            assert resultado.requiere_desambiguacion is True
            assert resultado.motivo_ambiguedad is not None
            assert len(resultado.candidatos) == 2
            assert len(resultado.alternativas) == 2
            assert resultado.fuente_autoritaria is None
            destinos = {c.destination for c in resultado.alternativas if c.destination}
            assert notepad in destinos
            assert ruta_sonda in destinos
            # Preflight real sobre cada candidato; nada se lanza.
            for c in resultado.candidatos:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision
            # Serialización del resultado.
            d = resultado.to_dict()
            assert d["ambiguo"] is True
            assert d["requiere_desambiguacion"] is True
            assert len(d["alternativas"]) == 2
        finally:
            os.unlink(ruta_sonda)

    def test_un_solo_candidato_no_es_ambiguo(self):
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("Notepad", notepad, FUENTE_START_MENU)]
        )
        resultado = descub.buscar_por_nombre_con_desambiguacion("notepad")

        assert resultado.ambiguo is False
        assert resultado.requiere_desambiguacion is False
        assert resultado.motivo_ambiguedad is None
        assert resultado.alternativas == []
        assert len(resultado.candidatos) == 1

    def test_sin_candidatos_no_es_ambiguo(self):
        descub, _, _ = _discovery_con_mocks(calib_apps=[])
        resultado = descub.buscar_por_nombre_con_desambiguacion("nombreque_noexiste_xyz")

        assert resultado.ambiguo is False
        assert resultado.requiere_desambiguacion is False
        assert resultado.candidatos == []

    def test_evaluar_ambiguedad_varios_inventario_es_ambiguo(self):
        """_evaluar_ambiguedad es lógica pura sobre candidatos: varios del
        inventario sin fuente autoritativa => ambigüedad."""
        descub, _, _ = _discovery_con_mocks()
        c1 = DiscoveredCandidate(
            candidate_id="a", name="App", destination=r"C:\a\app.exe",
            fuente=FUENTE_INVENTARIO, confianza="media",
        )
        c2 = DiscoveredCandidate(
            candidate_id="b", name="App2", destination=r"C:\b\app.exe",
            fuente=FUENTE_INVENTARIO, confianza="media",
        )
        ambiguo, motivo, fuente = descub._evaluar_ambiguedad([c1, c2])
        assert ambiguo is True
        assert motivo is not None
        assert fuente is None
        assert descub._evaluar_ambiguedad([c1]) == (False, None, None)
        assert descub._evaluar_ambiguedad([]) == (False, None, None)

    def test_evaluar_ambiguedad_fuente_autoritaria_unica_no_es_ambigua(self):
        """Una fuente autoritativa (catálogo o aplicación abierta) decide:
        no hay ambigüedad aunque haya otros candidatos de menor precedencia."""
        descub, _, _ = _discovery_con_mocks()
        c_cat = DiscoveredCandidate(
            candidate_id="a", name="App", destination=r"C:\a\app.exe",
            fuente=FUENTE_CATALOGO, confianza="alta",
        )
        c_inv = DiscoveredCandidate(
            candidate_id="b", name="App2", destination=r"C:\b\app.exe",
            fuente=FUENTE_INVENTARIO, confianza="media",
        )
        c_ab = DiscoveredCandidate(
            candidate_id="c", name="App3", destination=r"C:\c\app.exe",
            fuente=FUENTE_APLICACION_ABIERTA, confianza="alta",
        )
        assert descub._evaluar_ambiguedad([c_cat]) == (False, None, FUENTE_CATALOGO)
        assert descub._evaluar_ambiguedad([c_cat, c_inv]) == (False, None, FUENTE_CATALOGO)
        assert descub._evaluar_ambiguedad([c_ab]) == (False, None, FUENTE_APLICACION_ABIERTA)

    def test_evaluar_ambiguedad_varias_fuentes_autoritativas_es_ambigua(self):
        """Varias fuentes autoritativas a destinos distintos: ambigüedad real."""
        descub, _, _ = _discovery_con_mocks()
        c_cat = DiscoveredCandidate(
            candidate_id="a", name="App", destination=r"C:\a\app.exe",
            fuente=FUENTE_CATALOGO, confianza="alta",
        )
        c_ab = DiscoveredCandidate(
            candidate_id="b", name="App2", destination=r"C:\b\app.exe",
            fuente=FUENTE_APLICACION_ABIERTA, confianza="alta",
        )
        ambiguo, motivo, fuente = descub._evaluar_ambiguedad([c_cat, c_ab])
        assert ambiguo is True
        assert motivo is not None
        assert fuente is None

    def test_resultado_resolucion_to_dict(self):
        descub, _, _ = _discovery_con_mocks()
        c = DiscoveredCandidate(
            candidate_id="a", name="App", destination=r"C:\a\app.exe",
            fuente=FUENTE_INVENTARIO, confianza="baja",
        )
        r = ResultadoResolucionCandidatos(
            candidatos=[c], ambiguo=True, motivo_ambiguedad="varias opciones",
            alternativas=[c], requiere_desambiguacion=True, fuente_autoritaria=None,
        )
        d = r.to_dict()
        assert d["ambiguo"] is True
        assert d["requiere_desambiguacion"] is True
        assert d["motivo_ambiguedad"] == "varias opciones"
        assert d["fuente_autoritaria"] is None
        assert len(d["candidatos"]) == 1 and len(d["alternativas"]) == 1


# ---------------------------------------------------------------------------
# Ambigüedad y desambiguación con almacenamiento real (unidad 3.8.5.1.4.9.3)
# ---------------------------------------------------------------------------

class TestAmbiguedadAlmacenamientoReal:
    """3.8.5.1.4.9.3 con almacenamiento real (SystemInventoryStorage SQLite,
    ApplicationPreflight y LaunchClassifier reales): varias entradas del
    inventario que coinciden con un mismo nombre se devuelven como alternativas
    ambigüas, sin lanzar nada y sin tocar entities.json."""

    def _una_entrada(self, entry_id: str, ruta: str, nombre: str,
                     extension: str = ".exe", volume: str = "C:") -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": ruta,
            "relative_path": ruta,
            "name": nombre,
            "extension": extension,
            "entry_type": EntryType.FILE.value,
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }

    def test_dos_entradas_inventario_mismo_nombre_son_alternativas_ambiguas(self, tmp_path):
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 1024)
        try:
            db_path = tmp_path / "test_inventory_93.sqlite3"
            storage = SystemInventoryStorage(db_path=db_path)
            storage.initialize()
            storage.record_machine("maquina-integracion-93")
            storage.record_volume("vol-c:", "maquina-integracion-93", "C:", "local", "online")
            storage.begin_scan_run(
                "scan-integracion-93", "maquina-integracion-93",
                "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00",
            )
            storage.insert_file_entries(
                "scan-integracion-93", "maquina-integracion-93", "C:",
                [
                    self._una_entrada("e-sonda-1", notepad, "sondapp.exe"),
                    self._una_entrada("e-sonda-2", ruta_sonda, "sondapp2.exe"),
                ],
            )
            storage.end_scan_run(
                "scan-integracion-93", "2024-01-03T01:00:00",
                SCAN_RESULT_OK, 2, 0, 0, 100.0,
            )

            preflight = ApplicationPreflight()
            clasificador = LaunchClassifier(preflight=preflight)
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=preflight,
                clasificador=clasificador,
                storage=storage,
                calibration=calib,
                machine_id="maquina-integracion-93",
            )

            hash_antes = _hash_entities_json()
            resultado = discovery.buscar_por_nombre_con_desambiguacion("sondapp")
            hash_despues = _hash_entities_json()
            assert hash_despues == hash_antes, "entities.json no debe modificarse"

            assert resultado.ambiguo is True
            assert resultado.requiere_desambiguacion is True
            assert resultado.motivo_ambiguedad is not None
            assert len(resultado.candidatos) == 2
            assert len(resultado.alternativas) == 2
            assert resultado.fuente_autoritaria is None
            nombres = {c.name for c in resultado.alternativas}
            assert "sondapp.exe" in nombres
            assert "sondapp2.exe" in nombres
            for c in resultado.alternativas:
                assert c.fuente == FUENTE_INVENTARIO
                assert c.esta_en_inventario is True
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision
            d = resultado.to_dict()
            assert d["ambiguo"] is True
            assert d["requiere_desambiguacion"] is True
        finally:
            os.unlink(ruta_sonda)


# ---------------------------------------------------------------------------
# Deduplicacion por identidad y destino real (.7.7)
# ---------------------------------------------------------------------------

class TestDeduplicarPorDestinoReal:
    """Pruebas de `ApplicationDiscovery.deduplicar_por_destino_real` sobre
    `DiscoveredCandidate` ya clasificados."""

    def _candidato_discovered(self, name, destination, fuente=FUENTE_START_MENU,
                              confianza="media", launch_type="ejecutivo", evidencia=None):
        return DiscoveredCandidate(
            candidate_id=destination or name,
            name=name,
            absolute_path=destination,
            destination=destination,
            launch_type=launch_type,
            confianza=confianza,
            evidencia=list(evidencia or []),
            fuente=fuente,
        )

    def test_mismo_destino_ruta_queda_uno(self):
        """Misma ruta real: se conserva solo el candidato con mayor confianza."""
        descub, _, _ = _discovery_con_mocks()
        ruta = sys.executable
        candidatos = [
            self._candidato_discovered("python_a", ruta, confianza="baja", evidencia=["a"]),
            self._candidato_discovered("python_b", ruta, confianza="alta", evidencia=["b", "c"]),
        ]
        resultado = descub.deduplicar_por_destino_real(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == ruta
        assert resultado[0].confianza == "alta"

    def test_rutas_distintas_se_conservan_todas(self):
        """Rutas distintas son instalaciones diferentes: se conservan todas."""
        descub, _, _ = _discovery_con_mocks()
        ruta1 = sys.executable
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta2 = f.name
        try:
            candidatos = [
                self._candidato_discovered("app_a", ruta1, confianza="alta"),
                self._candidato_discovered("app_b", ruta2, confianza="alta"),
            ]
            resultado = descub.deduplicar_por_destino_real(candidatos)
            assert len(resultado) == 2
            destinos = {c.destination for c in resultado}
            assert destinos == {ruta1, ruta2}
        finally:
            os.unlink(ruta2)

    def test_mismo_uri_se_deduplica(self):
        """Misma URI (misma identidad de destino): se deduplica a uno."""
        descub, _, _ = _discovery_con_mocks()
        uri = "ms-settings:"
        candidatos = [
            self._candidato_discovered("config_a", uri, launch_type="uri_aplicacion", confianza="baja"),
            self._candidato_discovered("config_b", uri, launch_type="uri_aplicacion", confianza="alta"),
        ]
        resultado = descub.deduplicar_por_destino_real(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == uri
        assert resultado[0].confianza == "alta"

    def test_mismo_uri_lanzador_se_deduplica(self):
        """Misma URI de lanzador: se deduplica a uno (.7.7 incluye LANZADOR)."""
        descub, _, _ = _discovery_con_mocks()
        uri = "steam://rungameid/12345"
        candidatos = [
            self._candidato_discovered("steam_a", uri, launch_type="lanzador", confianza="baja"),
            self._candidato_discovered("steam_b", uri, launch_type="lanzador", confianza="alta"),
        ]
        resultado = descub.deduplicar_por_destino_real(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination == uri
        assert resultado[0].launch_type == "lanzador"
        assert resultado[0].confianza == "alta"

    def test_uris_lanzador_distintas_se_conservan(self):
        """URIs de lanzador distintas: se conservan todas."""
        descub, _, _ = _discovery_con_mocks()
        candidatos = [
            self._candidato_discovered("steam", "steam://rungameid/100", launch_type="lanzador"),
            self._candidato_discovered("epic", "epic://launch/200", launch_type="lanzador"),
        ]
        resultado = descub.deduplicar_por_destino_real(candidatos)
        assert len(resultado) == 2
        destinos = {c.destination for c in resultado}
        assert destinos == {"steam://rungameid/100", "epic://launch/200"}

    def test_sin_destino_va_a_sueltos(self):
        """Candidato sin destino identificable se conserva como suelto."""
        descub, _, _ = _discovery_con_mocks()
        candidatos = [
            self._candidato_discovered("fantasma", None),
        ]
        resultado = descub.deduplicar_por_destino_real(candidatos)
        assert len(resultado) == 1
        assert resultado[0].destination is None

    def test_ordena_por_confianza_descendente(self):
        """Resultado ordenado por confianza descendente."""
        descub, _, _ = _discovery_con_mocks()
        ruta1 = sys.executable
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta2 = f.name
        try:
            candidatos = [
                self._candidato_discovered("baja", ruta1, confianza="baja"),
                self._candidato_discovered("alta", ruta2, confianza="alta"),
                self._candidato_discovered("media", ruta1, confianza="media"),  # mismo destino que baja, se descarta
            ]
            resultado = descub.deduplicar_por_destino_real(candidatos)
            assert len(resultado) == 2
            assert _puntos_confianza(resultado[0].confianza) >= _puntos_confianza(resultado[1].confianza)
        finally:
            os.unlink(ruta2)


def _puntos_confianza(confianza: str) -> int:
    return {"alta": 3, "media": 2, "baja": 1, "ninguna": 0}.get(confianza or "ninguna", 0)


# ---------------------------------------------------------------------------
# Separacion catalogo dinamico vs entities.json (.7.8)
# ---------------------------------------------------------------------------

# Las siete entidades originales de data/knowledge/entities.json (documentadas
# en docs/README_DATA.md seccion 4.1) nunca deben verse alteradas por el flujo
# de descubrimiento y registro de candidatos.
ENTIDADES_ORIGINALES = (
    "nissaxter", "shroud", "pokimane",
    "youtube", "spotify", "github", "twitch",
)


def _ruta_entities_json() -> Path:
    """Ruta absoluta (según __file__) a data/knowledge/entities.json del repo."""
    return Path(__file__).resolve().parents[2] / "data" / "knowledge" / "entities.json"


def _hash_entities_json() -> str:
    """Huella SHA-256 de entities.json; solo lectura, nunca escritura."""
    h = hashlib.sha256()
    with open(_ruta_entities_json(), "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _leer_ids_entidades() -> list[str]:
    with open(_ruta_entities_json(), "r", encoding="utf-8") as f:
        datos = json.load(f)
    return [str(e.get("id", "")) for e in datos]


class TestSeparacionCatalogoDinamicoEntitiesJson:
    """.7.8: verificar que los candidatos descubiertos se mantienen en el
    catalogo dinamico separado (tabla SQLite `application_candidates` vía
    `ApplicationDiscovery.registrar_candidatos`) y que
    `data/knowledge/entities.json`, su esquema y las siete entidades originales
    no se modifican durante el flujo de descubrimiento y registro.

    Ninguna prueba de esta clase escribe en entities.json ni en el inventario
    de produccion: el almacenamiento SQLite se apunta a un fichero temporal y
    entities.json solo se lee para calcular su huella y leer sus ids.
    """

    def test_registrar_candidatos_no_modifica_entities_json(self, tmp_path):
        """registrar_candidatos persiste en application_candidates (catalogo
        separado) y deja entities.json con la misma huella y las mismas 7
        entidades."""
        db_path = tmp_path / "test_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize()
        discovery = ApplicationDiscovery(storage=storage, machine_id="maquina-test-78")

        hash_antes = _hash_entities_json()
        ids_antes = _leer_ids_entidades()

        ruta = sys.executable
        candidatos = [
            DiscoveredCandidate(
                candidate_id="c-78-1", name="Python",
                absolute_path=ruta, destination=ruta,
                launch_type="ejecutivo",
                confianza=CONFIANZA_ALTA,
                evidencia=["archivo_ejecutivo_existente", "version_recurso_leida"],
                version="3.14.7", producto="Python",
                fuente=FUENTE_INVENTARIO,
                ultima_comprobacion="2024-01-03T00:00:00+00:00",
            )
        ]

        insertados = discovery.registrar_candidatos(candidatos, volume="C:")
        assert insertados == 1

        # Los candidatos se recuperan del catalogo separado (SQLite application_candidates),
        # nunca de entities.json.
        recuperados = storage.buscar_candidatos_registrados("maquina-test-78")
        assert len(recuperados) == 1
        assert recuperados[0]["candidate_id"] == "c-78-1"
        assert recuperados[0]["name"] == "Python"
        assert recuperados[0]["fuente"] == FUENTE_INVENTARIO

        # entities.json no se modifico durante el registro.
        hash_despues = _hash_entities_json()
        assert hash_despues == hash_antes, (
            "entities.json fue modificado durante el registro de candidatos"
        )
        ids_despues = _leer_ids_entidades()
        assert ids_despues == ids_antes
        for eid in ENTIDADES_ORIGINALES:
            assert eid in ids_despues, f"La entidad original {eid} desaparecio de entities.json"

    def test_flujo_descubrir_y_registrar_respeta_entidades_originales(self, tmp_path):
        """Flujo completo: descubrimiento (clasificacion/preflight reales sobre
        archivos del sistema) + registro en catalogo separado, sin tocar
        entities.json."""
        db_path = tmp_path / "test_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize()
        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        ruta = _notepad()
        if not ruta:
            pytest.skip("notepad.exe no disponible en este equipo")
        calib.discover_applications.return_value = [
            _app("Notepad", ruta, FUENTE_START_MENU)
        ]
        discovery = ApplicationDiscovery(
            preflight=preflight, clasificador=clasificador,
            storage=storage, calibration=calib, machine_id="maquina-test-78b",
        )

        hash_antes = _hash_entities_json()
        ids_antes = _leer_ids_entidades()

        descubiertos = discovery.descubrir_todos(
            limite_por_fuente=10, incluir_inventario=False
        )
        assert len(descubiertos) >= 1
        insertados = discovery.registrar_candidatos(descubiertos, volume="C:")
        assert insertados >= 1

        recuperados = storage.buscar_candidatos_registrados("maquina-test-78b")
        assert len(recuperados) >= 1
        assert any(r["name"].casefold() == "notepad" for r in recuperados)

        hash_despues = _hash_entities_json()
        assert hash_despues == hash_antes
        ids_despues = _leer_ids_entidades()
        assert ids_despues == ids_antes
        for eid in ENTIDADES_ORIGINALES:
            assert eid in ids_despues

    def test_esquema_entities_json_invariante_siete_entidades(self):
        """El esquema de entities.json conserva exactamente las siete entidades
        originales con sus ids conocidos."""
        ids = _leer_ids_entidades()
        assert len(ids) == 7, f"Se esperaban 7 entidades, se encontraron {len(ids)}"
        for eid in ENTIDADES_ORIGINALES:
            assert eid in ids


# ---------------------------------------------------------------------------
# Integración con almacenamiento real (unidad 3.8.5.1.4.9.1)
# ---------------------------------------------------------------------------

class TestInventarioComplementoAlmacenamientoReal:
    """
    Pruebas de integración con almacenamiento real para verificar que la
    consulta al inventario como fuente complementaria de 3.8.1-3.8.3 funciona
    con SystemInventoryStorage real y ApplicationPreflight real (sin lanzar
    aplicaciones).

    Unidad: 3.8.5.1.4.9.1 — Integrar la consulta al inventario como fuente
    complementaria de 3.8.1-3.8.3; solo descubre/resuelve candidatos y los
    entrega a preflight, no lanza aplicaciones.
    """

    def _una_entrada(self, entry_id: str, ruta: str, nombre: str,
                     extension: str = ".exe", volume: str = "C:") -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": ruta,
            "relative_path": ruta,
            "name": nombre,
            "extension": extension,
            "entry_type": EntryType.FILE.value,
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }

    def test_buscar_por_nombre_con_inventario_real_encuentra_candidatos(self, tmp_path):
        """Con almacenamiento real y preflight real, buscar_por_nombre
        encuentra candidatos en el inventario cuando primarias no tienen
        coincidencia. No lanza aplicaciones: solo descubre/resuelve y valida
        con preflight (verificación real de unidad 3.8.5.1.4.9.1).

        Nota: se usa un nombre que NO está en el catálogo conocido para
        forzar el camino del inventario como fuente complementaria, ya que
        el catálogo conocido tiene mayor precedencia (unidad 3.8.5.1.4.9.2).
        """
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        db_path = tmp_path / "test_inventory_91.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize()
        storage.record_machine("maquina-integracion-91")
        storage.record_volume("vol-c:", "maquina-integracion-91", "C:",
                              "local", "online")
        storage.begin_scan_run("scan-integracion-91", "maquina-integracion-91",
                               "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00")

        # Insertar entrada apuntando a archivo real del sistema con un nombre
        # que no pertenece al catálogo conocido (para forzar fallback al
        # inventario).
        storage.insert_file_entries("scan-integracion-91", "maquina-integracion-91",
                                    "C:", [self._una_entrada("e-miapp", notepad,
                                                             "miapp.exe")])
        storage.end_scan_run("scan-integracion-91", "2024-01-03T01:00:00",
                             SCAN_RESULT_OK, 1, 0, 0, 100.0)

        # Discovery con almacenamiento REAL y calibración mockeada (sin
        # resultados primarios, para forzar fallback al inventario como
        # fuente complementaria).
        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        calib.discover_applications.return_value = []

        discovery = ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=calib,
            machine_id="maquina-integracion-91",
        )

        # buscar_por_nombre: primarias vacías → consulta inventario como complemento
        resultado = discovery.buscar_por_nombre("miapp", incluir_inventario=True)

        assert len(resultado) >= 1
        assert any(c.name.casefold() == "miapp.exe" for c in resultado)
        assert any(c.fuente == FUENTE_INVENTARIO for c in resultado)
        assert any(c.esta_en_inventario is True for c in resultado)
        assert any(FUENTE_INVENTARIO in c.fuentes_consultadas
                   for c in resultado)

        # Los candidatos deben tener preflight_decision de validación real
        # (sin lanzar la aplicación).
        for c in resultado:
            if c.destination:
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
                assert "launch_type" in c.preflight_decision
                # Notepad es un .exe real existente: preflight debe validar el destino
                assert c.preflight_decision["valid"] is True
                assert c.preflight_decision["launch_type"] == "ejecutable"


# ---------------------------------------------------------------------------
# Estado vigente de rutas de candidatos (unidad 3.8.5.1.4.9.4)
# ---------------------------------------------------------------------------

class TestEstadoVigenteRutasInaccesibles:
    """3.8.5.1.4.9.4: si la ruta de un candidato ha cambiado, ha desaparecido
    o ya no es accesible, se actualiza su estado y la resolución se repite
    con fuentes vigentes; no se intenta la ruta obsoleta.

    Estrategia de mocks: solo se mockean las fuentes de datos
    (CalibrationManager.discover_applications y SystemInventoryStorage). La
    clasificacion y el preflight son REALES (LaunchClassifier +
    ApplicationPreflight sobre archivos reales del equipo), por lo que ningún
    mock decide el resultado de la validacion. No se lanza ninguna aplicacion
    y no se modifica entities.json.
    """

    def _una_entrada(self, entry_id: str, ruta: str, nombre: str,
                     extension: str = ".exe", volume: str = "C:") -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": ruta,
            "relative_path": ruta,
            "name": nombre,
            "extension": extension,
            "entry_type": EntryType.FILE.value,
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }

    # ------ Unitarios: fuentes de datos mockeadas, clasificacion/preflight reales ------

    def test_excluye_candidato_inventario_ruta_eliminada_y_actualiza_estado(self):
        """Entrada de inventario cuyo archivo ya no existe: excluida de la
        resolucion, disponible=False, ultima comprobacion y evidencia
        registradas. No se intenta la ruta obsoleta."""
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_eliminada = f.name
        os.unlink(ruta_eliminada)
        try:
            storage.search.return_value = [
                {
                    "absolute_path": ruta_eliminada,
                    "name": "borradoapp.exe",
                    "volume": "C:",
                    "entry_type": "file",
                    "last_checked_at": "2024-01-03T00:00:00",
                }
            ]
            resultado = descub.buscar_por_nombre("borradoapp", incluir_inventario=True)

            assert resultado == []
            inaccesibles = descub.candidatos_inaccesibles_ultima_resolucion
            assert len(inaccesibles) == 1
            assert inaccesibles[0].disponible is False
            assert inaccesibles[0].ultima_comprobacion != ""
            assert any("inaccesible" in advertencia
                       for advertencia in inaccesibles[0].advertencias)
            assert any("ruta_no_accesible_en_disco" in evidencia
                       for evidencia in inaccesibles[0].evidencia)
            assert inaccesibles[0].preflight_decision is None
        finally:
            if os.path.exists(ruta_eliminada):
                os.unlink(ruta_eliminada)

    def test_ruta_vigente_se_devuelve_con_disponible_true(self):
        """Entrada de inventario con ruta existente: se devuelve y su estado
        sigue disponible=True."""
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        storage.search.return_value = [
            {
                "absolute_path": sys.executable,
                "name": "miapp.exe",
                "volume": "C:",
                "entry_type": "file",
                "last_checked_at": "",
            }
        ]
        resultado = descub.buscar_por_nombre("miapp", incluir_inventario=True)

        assert len(resultado) == 1
        assert resultado[0].name.casefold() == "miapp.exe"
        assert resultado[0].disponible is True

    def test_ruta_uri_no_se_descarta_por_no_existir_como_archivo(self):
        """Un destino URI (no es archivo de disco) no se descarta por no
        existir en el sistema de archivos."""
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        storage.search.return_value = [
            {
                "absolute_path": "ms-settings:",
                "name": "configuracion.exe",
                "volume": None,
                "entry_type": "file",
                "last_checked_at": "",
            }
        ]
        resultado = descub.buscar_por_nombre("configuracion", incluir_inventario=True)

        assert len(resultado) == 1
        assert resultado[0].destination == "ms-settings:"
        assert resultado[0].disponible is True

    def test_re_resolucion_con_fuentes_vigentes_descarta_la_obsoleta(self):
        """Mismo nombre con una ruta eliminada y otra vigente: solo se
        devuelve la vigente; la obsoleta queda registrada como inaccesible."""
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_eliminada = f.name
        os.unlink(ruta_eliminada)
        try:
            storage.search.return_value = [
                {
                    "absolute_path": ruta_eliminada,
                    "name": "dualapp.exe",
                    "volume": "C:",
                    "entry_type": "file",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
                {
                    "absolute_path": sys.executable,
                    "name": "dualapp.exe",
                    "volume": "C:",
                    "entry_type": "file",
                    "last_checked_at": "",
                },
            ]
            resultado = descub.buscar_por_nombre("dualapp", incluir_inventario=True)

            assert len(resultado) == 1
            assert resultado[0].destination == sys.executable
            assert resultado[0].disponible is True
            inaccesibles = descub.candidatos_inaccesibles_ultima_resolucion
            assert len(inaccesibles) == 1
            assert inaccesibles[0].destination == ruta_eliminada
            assert inaccesibles[0].disponible is False
        finally:
            if os.path.exists(ruta_eliminada):
                os.unlink(ruta_eliminada)

    # ------ Integracion con almacenamiento real (SQLite, preflight y
    # revalidacion de destino reales) ------

    def test_inventario_real_ruta_eliminada_excluida_estado_persistido(self, tmp_path):
        """Almacenamiento SQLite real, preflight real y revalidacion de
        destino real: la entrada cuya ruta se elimino no se resuelve, su
        estado se persiste (last_checked_at actualizado) y no se lanza nada.
        entities.json no se modifica."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_inaccesible = f.name
        os.unlink(ruta_inaccesible)
        try:
            db_path = tmp_path / "test_inventory_94.sqlite3"
            storage = SystemInventoryStorage(db_path=db_path)
            storage.initialize()
            storage.record_machine("maquina-integracion-94")
            storage.record_volume("vol-c:", "maquina-integracion-94", "C:",
                                  "local", "online")
            storage.begin_scan_run("scan-integracion-94", "maquina-integracion-94",
                                   "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00")
            storage.insert_file_entries("scan-integracion-94", "maquina-integracion-94",
                                        "C:", [
                                            self._una_entrada("e-borrado-94",
                                                              ruta_inaccesible,
                                                              "borradoapp94.exe"),
                                            self._una_entrada("e-notepad-94",
                                                              notepad,
                                                              "notepad.exe"),
                                        ])
            storage.end_scan_run("scan-integracion-94", "2024-01-03T01:00:00",
                                 SCAN_RESULT_OK, 2, 0, 0, 100.0)

            preflight = ApplicationPreflight()
            clasificador = LaunchClassifier(preflight=preflight)
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=preflight,
                clasificador=clasificador,
                storage=storage,
                calibration=calib,
                machine_id="maquina-integracion-94",
            )

            hash_antes = _hash_entities_json()

            # Ruta eliminada: excluida de la resolucion y su estado actualizado.
            resultado = discovery.buscar_por_nombre("borradoapp94",
                                                    incluir_inventario=True)
            assert resultado == []
            inaccesibles = discovery.candidatos_inaccesibles_ultima_resolucion
            assert len(inaccesibles) == 1
            assert inaccesibles[0].disponible is False
            assert inaccesibles[0].ultima_comprobacion != ""
            assert any("inaccesible" in advertencia
                       for advertencia in inaccesibles[0].advertencias)

            # Estado persistido: last_checked_at de la entrada se actualizo en
            # el almacenamiento real mediante la revalidacion de destino.
            filas = storage.search("maquina-integracion-94", extension=".exe",
                                   tipo=EntryType.FILE.value,
                                   solo_volumes_montados=True)
            fila_borrado = [f for f in filas
                            if str(f.get("absolute_path", "")) == ruta_inaccesible]
            assert len(fila_borrado) == 1
            assert fila_borrado[0]["last_checked_at"] != "2024-01-03T00:00:00"

            # Fuente vigente (notepad) sigue resolviéndose.
            resultado_notepad = discovery.buscar_por_nombre("notepad",
                                                            incluir_inventario=True)
            assert len(resultado_notepad) >= 1
            assert any(str(c.destination or "").casefold() == notepad.casefold()
                       for c in resultado_notepad)
            assert all(c.disponible is True for c in resultado_notepad)

            hash_despues = _hash_entities_json()
            assert hash_despues == hash_antes, "entities.json no debe modificarse"
        finally:
            if os.path.exists(ruta_inaccesible):
                os.unlink(ruta_inaccesible)


# ---------------------------------------------------------------------------
# Unidad 3.8.5.1.4.9.7: aislamiento por equipo y volumen del inventario;
# deteccion de host distinto y exigencia de reescaneo antes de usar destinos
# ---------------------------------------------------------------------------


class TestAislamientoInventarioPorEquipo:
    """El inventario persistente esta aislado por equipo: si la base de datos
    se copia a otro host, no se usan sus destinos y se exige reescaneo.
    Ninguna prueba lanza aplicaciones ni modifica entities.json."""

    def test_inventario_de_otro_equipo_no_se_consulta(
        self, tmp_path: Path
    ):
        """Storage de maquina distinta: discovery no consulta el inventario y
        senaliza requiere_reescaneo."""
        db_path = tmp_path / "inventario_otro_equipo.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual="maquina-otra-97")
        storage.record_machine("maquina-otra-97")
        storage.record_volume("vol-c:", "maquina-otra-97", "C:", "local", "online")

        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=calib,
            machine_id="maquina-actual-97",
        )

        informe = discovery.verificar_aislamiento_inventario()
        assert informe["bloqueado"] is True
        assert informe["equipo_coincide"] is False
        assert informe["requiere_reescaneo"] is True
        assert informe["inventario_utilizable"] is False
        assert discovery.inventario_requiere_reescaneo is True
        assert discovery.inventario_utilizable_para_maquina_actual is False
        assert discovery.informe_aislamiento_ultima_resolucion["requiere_reescaneo"] is True

        # El inventario no se consulta como fuente complementaria.
        resultado = discovery.buscar_por_nombre("cualquierapp", incluir_inventario=True)
        assert resultado == []

    def test_misma_maquina_inventario_utilizable(
        self, tmp_path: Path
    ):
        """Mismo equipo: el inventario puede consultarse y no senaliza
        reescaneo."""
        maquina = generate_machine_id()
        db_path = tmp_path / "inventario_misma_maquina.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual=maquina)
        storage.record_machine(maquina)
        storage.record_volume("vol-c:", maquina, "C:", "local", "online")

        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=calib,
            machine_id=maquina,
        )

        informe = discovery.verificar_aislamiento_inventario()
        assert informe["bloqueado"] is False
        assert informe["equipo_coincide"] is True
        assert informe["requiere_reescaneo"] is False
        assert informe["inventario_utilizable"] is True
        assert discovery.inventario_utilizable_para_maquina_actual is True
        assert discovery.inventario_requiere_reescaneo is False

    def test_inventario_copiado_a_otro_equipo_no_se_usa_entorno_real(
        self, tmp_path: Path
    ):
        """Copia fisica de la base de inventario en otro equipo (simulado con
        machine_id distinto): no se usan los destinos del inventario copiado y
        se exige reescaneo. La base original del equipo actual sigue sirviendo
        sus candidatos. No se lanza ninguna aplicacion."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        maquina_actual = generate_machine_id()
        maquina_otra = "maquina-otra-97-inexistente"

        # Base de inventario real del equipo actual con un candidato de
        # inventario que solo existe ahi.
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"MZplaceholder")
            ruta_inventario_real = f.name
        try:
            db_path = tmp_path / "inventario_real.sqlite3"
            storage = SystemInventoryStorage(db_path=db_path)
            storage.initialize(machine_id_actual=maquina_actual)
            storage.record_machine(maquina_actual)
            storage.record_volume("vol-c:", maquina_actual, "C:", "local", "online")
            storage.begin_scan_run("scan-97", maquina_actual, "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00")
            storage.insert_file_entries("scan-97", maquina_actual, "C:", [
                {
                    "entry_id": "e-app-97",
                    "absolute_path": ruta_inventario_real,
                    "relative_path": ruta_inventario_real,
                    "name": "appinventario97.exe",
                    "extension": ".exe",
                    "entry_type": EntryType.FILE.value,
                    "size_bytes": 1024,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                },
            ])
            storage.end_scan_run("scan-97", "2024-01-03T01:00:00", SCAN_RESULT_OK, 1, 0, 0, 100.0)

            preflight = ApplicationPreflight()
            clasificador = LaunchClassifier(preflight=preflight)
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery_actual = ApplicationDiscovery(
                preflight=preflight,
                clasificador=clasificador,
                storage=storage,
                calibration=calib,
                machine_id=maquina_actual,
            )

            # Mismo equipo: el candidato del inventario se resuelve.
            resultado_actual = discovery_actual.buscar_por_nombre(
                "appinventario97", incluir_inventario=True
            )
            assert len(resultado_actual) == 1
            assert resultado_actual[0].fuente == FUENTE_INVENTARIO
            assert str(resultado_actual[0].destination or "").casefold() == ruta_inventario_real.casefold()
            assert discovery_actual.inventario_utilizable_para_maquina_actual is True

            # Cerrar la conexion original (checkpoint del modo WAL) antes de
            # copiar el fichero, para que la copia contenga todo lo commitado.
            storage.close()

            # Copia fisica de la base a otro equipo.
            db_copia = tmp_path / "inventario_copia.sqlite3"
            shutil.copy2(db_path, db_copia)

            storage_copia = SystemInventoryStorage(db_path=db_copia)
            discovery_otra = ApplicationDiscovery(
                preflight=preflight,
                clasificador=clasificador,
                storage=storage_copia,
                calibration=calib,
                machine_id=maquina_otra,
            )

            informe_otra = discovery_otra.verificar_aislamiento_inventario()
            assert informe_otra["bloqueado"] is True
            assert informe_otra["equipo_coincide"] is False
            assert informe_otra["requiere_reescaneo"] is True
            assert informe_otra["inventario_utilizable"] is False

            # El inventario copiado no se consulta: no devuelve sus destinos.
            resultado_otra = discovery_otra.buscar_por_nombre(
                "appinventario97", incluir_inventario=True
            )
            assert resultado_otra == []
            assert discovery_otra.inventario_requiere_reescaneo is True
            assert discovery_otra.informe_aislamiento_ultima_resolucion["requiere_reescaneo"] is True

            storage_copia.close()
        finally:
            if os.path.exists(ruta_inventario_real):
                os.unlink(ruta_inventario_real)


class _AppManagerFake:
    """Doble ligero de ApplicationManager con get_application controlado por
    prueba. Solo lectura: nunca escribe entities.json."""

    def __init__(self, apps_por_nombre: Optional[dict] = None) -> None:
        self._apps = {str(k).strip().lower(): v for k, v in (apps_por_nombre or {}).items()}
        self.llamadas: list[str] = []

    def get_application(self, app_name: str):
        self.llamadas.append(str(app_name))
        return self._apps.get(str(app_name).strip().lower())


def _conocimiento_prueba(
    nombre: str = "Notepad", executable: str = "notepad.exe", tipo: str = "application"
) -> ApplicationKnowledge:
    return ApplicationKnowledge(
        name=nombre,
        type=tipo,
        executable=executable,
        capabilities=[
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN,
                name="open_" + nombre.strip().lower().replace(" ", "_"),
                description=f"Abre {nombre}",
                required_ui_elements=[],
                preconditions=[],
                effects=[],
                cost=5.0,
            )
        ],
    )


def _ruta_entities_json_memoria() -> Path:
    """Ruta absoluta a data/memory/entities.json (catalogo global)."""
    return Path(__file__).resolve().parents[2] / "data" / "memory" / "entities.json"


def _hash_archivo(ruta: Path) -> str:
    """Huella SHA-256 de un archivo; solo lectura, nunca escritura."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _discovery_con_manager_y_storage(
    app_manager,
    storage_entries: Optional[list] = None,
    machine_id: str = "maquina-vincula",
    calib_apps: Optional[list] = None,
):
    """ApplicationDiscovery con preflight/clasificador REALES, storage mockeado
    y application_manager inyectado."""
    preflight = ApplicationPreflight()
    clasificador = LaunchClassifier(preflight=preflight)
    storage = MagicMock()
    storage.connect.return_value = None
    storage.close.return_value = None
    storage.search.return_value = storage_entries or []
    calib = MagicMock()
    calib.discover_applications.return_value = calib_apps or []
    return ApplicationDiscovery(
        preflight=preflight,
        clasificador=clasificador,
        storage=storage,
        calibration=calib,
        machine_id=machine_id,
        app_manager=app_manager,
    )


class TestVinculacionCatalogo:
    """Unidad 3.8.5.1.4.9.5: vincular candidatos con ApplicationManager /
    ApplicationKnowledge solo mediante contratos verificados, sin modificar
    entities.json, sin lanzar aplicaciones y sin auto-registro."""

    def test_vinculacion_encuentra_conocimiento_por_nombre_tal_cual(self):
        """Candidato del inventario cuyo nombre coincide con una entidad del
        catalogo global: se vincula su ApplicationKnowledge."""
        manager = _AppManagerFake(
            {"bloc de notas": _conocimiento_prueba("Bloc de notas", "notepad.exe")}
        )
        discovery = _discovery_con_manager_y_storage(manager)
        candidato = DiscoveredCandidate(
            candidate_id="inv-1",
            name="bloc de notas",
            absolute_path=r"C:\Windows\System32\notepad.exe",
            destination=r"C:\Windows\System32\notepad.exe",
            fuente=FUENTE_INVENTARIO,
            esta_en_inventario=True,
            disponible=True,
        )
        vinculados = discovery.vincular_con_catalogo([candidato])
        assert len(vinculados) == 1
        v = vinculados[0]
        assert v.candidato is candidato
        assert v.en_catalogo_global is True
        assert v.conocimiento is not None
        assert v.conocimiento.name == "Bloc de notas"
        assert v.conocimiento.executable == "notepad.exe"
        # fuente inventario no es autoritativa; el catalogo decide la identidad
        assert v.fuente_autoritaria == FUENTE_CATALOGO
        d = v.to_dict()
        assert d["en_catalogo_global"] is True
        assert d["conocimiento"]["name"] == "Bloc de notas"
        assert d["conocimiento"]["executable"] == "notepad.exe"

    def test_vinculacion_no_encuentra_conocimiento_desconocido(self):
        """Candidato del inventario sin entidad en el catalogo: no se vincula
        a ningun ApplicationKnowledge."""
        manager = _AppManagerFake({})
        discovery = _discovery_con_manager_y_storage(manager)
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
        try:
            candidato = DiscoveredCandidate(
                candidate_id="inv-sonda",
                name="sondapp.exe",
                absolute_path=ruta_sonda,
                destination=ruta_sonda,
                fuente=FUENTE_INVENTARIO,
                esta_en_inventario=True,
                disponible=True,
            )
            vinculados = discovery.vincular_con_catalogo([candidato])
            assert len(vinculados) == 1
            v = vinculados[0]
            assert v.en_catalogo_global is False
            assert v.conocimiento is None
            assert v.fuente_autoritaria is None
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)

    def test_vinculacion_preserva_fuente_autoritaria(self):
        """La fuente autoritativa (aplicacion abierta / catalogo conocido) se
        preserva; un candidato del inventario vinculado al catalogo pasa a
        catalogo_conocido y uno no encontrado queda sin fuente autoritativa."""
        app = _conocimiento_prueba("App", "app.exe")
        manager = _AppManagerFake({"app": app})
        discovery = _discovery_con_manager_y_storage(manager)

        abierta = DiscoveredCandidate(
            candidate_id="a", name="app.exe", absolute_path=r"C:\app.exe",
            destination=r"C:\app.exe", fuente=FUENTE_APLICACION_ABIERTA, disponible=True,
        )
        catalogo = DiscoveredCandidate(
            candidate_id="b", name="app.exe", absolute_path=r"C:\app.exe",
            destination=r"C:\app.exe", fuente=FUENTE_CATALOGO, disponible=True,
        )
        inventario_encontrado = DiscoveredCandidate(
            candidate_id="c", name="app.exe", absolute_path=r"C:\app.exe",
            destination=r"C:\app.exe", fuente=FUENTE_INVENTARIO, disponible=True,
        )
        inventario_no_encontrado = DiscoveredCandidate(
            candidate_id="d", name="otro.exe", absolute_path=r"C:\otro.exe",
            destination=r"C:\otro.exe", fuente=FUENTE_INVENTARIO, disponible=True,
        )
        vinculados = discovery.vincular_con_catalogo(
            [abierta, catalogo, inventario_encontrado, inventario_no_encontrado]
        )
        assert [v.fuente_autoritaria for v in vinculados] == [
            FUENTE_APLICACION_ABIERTA,
            FUENTE_CATALOGO,
            FUENTE_CATALOGO,
            None,
        ]
        assert [v.en_catalogo_global for v in vinculados] == [True, True, True, False]

    def test_vinculacion_coincide_por_stem_ejecutivo_sin_extension(self):
        """El nombre del ejecutable sin extension permite vincular con el
        catalogo cuando el nombre del archivo difiere (p.ej. instalador)."""
        manager = _AppManagerFake(
            {"discord": _conocimiento_prueba("Discord", "Discord.exe")}
        )
        discovery = _discovery_con_manager_y_storage(manager)
        candidato = DiscoveredCandidate(
            candidate_id="inv-discord",
            name="DiscordInstalador.exe",
            absolute_path=r"C:\Program Files\Discord\Discord.exe",
            destination=r"C:\Program Files\Discord\Discord.exe",
            fuente=FUENTE_INVENTARIO,
            esta_en_inventario=True,
            disponible=True,
        )
        vinculados = discovery.vincular_con_catalogo([candidato])
        assert len(vinculados) == 1
        v = vinculados[0]
        assert v.en_catalogo_global is True
        assert v.conocimiento is not None
        assert v.conocimiento.name == "Discord"
        assert v.fuente_autoritaria == FUENTE_CATALOGO

    def test_vinculacion_no_modifica_entities_json_memoria(self):
        """Con el ApplicationManager real (catalogo entities.json), vincular
        solo lee: la huella de data/memory/entities.json no cambia."""
        discovery = ApplicationDiscovery(machine_id="maquina-vincula-real")
        hash_antes = _hash_archivo(_ruta_entities_json_memoria())

        conocidos = [
            DiscoveredCandidate(
                candidate_id="r1",
                name="bloc de notas",
                absolute_path=r"C:\Windows\System32\notepad.exe",
                destination=r"C:\Windows\System32\notepad.exe",
                fuente=FUENTE_INVENTARIO,
                esta_en_inventario=True,
                disponible=True,
            ),
            DiscoveredCandidate(
                candidate_id="r2",
                name="sondapp-no-existe.exe",
                absolute_path=r"C:\no\existe\sondapp.exe",
                destination=r"C:\no\existe\sondapp.exe",
                fuente=FUENTE_INVENTARIO,
                esta_en_inventario=True,
                disponible=True,
            ),
        ]
        vinculados = discovery.vincular_con_catalogo(conocidos)
        assert len(vinculados) == 2
        assert vinculados[0].en_catalogo_global is True
        assert vinculados[0].conocimiento is not None
        assert vinculados[0].conocimiento.name == "Bloc de notas"
        assert vinculados[0].conocimiento.executable == "notepad.exe"
        assert vinculados[1].en_catalogo_global is False
        assert vinculados[1].conocimiento is None

        hash_despues = _hash_archivo(_ruta_entities_json_memoria())
        assert hash_despues == hash_antes, (
            "vincular_con_catalogo no debe escribir data/memory/entities.json"
        )

    def test_buscar_por_nombre_con_catalogo_devuelve_tupla_ordenada(self):
        """Flujo combinado: buscar_por_nombre + vincular_con_catalogo con
        preflight/clasificador reales sobre un archivo real. Nombre sin entidad
        en el catalogo devuelve candidato de inventario sin vinculo."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 64)
        try:
            manager = _AppManagerFake({})
            storage = MagicMock()
            storage.connect.return_value = None
            storage.close.return_value = None
            storage.search.return_value = [
                {
                    "entry_id": "e-sonda",
                    "absolute_path": ruta_sonda,
                    "relative_path": ruta_sonda,
                    "name": "sondapp.exe",
                    "extension": ".exe",
                    "entry_type": EntryType.FILE.value,
                    "size_bytes": 1024,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                    "volume": "C:",
                }
            ]
            preflight = ApplicationPreflight()
            clasificador = LaunchClassifier(preflight=preflight)
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=preflight,
                clasificador=clasificador,
                storage=storage,
                calibration=calib,
                machine_id="maquina-vincula-tupla",
                app_manager=manager,
            )
            candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo("sondapp")
            assert len(candidatos) == len(vinculados) == 1
            assert vinculados[0].candidato is candidatos[0]
            assert candidatos[0].fuente == FUENTE_INVENTARIO
            assert candidatos[0].preflight_decision is not None
            assert "valid" in candidatos[0].preflight_decision
            assert vinculados[0].en_catalogo_global is False
            assert vinculados[0].conocimiento is None
            assert vinculados[0].fuente_autoritaria is None
            # Se uso realmente el contrato del catalogo (consulta por nombre y
            # por stem del ejecutable).
            assert "sondapp.exe" in manager.llamadas
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)


class TestVinculacionCatalogoEntornoReal:
    """Unidad 3.8.5.1.4.9.5 con componentes reales: ApplicationManager real
    (catalogo data/memory/entities.json), almacenamiento SQLite temporal real,
    LaunchClassifier y ApplicationPreflight reales. Solo lectura: no lanza nada
    ni modifica entities.json."""

    def _almacenamiento_con_entrada(
        self, tmp_path, entry_id: str, ruta: str, nombre: str, machine_id: str
    ) -> SystemInventoryStorage:
        db_path = tmp_path / "test_inventory_vincula.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize()
        storage.record_machine(machine_id)
        storage.record_volume("vol-c:", machine_id, "C:", "local", "online")
        storage.begin_scan_run(
            "scan-vincula", machine_id, "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00",
        )
        storage.insert_file_entries(
            "scan-vincula",
            machine_id,
            "C:",
            [
                {
                    "entry_id": entry_id,
                    "absolute_path": ruta,
                    "relative_path": ruta,
                    "name": nombre,
                    "extension": ".exe",
                    "entry_type": EntryType.FILE.value,
                    "size_bytes": 1024,
                    "modified_at": "2024-01-01T10:00:00",
                    "created_at": "2024-01-01T09:00:00",
                    "attributes": [],
                    "excluded": False,
                    "source": "filesystem_scan",
                    "last_checked_at": "2024-01-03T00:00:00",
                    "volume": "C:",
                }
            ],
        )
        storage.end_scan_run("scan-vincula", "2024-01-03T01:00:00", SCAN_RESULT_OK, 1, 0, 0, 100.0)
        return storage

    def test_catalogo_real_reconoce_notepad_desde_inventario(self, tmp_path):
        """Candidato del inventario (notepad.exe) se vincula con la entidad
        global real del catalogo y su ApplicationKnowledge; entities.json no
        se modifica."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        storage = self._almacenamiento_con_entrada(
            tmp_path, "e-notepad-real", notepad, "notepad.exe", "maquina-vincula-real"
        )
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=calib,
            machine_id="maquina-vincula-real",
        )
        hash_antes = _hash_archivo(_ruta_entities_json_memoria())

        candidato = DiscoveredCandidate(
            candidate_id="inv-notepad",
            name="bloc de notas",
            absolute_path=notepad,
            destination=notepad,
            fuente=FUENTE_INVENTARIO,
            esta_en_inventario=True,
            disponible=True,
        )
        vinculados = discovery.vincular_con_catalogo([candidato])
        assert len(vinculados) == 1
        v = vinculados[0]
        assert v.en_catalogo_global is True
        assert v.conocimiento is not None
        assert v.conocimiento.name == "Bloc de notas"
        assert v.conocimiento.executable == "notepad.exe"
        assert v.fuente_autoritaria == FUENTE_CATALOGO

        hash_despues = _hash_archivo(_ruta_entities_json_memoria())
        assert hash_despues == hash_antes, (
            "vincular_con_catalogo no debe escribir data/memory/entities.json"
        )

    def test_catalogo_real_no_encuentra_desconocido(self, tmp_path):
        """Candidato del inventario sin entidad en el catalogo: en_catalogo_global
        False y conocimiento None, sin lanzar nada."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 64)
        try:
            storage = self._almacenamiento_con_entrada(
                tmp_path, "e-sonda-real", ruta_sonda, "sondapp95.exe", "maquina-vincula-real-b"
            )
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=ApplicationPreflight(),
                clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                storage=storage,
                calibration=calib,
                machine_id="maquina-vincula-real-b",
            )
            hash_antes = _hash_archivo(_ruta_entities_json_memoria())
            candidato = DiscoveredCandidate(
                candidate_id="inv-sonda",
                name="sondapp95.exe",
                absolute_path=ruta_sonda,
                destination=ruta_sonda,
                fuente=FUENTE_INVENTARIO,
                esta_en_inventario=True,
                disponible=True,
            )
            vinculados = discovery.vincular_con_catalogo([candidato])
            assert len(vinculados) == 1
            assert vinculados[0].en_catalogo_global is False
            assert vinculados[0].conocimiento is None
            assert vinculados[0].fuente_autoritaria is None
            hash_despues = _hash_archivo(_ruta_entities_json_memoria())
            assert hash_despues == hash_antes
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)

    def test_buscar_por_nombre_con_catalogo_flujo_real(self, tmp_path):
        """buscar_por_nombre_con_catalogo con almacenamiento real y catalogo real:
        nombre sin entidad en el catalogo devuelve candidato de inventario sin
        vinculo al catalogo; preflight real ejecutado sin lanzar."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 64)
        try:
            storage = self._almacenamiento_con_entrada(
                tmp_path, "e-flujo-real", ruta_sonda, "sondapp96.exe", "maquina-vincula-real-c"
            )
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=ApplicationPreflight(),
                clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                storage=storage,
                calibration=calib,
                machine_id="maquina-vincula-real-c",
            )
            candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo("sondapp96")
            assert len(candidatos) == len(vinculados) == 1
            assert candidatos[0].fuente == FUENTE_INVENTARIO
            assert candidatos[0].preflight_decision is not None
            assert "valid" in candidatos[0].preflight_decision
            assert vinculados[0].en_catalogo_global is False
            assert vinculados[0].conocimiento is None
            assert vinculados[0].fuente_autoritaria is None
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)


# ---------------------------------------------------------------------------
# Preflight completo de política (unidad 3.8.5.1.4.9.6)
# ---------------------------------------------------------------------------

class TestPreflightPoliticaCompleta:
    """
    3.8.5.1.4.9.6: pasar los candidatos por ApplicationPreflight y las
    políticas existentes; no llamar a CalibrationManager.launch_application
    ni depender de verificación proceso/ventana.

    Estrategia de mocks: solo se mockean las fuentes de datos
    (CalibrationManager / SystemInventoryStorage). La clasificación y el
    preflight son REALES (LaunchClassifier + ApplicationPreflight sobre
    archivos reales del equipo). No se lanza ninguna aplicación.
    """

    def test_ejecutar_preflight_uri_admitida_esta_autorizado(self):
        """URI de aplicación admitida (ms-settings:) pasa el preflight completo:
        allowed=True, sin blocked_by, sin lanzar nada."""
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[
                _app("Configuracion", "ms-settings:", FUENTE_START_MENU),
            ]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        c = next((x for x in resultado if x.name.casefold() == "configuracion"), None)
        assert c is not None
        assert c.preflight_policy is not None
        assert c.preflight_policy.get("allowed") is True
        assert c.preflight_policy.get("blocked_by") is None

    def test_ejecutar_preflight_bloquea_nombre_administrativo(self):
        """Nombre con parte bloqueada (ej. 'task scheduler', 'registry editor')
        produce allowed=False y blocked_by='blocked_name'."""
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[
                _app("Task Scheduler", r"C:\Windows\System32\taskschd.msc",
                     FUENTE_START_MENU),
                _app("Registry Editor", r"C:\Windows\regedit.exe",
                     FUENTE_START_MENU),
            ]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        bloqueados_por_nombre = [
            c for c in resultado
            if c.preflight_policy is not None
            and not c.preflight_policy.get("allowed")
            and c.preflight_policy.get("blocked_by") == "blocked_name"
        ]
        nombres_bloqueados = {c.name for c in bloqueados_por_nombre}
        assert "Task Scheduler" in nombres_bloqueados or "Registry Editor" in nombres_bloqueados, (
            f"Esperaba al menos uno bloqueado por nombre, obtenidos: {nombres_bloqueados}"
        )

    def test_ejecutar_preflight_bloquea_app_id_administrativo(self):
        """app_id con parte bloqueada produce allowed=False y blocked_by='blocked_app_id'.
        Usa un nombre NO bloqueado pero destino con 'services' en la ruta
        (coincide con blocked_app_id). Llama directamente a
        ejecutar_preflight_sobre_candidato."""
        descub, _, _ = _discovery_con_mocks()
        candidato_raw = {
            "candidate_id": "svc-test",
            "name": "Utilidad de Sistema",
            "absolute_path": r"C:\Windows\System32\services.msc",
            "destination": r"C:\Windows\System32\services.msc",
            "source": FUENTE_START_MENU,
            "app_id": "services",
        }
        clasificacion = descub.clasificador.classify_candidate(candidato_raw)
        policy = descub.ejecutar_preflight_sobre_candidato(candidato_raw, clasificacion)
        assert policy.get("allowed") is False
        assert policy.get("blocked_by") == "blocked_app_id"

    def test_filtrar_por_preflight_policy_retorna_solo_autorizados(self):
        """filtrar_por_preflight_policy excluye candidatos con allowed=False
        y conserva los que tienen allowed=True."""
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[
                _app("Configuracion", "ms-settings:", FUENTE_START_MENU),
                _app("Task Scheduler", r"C:\Windows\System32\taskschd.msc",
                     FUENTE_START_MENU),
            ]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        autorizados = descub.filtrar_por_preflight_policy(resultado)
        nombres_autorizados = {c.name for c in autorizados}
        assert "Configuracion" in nombres_autorizados
        assert "Task Scheduler" not in nombres_autorizados
        for c in autorizados:
            assert c.preflight_policy.get("allowed") is True

    def test_to_dict_incluye_preflight_policy(self):
        """DiscoveredCandidate.to_dict serializa preflight_policy cuando está
        presente y None cuando no lo está."""
        c_con = DiscoveredCandidate(
            candidate_id="c1", name="App", destination=r"C:\app.exe",
            fuente=FUENTE_INVENTARIO,
            preflight_policy={"allowed": True, "blocked_by": None},
        )
        c_sin = DiscoveredCandidate(
            candidate_id="c2", name="App2", destination=r"C:\app2.exe",
            fuente=FUENTE_INVENTARIO,
        )
        assert c_con.to_dict()["preflight_policy"] == {"allowed": True, "blocked_by": None}
        assert c_sin.to_dict()["preflight_policy"] is None

    def test_candidato_sin_destino_tiene_preflight_policy_no_autorizado(self):
        """Candidato sin destino de lanzamiento: preflight_policy con
        allowed=False y blocked_by indicando el motivo."""
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[
                _app("SinDestino", "", FUENTE_START_MENU),
            ]
        )
        resultado = descub.descubrir_todos(limite_por_fuente=10, incluir_inventario=False)
        sin_destino = [c for c in resultado if c.name.casefold() == "sindestino"]
        assert len(sin_destino) >= 1, "Esperaba el candidato SinDestino"
        for c in sin_destino:
            assert c.preflight_policy is not None
            assert c.preflight_policy.get("allowed") is False


class TestPreflightPoliticaEntornoReal:
    """
    3.8.5.1.4.9.6 en entorno real: componentes de producción sobre archivos
    reales del equipo, sin lanzar aplicaciones ni modificar entities.json.
    """

    def test_buscar_por_nombre_con_preflight_policy_real_notepad(self):
        """buscar_por_nombre sobre notepad.exe real: preflight_policy poblado.
        El preflight puede devolver allowed=False si resolve_executable no
        encuentra el ejecutable vía shell:AppsFolder (comportamiento correcto
        y estricto). Lo importante es que preflight_policy esté presente y no
        se haya lanzado nada ni modificado entities.json."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("Notepad", notepad, FUENTE_START_MENU)]
        )
        resultado = descub.buscar_por_nombre("notepad", incluir_inventario=False)
        assert len(resultado) >= 1
        c = next(
            (x for x in resultado
             if x.destination and os.path.normcase(x.destination) == os.path.normcase(notepad)),
            None,
        )
        assert c is not None, f"No se encontró candidato con destino {notepad}; candidatos: {[x.destination for x in resultado]}"
        assert c.preflight_policy is not None
        assert "allowed" in c.preflight_policy
        assert "blocked_by" in c.preflight_policy

    def test_buscar_por_nombre_con_preflight_policy_real_cmd(self):
        """cmd.exe real: preflight_policy poblado (allowed puede ser True o
        False según resolución vía shell:AppsFolder; comportamiento estricto
        del preflight)."""
        cmd = r"C:\Windows\System32\cmd.exe"
        if not os.path.exists(cmd):
            pytest.skip("cmd.exe no disponible en este equipo")
        descub, _, _ = _discovery_con_mocks(
            calib_apps=[_app("cmd", cmd, FUENTE_START_MENU)]
        )
        resultado = descub.buscar_por_nombre("cmd", incluir_inventario=False)
        c = next((x for x in resultado if x.name.casefold() == "cmd"), None)
        assert c is not None
        assert c.preflight_policy is not None
        assert "allowed" in c.preflight_policy


# ---------------------------------------------------------------------------
# Integracion catalogo global + descubrimiento: sin rutas paralelas
# Brain/Planner/Executor (unidad 3.8.5.1.4.9.8)
# ---------------------------------------------------------------------------

def _almacenamiento_temporal_con_entrada(
    tmp_path, entry_id: str, ruta: str, nombre: str, machine_id: str
) -> SystemInventoryStorage:
    """Crea almacenamiento SQLite temporal real con una entrada de archivo."""
    db_path = tmp_path / f"test_inventory_98_{entry_id}.sqlite3"
    storage = SystemInventoryStorage(db_path=db_path)
    storage.initialize()
    storage.record_machine(machine_id)
    storage.record_volume("vol-c:", machine_id, "C:", "local", "online")
    storage.begin_scan_run(
        f"scan-98-{entry_id}", machine_id, "C:", SCAN_MODE_FULL, "2024-01-03T00:00:00",
    )
    storage.insert_file_entries(
        f"scan-98-{entry_id}",
        machine_id,
        "C:",
        [{
            "entry_id": entry_id,
            "absolute_path": ruta,
            "relative_path": ruta,
            "name": nombre,
            "extension": ".exe",
            "entry_type": EntryType.FILE.value,
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
            "volume": "C:",
        }],
    )
    storage.end_scan_run(f"scan-98-{entry_id}", "2024-01-03T01:00:00", SCAN_RESULT_OK, 1, 0, 0, 100.0)
    return storage


class TestIntegracionCatalogoDescubierto:
    """
    Unidad 3.8.5.1.4.9.8: verifica la integracion entre aplicaciones ya
    registradas (catalogo global / ApplicationManager) y descubiertas
    (inventario / fuentes primarias), sin crear rutas paralelas
    Brain/Planner/Executor.

    Estrategia de mocks: solo se mockean las fuentes de datos
    (CalibrationManager / SystemInventoryStorage cuando se inyecta). La
    clasificacion, el preflight y el catalogo son REALES. No se lanza ninguna
    aplicacion y no se modifica data/memory/entities.json.
    """

    def test_app_registrada_vinculada_al_catalogo_global_con_preflight(self, tmp_path):
        """Nombre registrado en el catalogo global (bloc de notas / notepad)
        se resuelve via ApplicationManager y vincula su ApplicationKnowledge:
        en_catalogo_global=True, fuente autoritativa, preflight_policy
        poblado. No se lanza nada ni se modifica entities.json."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        storage = _almacenamiento_temporal_con_entrada(
            tmp_path, "e-notepad-98", notepad, "notepad.exe", "maquina-integra-98"
        )
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=calib,
            machine_id="maquina-integra-98",
        )
        hash_antes = _hash_archivo(_ruta_entities_json_memoria())

        candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo(
            "bloc de notas", incluir_inventario=True
        )
        assert len(candidatos) == len(vinculados) >= 1

        vinculado_notepad = next(
            (
                v
                for v in vinculados
                if v.conocimiento is not None
                and str(v.conocimiento.name).casefold() == "bloc de notas"
            ),
            None,
        )
        assert vinculado_notepad is not None, (
            "No se vinculo notepad al catalogo global; vinculados: "
            f"{[v.candidato.name for v in vinculados]}"
        )
        assert vinculado_notepad.en_catalogo_global is True
        assert vinculado_notepad.conocimiento is not None
        assert vinculado_notepad.conocimiento.executable == "notepad.exe"
        assert vinculado_notepad.fuente_autoritaria is not None
        assert vinculado_notepad.candidato.preflight_policy is not None
        assert "allowed" in vinculado_notepad.candidato.preflight_policy
        assert "blocked_by" in vinculado_notepad.candidato.preflight_policy

        hash_despues = _hash_archivo(_ruta_entities_json_memoria())
        assert hash_despues == hash_antes, (
            "la integracion catalogo+descubrimiento no debe modificar entities.json"
        )

    def test_app_descubierta_no_registrada_sin_vinculo_al_catalogo(self, tmp_path):
        """Nombre no registrado en el catalogo se descubre del inventario sin
        vinculo al catalogo global: en_catalogo_global=False,
        fuente_autoritaria=None, preflight_policy poblado, sin lanzar."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 64)
        try:
            storage = _almacenamiento_temporal_con_entrada(
                tmp_path, "e-sonda-98", ruta_sonda, "sondapp98.exe",
                "maquina-integra-98-b",
            )
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=ApplicationPreflight(),
                clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                storage=storage,
                calibration=calib,
                machine_id="maquina-integra-98-b",
            )
            candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo(
                "sondapp98", incluir_inventario=True
            )
            assert len(candidatos) == len(vinculados) == 1
            assert candidatos[0].fuente == FUENTE_INVENTARIO
            assert vinculados[0].en_catalogo_global is False
            assert vinculados[0].conocimiento is None
            assert vinculados[0].fuente_autoritaria is None
            assert vinculados[0].candidato.preflight_policy is not None
            assert "allowed" in vinculados[0].candidato.preflight_policy
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)

    def test_nombre_registrado_no_es_ambiguo_tiene_fuente_autoritativa(self, tmp_path):
        """Nombre registrado en el catalogo (bloc de notas): la resolucion no
        es ambigua ni se elige silenciosamente, y la fuente_autoritaria es
        autoritativa (el catalogo decide). Sin lanzar nada."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        storage = _almacenamiento_temporal_con_entrada(
            tmp_path, "e-nota-98", notepad, "notepad.exe", "maquina-integra-98-d"
        )
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=calib,
            machine_id="maquina-integra-98-d",
        )
        resultado = discovery.buscar_por_nombre_con_desambiguacion(
            "bloc de notas", incluir_inventario=True
        )
        assert resultado.ambiguo is False
        assert resultado.requiere_desambiguacion is False
        assert resultado.motivo_ambiguedad is None
        assert resultado.fuente_autoritaria is not None
        assert len(resultado.candidatos) >= 1
        # El candidato vinculado conserva el conocimiento del catalogo global.
        vinculados = discovery.vincular_con_catalogo(resultado.candidatos)
        assert len(vinculados) == len(resultado.candidatos)
        vinculado_notepad = next(
            (
                v
                for v in vinculados
                if v.conocimiento is not None
                and str(v.conocimiento.name).casefold() == "bloc de notas"
            ),
            None,
        )
        assert vinculado_notepad is not None, (
            "bloc de notas no vinculado al catalogo; vinculados: "
            f"{[(v.en_catalogo_global, v.fuente_autoritaria) for v in vinculados]}"
        )
        assert vinculado_notepad.en_catalogo_global is True
        assert vinculado_notepad.conocimiento is not None
        assert vinculado_notepad.conocimiento.executable == "notepad.exe"


class TestSinRutasParalelasPlannerExecutor:
    """
    Unidad 3.8.5.1.4.9.8: verifica que el flujo de resolucion de aplicaciones
    (registradas + descubiertas) no crea rutas paralelas Brain/Planner/Executor.
    Solo usa ApplicationDiscovery + ApplicationManager + ApplicationPreflight.
    """

    def test_modulo_application_discovery_sin_imports_brain_planner_executor(self):
        """application_discovery.py no importa ni referencia Brain, Planner ni
        Executor; el flujo de resolucion reutiliza contratos verificados de
        aplicaciones y preflight."""
        ruta_modulo = (
            Path(__file__).resolve().parents[2]
            / "src" / "hands" / "application_discovery.py"
        )
        fuente = ruta_modulo.read_text(encoding="utf-8")
        prohibidos = [
            "src.brain",
            "src.hands.planner",
            "src.hands.executor",
            "src.tools.executor",
            "from src.brain",
            "from src.hands.planner",
            "from src.hands.executor",
            "from src.tools.executor",
        ]
        for prohibido in prohibidos:
            assert prohibido not in fuente, (
                f"Ruta paralela detectada: application_discovery referencia {prohibido}"
            )

    def test_flujo_resolucion_solo_usa_contratos_verificados(self):
        """buscar_por_nombre_con_catalogo solo consulta get_application_manager(),
        ApplicationManager.get_application (lectura) y ApplicationPreflight.check;
        nunca registra, nunca lanza, nunca delega en planificador ni ejecutor."""
        manager = _AppManagerFake(
            {"bloc de notas": _conocimiento_prueba("Bloc de notas", "notepad.exe")}
        )
        discovery = _discovery_con_manager_y_storage(manager)
        candidato = DiscoveredCandidate(
            candidate_id="inv-1",
            name="bloc de notas",
            absolute_path=r"C:\Windows\System32\notepad.exe",
            destination=r"C:\Windows\System32\notepad.exe",
            fuente=FUENTE_INVENTARIO,
            esta_en_inventario=True,
            disponible=True,
        )
        vinculados = discovery.vincular_con_catalogo([candidato])
        assert len(vinculados) == 1
        v = vinculados[0]
        assert v.en_catalogo_global is True
        assert v.conocimiento is not None
        assert v.conocimiento.executable == "notepad.exe"
        # Solo consulta (get_application registra la llamada), sin registro ni
        # auto-registro: el puente de auto-registro corresponde a 3.8.5.1.4.11.
        assert manager.llamadas == ["bloc de notas"]
        assert v.fuente_autoritaria == FUENTE_CATALOGO


# ---------------------------------------------------------------------------
# Unidad 3.8.5.1.4.9.9: consulta y resolucion reales en el equipo (sin
# lanzamiento, sin modificacion de entities.json)
# ---------------------------------------------------------------------------

class TestResolucionPreflightEntornoReal:
    """
    Unidad 3.8.5.1.4.9.9: ejecuta en el equipo real la ruta de consulta y
    resolucion de aplicaciones con (1) una aplicacion inocua conocida
    (bloc de notas / notepad, registrada en el catalogo global
    data/memory/entities.json) y (2) otra aplicacion localizada por el
    inventario y no registrada previamente, usando almacenamiento
    (SystemInventoryStorage sobre SQLite real y temporal), consulta
    (ApplicationDiscovery.buscar_por_nombre_con_catalogo) y
    ApplicationPreflight reales, sin lanzar ninguna aplicacion ni modificar
    entities.json. La apertura real de aplicaciones queda para 3.8.5.4-3.8.5.6.

    Ningun mock decide el resultado de clasificacion, preflight ni resolucion:
    se usan LaunchClassifier, ApplicationPreflight y ApplicationManager
    reales sobre archivos reales del equipo. El almacenamiento de inventario
    es una base SQLite real y temporal (nunca la base de produccion).
    """

    def _marca_entorno_real(self) -> dict:
        """Captura evidencia de entorno real (equipo, SO y machine_id)."""
        import sys

        return {
            "machine_id": generate_machine_id(),
            "sistema": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "equipo": platform.node(),
            "python": sys.version,
        }

    def _almacenamiento_inventario_real(
        self, tmp_path, machine_id: str, entry_id: str, ruta: str, nombre: str,
        volume: str = "C:",
    ) -> SystemInventoryStorage:
        """Crea almacenamiento SQLite real y temporal con una entrada de archivo
        para el equipo actual, respetando el aislamiento por machine_id."""
        ahora = datetime.now(timezone.utc).isoformat()
        storage = SystemInventoryStorage(db_path=tmp_path / f"test_inventory_99_{entry_id}.sqlite3")
        storage.initialize()
        storage.record_machine(machine_id)
        storage.record_volume(f"vol-{volume}", machine_id, volume, "local", "online")
        storage.begin_scan_run(
            f"scan-99-{entry_id}", machine_id, volume, SCAN_MODE_FULL, ahora,
        )
        storage.insert_file_entries(
            f"scan-99-{entry_id}",
            machine_id,
            volume,
            [{
                "entry_id": entry_id,
                "absolute_path": ruta,
                "relative_path": ruta,
                "name": nombre,
                "extension": ".exe",
                "entry_type": EntryType.FILE.value,
                "size_bytes": 1024,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "accessed_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": ahora,
                "volume": volume,
            }],
        )
        storage.end_scan_run(
            f"scan-99-{entry_id}", ahora, SCAN_RESULT_OK, 1, 0, 0, None,
        )
        return storage

    def _procesos_con_nombre(self, nombre_ejecutable: str) -> set[str]:
        """Instantanea real de procesos con ese nombre (tasklist del SO)."""
        nombre_ejecutable = str(nombre_ejecutable or "").lower()
        if not nombre_ejecutable:
            return set()
        try:
            resultado = subprocess.run(
                [
                    "tasklist", "/FO", "CSV", "/NH",
                    "/FI", f"IMAGENAME eq {nombre_ejecutable}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return set()
        procesos: set[str] = set()
        for linea in resultado.stdout.splitlines():
            if not linea.strip():
                continue
            partes = [p.strip('"') for p in linea.split(",")]
            if partes and partes[0].lower() == nombre_ejecutable:
                procesos.add(partes[0])
        return procesos

    # ------------------------------------------------------------------ #
    # Caso 1: aplicacion inocua conocida (catalogo global)
    # ------------------------------------------------------------------ #

    def test_aplicacion_conocida_resolucion_preflight_entorno_real(self, tmp_path):
        """bloc de notas (registrado en el catalogo global) se resuelve,
        vincula su ApplicationKnowledge y pasa preflight real, sin lanzar."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")
        entorno = self._marca_entorno_real()
        assert entorno["machine_id"], "machine_id no debe estar vacia en equipo real"
        assert entorno["sistema"], "el SO real debe identificarse"
        machine_id = entorno["machine_id"]

        storage = self._almacenamiento_inventario_real(
            tmp_path, machine_id, "e-notepad-99", notepad, "notepad.exe",
        )
        calib = MagicMock()
        calib.discover_applications.return_value = []
        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=calib,
            machine_id=machine_id,
        )

        ruta_entities = _ruta_entities_json_memoria()
        hash_antes = _hash_archivo(ruta_entities)

        procesos_antes = self._procesos_con_nombre("notepad.exe")

        candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo(
            "bloc de notas", incluir_inventario=True,
        )

        procesos_despues = self._procesos_con_nombre("notepad.exe")
        assert procesos_despues == procesos_antes, (
            "No se debe lanzar ninguna aplicacion durante la consulta/resolucion"
        )

        assert len(candidatos) == len(vinculados) >= 1
        vinculado_notepad = next(
            (
                v
                for v in vinculados
                if v.conocimiento is not None
                and str(v.conocimiento.name).casefold() == "bloc de notas"
            ),
            None,
        )
        assert vinculado_notepad is not None, (
            "No se vinculo notepad al catalogo global; vinculados: "
            f"{[v.candidato.name for v in vinculados]}"
        )
        assert vinculado_notepad.en_catalogo_global is True
        assert vinculado_notepad.conocimiento is not None
        assert vinculado_notepad.conocimiento.executable == "notepad.exe"
        assert vinculado_notepad.fuente_autoritaria is not None
        assert vinculado_notepad.candidato.preflight_policy is not None
        policy = vinculado_notepad.candidato.preflight_policy
        assert "allowed" in policy
        assert "blocked_by" in policy
        # La decision de destino de lanzamiento debe estar poblada para que el
        # flujo decida sin lanzar nada.
        assert vinculado_notepad.candidato.preflight_decision is not None
        assert "valid" in vinculado_notepad.candidato.preflight_decision

        hash_despues = _hash_archivo(ruta_entities)
        assert hash_despues == hash_antes, (
            "la consulta/resolucion con preflight real no debe modificar entities.json"
        )

    # ------------------------------------------------------------------ #
    # Caso 2: aplicacion localizada por el inventario, no registrada
    # ------------------------------------------------------------------ #

    def test_aplicacion_inventario_no_registrada_resolucion_preflight_entorno_real(
        self, tmp_path
    ):
        """Una aplicacion localizada solo por el inventario (no registrada en
        el catalogo global) se resuelve con fuente FUENTE_INVENTARIO, sin
        vinculo al catalogo, con preflight real poblado y sin lanzamiento."""
        entorno = self._marca_entorno_real()
        machine_id = entorno["machine_id"]

        # Ejecutable inocuo real en disco, no registrado en el catalogo.
        with tempfile.NamedTemporaryFile(
            suffix=".exe", delete=False, dir=str(tmp_path)
        ) as f:
            ruta_sonda = f.name
            f.write(b"MZ" + b"\x00" * 64)
        try:
            nombre_sonda = "AppInventarioPrueba99.exe"
            storage = self._almacenamiento_inventario_real(
                tmp_path, machine_id, "e-sonda-99", ruta_sonda, nombre_sonda,
            )
            calib = MagicMock()
            calib.discover_applications.return_value = []
            discovery = ApplicationDiscovery(
                preflight=ApplicationPreflight(),
                clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
                storage=storage,
                calibration=calib,
                machine_id=machine_id,
            )
            ruta_entities = _ruta_entities_json_memoria()
            hash_antes = _hash_archivo(ruta_entities)

            procesos_antes = self._procesos_con_nombre(os.path.basename(ruta_sonda))

            candidatos, vinculados = discovery.buscar_por_nombre_con_catalogo(
                "AppInventarioPrueba99", incluir_inventario=True,
            )

            procesos_despues = self._procesos_con_nombre(os.path.basename(ruta_sonda))
            assert procesos_despues == procesos_antes, (
                "No se debe lanzar ninguna aplicacion durante la consulta/resolucion"
            )

            assert len(candidatos) == len(vinculados) == 1
            c = candidatos[0]
            assert c.fuente == FUENTE_INVENTARIO
            assert c.esta_en_inventario is True
            assert c.preflight_decision is not None
            assert "valid" in c.preflight_decision
            v = vinculados[0]
            assert v.en_catalogo_global is False
            assert v.conocimiento is None
            assert v.fuente_autoritaria is None
            assert v.candidato.preflight_policy is not None
            policy = v.candidato.preflight_policy
            assert "allowed" in policy
            assert "blocked_by" in policy

            hash_despues = _hash_archivo(ruta_entities)
            assert hash_despues == hash_antes, (
                "la consulta de inventario no registrada no debe modificar entities.json"
            )
        finally:
            if os.path.exists(ruta_sonda):
                os.unlink(ruta_sonda)


# ---------------------------------------------------------------------------
# Unidad 3.8.5.1.4.9.10: comprobacion en entorno real de los tres escenarios
# de bloqueo / revalidacion / aclaracion sin lanzar aplicaciones:
# (1) ruta obsoleta, (2) volumen desmontado y (3) coincidencia ambigua.
# ---------------------------------------------------------------------------

class TestEscenariosBloqueoEntornoReal:
    """
    Unidad 3.8.5.1.4.9.10: comprueba en el flujo real (almacenamiento SQLite
    real y temporal, ApplicationPreflight y LaunchClassifier reales sobre
    archivos reales del disco, machine_id real del equipo) que:

    - una ruta obsoleta se bloquea y se revalida sin intentar el lanzador,
    - un volumen desmontado no se consulta ni se considera destino accesible,
    - una coincidencia ambigua se devuelve para aclaracion sin elegir
      silenciosamente.

    Ninguna prueba lanza aplicaciones ni modifica `entities.json`.
    """

    def _una_entrada(self, entry_id: str, ruta: str, nombre: str,
                     extension: str = ".exe", volume: str = "C:") -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": ruta,
            "relative_path": ruta,
            "name": nombre,
            "extension": extension,
            "entry_type": EntryType.FILE.value,
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
            "volume": volume,
        }

    def _crear_storage_con_entrada(self, tmp_path, machine_id: str,
                                   entry_id: str, ruta: str, nombre: str,
                                   volume: str = "C:"):
        """Almacenamiento SQLite real y temporal con una entrada de archivo
        para el equipo actual, respetando el aislamiento por machine_id."""
        ahora = datetime.now(timezone.utc).isoformat()
        storage = SystemInventoryStorage(
            db_path=tmp_path / f"test_inventory_910_{entry_id}.sqlite3")
        storage.initialize()
        storage.record_machine(machine_id)
        storage.record_volume(f"vol-{volume}", machine_id, volume, "local", "online")
        storage.begin_scan_run(
            f"scan-910-{entry_id}", machine_id, volume, SCAN_MODE_FULL, ahora,
        )
        storage.insert_file_entries(
            f"scan-910-{entry_id}", machine_id, volume,
            [self._una_entrada(entry_id, ruta, nombre, volume=volume)],
        )
        storage.end_scan_run(
            f"scan-910-{entry_id}", ahora, SCAN_RESULT_OK, 1, 0, 0, None,
        )
        return storage

    def _descubrimiento_real(self, storage, machine_id: str):
        """ApplicationDiscovery con preflight, clasificador y almacenamiento
        reales; fuentes de descubrimiento mockeadas (no deciden el resultado)."""
        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        calib.discover_applications.return_value = []
        return ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=calib,
            machine_id=machine_id,
        )

    def _marca_entorno_real(self) -> dict:
        """Captura evidencia de entorno real (equipo, SO y machine_id)."""
        import sys
        return {
            "machine_id": generate_machine_id(),
            "sistema": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "equipo": platform.node(),
            "python": sys.version,
        }

    def _procesos_con_nombre(self, nombre_ejecutable: str) -> set[str]:
        """Instantanea real de procesos con ese nombre (tasklist del SO)."""
        nombre_ejecutable = str(nombre_ejecutable or "").lower()
        if not nombre_ejecutable:
            return set()
        try:
            resultado = subprocess.run(
                [
                    "tasklist", "/FO", "CSV", "/NH",
                    "/FI", f"IMAGENAME eq {nombre_ejecutable}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return set()
        procesos: set[str] = set()
        for linea in resultado.stdout.splitlines():
            if not linea.strip():
                continue
            partes = [p.strip('"') for p in linea.split(",")]
            if partes and partes[0].lower() == nombre_ejecutable:
                procesos.add(partes[0])
        return procesos

    # ------------------------------------------------------------------
    # Escenario 1: ruta obsoleta
    # ------------------------------------------------------------------

    def test_ruta_obsoleta_bloqueada_sin_lanzar(self, tmp_path):
        """Una ruta cuyo archivo ya no existe se bloquea: no se resuelve
        como candidata, se registra como inaccesible, no se le invoca
        preflight ni lanzador, y la revalidacion real contra el SO devuelve
        valido=False / existe=False."""
        entorno = self._marca_entorno_real()
        machine_id = entorno["machine_id"]
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            ruta_obsoleta = f.name
        os.unlink(ruta_obsoleta)
        try:
            storage = self._crear_storage_con_entrada(
                tmp_path, machine_id, "e-obsoleto-910", ruta_obsoleta,
                "obsoleto910.exe",
            )
            discovery = self._descubrimiento_real(storage, machine_id)
            hash_antes = _hash_archivo(_ruta_entities_json_memoria())
            procesos_antes = self._procesos_con_nombre("obsoleto910.exe")

            resultado = discovery.buscar_por_nombre(
                "obsoleto910", incluir_inventario=True,
            )
            assert resultado == [], (
                "la ruta obsoleta no debe resolverse como candidata"
            )

            inaccesibles = discovery.candidatos_inaccesibles_ultima_resolucion
            assert len(inaccesibles) == 1
            assert inaccesibles[0].disponible is False
            assert inaccesibles[0].preflight_decision is None, (
                "la ruta obsoleta no debe pasar por preflight"
            )
            assert any("inaccesible" in a
                       for a in inaccesibles[0].advertencias)
            assert any("ruta_no_accesible_en_disco" in e
                       for e in inaccesibles[0].evidencia)

            # Revalidacion real contra el SO: la ruta obsoleta no existe.
            reval = storage.revalidar_destino_aplicacion(
                machine_id, "C:", ruta_obsoleta,
            )
            assert reval["valido"] is False
            assert reval["existe"] is False
            assert reval["es_archivo"] is False
            assert reval["razon"] is not None

            procesos_despues = self._procesos_con_nombre("obsoleto910.exe")
            assert procesos_despues == procesos_antes, (
                "no se lanza ninguna aplicacion durante la consulta/resolucion"
            )
            hash_despues = _hash_archivo(_ruta_entities_json_memoria())
            assert hash_despues == hash_antes, (
                "entities.json no debe modificarse"
            )
        finally:
            if os.path.exists(ruta_obsoleta):
                os.unlink(ruta_obsoleta)

    # ------------------------------------------------------------------
    # Escenario 2: volumen desmontado
    # ------------------------------------------------------------------

    def test_volumen_desmontado_bloqueado_y_revalidado(self, tmp_path):
        """Una entrada de inventario en un volumen no montado (D:) no se
        devuelve en la consulta filtrada por volumenes montados y su
        revalidacion real contra el SO devuelve valido=False / existe=False."""
        entorno = self._marca_entorno_real()
        machine_id = entorno["machine_id"]
        volumen_desmontado = "D:"
        if os.path.exists(volumen_desmontado):
            pytest.skip(
                f"el volumen {volumen_desmontado} esta montado; "
                "no se puede probar volumen desmontado"
            )

        ruta_en_volumen_desmontado = r"D:\jarvis_910_volumen\app_910.exe"
        storage = self._crear_storage_con_entrada(
            tmp_path, machine_id, "e-volumen-910", ruta_en_volumen_desmontado,
            "appvolumen910.exe", volume=volumen_desmontado,
        )
        # El constructor de ApplicationDiscovery inicializa ApplicationManager
        # (carga y normalizacion de entities.json), por lo que el hash de
        # referencia se toma DESPUES de crearlo, igual que en los tests .9.9.
        discovery = self._descubrimiento_real(storage, machine_id)
        hash_antes = _hash_archivo(_ruta_entities_json_memoria())
        procesos_antes = self._procesos_con_nombre("app_910.exe")

        # Consulta con filtro de volumenes montados: la entrada del volumen
        # desmontado no debe aparecer.
        entradas = storage.search(
            machine_id=machine_id,
            extension=".exe",
            tipo=EntryType.FILE.value,
            disponible=True,
            solo_volumes_montados=True,
        )
        rutas_devueltas = {str(e.get("absolute_path", "")) for e in entradas}
        assert ruta_en_volumen_desmontado not in rutas_devueltas, (
            "el volumen desmontado no debe aportar rutas en la consulta filtrada"
        )

        # Revalidacion real contra el SO: ruta en volumen desmontado no existe.
        reval = storage.revalidar_destino_aplicacion(
            machine_id, volumen_desmontado, ruta_en_volumen_desmontado,
        )
        assert reval["valido"] is False
        assert reval["existe"] is False
        assert reval["es_archivo"] is False
        assert reval["razon"] is not None

        # Tampoco debe resolverse como candidato de descubrimiento.
        resultado = discovery.buscar_por_nombre(
            "appvolumen910", incluir_inventario=True,
        )
        assert resultado == [], (
            "el volumen desmontado no debe producir candidato resoluble"
        )

        procesos_despues = self._procesos_con_nombre("app_910.exe")
        assert procesos_despues == procesos_antes, (
            "no se lanza ninguna aplicacion durante la consulta/resolucion"
        )
        hash_despues = _hash_archivo(_ruta_entities_json_memoria())
        assert hash_despues == hash_antes, (
            "entities.json no debe modificarse"
        )

    # ------------------------------------------------------------------
    # Escenario 3: coincidencia ambigua
    # ------------------------------------------------------------------

    def test_coincidencia_ambigua_devuelta_para_aclaracion(self, tmp_path):
        """Dos entradas de inventario con nombres plausibles para la misma
        consulta y destinos distintos se devuelven como alternativas ambiguas:
        ambiguo=True, requiere_desambiguacion=True, sin elegir silenciosamente
        y sin lanzar nada."""
        entorno = self._marca_entorno_real()
        machine_id = entorno["machine_id"]
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        rutas = []
        nombres = []
        for i in (1, 2):
            with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
                f.write(b"MZ" + b"\x00" * 64)
                rutas.append(f.name)
                nombres.append(f"ambigua910{i}.exe")
        try:
            storage = SystemInventoryStorage(
                db_path=tmp_path / "test_inventory_910_ambigua.sqlite3")
            storage.initialize()
            storage.record_machine(machine_id)
            storage.record_volume("vol-c:", machine_id, "C:", "local", "online")
            ahora = datetime.now(timezone.utc).isoformat()
            storage.begin_scan_run(
                "scan-910-ambigua", machine_id, "C:", SCAN_MODE_FULL, ahora,
            )
            storage.insert_file_entries(
                "scan-910-ambigua", machine_id, "C:",
                [self._una_entrada(
                    f"e-ambigua-910-{i}", rutas[i - 1], nombres[i - 1],
                    volume="C:") for i in (1, 2)],
            )
            storage.end_scan_run(
                "scan-910-ambigua", ahora, SCAN_RESULT_OK, 2, 0, 0, None,
            )

            discovery = self._descubrimiento_real(storage, machine_id)
            hash_antes = _hash_archivo(_ruta_entities_json_memoria())
            procesos_antes = self._procesos_con_nombre("ambigua9101.exe")

            resultado = discovery.buscar_por_nombre_con_desambiguacion(
                "ambigua910",
            )

            procesos_despues = self._procesos_con_nombre("ambigua9101.exe")
            assert procesos_despues == procesos_antes, (
                "no se lanza ninguna aplicacion durante la consulta/resolucion"
            )
            hash_despues = _hash_archivo(_ruta_entities_json_memoria())
            assert hash_despues == hash_antes, (
                "entities.json no debe modificarse"
            )

            assert resultado.ambiguo is True
            assert resultado.requiere_desambiguacion is True
            assert resultado.motivo_ambiguedad is not None
            assert "ambigua" in (resultado.motivo_ambiguedad or "").lower()
            assert len(resultado.candidatos) >= 2
            assert len(resultado.alternativas) >= 2
            assert resultado.fuente_autoritaria is None
            nombres_devueltos = {c.name for c in resultado.alternativas}
            assert nombres[0] in nombres_devueltos
            assert nombres[1] in nombres_devueltos
            for c in resultado.alternativas:
                assert c.fuente == FUENTE_INVENTARIO
                assert c.esta_en_inventario is True
                assert c.preflight_decision is not None
                assert "valid" in c.preflight_decision
        finally:
            for ruta in rutas:
                if os.path.exists(ruta):
                    os.unlink(ruta)


# ---------------------------------------------------------------------------
# Identidad global estable (3.8.5.1.4.11.2)
# ---------------------------------------------------------------------------

class TestIdentidadGlobalEstable:
    """Pruebas de `calcular_identidad_estable`: identidad estable por
    evidencia (paquete/AUMID, fabricante+producto, nombre comercial) sin
    basarse en la ruta absoluta, y conservacion de candidatos separados
    cuando la evidencia es insuficiente."""

    def _candidato(
        self,
        candidate_id: str,
        name: str,
        ruta: str = r"C:\falsa\ruta\app.exe",
        nombre_comercial: Optional[str] = None,
        producto: Optional[str] = None,
        version: Optional[str] = None,
        confianza: str = "media",
        fuente: str = FUENTE_INVENTARIO,
        evidencia: Optional[list] = None,
    ) -> DiscoveredCandidate:
        return DiscoveredCandidate(
            candidate_id=candidate_id,
            name=name,
            absolute_path=ruta,
            destination=ruta,
            nombre_comercial=nombre_comercial,
            aliases=[],
            producto=producto,
            version=version,
            confianza=confianza,
            fuente=fuente,
            evidencia=list(evidencia or []),
            ultima_comprobacion="2024-01-01T00:00:00+00:00",
        )

    def test_3_8_5_1_4_11_2_identidad_desde_paquete_id(self):
        """Identificador de paquete/AUMID da entidad estable independiente de la ruta."""
        c1 = self._candidato("pkg-1", "MiApp", ruta=r"C:\Uno\app.exe",
                             evidencia=["paquete_id:MiApp.Package.1.0"])
        c2 = self._candidato("pkg-1", "MiApp", ruta=r"D:\Otro\app.exe",
                             evidencia=["paquete_id:MiApp.Package.1.0"])
        id1 = calcular_identidad_estable(c1)
        id2 = calcular_identidad_estable(c2)
        assert id1.entity_id == id2.entity_id == "paquete:MiApp.Package.1.0"
        assert id1.tipo_evidencia == "paquete"
        assert id1.fusionar_por_nombre_desaconsejado is False
        assert id1.alternativas == []
        assert id1.nombre_canonico == "miapp"

    def test_3_8_5_1_4_11_2_identidad_desde_fabricante_producto_independiente_de_ruta(self):
        """Fabricante + producto dan entidad estable aunque la ruta cambie."""
        c1 = self._candidato("f1", "Notepad", ruta=r"C:\Windows\System32\notepad.exe",
                             nombre_comercial="Notepad", producto="Microsoft Corporation", version="10.0")
        c2 = self._candidato("f2", "Notepad", ruta=r"D:\Copia\notepad.exe",
                             nombre_comercial="Notepad", producto="Microsoft Corporation", version="10.0")
        id1 = calcular_identidad_estable(c1)
        id2 = calcular_identidad_estable(c2)
        assert id1.entity_id == id2.entity_id == "fabprod:microsoft corporation:microsoft corporation"
        assert id1.tipo_evidencia == "fabricante_producto"
        assert id1.fusionar_por_nombre_desaconsejado is False
        assert id1.alternativas == []

    def test_3_8_5_1_4_11_2_nombre_comercial_solo_no_fusiona_por_nombre(self):
        """Solo nombre comercial: entidad estable pero no se fusiona por nombre;
        se conserva la alternativa separada."""
        c1 = self._candidato("n1", "App", ruta=r"C:\Uno\app.exe", nombre_comercial="Mi App")
        c2 = self._candidato("n2", "App", ruta=r"D:\Dos\app.exe", nombre_comercial="Mi App")
        id1 = calcular_identidad_estable(c1)
        id2 = calcular_identidad_estable(c2)
        assert id1.entity_id == id2.entity_id == "nombre:mi app"
        assert id1.tipo_evidencia == "nombre_comercial"
        assert id1.fusionar_por_nombre_desaconsejado is True
        assert id1.alternativas == [c1.to_dict()]
        assert id2.alternativas == [c2.to_dict()]

    def test_3_8_5_1_4_11_2_evidencia_insuficiente_mantiene_candidato_separado(self):
        """Sin evidencia estable: tipo insuficiente, fusionar por nombre
        desaconsejado y candidato conservado como alternativa."""
        c = self._candidato("x1", "", ruta=r"C:\Nada\app.exe")
        identidad = calcular_identidad_estable(c)
        assert identidad.tipo_evidencia == "insuficiente"
        assert identidad.fusionar_por_nombre_desaconsejado is True
        assert identidad.alternativas == [c.to_dict()]
        assert identidad.entity_id.startswith("candidato:")
        assert identidad.nombre_canonico == ""

    def test_3_8_5_1_4_11_2_ruta_absoluta_no_es_base_de_identidad(self):
        """Misma evidencia estable, rutas absolutas distintas: mismo entity_id;
        la ruta absoluta no forma parte de la identidad."""
        c1 = self._candidato("r1", "App", ruta=r"C:\Uno\app.exe",
                             nombre_comercial="App", producto="Fab", version="1")
        c2 = self._candidato("r2", "App", ruta=r"D:\Otro\app.exe",
                             nombre_comercial="App", producto="Fab", version="1")
        id1 = calcular_identidad_estable(c1)
        id2 = calcular_identidad_estable(c2)
        assert id1.entity_id == id2.entity_id
        assert "C:\\Uno" not in id1.entity_id
        assert "D:\\Otro" not in id2.entity_id

    def test_3_8_5_1_4_11_2_precedencia_paquete_sobre_fabricante_producto(self):
        """Cuando hay paquete y fabricante+producto, gana el identificador de paquete."""
        c = self._candidato("p1", "App", ruta=r"C:\app.exe",
                            nombre_comercial="App", producto="Fab",
                            evidencia=["paquete_id:MiApp.Pkg"])
        identidad = calcular_identidad_estable(c)
        assert identidad.entity_id == "paquete:MiApp.Pkg"
        assert identidad.tipo_evidencia == "paquete"

    def test_3_8_5_1_4_11_2_evidencia_base_contiene_metadatos_verificables(self):
        """La evidencia base registra los metadatos verificables usados."""
        c = self._candidato("m1", "App", ruta=r"C:\app.exe",
                            nombre_comercial="Mi App", producto="Fab", version="2.0")
        identidad = calcular_identidad_estable(c)
        assert identidad.evidencia_base["nombre_comercial"] == "Mi App"
        assert identidad.evidencia_base["fabricante"] == "Fab"
        assert identidad.evidencia_base["version"] == "2.0"
        assert "fuentes" in identidad.evidencia_base

    def test_3_8_5_1_4_11_2_mismo_candidato_devuelve_misma_identidad(self):
        """La identidad es determinista para el mismo candidato."""
        c = self._candidato("d1", "App", ruta=r"C:\app.exe", nombre_comercial="App")
        assert (
            calcular_identidad_estable(c).entity_id
            == calcular_identidad_estable(c).entity_id
        )

    def test_3_8_5_1_4_11_2_entity_id_aptos_para_modelo_entity(self):
        """El entity_id resultante es apto como id de `Entity`: str estable,
        normalizado y sin rutas absolutas."""
        from src.memory.storage import Entity

        c = self._candidato("e1", "App", ruta=r"C:\app.exe",
                            nombre_comercial="Mi App", producto="Fab")
        identidad = calcular_identidad_estable(c)
        ent = Entity(
            id=identidad.entity_id,
            type="application",
            name=c.nombre_comercial or c.name,
            properties={
                "fabricante": identidad.evidencia_base.get("fabricante"),
                "producto": identidad.evidencia_base.get("producto"),
                "version": identidad.evidencia_base.get("version"),
                "tipo_evidencia": identidad.tipo_evidencia,
                "fuentes": identidad.evidencia_base.get("fuentes"),
            },
            aliases=list(c.aliases),
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
        )
        assert ent.id == identidad.entity_id
        assert ent.type == "application"
        assert "C:\\app.exe" not in ent.id
        assert ent.to_dict()["id"] == identidad.entity_id


# ---------------------------------------------------------------------------
# Registro mínimo de aplicación (unidad 3.8.5.1.4.11.3)
# ---------------------------------------------------------------------------


class TestRegistroMinimoAplicacion:
    """
    Pruebas del registro mínimo de aplicación (3.8.5.1.4.11.3) del catálogo
    global `data/memory/entities.json`.

    Cada entidad creada o actualizada incluye como mínimo: identificador
    estable, nombre, aliases observados y seguros, categoría/rol clasificado,
    ruta absoluta observada cuando existe, tipo de lanzamiento nativo y
    estado `available` con fecha, fuente de observación y evidencia. Nunca se
    inventan capacidades.
    """

    AHORA = "2026-11-12T00:00:00+00:00"
    RUTA_NOTEPAD = r"C:\Windows\System32\notepad.exe"

    def _candidato_notepad_real(self) -> DiscoveredCandidate:
        """Candidato real sobre notepad.exe del equipo (no se lanza)."""
        return DiscoveredCandidate(
            candidate_id="cand-notepad-real",
            name="Notepad",
            absolute_path=self.RUTA_NOTEPAD,
            destination=self.RUTA_NOTEPAD,
            nombre_comercial="Notepad",
            aliases=["notepad", "bloc de notas"],
            launch_type=LaunchType.EJECUTABLE,
            launch_subtype=LaunchSubtype.GUI_APLICACION,
            es_lanzable=True,
            evidencia=["archivo_existe:" + self.RUTA_NOTEPAD],
            confianza=CONFIANZA_ALTA,
            fuente=FUENTE_START_MENU,
            ultima_comprobacion=self.AHORA,
        )

    def _identidad_notepad(self) -> IdentidadGlobalEstable:
        return IdentidadGlobalEstable(
            entity_id="fabprod:microsoft corporation:notepad",
            nombre_canonico="notepad",
            tipo_evidencia="fabricante_producto",
            evidencia_base={
                "nombre_comercial": "Notepad",
                "fabricante": "Microsoft Corporation",
                "version": "10.0.26100.9949",
            },
            confianza="alta",
            fusionar_por_nombre_desaconsejado=False,
            alternativas=[],
        )

    def test_3_8_5_1_4_11_3_registro_minimo_todos_los_campos_requeridos(self):
        """El registro mínimo de un ejecutable real tiene todos los campos
        obligatorios y supera la validación."""
        candidato = self._candidato_notepad_real()
        identidad = self._identidad_notepad()
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert validar_registro_minimo_aplicacion(registro) == []
        assert registro.entity_id == identidad.entity_id
        assert registro.nombre == "notepad"
        assert registro.aliases == ["notepad", "bloc de notas"]
        assert registro.categoria_rol == "gui_aplicacion"
        assert registro.ruta_absoluta_observada == self.RUTA_NOTEPAD
        assert registro.tipo_lanzamiento_nativo == "ejecutable"
        assert registro.estado_disponible == "available"
        assert registro.fecha_observacion == self.AHORA
        assert registro.fuente_observacion == FUENTE_START_MENU
        assert registro.evidencia_observacion == [
            "archivo_existe:" + self.RUTA_NOTEPAD
        ]
        assert registro.capacidades_verificadas == []
        assert registro.capacidades_no_verificadas == []
        assert registro.metadata["tipo_evidencia_identidad"] == "fabricante_producto"

    def test_3_8_5_1_4_11_3_entity_id_estable_sin_ruta_absoluta(self):
        """El identificador estable nunca incorpora la ruta absoluta y es
        determinista para el mismo candidato e identidad."""
        candidato = self._candidato_notepad_real()
        identidad = self._identidad_notepad()
        r1 = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        r2 = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert r1.entity_id == r2.entity_id == identidad.entity_id
        assert "C:" not in r1.entity_id
        assert "Windows" not in r1.entity_id
        assert "System32" not in r1.entity_id
        assert r1.a_dict_entidad() is not None  # serializable a Entity
        assert r1.created_at == r1.updated_at == self.AHORA

    def test_3_8_5_1_4_11_3_paquete_uri_sin_exe_conserva_destino_nativo(self):
        """Paquete/URI sin .exe: conserva identificador y destino nativo,
        ruta absoluta ausente, estado available."""
        candidato = DiscoveredCandidate(
            candidate_id="cand-ms-settings",
            name="Configuración",
            absolute_path=None,
            destination="ms-settings:",
            nombre_comercial="Configuración",
            aliases=["config", "ajustes"],
            launch_type=LaunchType.URI_APLICACION,
            launch_subtype=LaunchSubtype.DESCONOCIDO,
            es_lanzable=True,
            evidencia=["esquema_uri:ms-settings"],
            confianza=CONFIANZA_ALTA,
            fuente=FUENTE_INVENTARIO,
            ultima_comprobacion=self.AHORA,
        )
        identidad = IdentidadGlobalEstable(
            entity_id="paquete:ms.settings",
            nombre_canonico="configuración",
            tipo_evidencia="paquete",
            evidencia_base={"paquete_id": "ms.settings", "fuentes": ["inventario"]},
            confianza="alta",
            fusionar_por_nombre_desaconsejado=False,
            alternativas=[],
        )
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert validar_registro_minimo_aplicacion(registro) == []
        assert registro.ruta_absoluta_observada is None
        assert registro.tipo_lanzamiento_nativo == "uri_aplicacion"
        assert registro.categoria_rol == "desconocido"
        assert registro.estado_disponible == "available"
        assert registro.fuente_observacion == FUENTE_INVENTARIO

    def test_3_8_5_1_4_11_3_no_inventa_capacidades(self):
        """Nunca se inventan capacidades: listas vacías y sin campo
        capabilities inventado en las propiedades."""
        candidato = self._candidato_notepad_real()
        identidad = self._identidad_notepad()
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        datos = registro.a_dict_entidad()
        assert registro.capacidades_verificadas == []
        assert registro.capacidades_no_verificadas == []
        assert "capabilities" not in datos["properties"]
        assert datos["properties"]["capacidades_verificadas"] == []
        assert datos["properties"]["capacidades_no_verificadas"] == []

    def test_3_8_5_1_4_11_3_categoria_rol_desde_subtipo_real(self):
        """La categoría/rol se clasifica desde el launch_subtype real del
        candidato, sin asumir GUI por la extensión."""
        cli = self._candidato_notepad_real()
        cli.launch_subtype = LaunchSubtype.HERRAMIENTA_CLI
        servicio = self._candidato_notepad_real()
        servicio.launch_subtype = LaunchSubtype.SERVICIO
        desconocido = self._candidato_notepad_real()
        desconocido.launch_subtype = LaunchSubtype.DESCONOCIDO
        identidad = self._identidad_notepad()
        assert (
            construir_registro_minimo_aplicacion(cli, identidad, ahora_iso=self.AHORA)
            .categoria_rol
            == "herramienta_cli"
        )
        assert (
            construir_registro_minimo_aplicacion(
                servicio, identidad, ahora_iso=self.AHORA
            ).categoria_rol
            == "servicio"
        )
        assert (
            construir_registro_minimo_aplicacion(
                desconocido, identidad, ahora_iso=self.AHORA
            ).categoria_rol
            == "desconocido"
        )

    def test_3_8_5_1_4_11_3_estado_available_con_fecha_fuente_evidencia(self):
        """Estado available con fecha ISO, fuente de observación y evidencia
        sobre un archivo real del equipo (sin lanzar nada)."""
        candidato = self._candidato_notepad_real()
        identidad = self._identidad_notepad()
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert registro.estado_disponible == "available"
        assert registro.fecha_observacion == self.AHORA
        datetime.fromisoformat(registro.fecha_observacion)
        assert registro.fuente_observacion == FUENTE_START_MENU
        assert len(registro.evidencia_observacion) > 0

    def test_3_8_5_1_4_11_3_registro_a_dict_entidad_compatible(self):
        """El registro se serializa a un diccionario apto para `Entity` de
        `src.memory.storage` (id, type, name, properties, aliases, tags)."""
        candidato = self._candidato_notepad_real()
        identidad = self._identidad_notepad()
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        datos = registro.a_dict_entidad()
        ent = Entity.from_dict(datos)
        assert ent.id == identidad.entity_id
        assert ent.type == "application"
        assert ent.name == "notepad"
        assert ent.aliases == ["notepad", "bloc de notas"]
        assert ent.tags == ["gui_aplicacion"]
        p = ent.properties
        assert p["ruta_absoluta_observada"] == self.RUTA_NOTEPAD
        assert p["tipo_lanzamiento_nativo"] == "ejecutable"
        assert p["estado_disponible"] == "available"
        assert p["fecha_observacion"] == self.AHORA
        assert p["fuente_observacion"] == FUENTE_START_MENU

    def test_3_8_5_1_4_11_3_validacion_rechaza_campos_faltantes(self):
        """La validación rechaza registros con campos obligatorios faltantes
        y acepta los completos."""
        registro_valido = construir_registro_minimo_aplicacion(
            self._candidato_notepad_real(), self._identidad_notepad(), ahora_iso=self.AHORA
        )
        assert validar_registro_minimo_aplicacion(registro_valido) == []
        assert validar_registro_minimo_aplicacion(registro_valido.a_dict_entidad()) == []

        incompleto = {
            "entity_id": "x",
            "nombre": "App",
            # falta tipo, aliases, categoria_rol, estado, fecha, fuente, evidencia
        }
        faltantes = validar_registro_minimo_aplicacion(incompleto)
        assert "tipo" in faltantes
        assert "aliases" in faltantes
        assert "categoria_rol" in faltantes
        assert "estado_disponible" in faltantes
        assert "fecha_observacion" in faltantes
        assert "fuente_observacion" in faltantes
        assert "evidencia_observacion" in faltantes
        assert "entity_id" not in faltantes
        assert "nombre" not in faltantes

        vacio = {}
        assert set(validar_registro_minimo_aplicacion(vacio)) == set(
            _CAMPOS_REQUERIDOS_REGISTRO_MINIMO
        )

    def test_3_8_5_1_4_11_3_destino_no_observable_estado_no_disponible(self):
        """Destino sin archivo existente ni destino nativo: estado
        no_disponible y ruta absoluta ausente."""
        candidato = DiscoveredCandidate(
            candidate_id="cand-inexistente",
            name="NoExiste",
            absolute_path=r"C:\No\Existe\app.exe",
            destination=None,
            nombre_comercial="NoExiste",
            aliases=[],
            launch_type=LaunchType.EJECUTABLE,
            launch_subtype=LaunchSubtype.DESCONOCIDO,
            es_lanzable=False,
            evidencia=[],
            confianza=CONFIANZA_NINGUNA,
            fuente=FUENTE_INVENTARIO,
            ultima_comprobacion=self.AHORA,
        )
        identidad = IdentidadGlobalEstable(
            entity_id="candidato:noexiste",
            nombre_canonico="noexiste",
            tipo_evidencia="insuficiente",
            evidencia_base={},
            confianza="ninguna",
            fusionar_por_nombre_desaconsejado=True,
            alternativas=[],
        )
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert registro.estado_disponible == "no_disponible"
        # La ruta observada se conserva aunque el archivo no exista; la
        # disponibilidad se expresa en el estado.
        assert registro.ruta_absoluta_observada == r"C:\No\Existe\app.exe"
        assert validar_registro_minimo_aplicacion(registro) == []

    def test_3_8_5_1_4_11_3_identidad_real_de_notepad_sin_ruta_en_id(self):
        """Integración con cálculo de identidad real (11.2) sobre notepad.exe
        del equipo: entity_id estable derivado de metadatos del SO, sin
        fragmentos de ruta absoluta."""
        candidato = self._candidato_notepad_real()
        identidad = calcular_identidad_estable(candidato)
        registro = construir_registro_minimo_aplicacion(
            candidato, identidad, ahora_iso=self.AHORA
        )
        assert identidad.entity_id == "nombre:notepad"
        assert identidad.tipo_evidencia == "nombre_comercial"
        assert identidad.fusionar_por_nombre_desaconsejado is True
        assert "C:" not in identidad.entity_id
        assert "System32" not in identidad.entity_id
        assert "Windows" not in identidad.entity_id
        assert registro.entity_id == identidad.entity_id
        assert registro.metadata["tipo_evidencia_identidad"] == "nombre_comercial"
        assert identidad.evidencia_base["fabricante"] == "Microsoft Corporation"
        assert validar_registro_minimo_aplicacion(registro) == []


# ---------------------------------------------------------------------------
# Unidad 3.8.5.1.4.11.4: auto-registro de candidatos descubiertos en el
# catalogo global data/memory/entities.json.
# ---------------------------------------------------------------------------

class TestAutoRegistroDescubiertos:
    """
    Pruebas de `ApplicationDiscovery.auto_registrar_descubiertos`
    (3.8.5.1.4.11.4): auto-registra cada `.exe` descubierto en el catalogo
    global `data/memory/entities.json`, sin filtro por GUI y sin
    intervencion manual.

    Usa `MemoryManager` sobre ruta temporal para no tocar `data/` de
    produccion. `descubrir_todos` se reemplaza por un doble que devuelve
    candidatos conocidos (no toca fuentes reales del SO ni el inventario).
    No lanza ninguna aplicacion.
    """

    def _discovery_con_registro_temp(self, tmp_path, candidatos,
                                     machine_id="maquina-prueba"):
        from src.hands.application_preflight import ApplicationPreflight
        from src.hands.application_launch_classifier import LaunchClassifier
        from unittest.mock import MagicMock

        preflight = ApplicationPreflight()
        clasificador = LaunchClassifier(preflight=preflight)
        calib = MagicMock()
        calib.discover_applications.return_value = []
        storage = MagicMock()
        storage.connect.return_value = None
        storage.close.return_value = None
        storage.search.return_value = []
        mm = MemoryManager(str(tmp_path / "data" / "memory"))
        app_manager = MagicMock()
        app_manager.memory_manager = mm
        discovery = ApplicationDiscovery(
            preflight=preflight,
            clasificador=clasificador,
            storage=storage,
            calibration=calib,
            machine_id=machine_id,
            app_manager=app_manager,
        )
        discovery.descubrir_todos = lambda *a, **k: list(candidatos)
        return discovery, mm

    def _candidato(self, candidate_id, name, ruta, fuente=FUENTE_PATH,
                   launch_subtype=LaunchSubtype.DESCONOCIDO,
                   nombre_comercial=None, aliases=None, evidencia=None):
        return DiscoveredCandidate(
            candidate_id=candidate_id,
            name=name,
            absolute_path=ruta,
            destination=ruta,
            nombre_comercial=nombre_comercial or name,
            aliases=list(aliases or []),
            launch_type=LaunchType.EJECUTABLE,
            launch_subtype=launch_subtype,
            es_lanzable=True,
            evidencia=list(evidencia or []),
            confianza=CONFIANZA_ALTA,
            fuente=fuente,
            ultima_comprobacion="2026-11-12T00:00:00+00:00",
            disponible=True,
        )

    def test_3_8_5_1_4_11_4_registra_accesibles_sin_filtro_gui(self, tmp_path):
        """Registra ejecutables GUI y CLI por igual (sin filtro por GUI) y
        omite los cuyo destino no es observable en el equipo. Los entity_id
        son estables y nunca contienen la ruta absoluta."""
        exe_gui = tmp_path / "app_gui.exe"
        exe_gui.write_text("dummy ejecutable gui")
        exe_cli = tmp_path / "app_cli.exe"
        exe_cli.write_text("dummy ejecutable cli")

        candidatos = [
            self._candidato("c-gui", "App GUI", str(exe_gui),
                            launch_subtype=LaunchSubtype.GUI_APLICACION,
                            nombre_comercial="App GUI"),
            self._candidato("c-cli", "App CLI", str(exe_cli),
                            nombre_comercial="App CLI"),
            self._candidato("c-missing", "App Inexistente",
                            str(tmp_path / "no_existe.exe"),
                            fuente=FUENTE_INVENTARIO),
        ]

        discovery, mm = self._discovery_con_registro_temp(tmp_path, candidatos)
        resultado = discovery.auto_registrar_descubiertos(memory_manager=mm)

        assert resultado["registrados"] == 2
        assert resultado["omitidos"] == 1
        assert resultado["errores"] == 0
        assert resultado["total_descubiertos"] == 3

        omitido = resultado["detalle_omitidos"][0]
        assert omitido["candidato"] == "App Inexistente"
        assert omitido["razon"] == "destino_no_observable"

        # entity_id estable y sin fragmentos de ruta absoluta
        ids_registrados = [e["id"] for e in resultado["detalle_registrados"]]
        for eid in ids_registrados:
            assert "C:" not in eid
            assert str(tmp_path) not in eid

        # Ambas entidades se persisten en el MemoryManager temporal
        for e in resultado["detalle_registrados"]:
            entidad = mm.get_entity(e["id"])
            assert entidad is not None
            assert entidad.type == "application"
            assert entidad.properties["estado_disponible"] == "available"
            assert entidad.properties["capacidades_verificadas"] == []
            assert entidad.properties["capacidades_no_verificadas"] == []

    def test_3_8_5_1_4_11_4_upsert_no_duplica_al_repetir(self, tmp_path):
        """El upsert por ID estable no duplica al registrar el mismo candidato
        dos veces (idemposiente)."""
        exe = tmp_path / "app_dup.exe"
        exe.write_text("dummy")
        candidato = self._candidato("c-dup", "App Dup", str(exe),
                                    nombre_comercial="App Dup")

        discovery, mm = self._discovery_con_registro_temp(tmp_path, [candidato])
        r1 = discovery.auto_registrar_descubiertos(memory_manager=mm)
        r2 = discovery.auto_registrar_descubiertos(memory_manager=mm)

        assert r1["registrados"] == 1
        assert r2["registrados"] == 1  # actualiza, no duplica
        entidades = mm.get_entities_by_type("application")
        assert len(entidades) == 1  # una sola entidad, no dos

    def test_3_8_5_1_4_11_4_preserva_entidades_preexistentes(self, tmp_path):
        """No borra ni sobrescribe entidades que ya estaban en el catalogo
        global (preservacion de entidades no-app y previas)."""
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entidades_path = memoria_dir / "entities.json"
        entidades_path.write_text(
            json.dumps([
                {"id": "streamer-existente", "type": "streamer", "name": "Streamer",
                 "properties": {}, "aliases": [], "tags": [], "confidence": 1.0},
                {"id": "app-previa", "type": "application", "name": "App Previa",
                 "properties": {"estado_disponible": "available"}, "aliases": [],
                 "tags": [], "confidence": 1.0},
            ], ensure_ascii=False)
        )

        exe = tmp_path / "app_nueva.exe"
        exe.write_text("dummy")
        candidato = self._candidato("c-nueva", "App Nueva", str(exe),
                                    nombre_comercial="App Nueva")

        discovery, mm = self._discovery_con_registro_temp(tmp_path, [candidato])
        resultado = discovery.auto_registrar_descubiertos(memory_manager=mm)

        assert resultado["registrados"] == 1
        ids_todos = [e.id for e in mm.get_entities_by_type("application")] + \
                    [e.id for e in mm.get_entities_by_type("streamer")]
        assert "streamer-existente" in ids_todos
        assert "app-previa" in ids_todos

    def test_3_8_5_1_4_11_4_json_corrupto_no_vacia_catalogo(self, tmp_path):
        """Un entities.json corrupto hace que save_entity rechace la escritura
        (retorna False) sin vaciar el catalogo; el candidato se reporta como
        error y no se registra."""
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entidades_path = memoria_dir / "entities.json"
        entidades_path.write_text("{json corrupto no valido")

        exe = tmp_path / "app_corrupt.exe"
        exe.write_text("dummy")
        candidato = self._candidato("c-corrupt", "App Corrupt", str(exe),
                                    nombre_comercial="App Corrupt")

        discovery, mm = self._discovery_con_registro_temp(tmp_path, [candidato])
        resultado = discovery.auto_registrar_descubiertos(memory_manager=mm)

        assert resultado["registrados"] == 0
        assert resultado["errores"] == 1
        assert resultado["detalle_errores"][0]["candidato"] == "App Corrupt"
        # El archivo corrupto no se vació (proteccion de save_entity)
        assert entidades_path.read_text(encoding="utf-8") == "{json corrupto no valido"

    def test_3_8_5_1_4_11_4_integracion_notepad_real(self, tmp_path):
        """Integracion real: registra notepad.exe del equipo en un catalogo
        temporal y verifica que quede representado con entity_id estable y
        sin ruta absoluta, sin lanzar la aplicacion."""
        candidato = DiscoveredCandidate(
            candidate_id="c-notepad-integ",
            name="Notepad",
            absolute_path=r"C:\Windows\System32\notepad.exe",
            destination=r"C:\Windows\System32\notepad.exe",
            nombre_comercial="Notepad",
            aliases=["notepad", "bloc de notas"],
            launch_type=LaunchType.EJECUTABLE,
            launch_subtype=LaunchSubtype.GUI_APLICACION,
            es_lanzable=True,
            evidencia=["archivo_existe:C:\\Windows\\System32\\notepad.exe"],
            confianza=CONFIANZA_ALTA,
            fuente=FUENTE_START_MENU,
            ultima_comprobacion="2026-11-12T00:00:00+00:00",
            disponible=True,
        )

        discovery, mm = self._discovery_con_registro_temp(tmp_path, [candidato])
        resultado = discovery.auto_registrar_descubiertos(memory_manager=mm)

        assert resultado["registrados"] == 1
        entidad = mm.get_entity(resultado["detalle_registrados"][0]["id"])
        assert entidad is not None
        assert entidad.name == "notepad"
        assert entidad.type == "application"
        assert "C:" not in entidad.id
        assert "System32" not in entidad.id
        assert "Windows" not in entidad.id


# ---------------------------------------------------------------------------
# TestResolucionAplicacionPorNombre (unidad 3.8.5.1.4.11.6)
# ---------------------------------------------------------------------------

class TestResolucionAplicacionPorNombre:
    """
    Pruebas de `ApplicationDiscovery.resolver_aplicacion_por_nombre`
    (3.8.5.1.4.11.6): resolucion de aplicaciones por nombre que consulta
    primero el catalogo global (entities.json) y, si no esta, consulta
    application_candidates de SQLite local filtrado por machine_id y
    volumenes montados, auto-registra en el catalogo y revalida la ruta
    en el SO antes de considerar valida.

    Usa `SystemInventoryStorage` real sobre SQLite temporal y
    `ApplicationManager` mockeado para controlar si la app esta en el
    catalogo global. No lanza ninguna aplicacion.
    """

    def _setup_resolver(
        self,
        tmp_path,
        app_en_catalogo: bool = True,
        ruta_sqlite: Optional[str] = None,
        nombre_sqlite: Optional[str] = None,
        machine_id: str = "maquina-prueba-116",
    ):
        """
        Crea un ApplicationDiscovery con:
        - SystemInventoryStorage real sobre SQLite temporal
        - ApplicationManager mockeado (get_application controlado por app_en_catalogo)
        - Clasificador/preflight REALES

        Retorna (discovery, storage, app_manager_mock, mm_temp).
        El llamante debe cerrar storage al terminar.
        """
        from unittest.mock import MagicMock

        from src.hands.applications_core import ApplicationKnowledge

        # SQLite real temporal
        db_path = tmp_path / "data" / "system_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual=machine_id)

        # Registrar candidato en SQLite si se proporciona ruta
        if ruta_sqlite:
            storage.record_machine(machine_id)
            scan_id = f"scan-test-{uuid.uuid4()}"
            ahora = datetime.now(timezone.utc).isoformat()
            storage.begin_scan_run(
                scan_id=scan_id,
                machine_id=machine_id,
                volume="C:",
                mode=SCAN_MODE_FULL,
                started_at=ahora,
            )
            storage.insert_application_candidates(
                scan_id=scan_id,
                machine_id=machine_id,
                volume="C:",
                candidates=[
                    {
                        "candidate_id": str(uuid.uuid4()),
                        "name": nombre_sqlite or "App Test",
                        "absolute_path": ruta_sqlite,
                        "launch_type": "ejecutable",
                        "confianza": "alta",
                        "version": None,
                        "producto": None,
                        "evidencia": [],
                        "source": "inventario",
                        "last_checked_at": ahora,
                    }
                ],
            )
            storage.end_scan_run(
                scan_id=scan_id,
                finished_at=ahora,
                result=SCAN_RESULT_OK,
                entries_count=1,
            )

        # MemoryManager temporal para entities.json
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        mm = MemoryManager(str(memoria_dir))

        # ApplicationManager mockeado
        app_manager = MagicMock()
        app_manager.memory_manager = mm
        if app_en_catalogo:
            app_manager.get_application.return_value = ApplicationKnowledge(
                name="App Test",
                type="application",
                executable=ruta_sqlite or r"C:\Windows\System32\notepad.exe",
                url=None,
                login_required=False,
                default_state=None,
                capabilities=[],
            )
        else:
            app_manager.get_application.return_value = None

        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=None,
            machine_id=machine_id,
            app_manager=app_manager,
        )

        return discovery, storage, app_manager, mm

    def _teardown_resolver(self, storage):
        """Cierra storage."""
        storage.close()

    def test_116_resolver_en_catalogo_con_ruta_sqlite_valida(self, tmp_path):
        """App en catalogo global + ruta valida en SQLite: se resuelve con
        ruta de SQLite (no del catalogo), revalidada en el SO."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, app_manager, mm = self._setup_resolver(
            tmp_path,
            app_en_catalogo=True,
            ruta_sqlite=notepad,
            nombre_sqlite="Notepad",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre("Notepad")

            assert resultado is not None
            assert resultado.name == "Notepad"
            assert resultado.absolute_path == notepad
            assert resultado.fuente == "catalogo_conocido"
            assert resultado.disponible is True
            assert resultado.preflight_decision is not None
            assert resultado.preflight_decision.get("valid") is True
        finally:
            self._teardown_resolver(storage)

    def test_116_resolver_no_en_catalogo_sino_en_sqlite_auto_registra(self, tmp_path):
        """App NO en catalogo global pero SI en SQLite: se auto-registra en
        entities.json y se resuelve con preflight."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, app_manager, mm = self._setup_resolver(
            tmp_path,
            app_en_catalogo=False,
            ruta_sqlite=notepad,
            nombre_sqlite="Notepad",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre("Notepad")

            assert resultado is not None
            assert resultado.name == "Notepad"
            assert resultado.absolute_path == notepad
            assert resultado.fuente == "inventario"
            assert resultado.disponible is True
            assert resultado.preflight_decision is not None

            # Verificar que se auto-registro en entities.json (leer disco directamente
            # para evitar problemas de cache entre el mm del test y el del discovery).
            entidades_path = tmp_path / "data" / "memory" / "entities.json"
            assert entidades_path.exists(), f"entities.json no existe en {entidades_path}"
            entidades = json.loads(entidades_path.read_text(encoding="utf-8"))
            entidad_notepad = [e for e in entidades if e.get("name") == "notepad"]
            assert len(entidad_notepad) == 1, f"Esperada 1 entidad notepad, encontradas {len(entidad_notepad)}"
            entidad = entidad_notepad[0]
            assert entidad.get("type") == "application"
            # entity_id estable y sin fragmentos de ruta absoluta
            assert "C:" not in entidad.get("id", "")
            assert "System32" not in entidad.get("id", "")
            assert "Windows" not in entidad.get("id", "")
            # Ruta real observada en properties
            props = entidad.get("properties", {})
            assert props.get("ruta_absoluta_observada") == notepad
            assert props.get("estado_disponible") == "available"
            assert props.get("fuente_observacion") == "inventario"
        finally:
            self._teardown_resolver(storage)

    def test_116_resolver_no_en_catalogo_no_en_sqlite_retorna_none(self, tmp_path):
        """App no en catalogo ni en SQLite: retorna None."""
        discovery, storage, app_manager, mm = self._setup_resolver(
            tmp_path,
            app_en_catalogo=False,
            ruta_sqlite=None,
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre("AppInexistenteXYZ")

            assert resultado is None
        finally:
            self._teardown_resolver(storage)

    def test_116_resolver_en_catalogo_sin_ruta_valida_sqlite_retorna_none(self, tmp_path):
        """App en catalogo global pero sin ruta valida en SQLite: retorna None
        (no se asume vigente la ruta del catalogo)."""
        discovery, storage, app_manager, mm = self._setup_resolver(
            tmp_path,
            app_en_catalogo=True,
            ruta_sqlite=None,  # No hay candidato en SQLite
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre("Notepad")

            assert resultado is None
        finally:
            self._teardown_resolver(storage)

    def test_116_resolver_ruta_inexistente_en_sqlite_se_salta(self, tmp_path):
        """Candidato en SQLite con ruta que no existe en disco: se salta y
        retorna None si no hay otra valida."""
        ruta_inexistente = r"C:\NoExiste\app_inexistente.exe"
        discovery, storage, app_manager, mm = self._setup_resolver(
            tmp_path,
            app_en_catalogo=False,
            ruta_sqlite=ruta_inexistente,
            nombre_sqlite="App Inexistente",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre("App Inexistente")

            assert resultado is None
        finally:
            self._teardown_resolver(storage)

    def test_116_buscar_candidatos_registrados_filtro_nombre(self, tmp_path):
        """buscar_candidatos_registrados filtra por nombre (case-insensitive,
        subcadena) cuando se pasa el parametro name."""
        db_path = tmp_path / "data" / "system_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual="maquina-prueba-116b")
        try:
            storage.record_machine("maquina-prueba-116b")
            scan_id = f"scan-test-{uuid.uuid4()}"
            ahora = datetime.now(timezone.utc).isoformat()
            storage.begin_scan_run(
                scan_id=scan_id,
                machine_id="maquina-prueba-116b",
                volume="C:",
                mode=SCAN_MODE_FULL,
                started_at=ahora,
            )
            storage.insert_application_candidates(
                scan_id=scan_id,
                machine_id="maquina-prueba-116b",
                volume="C:",
                candidates=[
                    {
                        "candidate_id": str(uuid.uuid4()),
                        "name": "Notepad",
                        "absolute_path": r"C:\Windows\System32\notepad.exe",
                        "launch_type": "ejecutable",
                        "confianza": "alta",
                        "version": None,
                        "producto": None,
                        "evidencia": [],
                        "source": "inventario",
                        "last_checked_at": ahora,
                    },
                    {
                        "candidate_id": str(uuid.uuid4()),
                        "name": "Calculator",
                        "absolute_path": r"C:\Windows\System32\calc.exe",
                        "launch_type": "ejecutable",
                        "confianza": "alta",
                        "version": None,
                        "producto": None,
                        "evidencia": [],
                        "source": "inventario",
                        "last_checked_at": ahora,
                    },
                ],
            )
            storage.end_scan_run(
                scan_id=scan_id,
                finished_at=ahora,
                result=SCAN_RESULT_OK,
                entries_count=2,
            )

            # Buscar por nombre "pad" (subcadena case-insensitive)
            resultados = storage.buscar_candidatos_registrados(
                machine_id="maquina-prueba-116b", name="pad", limite=10
            )
            assert len(resultados) == 1
            assert resultados[0]["name"] == "Notepad"

            # Buscar por nombre exacto "Calculator"
            resultados = storage.buscar_candidatos_registrados(
                machine_id="maquina-prueba-116b", name="Calculator", limite=10
            )
            assert len(resultados) == 1
            assert resultados[0]["name"] == "Calculator"

            # Buscar nombre que no existe
            resultados = storage.buscar_candidatos_registrados(
                machine_id="maquina-prueba-116b", name="NoExiste", limite=10
            )
            assert len(resultados) == 0

            # Sin filtro name devuelve todos
            resultados = storage.buscar_candidatos_registrados(
                machine_id="maquina-prueba-116b", limite=10
            )
            assert len(resultados) == 2
        finally:
            storage.close()


# ---------------------------------------------------------------------------
# TestResolucionAplicacionPorNombreConDesambiguacion (unidad 3.8.5.1.4.11.7)
# ---------------------------------------------------------------------------

class TestResolucionAplicacionPorNombreConDesambiguacion:
    """
    Pruebas de `ApplicationDiscovery.resolver_aplicacion_por_nombre_con_desambiguacion`
    (3.8.5.1.4.11.7): integración del catálogo global
    (`ApplicationManager` / `entities.json`: identidad, nombres y aliases
    primero) con la resolución de instalación local (`ApplicationDiscovery` /
    SQLite).

    Cuando existen varios destinos locales plausibles para el mismo nombre,
    mantiene todas las alternativas y señala `ambiguo=True` /
    `requiere_desambiguacion=True` (reutiliza la señal de 3.8.5.1.4.9.3) sin
    elegir silenciosamente. `ApplicationPreflight` es obligatorio y se
    ejecuta antes de considerar un destino válido. No lanza nada ni abre
    ventanas.

    Usa `SystemInventoryStorage` real sobre SQLite temporal y
    `ApplicationManager` mockeado para controlar si la app está en el
    catálogo global. El clasificador y el preflight son REALES salvo en la
    prueba de exclusión por preflight, donde se inyecta un preflight que
    deniega.
    """

    def _setup_resolver_117(
        self,
        tmp_path,
        app_en_catalogo: bool,
        rutas_sqlite: list,
        nombres_sqlite: list,
        machine_id: str = "maquina-prueba-117",
    ):
        from unittest.mock import MagicMock

        from src.hands.applications_core import ApplicationKnowledge

        # SQLite real temporal
        db_path = tmp_path / "data" / "system_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual=machine_id)

        if rutas_sqlite:
            storage.record_machine(machine_id)
            scan_id = f"scan-test-{uuid.uuid4()}"
            ahora = datetime.now(timezone.utc).isoformat()
            storage.begin_scan_run(
                scan_id=scan_id,
                machine_id=machine_id,
                volume="C:",
                mode=SCAN_MODE_FULL,
                started_at=ahora,
            )
            storage.insert_application_candidates(
                scan_id=scan_id,
                machine_id=machine_id,
                volume="C:",
                candidates=[
                    {
                        "candidate_id": str(uuid.uuid4()),
                        "name": n,
                        "absolute_path": r,
                        "launch_type": "ejecutable",
                        "confianza": "alta",
                        "version": None,
                        "producto": None,
                        "evidencia": [],
                        "source": "inventario",
                        "last_checked_at": ahora,
                    }
                    for r, n in zip(rutas_sqlite, nombres_sqlite)
                ],
            )
            storage.end_scan_run(
                scan_id=scan_id,
                finished_at=ahora,
                result=SCAN_RESULT_OK,
                entries_count=len(rutas_sqlite),
            )

        # MemoryManager temporal para entities.json
        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        mm = MemoryManager(str(memoria_dir))

        # ApplicationManager mockeado (get_application controlado)
        app_manager = MagicMock()
        app_manager.memory_manager = mm
        if app_en_catalogo and rutas_sqlite:
            app_manager.get_application.return_value = ApplicationKnowledge(
                name="App Test 117",
                type="application",
                executable=rutas_sqlite[0],
                url=None,
                login_required=False,
                default_state=None,
                capabilities=[],
            )
        else:
            app_manager.get_application.return_value = None

        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=LaunchClassifier(preflight=ApplicationPreflight()),
            storage=storage,
            calibration=None,
            machine_id=machine_id,
            app_manager=app_manager,
        )

        return discovery, storage, app_manager, mm

    def _teardown_resolver(self, storage):
        """Cierra storage."""
        storage.close()

    def _copia_notepad(self, tmp_path) -> str:
        """Copia real de notepad.exe en un directorio temporal (recurso controlado)."""
        import shutil

        origen = r"C:\Windows\System32\notepad.exe"
        destino = str(tmp_path / "notepad_copia_117.exe")
        shutil.copyfile(origen, destino)
        return destino

    def test_117_varios_destinos_locales_ambiguos_mantiene_alternativas(
        self, tmp_path
    ):
        """Dos destinos locales válidos para el mismo nombre: ambiguo, se
        conservan ambas alternativas y no se elige silenciosamente."""
        notepad = r"C:\Windows\System32\notepad.exe"
        copia = self._copia_notepad(tmp_path)
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, _, _ = self._setup_resolver_117(
            tmp_path,
            app_en_catalogo=False,
            rutas_sqlite=[notepad, copia],
            nombres_sqlite=["App Duplicada", "App Duplicada"],
            machine_id="maquina-prueba-117a",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "App Duplicada"
            )

            assert resultado.ambiguo is True
            assert resultado.requiere_desambiguacion is True
            assert len(resultado.candidatos) == 2
            assert len(resultado.alternativas) == 2
            rutas_devueltas = {c.absolute_path for c in resultado.candidatos}
            assert rutas_devueltas == {notepad, copia}
            # Ninguno se eligió silenciosamente: todas son alternativas.
            assert all(c.preflight_decision is not None for c in resultado.candidatos)
        finally:
            self._teardown_resolver(storage)

    def test_117_un_destino_valido_retorna_unico_sin_ambiguedad(self, tmp_path):
        """Un único destino local válido: resolución única, sin ambigüedad."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, _, _ = self._setup_resolver_117(
            tmp_path,
            app_en_catalogo=False,
            rutas_sqlite=[notepad],
            nombres_sqlite=["App Unica"],
            machine_id="maquina-prueba-117c",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "App Unica"
            )

            assert resultado.ambiguo is False
            assert resultado.requiere_desambiguacion is False
            assert len(resultado.candidatos) == 1
            assert len(resultado.alternativas) == 0
            assert resultado.candidatos[0].absolute_path == notepad
            assert resultado.candidatos[0].disponible is True
            assert resultado.candidatos[0].preflight_decision is not None
            assert resultado.candidatos[0].preflight_decision.get("valid") is True
        finally:
            self._teardown_resolver(storage)

    def test_117_app_en_catalogo_fuente_autoritaria_es_catalogo(self, tmp_path):
        """App en el catálogo global: la fuente autoritativa es el catálogo y
        la ruta se resuelve desde SQLite local (no se confía en la del catálogo)."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, _, _ = self._setup_resolver_117(
            tmp_path,
            app_en_catalogo=True,
            rutas_sqlite=[notepad],
            nombres_sqlite=["App Test 117"],
            machine_id="maquina-prueba-117d",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "App Test 117"
            )

            assert resultado.ambiguo is False
            assert len(resultado.candidatos) == 1
            assert resultado.fuente_autoritaria == FUENTE_CATALOGO
            assert resultado.candidatos[0].absolute_path == notepad
            assert resultado.candidatos[0].preflight_decision.get("valid") is True
        finally:
            self._teardown_resolver(storage)

    def test_117_candidato_sin_preflight_valido_se_excluye(self, tmp_path):
        """Candidato cuyo preflight no es válido: se excluye de la resolución
        (preflight obligatorio antes de cualquier lanzamiento)."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        from unittest.mock import MagicMock

        from src.hands.applications_core import ApplicationKnowledge

        db_path = tmp_path / "data" / "system_inventory.sqlite3"
        storage = SystemInventoryStorage(db_path=db_path)
        storage.initialize(machine_id_actual="maquina-prueba-117b")
        storage.record_machine("maquina-prueba-117b")
        scan_id = f"scan-test-{uuid.uuid4()}"
        ahora = datetime.now(timezone.utc).isoformat()
        storage.begin_scan_run(
            scan_id=scan_id, machine_id="maquina-prueba-117b", volume="C:",
            mode=SCAN_MODE_FULL, started_at=ahora,
        )
        storage.insert_application_candidates(
            scan_id=scan_id, machine_id="maquina-prueba-117b", volume="C:",
            candidates=[
                {
                    "candidate_id": str(uuid.uuid4()),
                    "name": "App Bloqueada",
                    "absolute_path": notepad,
                    "launch_type": "ejecutable",
                    "confianza": "alta",
                    "version": None,
                    "producto": None,
                    "evidencia": [],
                    "source": "inventario",
                    "last_checked_at": ahora,
                }
            ],
        )
        storage.end_scan_run(
            scan_id=scan_id,
            finished_at=ahora,
            result=SCAN_RESULT_OK,
            entries_count=1,
        )

        memoria_dir = tmp_path / "data" / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        mm = MemoryManager(str(memoria_dir))

        app_manager = MagicMock()
        app_manager.memory_manager = mm
        app_manager.get_application.return_value = None

        clasificador = LaunchClassifier(preflight=MagicMock())
        clasificador.preflight.validate_launch_destination.return_value = {
            "valid": False,
            "reason": "Destino bloqueado por política",
            "destination": notepad,
        }
        discovery = ApplicationDiscovery(
            preflight=ApplicationPreflight(),
            clasificador=clasificador,
            storage=storage,
            calibration=None,
            machine_id="maquina-prueba-117b",
            app_manager=app_manager,
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "App Bloqueada"
            )

            assert resultado.ambiguo is False
            assert resultado.requiere_desambiguacion is False
            assert len(resultado.candidatos) == 0
        finally:
            storage.close()

    def test_117_no_encontrado_retorna_vacio(self, tmp_path):
        """No hay catálogo ni candidatos locales: resolución vacía."""
        discovery, storage, _, _ = self._setup_resolver_117(
            tmp_path,
            app_en_catalogo=False,
            rutas_sqlite=[],
            nombres_sqlite=[],
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "AppQueNoExisteEnNingunLadoXYZ"
            )

            assert resultado.ambiguo is False
            assert resultado.requiere_desambiguacion is False
            assert len(resultado.candidatos) == 0
            assert len(resultado.alternativas) == 0
        finally:
            self._teardown_resolver(storage)

    def test_117_auto_registra_en_entities_json_cuando_no_esta_en_catalogo(
        self, tmp_path
    ):
        """App no en catálogo global y un destino local válido: se auto-registra
        en entities.json (upsert, sin intervención manual) y se resuelve."""
        notepad = r"C:\Windows\System32\notepad.exe"
        if not os.path.isfile(notepad):
            pytest.skip("notepad.exe no disponible en este equipo")

        discovery, storage, app_manager, mm = self._setup_resolver_117(
            tmp_path,
            app_en_catalogo=False,
            rutas_sqlite=[notepad],
            nombres_sqlite=["App AutoRegistro"],
            machine_id="maquina-prueba-117e",
        )
        try:
            resultado = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(
                "App AutoRegistro"
            )

            assert resultado is not None
            assert resultado.ambiguo is False
            assert len(resultado.candidatos) == 1
            assert resultado.candidatos[0].absolute_path == notepad
            assert resultado.candidatos[0].preflight_decision.get("valid") is True

            # Verificar auto-registro en entities.json del disco.
            entidades_path = tmp_path / "data" / "memory" / "entities.json"
            assert entidades_path.exists(), f"entities.json no existe en {entidades_path}"
            entidades = json.loads(entidades_path.read_text(encoding="utf-8"))
            entidad = [
                e
                for e in entidades
                if e.get("type") == "application"
                and e.get("properties", {}).get("ruta_absoluta_observada") == notepad
            ]
            assert len(entidad) == 1, f"Esperada 1 entidad, encontradas {len(entidad)}: {entidades}"
            entidad = entidad[0]
            assert entidad.get("type") == "application"
            props = entidad.get("properties", {})
            assert props.get("ruta_absoluta_observada") == notepad
            assert props.get("estado_disponible") == "available"
            # entity_id estable sin fragmentos de ruta absoluta.
            assert "C:" not in entidad.get("id", "")
            assert "System32" not in entidad.get("id", "")
            assert "Windows" not in entidad.get("id", "")
        finally:
            self._teardown_resolver(storage)
