# -*- coding: utf-8 -*-
"""Tests de verificacion del FORMATO REAL de las fuentes de datos de
Application Knowledge - unidad 3.2.1.2 (FASE 3.2.1 - Fuente de datos).

Verifica el formato REAL (no el esperado) de los ficheros/canaux que
alimentan (o no) al modelo Application Knowledge (ApplicationManager):

1. `data/memory/entities.json`: fuente REAL que lee `_load_custom_applications`
   (applications_core.py:510) via `memory_manager.get_entities_by_type("application")`
   (storage.py:718-753, MemoryType.ENTITIES -> "entities.json").
   Formato: lista JSON de entidades Entity.
2. `data/memory/applications.json`: mapeado a MemoryType.APPLICATIONS en
   JSONStorage.file_mapping (storage.py:358) con valor por defecto {}
   (storage.py:566). Fuente declarada pero NO usada por el modelo.
3. `data/knowledge/applications.json`: formato legacy leido por
   conversation.py:172 (DomainKnowledge), con schema DISTINTO al modelo
   ApplicationKnowledge (D5/D6).
4. `register_application` (applications_core.py:351-375): escribe Entity con
   `properties` = {type, executable, url, login_required, capabilities,
   ui_elements, states},
   que NO coincide con el `properties` real de entities.json
   ({url, executable, category}) -> discrepancia D-ENTIDAD-PROPERTIES.

No modifica codigo de produccion. La lectura de ficheros usa rutas absolutas
(get_project_root) y el runtime se verifica con un MemoryManager aislado en tmp_path.
"""

import dataclasses
import json
import shutil

import pytest

from src.hands.applications_core import (
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationCapability,
    ApplicationState,
)
from src.memory.storage import Entity, MemoryType, JSONStorage, MemoryManager
from src.utils.config import get_project_root


# ---------------------------------------------------------------------------
# Rutas absolutas de las fuentes de datos (read-only, no sandbox).
# ---------------------------------------------------------------------------
PROJECT_ROOT = get_project_root()
MEM_ENTITIES_PATH = PROJECT_ROOT / "data" / "memory" / "entities.json"
MEM_APPLICATIONS_PATH = PROJECT_ROOT / "data" / "memory" / "applications.json"
KNOWLEDGE_APPLICATIONS_PATH = PROJECT_ROOT / "data" / "knowledge" / "applications.json"
KNOWLEDGE_ENTITIES_PATH = PROJECT_ROOT / "data" / "knowledge" / "entities.json"

# Los 10 campos del modelo Entity (storage.py:46-58), en orden de declaracion.
ENTITY_FIELDS = [f.name for f in dataclasses.fields(Entity)]

# Los 13 campos del contrato ApplicationKnowledge (applications_core.py:137-152).
CONTRACT_FIELDS = [f.name for f in dataclasses.fields(ApplicationKnowledge)]

# Claves que register_application escribe en Entity.properties (applications_core.py:354-368).
# 3.2.2.2: ui_elements y states se unen al conjunto persistido (antes se perdian).
REGISTER_PROPERTIES_KEYS = {
    "type", "executable", "url", "login_required",
    "capabilities", "ui_elements", "states",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_minimal_manager():
    """ApplicationManager aislado (bypass __init__) con memory_manager falso.

    Evita registrar Chrome/Spotify y evita toda persistencia a entities.json:
    `save_entity` captura la Entity en vez de escribirla. Ideal para
    verificar que register_application construye la Entity con el formato
    real documentado.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _CapturingMemoryManager:
        def __init__(self):
            self.saved = []

        def save_entity(self, entity):
            self.saved.append(entity)

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _CapturingMemoryManager()
    return manager


def _load_real_entities():
    """Carga el contenido raw de data/memory/entities.json (read-only)."""
    return json.loads(MEM_ENTITIES_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Formato real de data/memory/entities.json
# ---------------------------------------------------------------------------
class TestMemoryEntitiesJsonFormat:
    """Verifica el formato REAL de `data/memory/entities.json`, la fuente que
    `_load_custom_applications` consume via get_entities_by_type('application')."""

    def test_file_exists(self):
        assert MEM_ENTITIES_PATH.exists(), "data/memory/entities.json debe existir"

    def test_top_level_is_list(self):
        data = _load_real_entities()
        assert isinstance(data, list), "entities.json es una lista JSON"

    def test_total_entity_count(self):
        data = _load_real_entities()
        # 7 entidades: 3 streamers + 4 applications
        assert len(data) == 7

    def test_application_entity_count(self):
        data = _load_real_entities()
        app_entities = [
            e for e in data
            if isinstance(e, dict) and e.get("type") == "application"
        ]
        assert len(app_entities) == 4

    def test_application_entity_ids(self):
        data = _load_real_entities()
        app_ids = [
            e["id"]
            for e in data
            if isinstance(e, dict) and e.get("type") == "application"
        ]
        assert set(app_ids) == {"youtube", "spotify", "github", "twitch"}

    def test_every_entity_has_all_entity_fields(self):
        data = _load_real_entities()
        for e in data:
            assert isinstance(e, dict)
            for field in ENTITY_FIELDS:
                assert field in e, f"entidad {e.get('id')} carece del campo '{field}'"

    def test_entity_key_order_is_consistent_across_all_entities(self):
        """Todas las entidades reales comparten un unico orden de claves."""
        data = _load_real_entities()
        orders = {tuple(e.keys()) for e in data}
        assert len(orders) == 1
        real_order = list(orders)[0]
        assert list(real_order) == [
            "id", "type", "name", "properties", "aliases", "tags",
            "confidence", "created_at", "updated_at", "metadata",
        ]

    def test_file_key_order_differs_from_dataclass_declaration(self):
        """El orden de claves del JSON difiere del orden de declaracion del
        dataclass Entity (created_at/updated_at/metadata aparecen al final del
        dataclass, pero intercalados tras confidence en el archivo). La lectura
        no depende del orden (Entity.from_dict usa cls(**data)), pero el formato
        real se documenta aqui."""
        data = _load_real_entities()
        first = data[0]
        assert list(first.keys()) != ENTITY_FIELDS  # orden distinto
        assert set(first.keys()) == set(ENTITY_FIELDS)  # mismos campos

    def test_application_entity_properties_keys(self):
        """properties real: {url, executable, category} (NO type/login_required/capabilities)."""
        data = _load_real_entities()
        app_entities = [
            e for e in data
            if isinstance(e, dict) and e.get("type") == "application"
        ]
        all_prop_keys = set()
        for e in app_entities:
            all_prop_keys |= set(e.get("properties", {}).keys())
        assert all_prop_keys == {"url", "executable", "category"}

    def test_spotify_application_has_no_url_property(self):
        """spotify.properties carece de 'url' en los datos reales."""
        data = _load_real_entities()
        spotify = next(
            e for e in data
            if isinstance(e, dict) and e.get("id") == "spotify"
        )
        assert "url" not in spotify["properties"]
        assert "executable" in spotify["properties"]

    def test_entity_from_dict_round_trip(self):
        """Entity.from_dict parsea TODAS las entidades reales sin error."""
        data = _load_real_entities()
        entities = [Entity.from_dict(e) for e in data]
        assert len(entities) == 7
        for ent in entities:
            assert isinstance(ent, Entity)
            assert isinstance(ent.id, str)
            assert isinstance(ent.properties, dict)

    def test_entity_from_dict_preserves_metadata_none(self):
        """metadata: null en JSON se mantiene como None tras from_dict."""
        data = _load_real_entities()
        for e in data:
            ent = Entity.from_dict(e)
            assert ent.metadata is None


# ---------------------------------------------------------------------------
# 2. Runtime: get_entities_by_type("application") sobre los datos reales
# ---------------------------------------------------------------------------
class TestGetEntitiesByTypeRuntime:
    """Verifica el canal real `get_entities_by_type('application')` (storage.py:718)
    sobre una copia de los datos reales, con un MemoryManager aislado."""

    @pytest.fixture
    def isolated_mm(self, tmp_path):
        """MemoryManager aislado en tmp_path con copia de entities.json real."""
        shutil.copy(MEM_ENTITIES_PATH, tmp_path / "entities.json")
        return MemoryManager(tmp_path)

    def test_loads_four_application_entities(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        assert isinstance(entities, list)
        assert len(entities) == 4

    def test_returns_entity_instances(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        for ent in entities:
            assert isinstance(ent, Entity)

    def test_entity_ids_match_real_source(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        ids = {e.id for e in entities}
        assert ids == {"youtube", "spotify", "github", "twitch"}

    def test_entity_names_match_real_source(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        names = {e.name for e in entities}
        assert names == {"YouTube", "Spotify", "GitHub", "Twitch"}

    def test_entity_type_is_application_string(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        for ent in entities:
            assert ent.type == "application"

    def test_entity_properties_structure_preserved(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("application")
        by_id = {e.id: e for e in entities}
        yt = by_id["youtube"]
        assert yt.properties["url"] == "https://www.youtube.com"
        assert yt.properties["executable"] == "chrome.exe"
        assert yt.properties["category"] == "video_platform"
        sp = by_id["spotify"]
        assert "url" not in sp.properties
        assert sp.properties["executable"] == "spotify.exe"

    def test_get_entities_by_type_streamer_returns_three(self, isolated_mm):
        entities = isolated_mm.get_entities_by_type("streamer")
        assert len(entities) == 3
        assert {e.id for e in entities} == {"nissaxter", "shroud", "pokimane"}


# ---------------------------------------------------------------------------
# 3. Formato real de data/memory/applications.json (MemoryType.APPLICATIONS)
# ---------------------------------------------------------------------------
class TestApplicationsMemoryFileFormat:
    """Verifica que `data/memory/applications.json` existe como dict vacio {} y
    esta mapeado a MemoryType.APPLICATIONS, pero NO es usado por ApplicationManager."""

    def test_file_exists(self):
        assert MEM_APPLICATIONS_PATH.exists(), (
            "data/memory/applications.json debe existir"
        )

    def test_top_level_is_dict(self):
        data = json.loads(
            MEM_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        assert isinstance(data, dict)

    def test_content_is_empty_dict(self):
        data = json.loads(
            MEM_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        assert data == {}

    def test_memory_type_applications_maps_to_applications_json(self):
        """JSONStorage.file_mapping mapea MemoryType.APPLICATIONS -> applications.json."""
        storage = JSONStorage(PROJECT_ROOT / "data" / "memory")
        path = storage.get_file_path(MemoryType.APPLICATIONS)
        assert path == MEM_APPLICATIONS_PATH

    def test_default_value_for_applications_is_dict(self):
        storage = JSONStorage(PROJECT_ROOT / "data" / "memory")
        assert storage._get_default_value(MemoryType.APPLICATIONS) == {}

    def test_no_code_reads_applications_via_memory_type(self):
        """Ningun codigo de applications_core.py referencia MemoryType.APPLICATIONS."""
        src = (
            (PROJECT_ROOT / "src" / "hands" / "applications_core.py")
            .read_text(encoding="utf-8")
        )
        assert MemoryType.APPLICATIONS.name not in src
        assert "applications.json" not in src


# ---------------------------------------------------------------------------
# 4. Formato real de data/knowledge/applications.json (legacy, DomainKnowledge)
# ---------------------------------------------------------------------------
class TestKnowledgeApplicationsJsonFormat:
    """Verifica el formato REAL de `data/knowledge/applications.json`, leido por
    conversation.py:172 (DomainKnowledge) con un schema DISTINTO al modelo
    ApplicationKnowledge (D5/D6)."""

    def test_file_exists(self):
        assert KNOWLEDGE_APPLICATIONS_PATH.exists()

    def test_top_level_is_dict(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        assert isinstance(data, dict)

    def test_keys_are_internal_app_names(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        assert set(data.keys()) == {"chrome", "spotify", "vscode", "obs_studio"}

    def test_entry_schema(self):
        """Cada entrada: name, executable, capabilities, states, ui_elements,
        login_required, calibration_needed (NO `type` top-level)."""
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        expected_keys = {
            "name", "executable", "capabilities", "states",
            "ui_elements", "login_required", "calibration_needed",
        }
        assert set(chrome.keys()) == expected_keys
        # No tiene 'type' (obligatorio en ApplicationKnowledge) -> D6
        assert "type" not in chrome

    def test_capabilities_are_string_list(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        assert isinstance(chrome["capabilities"], list)
        assert all(isinstance(c, str) for c in chrome["capabilities"])
        assert "open" in chrome["capabilities"]
        assert "navigate" in chrome["capabilities"]

    def test_ui_elements_are_dict_of_dicts(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        assert isinstance(chrome["ui_elements"], dict)
        address_bar = chrome["ui_elements"]["address_bar"]
        assert set(address_bar.keys()) == {"type", "description"}
        assert address_bar["type"] == "input"

    def test_states_are_dict_of_bool(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        assert isinstance(chrome["states"], dict)
        assert all(isinstance(v, bool) for v in chrome["states"].values())

    def test_calibration_needed_is_string_list(self):
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        assert isinstance(chrome["calibration_needed"], list)
        assert chrome["calibration_needed"] == ["address_bar", "new_tab_button"]

    def test_schema_differs_from_contract(self):
        """El schema de knowledge/applications.json difiere del contrato
        ApplicationKnowledge (calibration_needed vs calibration_policy; states
        Dict vs List; capabilities List[str] vs List[ApplicationCapabilityDef])."""
        data = json.loads(
            KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
        )
        chrome = data["chrome"]
        # knowledge usa 'calibration_needed'
        assert "calibration_needed" in chrome
        assert "calibration_needed" not in CONTRACT_FIELDS
        # el contrato usa 'calibration_policy'
        assert "calibration_policy" in CONTRACT_FIELDS
        # knowledge: states es Dict; contrato: states es List[ApplicationState]
        assert isinstance(chrome["states"], dict)


# ---------------------------------------------------------------------------
# 5. Discrepancia: register_application vs formato real de entities.json
# ---------------------------------------------------------------------------
class TestRegisterApplicationVsRealFormatDiscrepancy:
    """Documenta D-ENTIDAD-PROPERTIES: register_application (aplicaciones_core.py:354)
    escribe Entity.properties = {type, executable, url, login_required,
    capabilities, ui_elements, states},
    pero el formato REAL de entities.json tiene properties = {url, executable, category}.
    Las dos representaciones son INCOMPATIBLES en las claves: _load_custom_applications
    reconstruye ApplicationKnowledge desde la Entity real usando defaults para
    los campos ausentes (3.2.2.2)."""

    def test_register_application_writes_documented_properties_keys(self):
        """register_application persiste exactamente las 7 claves documentadas
        (type, executable, url, login_required, capabilities, ui_elements, states).
        """
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="RegApp", type="browser", executable="reg",
            url="https://reg.example", login_required=True,
        )
        manager.register_application(app)
        entity = manager.memory_manager.saved[-1]
        assert set(entity.properties.keys()) == REGISTER_PROPERTIES_KEYS

    def test_register_application_capabilities_serialized_as_strings(self):
        """capabilities se serializa a List[str] (capability.value)."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="CapApp", type="browser",
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_cap", description="d",
                    required_ui_elements=[], preconditions=[], effects=["e"],
                    cost=1.0,
                ),
            ],
        )
        manager.register_application(app)
        entity = manager.memory_manager.saved[-1]
        assert entity.properties["capabilities"] == ["open"]

    def test_real_entities_properties_differ_from_registered_schema(self):
        """properties REAL de entities.json: {url, executable, category};
        schema de register_application: {type, executable, url, login_required,
        capabilities, ui_elements, states}. La intersecion es solo
        {executable, url}."""
        real_keys = {"url", "executable", "category"}
        registered_keys = REGISTER_PROPERTIES_KEYS
        shared = real_keys & registered_keys
        assert shared == {"executable", "url"}
        # Campos que register_application ESCRIBE pero que NO estan en los datos reales
        assert "type" in registered_keys
        assert "type" not in real_keys
        assert "login_required" in registered_keys
        assert "login_required" not in real_keys
        assert "capabilities" in registered_keys
        assert "capabilities" not in real_keys
        # Campo que esta en los datos reales pero que register_application NO escribe
        assert "category" in real_keys
        assert "category" not in registered_keys

    def test_registered_entity_properties_is_incompatible_with_real(self):
        """Una Entity construida por register_application NO encajaria en el
        formato real de entities.json (le faltan type/login_required/capabilities
        de properties; le sobra category). Confirma la discrepancia de schema."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="RealApp", type="utility", executable="real",
            url="https://real.example",
        )
        manager.register_application(app)
        registered = manager.memory_manager.saved[-1]
        real = _load_real_entities()
        real_sample = next(e for e in real if e["id"] == "youtube")
        assert set(registered.properties.keys()) != set(real_sample["properties"].keys())


# ---------------------------------------------------------------------------
# 6. Discrepancia documental: data/knowledge/entities.json duplicado de
#    data/memory/entities.json (D-KNOWLEDGE-ENTITIES-DUP)
# ---------------------------------------------------------------------------
class TestKnowledgeEntitiesDuplicateFormat:
    """Documenta D-KNOWLEDGE-ENTITIES-DUP: `data/knowledge/entities.json` existe
    con contenido IDENTICO a `data/memory/entities.json`, servido por canales
    distintos (conversation.py:149 vs MemoryManager.get_entities_by_type)."""

    def test_knowledge_entities_file_exists(self):
        assert KNOWLEDGE_ENTITIES_PATH.exists(), (
            "data/knowledge/entities.json debe existir (fuente legacy duplicada)"
        )

    def test_knowledge_entities_equals_memory_entities_content(self):
        """Ambos ficheros contienen la MISMA lista de 7 entidades."""
        knowledge = json.loads(
            KNOWLEDGE_ENTITIES_PATH.read_text(encoding="utf-8")
        )
        memory = _load_real_entities()
        assert knowledge == memory

    def test_knowledge_entities_has_same_application_ids(self):
        knowledge = json.loads(
            KNOWLEDGE_ENTITIES_PATH.read_text(encoding="utf-8")
        )
        app_ids = {
            e["id"] for e in knowledge
            if isinstance(e, dict) and e.get("type") == "application"
        }
        assert app_ids == {"youtube", "spotify", "github", "twitch"}

    def test_contract_states_field_uses_application_state(self):
        """El contrato declara states: Optional[List[ApplicationState]] y
        default_state = ApplicationState.CLOSED (aplicaciones_core.py:147,151).
        Con `from __future__ import annotations`, .type se almacena como cadena.
        Esto contrasta con knowledge/applications.json donde states es
        Dict[str, bool] (D5)."""
        fields = {f.name: f for f in dataclasses.fields(ApplicationKnowledge)}
        states_field = fields["states"]
        assert states_field.type == "Optional[List[ApplicationState]]"
        assert fields["default_state"].default == ApplicationState.CLOSED
