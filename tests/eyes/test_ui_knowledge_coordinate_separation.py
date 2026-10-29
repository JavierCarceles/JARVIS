# -*- coding: utf-8 -*-
"""Tests de verificacion de la separacion conocimiento UI / coordenadas concretas — unidad 3.4.2.3 (FASE 3.4.2 — UI elements).

Objetivo verificable: en ``data/macros_coords.json`` el conocimiento de UI
(type, description, calibration_strategy, alternatives, confidence) vive bajo
``ui_knowledge`` SIN coordenadas (sin ``screens``), y las coordenadas concretas
viven bajo la seccion ``calibraciones`` (solo claves de pantalla y valores de
coordenada). ``CoordinateManager`` carga el conocimiento desde ``ui_knowledge``,
las coordenadas desde ``calibraciones`` y las fusiona por ``resource_id``.

No modifica codigo de produccion. Lectura read-only de ficheros de datos.
"""

import json

import pytest

from src.utils.config import get_project_root


PROJECT_ROOT = get_project_root()
MACROS_COORDS_PATH = PROJECT_ROOT / "data" / "macros_coords.json"


@pytest.fixture(autouse=True, scope="module")
def _suppress_system_logs():
    import logging

    logging.disable(logging.CRITICAL)
    yield


def _load_macros_coords():
    return json.loads(MACROS_COORDS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Estructura de datos: conocimiento sin coordenadas en ui_knowledge
# ---------------------------------------------------------------------------
class TestUiKnowledgeWithoutCoordinates:
    """``ui_knowledge`` contiene solo conocimiento (no ``screens``)."""

    def test_ui_knowledge_elements_have_no_screens(self):
        """Ningún elemento de ``ui_knowledge`` incluye la clave ``screens``."""
        data = _load_macros_coords()
        ui_knowledge = data.get("ui_knowledge", {})
        assert isinstance(ui_knowledge, dict) and ui_knowledge, (
            "ui_knowledge debe estar presente y no vacía"
        )
        for app_key, app_data in ui_knowledge.items():
            assert isinstance(app_data, dict), (
                f"app '{app_key}' no es un dict"
            )
            for elem_name, elem_def in app_data.items():
                assert isinstance(elem_def, dict), (
                    f"app '{app_key}' / '{elem_name}' no es un dict"
                )
                assert "screens" not in elem_def, (
                    f"app '{app_key}' / '{elem_name}': 'screens' no debe estar en ui_knowledge "
                    "(coordenadas mezcladas con conocimiento)"
                )
                assert "coordinates" not in elem_def, (
                    f"app '{app_key}' / '{elem_name}': 'coordinates' no debe estar en ui_knowledge"
                )

    def test_ui_knowledge_elements_keep_knowledge_fields(self):
        """Los elementos de ``ui_knowledge`` conservan campos de conocimiento."""
        data = _load_macros_coords()
        ui_knowledge = data.get("ui_knowledge", {})
        for app_key, app_data in ui_knowledge.items():
            for elem_name, elem_def in app_data.items():
                assert "type" in elem_def and isinstance(elem_def["type"], str), (
                    f"app '{app_key}' / '{elem_name}': falta 'type'"
                )
                assert "description" in elem_def and isinstance(elem_def["description"], str), (
                    f"app '{app_key}' / '{elem_name}': falta 'description'"
                )
                assert "calibration_strategy" in elem_def, (
                    f"app '{app_key}' / '{elem_name}': falta 'calibration_strategy'"
                )


# ---------------------------------------------------------------------------
# 2. Estructura de datos: coordenadas solo en calibraciones
# ---------------------------------------------------------------------------
class TestCalibracionesOnlyCoordinates:
    """``calibraciones`` contiene solo coordenadas (sin campos de conocimiento)."""

    def test_calibraciones_section_exists(self):
        """La seccion ``calibraciones`` existe y es un dict."""
        data = _load_macros_coords()
        assert "calibraciones" in data, "falta la seccion 'calibraciones'"
        assert isinstance(data["calibraciones"], dict), (
            "'calibraciones' debe ser un dict"
        )

    def test_calibraciones_entries_have_only_screen_keys(self):
        """Cada entrada de ``calibraciones`` solo tiene claves de pantalla (sN)
        y valores de coordenada."""
        data = _load_macros_coords()
        calibraciones = data["calibraciones"]
        for app_key, app_data in calibraciones.items():
            assert isinstance(app_data, dict), (
                f"app '{app_key}' no es un dict en calibraciones"
            )
            for elem_name, elem_def in app_data.items():
                assert isinstance(elem_def, dict), (
                    f"app '{app_key}' / '{elem_name}' no es un dict"
                )
                for screen_key, value in elem_def.items():
                    assert str(screen_key).lower().startswith("s"), (
                        f"app '{app_key}' / '{elem_name}': clave inesperada '{screen_key}' "
                        "(se esperaba s1, s2, ...)"
                    )
                    assert isinstance(value, (list, tuple)) and len(value) >= 2, (
                        f"app '{app_key}' / '{elem_name}' / '{screen_key}': valor no es lista de coordenadas"
                    )

    def test_calibraciones_entries_have_no_knowledge_fields(self):
        """Las entradas de ``calibraciones`` no tienen campos de conocimiento."""
        data = _load_macros_coords()
        calibraciones = data["calibraciones"]
        knowledge_keys = {"type", "description", "calibration_strategy", "alternatives", "confidence"}
        for app_key, app_data in calibraciones.items():
            for elem_name, elem_def in app_data.items():
                for key in knowledge_keys:
                    assert key not in elem_def, (
                        f"app '{app_key}' / '{elem_name}': '{key}' no debe estar en calibraciones "
                        "(es campo de conocimiento, no de coordenadas)"
                    )


# ---------------------------------------------------------------------------
# 3. CoordinateManager: conocimiento sin coordenadas
# ---------------------------------------------------------------------------
class TestCoordinateManagerKnowledgeWithoutCoordinates:
    """_create_resource_from_knowledge crea recursos sin coordenadas."""

    def test_create_resource_from_knowledge_no_coordinates(self):
        """Sin ``screens`` en element_data, el recurso no tiene coordenadas ni esta calibrado."""
        from src.hands.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        element_data = {
            "type": "input",
            "description": "Barra de direcciones",
            "calibration_strategy": "visual_detection",
            "alternatives": ["chrome.hotkey_ctrl_l"],
            "confidence": 0.9,
        }
        resource = cm._create_resource_from_knowledge(
            "chrome.address_bar", "chrome", "address_bar", element_data
        )
        assert resource is not None
        assert resource.element_type == "input"
        assert resource.description == "Barra de direcciones"
        assert resource.calibration_strategy.value == "visual_detection"
        assert resource.alternatives == ["chrome.hotkey_ctrl_l"]
        assert resource.confidence == 0.9
        assert resource.calibrated_coordinates == {}
        assert resource.calibrated_regions == {}
        assert resource.is_calibrated is False
        assert resource.is_available is False

    def test_create_resource_from_knowledge_ignores_screens_if_present(self):
        """Aunque element_data traiga ``screens`` (retrocompatibilidad), el
        metodo no los usa como coordenadas."""
        from src.hands.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        element_data = {
            "type": "button",
            "description": "Botón",
            "screens": {"s1": [100, 200]},
        }
        resource = cm._create_resource_from_knowledge(
            "app.btn", "app", "btn", element_data
        )
        assert resource is not None
        assert resource.calibrated_coordinates == {}
        assert resource.is_calibrated is False


# ---------------------------------------------------------------------------
# 4. CoordinateManager: carga de calibraciones y fusion
# ---------------------------------------------------------------------------
class TestCoordinateManagerLoadCalibraciones:
    """load_from_macros_coords carga calibraciones y fusiona con conocimiento."""

    def test_load_from_macros_coords_loads_calibraciones(self):
        """Las coordenadas de ``calibraciones`` se cargan y fusionan."""
        from src.hands.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        # Primero registrar un recurso de conocimiento (sin coordenadas)
        knowledge_data = {
            "type": "input",
            "description": "Barra de direcciones",
            "calibration_strategy": "visual_detection",
            "alternatives": ["chrome.hotkey_ctrl_l"],
            "confidence": 0.9,
        }
        res_knowledge = cm._create_resource_from_knowledge(
            "chrome.address_bar", "chrome", "address_bar", knowledge_data
        )
        cm.register_ui_resource(res_knowledge)
        assert cm.get_ui_resource("chrome.address_bar").is_calibrated is False

        # Cargar calibraciones
        data = _load_macros_coords()
        loaded = cm.load_from_macros_coords(data)
        assert loaded > 0, "debe cargar al menos un recurso de calibraciones"

        merged = cm.get_ui_resource("chrome.address_bar")
        assert merged is not None
        # Campos de conocimiento conservados
        assert merged.description == "Barra de direcciones"
        assert merged.element_type == "input"
        assert merged.alternatives == ["chrome.hotkey_ctrl_l"]
        assert merged.confidence == 0.9
        # Coordenadas fusionadas desde calibraciones
        assert merged.calibrated_coordinates != {}, (
            "debe tener coordenadas tras cargar calibraciones"
        )
        assert merged.is_calibrated is True
        assert merged.is_available is True

    def test_load_from_macros_coords_legacy_fallback_for_uncovered(self):
        """Entradas solo en legacy_data.macros (no en calibraciones) siguen cargándose."""
        from src.hands.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        data = _load_macros_coords()
        loaded = cm.load_from_macros_coords(data)
        # supercomplete.sc_button solo está en legacy, no en calibraciones ni ui_knowledge
        res = cm.get_ui_resource("supercomplete.sc_button")
        assert res is not None, "supercomplete.sc_button debe cargarse desde legacy"
        assert res.calibrated_coordinates != {}, (
            "supercomplete.sc_button debe tener coordenadas"
        )
        assert res.is_calibrated is True

    def test_get_calibrated_coordinate_uses_merged_resource(self):
        """get_calibrated_coordinate devuelve coordenadas del recurso fusionado."""
        from src.hands.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        data = _load_macros_coords()
        cm.load_from_macros_coords(data)

        coord = cm.get_calibrated_coordinate(data, "chrome", "address_bar", screen_number=1)
        assert coord == (3582, 339), f"esperado (3582, 339), obtenido {coord}"

        coord2 = cm.get_calibrated_coordinate(data, "chrome", "address_bar", screen_number=2)
        assert coord2 == (7447, 335), f"esperado (7447, 335), obtenido {coord2}"
