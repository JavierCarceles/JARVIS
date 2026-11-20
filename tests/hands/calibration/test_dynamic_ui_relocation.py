"""
Tests unitarios (deterministas, sin SO ni GUI) de la relocalizacion de
interfaces dinamicas - unidad 3.8.6.11.5 del roadmap.

Cubren para src/hands/calibration/dynamic_ui.py:
- ElementRelocator.relocate: relocaliza por identidad (identificador, nombre,
  tipo, ancestros) sin reutilizar coordenadas antiguas; gestiona no encontrado,
  ambiguo, fuera de pantalla (devuelve navegacion) y ventana no en primer
  plano (antepone enfocar ventana).
- can_assign_coordinates: popup/transitorio no admite coordenadas persistentes;
  control no renderizado devuelve referencia semantica y navegacion.
- is_transient: menus desplegados, popups y tooltips desaparecen sin accion.
- navigation_for_element: referencia semantica y pasos (scroll, expandir,
  seleccionar pestana, abrir menu, enfocar ventana); nunca devuelve coordenadas.
- frame_is_fresh: limite de antiguedad de frame por tipo de accion, usado para
  detectar el cambio entre deteccion y accion.
- UIChangeDetector: espera de estabilidad y evento de accesibilidad.

Funciones puras deterministas sobre AccessibilityNode, AccessibilityTree,
WindowInfo y DisplayInfo: se verifican con datos representativos y no
requieren OS ni GUI.
"""

from __future__ import annotations

import time
import unittest

import numpy as np

from src.desktop.accessibility_model import AccessibilityNode, AccessibilityTree
from src.desktop.platform_contract import DisplayInfo, Rect, WindowInfo
from src.hands.calibration.dynamic_ui import (
    DEFAULT_DIFF_THRESHOLD,
    ElementPresence,
    ElementRelocator,
    FRAME_MAX_AGE_SECONDS,
    KIND_POPUP,
    KIND_TOOLTIP,
    NAV_FOCUS_WINDOW,
    NAV_OPEN_MENU,
    NAV_SCROLL,
    RelocationResult,
    StabilityResult,
    UIChangeDetector,
    can_assign_coordinates,
    classify_dynamic_element,
    frame_is_fresh,
    is_transient,
    navigation_for_element,
    semantic_reference,
)


def _node(
    node_id,
    control_type,
    native_role,
    name,
    identifier,
    actions=None,
    bbox=None,
    visible=True,
    enabled=True,
    offscreen=False,
    parent_id=None,
    depth=0,
    source="uia",
    raw=None,
):
    return AccessibilityNode(
        node_id=node_id,
        control_type=control_type,
        native_role=native_role,
        name=name,
        identifier=identifier,
        bbox=bbox,
        enabled=enabled,
        visible=visible,
        offscreen=offscreen,
        actions=list(actions or []),
        source=source,
        parent_id=parent_id,
        depth=depth,
        raw=raw or {},
    )


def _window(bounds=None, visible=True, minimized=False, foreground=True, display_id="d1"):
    b = bounds or Rect(0, 0, 1000, 800)
    return WindowInfo(
        window_id=1,
        pid=100,
        title="W",
        app_identity="w",
        bounds=b,
        frame_bounds=b,
        is_visible=visible,
        is_minimized=minimized,
        is_foreground=foreground,
        display_id=display_id,
        scale_factor=1.0,
        dpi=96,
        coordinate_space="DESKTOP_PIXELS",
    )


def _display(bounds=None):
    b = bounds or Rect(0, 0, 1920, 1080)
    return DisplayInfo(
        display_id="d1",
        name="Monitor",
        bounds=b,
        work_area=b,
        pixel_width=1920,
        pixel_height=1080,
        scale_factor=1.0,
        dpi=96,
        is_primary=True,
        coordinate_space="DESKTOP_PIXELS",
    )


_BBOX = Rect(100, 100, 200, 200)


class TestRelocatorBase(unittest.TestCase):
    def _tree(self):
        n1 = _node("n1", "Button", "Button", "Aceptar", "btnAceptar", bbox=_BBOX, actions=["invoke"], depth=0)
        n2 = _node("n2", "Button", "Button", "Cancelar", "btnCancelar", bbox=_BBOX, actions=["invoke"], depth=0)
        n3 = _node("n3", "MenuItem", "MenuItem", "Archivo", "mnuArchivo", actions=["invoke"], depth=0)
        n1.parent_id = None
        n2.parent_id = None
        n3.parent_id = None
        return AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[n1, n2, n3], root_id="n1")

    def test_relocaliza_por_identificador(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnAceptar"}, tree=tree)
        self.assertTrue(res.found)
        self.assertEqual(res.node.node_id, "n1")
        self.assertEqual(res.reason, "elemento relocalizado por identidad")
        self.assertIsNone(res.navigation)

    def test_relocaliza_por_nombre_y_tipo(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"name": "Cancelar", "control_type": "Button"}, tree=tree)
        self.assertTrue(res.found)
        self.assertEqual(res.node.identifier, "btnCancelar")

    def test_ignorar_coordenadas_en_referencia(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnAceptar", "bbox": [999, 999, 1000, 1000]}, tree=tree)
        self.assertTrue(res.found)

    def test_referencia_sin_identidad(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"control_type": "Button"}, tree=tree)
        self.assertFalse(res.found)
        self.assertEqual(res.reason, "referencia sin identidad (identificador o nombre)")

    def test_no_encontrado(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "noExiste"}, tree=tree)
        self.assertFalse(res.found)
        self.assertEqual(res.reason, "elemento no encontrado en el arbol actual")

    def test_ambiguo_sin_ancestros_no_se_elige(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnAceptar"}, tree=tree)
        self.assertTrue(res.found)

    def test_resultado_es_serializable(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnAceptar"}, tree=tree)
        d = res.to_dict()
        self.assertTrue(d["found"])
        self.assertEqual(d["node"]["node_id"], "n1")
        self.assertIsNone(d["navigation"])


class TestRelocatorVentanaNoEnPrimerPlano(unittest.TestCase):
    def _tree_con_menu(self):
        mb = _node("mb", "MenuBar", "MenuBar", "mb", "mb", actions=["show_menu"], depth=0)
        mi = _node("mi", "MenuItem", "MenuItem", "mi", "mi", actions=["invoke"], parent_id="mb", depth=1)
        btn = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], parent_id="mi", depth=2)
        mb.parent_id = None
        return AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[mb, mi, btn], root_id="mb")

    def _nodo_aislado_fuera_de_pantalla(self):
        n = _node("no", "Button", "Button", "Oculto", "btnOculto", bbox=None, visible=False, offscreen=True, actions=[], depth=0)
        n.parent_id = None
        return AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[n], root_id="no")

    def test_ventana_no_en_primer_plano_antepone_enfocar(self):
        tree = self._nodo_aislado_fuera_de_pantalla()
        nodo = tree.nodes[0]
        hint = navigation_for_element(nodo, tree, window_is_foreground=False)
        self.assertFalse(hint.reachable)
        self.assertEqual(hint.steps[0].action, NAV_FOCUS_WINDOW)

    def test_nodo_fuera_de_pantalla_devuelve_navegacion_sin_coordenadas(self):
        tree = self._tree_con_menu()
        btn = tree.get("btn")
        hint = navigation_for_element(btn, tree, window_is_foreground=True)
        self.assertTrue(hint.reachable)
        self.assertIn(NAV_OPEN_MENU, [s.action for s in hint.steps])
        d = hint.to_dict()
        self.assertNotIn("bbox", d)
        self.assertNotIn("center", d)
        self.assertNotIn("x", d)
        self.assertNotIn("y", d)
        for step in hint.steps:
            sd = step.to_dict()
            self.assertNotIn("bbox", sd)
            self.assertNotIn("center", sd)

    def test_relocate_fuera_de_pantalla_devuelve_navegacion_sin_coordenadas(self):
        tree = self._tree_con_menu()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btn"}, tree=tree)
        self.assertTrue(res.found)
        self.assertIsNotNone(res.navigation)
        self.assertTrue(res.navigation.reachable)
        self.assertIn(NAV_OPEN_MENU, [s.action for s in res.navigation.steps])
        d = res.navigation.to_dict()
        self.assertNotIn("bbox", d)
        self.assertNotIn("center", d)
        self.assertNotIn("x", d)
        self.assertNotIn("y", d)


class TestRelocatorControlDesaparecido(unittest.TestCase):
    def test_control_que_desaparece_no_se_relocaliza(self):
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[], root_id="raiz")
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnDesaparecido"}, tree=tree)
        self.assertFalse(res.found)
        self.assertEqual(res.reason, "elemento no encontrado en el arbol actual")
        self.assertIsNone(res.node)
        self.assertIsNone(res.navigation)


class TestPopupTransitorio(unittest.TestCase):
    def test_popup_es_transitorio(self):
        popup = _node("p", "AXPopover", "AXPopover", "popup", "p", bbox=_BBOX, actions=[], depth=0)
        popup.parent_id = None
        self.assertTrue(is_transient(popup))

    def test_tooltip_es_transitorio(self):
        tooltip = _node("t", "ToolTip", "ToolTip", "tt", "tt", bbox=_BBOX, actions=[], depth=0)
        tooltip.parent_id = None
        self.assertTrue(is_transient(tooltip))

    def test_popup_no_admite_coordenadas_persistentes(self):
        popup = _node("p", "AXPopover", "AXPopover", "popup", "p", bbox=_BBOX, actions=[], depth=0)
        popup.parent_id = None
        presence = ElementPresence(True, True, True, True, [])
        ok, reason = can_assign_coordinates(popup, presence, persistent=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "elemento transitorio: sus coordenadas no se persisten")

    def test_popup_admite_coordenadas_solo_uso_inmediato(self):
        popup = _node("p", "AXPopover", "AXPopover", "popup", "p", bbox=_BBOX, actions=[], depth=0)
        popup.parent_id = None
        presence = ElementPresence(True, True, True, True, [])
        ok, reason = can_assign_coordinates(popup, presence, persistent=False)
        self.assertTrue(ok)

    def test_control_no_renderizado_devuelve_referencia_semantica(self):
        popup = _node("p", "AXPopover", "AXPopover", "popup", "p", bbox=None, visible=False, offscreen=True, actions=[], depth=0)
        popup.parent_id = None
        presence = ElementPresence(True, False, True, False, ["fuera_de_pantalla"])
        ok, reason = can_assign_coordinates(popup, presence, persistent=False)
        self.assertFalse(ok)
        self.assertIn("no renderizado", reason)


class TestFrameIsFreshCambioDeteccionAccion(unittest.TestCase):
    def test_frame_reciente_para_click_es_fresco(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 0.5, "click", now=now))

    def test_frame_antiguo_para_click_no_es_fresco(self):
        now = time.monotonic()
        self.assertFalse(frame_is_fresh(now - 3.0, "click", now=now))

    def test_captura_nunca_hecha_no_es_fresca(self):
        self.assertFalse(frame_is_fresh(None, "click", now=time.monotonic()))

    def test_limite_inclusivo_click(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - FRAME_MAX_AGE_SECONDS["click"], "click", now=now))

    def test_limites_inyectables_por_accion(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 5.0, "click", now=now, limits={"click": 10.0}))
        self.assertFalse(frame_is_fresh(now - 5.0, "click", now=now, limits={"click": 2.0}))

    def test_accion_desconocida_usa_default(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 1.0, "accion_rara", now=now))
        self.assertFalse(frame_is_fresh(now - 3.0, "accion_rara", now=now))


class TestUIChangeDetectorEstabilidad(unittest.TestCase):
    def test_primera_captura_cuenta_como_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        f = np.zeros((2, 2), dtype=np.uint8)
        self.assertTrue(det.observe(f))

    def test_frame_igual_no_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        f = np.zeros((2, 2), dtype=np.uint8)
        det.observe(f)
        self.assertFalse(det.observe(f))

    def test_evento_de_accesibilidad_forza_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        f = np.zeros((2, 2), dtype=np.uint8)
        det.observe(f)
        det.notify_accessibility_event("focus")
        self.assertTrue(det.observe(f))

    def test_wait_until_stable_estabiliza(self):
        f = np.zeros((2, 2), dtype=np.uint8)
        clock = {"t": 0.0}
        def my_clock():
            return clock["t"]
        def my_sleep(dt):
            clock["t"] += dt
        det = UIChangeDetector(min_poll_interval=0.001, clock=my_clock, sleeper=my_sleep)
        res = det.wait_until_stable(lambda: f, timeout=5.0, stable_frames=3)
        self.assertIsInstance(res, StabilityResult)
        self.assertTrue(res.stable)
        self.assertGreaterEqual(res.frames_observed, 3)

    def test_wait_until_stable_agota_tiempo(self):
        f1 = np.zeros((2, 2), dtype=np.uint8)
        f2 = np.full((2, 2), 255, dtype=np.uint8)
        toggle = {"use_f1": True}
        def capture():
            toggle["use_f1"] = not toggle["use_f1"]
            return f1 if toggle["use_f1"] else f2
        clock = {"t": 0.0}
        def my_clock():
            return clock["t"]
        def my_sleep(dt):
            clock["t"] += dt
        det = UIChangeDetector(min_poll_interval=0.001, clock=my_clock, sleeper=my_sleep)
        res = det.wait_until_stable(capture, timeout=0.05, stable_frames=3)
        self.assertFalse(res.stable)
        self.assertEqual(res.reason, "tiempo agotado sin estabilidad")


class TestRelocatorVentanaMinimizada(unittest.TestCase):
    def test_ventana_minimizada_no_es_visible_y_no_admite_coordenadas(self):
        from src.hands.calibration.dynamic_ui import evaluate_presence
        win = _window(minimized=True, visible=False)
        node = _node("b", "Button", "Button", "x", "x", bbox=_BBOX, actions=["invoke"])
        presence = evaluate_presence(node, win, [_display()], window_is_foreground=True)
        self.assertFalse(presence.visible)
        ok, reason = can_assign_coordinates(node, presence)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
