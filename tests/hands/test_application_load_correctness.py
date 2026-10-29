# -*- coding: utf-8 -*-
"""Tests de carga correcta e incorrecta — unidad 3.2.3.4 (FASE 3.2.3 — Errores,
bajo 3.2 CARGA Y REGISTRO).

Verifica el comportamiento del flujo de CARGA de aplicaciones
(`ApplicationManager._load_custom_applications`) a nivel de gestor — lo que
termina materializado en `manager.applications` — tanto para datos CORRECTOS
como INCORRECTOS. Es complementario a:

- `test_application_invalid_json.py` (3.2.3.1): resultados ante JSON sintáctico
  inválido, a nivel de `JSONStorage.load`.
- `test_application_data_incomplete.py` (3.2.3.2 / 3.2.3.3): resultados ante
  entidad inválida (campos obligatorios ausentes) y registro de errores, a
  nivel de `MemoryManager.get_entities_by_type`/`get_entity`.
- `test_application_load.py` (3.2.2.2): round-trip `register -> load` y
  reconstrucción de `ui_elements`/`states`.

Carga correcta: las entidades `application` válidas se materializan en
`ApplicationKnowledge` reconstruyendo todos sus campos (nombre, tipo,
ejecutable, url, `login_required`, capabilities como enums, `ui_elements`,
`states`, aliases en `metadata`); varias entidades se cargan como apps
independientes.

Carga incorrecta: entidades que no deben materializarse como aplicación (tipo
distinto) se omiten; una entidad cuyo nombre colisiona con una aplicación ya
registrada (p. ej. una duplicada de Chrome) se omite sin apagar ni sobreescribir
la app registrada; una entidad con nombre usable vacío produce
`_reconstruct_application -> None` y se omite; y si la fuente devuelve un tipo no
lista (`get_entities_by_type` no lista), `_load_custom_applications` retorna
tempranamente sin lanzar.

Los tests usan un `MemoryManager` aislado en `tmp_path` (sandbox) y, salvo que se
indique lo contrario, un `ApplicationManager` construido con `__new__` para
evitar tocar `data/` de producción y aislar la lógica de carga. No abren
aplicaciones, no lanzan procesos.
"""

import json
from pathlib import Path

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
)
from src.memory.storage import MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_entities_json(storage_path: Path, entities_list) -> None:
    """Escribe entities.json (lista de dicts) en el directorio de datos."""
    (storage_path / "entities.json").write_text(
        json.dumps(entities_list), encoding="utf-8"
    )


def _make_min_manager(memory_manager):
    """ApplicationManager aislado (bypass __init__) con el MemoryManager dado.

    No ejecuta `_initialize_applications`, por lo que `applications` parte
    vacío. Permite probar `_load_custom_applications` en aislamiento controlando
    exactamente qué hay pre-registrado.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = memory_manager
    return manager


def _full_application_entity(
    entity_id="app_full", name="FullApp", properties_extra=None
):
    """Construye un dict de entidad `application` con el formato de
    `register_application` (properties con type/executable/url/login_required/
    capabilities/ui_elements/states) y aliases de trazabilidad."""
    props = {
        "type": "browser",
        "executable": "full.exe",
        "url": "https://full.example",
        "login_required": True,
        "capabilities": ["open", "navigate", "search"],
        "ui_elements": [
            {
                "name": "url_bar",
                "type": "input",
                "description": "Barra de URL",
                "coordinates": {"x": 10, "y": 20},
                "screen": 1,
                "calibration_data": {"conf": 0.9},
                "required_capability": "navigate",
            },
            {
                "name": "go_button",
                "type": "button",
                "description": "Botón ir",
                "coordinates": {"x": 30, "y": 40},
                "screen": 1,
                "calibration_data": None,
                "required_capability": "click",
            },
        ],
        "states": ["closed", "open", "active"],
    }
    if properties_extra:
        props.update(properties_extra)
    return {
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": props,
        "aliases": ["full", "f"],
        "tags": ["t1"],
        "confidence": 0.9,
        "created_at": "2024-01-01T00:00:00.000000",
        "updated_at": "2024-01-01T00:00:00.000000",
        "metadata": None,
    }


def _legacy_entity(
    entity_id="app_legacy", name="LegacyApp", category="music", extra_props=None
):
    """Construye un dict de entidad `application` en formato legacy (solo
    url/executable/category en properties)."""
    props = {
        "url": "https://legacy.example",
        "executable": "legacy.exe",
        "category": category,
    }
    if extra_props:
        props.update(extra_props)
    return {
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": props,
        "aliases": [],
        "tags": [],
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00.000000",
        "updated_at": "2024-01-01T00:00:00.000000",
        "metadata": None,
    }


# ---------------------------------------------------------------------------
# 1. CARGA CORRECTA
# ---------------------------------------------------------------------------
class TestCargaCorrecta:
    """La carga materializa correctamente las applications válidas."""

    def test_load_valid_application_reconstructs_all_fields(self, tmp_path):
        """Una entidad `application` válida se reconstruye con todos sus campos
        a nivel de gestor (carga correcta)."""
        _write_entities_json(tmp_path, [_full_application_entity()])
        manager = _make_min_manager(MemoryManager(tmp_path))

        manager._load_custom_applications()

        assert "fullapp" in manager.applications
        app = manager.applications["fullapp"]
        assert app.name == "FullApp"
        assert app.type == "browser"
        assert app.executable == "full.exe"
        assert app.url == "https://full.example"
        assert app.login_required is True
        # capabilities reconstruidas como enums, en orden
        assert [c.capability for c in app.capabilities] == [
            ApplicationCapability.OPEN,
            ApplicationCapability.NAVIGATE,
            ApplicationCapability.SEARCH,
        ]
        # ui_elements y states preservados (conocimiento + coordenadas)
        assert [e.name for e in app.ui_elements] == ["url_bar", "go_button"]
        assert app.ui_elements[0].description == "Barra de URL"
        assert app.ui_elements[0].coordinates == {"x": 10, "y": 20}
        assert app.ui_elements[0].screen == 1
        assert app.ui_elements[0].calibration_data == {"conf": 0.9}
        assert app.ui_elements[0].required_capability == ApplicationCapability.NAVIGATE
        assert app.ui_elements[1].description == "Botón ir"
        assert app.ui_elements[1].coordinates == {"x": 30, "y": 40}
        assert app.ui_elements[1].required_capability == ApplicationCapability.CLICK
        assert app.states == [
            ApplicationState.CLOSED,
            ApplicationState.OPEN,
            ApplicationState.ACTIVE,
        ]

    def test_load_preserves_aliases_and_entity_id_in_metadata(self, tmp_path):
        """Los aliases de la entidad aparecen en metadata y se conserva el
        entity_id; el nombre normalizado no colisiona con los aliases."""
        _write_entities_json(tmp_path, [_full_application_entity()])
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        app = manager.applications["fullapp"]
        assert app.metadata["entity_id"] == "app_full"
        assert app.metadata["aliases"] == ["full", "f"]

    @pytest.mark.parametrize(
        "app_type",
        ["browser", "media", "utility", "video_platform"],
    )
    def test_load_preserves_application_type(self, tmp_path, app_type):
        """El tipo de aplicación se mantiene tras la carga."""
        _write_entities_json(
            tmp_path,
            [_full_application_entity(properties_extra={"type": app_type})],
        )
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert "fullapp" in manager.applications
        assert manager.applications["fullapp"].type == app_type

    def test_load_multiple_valid_applications(self, tmp_path):
        """Varias applications válidas se cargan como apps independientes bajo
        su nombre normalizado."""
        _write_entities_json(
            tmp_path,
            [
                _full_application_entity("app_one", "FirstApp"),
                _full_application_entity("app_two", "SecondApp"),
            ],
        )
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert set(manager.applications.keys()) == {"firstapp", "secondapp"}
        assert manager.applications["firstapp"].name == "FirstApp"
        assert manager.applications["secondapp"].name == "SecondApp"

    def test_load_legacy_category_maps_to_application_type(self, tmp_path):
        """Una entidad legacy (properties con `category`, sin `type`) reconstruye
        ApplicationKnowledge.type == category (formato legacy)."""
        _write_entities_json(
            tmp_path, [_legacy_entity("app_legacy", "LegacyApp", category="music")]
        )
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert "legacyapp" in manager.applications
        app = manager.applications["legacyapp"]
        assert app.name == "LegacyApp"
        assert app.type == "music"
        assert app.executable == "legacy.exe"
        assert app.url == "https://legacy.example"
        assert app.login_required is False
        # Sin ui_elements/states en legacy -> defaults
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]

    def test_load_returns_none_on_success(self, tmp_path):
        """_load_custom_applications es void: retorna None (no lanza) con datos
        correctos."""
        _write_entities_json(tmp_path, [_full_application_entity()])
        manager = _make_min_manager(MemoryManager(tmp_path))

        result = manager._load_custom_applications()

        assert result is None
        assert "fullapp" in manager.applications


# ---------------------------------------------------------------------------
# 2. CARGA INCORRECTA
# ---------------------------------------------------------------------------
class TestCargaIncorrecta:
    """La carga omite de forma segura las entidades que no deben materializarse
    como aplicación, sin afectar a las válidas ni a las ya registradas."""

    def test_load_skips_non_application_type_entities(self, tmp_path):
        """Una entidad cuyo `type` (discriminador) no es `application` (p. ej.
        `streamer`) no se materializa como aplicación; solo las `application`
        válidas se cargan."""
        streamer = {
            "id": "bad_streamer",
            "type": "streamer",
            "name": "StreamerEnt",
            "properties": {"url": "https://x.example", "platform": "twitch",
                           "category": "gaming"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01T00:00:00.000000",
            "updated_at": "2024-01-01T00:00:00.000000", "metadata": None,
        }
        _write_entities_json(tmp_path, [_full_application_entity("app_ok", "OkApp"), streamer])
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert set(manager.applications.keys()) == {"okapp"}
        # La entidad no-application no fue materializada
        assert "streamerent" not in manager.applications
        assert "bad_streamer" not in manager.applications

    def test_load_skips_invalid_entity_missing_name_keeps_valid(self, tmp_path):
        """Una entidad `application` inválida (falta `name`, campo obligatorio)
        se omite per-item durante `get_entities_by_type`; una entidad válida
        vecina se carga igual y no se propaga la excepción a la carga."""
        invalid = {
            "id": "bad_app",
            "type": "application",
            "properties": {"url": "http://bad.com", "executable": "bad.exe",
                           "category": "test"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_full_application_entity("app_ok", "OkApp"), invalid])
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert set(manager.applications.keys()) == {"okapp"}
        assert manager.applications["okapp"].name == "OkApp"
        # La entidad inválida (sin name usable) no se materializa
        assert "bad_app" not in manager.applications
        assert "badapp" not in manager.applications

    def test_load_skips_duplicate_app_keeps_registered(self, tmp_path):
        """Una entidad cuyo nombre normaliza a una app ya registrada
        (p. ej. 'Google Chrome' -> 'chrome') se omite sin sobreescribir la app
        registrada: la duplicada no entra y la app existente se conserva."""
        # Simula Chrome ya registrada durante _initialize_applications
        sentinel = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_chrome", description="Abre Chrome",
                    required_ui_elements=[], preconditions=["chrome_closed"],
                    effects=["chrome_open"], cost=10.0,
                ),
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.NAVIGATE,
                    name="navigate_to_url", description="Navega",
                    required_ui_elements=["address_bar"],
                    preconditions=["chrome_open"], effects=["url_changed"],
                    cost=3.0,
                ),
            ],
        )
        # Entidad duplicada (nombre normalizado -> 'chrome') + una app nueva válida
        dup_entity = _legacy_entity("app_dup", "Google Chrome")
        _write_entities_json(
            tmp_path,
            [dup_entity, _full_application_entity("app_new", "NewApp")],
        )
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)
        manager.applications["chrome"] = sentinel

        manager._load_custom_applications()

        # Chrome (sentinel) no fue sobrescrito por la duplicada
        assert "chrome" in manager.applications
        assert manager.applications["chrome"] is sentinel
        assert [c.capability for c in manager.applications["chrome"].capabilities] == [
            ApplicationCapability.OPEN, ApplicationCapability.NAVIGATE,
        ]
        # La duplicada no generó una entrada 'googlechrome'
        assert "googlechrome" not in manager.applications
        # La app nueva sí se cargó
        assert "newapp" in manager.applications
        assert manager.applications["newapp"].name == "NewApp"

    def test_load_skips_entity_with_empty_name(self, tmp_path):
        """Una entidad `application` con nombre usable vacío (name/id vacíos)
        produce `_reconstruct_application -> None` y se omite; no se materializa
        como aplicación y no lanza."""
        empty_name = {
            "id": "",
            "type": "application",
            "name": "",
            "properties": {"executable": "empty.exe"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01T00:00:00.000000",
            "updated_at": "2024-01-01T00:00:00.000000",
            "metadata": None,
        }
        _write_entities_json(
            tmp_path, [_full_application_entity("app_ok", "OkApp"), empty_name]
        )
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        assert set(manager.applications.keys()) == {"okapp"}
        # No se creó una entrada con clave vacía
        assert "" not in manager.applications

    def test_load_non_list_entities_returns_none_without_crash(self, tmp_path):
        """Si `get_entities_by_type` devuelve un tipo no lista,
        `_load_custom_applications` retorna early (None) sin lanzar y sin
        tocar las apps registradas."""
        manager = _make_min_manager(MemoryManager(tmp_path))
        # Fuente de datos que devuelve un tipo no lista (defensiva del código)
        manager.memory_manager.get_entities_by_type = lambda entity_type: {"not": "a list"}

        result = manager._load_custom_applications()

        assert result is None
        assert manager.applications == {}

    def test_load_non_dict_properties_degrades_gracefully(self, tmp_path):
        """Una entity con `properties` de tipo no dict (dato incorrecto) no
        lanza; `_reconstruct_application` normaliza properties a `{}` y la app
        se materializa con valores por defecto, sin afectar a una entity válida
        vecina."""
        bad_props_entity = {
            "id": "bad_props",
            "type": "application",
            "name": "BadProps",
            # properties no es un dict -> _reconstruct_application lo normaliza a {}
            "properties": "not-a-dict",
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(
            tmp_path, [_full_application_entity("app_ok", "OkApp"), bad_props_entity]
        )
        manager = _make_min_manager(MemoryManager(tmp_path))
        manager._load_custom_applications()

        # La entity válida se carga
        assert "okapp" in manager.applications
        # La entity con properties incorrecto se reconstruye con defaults (no crash)
        assert "badprops" in manager.applications
        assert manager.applications["badprops"].name == "BadProps"
        assert manager.applications["badprops"].type == "application"
        assert manager.applications["badprops"].executable is None
        assert manager.applications["badprops"].url is None
        assert manager.applications["badprops"].login_required is False
        assert manager.applications["badprops"].ui_elements == []
        assert manager.applications["badprops"].states == [ApplicationState.CLOSED]
