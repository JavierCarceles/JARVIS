# -*- coding: utf-8 -*-
"""Tests de carga del conjunto de aplicaciones — unidad 3.2.2.2 (FASE 3.2.2).

Objetivo: "Implementar o verificar carga del conjunto de aplicaciones" —
completar la carga materializando ``ui_elements`` y ``states`` desde
``Entity.properties``, tanto en la fase de persistencia
(``register_application``) como en la fase de reconstruccion
(``_reconstruct_application``).

Antes de 3.2.2.2, ``register_application`` persistia solo
{type, executable, url, login_required, capabilities} y perdia
``ui_elements``/``states`` (contrato 3.1.2.4 / caracterizacion 3.2.2.1).
Esta unidad cierra esa brecha: persiste y reconstruye ui_elements y states,
permitiendo un round-trip register -> entity -> reconstruct lossless para
estos campos.

Los tests usan un MemoryManager aislado (sandbox) para evitar tocar data/
de produccion. No abren aplicaciones, no lanzan procesos.
"""

import copy
import json
import shutil

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    _serialize_ui_element,
)
from src.memory.storage import Entity, MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_min_manager():
    """ApplicationManager aislado (bypass __init__) con MemoryManager que almacena.

    A diferencia del _FakeMemoryManager de test_application_read.py (que solo
    captura sin devolver), este almacena y devuelve entidades, permitiendo
    tests de round-trip register -> load.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _StoringMemoryManager:
        def __init__(self):
            self._entities = []

        def save_entity(self, entity):
            self._entities.append(entity)
            return True

        def get_entities_by_type(self, t):
            return [e for e in self._entities if e.type == t]

    manager.memory_manager = _StoringMemoryManager()
    return manager


def _entity_with_ui_states(name="TestApp", app_type="browser"):
    """Crea una Entity application con ui_elements y states en properties."""
    props = {
        "type": app_type,
        "executable": "test.exe",
        "url": "https://test.example",
        "login_required": False,
        "capabilities": ["open", "navigate"],
        "ui_elements": [
            {
                "name": "search_bar",
                "type": "input",
                "coordinates": {"x": 100, "y": 200},
                "screen": 1,
                "calibration_data": {"conf": 0.9},
                "required_capability": "search",
            },
            {
                "name": "play_button",
                "type": "button",
                "coordinates": {"x": 300, "y": 400},
                "screen": 2,
                "calibration_data": None,
                "required_capability": None,
            },
        ],
        "states": ["closed", "open", "active"],
    }
    data = {
        "id": f"app_{name.lower()}",
        "type": "application",
        "name": name,
        "properties": props,
        "aliases": [],
        "confidence": 1.0,
        "tags": [],
        "created_at": "2024-01-01T00:00:00.000000",
        "updated_at": "2024-01-01T00:00:00.000000",
        "metadata": None,
    }
    return Entity.from_dict(data)


def _entity_legacy(name="LegacyApp", app_type="utility"):
    """Crea una Entity application en formato legacy (sin ui_elements/states)."""
    data = {
        "id": f"app_{name.lower()}",
        "type": "application",
        "name": name,
        "properties": {
            "type": app_type,
            "executable": "legacy.exe",
            "url": "https://legacy.example",
        },
        "aliases": ["legacy"],
        "confidence": 1.0,
        "tags": [],
        "created_at": "2024-01-01T00:00:00.000000",
        "updated_at": "2024-01-01T00:00:00.000000",
        "metadata": None,
    }
    return Entity.from_dict(data)


# ---------------------------------------------------------------------------
# 1. _serialize_ui_element
# ---------------------------------------------------------------------------

class TestSerializeUIElement:
    """Verifica que _serialize_ui_element produce dicts JSON-friendly."""

    def test_serialize_basic_element(self):
        el = UIElement(name="btn", type="button")
        d = _serialize_ui_element(el)
        assert d == {
            "name": "btn",
            "type": "button",
            "coordinates": None,
            "screen": 0,
            "calibration_data": None,
            "required_capability": None,
        }

    def test_serialize_with_capability(self):
        el = UIElement(
            name="search", type="input",
            coordinates={"x": 10, "y": 20},
            required_capability=ApplicationCapability.SEARCH,
        )
        d = _serialize_ui_element(el)
        assert d["coordinates"] == {"x": 10, "y": 20}
        assert d["required_capability"] == "search"

    def test_serialize_is_json_serializable(self):
        """El dict resultante no contiene objetos enum (solo strings)."""
        el = UIElement(
            name="btn", type="button", screen=1,
            required_capability=ApplicationCapability.NAVIGATE,
        )
        d = _serialize_ui_element(el)
        json.dumps(d)  # no debe lanzar
        assert d["required_capability"] == "navigate"

    def test_serialize_multiscreen_coordinates(self):
        el = UIElement(
            name="btn", type="button",
            coordinates={"s1": [10, 20], "s2": [30, 40]},
        )
        d = _serialize_ui_element(el)
        assert d["coordinates"] == {"s1": [10, 20], "s2": [30, 40]}


# ---------------------------------------------------------------------------
# 2. _reconstruct_ui_elements
# ---------------------------------------------------------------------------

class TestReconstructUIElements:
    """Verifica la reconstruccion robusta de UIElement desde dicts."""

    def test_valid_elements_reconstructed(self):
        data = [
            {"name": "btn", "type": "button", "coordinates": {"x": 1, "y": 2}},
            {"name": "bar", "type": "input", "required_capability": "search"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert len(result) == 2
        assert result[0].name == "btn"
        assert result[0].type == "button"
        assert result[0].coordinates == {"x": 1, "y": 2}
        assert result[1].name == "bar"
        assert result[1].required_capability == ApplicationCapability.SEARCH

    def test_none_input_returns_empty(self):
        assert ApplicationManager._reconstruct_ui_elements(None) == []

    def test_non_list_input_returns_empty(self):
        assert ApplicationManager._reconstruct_ui_elements("not a list") == []
        assert ApplicationManager._reconstruct_ui_elements(42) == []

    def test_empty_list_returns_empty(self):
        assert ApplicationManager._reconstruct_ui_elements([]) == []

    def test_non_dict_items_skipped(self):
        data = ["string_item", 42, None, {"name": "valid", "type": "button"}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_item_missing_name_skipped(self):
        data = [{"type": "button"}, {"name": "ok", "type": "input"}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert len(result) == 1
        assert result[0].name == "ok"

    def test_item_missing_type_skipped(self):
        data = [{"name": "btn"}, {"name": "ok", "type": "input"}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert len(result) == 1
        assert result[0].name == "ok"

    def test_invalid_capability_becomes_none(self):
        data = [{"name": "btn", "type": "button", "required_capability": "nonexistent"}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert len(result) == 1
        assert result[0].required_capability is None

    def test_none_capability_stays_none(self):
        data = [{"name": "btn", "type": "button", "required_capability": None}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert result[0].required_capability is None

    def test_screen_defaults_to_zero(self):
        data = [{"name": "btn", "type": "button"}]
        result = ApplicationManager._reconstruct_ui_elements(data)
        assert result[0].screen == 0

    def test_all_fields_preserved(self):
        data = [{
            "name": "btn", "type": "button",
            "coordinates": {"x": 5, "y": 10},
            "screen": 3,
            "calibration_data": {"c": 1},
            "required_capability": "click",
        }]
        result = ApplicationManager._reconstruct_ui_elements(data)
        el = result[0]
        assert el.coordinates == {"x": 5, "y": 10}
        assert el.screen == 3
        assert el.calibration_data == {"c": 1}
        assert el.required_capability == ApplicationCapability.CLICK


# ---------------------------------------------------------------------------
# 3. _reconstruct_states
# ---------------------------------------------------------------------------

class TestReconstructStates:
    """Verifica la reconstruccion robusta de ApplicationState desde strings."""

    def test_valid_states_reconstructed(self):
        data = ["closed", "open", "active"]
        result = ApplicationManager._reconstruct_states(data)
        assert result == [
            ApplicationState.CLOSED,
            ApplicationState.OPEN,
            ApplicationState.ACTIVE,
        ]

    def test_none_input_returns_default_closed(self):
        result = ApplicationManager._reconstruct_states(None)
        assert result == [ApplicationState.CLOSED]

    def test_non_list_input_returns_default_closed(self):
        assert ApplicationManager._reconstruct_states("closed") == [ApplicationState.CLOSED]
        assert ApplicationManager._reconstruct_states(42) == [ApplicationState.CLOSED]

    def test_empty_list_returns_default_closed(self):
        assert ApplicationManager._reconstruct_states([]) == [ApplicationState.CLOSED]

    def test_invalid_state_skipped(self):
        result = ApplicationManager._reconstruct_states(["closed", "bogus", "open"])
        assert result == [ApplicationState.CLOSED, ApplicationState.OPEN]

    def test_all_invalid_returns_default_closed(self):
        result = ApplicationManager._reconstruct_states(["bogus1", "bogus2"])
        assert result == [ApplicationState.CLOSED]

    def test_non_string_items_skipped(self):
        result = ApplicationManager._reconstruct_states(["open", 42, None, True])
        assert result == [ApplicationState.OPEN]

    def test_case_insensitive(self):
        result = ApplicationManager._reconstruct_states(["OPEN", "Closed"])
        assert result == [ApplicationState.OPEN, ApplicationState.CLOSED]

    def test_error_state_reconstructed(self):
        result = ApplicationManager._reconstruct_states(["error"])
        assert result == [ApplicationState.ERROR]


# ---------------------------------------------------------------------------
# 4. _reconstruct_application: ui_elements / states desde Entity.properties
# ---------------------------------------------------------------------------

class TestReconstructApplicationWithUIElementsAndStates:
    """Verifica que _reconstruct_application materializa ui_elements y states."""

    def test_reconstruct_with_ui_elements(self):
        entity = _entity_with_ui_states()
        manager = _make_min_manager()
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert len(app.ui_elements) == 2
        assert app.ui_elements[0].name == "search_bar"
        assert app.ui_elements[0].coordinates == {"x": 100, "y": 200}
        assert app.ui_elements[0].screen == 1
        assert app.ui_elements[0].calibration_data == {"conf": 0.9}
        assert app.ui_elements[0].required_capability == ApplicationCapability.SEARCH
        assert app.ui_elements[1].name == "play_button"
        assert app.ui_elements[1].coordinates == {"x": 300, "y": 400}
        assert app.ui_elements[1].screen == 2
        assert app.ui_elements[1].required_capability is None

    def test_reconstruct_with_states(self):
        entity = _entity_with_ui_states()
        manager = _make_min_manager()
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.states == [
            ApplicationState.CLOSED,
            ApplicationState.OPEN,
            ApplicationState.ACTIVE,
        ]

    def test_reconstruct_without_ui_elements_uses_default(self):
        """Entity sin ui_elements en properties -> default []."""
        manager = _make_min_manager()
        app = manager._reconstruct_application(_entity_legacy())
        assert app is not None
        assert app.ui_elements == []

    def test_reconstruct_without_states_uses_default_closed(self):
        """Entity sin states en properties -> default [CLOSED]."""
        manager = _make_min_manager()
        app = manager._reconstruct_application(_entity_legacy())
        assert app is not None
        assert app.states == [ApplicationState.CLOSED]

    def test_reconstruct_full_app_presists_all_fields(self):
        entity = _entity_with_ui_states()
        manager = _make_min_manager()
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "TestApp"
        assert app.type == "browser"
        assert app.executable == "test.exe"
        assert app.url == "https://test.example"
        assert app.login_required is False
        assert len(app.capabilities) == 2
        assert [c.capability.value for c in app.capabilities] == ["open", "navigate"]
        assert len(app.ui_elements) == 2
        assert len(app.states) == 3
        assert app.metadata["entity_id"] == "app_testapp"

    def test_reconstruct_capabilities_uses_minimal_defaults(self):
        """Las capabilities reconstruidas usan defaults minimos (cost=5.0, empty)."""
        entity = _entity_with_ui_states()
        manager = _make_min_manager()
        app = manager._reconstruct_application(entity)
        assert app is not None
        cap = app.capabilities[0]
        assert cap.capability == ApplicationCapability.OPEN
        assert cap.cost == 5.0
        assert cap.name == "cap_open"


# ---------------------------------------------------------------------------
# 5. register_application: persiste ui_elements y states
# ---------------------------------------------------------------------------

class TestRegisterApplicationPersistsUIElementsAndStates:
    """Verifica que register_application escribe ui_elements/states en properties."""

    def test_register_persists_ui_elements(self):
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="PersistApp", type="browser",
            ui_elements=[
                UIElement(name="btn", type="button",
                          required_capability=ApplicationCapability.OPEN),
            ],
            states=[ApplicationState.OPEN, ApplicationState.ACTIVE],
        )
        manager.register_application(app)
        entity = manager.memory_manager._entities[-1]
        props = entity.properties
        assert "ui_elements" in props
        assert "states" in props
        assert len(props["ui_elements"]) == 1
        assert props["ui_elements"][0]["name"] == "btn"
        assert props["ui_elements"][0]["required_capability"] == "open"
        assert props["states"] == ["open", "active"]

    def test_register_empty_ui_elements_defaults(self):
        """App con defaults (ui_elements=[], states=[CLOSED]) se persiste."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(name="EmptyApp", type="browser", executable="x")
        manager.register_application(app)
        entity = manager.memory_manager._entities[-1]
        props = entity.properties
        assert props["ui_elements"] == []
        assert props["states"] == [ApplicationState.CLOSED.value]

    def test_register_saves_entity_to_memory(self):
        manager = _make_min_manager()
        app = ApplicationKnowledge(name="SaveApp", type="browser", executable="x")
        assert manager.register_application(app) is True
        assert len(manager.memory_manager._entities) == 1
        assert manager.memory_manager._entities[-1].id == "app_saveapp"

    def test_register_entity_properties_keys_count_is_seven(self):
        """register_application escribe exactamente 7 claves en Entity.properties."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(name="CountApp", type="browser", executable="x")
        manager.register_application(app)
        entity = manager.memory_manager._entities[-1]
        assert set(entity.properties.keys()) == {
            "type", "executable", "url", "login_required",
            "capabilities", "ui_elements", "states",
        }

    def test_register_app_added_to_internal_dict(self):
        """register_application también registra la app en memoria interna."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(name="CacheApp", type="browser")
        manager.register_application(app)
        assert "cacheapp" in manager.applications


# ---------------------------------------------------------------------------
# 6. Round-trip: register -> entity -> _load_custom_applications -> reconstruct
# ---------------------------------------------------------------------------

class TestRoundTripRegisterLoad:
    """Round-trip completo: register_application persiste, luego _load_custom_applications
    reconstruye con ui_elements y states preservados."""

    def test_round_trip_preserves_ui_elements(self):
        manager = _make_min_manager()
        original = ApplicationKnowledge(
            name="RoundTripApp", type="browser", executable="rt.exe",
            url="https://rt.example",
            ui_elements=[
                UIElement(
                    name="btn", type="button",
                    coordinates={"x": 10, "y": 20},
                    required_capability=ApplicationCapability.CLICK,
                ),
            ],
            states=[ApplicationState.OPEN, ApplicationState.ACTIVE],
        )
        manager.register_application(original)
        # Simulate fresh load: clear in-memory apps
        manager.applications = {}
        manager._load_custom_applications()

        loaded = manager.get_application("RoundTripApp")
        assert loaded is not None
        assert len(loaded.ui_elements) == 1
        assert loaded.ui_elements[0].name == "btn"
        assert loaded.ui_elements[0].coordinates == {"x": 10, "y": 20}
        assert loaded.ui_elements[0].required_capability == ApplicationCapability.CLICK
        assert loaded.states == [ApplicationState.OPEN, ApplicationState.ACTIVE]

    def test_round_trip_preserves_capabilities_as_strings(self):
        manager = _make_min_manager()
        original = ApplicationKnowledge(
            name="CapRoundTrip", type="browser",
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_app", description="d",
                    required_ui_elements=[], preconditions=[], effects=[],
                    cost=1.0,
                ),
            ],
        )
        manager.register_application(original)
        manager.applications = {}
        manager._load_custom_applications()

        loaded = manager.get_application("CapRoundTrip")
        assert loaded is not None
        cap_values = [c.capability.value for c in loaded.capabilities]
        assert cap_values == ["open"]

    def test_round_trip_multiple_apps_no_collision(self):
        manager = _make_min_manager()
        for nm in ["AlphaApp", "BetaApp"]:
            manager.register_application(
                ApplicationKnowledge(
                    name=nm, type="browser", executable=nm.lower(),
                    ui_elements=[UIElement(name="btn", type="button")],
                    states=[ApplicationState.OPEN],
                )
            )
        manager.applications = {}
        manager._load_custom_applications()

        alpha = manager.get_application("AlphaApp")
        beta = manager.get_application("BetaApp")
        assert alpha is not None and beta is not None
        assert alpha.executable == "alphaapp"
        assert beta.executable == "betaapp"

    def test_round_trip_legacy_entity_gets_defaults(self):
        """Legacy entity (sin ui_elements/states) -> defaults al reconstruir."""
        manager = _make_min_manager()
        manager.memory_manager.save_entity(_entity_legacy())
        manager._load_custom_applications()

        loaded = manager.get_application("LegacyApp")
        assert loaded is not None
        assert loaded.ui_elements == []
        assert loaded.states == [ApplicationState.CLOSED]


# ---------------------------------------------------------------------------
# 7. Integracion: carga del conjunto completo con MemoryManager real
# ---------------------------------------------------------------------------

class TestLoadFullApplicationSet:
    """Carga las 32 aplicaciones reales de entities.json con MemoryManager real
    en sandbox (tmp_path). Verifica que el conjunto se materializa con
    defaults para ui_elements/states (legacy format)."""

    MEM_ENTITIES_PATH = None  # set en fixture

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from src.utils.config import get_project_root
        real = get_project_root() / "data" / "memory" / "entities.json"
        shutil.copy(real, tmp_path / "entities.json")
        self._tmp = tmp_path

    def _make_manager_with_real_mm(self):
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}
        manager.memory_manager = MemoryManager(self._tmp)
        return manager

    def test_loads_four_applications(self):
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        assert len(manager.applications) == 32

    def test_application_ids_match_real_source(self):
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        assert set(manager.applications.keys()) == {
            "youtube", "spotify", "github", "twitch",
            "brave", "discord", "steam", "epic games launcher",
            "ubisoft connect", "riot client", "obs studio",
            "docker desktop", "visual studio code", "pycharm",
            "intellij idea", "ollama", "plex",
            "teamspeak 3 client", "tlauncher", "overwolf", "outplayed",
            "microsoft teams", "outlook", "microsoft onedrive",
            "windows terminal", "notepad", "calculator", "paint",
            "explorer", "edge", "battle.net", "chrome",
        }

    def test_legacy_apps_get_default_states(self):
        """Entidades legacy (sin states) -> [ApplicationState.CLOSED]."""
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        for app in manager.applications.values():
            assert app.states == [ApplicationState.CLOSED], (
                f"{app.name} deberia tener states=[CLOSED] por defecto"
            )

    def test_legacy_apps_get_empty_ui_elements(self):
        """Entidades legacy (sin ui_elements) -> []."""
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        for app in manager.applications.values():
            assert app.ui_elements == [], (
                f"{app.name} deberia tener ui_elements=[] por defecto"
            )

    def test_all_loaded_apps_are_application_knowledge(self):
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        for app in manager.applications.values():
            assert isinstance(app, ApplicationKnowledge)

    def test_app_specific_properties_preserved(self):
        """Verifica que los campos legacy se preservan tras la reconstruccion."""
        manager = self._make_manager_with_real_mm()
        manager._load_custom_applications()
        yt = manager.applications["youtube"]
        assert yt.executable == "chrome.exe"
        assert yt.url == "https://www.youtube.com"
        assert yt.name == "YouTube"
        sp = manager.applications["spotify"]
        assert sp.executable == "spotify.exe"
        assert sp.url is None  # spotify no tiene url en entities.json real
