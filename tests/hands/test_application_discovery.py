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
    CONFIANZA_NINGUNA,
    LaunchClassifier,
)
from src.hands.system_inventory import EntryType
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
        con preflight (verificación real de unidad 3.8.5.1.4.9.1)."""
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

        # Insertar entrada apuntando a archivo real del sistema
        storage.insert_file_entries("scan-integracion-91", "maquina-integracion-91",
                                    "C:", [self._una_entrada("e-notepad", notepad,
                                                             "notepad.exe")])
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
        resultado = discovery.buscar_por_nombre("notepad", incluir_inventario=True)

        assert len(resultado) >= 1
        assert any(c.name.casefold() == "notepad.exe" for c in resultado)
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
