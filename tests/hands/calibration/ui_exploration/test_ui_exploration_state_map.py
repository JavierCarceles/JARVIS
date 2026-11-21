# -*- coding: utf-8 -*-
"""Tests de unidad del mapa de estados UI y del explorador profundo (3.8.6.12.1, 3.8.6.12.2, 3.8.6.12.3, 3.8.6.12.4).

Cubre:
- UIStateNode: creacion, serializacion y deserializacion del estado UI.
- UITransition: transicion accion -> estado resultante con forma de volver.
- UIStateMap: mapa de estados, transiciones, ruta verificada y representacion logica.
- element_reference: referencia logica de un elemento sin coordenadas fisicas.
- ExplorationSafetyPolicy: acciones admitidas y decisiones de permitido/denegado.
- ExplorationBudget: limites de exploracion y serializacion.
- ExplorationCheckpoint: punto de control serializable y round-trip JSON.
- persist_state_map_logically: persistencia logica en el catalogo (sin coordenadas).
- DeepUIExplorer: recorrido en anchura acotado, presupuestos, estados repetidos, vuelta comprobada y reanudacion.
- Recuperacion (3.8.6.12.4): si la vuelta falla o aparece algo inesperado, se detiene la
  exploracion, se cierra solo lo abierto por JARVIS, se registra el estado y nunca se
  fuerza el cierre de la aplicacion del usuario.

Todos los tests son deterministas, sin interaccion GUI ni SO real.
"""

from unittest.mock import MagicMock

import pytest

from src.desktop.accessibility_model import AccessibilityNode, AccessibilityTree
from src.desktop.platform_contract import PlatformErrorCode, PlatformResult, WindowInfo

from src.hands.calibration.ui_exploration import (
    ACTION_EXPAND,
    ACTION_OPEN_DIALOG,
    ACTION_OPEN_MENU,
    ACTION_SELECT_TAB,
    DIALOG_FORBIDDEN_TERMS,
    DeepUIExplorer,
    ExplorationBudget,
    ExplorationCheckpoint,
    ExplorationResult,
    ExplorationSafetyPolicy,
    FORBIDDEN_ICON_HINTS,
    FORBIDDEN_SYMBOL_LABELS,
    FORBIDDEN_TERMS_EN,
    FORBIDDEN_TERMS_ES,
    NEVER_ACTIONS,
    UIStateMap,
    UIStateNode,
    UITransition,
    element_reference,
    persist_state_map_logically,
)

# Claves que nunca deben aparecer en la representacion logica (catalogo).
_PHYSICAL_KEYS = frozenset({
    "bbox", "box", "center", "coordinates", "x", "y", "left", "top", "right",
    "bottom", "width", "height", "rect", "bounds", "point", "monitor",
    "display_id", "dpi", "scale_factor", "pid", "hwnd", "window_id",
})


def _encontrar_claves_fisicas(obj, path=""):
    """Devuelve lista de (ruta, valor) para claves fisicas en cualquier nivel."""
    encontrados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in _PHYSICAL_KEYS:
                encontrados.append((path + "." + str(k), v))
            encontrados.extend(_encontrar_claves_fisicas(v, path + "." + str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            encontrados.extend(_encontrar_claves_fisicas(v, path + "[%d]" % i))
    return encontrados


# ---------------------------------------------------------------------------
# UIStateNode
# ---------------------------------------------------------------------------
class TestUIStateNode:
    def test_creacion_con_todos_los_campos(self):
        nodo = UIStateNode(
            state_id="s1",
            window_fingerprint="wfp1",
            tree_hash="th1",
            visible_elements=["btn1", "btn2"],
            depth=2,
        )
        assert nodo.state_id == "s1"
        assert nodo.window_fingerprint == "wfp1"
        assert nodo.tree_hash == "th1"
        assert nodo.visible_elements == ["btn1", "btn2"]
        assert nodo.depth == 2

    def test_creacion_valores_por_defecto(self):
        nodo = UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1")
        assert nodo.visible_elements == []
        assert nodo.depth == 0

    def test_to_dict_from_dict_round_trip(self):
        nodo = UIStateNode(
            state_id="s1", window_fingerprint="wfp1", tree_hash="th1",
            visible_elements=["menu", "btn"], depth=3,
        )
        datos = nodo.to_dict()
        nodo2 = UIStateNode.from_dict(datos)
        assert nodo2.state_id == nodo.state_id
        assert nodo2.window_fingerprint == nodo.window_fingerprint
        assert nodo2.tree_hash == nodo.tree_hash
        assert nodo2.visible_elements == nodo.visible_elements
        assert nodo2.depth == nodo.depth

    def test_from_dict_datos_incompletos(self):
        nodo = UIStateNode.from_dict({"state_id": "s1"})
        assert nodo.state_id == "s1"
        assert nodo.window_fingerprint == ""
        assert nodo.tree_hash == ""
        assert nodo.visible_elements == []
        assert nodo.depth == 0


# ---------------------------------------------------------------------------
# UITransition
# ---------------------------------------------------------------------------
class TestUITransition:
    def test_creacion_con_todos_los_campos(self):
        trans = UITransition(
            from_state="s1",
            action="expand",
            element_ref={"identifier": "btn1", "name": "Boton"},
            to_state="s2",
            return_action="collapse",
            verified_return=True,
        )
        assert trans.from_state == "s1"
        assert trans.action == "expand"
        assert trans.element_ref == {"identifier": "btn1", "name": "Boton"}
        assert trans.to_state == "s2"
        assert trans.return_action == "collapse"
        assert trans.verified_return is True

    def test_to_dict_from_dict_round_trip(self):
        trans = UITransition(
            from_state="s1", action="select_tab",
            element_ref={"identifier": "tab2", "name": "Pestana 2"},
            to_state="s3", return_action="select_previous_tab", verified_return=False,
        )
        datos = trans.to_dict()
        trans2 = UITransition.from_dict(datos)
        assert trans2.from_state == trans.from_state
        assert trans2.action == trans.action
        assert trans2.element_ref == trans.element_ref
        assert trans2.to_state == trans.to_state
        assert trans2.return_action == trans.return_action
        assert trans2.verified_return == trans.verified_return

    def test_from_dict_valores_por_defecto(self):
        trans = UITransition.from_dict({"from_state": "s1", "action": "expand"})
        assert trans.from_state == "s1"
        assert trans.action == "expand"
        assert trans.element_ref == {}
        assert trans.to_state == ""
        assert trans.return_action == ""
        assert trans.verified_return is False


# ---------------------------------------------------------------------------
# UIStateMap
# ---------------------------------------------------------------------------
class TestUIStateMap:
    def test_add_state_nuevo_y_duplicado(self):
        mapa = UIStateMap(app_id="app_notepad")
        nodo = UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1")
        assert mapa.add_state(nodo) is True
        assert mapa.root_state_id == "s1"
        assert mapa.has_state("s1") is True
        assert mapa.get_state("s1") is nodo
        assert mapa.add_state(nodo) is False  # duplicado no se anade de nuevo

    def test_add_transition_actualiza_si_existe(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        mapa.add_state(UIStateNode(state_id="s2", window_fingerprint="wfp2", tree_hash="th2"))
        t1 = UITransition("s1", "expand", {"identifier": "btn1"}, "s2", "collapse", True)
        mapa.add_transition(t1)
        assert len(mapa.transitions) == 1
        # Misma transicion -> se actualiza, no se duplica
        t2 = UITransition("s1", "expand", {"identifier": "btn1"}, "s2", "escape", False)
        mapa.add_transition(t2)
        assert len(mapa.transitions) == 1
        actual = mapa.transitions[0]
        assert actual.return_action == "escape"
        assert actual.verified_return is False

    def test_transitions_from(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        mapa.add_state(UIStateNode(state_id="s2", window_fingerprint="wfp2", tree_hash="th2"))
        mapa.add_transition(UITransition("s1", "expand", {"identifier": "btn1"}, "s2", "collapse", True))
        mapa.add_transition(UITransition("s1", "select_tab", {"identifier": "tab2"}, "s2", "select_previous_tab", True))
        trs = mapa.transitions_from("s1")
        assert len(trs) == 2
        assert mapa.transitions_from("s2") == []

    def test_path_to_encontrada_y_no_encontrada(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s0", window_fingerprint="wfp0", tree_hash="th0"))
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        mapa.add_state(UIStateNode(state_id="s2", window_fingerprint="wfp2", tree_hash="th2"))
        mapa.add_transition(UITransition("s0", "expand", {"identifier": "btn1"}, "s1", "collapse", True))
        mapa.add_transition(UITransition("s1", "expand", {"identifier": "btn2"}, "s2", "collapse", True))
        camino = mapa.path_to("s2")
        assert camino is not None
        assert len(camino) == 2
        assert camino[0].to_state == "s1"
        assert camino[1].to_state == "s2"
        assert mapa.path_to("s0") == []  # raiz: camino vacio
        assert mapa.path_to("inexistente") is None

    def test_path_to_sin_transiciones_verificadas_no_llega(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s0", window_fingerprint="wfp0", tree_hash="th0"))
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        # Transicion sin retorno verificado -> no cuenta para path_to
        mapa.add_transition(UITransition("s0", "expand", {"identifier": "btn1"}, "s1", "collapse", False))
        assert mapa.path_to("s1") is None

    def test_to_logical_dict_sin_claves_fisicas(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        mapa.add_transition(UITransition(
            "s1", "expand", {"identifier": "btn1", "name": "Boton"},
            "s2", "collapse", True,
        ))
        logico = mapa.to_logical_dict()
        assert logico["app_id"] == "app_notepad"
        assert logico["root_state_id"] == "s1"
        assert len(logico["states"]) == 1
        assert len(logico["transitions"]) == len(mapa.transitions)
        fisicas = _encontrar_claves_fisicas(logico)
        assert fisicas == [], "claves fisicas en logico: %s" % fisicas

    def test_from_logical_dict_round_trip(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1", visible_elements=["btn1"], depth=1))
        mapa.add_transition(UITransition("s1", "expand", {"identifier": "btn1"}, "s2", "collapse", True))
        logico = mapa.to_logical_dict()
        mapa2 = UIStateMap.from_logical_dict(logico)
        assert mapa2.app_id == "app_notepad"
        assert mapa2.root_state_id == "s1"
        assert mapa2.has_state("s1")
        assert len(mapa2.transitions) == 1
        t = mapa2.transitions[0]
        assert t.from_state == "s1"
        assert t.action == "expand"
        assert t.to_state == "s2"
        assert t.return_action == "collapse"
        assert t.verified_return is True

    def test_from_logical_dict_vacio(self):
        mapa = UIStateMap.from_logical_dict({})
        assert mapa.app_id == ""
        assert mapa.root_state_id is None
        assert mapa.states == {}
        assert mapa.transitions == []


# ---------------------------------------------------------------------------
# element_reference (sin coordenadas)
# ---------------------------------------------------------------------------
class TestElementReference:
    def test_devuelve_referencia_logica_sin_coordenadas(self):
        class NodoFalso:
            identifier = "btn1"
            name = "Boton"
            control_type = "Button"
            native_role = "Button"
            parent_id = None
            depth = 1
        ref = element_reference(NodoFalso())
        assert ref["identifier"] == "btn1"
        assert ref["name"] == "Boton"
        assert ref["control_type"] == "Button"
        assert ref["native_role"] == "Button"
        assert ref["parent_name"] == ""
        assert ref["depth"] == 1
        fisicas = _encontrar_claves_fisicas(ref)
        assert fisicas == [], "claves fisicas en referencia: %s" % fisicas

    def test_con_nombre_del_padre(self):
        class Padre:
            name = "MenuPrincipal"
        class NodoFalso:
            identifier = "item1"
            name = "Item"
            control_type = "MenuItem"
            native_role = "MenuItem"
            parent_id = "p1"
            depth = 2
        tree = {"p1": Padre()}
        ref = element_reference(NodoFalso(), tree)
        assert ref["parent_name"] == "MenuPrincipal"


# ---------------------------------------------------------------------------
# ExplorationSafetyPolicy
# ---------------------------------------------------------------------------
class TestExplorationSafetyPolicy:
    def test_acciones_admitidas_por_defecto(self):
        p = ExplorationSafetyPolicy()
        acciones = p.allowed_actions()
        assert ACTION_EXPAND in acciones
        assert ACTION_SELECT_TAB in acciones
        assert ACTION_OPEN_MENU in acciones
        assert ACTION_OPEN_DIALOG not in acciones

    def test_acciones_admitidas_con_dialogos(self):
        p = ExplorationSafetyPolicy(allow_dialogs=True)
        acciones = p.allowed_actions()
        assert ACTION_OPEN_DIALOG in acciones

    def test_is_allowed_expand_valido(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            enabled = True
            visible = True
            offscreen = False
            native_role = "Button"
            actions = ["expand"]
            name = "Menu"
            identifier = "menu1"
        nodo = Nodo()
        permitido, motivo = p.is_allowed(nodo, ACTION_EXPAND)
        assert permitido is True
        assert motivo == "expandir"

    def test_abridor_de_menu_con_expandir_se_abre_como_menu(self):
        """Un MenuItem de la barra de menus que expone expandir (Qt en UIA) se
        abre como menu (en modo clic se pulsa con el raton); un ComboBox o un
        TreeItem con expandir siguen siendo expandir."""
        p = ExplorationSafetyPolicy()

        def nodo(rol):
            class Nodo:
                enabled = True
                visible = True
                offscreen = False
                native_role = rol
                actions = ["expand", "collapse"]
                name = "Sistema"
                identifier = ""
            return Nodo()

        assert p.candidate_action(nodo("MenuItem")) == ACTION_OPEN_MENU
        assert p.candidate_action(nodo("MenuBarItem")) == ACTION_OPEN_MENU
        assert p.is_allowed(nodo("MenuItem"), ACTION_OPEN_MENU)[0] is True
        assert p.candidate_action(nodo("ComboBox")) == ACTION_EXPAND
        assert p.candidate_action(nodo("TreeItem")) == ACTION_EXPAND

    def test_is_allowed_rechaza_accion_never(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            enabled = True
            visible = True
            offscreen = False
            native_role = "Button"
            actions = ["invoke"]
            name = "Btn"
            identifier = "btn1"
        nodo = Nodo()
        permitido, _ = p.is_allowed(nodo, "type_text")
        assert permitido is False

    def test_is_allowed_rechaza_control_deshabilitado(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            enabled = False
            visible = True
            offscreen = False
            native_role = "Button"
            actions = ["expand"]
            name = "Menu"
            identifier = "menu1"
        nodo = Nodo()
        permitido, _ = p.is_allowed(nodo, ACTION_EXPAND)
        assert permitido is False

    def test_is_allowed_rechaza_etiqueta_prohibida(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            enabled = True
            visible = True
            offscreen = False
            native_role = "MenuItem"
            actions = ["expand", "invoke"]
            name = "Guardar"
            identifier = "guardar1"
        nodo = Nodo()
        permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_MENU)
        assert permitido is False
        assert "prohibida" in motivo

    def test_is_forbidden_label_etiqueta_vacia(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            name = ""
            identifier = ""
        nodo = Nodo()
        prohibido, motivo = p.is_forbidden_label(nodo)
        assert prohibido is True
        assert "etiqueta" in motivo

    def test_candidate_action_pestana(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            native_role = "TabItem"
            actions = ["select"]
            name = "Pestana2"
            identifier = "tab2"
        nodo = Nodo()
        accion = p.candidate_action(nodo)
        assert accion == ACTION_SELECT_TAB

    def test_candidate_action_sin_accion_valida(self):
        p = ExplorationSafetyPolicy()
        class Nodo:
            native_role = "Text"
            actions = []
            name = "Etiqueta"
            identifier = "lbl1"
        nodo = Nodo()
        accion = p.candidate_action(nodo)
        assert accion is None

    # ---------------------------------------------------------------------------
    # Politica de seguridad: cobertura exhaustiva de 3.8.6.12.2
    # ---------------------------------------------------------------------------
    def _nodo(self, nombre="Menu", identificador="menu1", rol="MenuItem", acciones=None, habilitado=True, visible=True, fuera_pantalla=False):
        class Nodo:
            pass
        nodo = Nodo()
        nodo.name = nombre
        nodo.identifier = identificador
        nodo.native_role = rol
        nodo.actions = list(acciones or ["expand", "invoke"])
        nodo.enabled = habilitado
        nodo.visible = visible
        nodo.offscreen = fuera_pantalla
        return nodo

    def test_rechaza_todos_los_terminos_prohibidos_espanol(self):
        p = ExplorationSafetyPolicy()
        for termino in FORBIDDEN_TERMS_ES:
            nodo = self._nodo(nombre=termino, identificador=termino, rol="MenuItem", acciones=["expand", "invoke"])
            permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_MENU)
            assert permitido is False, "debe rechazar ES: %s (%s)" % (termino, motivo)
            assert "prohibida" in motivo, motivo

    def test_rechaza_todos_los_terminos_prohibidos_ingles(self):
        p = ExplorationSafetyPolicy()
        for termino in FORBIDDEN_TERMS_EN:
            nodo = self._nodo(nombre=termino, identificador=termino, rol="MenuItem", acciones=["expand", "invoke"])
            permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_MENU)
            assert permitido is False, "debe rechazar EN: %s (%s)" % (termino, motivo)
            assert "prohibida" in motivo, motivo

    def test_is_forbidden_label_rechaza_terminos_espanol(self):
        p = ExplorationSafetyPolicy()
        for termino in ("guardar", "enviar", "borrar", "eliminar", "comprar", "pagar", "publicar", "cerrar sesion", "instalar", "actualizar", "formatear", "salir", "aceptar terminos"):
            nodo = self._nodo(nombre=termino, identificador=termino)
            prohibido, motivo = p.is_forbidden_label(nodo)
            assert prohibido is True, "ES no prohibido: %s (%s)" % (termino, motivo)

    def test_is_forbidden_label_rechaza_terminos_ingles(self):
        p = ExplorationSafetyPolicy()
        for termino in ("save", "send", "delete", "remove", "buy", "pay", "publish", "sign out", "log out", "exit", "quit", "install", "update", "format", "accept terms"):
            nodo = self._nodo(nombre=termino, identificador=termino)
            prohibido, motivo = p.is_forbidden_label(nodo)
            assert prohibido is True, "EN no prohibido: %s (%s)" % (termino, motivo)

    def test_rechaza_pistas_de_icono(self):
        p = ExplorationSafetyPolicy()
        for pista in FORBIDDEN_ICON_HINTS:
            nodo = self._nodo(nombre="Boton", identificador="btn_" + pista)
            prohibido, motivo = p.is_forbidden_label(nodo)
            assert prohibido is True, "icono no prohibido: %s (%s)" % (pista, motivo)

    def test_rechaza_etiquetas_simbolo(self):
        p = ExplorationSafetyPolicy()
        for simbolo in FORBIDDEN_SYMBOL_LABELS:
            nodo = self._nodo(nombre=simbolo, identificador="")
            prohibido, motivo = p.is_forbidden_label(nodo)
            assert prohibido is True, "simbolo no prohibido: %r (%s)" % (simbolo, motivo)

    def test_rechaza_todas_las_acciones_de_escritura(self):
        p = ExplorationSafetyPolicy()
        nodo = self._nodo(nombre="Btn", identificador="btn1", rol="Button", acciones=["expand"])
        for accion in NEVER_ACTIONS:
            permitido, motivo = p.is_allowed(nodo, accion)
            assert permitido is False, "never action no rechazada: %s (%s)" % (accion, motivo)

    def test_ante_duda_no_pulsar_accion_desconocida(self):
        p = ExplorationSafetyPolicy()
        nodo = self._nodo(nombre="Btn", identificador="btn1", rol="Button", acciones=["expand"])
        permitido, motivo = p.is_allowed(nodo, "accion_inexistente")
        assert permitido is False, "accion desconocida debe rechazarse (%s)" % motivo

    def test_no_acepta_control_sin_etiqueta(self):
        p = ExplorationSafetyPolicy()
        nodo = self._nodo(nombre="", identificador="")
        permitido, motivo = p.is_allowed(nodo, ACTION_EXPAND)
        assert permitido is False, "sin etiqueta debe rechazarse (%s)" % motivo

    def test_no_abre_dialogo_sin_puntos_suspensivos(self):
        p = ExplorationSafetyPolicy(allow_dialogs=True)
        nodo = self._nodo(nombre="Preferencias", identificador="prefs", rol="MenuItem", acciones=["invoke"])
        permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_DIALOG)
        assert permitido is False, "dialogo sin puntos suspensivos debe rechazarse (%s)" % motivo

    def test_rechaza_dialogo_con_termino_prohibido(self):
        p = ExplorationSafetyPolicy(allow_dialogs=True)
        nodo = self._nodo(nombre="Abrir archivo...", identificador="abrir_archivo", rol="MenuItem", acciones=["invoke"])
        permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_DIALOG)
        assert permitido is False, "dialogo prohibido debe rechazarse (%s)" % motivo

    def test_abre_dialogo_solo_con_puntos_suspensivos(self):
        p = ExplorationSafetyPolicy(allow_dialogs=True)
        nodo = self._nodo(nombre="Preferencias...", identificador="prefs", rol="MenuItem", acciones=["invoke"])
        permitido, motivo = p.is_allowed(nodo, ACTION_OPEN_DIALOG)
        assert permitido is True, "dialogo con puntos suspensivos debe aceptarse (%s)" % motivo

    def test_acepta_acciones_seguras_con_etiqueta_segura(self):
        p = ExplorationSafetyPolicy()
        btn = self._nodo(nombre="Menu", identificador="btn1", rol="Button", acciones=["expand"])
        assert p.is_allowed(btn, ACTION_EXPAND)[0] is True
        mbi = self._nodo(nombre="Archivo", identificador="menu_archivo", rol="MenuBarItem", acciones=["show_menu"])
        assert p.is_allowed(mbi, ACTION_OPEN_MENU)[0] is True
        assert p.is_allowed(btn, ACTION_SELECT_TAB)[0] is False

    def test_acepta_pestana_segura(self):
        p = ExplorationSafetyPolicy()
        nodo = self._nodo(nombre="Pestana 2", identificador="tab2", rol="TabItem", acciones=["select"])
        permitido, motivo = p.is_allowed(nodo, ACTION_SELECT_TAB)
        assert permitido is True, "pestana segura debe aceptarse (%s)" % motivo


# ---------------------------------------------------------------------------
# ExplorationBudget
# ---------------------------------------------------------------------------
class TestExplorationBudget:
    def test_valores_por_defecto(self):
        b = ExplorationBudget()
        assert b.max_depth == 3
        assert b.max_states == 60
        assert b.max_seconds == 120.0
        assert b.max_actions == 300
        assert b.settle_timeout == 2.0
        assert b.settle_poll == 0.1
        assert b.return_similarity == 0.97

    def test_valores_personalizados(self):
        b = ExplorationBudget(max_depth=5, max_states=100, max_seconds=60.0)
        assert b.max_depth == 5
        assert b.max_states == 100
        assert b.max_seconds == 60.0

    def test_to_dict(self):
        b = ExplorationBudget(max_depth=4, max_states=50)
        d = b.to_dict()
        assert d["max_depth"] == 4
        assert d["max_states"] == 50
        assert d["max_seconds"] == 120.0


# ---------------------------------------------------------------------------
# ExplorationCheckpoint
# ---------------------------------------------------------------------------
class TestExplorationCheckpoint:
    def test_creacion_y_to_dict(self):
        cp = ExplorationCheckpoint(
            app_id="app_x", mode="full", root_state_id="s0",
            actions_performed=10, elapsed_seconds=5.5,
        )
        d = cp.to_dict()
        assert d["app_id"] == "app_x"
        assert d["mode"] == "full"
        assert d["root_state_id"] == "s0"
        assert d["actions_performed"] == 10
        assert d["elapsed_seconds"] == 5.5
        assert d["frontier"] == []
        assert d["state_map"] == {}
        assert d["skipped_forbidden"] == []
        assert d["target_ref"] is None

    def test_to_json_from_json_round_trip(self):
        cp = ExplorationCheckpoint(
            app_id="app_x", mode="branch", root_state_id="s0",
            frontier=[[{"action": "expand"}]],
            state_map={"estados": 2},
            actions_performed=3,
            elapsed_seconds=12.0,
            skipped_forbidden=[{"elemento": "btn", "motivo": "prohibido"}],
            target_ref={"identifier": "btn_meta"},
        )
        cp2 = ExplorationCheckpoint.from_json(cp.to_json())
        assert cp2.app_id == cp.app_id
        assert cp2.mode == cp.mode
        assert cp2.root_state_id == cp.root_state_id
        assert cp2.frontier == cp.frontier
        assert cp2.state_map == cp.state_map
        assert cp2.actions_performed == cp.actions_performed
        assert cp2.elapsed_seconds == cp.elapsed_seconds
        assert cp2.skipped_forbidden == cp.skipped_forbidden
        assert cp2.target_ref == cp.target_ref

    def test_from_dict_valores_por_defecto(self):
        cp = ExplorationCheckpoint.from_dict({"app_id": "app_y"})
        assert cp.app_id == "app_y"
        assert cp.mode == "full"
        assert cp.root_state_id is None
        assert cp.frontier == []
        assert cp.state_map == {}
        assert cp.actions_performed == 0
        assert cp.elapsed_seconds == 0.0
        assert cp.skipped_forbidden == []
        assert cp.target_ref is None


# ---------------------------------------------------------------------------
# persist_state_map_logically (con memory_manager simulado)
# ---------------------------------------------------------------------------
class TestPersistStateMapLogically:
    def _mapa_simple(self):
        mapa = UIStateMap(app_id="app_notepad")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1"))
        mapa.add_transition(UITransition("s1", "expand", {"identifier": "btn1"}, "s2", "collapse", True))
        return mapa

    def test_guarda_en_entidad_existente(self):
        mapa = self._mapa_simple()
        mm = MagicMock()
        entidad = MagicMock()
        entidad.properties = {}
        mm.get_entity.return_value = entidad
        mm.save_entity.return_value = True
        guardado, motivo = persist_state_map_logically("notepad", mapa, memory_manager=mm)
        assert guardado is True
        assert motivo == "guardado"
        mm.get_entity.assert_called_once_with("app_notepad")
        mm.save_entity.assert_called_once()
        assert "ui_state_map" in entidad.properties
        assert entidad.properties["ui_state_map"]["app_id"] == "app_notepad"

    def test_no_guarda_si_entidad_no_existe(self):
        mapa = self._mapa_simple()
        mm = MagicMock()
        mm.get_entity.return_value = None
        guardado, motivo = persist_state_map_logically("desconocida", mapa, memory_manager=mm)
        assert guardado is False
        assert "no existe" in motivo
        mm.save_entity.assert_not_called()

    def test_no_guarda_si_save_entity_devuelve_false(self):
        mapa = self._mapa_simple()
        mm = MagicMock()
        entidad = MagicMock()
        entidad.properties = {}
        mm.get_entity.return_value = entidad
        mm.save_entity.return_value = False
        guardado, motivo = persist_state_map_logically("notepad", mapa, memory_manager=mm)
        assert guardado is False
        assert "devolvio False" in motivo

    def test_clave_normalizada_sin_espacios(self):
        mapa = self._mapa_simple()
        mm = MagicMock()
        entidad = MagicMock()
        entidad.properties = {}
        mm.get_entity.return_value = entidad
        mm.save_entity.return_value = True
        persist_state_map_logically("Mi App Con Espacios", mapa, memory_manager=mm)
        mm.get_entity.assert_called_once_with("app_mi_app_con_espacios")

    def test_no_agrega_claves_fisicas_al_catalogo(self):
        mapa = self._mapa_simple()
        mm = MagicMock()
        entidad = MagicMock()
        entidad.properties = {}
        mm.get_entity.return_value = entidad
        mm.save_entity.return_value = True
        persist_state_map_logically("notepad", mapa, memory_manager=mm)
        fisicas = _encontrar_claves_fisicas(entidad.properties)
        assert fisicas == [], "claves fisicas en catalogo: %s" % fisicas


# ---------------------------------------------------------------------------
# No hay claves fisicas en la representacion logica completa
# ---------------------------------------------------------------------------
class TestRepresentacionLogicaSinClavesFisicas:
    def test_mapa_completo_no_tiene_claves_fisicas(self):
        mapa = UIStateMap(app_id="app_chrome")
        mapa.add_state(UIStateNode(state_id="s1", window_fingerprint="wfp1", tree_hash="th1", visible_elements=["btn1", "menu1"], depth=1))
        mapa.add_transition(UITransition("s1", "expand", {"identifier": "btn1", "name": "Boton"}, "s2", "collapse", True))
        mapa.add_transition(UITransition("s2", "escape", {"identifier": "btn_cerrar"}, "s1", "reabrir", True))
        logico = mapa.to_logical_dict()
        fisicas = _encontrar_claves_fisicas(logico)
        assert fisicas == [], "claves fisicas encontradas: %s" % fisicas


# ---------------------------------------------------------------------------
# Dobles de prueba para DeepUIExplorer (algoritmo 3.8.6.12.3)
# ---------------------------------------------------------------------------


def _nodo(
    node_id,
    control_type,
    native_role,
    name,
    identifier,
    acciones,
    depth,
    parent_id=None,
):
    """Construye un AccessibilityNode determinista sin coordenadas fisicas."""
    return AccessibilityNode(
        node_id=node_id,
        control_type=control_type,
        native_role=native_role,
        name=name,
        identifier=identifier,
        actions=list(acciones),
        enabled=True,
        visible=True,
        offscreen=False,
        window_id=100,
        depth=depth,
        parent_id=parent_id,
    )


class _AdapterFalso:
    """Adaptador de escritorio falso y determinista para probar el algoritmo.

    Simula una ventana 100 (pid 1234) con un arbol de accesibilidad que cambia
    segun el estado interno. Las acciones de accesibilidad cambian el estado de
    forma predecible para verificar el recorrido del explorador.
    """

    def __init__(self, modo="estandar"):
        self.modo = modo
        self.estado = "raiz"
        self.realizadas = []
        self.cierres = []
        self.fallar_siguiente_accion = False
        self.fallar_colapso = False

    def list_windows(self, pid=None, visible_only=True):
        return PlatformResult.success([
            WindowInfo(window_id=100, pid=1234, title="App de prueba", is_visible=True)
        ])

    def get_window(self, window_id):
        return PlatformResult.success(WindowInfo(window_id=100, pid=1234))

    def get_accessibility_tree(self, window_id, pid=None, max_depth=60, max_nodes=2000):
        if self.modo == "refrescar":
            nodos = [_nodo("n1", "Button", "Button", "Refrescar", "btn_refrescar", ["expand"], 1)]
        elif self.estado == "raiz":
            nodos = [
                _nodo("n1", "Button", "Button", "Menu", "btn_menu", ["expand"], 1),
                _nodo("n2", "Button", "Button", "Guardar", "btn_guardar", ["expand"], 1),
            ]
        elif self.estado == "menu":
            nodos = [
                _nodo("n1", "Button", "Button", "Menu", "btn_menu", ["collapse", "expand"], 1),
                _nodo(
                    "n2",
                    "MenuItem",
                    "MenuItem",
                    "Submenu",
                    "submenu",
                    ["expand", "invoke"],
                    2,
                    "n1",
                ),
            ]
        elif self.estado == "menu_abierto":
            nodos = [
                _nodo("n1", "Button", "Button", "Menu", "btn_menu", ["collapse", "expand"], 1),
                _nodo(
                    "n2",
                    "MenuItem",
                    "MenuItem",
                    "Submenu",
                    "submenu",
                    ["collapse", "expand", "invoke"],
                    2,
                    "n1",
                ),
                _nodo("n3", "MenuItem", "MenuItem", "Opcion", "opcion", ["invoke"], 3, "n2"),
            ]
        else:
            nodos = []
        return PlatformResult.success(
            AccessibilityTree(window_id=100, pid=1234, source="fake", nodes=nodos, root_id="n1")
        )

    def get_foreground_window(self):
        return PlatformResult.success(WindowInfo(window_id=100, pid=1234))

    def perform_accessibility_action(self, window_id, node_id, action, value=None):
        self.realizadas.append((node_id, action))
        if self.fallar_siguiente_accion:
            self.fallar_siguiente_accion = False
            return PlatformResult.failure(PlatformErrorCode.NATIVE_ERROR, "fallo inyectado")
        if self.fallar_colapso and action == "collapse":
            self.fallar_colapso = False
            return PlatformResult.failure(PlatformErrorCode.NATIVE_ERROR, "colapso inyectado")
        if self.modo == "refrescar" and node_id == "n1" and action == "expand":
            return PlatformResult.success(None)
        if self.estado == "raiz" and node_id == "n1" and action == "expand":
            self.estado = "menu"
        elif self.estado == "menu" and node_id == "n1" and action == "collapse":
            self.estado = "raiz"
        elif self.estado == "menu" and node_id == "n2" and action == "expand":
            self.estado = "menu_abierto"
        elif self.estado == "menu_abierto" and node_id == "n2" and action == "collapse":
            self.estado = "menu"
        return PlatformResult.success(None)

    def press_keys(self, keys):
        return PlatformResult.success(None)

    def close_window(self, window_id):
        self.cierres.append(window_id)
        return PlatformResult.success(None)


# ---------------------------------------------------------------------------
# DeepUIExplorer: algoritmo de exploracion acotada (3.8.6.12.3)
# ---------------------------------------------------------------------------


class TestDeepUIExplorer:
    def _explorador(self, adapter=None, **presupuesto_kwargs):
        if adapter is None:
            adapter = _AdapterFalso()
        if presupuesto_kwargs:
            presupuesto = ExplorationBudget(**presupuesto_kwargs)
        else:
            presupuesto = ExplorationBudget()
        return DeepUIExplorer(adapter=adapter, app_id="app_prueba", budget=presupuesto)

    def test_exploracion_bsf_registra_estados_y_transiciones_verificadas(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert resultado.abort_reason == ""
        assert resultado.budget_exhausted == ""
        assert len(resultado.errors) == 0
        assert len(resultado.state_map.states) == 3  # raiz, menu, menu_abierto
        assert len(resultado.state_map.transitions) == 2
        assert all(t.verified_return for t in resultado.state_map.transitions)
        acciones_realizadas = [a["element_ref"].get("identifier") for a in explorador.performed_actions]
        assert "btn_menu" in acciones_realizadas
        assert "btn_guardar" not in acciones_realizadas  # prohibido, nunca se ejecuta
        assert resultado.state_map.has_state(resultado.state_map.root_state_id)

    def test_respeta_presupuesto_profundidad(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter, max_depth=1)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert resultado.budget_exhausted == ""
        assert len(resultado.state_map.states) == 2  # raiz + menu
        assert len(resultado.state_map.transitions) == 1
        transicion = resultado.state_map.transitions[0]
        assert transicion.action == ACTION_EXPAND
        assert transicion.element_ref["identifier"] == "btn_menu"
        assert transicion.verified_return is True
        # No se alcanza menu_abierto porque el siguiente nivel excede la profundidad.
        assert all(t.element_ref["identifier"] != "submenu" for t in resultado.state_map.transitions)

    def test_respeta_presupuesto_tiempo(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter, max_seconds=0)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert resultado.budget_exhausted == "presupuesto de tiempo agotado"
        assert len(resultado.state_map.states) == 1  # solo raiz
        assert len(resultado.state_map.transitions) == 0
        assert resultado.checkpoint is not None

    def test_respeta_presupuesto_estados(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter, max_states=2)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert resultado.budget_exhausted == "presupuesto de estados agotado"
        assert len(resultado.state_map.states) == 2  # raiz + menu
        assert len(resultado.state_map.transitions) == 1
        assert resultado.checkpoint is not None
        assert len(resultado.checkpoint.frontier) == 2
        assert [] in resultado.checkpoint.frontier
        assert any(
            len(p) == 1
            and p[0]["action"] == ACTION_EXPAND
            and p[0]["element_ref"].get("identifier") == "btn_menu"
            for p in resultado.checkpoint.frontier
        )

    def test_es_reanudable_desde_checkpoint(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter, max_states=2)
        parcial = explorador.explore(window_id=100, pid=1234, mode="full")
        assert parcial.budget_exhausted == "presupuesto de estados agotado"
        assert parcial.checkpoint is not None
        acciones_parcial = parcial.actions_performed

        adapter2 = _AdapterFalso()
        explorador2 = self._explorador(adapter2)
        completo = explorador2.explore(
            window_id=100, pid=1234, mode="full", checkpoint=parcial.checkpoint
        )
        assert completo.aborted is False
        assert completo.budget_exhausted == ""
        assert len(completo.state_map.states) == 3  # raiz, menu, menu_abierto
        assert len(completo.state_map.transitions) == 2
        assert completo.actions_performed > acciones_parcial

    def test_estado_repetido_no_se_duplica(self):
        adapter = _AdapterFalso(modo="refrescar")
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert len(resultado.state_map.states) == 1  # solo raiz, sin duplicados
        assert len(resultado.state_map.transitions) == 1
        transicion = resultado.state_map.transitions[0]
        assert transicion.from_state == transicion.to_state  # auto-bucle sobre raiz
        assert transicion.verified_return is True
        assert resultado.state_map.root_state_id == transicion.from_state

    def test_accion_prohibida_se_salta_y_no_se_ejecuta(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        prohibidas = [
            s for s in resultado.skipped_forbidden if s["action"] == ACTION_EXPAND
        ]
        assert len(prohibidas) == 1
        assert "guardar" in prohibidas[0]["reason"]
        assert all(
            a["element_ref"].get("identifier") != "btn_guardar"
            for a in explorador.performed_actions
        ), "btn_guardar nunca debe ejecutarse"

    def test_accion_que_falla_sin_cambiar_interfaz_se_registra_y_continua(self):
        adapter = _AdapterFalso()
        adapter.fallar_siguiente_accion = True
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is False
        assert len(resultado.state_map.states) == 1  # raiz, no avanzo
        assert len(resultado.state_map.transitions) == 0
        assert len(resultado.errors) == 1
        assert "fallo inyectado" in resultado.errors[0]

    def test_fallo_de_vuelta_provoca_parada_segura(self):
        adapter = _AdapterFalso()
        adapter.fallar_colapso = True
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is True
        assert "no se pudo volver" in resultado.abort_reason
        assert len(resultado.state_map.states) == 2  # raiz + menu
        assert len(resultado.state_map.transitions) == 1
        assert resultado.state_map.transitions[0].verified_return is False

    def test_sin_arbol_accesibilidad_aborta(self):
        adapter = _AdapterFalso()

        def arbol_fallido(window_id, pid=None, max_depth=60, max_nodes=2000):
            return PlatformResult.failure(PlatformErrorCode.NOT_FOUND, "sin arbol")

        adapter.get_accessibility_tree = arbol_fallido
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is True
        assert "sin arbol de accesibilidad" in resultado.abort_reason

    def test_ventana_principal_inaccesible_aborta(self):
        adapter = _AdapterFalso()

        def get_window_falla(window_id):
            return PlatformResult.failure(PlatformErrorCode.NOT_FOUND, "no existe")

        adapter.get_window = get_window_falla
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")
        assert resultado.aborted is True
        assert "ventana principal no existe o no es accesible" in resultado.abort_reason

    def test_modo_branch_detiene_al_encontrar_objetivo(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter)
        ref_submenu = {
            "identifier": "submenu",
            "name": "Submenu",
            "native_role": "MenuItem",
            "parent_name": "Menu",
            "depth": 2,
        }
        resultado = explorador.explore(
            window_id=100, pid=1234, mode="branch", target_ref=ref_submenu
        )
        assert resultado.aborted is False
        assert resultado.target_found is True
        assert len(resultado.target_path) == 1
        assert resultado.target_path[0]["action"] == ACTION_EXPAND
        assert len(resultado.state_map.states) == 2  # raiz + menu

    def test_modo_branch_requiere_target_ref(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter)
        with pytest.raises(ValueError, match="requiere target_ref"):
            explorador.explore(window_id=100, pid=1234, mode="branch")

    def test_modo_invalido_raise_valuerror(self):
        adapter = _AdapterFalso()
        explorador = self._explorador(adapter)
        with pytest.raises(ValueError, match="mode debe ser"):
            explorador.explore(window_id=100, pid=1234, mode="invalido")


# ---------------------------------------------------------------------------
# Dobles de prueba para recuperacion de exploracion (3.8.6.12.4)
# ---------------------------------------------------------------------------


class _AdapterRecuperacion(_AdapterFalso):
    """Adaptador para pruebas de recuperacion (3.8.6.12.4).

    Permite definir varias ventanas base (incluyendo una ventana del usuario
    que no es la principal) y una ventana que aparece tras una accion de
    exploracion (simula un dialogo/popup abierto por JARVIS o algo inesperado).
    Cada ventana devuelve su propio arbol de accesibilidad (la ventana del
    usuario no expone nodos explorables), de modo que _locate no resulta ambiguo.
    Solo se cierra (graceful, WM_CLOSE / AXCloseButton) lo que no estaba en el
    baseline; nunca se fuerza el cierre de la aplicacion del usuario.
    """

    def __init__(self, ventanas_base=None, ventana_nueva=None, fallar_colapso=False):
        super().__init__(modo="estandar")
        self.ventanas_base = list(ventanas_base or [100])
        self.ventana_nueva = ventana_nueva
        self.ventana_nueva_activa = False
        self.fallar_colapso = fallar_colapso

    def list_windows(self, pid=None, visible_only=True):
        ids = list(self.ventanas_base)
        if self.ventana_nueva is not None and self.ventana_nueva_activa:
            ids.append(self.ventana_nueva)
        return PlatformResult.success([
            WindowInfo(window_id=wid, pid=1234, title="App de prueba", is_visible=True)
            for wid in ids
        ])

    def get_window(self, window_id):
        return PlatformResult.success(WindowInfo(window_id=window_id, pid=1234))

    def _arbol_raiz(self):
        return [
            _nodo("n1", "Button", "Button", "Menu", "btn_menu", ["expand"], 1),
            _nodo("n2", "Button", "Button", "Guardar", "btn_guardar", ["expand"], 1),
        ]

    def _arbol_menu(self):
        return [
            _nodo("n1", "Button", "Button", "Menu", "btn_menu", ["collapse", "expand"], 1),
            _nodo("n2", "MenuItem", "MenuItem", "Submenu", "submenu", ["expand", "invoke"], 2, "n1"),
        ]

    def _arbol_vacio(self):
        return []

    def get_accessibility_tree(self, window_id, pid=None, max_depth=60, max_nodes=2000):
        if self.ventana_nueva is not None and window_id == self.ventana_nueva and self.ventana_nueva_activa:
            nodos = self._arbol_menu()
        elif window_id == 200 and 200 in self.ventanas_base:
            # Ventana del usuario: sin nodos explorables.
            nodos = self._arbol_vacio()
        else:
            if self.estado == "raiz":
                nodos = self._arbol_raiz()
            elif self.estado == "menu":
                nodos = self._arbol_menu()
            elif self.estado == "menu_abierto":
                nodos = self._arbol_menu() + [
                    _nodo("n3", "MenuItem", "MenuItem", "Opcion", "opcion", ["invoke"], 3, "n2"),
                ]
            else:
                nodos = []
        return PlatformResult.success(
            AccessibilityTree(
                window_id=window_id, pid=1234, source="fake", nodes=nodos,
                root_id="n1" if nodos else None,
            )
        )

    def perform_accessibility_action(self, window_id, node_id, action, value=None):
        self.realizadas.append((node_id, action))
        if self.fallar_colapso and action == "collapse":
            self.fallar_colapso = False
            return PlatformResult.failure(PlatformErrorCode.NATIVE_ERROR, "colapso inyectado")
        if action == "expand" and self.ventana_nueva is not None:
            self.ventana_nueva_activa = True
        if self.estado == "raiz" and node_id == "n1" and action == "expand":
            self.estado = "menu"
        elif self.estado == "menu" and node_id == "n1" and action == "collapse":
            self.estado = "raiz"
        elif self.estado == "menu" and node_id == "n2" and action == "expand":
            self.estado = "menu_abierto"
        elif self.estado == "menu_abierto" and node_id == "n2" and action == "collapse":
            self.estado = "menu"
        return PlatformResult.success(None)

    def close_window(self, window_id):
        self.cierres.append(window_id)
        return PlatformResult.success(None)


# ---------------------------------------------------------------------------
# Recuperacion de exploracion profunda (3.8.6.12.4)
# ---------------------------------------------------------------------------


class TestRecuperacionExploracion:
    """Pruebas de recuperacion de la exploracion profunda (3.8.6.12.4).

    Verifica que:
    - si la vuelta falla, la exploracion se detiene y se registra el estado;
    - se cierran solo ventanas abiertas durante la exploracion (no la ventana
      principal ni ventanas preexistentes del usuario);
    - nunca se fuerza el cierre de la aplicacion del usuario (close_window es
      graceful: WM_CLOSE / AXCloseButton, nunca TerminateProcess);
    - si aparece algo inesperado (ventana nueva no buscada), se para igualmente
      y solo se cierra lo que no estaba en el baseline.
    """

    def _explorador(self, adapter=None, **presupuesto_kwargs):
        if adapter is None:
            adapter = _AdapterRecuperacion()
        if presupuesto_kwargs:
            presupuesto = ExplorationBudget(**presupuesto_kwargs)
        else:
            presupuesto = ExplorationBudget()
        return DeepUIExplorer(adapter=adapter, app_id="app_rec", budget=presupuesto)

    def test_recuperacion_vuelta_falla_cierra_solo_ventana_abierta_por_jarvis(self):
        # Baseline: ventana principal 100 + ventana del usuario 200.
        # Al expandir el menu aparece la ventana 300 (abierta por JARVIS).
        # El colapso falla -> no se puede volver -> recuperacion.
        adapter = _AdapterRecuperacion(ventanas_base=[100, 200], ventana_nueva=300, fallar_colapso=True)
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")

        assert resultado.aborted is True
        assert resultado.abort_reason != ""
        assert "no se pudo volver" in resultado.abort_reason
        # Solo la ventana abierta por JARVIS (300) se cierra.
        assert 300 in resultado.closed_windows
        assert 300 in adapter.cierres
        # La ventana del usuario (200) y la principal (100) nunca se cierran.
        assert 200 not in resultado.closed_windows
        assert 200 not in adapter.cierres
        assert 100 not in resultado.closed_windows
        assert 100 not in adapter.cierres
        # btn_guardar (prohibido) nunca se ejecuta.
        assert all(
            a["element_ref"].get("identifier") != "btn_guardar"
            for a in explorador.performed_actions
        )

    def test_recuperacion_ventana_inesperada_preserva_ventanas_usuario(self):
        # Aparece una ventana inesperada 400 durante la exploracion (no fue
        # solicitada por el explorador, simplemente esta ahi). El retorno no
        # puede restaurar el estado original porque 400 persiste.
        adapter = _AdapterRecuperacion(ventanas_base=[100, 200], ventana_nueva=400, fallar_colapso=False)
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")

        assert resultado.aborted is True
        assert resultado.abort_reason != ""
        # La ventana inesperada se cierra (graceful).
        assert 400 in resultado.closed_windows
        assert 400 in adapter.cierres
        # Las ventanas del usuario y la principal se preservan.
        assert 200 not in resultado.closed_windows
        assert 200 not in adapter.cierres
        assert 100 not in resultado.closed_windows
        assert 100 not in adapter.cierres

    def test_recuperacion_registra_estado_y_acciones(self):
        adapter = _AdapterRecuperacion(ventanas_base=[100, 200], ventana_nueva=300, fallar_colapso=True)
        explorador = self._explorador(adapter)
        resultado = explorador.explore(window_id=100, pid=1234, mode="full")

        assert resultado.aborted is True
        assert resultado.abort_reason != ""
        assert resultado.closed_windows == [300]
        assert resultado.actions_performed > 0
        # El resultado serializable incluye el estado de aborto.
        d = resultado.to_dict()
        assert d["aborted"] is True
        assert d["abort_reason"] != ""
        assert d["closed_windows_count"] == 1

    def test_recuperacion_no_ejecuta_acciones_prohibidas_durante_el_retorno(self):
        # Durante el intento de volver (collapse/escape) nunca se ejecuta una
        # accion de escritura ni se pulsa un boton prohibido.
        adapter = _AdapterRecuperacion(ventanas_base=[100, 200], ventana_nueva=300, fallar_colapso=True)
        explorador = self._explorador(adapter)
        explorador.explore(window_id=100, pid=1234, mode="full")

        ejecutados = [a["action"] for a in explorador.performed_actions]
        assert "set_value" not in ejecutados
        assert "toggle" not in ejecutados
        assert "type_text" not in ejecutados
        assert "invoke_leaf" not in ejecutados
        # btn_guardar nunca se pulsa ni siquiera como intento de retorno.
        assert all(
            a["element_ref"].get("identifier") != "btn_guardar"
            for a in explorador.performed_actions
        )
