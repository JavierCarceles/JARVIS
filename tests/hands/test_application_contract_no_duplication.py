# -*- coding: utf-8 -*-
"""Tests del contrato minimo 3.1.2.4 — verificacion de duplicacion de informacion.

Unidad 3.1.2.4: "Verificar que el contrato no duplique informacion ya existente".

El "contrato minimo" es el modelo `ApplicationKnowledge` (src/hands/applications_core.py:137-166).
La "informacion ya existente" son los sistemas/lugares donde los mismos datos residen
canonicamente:

1. Modelo `Entity` de storage.py:45-91 (id, type, name, properties, created_at,
   updated_at, metadata, aliases, confidence, tags).
2. `register_application` (aplicaciones_core.py:351-375): persiste una Entity derivada
   del ApplicationKnowledge, copiando ciertos campos a `properties`.
3. Fichero de datos `data/knowledge/applications.json` (schema con name, executable,
   capabilities, states, ui_elements, login_required, calibration_needed).
4. `get_application_knowledge` (aplicaciones_core.py:982-1002): serializa de vuelta
   el ApplicationKnowledge a un dict.

Estos tests NO modifican codigo de produccion. Caracterizan el estado actual para
documentar EXACTAMENTE que campos se duplican, cuales se pierden y cuales se
derivan, quedando como base para la decision de modelo canonico (3.1.3).
"""

import dataclasses
import json

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_knowledge,
    get_application_manager,
)
from src.memory.storage import Entity
from src.utils.config import get_project_root


# ---------------------------------------------------------------------------
# Constantes del contrato
# ---------------------------------------------------------------------------

# Los 13 campos del contrato ApplicationKnowledge.
CONTRACT_FIELDS = [f.name for f in dataclasses.fields(ApplicationKnowledge)]

# Los 11 campos opcionales (todos excepto name y type).
OPTIONAL_FIELDS = [f.name for f in dataclasses.fields(ApplicationKnowledge)
                   if f.name not in ("name", "type")]

# Campos opcionales que register_application PERSISTE en Entity.properties
# (duplican el contrato). type es obligatorio, no opcional.
# 3.2.2.2: ui_elements y states ahora se persisten (antes se perdian).
DUPLICATED_OPTIONAL_FIELDS = {
    "executable", "url", "login_required", "capabilities",
    "ui_elements", "states",
}

# Campos opcionales que register_application NO persiste en Entity.properties
# (se pierden al registrar). Heredado de 3.1.2.3 (test_application_optional_data.py:49-53).
# 3.2.2.2: ui_elements y states dejaron de ser 'lost' al pasar al conjunto de
# duplicados arriba.
LOST_OPTIONAL_FIELDS = {
    "icon", "calibration_policy",
    "preflight_requirements", "default_state", "metadata",
}

# Las claves que register_application escribe en Entity.properties.
# 3.2.2.2: ahora incluye ui_elements y states (7 claves en total).
ENTITY_PROPERTIES_KEYS = {
    "type", "executable", "url", "login_required",
    "capabilities", "ui_elements", "states",
}

# Los 10 campos del modelo Entity (storage.py:46-58).
ENTITY_FIELDS = [f.name for f in dataclasses.fields(Entity)]

APPS_JSON_PATH = get_project_root() / "data" / "knowledge" / "applications.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_manager():
    """Crea un ApplicationManager sin __init__ (evita registrar Chrome/Spotify)."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def __init__(self):
            self.saved = []

        def save_entity(self, entity):
            self.saved.append(entity)

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _FakeMemoryManager()
    return manager


def _sample_value(field_name):
    """Valor de ejemplo para un campo opcional, para construir ApplicationKnowledge."""
    samples = {
        "executable": "x",
        "url": "https://x.example",
        "icon": "icon.png",
        "capabilities": [
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN, name="n",
                description="d", required_ui_elements=[], preconditions=[],
                effects=["e"], cost=1.0,
            )
        ],
        "ui_elements": [UIElement(name="btn", type="button")],
        "states": [ApplicationState.OPEN],
        "login_required": True,
        "calibration_policy": ["s1"],
        "preflight_requirements": ["r1"],
        "default_state": ApplicationState.ACTIVE,
        "metadata": {"k": "v"},
    }
    return samples[field_name]


# ---------------------------------------------------------------------------
# 1. Overlap de nombres de campos: contrato vs modelo Entity
# ---------------------------------------------------------------------------

class TestContractFieldOverlapWithEntityModel:
    """Verifica cuales campos del contrato comparten nombre con el modelo Entity."""

    def test_entity_has_10_top_level_fields(self):
        """Entity define 10 campos (storage.py:46-58)."""
        assert ENTITY_FIELDS == [
            "id", "type", "name", "properties", "created_at",
            "updated_at", "metadata", "aliases", "confidence", "tags",
        ]

    def test_contract_has_13_fields(self):
        """ApplicationKnowledge define 13 campos (3.1.2.3 verificado)."""
        assert len(CONTRACT_FIELDS) == 13

    def test_shared_top_level_field_names(self):
        """Campos cuyo nombre aparece tanto en ApplicationKnowledge como en Entity.

        Estos son los puntos de duplicacion de NOMBRE a nivel top-level:
        - `name`: ApplicationKnowledge.name == Entity.name
        - `type`: ApplicationKnowledge.type (categoria de app, ej. 'browser') vs
          Entity.type ('application' — categoria de entidad). El NOMBRE coincide
          aunque el significado sea distinto; register_application duplica el valor
          de app.type dentro de Entity.properties.type.
        - `metadata`: ambos modelos disponen del campo, aunque register_application
          no lo popula (queda None en Entity).
        """
        ak = set(CONTRACT_FIELDS)
        ent = set(ENTITY_FIELDS)
        shared = ak & ent
        assert shared == {"name", "type", "metadata"}

    def test_entity_only_fields_not_in_contract(self):
        """Campos de Entity que NO existen en el contrato (no son duplicacion)."""
        ak = set(CONTRACT_FIELDS)
        ent = set(ENTITY_FIELDS)
        entity_only = ent - ak
        assert entity_only == {"id", "properties", "created_at", "updated_at",
                               "aliases", "confidence", "tags"}

    def test_contract_only_fields_not_in_entity(self):
        """Campos del contrato que NO existen como campo top-level de Entity."""
        ak = set(CONTRACT_FIELDS)
        ent = set(ENTITY_FIELDS)
        contract_only = ak - ent
        assert contract_only == {
            "executable", "url", "icon", "capabilities",
            "ui_elements", "states", "login_required",
            "calibration_policy", "preflight_requirements", "default_state",
        }


# ---------------------------------------------------------------------------
# 2. register_application: campos duplicados en Entity.properties
# ---------------------------------------------------------------------------

class TestRegisterApplicationDuplicatesFields:
    """register_application copia campos del contrato a Entity.properties.

    Verificacion de aplicaciones_core.py:354-368: `entity_data["properties"]`
    contiene exactamente {type, executable, url, login_required, capabilities,
    ui_elements, states}. Estos DUPLICAN los campos homonimos de
    ApplicationKnowledge.
    """

    def test_entity_properties_keys_are_duplicated_contract_fields(self):
        """Las claves de Entity.properties son campos del contrato (duplicacion)."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="DupApp", type="browser",
            executable="dup", url="https://dup.example",
            login_required=True,
            capabilities=[
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.OPEN,
                    name="open_dup", description="d",
                    required_ui_elements=[], preconditions=[], effects=["e"],
                    cost=1.0,
                )
            ],
        )
        manager.register_application(app)

        props = manager.memory_manager.saved[-1].properties
        # Exactamente las 7 claves que register_application escribe en properties
        assert set(props.keys()) == ENTITY_PROPERTIES_KEYS
        # Todas esas claves son campos del contrato (excepto 'type' que se
        # duplica como valor dentro de properties, no como campo top-level)
        assert ENTITY_PROPERTIES_KEYS <= set(CONTRACT_FIELDS) | {"type"}

    def test_entity_properties_keys_count_is_seven(self):
        """register_application escribe exactamente 7 claves en Entity.properties.

        3.2.2.2: ui_elements y states se unen al conjunto persistido, pasando
        de 5 a 7 claves.
        """
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(name="CountApp", type="browser", executable="x")
        manager.register_application(app)
        assert len(manager.memory_manager.saved[-1].properties) == 7

    def test_entity_name_duplicated_from_contract(self):
        """Entity.name es una copia directa de ApplicationKnowledge.name."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(name="NameApp", type="utility", executable="x")
        manager.register_application(app)
        entity = manager.memory_manager.saved[-1]
        assert entity.name == app.name

    def test_entity_id_derived_from_contract_name(self):
        """Entity.id se DERIVA de name (app_{name.lower()}); no es un campo del contrato.

        La derivacion no es duplicacion directa: `id` no existe en ApplicationKnowledge,
        pero codifica el mismo identificador. Verificado para confirmar que `id` no
        es un campo redundante del contrato.
        """
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(name="MyDeriveApp", type="utility")
        manager.register_application(app)
        entity = manager.memory_manager.saved[-1]
        assert entity.id == "app_myderiveapp"
        assert "id" not in CONTRACT_FIELDS

    def test_entity_type_is_entity_category_not_app_type(self):
        """Entity.type='application' (categoria de entidad) difiere de app.type.

        register_application pone app.type dentro de properties.type (duplicacion
        del valor real del contrato), mientras Entity.type top-level es siempre
        'application'. Esto confirma que `type` se duplica con valores distintos
        segun el nivel: no es redundancia inutil sino una division de responsabilidad
        (Entity.type=entidad, properties.type=aplicacion).
        """
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(name="TypeApp", type="browser", executable="x")
        manager.register_application(app)
        entity = manager.memory_manager.saved[-1]
        assert entity.type == "application"          # categoria de entidad (hardcoded)
        assert entity.properties["type"] == "browser"  # duplica app.type del contrato


# ---------------------------------------------------------------------------
# 3. Consistencia de los valores duplicados
# ---------------------------------------------------------------------------

class TestRegisterApplicationValueConsistency:
    """Los valores duplicados deben ser consistentes entre contrato y Entity."""

    def test_duplicated_scalar_values_match(self):
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="CnsApp", type="browser",
            executable="cns", url="https://cns.example",
            login_required=True,
        )
        manager.register_application(app)
        props = manager.memory_manager.saved[-1].properties
        assert props["type"] == app.type
        assert props["executable"] == app.executable
        assert props["url"] == app.url
        assert props["login_required"] == app.login_required

    def test_capabilities_duplicated_as_string_values(self):
        """capabilities se duplica como lista de strings (capability.value),
        mientras el contrato usa List[ApplicationCapabilityDef]. La forma difiere:
        ApplicationCapabilityDef se reduce a su enum value en la Entity."""
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
                ApplicationCapabilityDef(
                    capability=ApplicationCapability.NAVIGATE,
                    name="nav_cap", description="d",
                    required_ui_elements=[], preconditions=[], effects=["e"],
                    cost=2.0,
                ),
            ],
        )
        manager.register_application(app)
        props = manager.memory_manager.saved[-1].properties
        assert props["capabilities"] == ["open", "navigate"]
        # El contrato conserva los objetos completos
        assert [c.capability.value for c in app.capabilities] == ["open", "navigate"]


# ---------------------------------------------------------------------------
# 4. Campos NO duplicados (perdidos) y duplicados por register_application
# ---------------------------------------------------------------------------

class TestRegisterApplicationLostFields:
    """Campos del contrato que register_application NO persiste en la Entity."""

    @pytest.mark.parametrize("field", sorted(LOST_OPTIONAL_FIELDS))
    def test_lost_optional_field_absent_from_entity_properties(self, field):
        """Estos campos opcionales se pierden: no aparecen en Entity.properties."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="LostApp", type="utility",
            **{f: _sample_value(f) for f in OPTIONAL_FIELDS},
        )
        manager.register_application(app)
        props = manager.memory_manager.saved[-1].properties
        assert field not in props, (
            f"El campo '{field}' no deberia estar en Entity.properties "
            f"(register_application lo pierde)."
        )


class TestRegisterApplicationDuplicatedOptionalFields:
    """Campos opcionales que register_application SÍ persiste en Entity.properties
    (duplican el contrato). Complementa 3.1.2.3."""

    @pytest.mark.parametrize("field", sorted(DUPLICATED_OPTIONAL_FIELDS))
    def test_duplicated_optional_field_present_in_properties(self, field):
        """executable, url, login_required y capabilities se duplican en properties."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="DupOptApp", type="browser",
            **{f: _sample_value(f) for f in DUPLICATED_OPTIONAL_FIELDS},
        )
        manager.register_application(app)
        props = manager.memory_manager.saved[-1].properties
        assert field in props, (
            f"El campo opcional '{field}' deberia estar en Entity.properties."
        )

    def test_no_extra_properties_beyond_duplication_set(self):
        """Entity.properties no contiene claves ajenas al conjunto de duplicacion."""
        manager = _make_minimal_manager()
        app = ApplicationKnowledge(
            name="NoExtraApp", type="browser",
            **{f: _sample_value(f) for f in OPTIONAL_FIELDS},
        )
        manager.register_application(app)
        props = manager.memory_manager.saved[-1].properties
        assert set(props.keys()) == ENTITY_PROPERTIES_KEYS


# ---------------------------------------------------------------------------
# 5. Overlap con el fichero de datos applications.json
# ---------------------------------------------------------------------------

class TestContractOverlapWithDataFileSchema:
    """Verifica la superposicion de nombres de campos entre el contrato y
    data/knowledge/applications.json (D2, D5, D6).

    applications.json NO es cargado por ApplicationManager.__init__ (D5); solo se
    consume como dict raw en DomainMemory (conversation.py:170-178). El contrato
    y el fichero coexisten sin adaptador (D6). Estos tests documentan la
    superposicion de nombres y las diferencias de representacion.
    """

    def test_applications_json_exists(self):
        assert APPS_JSON_PATH.exists(), "data/knowledge/applications.json debe existir"

    def test_applications_json_schema_keys(self):
        """Schema de applications.json: name, executable, capabilities, states,
        ui_elements, login_required, calibration_needed (NO `type` top-level)."""
        data = json.loads(APPS_JSON_PATH.read_text())
        chrome = data["chrome"]
        assert "name" in chrome
        assert "executable" in chrome
        assert "capabilities" in chrome
        assert "states" in chrome
        assert "ui_elements" in chrome
        assert "login_required" in chrome
        assert "calibration_needed" in chrome
        # applications.json NO tiene 'type' como clave del app
        assert "type" not in chrome

    def test_contract_field_names_overlapping_with_applications_json(self):
        """Campos del contrato cuyo nombre tambien aparece en applications.json."""
        data = json.loads(APPS_JSON_PATH.read_text())
        chrome = data["chrome"]
        ak = set(CONTRACT_FIELDS)
        json_keys = set(chrome.keys())
        shared = ak & json_keys
        # name, executable, capabilities, states, ui_elements, login_required
        assert shared == {"name", "executable", "capabilities",
                          "states", "ui_elements", "login_required"}

    def test_applications_json_has_field_not_in_contract(self):
        """calibration_needed existe en applications.json pero NO en el contrato."""
        data = json.loads(APPS_JSON_PATH.read_text())
        chrome = data["chrome"]
        assert "calibration_needed" in chrome
        assert "calibration_needed" not in CONTRACT_FIELDS

    def test_construction_type_differs_between_contract_and_json(self):
        """El contrato requiere `type` (obligatorio); applications.json no lo tiene.

        Esto confirma D2: el modelo hardcoded (name='Chrome', type='browser') no
        coincide con el JSON (key='chrome', name='Google Chrome', sin type).
        """
        assert "type" in CONTRACT_FIELDS       # el contrato SI tiene type
        data = json.loads(APPS_JSON_PATH.read_text())
        assert "type" not in data["chrome"]    # el JSON NO tiene type


# ---------------------------------------------------------------------------
# 6. Overlap: get_application_knowledge serializa campos del contrato (duplicacion)
# ---------------------------------------------------------------------------

class TestKnowledgeOutputOverlapsContract:
    """get_application_knowledge (aplicaciones_core.py:982-1002) serializa de
    vuelta los campos del contrato a un dict. Verifica cuales se duplican y
    cual cae (icon)."""

    def test_knowledge_output_keys_subset_of_contract(self):
        """Todas las claves devueltas estan en el contrato o son campos calculados
        introducidos por 3.3.2.2 (available, declared_capabilities)."""
        result = get_application_knowledge("chrome")
        assert isinstance(result, dict)
        # 3.3.2.2: get_application_knowledge añade dos campos calculados que no
        # son dataclass fields (no están en CONTRACT_FIELDS): 'available' (runtime
        # availability) y 'declared_capabilities' (lista de capabilities declaradas).
        EXTRA_COMPUTED_KEYS = {"available", "declared_capabilities"}
        assert set(result.keys()) <= set(CONTRACT_FIELDS) | EXTRA_COMPUTED_KEYS

    def test_knowledge_output_drops_icon_field(self):
        """`icon` esta en el contrato pero get_application_knowledge NO lo expone.

        Esto es una duplicacion parcial/incompleta: 12 de 13 campos del contrato
        se reexponen, pero `icon` se pierde en la serializacion (Chrome no lo
        popula -> None). Ademas (3.3.2.2) se añaden 2 campos calculados:
        'available' y 'declared_capabilities'."""
        manager = get_application_manager()
        app = manager.get_application("Chrome")
        assert app is not None
        # El contrato incluye icon
        assert "icon" in CONTRACT_FIELDS
        # Chrome no lo popula -> None
        assert app.icon is None
        # get_application_knowledge no expone icon
        result = get_application_knowledge("chrome")
        assert "icon" not in result
        EXTRA_COMPUTED_KEYS = {"available", "declared_capabilities"}
        assert set(result.keys()) == (set(CONTRACT_FIELDS) - {"icon"}) | EXTRA_COMPUTED_KEYS

    def test_knowledge_output_keys_count(self):
        """get_application_knowledge expone 14 claves (13 - icon + 2 calculados)."""
        result = get_application_knowledge("chrome")
        assert len(result) == 14
