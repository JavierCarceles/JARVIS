# -*- coding: utf-8 -*-
"""Tests de implementacion de la lectura de aplicaciones desde entidades
— unidad 3.2.2.1 (FASE 3.2.2 — Carga).

Objetivo: "Implementar o verificar lectura de una aplicacion".

Este modulo implementa y verifica la materializacion de entidades Entity
→ ApplicationKnowledge mediante dos metodos nuevos en ApplicationManager:

1. `_reconstruct_application(entity: Entity) -> Optional[ApplicationKnowledge]`
   Lee una sola Entity y reconstruye un objeto ApplicationKnowledge,
   manejando dos formatos de properties:
   - Formato register_application: {type, executable, url, login_required, capabilities}
   - Formato legacy entities.json: {url, executable, category}

2. `_load_custom_applications()` — implementacion del metodo existente (anteriormente
   un stub vacio con errores de sintaxis), que itera sobre las entities de tipo
   "application" y registra las que no estan ya cargadas, evitando duplicados.

Los tests usan un MemoryManager aislado en tmp_path (sandbox) para evitar tocar
data/ de produccion. No abren aplicaciones, no lanzan procesos, no tests de integracion.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
)
from src.memory.storage import Entity, MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_min_manager():
    """ApplicationManager aislado (bypass __init__) con memory_manager falso.

    Evita registrar Chrome/Spotify y evita toda persistencia a entities.json.
    Ideal para testear _reconstruct_application y _load_custom_applications
    de forma controlada.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def __init__(self):
            self._entities = []

        def set_entities(self, entities):
            self._entities = list(entities)

        def get_entities_by_type(self, t):
            return list(self._entities)

        def save_entity(self, entity):
            return True

    manager.memory_manager = _FakeMemoryManager()
    return manager


def _entity_from_dict(data):
    """Crea un objeto Entity desde un dict (como viene de entities.json)."""
    return Entity.from_dict(data)


def _make_register_entity(name="Chrome", app_type="browser", executable="chrome",
                          url="https://chrome.google.com", login_required=False,
                          capabilities=["open", "navigate"], entity_id=None,
                          aliases=None):
    """Crea una Entity en el FORMATO register_application."""
    if entity_id is None:
        entity_id = f"app_{name.lower()}"
    return _entity_from_dict({
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": {
            "type": app_type,
            "executable": executable,
            "url": url,
            "login_required": login_required,
            "capabilities": capabilities,
        },
        "aliases": aliases or [],
        "tags": [],
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "metadata": None,
    })


def _make_legacy_entity(name="YouTube", category="video_platform", executable="chrome.exe",
                        url="https://youtube.com", entity_id=None, aliases=None,
                        properties_extra=None):
    """Crea una Entity en el FORMATO LEGACY entities.json (properties.category)."""
    if entity_id is None:
        entity_id = name.lower()
    props = {
        "url": url,
        "executable": executable,
        "category": category,
    }
    if properties_extra:
        props.update(properties_extra)
    return _entity_from_dict({
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": props,
        "aliases": aliases or [],
        "tags": [],
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "metadata": None,
    })


# ===========================================================================
# TESTS: _reconstruct_application — mapeo entity → ApplicationKnowledge
# ===========================================================================

class TestReconstructApplication:
    """Verifica _reconstruct_application(entity) con ambos formatos de properties."""

    # --- Formato register_application (properties.type + capabilities) ---

    def test_reconstruct_from_register_application_format(self):
        """Entity con properties.type + capabilities se reconstruye con type y capabilities."""
        manager = _make_min_manager()
        entity = _make_register_entity(
            name="Chrome", app_type="browser",
            executable="chrome", url="https://chrome.google.com",
            login_required=False, capabilities=["open", "navigate"],
        )
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "Chrome"
        assert app.type == "browser"
        assert app.executable == "chrome"
        assert app.url == "https://chrome.google.com"
        assert app.login_required is False

    def test_reconstruct_capabilities_from_register_format(self):
        """Las capabilities como List[str] se convierten a ApplicationCapabilityDef."""
        manager = _make_min_manager()
        entity = _make_register_entity(
            name="App1", capabilities=["open", "close", "search"],
        )
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert len(app.capabilities) == 3
        cap_values = {c.capability for c in app.capabilities}
        assert cap_values == {
            ApplicationCapability.OPEN,
            ApplicationCapability.CLOSE,
            ApplicationCapability.SEARCH,
        }
        for cap_def in app.capabilities:
            assert isinstance(cap_def, ApplicationCapabilityDef)
            assert cap_def.required_ui_elements == []
            assert cap_def.preconditions == []
            assert cap_def.effects == []
            assert cap_def.cost == 5.0

    def test_reconstruct_login_required_true(self):
        """login_required=True se propaga correctamente."""
        manager = _make_min_manager()
        entity = _make_register_entity(name="Spotify", login_required=True)
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.login_required is True

    # --- Formato legacy entities.json (properties.category, sin capabilities) ---

    def test_reconstruct_from_legacy_entity_format(self):
        """Entity con properties.category (sin type) se reconstruye usando category como type."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="YouTube", category="video_platform")
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "YouTube"
        assert app.type == "video_platform"
        assert app.executable == "chrome.exe"
        assert app.url == "https://youtube.com"

    def test_reconstruct_legacy_no_capabilities_empty_list(self):
        """Entity legacy sin capabilities → capabilities lista vacia."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="GitHub", category="development")
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.capabilities == []

    # --- Type fallback: properties.type → properties.category → "application" ---

    def test_reconstruct_type_from_properties_type(self):
        """Cuando properties.type existe, se usa como app.type."""
        manager = _make_min_manager()
        entity = _make_register_entity(name="App1", app_type="browser")
        app = manager._reconstruct_application(entity)
        assert app.type == "browser"

    def test_reconstruct_type_fallback_to_category(self):
        """Si no hay properties.type, se usa properties.category."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="App1", category="streaming")
        app = manager._reconstruct_application(entity)
        assert app.type == "streaming"

    def test_reconstruct_type_defaults_to_application(self):
        """Sin type ni category, type defaults a 'application'."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(
            name="BareApp", properties_extra={"executable": "bare.exe"},
        )
        # Remove category from properties
        raw = entity.to_dict()
        del raw["properties"]["category"]
        entity = _entity_from_dict(raw)
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.type == "application"

    # --- Edge cases: properties nula / no dict ---

    def test_reconstruct_with_none_properties(self):
        """Entity con properties=None no lanza error; type defaults a 'application'."""
        manager = _make_min_manager()
        entity = _entity_from_dict({
            "id": "nullprops", "type": "application", "name": "NullProps",
            "properties": None,
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
            "metadata": None,
        })
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "NullProps"
        assert app.type == "application"
        assert app.executable is None
        assert app.url is None

    def test_reconstruct_with_non_dict_properties(self):
        """Entity con properties como lista (no dict) no lanza error."""
        manager = _make_min_manager()
        entity = _entity_from_dict({
            "id": "listprops", "type": "application", "name": "ListProps",
            "properties": [],
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
            "metadata": None,
        })
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "ListProps"
        assert app.type == "application"
        assert app.capabilities == []

    # --- Capabilities: invalid strings skipped ---

    def test_reconstruct_invalid_capabilities_skipped(self):
        """Capability strings invalidas se omiten sin lanzar error."""
        manager = _make_min_manager()
        entity = _make_register_entity(
            name="App1", capabilities=["open", "INVALID_CAP", "close"],
        )
        app = manager._reconstruct_application(entity)
        assert app is not None
        cap_values = {c.capability for c in app.capabilities}
        assert ApplicationCapability.OPEN in cap_values
        assert ApplicationCapability.CLOSE in cap_values
        assert len(app.capabilities) == 2

    def test_reconstruct_capabilities_case_insensitive(self):
        """Capability strings con mayusculas se normalizan."""
        manager = _make_min_manager()
        entity = _make_register_entity(name="App1", capabilities=["Open", "CLOSE"])
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert len(app.capabilities) == 2

    # --- Missing name fallback ---

    def test_reconstruct_missing_name_uses_id(self):
        """Si entity.name es None, se usa entity.id como nombre."""
        manager = _make_min_manager()
        entity = _entity_from_dict({
            "id": "fallback_id", "type": "application", "name": None,
            "properties": {"type": "browser"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
            "metadata": None,
        })
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert app.name == "fallback_id"

    def test_reconstruct_missing_name_and_id_returns_none(self):
        """Si tanto name como id son None/falsy, reconstruction falla → None."""
        manager = _make_min_manager()
        entity = _entity_from_dict({
            "id": "", "type": "application", "name": None,
            "properties": {"type": "browser"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
            "metadata": None,
        })
        app = manager._reconstruct_application(entity)
        assert app is None

    # --- Metadata: entity_id + aliases ---

    def test_reconstruct_stores_entity_id_in_metadata(self):
        """entity.id se guarda en metadata para trazabilidad."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="App1", entity_id="my_app_id")
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert "entity_id" in app.metadata
        assert app.metadata["entity_id"] == "my_app_id"

    def test_reconstruct_stores_aliases_in_metadata(self):
        """entity.aliases se guardan en metadata para normalizacion futura."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="App1", aliases=["alias1", "alias2"])
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert "aliases" in app.metadata
        assert app.metadata["aliases"] == ["alias1", "alias2"]

    # --- ApplicationKnowledge well-formed ---

    def test_reconstructed_app_has_valid_contract(self):
        """La ApplicationKnowledge reconstruida satisface el contrato minimo (name+type)."""
        manager = _make_min_manager()
        entity = _make_legacy_entity(name="TestApp", category="test")
        app = manager._reconstruct_application(entity)
        assert app is not None
        assert isinstance(app, ApplicationKnowledge)
        assert isinstance(app.name, str) and app.name
        assert isinstance(app.type, str) and app.type
        assert isinstance(app.capabilities, list)
        assert isinstance(app.ui_elements, list)
        assert isinstance(app.states, list)
        assert isinstance(app.metadata, dict)


# ===========================================================================
# TESTS: _load_custom_applications — integracion entity → modelo
# ===========================================================================

class TestLoadCustomApplications:
    """Verifica _load_custom_applications() con entities aisladas en tmp_path."""

    @pytest.fixture
    def manager_with_entities(self, tmp_path):
        """ApplicationManager con entities pre-cargadas en el cache.

        Usa _make_min_manager() (bypass __init__) y un _FakeMemoryManager
        para controlar exactamente que entities devuelve get_entities_by_type.
        """
        manager = _make_min_manager()
        # Pre-populate with Chrome/Spotify (simula _initialize_applications)
        manager.applications["chrome"] = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome")
        manager.applications["spotify"] = ApplicationKnowledge(
            name="Spotify", type="media", executable="spotify")
        return manager

    def test_loads_new_applications_from_entities(self, manager_with_entities):
        """Entities nuevas (no duplicadas) se cargan en self.applications."""
        entity = _make_legacy_entity(name="YouTube", category="video_platform")
        manager_with_entities.memory_manager.set_entities([entity])
        manager_with_entities._load_custom_applications()
        assert "youtube" in manager_with_entities.applications
        app = manager_with_entities.applications["youtube"]
        assert app.name == "YouTube"
        assert app.type == "video_platform"

    def test_loads_multiple_new_applications(self, manager_with_entities):
        """Multiples entities nuevas se cargan todas."""
        entities = [
            _make_legacy_entity(name="YouTube", category="video_platform"),
            _make_legacy_entity(name="GitHub", category="development"),
            _make_legacy_entity(name="Twitch", category="streaming"),
        ]
        manager_with_entities.memory_manager.set_entities(entities)
        manager_with_entities._load_custom_applications()
        assert "youtube" in manager_with_entities.applications
        assert "github" in manager_with_entities.applications
        assert "twitch" in manager_with_entities.applications

    def test_skips_duplicate_applications(self, manager_with_entities):
        """Entities que ya estan registradas (Chrome, Spotify) se omiten."""
        entities = [
            _make_register_entity(name="Chrome", app_type="browser"),
            _make_register_entity(name="Spotify", app_type="media"),
        ]
        manager_with_entities.memory_manager.set_entities(entities)
        before = set(manager_with_entities.applications.keys())
        manager_with_entities._load_custom_applications()
        after = set(manager_with_entities.applications.keys())
        assert before == after == {"chrome", "spotify"}

    def test_skips_duplicates_but_loads_new(self, manager_with_entities):
        """Mezcla de duplicados y nuevas: solo las nuevas se cargan."""
        entities = [
            _make_register_entity(name="Chrome", app_type="browser"),
            _make_legacy_entity(name="YouTube", category="video_platform"),
        ]
        manager_with_entities.memory_manager.set_entities(entities)
        manager_with_entities._load_custom_applications()
        assert "chrome" in manager_with_entities.applications  # pre-existing
        assert "youtube" in manager_with_entities.applications  # loaded

    def test_empty_entities_no_effect(self, manager_with_entities):
        """Sin entities, no se anaden apps."""
        manager_with_entities.memory_manager.set_entities([])
        before = set(manager_with_entities.applications.keys())
        manager_with_entities._load_custom_applications()
        after = set(manager_with_entities.applications.keys())
        assert before == after

    def test_returns_none(self, manager_with_entities):
        """_load_custom_applications devuelve None (void)."""
        result = manager_with_entities._load_custom_applications()
        assert result is None

    def test_no_crash_on_reconstruction_failure(self, manager_with_entities):
        """Entities que fallan en reconstruction no hacen crash; se omiten."""
        bad_entity = _entity_from_dict({
            "id": "", "type": "application", "name": None,
            "properties": {"type": "browser"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
            "metadata": None,
        })
        good_entity = _make_legacy_entity(name="GoodApp", category="test")
        manager_with_entities.memory_manager.set_entities([bad_entity, good_entity])
        manager_with_entities._load_custom_applications()
        # La entity valida se carga, la invalida se omite
        assert "goodapp" in manager_with_entities.applications
        assert "" not in manager_with_entities.applications

    def test_mixed_formats_loaded(self, manager_with_entities):
        """Entities con formato register_application y legacy se cargan ambos."""
        entities = [
            _make_register_entity(name="RegApp", app_type="browser",
                                  capabilities=["open", "search"]),
            _make_legacy_entity(name="LegacyApp", category="media"),
        ]
        manager_with_entities.memory_manager.set_entities(entities)
        manager_with_entities._load_custom_applications()
        assert "regapp" in manager_with_entities.applications
        assert "legacyapp" in manager_with_entities.applications

    def test_non_list_entities_handled(self, manager_with_entities):
        """Si get_entities_by_type devuelve algo que no es lista, no hace nada."""
        manager_with_entities.memory_manager.set_entities("not_a_list")
        # No crash
        result = manager_with_entities._load_custom_applications()
        assert result is None

    def test_capabilities_from_loaded_entity(self, manager_with_entities):
        """Capabilities registradas en la entity se reconstruyen en ApplicationKnowledge."""
        entity = _make_register_entity(
            name="CapApp", capabilities=["open", "navigate", "search"],
        )
        manager_with_entities.memory_manager.set_entities([entity])
        manager_with_entities._load_custom_applications()
        app = manager_with_entities.applications["capapp"]
        assert len(app.capabilities) == 3
        cap_values = {c.capability for c in app.capabilities}
        assert ApplicationCapability.OPEN in cap_values
        assert ApplicationCapability.NAVIGATE in cap_values
        assert ApplicationCapability.SEARCH in cap_values

    def test_repeated_call_no_duplicate(self, manager_with_entities):
        """Llamar _load_custom_applications dos veces no duplica apps."""
        entity = _make_legacy_entity(name="YouTube", category="video_platform")
        manager_with_entities.memory_manager.set_entities([entity])
        manager_with_entities._load_custom_applications()
        manager_with_entities._load_custom_applications()
        assert list(manager_with_entities.applications.keys()).count("youtube") == 1
