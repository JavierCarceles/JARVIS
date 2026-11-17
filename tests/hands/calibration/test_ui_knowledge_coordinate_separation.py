# -*- coding: utf-8 -*-
"""Tests de verificacion de la separacion conocimiento UI / coordenadas concretas - unidad 3.4.2.3 (FASE 3.4.2 - UI elements).

Objetivo verificable: en el formato oficial de ``macros_coords.json`` el
conocimiento de UI (type, description, calibration_strategy, alternatives,
confidence) vive bajo ``ui_knowledge`` SIN coordenadas (sin ``screens``), y las
coordenadas concretas viven bajo la seccion ``calibraciones`` (solo claves de
pantalla y valores de coordenada). ``CoordinateManager`` carga el conocimiento
desde ``ui_knowledge``, las coordenadas desde ``calibraciones`` y las fusiona
por ``resource_id``.

``data/macros_coords.json`` es un fichero local de cada equipo (``data/`` esta
excluido del repositorio) y puede no existir, por lo que los tests usan el
fixture ``tests/hands/calibration/fixtures/macros_coords_formato_oficial.json``
con el formato oficial, y comprueban ademas que ``CoordinateManager`` arranca
sin error cuando el fichero no existe. No se lee ni se escribe ``data/``.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.calibration.coordinate_manager import CoordinateManager


MACROS_COORDS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "macros_coords_formato_oficial.json"
)


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
        """Ningun elemento de ``ui_knowledge`` incluye la clave ``screens``."""
        data = _load_macros_coords()
        ui_knowledge = data.get("ui_knowledge", {})
        assert isinstance(ui_knowledge, dict) and ui_knowledge, (
            "ui_knowledge debe estar presente y no vac\u00eda"
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
        from src.hands.calibration.coordinate_manager import CoordinateManager
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
        from src.hands.calibration.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        element_data = {
            "type": "button",
            "description": "Bot\u00f3n",
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
        from src.hands.calibration.coordinate_manager import CoordinateManager
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
        """Entradas solo en legacy_data.macros (no en calibraciones) siguen cargandose."""
        from src.hands.calibration.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        data = _load_macros_coords()
        loaded = cm.load_from_macros_coords(data)
        # supercomplete.sc_button solo esta en legacy, no en calibraciones ni ui_knowledge
        res = cm.get_ui_resource("supercomplete.sc_button")
        assert res is not None, "supercomplete.sc_button debe cargarse desde legacy"
        assert res.calibrated_coordinates != {}, (
            "supercomplete.sc_button debe tener coordenadas"
        )
        assert res.is_calibrated is True

    def test_get_calibrated_coordinate_uses_merged_resource(self):
        """get_calibrated_coordinate devuelve coordenadas del recurso fusionado."""
        from src.hands.calibration.coordinate_manager import CoordinateManager
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        data = _load_macros_coords()
        cm.load_from_macros_coords(data)

        coord = cm.get_calibrated_coordinate(data, "chrome", "address_bar", screen_number=1)
        assert coord == (3582, 339), f"esperado (3582, 339), obtenido {coord}"

        coord2 = cm.get_calibrated_coordinate(data, "chrome", "address_bar", screen_number=2)
        assert coord2 == (7447, 335), f"esperado (7447, 335), obtenido {coord2}"


# ---------------------------------------------------------------------------
# 5. CoordinateManager: carga desde el fichero (presente o ausente)
# ---------------------------------------------------------------------------
def _coordinate_manager_sin_init():
    """CoordinateManager con el estado que deja ``__init__`` antes de cargar
    el fichero (sin ScreenManager ni lectura de ``data/``)."""
    cm = CoordinateManager.__new__(CoordinateManager)
    cm.ui_resources = {}
    cm.ui_capabilities = {}
    cm.ui_knowledge = {}
    cm.calibration_policies = {}
    return cm


class TestCoordinateManagerLoadFromFile:
    """``_load_ui_knowledge`` lee la ruta ``macros_coords_path`` real del
    gestor (sustituida por el fixture o por una ruta inexistente)."""

    def test_carga_desde_fichero_fusiona_conocimiento_y_coordenadas(self):
        cm = _coordinate_manager_sin_init()
        with patch.object(
            CoordinateManager, "macros_coords_path", new=property(lambda self: MACROS_COORDS_PATH)
        ):
            cm._load_ui_knowledge()

        assert set(cm.ui_knowledge) == {"chrome", "spotify", "riot_api"}
        assert "blocked_applications" in cm.calibration_policies
        # Conocimiento + coordenadas de ``calibraciones`` fusionados.
        address_bar = cm.get_ui_resource("chrome.address_bar")
        assert address_bar is not None
        assert address_bar.description == "Barra de direcciones de Chrome"
        assert address_bar.alternatives == ["chrome.hotkey_ctrl_l"]
        assert address_bar.is_calibrated is True
        assert cm.get_calibrated_coordinate({}, "chrome", "address_bar", screen_number=1) == (3582, 339)
        # Cada elemento de ``ui_knowledge`` conserva su conocimiento y recibe
        # las coordenadas de su entrada en ``calibraciones``.
        play_button = cm.get_ui_resource("spotify.play_button")
        assert play_button is not None
        assert play_button.alternatives == ["spotify.hotkey_space"]
        assert play_button.is_calibrated is True
        assert cm.get_calibrated_coordinate({}, "spotify", "play_button", screen_number=2) == (5015, 1020)
        # Entrada solo legacy: se carga desde ``legacy_data.macros``.
        sc_button = cm.get_ui_resource("supercomplete.sc_button")
        assert sc_button is not None
        assert sc_button.is_calibrated is True

    def test_fichero_ausente_no_carga_nada_ni_lo_crea(self, tmp_path):
        ruta_inexistente = tmp_path / "macros_coords.json"
        cm = _coordinate_manager_sin_init()
        with patch.object(
            CoordinateManager, "macros_coords_path", new=property(lambda self: ruta_inexistente)
        ):
            cm._load_ui_knowledge()

        assert cm.ui_resources == {}
        assert cm.ui_knowledge == {}
        assert cm.calibration_policies == {}
        assert cm.get_ui_resource("chrome.address_bar") is None
        assert not ruta_inexistente.exists()
