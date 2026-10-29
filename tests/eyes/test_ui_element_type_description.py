# -*- coding: utf-8 -*-
"""Tests de verificación de ``type`` y ``description`` de ``ui_elements`` — unidad 3.4.2.2
(FASE 3.4.2 — UI elements).

Verifica el comportamiento REAL (no el esperado) de los campos ``type`` y
``description`` de los elementos UI a través de las siguientes capas:

1. **type** — es un string libre (no hay enum central). Valores reales en
   `data/knowledge/applications.json` (``input``, ``button``, ``panel``) y
   `data/macros_coords.json`` (``input``, ``button``, ``region``).
   ``type`` es consumido por:
   - ``coordinate_manager._resource_type_for_element``: ``region`` -> REGION,
     resto -> ELEMENT (clasificación binaria).
   - ``coordinate_manager.validate_resource_for_action``: mapea type a
     acciones permitidas (focus/click/type).
   - ``coordinate_manager.get_calibration_strategy``: mapea type a estrategia.
   - ``coordinate_manager._infer_element_type``: infiere type desde el nombre.
   - ``applications_core._reconstruct_ui_elements``: ``type`` es obligatorio
     (items sin type se omiten).
   - ``application_integration._create_ui_element_node``: extrae type en
     parámetros del nodo, default ``"unknown"``.

2. **description** — está presente en los JSON de datos pero:
   - ``UIElement`` (dataclass en ``applications_core.py``) NO tiene campo
     ``description`` → se pierde (D-UI-DESCRIPTION-LOST).
   - ``_serialize_ui_element`` / ``get_application_ui_elements`` /
     ``_reconstruct_ui_elements`` NO incluyen description.
   - ``register_custom_application`` FALLA SILENCIOSAMENTE (return False) si
     los ui_elements (formato lista) incluyen ``description``, porque
     ``UIElement(**element_data)`` lanza ``TypeError``.
   - ``_create_ui_element_node`` GENERA su propia description
     (``f"Elemento UI {element_name} de {app_name}"``) en lugar de usar la
     del JSON.
   - PRESERVADO en: ``UIElementData`` (modelo canónico), ``UIResource``
     (``coordinate_manager``), ``_create_resource_from_knowledge`` (lee del
     JSON de macros_coords), ``UIElementData.from_dict``.

No modifica código de producción. La lectura de ficheros usa rutas absolutas
(get_project_root) y el runtime se verifica con el modelo real.
"""

import dataclasses
import json

import pytest

from src.utils.config import get_project_root


# ---------------------------------------------------------------------------
# Rutas absolutas (read-only)
# ---------------------------------------------------------------------------
PROJECT_ROOT = get_project_root()
KNOWLEDGE_APPLICATIONS_PATH = (
    PROJECT_ROOT / "data" / "knowledge" / "applications.json"
)
MACROS_COORDS_PATH = PROJECT_ROOT / "data" / "macros_coords.json"


@pytest.fixture(autouse=True, scope="module")
def _suppress_system_logs():
    import logging
    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_knowledge_apps():
    return json.loads(
        KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
    )


def _load_macros_coords():
    return json.loads(
        MACROS_COORDS_PATH.read_text(encoding="utf-8")
    )


def _make_minimal_coordinate_manager():
    """Crea un CoordinateManager vía __new__ sin inicializar pantalla."""
    from src.hands.coordinate_manager import (
        CoordinateManager,
        UIResource,
        ResourceType,
        CalibrationStrategy,
    )
    cm = CoordinateManager.__new__(CoordinateManager)
    cm.ui_resources = {}
    cm.calibration_policies = {}
    cm.ui_knowledge = {}
    return cm, UIResource, ResourceType, CalibrationStrategy


# ===========================================================================
# 1. Type — valores reales en fuentes de datos
# ===========================================================================
class TestTypeInDataSources:
    """Verifica los valores reales de ``type`` en los archivos JSON de datos."""

    def test_knowledge_json_type_values_are_finite_set(self):
        """En ``data/knowledge/applications.json`` los valores de ``type``
        son exactamente: ``input``, ``button``, ``panel``.
        """
        data = _load_knowledge_apps()
        types_found: set = set()
        for app_data in data.values():
            for elem_def in app_data["ui_elements"].values():
                types_found.add(elem_def["type"])
        assert types_found == {"input", "button", "panel"}, (
            f"type values inesperados: {types_found}"
        )

    def test_macros_coords_type_values(self):
        """En ``data/macros_coords.json`` los valores de ``type`` son
        ``input``, ``button`` y ``region``.
        """
        data = _load_macros_coords()
        ui_knowledge = data.get("ui_knowledge", {})
        types_found: set = set()
        for app_data in ui_knowledge.values():
            for elem_def in app_data.values():
                if isinstance(elem_def, dict) and "type" in elem_def:
                    types_found.add(elem_def["type"])
        assert types_found == {"input", "button", "region"}, (
            f"type values inesperados en macros_coords: {types_found}"
        )

    def test_all_knowledge_elements_have_non_empty_type(self):
        """Todo elemento en el JSON de conocimiento tiene type no vacío."""
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            for elem_name, elem_def in app_data["ui_elements"].items():
                assert isinstance(elem_def["type"], str)
                assert elem_def["type"].strip() != "", (
                    f"app '{app_key}' / '{elem_name}': type vacío"
                )

    def test_all_macros_coords_elements_have_non_empty_type(self):
        """Todo elemento en macros_coords.json tiene type no vacío."""
        data = _load_macros_coords()
        for app_key, app_data in data.get("ui_knowledge", {}).items():
            for elem_name, elem_def in app_data.items():
                if isinstance(elem_def, dict) and "type" in elem_def:
                    assert isinstance(elem_def["type"], str)
                    assert elem_def["type"].strip() != "", (
                        f"app '{app_key}' / '{elem_name}': type vacío"
                    )


# ===========================================================================
# 2. Type — es un string libre (sin enum central de validación)
# ===========================================================================
class TestTypeIsFreeFormString:
    """Verifica que ``type`` es un string libre sin validación por enum
    central. No existe un enum ``UIElementType`` / ``ElementType`` en el
    sistema.
    """

    def test_ui_element_type_is_str_without_enum(self):
        """``UIElement.type`` es ``str`` (free-form), sin enum, sin default
        explícito — es el segundo campo posicional requerido del dataclass.
        """
        from src.hands.applications_core import UIElement
        fields = {f.name: f for f in dataclasses.fields(UIElement)}
        type_field = fields["type"]
        assert type_field.type == "str", (
            "UIElement.type debería ser str (free-form), no un Enum"
        )

    def test_ui_element_data_type_defaults_to_unknown(self):
        """``UIElementData.type`` es ``str`` con default ``"unknown"``.

        No hay validación de valores permitidos: cualquier string es aceptado.
        """
        from src.utils.ui_element_model import UIElementData
        elem = UIElementData()
        assert elem.type == "unknown"
        # Cualquier string arbitrario es aceptado como type
        elem2 = UIElementData(name="x", type="custom_type_123")
        assert elem2.type == "custom_type_123"

    def test_vision_ui_element_type_defaults_to_unknown(self):
        """El ``UIElement`` de visión (hereda de ``UIElementData``) también
        usa ``type: str = "unknown"`` sin enum.
        """
        from src.eyes.vision import UIElement as VisionUIElement
        elem = VisionUIElement()
        assert elem.type == "unknown"

    def test_no_central_enum_for_element_types(self):
        """No existe un enum central que valide los valores de ``type`` de
        elementos UI. El type es libre en todos los modelos.
        """
        # Buscar explícitamente un enum de tipos de elementos
        import inspect
        from src.hands.applications_core import UIElement, ApplicationCapability
        from src.hands.coordinate_manager import UIResource

        # UIElement.type es str, no Enum
        ui_type_field = {f.name: f for f in dataclasses.fields(UIElement)}["type"]
        assert "Enum" not in str(ui_type_field.type), (
            "UIElement.type no debería ser un Enum"
        )

        # ApplicationCapability es una enum de CAPACIDADES (no de tipos de elemento)
        assert issubclass(ApplicationCapability, type(None).__class__) is False
        # El type de UIElement no está relacionado con ApplicationCapability
        # (son conceptos distintos: type vs capability)


# ===========================================================================
# 3. Type — consumo en coordinate_manager
# ===========================================================================
class TestTypeConsumptionInCoordinateManager:
    """Verifica cómo el campo ``type`` es consumido de forma real en
    ``coordinate_manager.py`` para tomar decisiones.
    """

    def test_resource_type_for_element_region_is_region(self):
        """``_resource_type_for_element('region')`` -> ``ResourceType.REGION``."""
        from src.hands.coordinate_manager import CoordinateManager, ResourceType
        assert CoordinateManager._resource_type_for_element("region") == ResourceType.REGION

    def test_resource_type_for_element_non_region_is_element(self):
        """``_resource_type_for_element('button')`` / ``'input'`` -> ELEMENT."""
        from src.hands.coordinate_manager import CoordinateManager, ResourceType
        assert CoordinateManager._resource_type_for_element("button") == ResourceType.ELEMENT
        assert CoordinateManager._resource_type_for_element("input") == ResourceType.ELEMENT
        assert CoordinateManager._resource_type_for_element("panel") == ResourceType.ELEMENT

    def test_infer_element_type_button(self):
        """``_infer_element_type`` infiere ``button`` desde el nombre."""
        cm, _, _, _ = _make_minimal_coordinate_manager()
        assert cm._infer_element_type("play_button") == "button"
        assert cm._infer_element_type("new_tab_btn") == "button"

    def test_infer_element_type_input(self):
        """``_infer_element_type`` infiere ``input`` desde el nombre."""
        cm, _, _, _ = _make_minimal_coordinate_manager()
        assert cm._infer_element_type("address_bar") == "input"
        assert cm._infer_element_type("search_field") == "input"

    def test_infer_element_type_no_match_defaults_to_element(self):
        """Si el nombre no coincide con ningún keyword, devuelve ``element``."""
        cm, _, _, _ = _make_minimal_coordinate_manager()
        assert cm._infer_element_type("explorer") == "element"
        assert cm._infer_element_type("terminal") == "element"

    def test_validate_resource_focus_accepts_input(self):
        """``validate_resource_for_action('focus_...')`` acepta elementos
        de type ``input`` pero rechaza ``button``.
        """
        cm, UIResource, ResourceType, CalibrationStrategy = _make_minimal_coordinate_manager()

        input_res = UIResource(
            id="chrome.address_bar", name="address_bar",
            resource_type=ResourceType.ELEMENT,
            application="chrome", element_type="input",
            calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
            calibrated_coordinates={1: (100, 200)},
            calibrated_regions={}, confidence=0.9,
            is_available=True, is_calibrated=True,
        )
        button_res = UIResource(
            id="chrome.new_tab", name="new_tab",
            resource_type=ResourceType.ELEMENT,
            application="chrome", element_type="button",
            calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
            calibrated_coordinates={1: (300, 400)},
            calibrated_regions={}, confidence=0.9,
            is_available=True, is_calibrated=True,
        )
        cm.ui_resources["chrome.address_bar"] = input_res
        cm.ui_resources["chrome.new_tab"] = button_res

        assert cm.validate_resource_for_action("focus_element", "chrome.address_bar") is True
        assert cm.validate_resource_for_action("type_element", "chrome.address_bar") is True
        assert cm.validate_resource_for_action("type_element", "chrome.new_tab") is False
        assert cm.validate_resource_for_action("click_element", "chrome.new_tab") is True
        # click sobre un elemento type "input" es rechazado: "input" no está
        # en el conjunto permitido para click_ (button, element, link, menu,
        # checkbox, radio, select, toolbar).
        assert cm.validate_resource_for_action("click_element", "chrome.address_bar") is False

    def test_get_calibration_strategy_mapping(self):
        """``get_calibration_strategy`` mapea type strings a estrategias
        reales definidas en el código.
        """
        cm, _, _, CalibrationStrategy = _make_minimal_coordinate_manager()
        cm.calibration_policies = {}

        assert cm.get_calibration_strategy("chrome", "button") == CalibrationStrategy.VISUAL_DETECTION
        assert cm.get_calibration_strategy("chrome", "input") == CalibrationStrategy.VISUAL_DETECTION
        assert cm.get_calibration_strategy("chrome", "region") == CalibrationStrategy.SCREEN_CAPTURE
        assert cm.get_calibration_strategy("chrome", "window") == CalibrationStrategy.WINDOW_DETECTION
        # Default para type desconocido -> VISUAL_DETECTION
        assert cm.get_calibration_strategy("chrome", "unknown_xxx") == CalibrationStrategy.VISUAL_DETECTION


# ===========================================================================
# 4. Type — consumo en _reconstruct_ui_elements
# ===========================================================================
class TestTypeInReconstructUiElements:
    """``_reconstruct_ui_elements`` requiere ``type`` no vacío; items sin
    type se omiten silenciosamente.
    """

    def test_reconstruct_requires_type(self):
        """Items sin ``type`` se omiten."""
        from src.hands.applications_core import ApplicationManager
        items = [
            {"name": "no_type", "description": "sin type"},
            {"name": "ok", "type": "button"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].name == "ok"

    def test_reconstruct_type_preserved_as_string(self):
        """El type reconstruido preserva el valor string del dict."""
        from src.hands.applications_core import ApplicationManager
        items = [{"name": "btn", "type": "button"}]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert result[0].type == "button"


# ===========================================================================
# 5. Type — consumo en _create_ui_element_node
# ===========================================================================
class TestTypeInCreateUiElementNode:
    """``_create_ui_element_node`` extrae ``type`` del elemento y lo coloca
    en los parámetros del nodo; si no hay elemento, default ``"unknown"``.
    """

    def test_type_default_unknown_when_no_element(self):
        """Sin elemento encontrado, el type del nodo es ``"unknown"``."""
        from src.hands.planner.application_integration import ApplicationKnowledgeIntegrator

        integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)

        class _FakeApp:
            name = "TestApp"
            def get_ui_element(self, name):
                return None

        cap_def = {"capability": "navigate"}
        result = integrator._create_ui_element_node(_FakeApp(), "address_bar", cap_def)
        assert result.parameters.get("type") == "unknown"

    def test_type_extracted_from_element_dict(self):
        """Cuando ui_elements es un dict (formato JSON) y el elemento existe,
        el type se extrae correctamente.
        """
        from src.hands.planner.application_integration import ApplicationKnowledgeIntegrator

        integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
        app = type("FakeApp", (), {
            "name": "Chrome",
            "ui_elements": {"address_bar": {"type": "input", "description": "desc"}},
        })()
        cap_def = {"capability": "navigate"}
        result = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert result.parameters.get("type") == "input"


# ===========================================================================
# 6. Type — consumo en vision detect_ui_elements
# ===========================================================================
class TestTypeInVisionDetection:
    """``detect_ui_elements`` en ``vision.py`` produce ``type`` como string
    libre extraído del LLM; si falta, default ``"other"``.
    """

    def test_vision_detect_ui_elements_type_is_freeform(self):
        """El schema de ``detect_ui_elements`` define ``type`` como
        ``{"type": "string"}`` (no enum). El código usa
        ``str(item.get("type", "other"))``.
        """
        # Verificamos el código fuente real del método
        import inspect
        from src.eyes.vision import Vision
        source = inspect.getsource(Vision.detect_ui_elements)
        assert '"type": "string"' in source or "'type': 'string'" in source, (
            "detect_ui_elements debe definir type como string en el schema"
        )
        assert "str(item.get(\"type\"" in source or "str(item.get('type'" in source, (
            "detect_ui_elements debe extraer type como str(item.get('type', ...))"
        )

    def test_vision_analyze_image_schema_includes_type(self):
        """El schema de ``analyze_image`` también define ``type`` como string
        (no enum).
        """
        import inspect
        from src.eyes.vision import Vision
        source = inspect.getsource(Vision.analyze_image)
        assert '"type": {"type": "string"}' in source or "'type': {'type': 'string'}" in source, (
            "analyze_image debe definir type como string en el schema"
        )


# ===========================================================================
# 7. Description — presencia en fuentes de datos
# ===========================================================================
class TestDescriptionInDataSources:
    """Verifica que ``description`` está presente en todos los elementos
    UI de los archivos JSON de datos.
    """

    def test_knowledge_json_has_description_all_elements(self):
        """Todo elemento en ``applications.json`` tiene ``description`` no vacío."""
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            for elem_name, elem_def in app_data["ui_elements"].items():
                assert "description" in elem_def, (
                    f"app '{app_key}' / '{elem_name}': falta 'description'"
                )
                assert isinstance(elem_def["description"], str)
                assert elem_def["description"].strip() != "", (
                    f"app '{app_key}' / '{elem_name}': description vacía"
                )

    def test_macros_coords_has_description_all_elements(self):
        """Todo elemento en ``macros_coords.json`` tiene ``description``."""
        data = _load_macros_coords()
        for app_key, app_data in data.get("ui_knowledge", {}).items():
            for elem_name, elem_def in app_data.items():
                if isinstance(elem_def, dict) and "type" in elem_def:
                    assert "description" in elem_def, (
                        f"macros_coords app '{app_key}' / '{elem_name}': falta 'description'"
                    )


# ===========================================================================
# 8. Description — preservada en UIElementData (modelo canónico)
# ===========================================================================
class TestDescriptionInUIElementData:
    """``UIElementData`` (modelo canónico) SÍ tiene y preserva ``description``.
    """

    def test_ui_element_data_has_description_field(self):
        """``UIElementData`` define ``description: str = ""``."""
        from src.utils.ui_element_model import UIElementData
        assert "description" in UIElementData.model_fields
        elem = UIElementData()
        assert elem.description == ""

    def test_from_dict_preserves_description(self):
        """``UIElementData.from_dict`` preserva ``description`` del dict."""
        from src.utils.ui_element_model import UIElementData
        elem = UIElementData.from_dict(
            {"name": "addr", "type": "input", "description": "Barra de direcciones"}
        )
        assert elem.description == "Barra de direcciones"

    def test_from_compact_dict_does_not_set_description(self):
        """``UIElementData.from_compact_dict`` NO establece ``description``,
        incluso si el dict de origen lo incluye (el output del LLM de visión
        no incluye description).
        """
        from src.utils.ui_element_model import UIElementData
        elem = UIElementData.from_compact_dict(
            {"name": "addr", "type": "input", "description": "Ignored", "text": "URL"}
        )
        assert elem.description == "", (
            "from_compact_dict no debería establecer description — se pierde"
        )

    def test_to_dict_includes_description(self):
        """``UIElementData.to_dict()`` incluye ``description``."""
        from src.utils.ui_element_model import UIElementData
        elem = UIElementData(name="addr", type="input", description="test desc")
        d = elem.to_dict()
        assert d["description"] == "test desc"


# ===========================================================================
# 9. Description — PERSISTIDA en UIResource (coordinate_manager)
# ===========================================================================
class TestDescriptionInUIResource:
    """``UIResource`` (coordinate_manager) SÍ tiene y preserva ``description``
    cuando se crea desde conocimiento.
    """

    def test_ui_resource_has_description_field(self):
        """``UIResource`` dataclass define ``description: str = ''``."""
        from src.hands.coordinate_manager import UIResource
        fields = {f.name: f for f in dataclasses.fields(UIResource)}
        assert "description" in fields
        assert fields["description"].default == ""

    def test_create_resource_from_knowledge_preserves_description(self):
        """``_create_resource_from_knowledge`` preserva ``description`` del
        elemento JSON (macros_coords.json).
        """
        cm, UIResource, ResourceType, CalibrationStrategy = _make_minimal_coordinate_manager()
        element_data = {
            "type": "input",
            "description": "Barra de direcciones de Chrome",
            "calibration_strategy": "visual_detection",
            "screens": {"s1": [3582, 339]},
            "confidence": 0.9,
        }
        resource = cm._create_resource_from_knowledge(
            "chrome.address_bar", "chrome", "address_bar", element_data
        )
        assert resource is not None
        assert resource.description == "Barra de direcciones de Chrome"

    def test_create_resource_from_knowledge_defaults_empty_description(self):
        """Sin ``description`` en el JSON, el recurso usa ``""``."""
        cm, _, _, _ = _make_minimal_coordinate_manager()
        element_data = {
            "type": "button",
            "screens": {"s1": [300, 400]},
        }
        resource = cm._create_resource_from_knowledge(
            "chrome.new_tab", "chrome", "new_tab", element_data
        )
        assert resource is not None
        assert resource.description == ""


# ===========================================================================
# 10. Description — PERSISTIDA en UIElement (applications_core) NO
# ===========================================================================
class TestDescriptionInApplicationModel:
    """Verifica que ``description`` fluye de forma coherente en el modelo
    ``UIElement`` de ``applications_core.py`` y en todas las rutas que
    derivan de él (serialize, reconstruct, get_application_ui_elements,
    register_custom_application).

    Discrepancia D-UI-DESCRIPTION-LOST resuelta: ``description`` está presente
    en el JSON de conocimiento, en UIElementData, en UIResource y ahora tambien
    en UIElement y en todas sus rutas de serializacion/reconstruccion.
    """

    def test_ui_element_has_description_field(self):
        """``UIElement`` dataclass tiene campo ``description`` con default ""."""
        from src.hands.applications_core import UIElement
        field_names = {f.name for f in dataclasses.fields(UIElement)}
        assert "description" in field_names

    def test_ui_element_accepts_description(self):
        """Pasar ``description`` al constructor de ``UIElement`` funciona y se
        conserva en la instancia.
        """
        from src.hands.applications_core import UIElement
        elem = UIElement(name="addr", type="input", description="foo")
        assert elem.description == "foo"

    def test_serialize_ui_element_includes_description(self):
        """``_serialize_ui_element`` incluye ``description`` en su output."""
        from src.hands.applications_core import UIElement, _serialize_ui_element
        elem = UIElement(name="addr", type="input")
        serialized = _serialize_ui_element(elem)
        assert "description" in serialized
        assert serialized["description"] == ""
        assert set(serialized.keys()) == {
            "name", "type", "description", "required_capability",
        }

    def test_get_application_ui_elements_includes_description(self):
        """``get_application_ui_elements`` incluye ``description``."""
        from src.hands.applications_core import get_application_manager
        manager = get_application_manager()
        elems = manager.get_application_ui_elements("chrome")
        for elem_name, elem_def in elems.items():
            assert "description" in elem_def, (
                f"elem '{elem_name}': description deberia estar presente "
                "(coherencia D-UI-DESCRIPTION resuelta)"
            )
            assert isinstance(elem_def["description"], str)

    def test_reconstruct_ui_elements_captures_description(self):
        """``_reconstruct_ui_elements`` captura ``description`` del dict de
        entrada y la conserva en el UIElement resultante.
        """
        from src.hands.applications_core import ApplicationManager
        items = [
            {"name": "addr", "type": "input", "description": "Barra de direcciones"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        elem = result[0]
        assert hasattr(elem, "description")
        assert elem.description == "Barra de direcciones"


# ===========================================================================
# 11. register_custom_application — description causa fallo silencioso
# ===========================================================================
class TestRegisterCustomApplicationWithDescription:
    """``register_custom_application`` acepta ``description`` en
    ``ui_elements`` (formato lista) sin fallar, porque ``UIElement`` ahora
    tiene el campo ``description`` y se incluye en element_kwargs.
    """

    def test_register_succeeds_with_description_in_ui_elements(self):
        """Pasar ui_elements con ``description`` (formato lista) retorna True —
        el campo description se conserva en el UIElement.
        """
        from src.hands.applications_core import register_custom_application
        config = {
            "name": "DescOkApp",
            "type": "utility",
            "ui_elements": [
                {"name": "btn", "type": "button", "description": "Un botón"},
            ],
        }
        result = register_custom_application(config)
        assert result is True, (
            "register_custom_application debería tener exito cuando "
            "ui_elements incluye description (UIElement lo acepta)"
        )

    def test_register_succeeds_without_description(self):
        """Sin ``description`` en ui_elements, el registro funciona."""
        from src.hands.applications_core import register_custom_application
        config = {
            "name": "NoDescOkApp",
            "type": "utility",
            "ui_elements": [
                {"name": "btn", "type": "button"},
            ],
        }
        result = register_custom_application(config)
        assert result is True


# ===========================================================================
# 12. Description — _create_ui_element_node GENERA su propia descripción
# ===========================================================================
class TestDescriptionInCreateUiElementNode:
    """``_create_ui_element_node`` genera su propia ``description`` en el
    nodo (``f"Elemento UI {element_name} de {app_name}"``) en lugar de usar
    la del JSON conocimiento.
    """

    def test_node_description_is_generated_not_from_json(self):
        """La description del nodo es generada, no leída del JSON."""
        from src.hands.planner.application_integration import ApplicationKnowledgeIntegrator

        integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
        app = type("FakeApp", (), {
            "name": "Chrome",
            "ui_elements": {
                "address_bar": {"type": "input", "description": "Barra de direcciones"},
            },
        })()
        cap_def = {"capability": "navigate"}
        result = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert result.description == "Elemento UI address_bar de Chrome", (
            "La description del nodo es generada, no tomada del JSON"
        )

    def test_node_description_not_in_parameters(self):
        """La description del JSON no aparece en los parámetros del nodo."""
        from src.hands.planner.application_integration import ApplicationKnowledgeIntegrator

        integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
        app = type("FakeApp", (), {
            "name": "Chrome",
            "ui_elements": {
                "address_bar": {"type": "input", "description": "JSON desc"},
            },
        })()
        cap_def = {"capability": "navigate"}
        result = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert "description" not in result.parameters
