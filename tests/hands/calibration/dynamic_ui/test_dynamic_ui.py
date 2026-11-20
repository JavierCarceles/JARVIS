"""
Tests unitarios (deterministas, sin SO ni GUI) de la gestion de interfaces
dinamicas - unidad 3.8.6.11.2 del roadmap.

Cubren para src/hands/calibration/dynamic_ui.py:
- classify_dynamic_element: menus, popups, tooltips, pestanas, dialogos,
  elementos de lista, contenedores con scroll y contenido estatico.
- is_transient: menus desplegados, popups y tooltips desaparecen sin accion
  del usuario.
- can_assign_coordinates: nunca coordenadas a controles no renderizados;
  los transitorios solo admiten coordenadas de uso inmediato, no persistentes.
- navigation_for_element: referencia semantica y navegacion (scroll, expandir,
  seleccionar pestana, abrir menu, enfocar ventana); nunca devuelve coordenadas.
- semantic_reference: referencia estable de un nodo sin coordenadas.
- frame_is_fresh: limite de antiguedad de frame por tipo de accion (hover,
  click, scroll, etc.), valor por defecto y limites inyectables.
- UIChangeDetector: deteccion de cambios por comparacion de frames, eventos
  de accesibilidad y espera de estabilidad sin espera fija con limite de CPU.
- ElementRelocator: relocalizacion por identidad (identificador, nombre, tipo,
  ancestros), nunca reutiliza coordenadas antiguas; ambiguo y no encontrado.

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
    KIND_DIALOG,
    KIND_LIST_ITEM,
    KIND_MENU,
    KIND_POPUP,
    KIND_SCROLL_CONTAINER,
    KIND_STATIC,
    KIND_TAB,
    KIND_TOOLTIP,
    NAV_EXPAND,
    NAV_FOCUS_WINDOW,
    NAV_OPEN_MENU,
    NAV_SCROLL,
    NAV_SELECT_TAB,
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


def _window(
    bounds=None,
    visible=True,
    minimized=False,
    foreground=True,
    display_id="d1",
):
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


class TestClassifyDynamicElement(unittest.TestCase):
    def test_tooltip(self):
        self.assertEqual(
            KIND_TOOLTIP,
            classify_dynamic_element(_node("t1", "ToolTip", "ToolTip", "tt", "tt")),
        )
        self.assertEqual(
            KIND_TOOLTIP,
            classify_dynamic_element(_node("t2", "AXHelpTag", "AXHelpTag", "ht", "ht")),
        )

    def test_menu_roles(self):
        for role in ("Menu", "MenuBar", "MenuItem", "AXMenu", "AXMenuItem", "AXMenuBar", "AXMenuBarItem"):
            self.assertEqual(KIND_MENU, classify_dynamic_element(_node("m", role, role, "x", "x")))

    def test_popup_roles(self):
        for role in ("AXPopover",):
            self.assertEqual(KIND_POPUP, classify_dynamic_element(_node("p", role, role, "x", "x")))

    def test_dialog_roles(self):
        self.assertEqual(KIND_DIALOG, classify_dynamic_element(_node("d", "AXDialog", "AXDialog", "x", "x")))
        self.assertEqual(KIND_DIALOG, classify_dynamic_element(_node("s", "AXSheet", "AXSheet", "x", "x")))
        self.assertEqual(
            KIND_DIALOG,
            classify_dynamic_element(_node("sd", "Window", "AXSystemDialog", "x", "x", raw={"subrole": "AXSystemDialog"})),
        )

    def test_tab_roles(self):
        self.assertEqual(KIND_TAB, classify_dynamic_element(_node("t", "Tab", "Tab", "x", "x")))
        self.assertEqual(KIND_TAB, classify_dynamic_element(_node("ti", "TabItem", "TabItem", "x", "x")))
        self.assertEqual(KIND_TAB, classify_dynamic_element(_node("tg", "AXTabGroup", "AXTabGroup", "x", "x")))
        self.assertEqual(
            KIND_TAB,
            classify_dynamic_element(_node("tb", "AXRadioButton", "AXRadioButton", "x", "x", raw={"subrole": "AXTabButton"})),
        )

    def test_list_item_roles(self):
        for role in ("ListItem", "TreeItem", "DataItem", "AXRow", "AXCell", "AXOutlineRow"):
            self.assertEqual(KIND_LIST_ITEM, classify_dynamic_element(_node("li", role, role, "x", "x")))

    def test_scroll_container(self):
        self.assertEqual(
            KIND_SCROLL_CONTAINER,
            classify_dynamic_element(_node("sc", "Pane", "Pane", "x", "x", actions=["scroll"])),
        )

    def test_static(self):
        self.assertEqual(KIND_STATIC, classify_dynamic_element(_node("s", "Text", "Text", "x", "x")))
        self.assertEqual(KIND_STATIC, classify_dynamic_element(_node("i", "Image", "Image", "x", "x")))

    def test_tooltip_checked_before_menu(self):
        node = _node("tt", "MenuItem", "AXHelpTag", "x", "x")
        self.assertEqual(KIND_TOOLTIP, classify_dynamic_element(node))


class TestIsTransient(unittest.TestCase):
    def test_transient_roles(self):
        for role in ("Menu", "ToolTip", "AXMenu", "AXHelpTag", "AXPopover", "AXSheet"):
            self.assertTrue(is_transient(_node("n", role, role, "x", "x")))

    def test_not_transient(self):
        self.assertFalse(is_transient(_node("n", "Button", "Button", "x", "x")))
        self.assertFalse(is_transient(_node("n", "Text", "Text", "x", "x")))


class TestCanAssignCoordinates(unittest.TestCase):
    def setUp(self):
        self.presence_ok = ElementPresence(True, True, True, True, [])
        self.node_ok = _node("b", "Button", "Button", "Aceptar", "btnAceptar", bbox=_BBOX, actions=["invoke"])

    def test_rendered_persistent_ok(self):
        ok, reason = can_assign_coordinates(self.node_ok, self.presence_ok, persistent=True)
        self.assertTrue(ok)
        self.assertEqual(reason, "control renderizado")

    def test_rendered_non_persistent_ok(self):
        ok, reason = can_assign_coordinates(self.node_ok, self.presence_ok, persistent=False)
        self.assertTrue(ok)

    def test_not_in_tree(self):
        ok, reason = can_assign_coordinates(self.node_ok, ElementPresence(False, False, False, False, ["no_presente_en_arbol"]))
        self.assertFalse(ok)
        self.assertEqual(reason, "no presente en el arbol")

    def test_not_visible(self):
        ok, reason = can_assign_coordinates(self.node_ok, ElementPresence(True, False, True, False, ["no_visible"]))
        self.assertFalse(ok)
        self.assertIn("no renderizado", reason)

    def test_no_bbox(self):
        node_no_bbox = _node("b", "Button", "Button", "x", "x", actions=["invoke"])
        ok, reason = can_assign_coordinates(node_no_bbox, self.presence_ok)
        self.assertFalse(ok)
        self.assertIn("no renderizado", reason)

    def test_transient_persistent_no(self):
        tooltip = _node("t", "ToolTip", "ToolTip", "tt", "tt", bbox=_BBOX, actions=[])
        ok, reason = can_assign_coordinates(tooltip, self.presence_ok, persistent=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "elemento transitorio: sus coordenadas no se persisten")

    def test_transient_non_persistent_yes(self):
        tooltip = _node("t", "ToolTip", "ToolTip", "tt", "tt", bbox=_BBOX, actions=[])
        ok, reason = can_assign_coordinates(tooltip, self.presence_ok, persistent=False)
        self.assertTrue(ok)


class TestNavigationForElement(unittest.TestCase):
    def _tree_visible(self):
        mb = _node("mb", "MenuBar", "MenuBar", "mb", "mb", actions=["show_menu"], depth=0)
        mi = _node("mi", "MenuItem", "MenuItem", "mi", "mi", actions=["invoke"], parent_id="mb", depth=1)
        btn = _node("btn", "Button", "Button", "btn", "btn", bbox=_BBOX, actions=["invoke"], parent_id="mi", depth=2)
        mb.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[mb, mi, btn], root_id="mb")
        return tree, btn

    def test_element_ya_visible_sin_pasos(self):
        tree, btn = self._tree_visible()
        hint = navigation_for_element(btn, tree, window_is_foreground=True)
        self.assertTrue(hint.reachable)
        self.assertEqual(hint.steps, [])
        self.assertEqual(hint.element_node_id, "btn")

    def test_menu_cerrado_abre_menu(self):
        tree, _ = self._tree_visible()
        mi = tree.get("mi")
        btn_off = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], parent_id="mi", depth=2)
        hint = navigation_for_element(btn_off, tree, window_is_foreground=True)
        self.assertTrue(hint.reachable)
        actions = [s.action for s in hint.steps]
        self.assertIn(NAV_OPEN_MENU, actions)
        self.assertIsNone(hint.element_ref.get("bbox"))

    def test_pestana_no_seleccionada(self):
        tab = _node("tg", "AXTabGroup", "AXTabGroup", "grupo", "grupo", actions=["select"], depth=0)
        tabitem = _node("ti", "AXRadioButton", "AXRadioButton", "tia", "tia", actions=["select"], parent_id="tg", depth=1, raw={"subrole": "AXTabButton"})
        btn_off = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], parent_id="ti", depth=2)
        tab.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[tab, tabitem, btn_off], root_id="tg")
        hint = navigation_for_element(btn_off, tree, window_is_foreground=True)
        self.assertTrue(hint.reachable)
        self.assertIn(NAV_SELECT_TAB, [s.action for s in hint.steps])

    def test_contenedor_con_scroll(self):
        scroll = _node("sc", "Pane", "Pane", "sc", "sc", actions=["scroll"], depth=0)
        btn_off = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], parent_id="sc", depth=1)
        scroll.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[scroll, btn_off], root_id="sc")
        hint = navigation_for_element(btn_off, tree, window_is_foreground=True)
        self.assertTrue(hint.reachable)
        self.assertIn(NAV_SCROLL, [s.action for s in hint.steps])

    def test_ventana_no_en_primer_plano_enfoca_primero(self):
        tree, _ = self._tree_visible()
        mi = tree.get("mi")
        btn_off = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], parent_id="mi", depth=2)
        hint = navigation_for_element(btn_off, tree, window_is_foreground=False)
        self.assertTrue(hint.reachable)
        self.assertEqual(hint.steps[0].action, NAV_FOCUS_WINDOW)

    def test_sin_ruta_conocida_no_alcanzable(self):
        isolated = _node("btn", "Button", "Button", "btn", "btn", bbox=None, visible=False, offscreen=True, actions=[], depth=0)
        isolated.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[isolated], root_id="btn")
        hint = navigation_for_element(isolated, tree, window_is_foreground=True)
        self.assertFalse(hint.reachable)
        self.assertIn("sin ruta de navegacion conocida", hint.reason)

    def test_nunca_devuelve_coordenadas(self):
        tree, btn = self._tree_visible()
        hint = navigation_for_element(btn, tree, window_is_foreground=True)
        d = hint.to_dict()
        self.assertNotIn("bbox", d)
        self.assertNotIn("center", d)
        self.assertNotIn("x", d)
        self.assertNotIn("y", d)
        for step in hint.steps:
            sd = step.to_dict()
            self.assertNotIn("bbox", sd)
            self.assertNotIn("center", sd)


class TestSemanticReference(unittest.TestCase):
    def test_referencia_estable_sin_coordenadas(self):
        anc = _node("a", "MenuBar", "MenuBar", "mb", "mb", depth=0)
        node = _node("n", "Button", "Button", "Aceptar", "btnAceptar", parent_id="a", depth=1)
        anc.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[anc, node], root_id="a")
        ref = semantic_reference(node, tree)
        self.assertEqual(ref["identifier"], "btnAceptar")
        self.assertEqual(ref["name"], "Aceptar")
        self.assertEqual(ref["native_role"], "Button")
        self.assertEqual(len(ref["ancestors"]), 1)
        self.assertEqual(ref["ancestors"][0]["native_role"], "MenuBar")
        self.assertNotIn("bbox", ref)
        self.assertNotIn("x", ref)

    def test_sin_arbol(self):
        node = _node("n", "Button", "Button", "Aceptar", "btnAceptar")
        ref = semantic_reference(node, None)
        self.assertEqual(ref["ancestors"], [])


class TestFrameIsFresh(unittest.TestCase):
    def test_frame_reciente_es_fresco(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 0.5, "click", now=now))

    def test_frame_expirado_no_es_fresco(self):
        now = time.monotonic()
        self.assertFalse(frame_is_fresh(now - 3.0, "click", now=now))

    def test_captura_nunca_hecha_no_es_fresca(self):
        self.assertFalse(frame_is_fresh(None, "click", now=time.monotonic()))

    def test_hover_tiene_limite_corto(self):
        now = time.monotonic()
        self.assertFalse(frame_is_fresh(now - 1.5, "hover", now=now))
        self.assertTrue(frame_is_fresh(now - 0.5, "hover", now=now))

    def test_accion_desconocida_usa_default(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 1.0, "accion_rara", now=now))
        self.assertFalse(frame_is_fresh(now - 3.0, "accion_rara", now=now))

    def test_limites_inyectables(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - 5.0, "click", now=now, limits={"click": 10.0}))
        self.assertFalse(frame_is_fresh(now - 5.0, "click", now=now, limits={"click": 2.0}))

    def test_limite_inclusivo(self):
        now = time.monotonic()
        self.assertTrue(frame_is_fresh(now - FRAME_MAX_AGE_SECONDS["click"], "click", now=now))


class TestUIChangeDetector(unittest.TestCase):
    def _frames_equal(self):
        return np.zeros((10, 10, 3), dtype=np.uint8)

    def _frames_different(self):
        f1 = np.zeros((10, 10, 3), dtype=np.uint8)
        f2 = np.full((10, 10, 3), 255, dtype=np.uint8)
        return f1, f2

    def test_primera_captura_cuenta_como_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        self.assertTrue(det.observe(self._frames_equal()))

    def test_frame_igual_no_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        f = self._frames_equal()
        det.observe(f)
        self.assertFalse(det.observe(f))
        self.assertEqual(det.last_diff, 0.0)

    def test_cambio_por_debajo_de_umbral_no_cuenta(self):
        det = UIChangeDetector(diff_threshold=0.05, min_poll_interval=0.001)
        f1, f2 = self._frames_equal(), self._frames_equal()
        f2[5, 5, :] = 255
        det.observe(f1)
        self.assertFalse(det.observe(f2))
        self.assertLess(det.last_diff, DEFAULT_DIFF_THRESHOLD)

    def test_evento_de_accesibilidad_forza_cambio(self):
        det = UIChangeDetector(min_poll_interval=0.001)
        f = self._frames_equal()
        det.observe(f)
        det.notify_accessibility_event("focus")
        self.assertTrue(det.observe(f))

    def test_wait_until_stable_estabiliza(self):
        f = self._frames_equal()
        def capture():
            return f
        clock = {"t": 0.0}
        def my_clock():
            return clock["t"]
        def my_sleep(dt):
            clock["t"] += dt
        det = UIChangeDetector(min_poll_interval=0.001, clock=my_clock, sleeper=my_sleep)
        res = det.wait_until_stable(capture, timeout=5.0, stable_frames=3)
        self.assertIsInstance(res, StabilityResult)
        self.assertTrue(res.stable)
        self.assertGreaterEqual(res.frames_observed, 3)

    def test_wait_until_stable_agota_tiempo(self):
        f1, f2 = self._frames_different()
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

    def test_respeta_limite_de_cpu(self):
        det = UIChangeDetector(max_cpu_fraction=0.5, min_poll_interval=0.001)
        self.assertGreaterEqual(det._poll_interval(), 0.001)


class TestElementRelocator(unittest.TestCase):
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

    def test_nodo_fuera_de_pantalla_devuelve_navegacion(self):
        n_off = _node("no", "Button", "Button", "Oculto", "btnOculto", bbox=None, visible=False, offscreen=True, actions=[], depth=0)
        n_off.parent_id = None
        tree = AccessibilityTree(window_id=1, pid=100, source="uia", nodes=[n_off], root_id="no")
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnOculto"}, tree=tree)
        self.assertTrue(res.found)
        self.assertIsNotNone(res.navigation)
        self.assertFalse(res.navigation.reachable)

    def test_resultado_es_serializable(self):
        tree = self._tree()
        rel = ElementRelocator()
        res = rel.relocate(1, {"identifier": "btnAceptar"}, tree=tree)
        d = res.to_dict()
        self.assertTrue(d["found"])
        self.assertEqual(d["node"]["node_id"], "n1")
        self.assertIsNone(d["navigation"])


if __name__ == "__main__":
    unittest.main()
