"""
Tests unitarios (deterministas, sin SO ni GUI) de evaluate_presence y
ElementPresence - unidad 3.8.6.11.1 del roadmap.

Cubren para src/hands/calibration/dynamic_ui.py:
- nodo ausente: in_tree=False, visible=False, enabled=False, interactable_now=False
- nodo presente, visible, habilitado, con accion, ventana en primer plano,
  caja dentro del monitor y de la ventana: in_tree/visible/enabled/interactable_now True
- fuera de pantalla: visible=False
- no visible: visible=False
- deshabilitado: enabled=False
- ventana minimizada u oculta: visible=False
- ventana no en primer plano: interactable_now=False
- sin accion disponible: interactable_now=False
- caja parcialmente fuera del monitor: interactable_now=False
- caja fuera de la ventana: visible=False
- serializacion to_dict

Funcion puramente determinista sobre AccessibilityNode, WindowInfo y
DisplayInfo: se verifica con datos representativos y no requiere OS ni GUI.
"""

from __future__ import annotations

import unittest

from src.desktop.accessibility_model import AccessibilityNode
from src.desktop.platform_contract import DisplayInfo, Rect, WindowInfo
from src.hands.calibration.dynamic_ui import ElementPresence, evaluate_presence


def _node(
    enabled=True,
    visible=True,
    offscreen=False,
    actions=None,
    bbox=None,
    native_role="Button",
    name="Aceptar",
):
    return AccessibilityNode(
        node_id="n1",
        control_type="button",
        native_role=native_role,
        name=name,
        identifier="btnAceptar",
        bbox=bbox,
        enabled=enabled,
        visible=visible,
        offscreen=offscreen,
        actions=list(actions or []),
        source="uia",
    )


def _window(is_visible=True, is_minimized=False, is_foreground=True, bounds=None):
    b = bounds or Rect(0, 0, 1000, 800)
    return WindowInfo(
        window_id=1001,
        pid=100,
        title="Notepad",
        app_identity="notepad",
        bounds=b,
        frame_bounds=b,
        is_visible=is_visible,
        is_minimized=is_minimized,
        is_foreground=is_foreground,
        display_id="d1",
        scale_factor=1.0,
        dpi=96,
        coordinate_space="DESKTOP_PIXELS",
    )


def _display():
    r = Rect(0, 0, 1920, 1080)
    return DisplayInfo(
        display_id="d1",
        name="Monitor",
        bounds=r,
        work_area=r,
        pixel_width=1920,
        pixel_height=1080,
        scale_factor=1.0,
        dpi=96,
        is_primary=True,
        coordinate_space="DESKTOP_PIXELS",
    )


class TestNodoAusente(unittest.TestCase):
    def test_nodo_none_no_presente_en_arbol(self):
        p = evaluate_presence(None, _window(), [_display()], True)
        self.assertFalse(p.in_tree)
        self.assertFalse(p.visible)
        self.assertFalse(p.enabled)
        self.assertFalse(p.interactable_now)
        self.assertIn("no_presente_en_arbol", p.reasons)

    def test_element_presence_valores_por_defecto(self):
        p = ElementPresence(False, False, False, False, ["no_presente_en_arbol"])
        self.assertFalse(p.in_tree)
        self.assertFalse(p.visible)
        self.assertFalse(p.enabled)
        self.assertFalse(p.interactable_now)
        self.assertEqual(p.reasons, ["no_presente_en_arbol"])


class TestNodoPresenteInteractuable(unittest.TestCase):
    def test_nodo_presente_visible_habilitado_interactuable_ahora(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertTrue(p.in_tree)
        self.assertTrue(p.visible)
        self.assertTrue(p.enabled)
        self.assertTrue(p.interactable_now)
        self.assertEqual(p.reasons, [])

    def test_to_dict_serializa_cinco_campos(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        d = p.to_dict()
        self.assertEqual(d["in_tree"], True)
        self.assertEqual(d["visible"], True)
        self.assertEqual(d["enabled"], True)
        self.assertEqual(d["interactable_now"], True)
        self.assertEqual(d["reasons"], [])


class TestVisible(unittest.TestCase):
    def test_fuera_de_pantalla_no_visible(self):
        node = _node(bbox=Rect(100, 100, 200, 200), offscreen=True, actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertTrue(p.in_tree)
        self.assertFalse(p.visible)
        self.assertIn("fuera_de_pantalla", p.reasons)

    def test_no_visible_no_visible(self):
        node = _node(bbox=Rect(100, 100, 200, 200), visible=False, actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertFalse(p.visible)
        self.assertIn("no_visible", p.reasons)

    def test_ventana_minimizada_no_visible(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=["invoke"])
        p = evaluate_presence(node, _window(is_minimized=True), [_display()], True)
        self.assertFalse(p.visible)
        self.assertIn("ventana_minimizada", p.reasons)

    def test_ventana_oculta_no_visible(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=["invoke"])
        p = evaluate_presence(node, _window(is_visible=False), [_display()], True)
        self.assertFalse(p.visible)
        self.assertIn("ventana_oculta", p.reasons)

    def test_caja_fuera_de_la_ventana_no_visible(self):
        node = _node(bbox=Rect(2000, 2000, 2100, 2100), actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertFalse(p.visible)
        self.assertIn("fuera_de_la_ventana", p.reasons)

    def test_caja_parcialmente_fuera_del_monitor_visible_pero_no_interactuable(self):
        node = _node(bbox=Rect(1900, 1000, 2000, 1100), actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertFalse(p.interactable_now)
        self.assertIn("parcialmente_fuera_de_monitor", p.reasons)


class TestHabilitado(unittest.TestCase):
    def test_control_deshabilitado_no_habilitado(self):
        node = _node(bbox=Rect(100, 100, 200, 200), enabled=False, actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertFalse(p.enabled)
        self.assertFalse(p.interactable_now)
        self.assertIn("deshabilitado", p.reasons)


class TestInteractuableAhora(unittest.TestCase):
    def test_ventana_no_en_primer_plano_no_interactuable_ahora(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=["invoke"])
        p = evaluate_presence(node, _window(), [_display()], False)
        self.assertTrue(p.visible)
        self.assertTrue(p.enabled)
        self.assertFalse(p.interactable_now)
        self.assertIn("ventana_no_en_primer_plano", p.reasons)

    def test_sin_accion_disponible_no_interactuable(self):
        node = _node(bbox=Rect(100, 100, 200, 200), actions=[], native_role="StaticText")
        p = evaluate_presence(node, _window(), [_display()], True)
        self.assertFalse(p.interactable_now)
        self.assertIn("sin_accion_disponible", p.reasons)


if __name__ == "__main__":
    unittest.main()
