# -*- coding: utf-8 -*-
"""Tests para ApplicationKnowledgeIntegrator (src/hands/planner/application_integration.py).

Verifica que el conocimiento estructurado de aplicaciones se convierte en Nodes
canónicos para el planificador sin tocar código de producción.
"""

import copy
from dataclasses import is_dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.hands.planner.node import Node, NodeType
from src.hands.planner.application_integration import (
    ApplicationKnowledgeIntegrator,
    get_application_knowledge_integrator,
    get_applications_by_capability as legacy_get_apps_by_cap,
    get_application_knowledge as legacy_get_app_knowledge,
)
from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_manager,
)
from src.memory.storage import Entity


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_capability(
    capability: ApplicationCapability = ApplicationCapability.OPEN,
    name: str = "open_app",
    description: str = "Abre la aplicación",
    required_ui_elements=None,
    preconditions=None,
    effects=None,
    cost: float = 10.0,
    **extra,
) -> ApplicationCapabilityDef:
    return ApplicationCapabilityDef(
        capability=capability,
        name=name,
        description=description,
        required_ui_elements=list(required_ui_elements) if required_ui_elements else [],
        preconditions=list(preconditions) if preconditions else [],
        effects=list(effects) if effects else [],
        cost=cost,
        **extra,
    )


def _make_app(
    name: str = "TestApp",
    app_type: str = "utility",
    capabilities=None,
    ui_elements=None,
    states=None,
    login_required: bool = False,
    calibration_policy=None,
    preflight_requirements=None,
    metadata=None,
    **kwargs,
) -> ApplicationKnowledge:
    kwargs.setdefault("name", name)
    kwargs.setdefault("type", app_type)
    kwargs.setdefault("executable", f"{name.lower()}_exe")
    kwargs.setdefault("url", "https://example.com")
    kwargs.setdefault("capabilities", capabilities or [])
    kwargs.setdefault("ui_elements", ui_elements or [])
    kwargs.setdefault("states", states or [ApplicationState.CLOSED])
    kwargs.setdefault("login_required", login_required)
    kwargs.setdefault("calibration_policy", calibration_policy or [])
    kwargs.setdefault("preflight_requirements", preflight_requirements or [])
    kwargs.setdefault("metadata", metadata or {})
    return ApplicationKnowledge(**kwargs)


def _make_integrator_with_manager(manager=None) -> ApplicationKnowledgeIntegrator:
    """Crea una instancia de integrador para testing, inyectando un gestor."""
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager  # puede ser None
    integrator.memory_manager = None
    return integrator


def _make_dict_app(**kwargs):
    """Crea un diccionario que simula ApplicationKnowledge para tests con
    managers basados en dicts."""
    defaults = {
        "name": "DictApp",
        "type": "utility",
        "executable": "dictapp",
        "url": None,
        "capabilities": [],
        "ui_elements": {},
        "states": [],
        "login_required": False,
        "calibration_policy": [],
        "preflight_requirements": [],
        "is_capable": lambda self, cap: False,
        "get_ui_element": lambda self, name: None,
        "get_capability": lambda self, name: None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# STATIC / CLASS METHOD TESTS
# ---------------------------------------------------------------------------

class TestNormalizeName:
    """_normalize_name: normaliza nombres a claves deterministas."""

    def test_basic(self):
        assert ApplicationKnowledgeIntegrator._normalize_name("Hello World") == "hello_world"

    def test_separators_collapsed(self):
        assert ApplicationKnowledgeIntegrator._normalize_name("a---b===c") == "a_b_c"

    def test_strips_whitespace(self):
        assert ApplicationKnowledgeIntegrator._normalize_name("  My App  ") == "my_app"

    def test_empty_string(self):
        assert ApplicationKnowledgeIntegrator._normalize_name("") == ""

    def test_none(self):
        assert ApplicationKnowledgeIntegrator._normalize_name(None) == ""

    def test_unicode_preserved(self):
        # caracteres alfanuméricos Unicode se conservan
        result = ApplicationKnowledgeIntegrator._normalize_name("Café App")
        assert "caf" in result.lower()


class TestAsList:
    """_as_list: normaliza valores a listas sin dividir strings/dicts."""

    def test_none(self):
        assert ApplicationKnowledgeIntegrator._as_list(None) == []

    def test_list_preserves(self):
        assert ApplicationKnowledgeIntegrator._as_list([1, 2, 3]) == [1, 2, 3]

    def test_tuple_to_list(self):
        assert ApplicationKnowledgeIntegrator._as_list((1, 2)) == [1, 2]

    def test_set_to_list(self):
        result = ApplicationKnowledgeIntegrator._as_list({1, 2})
        assert set(result) == {1, 2}

    def test_string_not_split(self):
        assert ApplicationKnowledgeIntegrator._as_list("hello") == ["hello"]

    def test_dict_not_split(self):
        d = {"a": 1}
        assert ApplicationKnowledgeIntegrator._as_list(d) == [d]

    def test_integer(self):
        assert ApplicationKnowledgeIntegrator._as_list(42) == [42]

    def test_generator(self):
        assert ApplicationKnowledgeIntegrator._as_list(iter([1, 2])) == [1, 2]


class TestGetValue:
    """_get_value: lectura unificada de dicts y objetos."""

    def test_dict_hit(self):
        assert ApplicationKnowledgeIntegrator._get_value({"x": 1}, "x", 0) == 1

    def test_dict_miss_default(self):
        assert ApplicationKnowledgeIntegrator._get_value({"x": 1}, "y", 0) == 0

    def test_object_attribute(self):
        obj = MagicMock(x=5)
        assert ApplicationKnowledgeIntegrator._get_value(obj, "x", 0) == 5

    def test_object_attribute_missing_default(self):
        obj = MagicMock(spec=[])
        assert ApplicationKnowledgeIntegrator._get_value(obj, "missing", 99) == 99

    def test_none_object(self):
        assert ApplicationKnowledgeIntegrator._get_value(None, "x", 42) == 42


class TestSafeCopy:
    """_safe_copy: deep copy con fallback."""

    def test_deep_copy_mutable(self):
        original = [{"a": 1}]
        copied = ApplicationKnowledgeIntegrator._safe_copy(original)
        assert copied == original
        assert copied is not original
        assert copied[0] is not original[0]

    def test_immutable_returns_same(self):
        result = ApplicationKnowledgeIntegrator._safe_copy(42)
        assert result == 42

    def test_non_copyable_falls_back(self):
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise TypeError("cannot copy")
            def __copy__(self):
                raise TypeError("cannot copy")

        obj = Uncopyable()
        result = ApplicationKnowledgeIntegrator._safe_copy(obj, default="fallback")
        assert result == "fallback"

    def test_none(self):
        assert ApplicationKnowledgeIntegrator._safe_copy(None) is None


class TestCapabilityValue:
    """_capability_value: obtiene el valor de una capacidad."""

    def test_enum(self):
        result = ApplicationKnowledgeIntegrator._capability_value(ApplicationCapability.OPEN)
        assert result == "open"

    def test_string(self):
        assert ApplicationKnowledgeIntegrator._capability_value("open") == "open"

    def test_dict_with_value(self):
        assert ApplicationKnowledgeIntegrator._capability_value({"value": "click"}) == "click"

    def test_dict_with_value_key(self):
        assert ApplicationKnowledgeIntegrator._capability_value({"value": "click"}) == "click"

    def test_dict_without_value_key_returns_str_repr(self):
        # dicts without 'value' key fall back to str(obj) — caller should
        # extract 'capability' key before calling this method
        result = ApplicationKnowledgeIntegrator._capability_value({"capability": "search"})
        assert result == str({"capability": "search"})

    def test_object_with_value_attr(self):
        obj = MagicMock(value="test_cap")
        assert ApplicationKnowledgeIntegrator._capability_value(obj) == "test_cap"

    def test_none(self):
        assert ApplicationKnowledgeIntegrator._capability_value(None) == ""


class TestCapabilityKey:
    """_capability_key: normaliza el valor de capacidad."""

    def test_basic(self):
        assert ApplicationKnowledgeIntegrator._capability_key("Open App") == "open_app"

    def test_enum(self):
        assert ApplicationKnowledgeIntegrator._capability_key(ApplicationCapability.OPEN) == "open"


class TestNormalizedConditions:
    """_normalized_conditions: copia de precondiciones/efectos."""

    def test_strings(self):
        result = ApplicationKnowledgeIntegrator._normalized_conditions(["a", "b"])
        assert result == ["a", "b"]

    def test_filters_none(self):
        result = ApplicationKnowledgeIntegrator._normalized_conditions(["a", None, "b"])
        assert result == ["a", "b"]

    def test_non_list_input(self):
        result = ApplicationKnowledgeIntegrator._normalized_conditions("single")
        assert result == ["single"]

    def test_dicts_are_distinct_copies(self):
        original = [{"x": 1}]
        result = ApplicationKnowledgeIntegrator._normalized_conditions(original)
        assert result[0] == {"x": 1}
        assert result[0] is not original[0]


class TestUniqueNodes:
    """_unique_nodes: deduplicación por ID con fusión de metadata."""

    def test_dedup_by_id(self):
        n1 = Node(id="a", type=NodeType.ACTION, name="a1")
        n2 = Node(id="a", type=NodeType.ACTION, name="a2")  # mismo ID
        n3 = Node(id="b", type=NodeType.ACTION, name="b1")
        result = ApplicationKnowledgeIntegrator._unique_nodes([n1, n2, n3])
        ids = [n.id for n in result]
        assert ids == ["a", "b"]

    def test_skips_nodes_without_id(self):
        n1 = Node(id="a", type=NodeType.ACTION, name="a1")
        n_empty = Node(id="", type=NodeType.ACTION, name="empty")
        result = ApplicationKnowledgeIntegrator._unique_nodes([n1, n_empty])
        assert len(result) == 1
        assert result[0].id == "a"

    def test_merges_required_by_capabilities(self):
        n1 = Node(id="x", type=NodeType.UI_ELEMENT, name="x1",
                  metadata={"required_by_capabilities": ["cap_a"]})
        n2 = Node(id="x", type=NodeType.UI_ELEMENT, name="x2",
                  metadata={"required_by_capabilities": ["cap_b"]})
        result = ApplicationKnowledgeIntegrator._unique_nodes([n1, n2])
        assert len(result) == 1
        providers = result[0].metadata.get("required_by_capabilities", [])
        assert "cap_a" in providers
        assert "cap_b" in providers


# ---------------------------------------------------------------------------
# INSTANCIA: _get_application
# ---------------------------------------------------------------------------

class TestGetApplication:
    """_get_application: resolución de aplicación."""

    def test_none_manager(self):
        integrator = _make_integrator_with_manager(None)
        assert integrator._get_application("chrome") is None

    def test_found_via_getter(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = integrator._get_application("chrome")
        assert app is not None
        assert app.name == "Chrome"

    def test_found_via_dict(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = integrator._get_application("spotify")
        assert app is not None
        assert app.name == "Spotify"

    def test_not_found(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator._get_application("nonexistent") is None

    def test_empty_name(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator._get_application("") is None

    def test_alias_resolution(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = integrator._get_application("google chrome")
        assert app is not None
        assert app.name == "Chrome"


# ---------------------------------------------------------------------------
# INSTANCIA: convert_application_to_nodes
# ---------------------------------------------------------------------------

class TestConvertApplicationToNodes:
    """convert_application_to_nodes: conversión declarativa a Nodes."""

    def test_chrome_nodes(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        assert len(nodes) >= 4  # app + capabilities + ui_elements
        ids = [n.id for n in nodes]
        assert "app_chrome" in ids

    def test_node_types_present(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        types = {n.type for n in nodes}
        assert NodeType.APPLICATION in types

    def test_nonexistent_app_returns_empty(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.convert_application_to_nodes("nonexistent") == []

    def test_deduplication_ui_element(self):
        """Un elemento UI requerido por dos capacidades debe aparecer una sola vez."""
        app = _make_app(
            name="DupApp",
            capabilities=[
                _make_capability(ApplicationCapability.NAVIGATE, "nav", required_ui_elements=["shared_elem"]),
                _make_capability(ApplicationCapability.SEARCH, "search", required_ui_elements=["shared_elem"]),
            ],
            ui_elements=[UIElement(name="shared_elem", type="input")],
        )
        manager = ApplicationManager()
        manager.register_application(app)
        integrator = _make_integrator_with_manager(manager)
        nodes = integrator.convert_application_to_nodes("dupapp")
        shared = [n for n in nodes if n.id == "dupapp_shared_elem"]
        assert len(shared) == 1

    def test_hierarchy_parent_children(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        node_map = {n.id: n for n in nodes}
        app_node = node_map["app_chrome"]
        # ALL capability IDs are children of the app node
        assert "chrome_open" in app_node.children
        assert "chrome_navigate" in app_node.children
        assert "chrome_search" in app_node.children
        nav_node = node_map.get("chrome_navigate")
        assert nav_node is not None
        assert nav_node.parent == "app_chrome"
        # UI elements have parent = app node, but capability node children include them
        addr_node = node_map.get("chrome_address_bar")
        assert addr_node is not None
        assert addr_node.parent == "app_chrome"
        assert "chrome_address_bar" in nav_node.children

    def test_capability_node_has_preconditions(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        nav_node = next((n for n in nodes if n.id == "chrome_navigate"), None)
        assert nav_node is not None
        # debe incluir la precondicion de aplicacion abierta
        assert "chrome_open" in nav_node.preconditions

    def test_ui_element_node_has_availability_effect(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        addr_node = next((n for n in nodes if n.id == "chrome_address_bar"), None)
        assert addr_node is not None
        assert addr_node.type == NodeType.UI_ELEMENT
        # efecto de disponibilidad del elemento
        assert "chrome_address_bar_available" in addr_node.effects

    def test_capability_node_is_reusable(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        nav_node = next((n for n in nodes if n.id == "chrome_navigate"), None)
        assert nav_node is not None
        assert nav_node.reusable_action is True

    def test_capability_node_action_category(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("chrome")
        nav_node = next((n for n in nodes if n.id == "chrome_navigate"), None)
        assert nav_node is not None
        assert nav_node.action_category == "application_capability"

    def test_no_capabilities_app(self):
        app = _make_app(name="NoCaps", capabilities=[])
        manager = ApplicationManager()
        manager.register_application(app)
        integrator = _make_integrator_with_manager(manager)
        nodes = integrator.convert_application_to_nodes("nocaps")
        assert len(nodes) == 1  # solo el nodo de aplicación
        assert nodes[0].type == NodeType.APPLICATION


# ---------------------------------------------------------------------------
# INSTANCIA: _create_application_node
# ---------------------------------------------------------------------------

class TestCreateApplicationNode:
    """_create_application_node: estructura del nodo de aplicación."""

    def test_node_structure(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        node = integrator._create_application_node(
            get_application_manager().get_application("chrome")
        )
        assert node.id == "app_chrome"
        assert node.type == NodeType.APPLICATION
        assert node.name == "Chrome"
        assert node.cost == 5.0

    def test_parameters(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        node = integrator._create_application_node(app)
        params = node.parameters
        assert params["executable"] == "chrome"
        assert params["login_required"] is False
        assert "calibration_policy" in params

    def test_effects_app_available(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        node = integrator._create_application_node(app)
        assert "chrome_available" in node.effects

    def test_metadata_source(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        node = integrator._create_application_node(app)
        assert node.metadata["source"] == "application_knowledge"
        assert node.metadata["application_type"] == "browser"

    def test_preflight_requirements_in_preconditions(self):
        app = _make_app(
            name="PreApp",
            preflight_requirements=["req_a", "req_b", "req_a"],  # duplicado
        )
        integrator = _make_integrator_with_manager(None)
        node = integrator._create_application_node(app)
        assert "req_a" in node.preconditions
        assert "req_b" in node.preconditions
        # deduplicado
        assert node.preconditions.count("req_a") == 1


# ---------------------------------------------------------------------------
# INSTANCIA: _create_capability_node
# ---------------------------------------------------------------------------

class TestCreateCapabilityNode:
    """_create_capability_node: estructura del nodo de capacidad."""

    def test_node_structure(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[0]  # OPEN
        node = integrator._create_capability_node(app, cap_def)
        assert node.id == "chrome_open"
        assert node.type == NodeType.ACTION
        assert node.name == "open_chrome"

    def test_app_open_precondition_added(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[1]  # NAVIGATE (navigate_to_url)
        node = integrator._create_capability_node(app, cap_def)
        assert "chrome_open" in node.preconditions

    def test_ui_element_availability_precondition(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[1]  # NAVIGATE, requires address_bar
        node = integrator._create_capability_node(app, cap_def)
        assert "chrome_address_bar_available" in node.preconditions

    def test_cost_fallback(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[0]  # OPEN, cost=10
        node = integrator._create_capability_node(app, cap_def)
        assert node.cost == 10.0

    def test_cost_invalid_fallback(self):
        app = _make_app(
            name="CostApp",
            capabilities=[_make_capability(ApplicationCapability.OPEN, "oc", cost="invalid")],
        )
        integrator = _make_integrator_with_manager(None)
        node = integrator._create_capability_node(app, app.capabilities[0])
        assert node.cost == 1.0  # fallback


# ---------------------------------------------------------------------------
# INSTANCIA: _create_ui_element_node
# ---------------------------------------------------------------------------

class TestCreateUIElementNode:
    """_create_ui_element_node: nodos de elementos UI."""

    def test_element_found_type(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[1]  # NAVIGATE, requires address_bar
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert node.type == NodeType.UI_ELEMENT
        assert node.metadata["known"] is True

    def test_element_not_found_type(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[0]  # OPEN, no ui elements
        node = integrator._create_ui_element_node(app, "nonexistent_elem", cap_def)
        assert node.type == NodeType.RESOURCE
        assert node.metadata["known"] is False

    def test_uncalibrated_element_no_calibration_precondition(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("chrome")
        cap_def = app.capabilities[1]
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        # address_bar has no coordinates -> not calibrated
        assert node.metadata["calibrated"] is False
        # no calibration precondition/effect
        assert "_calibrated" not in " ".join(str(p) for p in node.preconditions)

    def test_calibrated_element(self):
        elem = UIElement(name="btn", type="button", coordinates={"x": 10, "y": 20})
        app = _make_app(
            name="CalApp",
            capabilities=[_make_capability(ApplicationCapability.NAVIGATE, "nav", required_ui_elements=["btn"])],
            ui_elements=[elem],
        )
        integrator = _make_integrator_with_manager(None)
        node = integrator._create_ui_element_node(app, "btn", app.capabilities[0])
        assert node.metadata["calibrated"] is True
        assert "calapp_btn_calibrated" in node.preconditions
        assert "calapp_btn_calibrated" in node.effects


# ---------------------------------------------------------------------------
# INSTANCIA: _is_element_calibrated
# ---------------------------------------------------------------------------

class TestIsElementCalibrated:
    """_is_element_calibrated: detección de calibración."""

    def test_none_element(self):
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(None) is False

    def test_callable_method(self):
        elem = UIElement(name="btn", type="button")
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem) is False

        elem_cal = UIElement(name="btn", type="button", coordinates={"x": 1, "y": 2})
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem_cal) is True

    def test_dict_with_callable(self):
        elem = {"is_calibrated": lambda: True}
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem) is True

    def test_dict_with_value(self):
        elem = {"is_calibrated": True}
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem) is True

    def test_dict_without_is_calibrated_uses_calibrated_key(self):
        elem = {"calibrated": True}
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem) is True

    def test_dict_no_keys(self):
        elem = {}
        assert ApplicationKnowledgeIntegrator._is_element_calibrated(elem) is False


# ---------------------------------------------------------------------------
# INSTANCIA: _get_application_current_state
# ---------------------------------------------------------------------------

class TestGetCurrentState:
    """_get_application_current_state: obtención de estado persistido."""

    def test_none_manager(self):
        integrator = _make_integrator_with_manager(None)
        assert integrator._get_application_current_state("chrome") == {}

    def test_entity_found(self):
        mock_mm = MagicMock()
        mock_entity = MagicMock()
        mock_entity.properties = {"foo": "bar"}
        mock_mm.get_entity.return_value = mock_entity
        integrator = _make_integrator_with_manager(get_application_manager())
        integrator.memory_manager = mock_mm
        result = integrator._get_application_current_state("chrome")
        assert result == {"foo": "bar"}

    def test_entity_not_found(self):
        mock_mm = MagicMock()
        mock_mm.get_entity.return_value = None
        integrator = _make_integrator_with_manager(get_application_manager())
        integrator.memory_manager = mock_mm
        assert integrator._get_application_current_state("chrome") == {}

    def test_non_dict_properties(self):
        mock_mm = MagicMock()
        mock_entity = MagicMock()
        mock_entity.properties = "not_a_dict"
        mock_mm.get_entity.return_value = mock_entity
        integrator = _make_integrator_with_manager(get_application_manager())
        integrator.memory_manager = mock_mm
        assert integrator._get_application_current_state("chrome") == {}


# ---------------------------------------------------------------------------
# INSTANCIA: _generate_application_preconditions / _effects
# ---------------------------------------------------------------------------

class TestGeneratePreconditions:
    """_generate_application_preconditions: generación de precondiciones."""

    def test_string_requirements_deduped(self):
        app = _make_app(
            name="PreApp2",
            preflight_requirements=["a", "b", "a", ""],
        )
        integrator = _make_integrator_with_manager(None)
        result = integrator._generate_application_preconditions(app, {})
        assert "a" in result
        assert "b" in result
        assert result.count("a") == 1
        assert "" not in result

    def test_dict_requirements(self):
        app = _make_app(
            name="DictPreApp",
            preflight_requirements=[{"type": "state", "key": "ready"}],
        )
        integrator = _make_integrator_with_manager(None)
        result = integrator._generate_application_preconditions(app, {})
        assert {"type": "state", "key": "ready"} in result

    def test_non_string_non_dict_passes_through(self):
        app = _make_app(
            name="MixedPreApp",
            preflight_requirements=[123],
        )
        integrator = _make_integrator_with_manager(None)
        result = integrator._generate_application_preconditions(app, {})
        assert 123 in result

    def test_empty_requirements(self):
        app = _make_app(name="EmptyPreApp", preflight_requirements=[])
        integrator = _make_integrator_with_manager(None)
        assert integrator._generate_application_preconditions(app, {}) == []


class TestGenerateApplicationEffects:
    """_generate_application_effects: efectos declarativos."""

    def test_effect_contains_app_key(self):
        app = _make_app(name="EffectApp")
        integrator = _make_integrator_with_manager(None)
        effects = integrator._generate_application_effects(app)
        assert "effectapp_available" in effects

    def test_empty_name(self):
        app = _make_app(name="")
        integrator = _make_integrator_with_manager(None)
        effects = integrator._generate_application_effects(app)
        assert "application_available" in effects


# ---------------------------------------------------------------------------
# INSTANCIA: _validate_node_references
# ---------------------------------------------------------------------------

class TestValidateNodeReferences:
    """_validate_node_references: validación de referencias jerárquicas."""

    def test_valid_references(self, caplog):
        n1 = Node(id="app", type=NodeType.APPLICATION, name="app", children=["child1"])
        n2 = Node(id="child1", type=NodeType.UI_ELEMENT, name="child1", parent="app")
        integrator = _make_integrator_with_manager(None)
        # no debe lanzar
        integrator._validate_node_references([n1, n2])

    def test_missing_parent_logs_warning(self, caplog):
        n = Node(id="orphan", type=NodeType.UI_ELEMENT, name="o", parent="missing_parent")
        integrator = _make_integrator_with_manager(None)
        with caplog.at_level("WARNING"):
            integrator._validate_node_references([n])
        assert "Parent" in caplog.text or "parent" in caplog.text

    def test_missing_child_logs_warning(self, caplog):
        n = Node(id="parent", type=NodeType.APPLICATION, name="p", children=["missing_child"])
        integrator = _make_integrator_with_manager(None)
        with caplog.at_level("WARNING"):
            integrator._validate_node_references([n])
        assert "Child" in caplog.text or "child" in caplog.text


# ---------------------------------------------------------------------------
# INSTANCIA: métodos de consulta
# ---------------------------------------------------------------------------

class TestQueryGetApplicationsByCapability:
    """get_applications_by_capability: consulta de aplicaciones por capacidad."""

    def test_none_manager(self):
        integrator = _make_integrator_with_manager(None)
        assert integrator.get_applications_by_capability(ApplicationCapability.OPEN) == []

    def test_real_query_open(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_applications_by_capability(ApplicationCapability.OPEN)
        assert isinstance(result, list)
        assert len(result) >= 2  # chrome + spotify

    def test_real_query_enum_capability(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_applications_by_capability(ApplicationCapability.NAVIGATE)
        assert isinstance(result, list)
        assert "Chrome" in result
        assert "Spotify" in result

    def test_real_query_string_capability(self):
        """String capability input returns [] because ApplicationManager
        only resolves enums — documented behavior."""
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_applications_by_capability("navigate_to_url")
        assert isinstance(result, list)
        assert result == []

    def test_unknown_capability(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_applications_by_capability("nonexistent")
        assert result == []


class TestQueryGetApplicationCapabilities:
    """get_application_capabilities: consulta declarativa."""

    def test_none_manager(self):
        integrator = _make_integrator_with_manager(None)
        assert integrator.get_application_capabilities("chrome") == {}

    def test_app_not_found(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.get_application_capabilities("nonexistent") == {}

    def test_chrome_capabilities_declared(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        caps = integrator.get_application_capabilities("chrome")
        assert isinstance(caps, dict)
        # ApplicationManager returns capability names as keys
        assert "open_chrome" in caps
        assert caps["open_chrome"]["capability"] == "open"
        assert "navigate_to_url" in caps
        assert caps["navigate_to_url"]["capability"] == "navigate"

    def test_capability_structure(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        caps = integrator.get_application_capabilities("chrome")
        for key, value in caps.items():
            assert "capability" in value
            assert isinstance(value["capability"], str)
            assert value["capability"] in ("open", "navigate", "search")
            assert "preconditions" in value
            assert "effects" in value
            assert "required_ui_elements" in value


class TestQueryGetUIElementsForCapability:
    """get_ui_elements_for_capability: elementos UI requeridos."""

    def test_app_not_found(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.get_ui_elements_for_capability("nonexistent", ApplicationCapability.OPEN) == []

    def test_known_capability(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_ui_elements_for_capability("chrome", ApplicationCapability.NAVIGATE)
        assert "address_bar" in result

    def test_capability_with_no_elements(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_ui_elements_for_capability("chrome", ApplicationCapability.OPEN)
        assert result == []

    def test_string_capability_name(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        result = integrator.get_ui_elements_for_capability("chrome", "search")
        assert "search_bar" in result


class TestQueryIsApplicationCapable:
    """is_application_capable: verificación de capacidad."""

    def test_app_not_found(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.is_application_capable("nonexistent", ApplicationCapability.OPEN) is False

    def test_capable(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.is_application_capable("chrome", ApplicationCapability.OPEN) is True

    def test_not_capable(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.is_application_capable("chrome", ApplicationCapability.LOGIN) is False

    def test_string_capability_not_supported_by_app(self):
        """ApplicationKnowledge.is_capable doesn't normalize strings,
        so the integrator returns False for string capabilities."""
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.is_application_capable("chrome", "open") is False


# ---------------------------------------------------------------------------
# INSTANCIA: register_application_knowledge
# ---------------------------------------------------------------------------

class TestRegisterApplicationKnowledge:
    """register_application_knowledge: registro vía API pública."""

    def test_empty_name_returns_false(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.register_application_knowledge({"type": "utility"}) is False

    def test_non_dict_returns_false(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        assert integrator.register_application_knowledge("not_a_dict") is False
        assert integrator.register_application_knowledge(None) is False

    def test_valid_config_returns_true(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        config = {
            "name": "RegisterTestApp",
            "type": "utility",
            "executable": "regtestapp",
            "capabilities": [],
        }
        try:
            assert integrator.register_application_knowledge(config) is True
            # verify the application was registered via the integrator's _get_application
            app = integrator._get_application("registertestapp")
            assert app is not None
            assert app.name == "RegisterTestApp"
        finally:
            pass


# ---------------------------------------------------------------------------
# SINGLETON
# ---------------------------------------------------------------------------

class TestSingleton:
    """get_application_knowledge_integrator: singleton."""

    def test_returns_same_instance(self):
        i1 = get_application_knowledge_integrator()
        i2 = get_application_knowledge_integrator()
        assert i1 is i2

    def test_singleton_has_manager(self):
        integrator = get_application_knowledge_integrator()
        assert integrator.application_manager is not None


# ---------------------------------------------------------------------------
# LEGACY MODULE-LEVEL COMPATIBILITY
# ---------------------------------------------------------------------------

class TestLegacyCompatibility:
    """Funciones legacy de compatibilidad."""

    def test_legacy_get_apps_by_capability(self):
        result = legacy_get_apps_by_cap("open")
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_legacy_get_apps_by_capability_invalid(self):
        result = legacy_get_apps_by_cap("nonexistent_cap_x")
        assert result == []

    def test_legacy_get_apps_by_capability_enum(self):
        result = legacy_get_apps_by_cap(ApplicationCapability.OPEN)
        assert isinstance(result, list)
        assert "Chrome" in result

    def test_legacy_get_app_knowledge(self):
        result = legacy_get_app_knowledge("chrome")
        assert isinstance(result, dict)
        assert result  # no vacío para chrome

    def test_legacy_get_app_knowledge_not_found(self):
        result = legacy_get_app_knowledge("nonexistent_xyz")
        assert result == {}


# ---------------------------------------------------------------------------
# INTEGRACIÓN: convert_application_to_nodes con Spotify (login_required)
# ---------------------------------------------------------------------------

class TestConvertSpotify:
    """Conversión de Spotify: aplicación con login_required."""

    def test_spotify_nodes(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        nodes = integrator.convert_application_to_nodes("spotify")
        assert len(nodes) >= 3  # app + capabilities
        ids = [n.id for n in nodes]
        assert "app_spotify" in ids

    def test_spotify_login_required_in_metadata(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("spotify")
        node = integrator._create_application_node(app)
        assert node.metadata["login_required"] is True
        assert node.parameters["login_required"] is True

    def test_spotify_has_preflight(self):
        integrator = _make_integrator_with_manager(get_application_manager())
        app = get_application_manager().get_application("spotify")
        node = integrator._create_application_node(app)
        assert "application_available" in node.preconditions
        assert "login_required" in node.preconditions
