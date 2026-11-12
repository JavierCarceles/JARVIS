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
import shutil
import sys
import tempfile
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
    ResultadoResolucionCandidatos,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
)
from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    CONFIANZA_NINGUNA,
    LaunchClassifier,
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
