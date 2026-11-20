# -*- coding: utf-8 -*-
"""Tests de unidad del mapa de estados UI (unidad 3.8.6.12.1).

Cubre:
- UIStateNode: creacion, serializacion y deserializacion del estado UI.
- UITransition: transicion accion -> estado resultante con forma de volver.
- UIStateMap: mapa de estados, transiciones, ruta verificada y representacion logica.
- element_reference: referencia logica de un elemento sin coordenadas fisicas.
- ExplorationSafetyPolicy: acciones admitidas y decisiones de permitido/denegado.
- ExplorationBudget: limites de exploracion y serializacion.
- ExplorationCheckpoint: punto de control serializable y round-trip JSON.
- persist_state_map_logically: persistencia logica en el catalogo (sin coordenadas).

Todos los tests son deterministas, sin interaccion GUI ni SO real.
"""

from unittest.mock import MagicMock

import pytest

from src.hands.calibration.ui_exploration import (
    ACTION_EXPAND,
    ACTION_OPEN_DIALOG,
    ACTION_OPEN_MENU,
    ACTION_SELECT_TAB,
    ExplorationBudget,
    ExplorationCheckpoint,
    ExplorationSafetyPolicy,
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
