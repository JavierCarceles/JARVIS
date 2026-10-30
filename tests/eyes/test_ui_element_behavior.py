# -*- coding: utf-8 -*-
"""Tests de comportamiento de elementos UI — unidad 3.4.4.2
(FASE 3.4.4 — Tests de elementos UI).

Verifica el comportamiento REAL de las clases y métodos de elementos UI
que no están cubiertos por las baterías de inspección de la fase 3.4.2
(estructura, type/description, separación conocimiento/coordenadas,
integración visión/calibración):

1. ``UIElement`` (applications_core.py):
   - ``is_calibrated()`` con varios formatos de coordenadas (None, dict con x/y,
     dict parcial, dict vacío, valores coordenada no-dict).
   - Valores por defecto de todos los campos del dataclass.
   - ``_serialize_ui_element`` con coordinates, screen, calibration_data,
     required_capability (casos con datos y sin datos).
   - ``_reconstruct_ui_elements`` con ``required_capability`` válida e inválida
     y preservación de coordinates/screen/calibration_data.

2. ``UIElementData`` (ui_element_model.py) — modelo canónico:
   - ``is_calibrated()`` (flag, formato clásico {x,y}, multipantalla {sN:[x,y]},
     None, dict vacío, coordenadas incompletas).
   - ``_coordinates_calibrated()`` (staticmethod, testing directo).
   - ``has_valid_geometry()`` (bbox, center, fallback a is_calibrated).
   - ``matches_name()`` (por nombre, por type+text, no coincidencia, vacío).
   - ``normalize_name()`` (lowercase, símbolos, espacios, None, acentos).
   - ``from_dict()`` (filtrado de claves desconocidas, entrada no-dict).
   - ``from_compact_dict()`` (campos completos, inferencia de nombre, defaults).
   - ``to_dict()`` (todos los campos presentes).

3. ``ApplicationKnowledge``:
   - ``get_ui_element()`` (encontrado, case-insensitive, con whitespace,
     no encontrado, lista vacía).
   - ``get_calibrated_elements()`` (sin CoordinateManager, elementos no
     calibrados, elementos calibrados).

4. ``_create_ui_element_node`` (application_integration.py):
   - Verificación completa de las propiedades del nodo resultante: id,
     name, description, parameters, preconditions, effects, cost,
     dependencies, application, ui_element, metadata.

No modifica código de producción.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.config import get_project_root


PROJECT_ROOT = get_project_root()
KNOWLEDGE_APPLICATIONS_PATH = PROJECT_ROOT / "data" / "knowledge" / "applications.json"
MACROS_COORDS_PATH = PROJECT_ROOT / "data" / "macros_coords.json"

from src.hands.applications_core import get_application_manager  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _suppress_system_logs():
    import logging

    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_knowledge_app(
    name: str = "TestApp",
    app_type: str = "utility",
    ui_elements=None,
    capabilities=None,
    states=None,
    metadata=None,
    **kwargs,
) -> "ApplicationKnowledge":
    """Crea una ApplicationKnowledge directamente (dataclass) para tests unitarios."""
    from src.hands.applications_core import ApplicationKnowledge, ApplicationState

    kwargs.setdefault("name", name)
    kwargs.setdefault("type", app_type)
    kwargs.setdefault("ui_elements", ui_elements or [])
    kwargs.setdefault("capabilities", capabilities or [])
    kwargs.setdefault("states", states or [ApplicationState.CLOSED])
    kwargs.setdefault("metadata", metadata or {})
    return ApplicationKnowledge(**kwargs)


# ===========================================================================
# 1. UIElement.is_calibrated()
# ===========================================================================

class TestUIElementIsCalibrated:
    """Verifica ``UIElement.is_calibrated()`` (applications_core.py:95).

    El método:
    - Devuelve ``False`` si ``coordinates`` es ``None``.
    - Si ``coordinates`` es dict, comprueba que existan ambas claves ``"x"`` y
      ``"y"``.
    - Si ``coordinates`` no es dict, devuelve ``bool(coordinates)``.
    """

    def test_coordinates_none(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates=None)
        assert elem.is_calibrated() is False

    def test_coordinates_dict_with_xy(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={"x": 10, "y": 20})
        assert elem.is_calibrated() is True

    def test_coordinates_dict_with_extra_keys(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={"x": 10, "y": 20, "z": 30})
        assert elem.is_calibrated() is True

    def test_coordinates_dict_missing_y(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={"x": 10})
        assert elem.is_calibrated() is False

    def test_coordinates_dict_missing_x(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={"y": 20})
        assert elem.is_calibrated() is False

    def test_coordinates_empty_dict(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={})
        assert elem.is_calibrated() is False

    def test_coordinates_dict_zero_values(self):
        """x=0, y=0 sigue siendo calibrado: la presencia de claves es lo que
        importa, no el valor."""
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates={"x": 0, "y": 0})
        assert elem.is_calibrated() is True

    def test_coordinates_non_dict_truthy(self):
        """Lista no vacía -> bool() es True."""
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates=[100, 200])
        assert elem.is_calibrated() is True

    def test_coordinates_non_dict_falsy(self):
        """Lista vacía -> bool() es False."""
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates=[])
        assert elem.is_calibrated() is False

    def test_coordinates_non_dict_string(self):
        """String no vacío -> bool() es True."""
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates="100,200")
        assert elem.is_calibrated() is True

    def test_coordinates_non_dict_empty_string(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button", coordinates="")
        assert elem.is_calibrated() is False


# ===========================================================================
# 2. UIElement defaults
# ===========================================================================

class TestUIElementDefaults:
    """Verifica los valores por defecto de los campos del dataclass UIElement."""

    def test_default_description_is_empty_string(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button")
        assert elem.description == ""

    def test_default_required_capability_is_none(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button")
        assert elem.required_capability is None

    def test_default_coordinates_is_none(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button")
        assert elem.coordinates is None

    def test_default_screen_is_zero(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button")
        assert elem.screen == 0

    def test_default_calibration_data_is_none(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="e", type="button")
        assert elem.calibration_data is None


# ===========================================================================
# 3. _serialize_ui_element — con datos de calibración
# ===========================================================================

class TestSerializeUiElementWithData:
    """Verifica ``_serialize_ui_element`` con coordinates, screen,
    calibration_data y required_capability.

    Solo las claves con valores no-default se incluyen condicionalmente;
    ``name``, ``type``, ``description`` y ``required_capability`` siempre están.
    """

    def test_serializes_coordinates(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(
            name="addr", type="input",
            coordinates={"x": 100, "y": 200},
        )
        serialized = _serialize_ui_element(elem)
        assert "coordinates" in serialized
        assert serialized["coordinates"] == {"x": 100, "y": 200}

    def test_serializes_required_capability(self):
        from src.hands.applications_core import (
            UIElement, _serialize_ui_element, ApplicationCapability,
        )

        elem = UIElement(
            name="btn", type="button",
            required_capability=ApplicationCapability.CLICK,
        )
        serialized = _serialize_ui_element(elem)
        assert serialized["required_capability"] == "click"

    def test_serializes_none_required_capability(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button")
        serialized = _serialize_ui_element(elem)
        assert serialized["required_capability"] is None

    def test_serializes_non_default_screen(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button", screen=2)
        serialized = _serialize_ui_element(elem)
        assert serialized["screen"] == 2

    def test_omits_default_screen(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button", screen=0)
        serialized = _serialize_ui_element(elem)
        assert "screen" not in serialized

    def test_serializes_calibration_data(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(
            name="btn", type="button",
            calibration_data={"strategy": "visual"},
        )
        serialized = _serialize_ui_element(elem)
        assert serialized["calibration_data"] == {"strategy": "visual"}

    def test_omits_none_coordinates(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button", coordinates=None)
        serialized = _serialize_ui_element(elem)
        assert "coordinates" not in serialized

    def test_omits_none_calibration_data(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button", calibration_data=None)
        serialized = _serialize_ui_element(elem)
        assert "calibration_data" not in serialized

    def test_always_has_core_keys(self):
        from src.hands.applications_core import UIElement, _serialize_ui_element

        elem = UIElement(name="btn", type="button")
        serialized = _serialize_ui_element(elem)
        assert set(serialized.keys()) == {
            "name", "type", "description", "required_capability",
        }


# ===========================================================================
# 4. _reconstruct_ui_elements — required_capability y campos de coordenadas
# ===========================================================================

class TestReconstructUiElementsCapability:
    """Verifica ``_reconstruct_ui_elements`` con ``required_capability``
    válida/inválida y preservación de coordinates/screen/calibration_data."""

    def test_valid_required_capability(self):
        from src.hands.applications_core import (
            ApplicationManager, ApplicationCapability,
        )

        items = [
            {"name": "btn", "type": "button", "required_capability": "click"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].required_capability == ApplicationCapability.CLICK

    def test_invalid_required_capability_becomes_none(self):
        from src.hands.applications_core import ApplicationManager

        items = [
            {"name": "btn", "type": "button", "required_capability": "nonexistent_cap"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].required_capability is None

    def test_no_required_capability_is_none(self):
        from src.hands.applications_core import ApplicationManager

        items = [{"name": "btn", "type": "button"}]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].required_capability is None

    def test_preserves_coordinates(self):
        from src.hands.applications_core import ApplicationManager

        items = [
            {"name": "btn", "type": "button", "coordinates": {"x": 10, "y": 20}},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].coordinates == {"x": 10, "y": 20}

    def test_preserves_screen(self):
        from src.hands.applications_core import ApplicationManager

        items = [{"name": "btn", "type": "button", "screen": 2}]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].screen == 2

    def test_preserves_calibration_data(self):
        from src.hands.applications_core import ApplicationManager

        items = [
            {"name": "btn", "type": "button", "calibration_data": {"k": "v"}},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].calibration_data == {"k": "v"}

    def test_description_default_empty(self):
        from src.hands.applications_core import ApplicationManager

        items = [{"name": "btn", "type": "button"}]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert result[0].description == ""

    def test_description_from_input(self):
        from src.hands.applications_core import ApplicationManager

        items = [
            {"name": "btn", "type": "button", "description": "A button"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert result[0].description == "A button"

    def test_all_capability_values_resolve(self):
        """Todos los valores de ApplicationCapability son resolubles."""
        from src.hands.applications_core import (
            ApplicationManager, ApplicationCapability,
        )

        all_caps = [cap.value for cap in ApplicationCapability]
        items = [
            {"name": f"e_{cap}", "type": "button", "required_capability": cap}
            for cap in all_caps
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == len(all_caps)
        resolved = {elem.required_capability for elem in result}
        expected = set(ApplicationCapability)
        assert resolved == expected


# ===========================================================================
# 5. ApplicationKnowledge.get_ui_element()
# ===========================================================================

class TestApplicationKnowledgeGetUiElement:
    """Verifica ``ApplicationKnowledge.get_ui_element(element_name)``."""

    def test_found_exact_name(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        result = app.get_ui_element("address_bar")
        assert result is not None
        assert result.name == "address_bar"

    def test_found_case_insensitive(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        result = app.get_ui_element("ADDRESS_BAR")
        assert result is not None
        assert result.name == "address_bar"

    def test_found_with_whitespace(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        result = app.get_ui_element("  address_bar  ")
        assert result is not None

    def test_not_found(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        assert app.get_ui_element("nonexistent") is None

    def test_empty_ui_elements(self):
        app = _make_knowledge_app(ui_elements=[])
        assert app.get_ui_element("anything") is None

    def test_none_input(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[UIElement(name="btn", type="button")],
        )
        assert app.get_ui_element(None) is None

    def test_multiple_elements_returns_first_match(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            ui_elements=[
                UIElement(name="btn", type="button"),
                UIElement(name="btn2", type="button"),
            ],
        )
        result = app.get_ui_element("btn")
        assert result is not None
        assert result.name == "btn"


# ===========================================================================
# 6. ApplicationKnowledge.get_calibrated_elements()
# ===========================================================================

class TestApplicationKnowledgeGetCalibratedElements:
    """Verifica ``ApplicationKnowledge.get_calibrated_elements()``."""

    def test_no_coord_manager_returns_empty(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={"entity_id": "calapp"},
        )
        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            side_effect=Exception("import error"),
        ):
            assert app.get_calibrated_elements() == []

    def test_coord_manager_none_returns_empty(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={"entity_id": "calapp"},
        )
        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=None,
        ):
            assert app.get_calibrated_elements() == []

    def test_element_not_calibrated_excluded(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={"entity_id": "calapp"},
        )
        mock_cm = MagicMock()
        mock_resource = MagicMock()
        mock_resource.is_usable = False
        mock_cm.get_ui_resource.return_value = mock_resource

        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=mock_cm,
        ):
            result = app.get_calibrated_elements()
        assert result == []
        mock_cm.get_ui_resource.assert_called_once_with("calapp.btn")

    def test_element_calibrated_included(self):
        from src.hands.applications_core import UIElement

        elem = UIElement(name="btn", type="button")
        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[elem],
            metadata={"entity_id": "calapp"},
        )
        mock_cm = MagicMock()
        mock_resource = MagicMock()
        mock_resource.is_usable = True
        mock_cm.get_ui_resource.return_value = mock_resource

        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=mock_cm,
        ):
            result = app.get_calibrated_elements()
        assert len(result) == 1
        assert result[0] is elem

    def test_resource_none_excluded(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={"entity_id": "calapp"},
        )
        mock_cm = MagicMock()
        mock_cm.get_ui_resource.return_value = None

        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=mock_cm,
        ):
            result = app.get_calibrated_elements()
        assert result == []

    def test_uses_metadata_entity_id(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="CalApp",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={"entity_id": "my_app_key"},
        )
        mock_cm = MagicMock()
        mock_resource = MagicMock()
        mock_resource.is_usable = True
        mock_cm.get_ui_resource.return_value = mock_resource

        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=mock_cm,
        ):
            app.get_calibrated_elements()
        mock_cm.get_ui_resource.assert_called_once_with("my_app_key.btn")

    def test_falls_back_to_name_without_entity_id(self):
        from src.hands.applications_core import UIElement

        app = _make_knowledge_app(
            name="My App",
            ui_elements=[UIElement(name="btn", type="button")],
            metadata={},
        )
        mock_cm = MagicMock()
        mock_resource = MagicMock()
        mock_resource.is_usable = True
        mock_cm.get_ui_resource.return_value = mock_resource

        with patch(
            "src.hands.coordinate_manager.get_coordinate_manager",
            return_value=mock_cm,
        ):
            app.get_calibrated_elements()
        # {} es falsy, por lo que el fallback a self.name no aplica .lower()
        mock_cm.get_ui_resource.assert_called_once_with("My App.btn")


# ===========================================================================
# 7. UIElementData.is_calibrated()
# ===========================================================================

class TestUIElementDataIsCalibrated:
    """Verifica ``UIElementData.is_calibrated()`` (ui_element_model.py:76)."""

    def test_calibrated_flag_true(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(calibrated=True)
        assert elem.is_calibrated() is True

    def test_calibrated_flag_true_ignores_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(calibrated=True, coordinates={"x": 10, "y": 20})
        assert elem.is_calibrated() is True

    def test_calibrated_flag_false_with_classic_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            calibrated=False, coordinates={"x": 10, "y": 20},
        )
        assert elem.is_calibrated() is True

    def test_calibrated_flag_false_with_multiscreen_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            calibrated=False, coordinates={"s1": [100, 200], "s2": [300, 400]},
        )
        assert elem.is_calibrated() is True

    def test_calibrated_flag_false_without_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(calibrated=False, coordinates=None)
        assert elem.is_calibrated() is False

    def test_calibrated_flag_false_empty_dict(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(calibrated=False, coordinates={})
        assert elem.is_calibrated() is False

    def test_calibrated_flag_false_multiscreen_short_value(self):
        """Coordenada de pantalla con menos de 2 valores -> False."""
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            calibrated=False, coordinates={"s1": [100]},
        )
        assert elem.is_calibrated() is False

    def test_calibrated_flag_false_non_xy_dict(self):
        """Dict sin x/y ni claves s* -> False."""
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            calibrated=False, coordinates={"z": 10},
        )
        assert elem.is_calibrated() is False


# ===========================================================================
# 8. UIElementData._coordinates_calibrated() (staticmethod directo)
# ===========================================================================

class TestUIElementDataCoordinatesCalibrated:
    """Verifica ``UIElementData._coordinates_calibrated()`` directamente."""

    def test_none(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(None) is False

    def test_empty_dict(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated({}) is False

    def test_non_dict(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated([100, 200]) is False
        assert UIElementData._coordinates_calibrated("string") is False
        assert UIElementData._coordinates_calibrated(42) is False

    def test_classic_xy(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"x": 10, "y": 20}
        ) is True

    def test_classic_xy_non_numeric(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"x": "a", "y": 20}
        ) is False
        assert UIElementData._coordinates_calibrated(
            {"x": 10, "y": True}  # bool no es number
        ) is False

    def test_classic_xy_zero(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"x": 0, "y": 0}
        ) is True

    def test_classic_missing_y(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"x": 10}
        ) is False

    def test_multiscreen_valid(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"s1": [100, 200]}
        ) is True
        assert UIElementData._coordinates_calibrated(
            {"s1": [100, 200, 300]}
        ) is True

    def test_multiscreen_short(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"s1": [100]}
        ) is False

    def test_multiscreen_non_numeric(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"s1": ["a", "b"]}
        ) is False

    def test_no_screen_keys(self):
        """Dict con claves que no empiezan por 's' ni tienen x/y -> False."""
        from src.utils.ui_element_model import UIElementData

        assert UIElementData._coordinates_calibrated(
            {"z": 10, "w": 20}
        ) is False

    def test_mixed_screens_some_valid(self):
        from src.utils.ui_element_model import UIElementData

        coords = {"s1": [100, 200], "s2": ["a", "b"]}
        assert UIElementData._coordinates_calibrated(coords) is True


# ===========================================================================
# 9. UIElementData.has_valid_geometry()
# ===========================================================================

class TestUIElementDataHasValidGeometry:
    """Verifica ``UIElementData.has_valid_geometry()``."""

    def test_bbox_valid(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=[10, 20, 30, 40])
        assert elem.has_valid_geometry() is True

    def test_bbox_short(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=[10, 20])
        assert elem.has_valid_geometry() is False

    def test_bbox_non_numeric(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.model_construct(bbox=["a", "b", "c", "d"])
        assert elem.has_valid_geometry() is False

    def test_bbox_none_center_valid(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=None, center=[100, 200])
        assert elem.has_valid_geometry() is True

    def test_bbox_none_center_short(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=None, center=[100])
        assert elem.has_valid_geometry() is False

    def test_bbox_none_center_empty_falls_to_is_calibrated(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=None, center=[])
        # No coords -> is_calibrated() returns False
        assert elem.has_valid_geometry() is False

    def test_bbox_none_center_empty_with_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            bbox=None, center=[],
            coordinates={"x": 10, "y": 20},
        )
        assert elem.has_valid_geometry() is True

    def test_bbox_none_center_empty_without_coordinates(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(bbox=None, center=[], coordinates=None)
        assert elem.has_valid_geometry() is False


# ===========================================================================
# 10. UIElementData.matches_name()
# ===========================================================================

class TestUIElementDataMatchesName:
    """Verifica ``UIElementData.matches_name(name)``."""

    def test_match_by_exact_name(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="address_bar", type="input")
        assert elem.matches_name("address_bar") is True

    def test_match_by_name_case_insensitive(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="Address_Bar", type="input")
        assert elem.matches_name("address_bar") is True

    def test_match_by_name_with_whitespace(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="address_bar", type="input")
        assert elem.matches_name("  address_bar  ") is True

    def test_match_by_type_and_text(self):
        """Cuando name no coincide, se busca en 'type text'."""
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="", type="button", text="Click me")
        assert elem.matches_name("button") is True
        assert elem.matches_name("click") is True

    def test_no_match(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="address_bar", type="input")
        assert elem.matches_name("nonexistent") is False

    def test_empty_target(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="address_bar", type="input")
        assert elem.matches_name("") is False
        assert elem.matches_name(None) is False
        assert elem.matches_name("   ") is False

    def test_name_takes_precedence_over_haystack(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(name="match", type="button", text="nomatch text")
        assert elem.matches_name("match") is True
        # "nomatch" está en el haystack "button nomatch text"
        assert elem.matches_name("nomatch") is True
        # Pero "xyz" no está ni en name ni en haystack
        assert elem.matches_name("xyz") is False


# ===========================================================================
# 11. UIElementData.normalize_name() (staticmethod)
# ===========================================================================

class TestUIElementDataNormalizeName:
    """Verifica ``UIElementData.normalize_name(name)`` (staticmethod)."""

    def test_simple(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("Hello World") == "hello_world"

    def test_multiple_separators(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("a---b===c") == "a_b_c"

    def test_whitespace_trimmed(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("  My App  ") == "my_app"

    def test_empty_string(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("") == ""

    def test_none(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name(None) == ""

    def test_accents(self):
        from src.utils.ui_element_model import UIElementData

        # é no está en [a-z], se reemplaza con _
        assert UIElementData.normalize_name("Café App") == "caf_app"

    def test_alphanumeric_preserved(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("btn1_btn2") == "btn1_btn2"

    def test_dots_and_dashes(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("a.b-c") == "a_b_c"

    def test_leading_trailing_underscores_stripped(self):
        from src.utils.ui_element_model import UIElementData

        assert UIElementData.normalize_name("---hello---") == "hello"


# ===========================================================================
# 12. UIElementData.from_dict()
# ===========================================================================

class TestUIElementDataFromDict:
    """Verifica ``UIElementData.from_dict(data)``."""

    def test_basic_from_dict(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_dict(
            {"name": "addr", "type": "input", "description": "Barra"}
        )
        assert elem.name == "addr"
        assert elem.type == "input"
        assert elem.description == "Barra"

    def test_extra_keys_filtered(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_dict(
            {"name": "addr", "type": "input", "unknown_key": "value"},
        )
        assert elem.name == "addr"
        assert elem.type == "input"
        # unknown_key no es un campo del modelo
        assert "unknown_key" not in elem.model_fields

    def test_non_dict_input(self):
        from src.utils.ui_element_model import UIElementData

        result = UIElementData.from_dict("not a dict")
        assert isinstance(result, UIElementData)
        assert result.name == ""
        assert result.type == "unknown"

    def test_none_input(self):
        from src.utils.ui_element_model import UIElementData

        result = UIElementData.from_dict(None)
        assert isinstance(result, UIElementData)
        assert result.name == ""

    def test_preserves_all_known_fields(self):
        from src.utils.ui_element_model import UIElementData

        data = {
            "name": "btn",
            "type": "button",
            "description": "A button",
            "text": "Click",
            "bbox": [1, 2, 3, 4],
            "center": [5, 6],
            "coordinates": {"x": 10, "y": 20},
            "screen": 2,
            "interactive": False,
            "confidence": 0.85,
            "calibrated": True,
            "calibration_data": {"strategy": "visual"},
            "required_capability": "click",
        }
        elem = UIElementData.from_dict(data)
        assert elem.name == "btn"
        assert elem.type == "button"
        assert elem.description == "A button"
        assert elem.text == "Click"
        assert elem.bbox == [1, 2, 3, 4]
        assert elem.center == [5, 6]
        assert elem.coordinates == {"x": 10, "y": 20}
        assert elem.screen == 2
        assert elem.interactive is False
        assert elem.confidence == 0.85
        assert elem.calibrated is True
        assert elem.calibration_data == {"strategy": "visual"}
        assert elem.required_capability == "click"


# ===========================================================================
# 13. UIElementData.from_compact_dict()
# ===========================================================================

class TestUIElementDataFromCompactDict:
    """Verifica ``UIElementData.from_compact_dict(data)``."""

    def test_full_data(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {
                "name": "address_bar",
                "type": "input",
                "text": "https://...",
                "bbox": [100, 200, 300, 400],
                "center": [200, 300],
                "interactive": True,
                "confidence": 0.95,
            }
        )
        assert elem.name == "address_bar"
        assert elem.type == "input"
        assert elem.text == "https://..."
        assert elem.bbox == [100, 200, 300, 400]
        assert elem.center == [200, 300]
        assert elem.interactive is True
        assert elem.confidence == 0.95

    def test_name_inferred_from_text(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {"type": "input", "text": "Click me"}
        )
        assert elem.name == "Click me"

    def test_name_inferred_from_type(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict({"type": "button"})
        assert elem.name == "button"

    def test_name_inferred_default(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict({})
        assert elem.name == "element"

    def test_non_dict_input(self):
        from src.utils.ui_element_model import UIElementData

        result = UIElementData.from_compact_dict(None)
        assert isinstance(result, UIElementData)
        assert result.name == ""

    def test_bbox_invalid(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {"name": "btn", "type": "button", "bbox": "invalid"},
        )
        assert elem.bbox is None

    def test_bbox_short(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {"name": "btn", "type": "button", "bbox": [1, 2]},
        )
        assert elem.bbox is None

    def test_center_invalid(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {"name": "btn", "type": "button", "center": "invalid"},
        )
        assert elem.center == []

    def test_center_short(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict(
            {"name": "btn", "type": "button", "center": [1]},
        )
        assert elem.center == []

    def test_confidence_default(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict({"name": "btn", "type": "button"})
        assert elem.confidence == 0.0

    def test_interactive_default(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData.from_compact_dict({"name": "btn", "type": "button"})
        assert elem.interactive is True


# ===========================================================================
# 14. UIElementData.to_dict()
# ===========================================================================

class TestUIElementDataToDict:
    """Verifica ``UIElementData.to_dict()`` devuelve todos los campos canónicos."""

    def test_all_fields_present(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData()
        d = elem.to_dict()
        expected_fields = {
            "name", "type", "description", "text",
            "bbox", "center", "coordinates", "screen",
            "interactive", "confidence", "calibrated",
            "calibration_data", "required_capability",
        }
        assert set(d.keys()) == expected_fields

    def test_values_match(self):
        from src.utils.ui_element_model import UIElementData

        elem = UIElementData(
            name="btn", type="button", description="A button",
            text="Click", bbox=[1, 2, 3, 4], center=[5, 6],
            coordinates={"x": 10, "y": 20}, screen=1,
            interactive=False, confidence=0.9,
            calibrated=True, calibration_data={"k": "v"},
            required_capability="click",
        )
        d = elem.to_dict()
        assert d["name"] == "btn"
        assert d["type"] == "button"
        assert d["description"] == "A button"
        assert d["text"] == "Click"
        assert d["bbox"] == [1, 2, 3, 4]
        assert d["center"] == [5, 6]
        assert d["coordinates"] == {"x": 10, "y": 20}
        assert d["screen"] == 1
        assert d["interactive"] is False
        assert d["confidence"] == 0.9
        assert d["calibrated"] is True
        assert d["calibration_data"] == {"k": "v"}
        assert d["required_capability"] == "click"


# ===========================================================================
# 15. _create_ui_element_node — verificación completa de propiedades
# ===========================================================================

class TestCreateUiElementNodeFull:
    """Verifica todas las propiedades del nodo creado por
    ``_create_ui_element_node`` (application_integration.py:437)."""

    def _make_integrator(self):
        from src.hands.planner.application_integration import (
            ApplicationKnowledgeIntegrator,
        )
        integrator = ApplicationKnowledgeIntegrator.__new__(
            ApplicationKnowledgeIntegrator
        )
        integrator.application_manager = get_application_manager()
        integrator.memory_manager = None
        return integrator

    def test_node_id_format(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert node.id == "testapp_address_bar"

    def test_node_name(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert node.name == "address_bar"

    def test_node_description(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert node.description == "Elemento UI address_bar de TestApp"

    def test_node_parameters_type(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        assert node.parameters["type"] == "input"

    def test_node_parameters_type_unknown_when_not_found(self):
        integrator = self._make_integrator()
        app = _make_knowledge_app(name="TestApp", ui_elements=[])
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "nonexistent", cap_def)
        assert node.parameters["type"] == "unknown"

    def test_node_parameters_screen(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button", screen=2)],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.parameters["screen"] == 2

    def test_node_parameters_screen_none_when_not_found(self):
        integrator = self._make_integrator()
        app = _make_knowledge_app(name="TestApp", ui_elements=[])
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "nonexistent", cap_def)
        assert node.parameters["screen"] is None

    def test_node_parameters_calibrated_false(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.parameters["calibrated"] is False

    def test_node_parameters_calibrated_true(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        elem = UIElement(name="btn", type="button", coordinates={"x": 1, "y": 2})
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[elem],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.parameters["calibrated"] is True

    def test_node_parameters_capability(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.parameters["capability"] == "click"

    def test_node_preconditions_app_open(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert "testapp_open" in node.preconditions

    def test_node_preconditions_calibrated(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        elem = UIElement(name="btn", type="button", coordinates={"x": 1, "y": 2})
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[elem],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert "testapp_btn_calibrated" in node.preconditions

    def test_node_preconditions_no_calibrated_when_uncalibrated(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert "testapp_btn_calibrated" not in node.preconditions

    def test_node_effects_available(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert "testapp_btn_available" in node.effects

    def test_node_effects_no_available_when_not_found(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "nonexistent", cap_def)
        assert "testapp_nonexistent_available" not in node.effects

    def test_node_effects_calibrated(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        elem = UIElement(name="btn", type="button", coordinates={"x": 1, "y": 2})
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[elem],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert "testapp_btn_calibrated" in node.effects

    def test_node_cost_is_zero(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.cost == 0.0

    def test_node_dependencies_empty(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.dependencies == []

    def test_node_application(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.application == "TestApp"

    def test_node_ui_element(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.ui_element == "btn"

    def test_node_metadata_source(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.metadata["source"] == "application_knowledge"

    def test_node_metadata_known_true(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.metadata["known"] is True

    def test_node_metadata_known_false(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "nonexistent", cap_def)
        assert node.metadata["known"] is False

    def test_node_metadata_required_by_capabilities(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.metadata["required_by_capabilities"] == ["click"]

    def test_node_type_resource_when_not_found(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "nonexistent", cap_def)
        from src.hands.planner.node import NodeType
        assert node.type == NodeType.RESOURCE

    def test_node_type_ui_element_when_found(self):
        from src.hands.applications_core import UIElement
        from src.hands.planner.node import NodeType

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.type == NodeType.UI_ELEMENT

    def test_app_name_normalized_in_id(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="Google Chrome",
            ui_elements=[UIElement(name="address_bar", type="input")],
        )
        cap_def = {"capability": "navigate"}
        node = integrator._create_ui_element_node(app, "address_bar", cap_def)
        # _normalize_name de ApplicationKnowledgeIntegrator normaliza a
        # "google_chrome" (sin alias de applications_core)
        assert node.id == "google_chrome_address_bar"
        assert node.application == "Google Chrome"

    def test_element_name_with_spaces_normalized(self):
        from src.hands.applications_core import UIElement

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="my element", type="button")],
        )
        cap_def = {"capability": "click"}
        node = integrator._create_ui_element_node(app, "my element", cap_def)
        assert node.id == "testapp_my_element"
        assert node.name == "my element"

    def test_capability_from_capability_def_object(self):
        """Cuando cap_def es un ApplicationCapabilityDef, se extrae su capability."""
        from src.hands.applications_core import (
            UIElement, ApplicationCapability, ApplicationCapabilityDef,
        )

        integrator = self._make_integrator()
        app = _make_knowledge_app(
            name="TestApp",
            ui_elements=[UIElement(name="btn", type="button")],
        )
        cap_def = ApplicationCapabilityDef(
            capability=ApplicationCapability.CLICK,
            name="click_btn",
            description="Click button",
            required_ui_elements=["btn"],
            preconditions=[],
            effects=[],
            cost=1.0,
        )
        node = integrator._create_ui_element_node(app, "btn", cap_def)
        assert node.parameters["capability"] == "click"
        assert node.metadata["required_by_capabilities"] == ["click"]
