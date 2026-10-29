# -*- coding: utf-8 -*-
"""Tests de verificacion de la estructura REAL de ``ui_elements`` — unidad 3.4.2.1
(FASE 3.4.2 — UI elements).

Verifica el formato REAL (no el esperado) de ``ui_elements`` en las capas
siguientes, documentando discrepancias de formato sin modificar codigo de
produccion:

1. ``data/knowledge/applications.json``: dict-of-dicts con ``{type, description}``
   por elemento (conocido, declarativo, leido por DomainMemory).
2. ``UIElement`` (dataclass en ``applications_core.py``): NO tiene campo
   ``description`` — se pierde la descripcion del JSON conocimiento.
3. ``_reconstruct_ui_elements``: espera una **lista** de dicts (``name+type``);
   si recibe el dict-of-dicts del JSON devuelve ``[]`` (elementos perdidos).
4. ``register_application`` / ``_serialize_ui_element``: serializan a lista de
   dicts SIN ``description``.
5. ``get_application_ui_elements``: devuelve dict-of-dicts SIN ``description``.
6. ``application_integration.py`` ``_create_ui_element_node``: consume
   dict-of-dicts (compatible con el JSON).
7. Estado en runtime (``WorldState`` / ``ExecutionState``): dict-of-dicts.

No modifica codigo de produccion. La lectura de ficheros usa rutas absolutas
(get_project_root) y el runtime se verifica con el modelo real cuando procede.
"""

import dataclasses
import json

import pytest

from src.utils.config import get_project_root
from src.hands.applications_core import (
    UIElement,
    ApplicationKnowledge,
    ApplicationManager,
    _serialize_ui_element,
    UIElement as UIE,
)
from src.hands.applications_core import get_application_manager


# ---------------------------------------------------------------------------
# Rutas absolutas (read-only)
# ---------------------------------------------------------------------------
PROJECT_ROOT = get_project_root()
KNOWLEDGE_APPLICATIONS_PATH = (
    PROJECT_ROOT / "data" / "knowledge" / "applications.json"
)


@pytest.fixture(autouse=True, scope="module")
def _suppress_system_logs():
    import logging
    logging.disable(logging.CRITICAL)
    yield


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _load_knowledge_apps():
    """Carga raw de data/knowledge/applications.json (read-only)."""
    return json.loads(
        KNOWLEDGE_APPLICATIONS_PATH.read_text(encoding="utf-8")
    )


# ===========================================================================
# 1. Estructura REAL de ui_elements en data/knowledge/applications.json
# ===========================================================================
class TestKnowledgeJsonUiElementsStructure:
    """Verifica la estructura REAL de ``ui_elements`` en el fichero de
    conocimiento declarativo.

    El formato real es **dict-of-dicts**: la clave externa es el nombre del
    elemento y el valor es un dict con exactamente ``{type, description}``.
    """

    def test_file_exists(self):
        assert KNOWLEDGE_APPLICATIONS_PATH.exists()

    def test_all_apps_have_ui_elements(self):
        """Todas las aplicaciones conocidas declaran ui_elements."""
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            assert "ui_elements" in app_data, (
                f"app '{app_key}' no tiene clave 'ui_elements'"
            )

    def test_ui_elements_is_dict_of_dicts_across_all_apps(self):
        """En TODAS las apps, ui_elements es un dict-of-dicts (no una lista).

        Contrario al formato esperado por ``_reconstruct_ui_elements``
        (que pide lista) y por ``UIElement`` (modelo tipo list).
        """
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            ui_elements = app_data["ui_elements"]
            assert isinstance(ui_elements, dict), (
                f"app '{app_key}': ui_elements debe ser dict, "
                f"got {type(ui_elements).__name__}"
            )
            for elem_name, elem_def in ui_elements.items():
                assert isinstance(elem_def, dict), (
                    f"app '{app_key}' / '{elem_name}': "
                    f"elemento debe ser dict, got {type(elem_def).__name__}"
                )

    def test_each_element_has_exactly_type_and_description(self):
        """Cada elemento del JSON tiene EXACTAMENTE las claves {type, description}.

        La estructura real NO incluye 'name' como clave interna: el nombre
        es la clave externa del dict.
        """
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            for elem_name, elem_def in app_data["ui_elements"].items():
                assert set(elem_def.keys()) == {"type", "description"}, (
                    f"app '{app_key}' / '{elem_name}': "
                    f"expected {{type, description}}, got {set(elem_def.keys())}"
                )

    def test_type_is_non_empty_string_for_all_elements(self):
        """El campo 'type' es un string no vacio en todos los elementos."""
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            for elem_name, elem_def in app_data["ui_elements"].items():
                assert isinstance(elem_def["type"], str)
                assert elem_def["type"].strip() != "", (
                    f"app '{app_key}' / '{elem_name}': type vacio"
                )

    def test_description_is_non_empty_string_for_all_elements(self):
        """El campo 'description' es un string no vacio en todos los elementos.

        La descripcion existe en el JSON de conocimiento PERO el modelo
        ``UIElement`` no la preserva (ver TestUIElementModelFields).
        """
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            for elem_name, elem_def in app_data["ui_elements"].items():
                assert isinstance(elem_def["description"], str)
                assert elem_def["description"].strip() != "", (
                    f"app '{app_key}' / '{elem_name}': description vacia"
                )

    def test_element_names_match_calibration_needed(self):
        """Los elementos referenciados en 'calibration_needed' existen en
        'ui_elements' en todas las apps donde aplica."""
        data = _load_knowledge_apps()
        for app_key, app_data in data.items():
            calibration_needed = app_data.get("calibration_needed", [])
            ui_element_names = set(app_data["ui_elements"].keys())
            for needed_elem in calibration_needed:
                assert needed_elem in ui_element_names, (
                    f"app '{app_key}': '{needed_elem}' en calibration_needed "
                    f"pero no existe en ui_elements"
                )

    def test_specific_element_names_per_app(self):
        """Verifica los nombres de elementos UI conocidos por app."""
        data = _load_knowledge_apps()
        assert set(data["chrome"]["ui_elements"].keys()) == {
            "address_bar", "new_tab_button", "refresh_button",
            "back_button", "forward_button",
        }
        assert set(data["spotify"]["ui_elements"].keys()) == {
            "search_bar", "play_button", "next_button", "previous_button",
        }
        assert set(data["vscode"]["ui_elements"].keys()) == {
            "explorer", "editor", "terminal",
        }
        assert set(data["obs_studio"]["ui_elements"].keys()) == {
            "controls", "sources", "scenes",
        }

    def test_chrome_address_bar_structure(self):
        """El elemento 'address_bar' de chrome: {type: input, description: ...}."""
        data = _load_knowledge_apps()
        elem = data["chrome"]["ui_elements"]["address_bar"]
        assert elem["type"] == "input"
        assert isinstance(elem["description"], str)
        assert len(elem["description"]) > 0


# ===========================================================================
# 2. Modelo UIElement — ausencia del campo 'description'
# ===========================================================================
class TestUIElementModelFields:
    """Verifica los campos REALES del modelo ``UIElement`` y documenta que
    ``description`` (presente en el JSON de conocimiento) NO es un campo del
    modelo, por lo que se pierde al reconstruir objetos UIElement.

    Discrepancia D-UI-DESCRIPTION-LOST.
    """

    def test_uint_element_fields(self):
        """UIElement tiene exactamente estos campos (en orden deDeclaracion)."""
        fields = [f.name for f in dataclasses.fields(UIElement)]
        assert fields == [
            "name", "type", "coordinates", "screen",
            "calibration_data", "required_capability",
        ]

    def test_description_is_not_a_field(self):
        """'description' NO es un campo del modelo UIElement."""
        field_names = {f.name for f in dataclasses.fields(UIElement)}
        assert "description" not in field_names, (
            "UIElement no deberia tener 'description' como campo "
            "(D-UI-DESCRIPTION-LOST: se pierde la descripcion del JSON)"
        )

    def test_application_knowledge_ui_elements_is_optional_list(self):
        """ApplicationKnowledge.ui_elements esta tipado como
        Optional[List[UIElement]] — una LISTA, no un dict.

        Esto es incompatible con el formato dict-of-dicts usado en el
        JSON de conocimiento (D-UI-FORMAT-MISMATCH).
        """
        fields = {f.name: f for f in dataclasses.fields(ApplicationKnowledge)}
        ui_elements_field = fields["ui_elements"]
        # Con from __future__ import annotations, el tipo se guarda como cadena.
        assert ui_elements_field.type == "Optional[List[UIElement]]"


# ===========================================================================
# 3. _reconstruct_ui_elements — formato esperado (lista) vs JSON (dict)
# ===========================================================================
class TestReconstructUiElementsFormatMismatch:
    """Documenta D-UI-FORMAT-MISMATCH: ``_reconstruct_ui_elements`` espera una
    LISTA de dicts (cada uno con 'name' y 'type'), pero el JSON de conocimiento
    usa un DICT-of-dicts. Si se pasara el formato del JSON, todos los
    elementos se perderian silenciosamente.
    """

    def test_reconstruct_returns_empty_for_dict_format(self):
        """Si recibe el dict-of-dicts del JSON, devuelve [] (elementos perdidos).

        El codigo comprueba ``isinstance(elements_data, list)``; un dict no
        pasa ese filtro.
        """
        data = _load_knowledge_apps()
        chrome_ui = data["chrome"]["ui_elements"]
        result = ApplicationManager._reconstruct_ui_elements(chrome_ui)
        assert result == [], (
            "_reconstruct_ui_elements ignora el formato dict-of-dicts del JSON; "
            "si cambiara, perderia todos los elementos UI declarados"
        )

    def test_reconstruct_works_with_list_of_dicts(self):
        """El formato que expecta el codigo: lista de dicts con name+type."""
        list_format = [
            {"name": "address_bar", "type": "input"},
            {"name": "new_tab_button", "type": "button"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(list_format)
        assert len(result) == 2
        assert result[0].name == "address_bar"
        assert result[0].type == "input"
        assert result[1].name == "new_tab_button"
        assert result[1].type == "button"

    def test_reconstruct_drops_description_field(self):
        """Ni siquiera con formato lista, _reconstruct_ui_elements captura
        'description' — UIElement no tiene ese campo (D-UI-DESCRIPTION-LOST)."""
        list_format = [
            {"name": "address_bar", "type": "input", "description": "Barra de direcciones"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(list_format)
        assert len(result) == 1
        elem = result[0]
        assert not hasattr(elem, "description"), (
            "UIElement no preserva 'description' aun cuando el dict lo incluya"
        )

    def test_reconstruct_skips_items_without_name(self):
        """Items sin 'name' se omiten silenciosamente."""
        items = [
            {"type": "button"},  # sin name -> omitido
            {"name": "ok", "type": "button"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].name == "ok"

    def test_reconstruct_skips_items_without_type(self):
        """Items sin 'type' se omiten silenciosamente."""
        items = [
            {"name": "ok"},  # sin type -> omitido
            {"name": "btn", "type": "button"},
        ]
        result = ApplicationManager._reconstruct_ui_elements(items)
        assert len(result) == 1
        assert result[0].name == "btn"

    def test_reconstruct_returns_empty_for_non_list(self):
        """Cualquier entrada que no sea lista devuelve []."""
        for bad_input in [None, "string", 42, {"a": {"type": "b"}}]:
            result = ApplicationManager._reconstruct_ui_elements(bad_input)
            assert result == []


# ===========================================================================
# 4. _serialize_ui_element — salida NO incluye 'description'
# ===========================================================================
class TestSerializeUiElementFormat:
    """Documenta que ``_serialize_ui_element`` (usado por register_application
    para persistir entities) NO incluye 'description', coincidiendo con el
    modelo UIElement que tampoco lo tiene.
    """

    def test_serialize_output_keys(self):
        """_serialize_ui_element produce: name, type, coordinates, screen,
        calibration_data, required_capability (NO description)."""
        elem = UIElement(
            name="address_bar",
            type="input",
            coordinates=None,
            screen=0,
            calibration_data=None,
            required_capability=None,
        )
        serialized = _serialize_ui_element(elem)
        assert set(serialized.keys()) == {
            "name", "type", "coordinates", "screen",
            "calibration_data", "required_capability",
        }
        assert "description" not in serialized


# ===========================================================================
# 5. get_application_ui_elements — salida REAL (dict-of-dicts, sin description)
# ===========================================================================
class TestGetApplicationUiElementsOutputFormat:
    """Verifica el formato REAL de salida de ``get_application_ui_elements``
    sobre el modelo real (Chrome/Spotify hardcodeadas).

    La salida es dict-of-dicts (clave = nombre de elemento) con claves
    {type, coordinates, screen, is_calibrated, required_capability,
    calibration_data} — NO incluye 'description'.
    """

    def test_chrome_ui_elements_format(self):
        """get_application_ui_elements('chrome') devuelve dict-of-dicts sin
        'description' y sin 'name' interno (el nombre es la clave)."""
        manager = get_application_manager()
        elems = manager.get_application_ui_elements("chrome")
        assert isinstance(elems, dict)
        assert "address_bar" in elems
        assert "search_bar" in elems
        assert "new_tab_button" in elems
        for elem_name, elem_def in elems.items():
            assert isinstance(elem_def, dict)
            assert set(elem_def.keys()) == {
                "type", "coordinates", "screen",
                "is_calibrated", "required_capability", "calibration_data",
            }, (
                f"elem '{elem_name}': keys inesperadas "
                f"{set(elem_def.keys())}"
            )
            assert "description" not in elem_def, (
                f"elem '{elem_name}': 'description' no deberia estar presente "
                f"(D-UI-DESCRIPTION-LOST en get_application_ui_elements)"
            )

    def test_spotify_has_play_button(self):
        """Spotify expone 'play_button' como elemento UI."""
        manager = get_application_manager()
        elems = manager.get_application_ui_elements("spotify")
        assert "play_button" in elems
        assert elems["play_button"]["type"] == "button"


# ===========================================================================
# 6. application_integration._create_ui_element_node — consume dict-of-dicts
# ===========================================================================
class TestApplicationIntegrationUiElementsAsDict:
    """Verifica que ``_create_ui_element_node`` consume ``ui_elements`` como
    dict-of-dicts (compatible con el formato del JSON de conocimiento y con
    la salida de ``get_application_ui_elements``).

    Contrario a ``_reconstruct_ui_elements`` que espera lista.
    """

    def test_create_ui_element_node_reads_dict(self):
        """El integrador lee ui_elements como dict (get via .get(element_name))."""
        from src.hands.planner.application_integration import (
            ApplicationKnowledgeIntegrator,
        )
        integrator = ApplicationKnowledgeIntegrator.__new__(
            ApplicationKnowledgeIntegrator
        )
        # Minimal app mock with dict-format ui_elements (como el JSON).
        class _FakeApp:
            name = "TestApp"
            def get_ui_element(self, element_name):
                return None
        app = _FakeApp()
        cap_def = {"capability": "navigate"}
        # Build node from dict-format ui_elements (like applications.json).
        result = integrator._create_ui_element_node(app, "address_bar", cap_def)
        # The node is created; element is None (no getter match) -> RESOURCE.
        assert result is not None
        assert result.id == "testapp_address_bar"

    def test_create_ui_element_node_finds_element_in_dict(self):
        """Cuando ui_elements es un dict y el elemento existe, se encuentra."""
        from src.hands.planner.application_integration import (
            ApplicationKnowledgeIntegrator,
        )
        integrator = ApplicationKnowledgeIntegrator.__new__(
            ApplicationKnowledgeIntegrator
        )
        app = type("FakeApp", (), {
            "name": "Chrome",
            "ui_elements": {
                "address_bar": {"type": "input", "description": "..."},
            },
        })()
        cap_def = {"capability": "navigate"}
        result = integrator._create_ui_element_node(app, "address_bar", cap_def)
        # Node type should be UI_ELEMENT (not RESOURCE) because element found.
        from src.hands.planner.node import NodeType
        assert result.type == NodeType.UI_ELEMENT
        assert result.parameters.get("type") == "input"


# ===========================================================================
# 7. Estado en runtime — WorldState y ExecutionState usan dict-of-dicts
# ===========================================================================
class TestRuntimeStateUiElementsFormat:
    """Verifica que los estados en runtime (WorldState y ExecutionState)
    tipan ``ui_elements`` como ``Dict[str, Dict[str, Any]]`` (dict-of-dicts),
    lo que coincide con el formato del JSON de conocimiento pero NO con el
    modelo ``ApplicationKnowledge.ui_elements`` (List[UIElement]).
    """

    def test_world_state_ui_elements_is_dict_type(self):
        """WorldState.ui_elements: Dict[str, Dict[str, Any]].

        No usa from __future__ import annotations, asi que el tipo es un
        objeto real (no cadena).
        """
        from src.memory.storage import WorldState
        from typing import Dict, Any
        fields = {f.name: f for f in dataclasses.fields(WorldState)}
        ui_field = fields["ui_elements"]
        assert ui_field.type == Dict[str, Dict[str, Any]]

    def test_execution_state_ui_elements_is_dict_type(self):
        """ExecutionState.ui_elements: Dict[str, Dict[str, Any]].

        executor.py usa from __future__ import annotations, asi que el tipo
        se guarda como cadena.
        """
        from src.hands.executor import ExecutionState
        fields = {f.name: f for f in dataclasses.fields(ExecutionState)}
        ui_field = fields["ui_elements"]
        assert ui_field.type == "Dict[str, Dict[str, Any]]"


# ===========================================================================
# 8. Vision.detect_ui_elements — formato de deteccion runtime
# ===========================================================================
class TestVisionDetectUiElementsFormat:
    """Verifica el formato REAL que produce ``detect_ui_elements`` en vision.py:
    dict-of-dicts con claves {name, type, text, interactive, monitor}.

    Este es el tercer formato distinto de ui_elements en el sistema.
    """

    def test_detect_ui_elements_node_format(self):
        """El nodo vision.detect_ui_elements declara efecto
        'ui_elements_detected' y funcion 'detect_ui_elements'.

        El output en runtime es un dict-of-dicts con claves
        {name, type, text, interactive, monitor} — un tercer formato
        distinto al del JSON de conocimiento y al del modelo UIElement.
        """
        from src.eyes.vision import Vision
        vision = Vision()
        node = vision.get_vision_node("vision.detect_ui_elements")
        assert node is not None
        assert node.id == "vision.detect_ui_elements"
        assert "ui_elements_detected" in node.effects
        assert node.execute_function == "detect_ui_elements"
