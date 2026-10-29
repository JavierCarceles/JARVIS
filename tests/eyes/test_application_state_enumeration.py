# -*- coding: utf-8 -*-
"""Inspecci\u00F3n de estados soportados por el c\u00F3digo y los datos (hoja 3.4.1.1).

OBJETIVO DE LA HOJA: "Enumerar estados realmente soportados por el
c\u00F3digo/datos."

Esta suite documenta y verifica, contra el modelo REAL, el conjunto de
"estados" que el sistema JARVIS reconoce en cada una de sus capas. No modifica
c\u00F3digo de producci\u00F3n; es una inspecci\u00F3n read-only que registra
qu\u00E9 estados existen y d\u00F3nde, dejando constancia de las discrepancias
para que las hojas siguientes de la fase 3.4 (3.4.1.2, 3.4.1.3) las resuelvan.

Capas inspeccionadas:

A. **Percepci\u00F3n** (\`src/eyes/screen.py\`): \
   \`ApplicationState\` Enum (5 miembros: closed, open, active, minimized,
   maximized). Usado por Vision/Screen para clasificar el estado visual de una
   ventana.

B. **Conocimiento de aplicaciones / planificaci\u00F3n** (\`src/hands/applications_core.py\`): \
   \`ApplicationState\` Enum (8 miembros: closed, open, active, inactive,
   loading, ready, error, background). Usado por \`ApplicationKnowledge.states\`
   y \`default_state\`.

C. **Datos de conocimiento** (\`data/knowledge/applications.json\`): \
   diccionario por-app de flags booleanos (open, active, maximized, focused,
   playing, streaming, recording).

D. **Datos de capacidades** (\`data/knowledge/capabilities.json\`): \
   \`required_state\` y \`effects\` como \u00E1tomos de estado para la
   planificaci\u00F3n.

E. **Grafo planificador** (\`src/hands/planner/graph.py\` \`GraphBuilder\`): \
   claves de hechos de estado codificadas en \`build_navigation_graph\` y
   \`build_application_graph\`.

DISCREPANCIA PRINCIPAL (D-STATE-TWO-ENUMS): existe dos \`ApplicationState\`
Enum con el mismo nombre pero miembros distintos (solo 3 se superponen). No
hay import-crossing en producci\u00F3n: cada capa usa su propio enum.

DISCREPANCIA SECUNDARIA (D-STATE-DATA-ONLY): los datos declaran estados
(focused, playing, streaming, recording) que no aparecen en ninguno de los dos
Enum.
"""

import json

import pytest

from src.eyes.screen import (
    ApplicationState as ScreenApplicationState,
    ApplicationInfo,
    WorldState,
)
from src.hands.applications_core import (
    ApplicationState as HandsApplicationState,
    ApplicationKnowledge,
    ApplicationManager,
    get_application_manager,
)
from src.hands.planner.graph import GraphBuilder, StateGraph
from src.hands.planner.node import Node, NodeType
from src.utils.config import get_project_root

APPS_JSON_PATH = get_project_root() / "data" / "knowledge" / "applications.json"
CAPS_JSON_PATH = get_project_root() / "data" / "knowledge" / "capabilities.json"


# ---------------------------------------------------------------------------
# A. Capa percepci\u00F3n — ApplicationState en src/eyes/screen.py
# ---------------------------------------------------------------------------

class TestPerceptionLayerStateEnum:
    """Verifica los miembros del Enum de percepci\u00F3n (eyes/screen.py)."""

    def test_perception_enum_has_exactly_five_members(self):
        members = {m.value for m in ScreenApplicationState}
        assert members == {"closed", "open", "active", "minimized", "maximized"}

    def test_perception_enum_member_names(self):
        names = {m.name for m in ScreenApplicationState}
        assert names == {
            "CLOSED", "OPEN", "ACTIVE", "MINIMIZED", "MAXIMIZED",
        }

    def test_perception_enum_known_values(self):
        assert ScreenApplicationState.CLOSED.value == "closed"
        assert ScreenApplicationState.OPEN.value == "open"
        assert ScreenApplicationState.ACTIVE.value == "active"
        assert ScreenApplicationState.MINIMIZED.value == "minimized"
        assert ScreenApplicationState.MAXIMIZED.value == "maximized"

    def test_perception_enum_no_extra_members(self):
        """No hay miembros adicionales m\u00E1s all\u00E1 los 5 declarados."""
        assert len(list(ScreenApplicationState)) == 5


# ---------------------------------------------------------------------------
# B. Capa de conocimiento de aplicaciones — ApplicationState en
#    src/hands/applications_core.py
# ---------------------------------------------------------------------------

class TestPlanningLayerStateEnum:
    """Verifica los miembros del Enum de planificaci\u00F3n (applications_core.py)."""

    def test_planning_enum_has_exactly_eight_members(self):
        members = {m.value for m in HandsApplicationState}
        assert members == {
            "closed", "open", "active", "inactive", "loading",
            "ready", "error", "background",
        }

    def test_planning_enum_member_names(self):
        names = {m.name for m in HandsApplicationState}
        assert names == {
            "CLOSED", "OPEN", "ACTIVE", "INACTIVE", "LOADING",
            "READY", "ERROR", "BACKGROUND",
        }

    def test_planning_enum_no_extra_members(self):
        assert len(list(HandsApplicationState)) == 8


# ---------------------------------------------------------------------------
# C. Discrepancia entre los dos Enum
# ---------------------------------------------------------------------------

class TestStateEnumDiscrepancy:
    """Documenta que los dos ApplicationState Enum tienen miembros distintos.

    D-STATE-TWO-ENUMS: ambos enums comparten el nombre ApplicationState pero
    no comparten la misma definici\u00F3n. Solo 3 valores coinciden.
    """

    def test_two_enums_have_different_member_sets(self):
        screen_vals = {m.value for m in ScreenApplicationState}
        hands_vals = {m.value for m in HandsApplicationState}
        assert screen_vals != hands_vals

    def test_three_shared_members(self):
        screen_vals = {m.value for m in ScreenApplicationState}
        hands_vals = {m.value for m in HandsApplicationState}
        shared = screen_vals & hands_vals
        assert shared == {"closed", "open", "active"}

    def test_perception_only_members(self):
        screen_vals = {m.value for m in ScreenApplicationState}
        hands_vals = {m.value for m in HandsApplicationState}
        only_screen = screen_vals - hands_vals
        assert only_screen == {"minimized", "maximized"}

    def test_planning_only_members(self):
        screen_vals = {m.value for m in ScreenApplicationState}
        hands_vals = {m.value for m in HandsApplicationState}
        only_hands = hands_vals - screen_vals
        assert only_hands == {"inactive", "loading", "ready", "error", "background"}


# ---------------------------------------------------------------------------
# D. Datos — data/knowledge/applications.json (states por app, dict bool)
# ---------------------------------------------------------------------------

class TestDataApplicationStates:
    """Verifica el diccionario \`states\` booleano por aplicaci\u00F3n en
    data/knowledge/applications.json."""

    def test_applications_json_states_exist_for_known_apps(self):
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        for app_key in ("chrome", "spotify", "vscode", "obs_studio"):
            assert "states" in data[app_key], f"{app_key} debe tener clave 'states'"

    def test_chrome_states_keys(self):
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        keys = set(data["chrome"]["states"].keys())
        assert keys == {"open", "active", "maximized", "focused"}

    def test_spotify_states_keys(self):
        # 3.4.1.2: `active` se separa como flag independiente (era omitido, confundido con `open`).
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        keys = set(data["spotify"]["states"].keys())
        assert keys == {"open", "active", "playing", "maximized", "focused"}

    def test_vscode_states_keys(self):
        # 3.4.1.2: `active` se separa como flag independiente.
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        keys = set(data["vscode"]["states"].keys())
        assert keys == {"open", "active", "maximized", "focused"}

    def test_obs_states_keys(self):
        # 3.4.1.2: `active` y `focused` se separan como flags independientes.
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        keys = set(data["obs_studio"]["states"].keys())
        assert keys == {"open", "active", "streaming", "recording", "maximized", "focused"}

    def test_data_union_of_states(self):
        """La uni\u00F3n de todas las claves 'states' del data."""
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        union = set()
        for app_data in data.values():
            union.update(app_data.get("states", {}).keys())
        assert union == {
            "open", "active", "maximized", "focused",
            "playing", "streaming", "recording",
        }

    def test_data_states_are_boolean_dicts(self):
        data = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        for app_key, app_data in data.items():
            states = app_data.get("states", {})
            assert isinstance(states, dict)
            for value in states.values():
                assert isinstance(value, bool)


# ---------------------------------------------------------------------------
# E. Datos — data/knowledge/capabilities.json (required_state / effects)
# ---------------------------------------------------------------------------

class TestDataCapabilityStateAtoms:
    """Verifica los \u00E1tomos de estado en required_state y effects de
    data/knowledge/capabilities.json."""

    @pytest.fixture(scope="class")
    def caps_data(self):
        return json.loads(CAPS_JSON_PATH.read_text(encoding="utf-8"))

    def test_required_state_atoms(self, caps_data):
        atoms = set()
        for cat, cat_data in caps_data.items():
            for cap_name, cap_data in cat_data.items():
                atoms.update(cap_data.get("required_state", []))
        assert atoms == {
            "application_open", "chrome_open", "chrome_active",
            "address_bar_focused", "url_typed",
            "spotify_open", "spotify_active", "media_playing",
            "search_bar_focused",
            "vscode_open", "vscode_active", "file_opened", "terminal_open",
            "obs_open", "obs_active", "stream_started", "recording_started",
        }

    def test_effects_atoms(self, caps_data):
        atoms = set()
        for cat, cat_data in caps_data.items():
            for cap_name, cap_data in cat_data.items():
                atoms.update(cap_data.get("effects", []))
        # Nota: los átomos efectos NO incluyen los flags de apertura/activación
        # por app (chrome_open, chrome_active, spotify_open, ...). Esas claves
        # aparecen SOLO en required_state — son precondiciones, no efectos.
        assert atoms == {
            "application_open", "application_closed", "window_active",
            "address_bar_focused", "url_typed", "navigation_initiated",
            "url_changed", "new_tab_opened", "tab_closed", "page_refreshed",
            "media_playing", "media_paused", "track_changed",
            "search_results_displayed",
            "file_opened", "file_saved", "code_executed", "terminal_opened",
            "stream_started", "stream_stopped",
            "recording_started", "recording_stopped",
        }


# ---------------------------------------------------------------------------
# F. Grafo planificador — GraphBuilder state fact keys (graph.py)
# ---------------------------------------------------------------------------

class TestPlannerGraphStateKeys:
    """Verifica las claves de hechos de estado codificadas en GraphBuilder."""

    @pytest.fixture(scope="class")
    def all_graph_state_keys(self):
        # Nodos requeridos por build_navigation_graph y build_application_graph
        nav_ids = [
            "chrome.closed", "chrome.open", "chrome.activate",
            "focus_address_bar", "type_url", "press_enter",
            "destination.loaded", "click_address_bar",
            "hotkey_ctrl_l", "search_google",
        ]
        app_ids = [
            "application.closed", "application.open", "application.active",
            "application.inactive", "element.focused", "text.typed",
            "action.executed",
        ]
        keys = set()
        for builder_ids in (nav_ids, app_ids):
            nodes = {
                nid: Node(id=nid, type=NodeType.STATE, name=nid, description="")
                for nid in builder_ids
            }
            if builder_ids is nav_ids:
                g = GraphBuilder.build_navigation_graph(nodes)
            else:
                g = GraphBuilder.build_application_graph(nodes)
            for edge in g.edges:
                keys.update(edge.conditions)
                for pc in edge.preconditions:
                    k = getattr(pc, "key", None)
                    if k:
                        keys.add(k)
                for ef in edge.effects:
                    k = getattr(ef, "key", None)
                    if k:
                        keys.add(k)
        return keys

    def test_navigation_graph_has_chrome_state_keys(self, all_graph_state_keys):
        for k in ("chrome_closed", "chrome_open", "chrome_active"):
            assert k in all_graph_state_keys

    def test_application_graph_has_app_state_keys(self, all_graph_state_keys):
        for k in ("app_closed", "app_open", "app_active", "app_inactive"):
            assert k in all_graph_state_keys

    def test_graph_state_keys_partial_overlap_with_data(self, all_graph_state_keys):
        """El grafo planificador usa claves de hechos de estado que apenas se
        superponen con los \u00E1tomos de data/knowledge/capabilities.json.

        D-STATE-GRAPH-DATA-GAP: claves del grafo que NO aparecen en data:
        element_focused, destination_loaded, search_performed, text_typed,
        address_bar_clicked, app_closed, app_inactive, app_open, chrome_closed.
        El grafo mantiene su propio vocabulario plano parcial con estados
        intermedios no modelados en los datos can\u00F3nicos.
        """
        data = json.loads(CAPS_JSON_PATH.read_text(encoding="utf-8"))
        cap_atoms = set()
        for cat_data in data.values():
            for cap_data in cat_data.values():
                cap_atoms.update(cap_data.get("required_state", []))
                cap_atoms.update(cap_data.get("effects", []))
        in_data = all_graph_state_keys & cap_atoms
        assert in_data == {"address_bar_focused", "url_typed", "chrome_active", "chrome_open"}
        not_in_data = all_graph_state_keys - cap_atoms
        assert not_in_data == {
            "address_bar_clicked", "destination_loaded", "search_performed",
            "text_typed",
            "app_closed", "app_open", "app_active", "app_inactive",
            "chrome_closed",
            "element_focused",
        }

    def test_full_graph_state_key_union(self, all_graph_state_keys):
        expected = {
            "chrome_closed", "chrome_open", "chrome_active",
            "address_bar_focused", "url_typed", "destination_loaded",
            "address_bar_clicked", "search_performed",
            "app_closed", "app_open", "app_active", "app_inactive",
            "element_focused", "text_typed",
        }
        assert all_graph_state_keys == expected


# ---------------------------------------------------------------------------
# G. Estados en datos que NO aparecen en ningún Enum
# ---------------------------------------------------------------------------

class TestDataOnlyStateNames:
    """Documenta estados declarados en data/knowledge que no existen como miembro
    de ninguno de los dos ApplicationState Enum.

    D-STATE-DATA-ONLY: 'focused', 'playing', 'streaming', 'recording' aparecen
    en data/knowledge/applications.json (states) y/o capabilities.json
    (required_state/effects), pero no son miembros de ningún Enum de estado.
    """

    @pytest.fixture(scope="class")
    def data_only_states(self):
        # Union de claves de states en applications.json + atoms en capabilities.json
        apps = json.loads(APPS_JSON_PATH.read_text(encoding="utf-8"))
        caps = json.loads(CAPS_JSON_PATH.read_text(encoding="utf-8"))
        data_states = set()
        for app_data in apps.values():
            data_states.update(app_data.get("states", {}).keys())
        cap_atoms = set()
        for cat_data in caps.values():
            for cap_data in cat_data.values():
                cap_atoms.update(cap_data.get("required_state", []))
                cap_atoms.update(cap_data.get("effects", []))
        data_states |= cap_atoms
        return data_states

    def test_data_states_not_in_planning_enum(self, data_only_states):
        hands_vals = {m.value for m in HandsApplicationState}
        not_in_hands = data_only_states - hands_vals
        # focused, playing, streaming, recording, media_paused, etc. no están
        # en el Enum de planificación.
        assert "focused" in not_in_hands
        assert "playing" in not_in_hands
        assert "streaming" in not_in_hands
        assert "recording_started" in not_in_hands

    def test_data_atoms_not_in_perception_enum(self, data_only_states):
        screen_vals = {m.value for m in ScreenApplicationState}
        not_in_screen = data_only_states - screen_vals
        # states como focused, playing, streaming, recording, chrome_open, etc.
        # no están en el Enum de percepción.
        for s in ("focused", "playing", "streaming", "recording_started"):
            assert s in not_in_screen


# ---------------------------------------------------------------------------
# H. ApplicationKnowledge.states declarados (modelo real)
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeDeclaredStates:
    """Verifica los estados declarados en el modelo real para apps hardcoded.

    Chrome y Spotify están hardcoded en ApplicationManager.__init__ con listas
    de estados explícitas. Apps reconstruidas desde entities.json carecen de la
    clave 'states' y reciben el default [CLOSED].
    """

    def test_chrome_declared_states(self):
        app = get_application_manager().get_application("chrome")
        assert app is not None
        assert [s.value for s in app.states] == [
            "closed", "open", "active", "loading",
        ]

    def test_spotify_declared_states(self):
        app = get_application_manager().get_application("spotify")
        assert app is not None
        assert [s.value for s in app.states] == ["closed", "open", "active"]

    def test_reconstructed_app_defaults_to_closed(self):
        """YouTube se reconstruye desde entities.json (sin clave 'states') y
        recibe [CLOSED] como único estado declarado (contrato
        ApplicationKnowledge.__post_init__)."""
        app = get_application_manager().get_application("youtube")
        assert app is not None
        assert app is not None
        assert [s.value for s in app.states] == ["closed"]

    def test_application_knowledge_default_state_is_closed(self):
        ak = ApplicationKnowledge(name="test", type="application")
        assert ak.default_state == HandsApplicationState.CLOSED
        assert ak.states == [HandsApplicationState.CLOSED]

    def test_reconstruct_states_unknown_string_omitted(self):
        """_reconstruct_states omite strings inválidos (no lanza) y devuelve
        [CLOSED] si ninguno es válido."""
        result = ApplicationManager._reconstruct_states(["teleportar"])
        assert result == [HandsApplicationState.CLOSED]

    def test_reconstruct_states_valid_strings(self):
        result = ApplicationManager._reconstruct_states(["open", "loading", "ready"])
        assert result == [
            HandsApplicationState.OPEN,
            HandsApplicationState.LOADING,
            HandsApplicationState.READY,
        ]


# ---------------------------------------------------------------------------
# I. WorldState / ApplicationInfo (screen.py)
# ---------------------------------------------------------------------------

class TestWorldStateApplicationInfo:
    """Verifica que WorldState y ApplicationInfo usan ApplicationState de
    screen.py (percepci\u00F3n), no el de applications_core."""

    def test_application_info_is_screen_enum(self):
        info = ApplicationInfo(name="x", state=ScreenApplicationState.ACTIVE)
        assert info.state == ScreenApplicationState.ACTIVE
        # El Enum de percepción tiene MINIMIZED/MAXIMIZED que el de planning no
        assert hasattr(ScreenApplicationState, "MINIMIZED")
        assert not hasattr(HandsApplicationState, "MINIMIZED")

    def test_world_state_defaults(self):
        ws = WorldState(timestamp=0.0, applications={})
        assert ws.focused_application is None
        assert ws.applications == {}
