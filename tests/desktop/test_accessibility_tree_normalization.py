# -*- coding: utf-8 -*-
"""Tests de normalizacion del arbol de accesibilidad (unidad 3.8.6.5.6).

Verifica que el arbol de accesibilidad de Windows (UI Automation) y de
macOS (AXUIElement) se normaliza al unico modelo canonico ``UIElementData``
con: tipo de control, nombre, identificador, caja, habilitado, visible y
acciones disponibles, conservando el rol nativo original como dato.

Todas las pruebas son deterministas y usan datos sinteticos. No abren
ventanas, no capturan pantalla ni llaman a APIs nativas del SO.
"""

from src.core.ui_element_model import UIElementData, ElementClassification
from src.desktop.accessibility_model import (
    AccessibilityTree,
    build_tree,
    normalize_ax_attributes,
    normalize_uia_element,
    normalize_uia_tree,
)
from src.desktop.platform_contract import DESKTOP_POINTS, DESKTOP_PIXELS, Rect


# ---------------------------------------------------------------------------
# Sinteticos Windows UIA
# ---------------------------------------------------------------------------


class _FakeUIAElement:
    """Simula un elemento de UI Automation con los atributos que lee
    ``normalize_uia_element`` (sin importar pywinauto)."""


def _make_uia_element(
    control_type="Button",
    automation_id="btnOk",
    name="Aceptar",
    runtime_id=(42, 101),
    handle=12345,
    parent_handle=100,
    class_name="Button",
    framework_id="Win32",
    control_id=7,
    process_id=999,
    depth=2,
    framework="Win32",
    patterns=None,
    bounding_rectangle=(10, 20, 110, 60),
    is_enabled=True,
    visible=True,
    is_offscreen=False,
):
    if patterns is None:
        patterns = ["Invoke", "Value"]
    el = _FakeUIAElement()
    el.control_type = control_type
    el.automation_id = automation_id
    el.name = name
    el.runtime_id = runtime_id
    el.handle = handle
    el.parent_handle = parent_handle
    el.class_name = class_name
    el.framework_id = framework_id
    el.control_id = control_id
    el.process_id = process_id
    el.depth = depth
    el.framework = framework
    el.patterns = patterns
    el.bounding_rectangle = bounding_rectangle
    el.is_enabled = is_enabled
    el.visible = visible
    el.is_offscreen = is_offscreen
    return el


class _FakeUiaTree:
    def __init__(self, elements, window_handle=55, process_id=999, truncated=False, error=None, elapsed_seconds=0.0):
        self.window_handle = window_handle
        self.elements = elements
        self.process_id = process_id
        self.truncated = truncated
        self.error = error
        self.elapsed_seconds = elapsed_seconds


# ---------------------------------------------------------------------------
# Sinteticos macOS AX
# ---------------------------------------------------------------------------


def _make_ax_attributes(
    role="AXButton",
    subrole="",
    title="Aceptar",
    identifier="axBtn1",
    position=(15.5, 25.5),
    size=(100.0, 40.0),
    enabled=True,
    hidden=False,
    focusable=True,
    actions=None,
    value_settable=False,
    onscreen=True,
):
    actions = actions or ["AXPress"]
    return {
        "AXRole": role,
        "AXSubrole": subrole,
        "AXTitle": title,
        "AXIdentifier": identifier,
        "AXValue": "",
        "AXPosition": list(position),
        "AXSize": list(size),
        "AXEnabled": enabled,
        "AXHidden": hidden,
        "_focusable": focusable,
        "_actions": actions,
        "_value_settable": value_settable,
        "_onscreen": onscreen,
    }


# ===========================================================================
# Normalizacion de un nodo Windows UIA -> UIElementData
# ===========================================================================


class TestUiaNodeToUiElementData:
    def test_todos_los_campos_del_modelo_unico(self):
        el = _make_uia_element()
        node = normalize_uia_element(el, window_id=55, parent_id=None)
        data = node.to_ui_element_data()

        assert isinstance(data, UIElementData)
        assert data.type == "button"
        assert data.name == "Aceptar"
        assert data.identifier == "btnOk"
        assert data.bbox == [10, 20, 110, 60]
        assert data.visible is True
        assert data.enabled is True
        assert data.actions == ["invoke", "set_value"]
        assert data.interactive is True
        assert data.classification == ElementClassification.UIA_ACTIONABLE
        assert data.calibration_data["native_role"] == "Button"
        assert data.calibration_data["source"] == "uia"
        assert data.calibration_data["coordinate_space"] == DESKTOP_PIXELS

    def test_control_deshabilitado_se_clasifica_como_disabled(self):
        el = _make_uia_element(is_enabled=False, visible=True)
        node = normalize_uia_element(el, window_id=55, parent_id=None)
        data = node.to_ui_element_data()
        assert data.enabled is False
        assert data.classification == ElementClassification.DISABLED

    def test_elemento_fuera_de_pantalla_se_clasifica_como_offscreen(self):
        el = _make_uia_element(is_enabled=True, visible=False, is_offscreen=True)
        node = normalize_uia_element(el, window_id=55, parent_id=None)
        data = node.to_ui_element_data()
        assert data.visible is False
        assert data.classification == ElementClassification.OFFSCREEN

    def test_elemento_sin_acciones_no_es_accionable(self):
        el = _make_uia_element(patterns=[], bounding_rectangle=(10, 20, 110, 60))
        node = normalize_uia_element(el, window_id=55, parent_id=None)
        data = node.to_ui_element_data()
        assert data.actions == []
        assert data.interactive is False
        assert data.classification != ElementClassification.UIA_ACTIONABLE

    def test_caja_invalida_se_descarta(self):
        el = _make_uia_element(bounding_rectangle=(10, 20, 5, 6))  # degenerate
        node = normalize_uia_element(el, window_id=55, parent_id=None)
        data = node.to_ui_element_data()
        assert data.bbox is None


# ===========================================================================
# Normalizacion de un nodo macOS AX -> UIElementData
# ===========================================================================


class TestAxNodeToUiElementData:
    def test_todos_los_campos_del_modelo_unico(self):
        attrs = _make_ax_attributes()
        node = normalize_ax_attributes(
            attrs, window_id=55, pid=999, parent_id=None, depth=1, path="0.1"
        )
        data = node.to_ui_element_data()

        assert isinstance(data, UIElementData)
        assert data.type == "button"
        assert data.name == "Aceptar"
        assert data.identifier == "axBtn1"
        assert data.bbox == [16, 26, 116, 66]
        assert data.visible is True
        assert data.enabled is True
        assert data.actions == ["invoke"]
        assert data.classification == ElementClassification.UIA_ACTIONABLE
        assert data.calibration_data["native_role"] == "AXButton"
        assert data.calibration_data["source"] == "ax"
        assert data.calibration_data["coordinate_space"] == DESKTOP_POINTS

    def test_rol_nativo_se_conserva_como_dato(self):
        attrs = _make_ax_attributes(role="AXCheckBox", identifier="chk1")
        node = normalize_ax_attributes(
            attrs, window_id=55, pid=999, parent_id=None, depth=0, path="0"
        )
        data = node.to_ui_element_data()
        assert data.calibration_data["native_role"] == "AXCheckBox"
        assert data.type == "checkbox"

    def test_elemento_oculto_no_es_visible(self):
        attrs = _make_ax_attributes(hidden=True, onscreen=False)
        node = normalize_ax_attributes(
            attrs, window_id=55, pid=999, parent_id=None, depth=0, path="0"
        )
        data = node.to_ui_element_data()
        assert data.visible is False


# ===========================================================================
# Arbol completo -> lista de UIElementData
# ===========================================================================


class TestTreeToUiElements:
    def test_uia_tree_a_lista_de_elementos(self):
        el1 = _make_uia_element(control_type="Button", name="Aceptar", automation_id="btn1")
        el2 = _make_uia_element(control_type="Edit", name="Nombre", automation_id="txt1")
        nodes = [
            normalize_uia_element(el1, window_id=55, parent_id=None),
            normalize_uia_element(el2, window_id=55, parent_id=None),
        ]
        tree = build_tree(
            window_id=55, pid=999, source="uia", nodes=nodes,
            coordinate_space=DESKTOP_PIXELS,
        )
        elements = tree.to_ui_elements()
        assert len(elements) == 2
        assert elements[0].type == "button"
        assert elements[0].name == "Aceptar"
        assert elements[1].type == "input"
        assert elements[1].name == "Nombre"
        for e in elements:
            assert isinstance(e, UIElementData)
            assert e.calibration_data["native_role"] in ("Button", "Edit")

    def test_ax_tree_a_lista_de_elementos(self):
        attrs1 = _make_ax_attributes(role="AXButton", title="Aceptar", identifier="b1")
        attrs2 = _make_ax_attributes(role="AXTextField", title="Nombre", identifier="t1")
        nodes = [
            normalize_ax_attributes(attrs1, window_id=55, pid=999, parent_id=None, depth=0, path="0"),
            normalize_ax_attributes(attrs2, window_id=55, pid=999, parent_id=None, depth=0, path="1"),
        ]
        tree = build_tree(
            window_id=55, pid=999, source="ax", nodes=nodes,
            coordinate_space=DESKTOP_POINTS,
        )
        elements = tree.to_ui_elements()
        assert len(elements) == 2
        assert elements[0].type == "button"
        assert elements[1].type == "input"
        for e in elements:
            assert e.calibration_data["source"] == "ax"
            assert e.calibration_data["coordinate_space"] == DESKTOP_POINTS

    def test_normalize_uia_tree_devuelve_accessibility_tree(self):
        el = _make_uia_element()
        tree = normalize_uia_tree(_FakeUiaTree([el]))
        assert isinstance(tree, AccessibilityTree)
        assert tree.source == "uia"
        assert tree.window_id == 55
        assert len(tree.nodes) == 1
        data = tree.to_ui_elements()[0]
        assert data.name == "Aceptar"
        assert data.identifier == "btnOk"


# ===========================================================================
# build_tree helper
# ===========================================================================


class TestBuildTree:
    def test_construye_arbol_con_nodos(self):
        node = normalize_uia_element(_make_uia_element(), window_id=55, parent_id=None)
        tree = build_tree(window_id=55, pid=999, source="uia", nodes=[node])
        assert tree.window_id == 55
        assert tree.pid == 999
        assert tree.source == "uia"
        assert tree.root_id == node.node_id
        assert len(tree.nodes) == 1
