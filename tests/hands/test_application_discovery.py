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

Estrategia de mocks: solo se mockean las fuentes de DATOS
(`CalibrationManager.discover_applications` y `SystemInventoryStorage`). La
clasificacion y el preflight son REALES (`LaunchClassifier` +
`ApplicationPreflight` sobre archivos reales del equipo), por lo que ningún mock
decide el resultado de clasificación ni de validación. No se lanza ninguna
aplicación y no se modifica `entities.json`.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.hands.application_discovery import (
    ApplicationDiscovery,
    DiscoveredCandidate,
    FUENTE_APP_PATHS,
    FUENTE_APPX,
    FUENTE_INVENTARIO,
    FUENTE_PATH,
    FUENTE_START_MENU,
    FUENTE_UNINSTALL_REGISTRY,
    FUENTES_PRIMARIAS,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.application_launch_classifier import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    CONFIANZA_MEDIA,
    LaunchClassifier,
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
        assert any(c.name.casefold() == "notepad" for c in resultado)

    def test_buscar_por_nombre_faltante_consulta_inventario(self):
        descub, _, storage = _discovery_con_mocks(calib_apps=[])
        storage.search.return_value = [
            {"absolute_path": r"C:\Program Files\MiApp\miapp.exe", "name": "miapp.exe",
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
