# -*- coding: utf-8 -*-
"""Tests de verificación de la hoja 3.3.4.1 — «Caso de aplicacion con varias
capacidades».

Verifica el **camino de planificación** de las capabilities, complementario a la
hoja 3.3.3.3 (trazabilidad). Mientras
``trace_application_capability_to_action`` documenta los nodos proveedores
*ignorando* el estado, ``_find_nodes_for_capability`` —usado por
``_build_hierarchical_plan``— aplica el filtro de estado ``can_execute`` y solo
devuelve los nodos **ejecutables** para la capability solicitada en el estado
actual.

Chrome es la aplicación de referencia de «varias capabilities» : expone
``open``, ``navigate`` y ``search``, cada una proveída por nodos distintos
(``chrome.open``, ``chrome_open``, ``chrome_navigate``, ``search_google``,
``chrome_search``). Los tests se ejercitan contra el modelo REAL: no escriben ni
alteran ``entities.json`` ni el ``ActionRegistry`` global.
"""

import logging
from typing import Dict

# ---------------------------------------------------------------------------
# SUPRESIÓN DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
# Importar Planner inicializa componentes del sistema (PerformanceOptimizer,
# SelfImprovementSystem, etc.) que escriben a stdout.
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.planner.planner import Planner  # noqa: E402
from src.hands.planner.node import Node, NodeType  # noqa: E402


# Capacidades canónicas que expone Chrome (verificado contra el modelo real).
CHROME_CAPABILITIES = ["open", "navigate", "search"]

# Aplicación conocida en el modelo pero SIN capacities declaradas
# (verificado contra el modelo real: YouTube está en entities.json con
# type=video_platform y sin campo capabilities, por lo que
# ApplicationKnowledge.capabilities == []).
NO_CAP_APP = "youtube"
NO_CAP_APP_NAME = "YouTube"

# Capacidades canónicas que un planner solicita por defecto (ver
# Goal.get_required_capabilities / Planner._node_provides_capability aliases).
CANONICAL_CAPABILITIES = ["open", "navigate", "search"]

# Capability totalmente desconocida: no es canónica (open/navigate/search), no
# está en el mapa de aliases de _node_provides_capability, ni es declarada por
# ninguna aplicación ni nodo del modelo real. Verificado read-only contra el
# modelo real: ningún nodo la provee.
UNKNOWN_CAPABILITY = "teleportar"

# Estado que satisface las precondiciones declarativas de los nodos ejecutables
# de Chrome (verificado contra el modelo real):
#   open        -> chrome.open        (precondition: application_available)
#   navigate    -> chrome_navigate    (chrome_open, chrome_active,
#                                      address_bar_focused,
#                                      chrome_address_bar_available)
#   search      -> search_google / chrome_search
#                 (chrome_open, chrome_active, chrome_search_bar_available)
CHROME_EXECUTABLE_STATE = {
    "application_available": True,
    "chrome_open": True,
    "chrome_active": True,
    "address_bar_focused": True,
    "chrome_address_bar_available": True,
    "chrome_search_bar_available": True,
}


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    """Mantiene ``logging.disable(CRITICAL)`` activo durante toda la sesión."""
    logging.disable(logging.CRITICAL)
    yield


def _planner() -> Planner:
    """Planificador con el integrador REAL (singleton)."""
    return Planner()


def _chrome_nodes(planner: Planner):
    """Nodos cuya aplicación normaliza a 'chrome' (equivalente a la scoping que
    aplica ``build_application_aware_plan`` al filtrar por aplicación objetivo)."""
    nodes = planner._get_available_nodes()
    return {
        nid: node
        for nid, node in nodes.items()
        if str(getattr(node, "application", "")).lower() == "chrome"
    }


# ---------------------------------------------------------------------------
# Caso de aplicacion con varias capacidades
# ---------------------------------------------------------------------------


class TestFindNodesForCapabilityMultipleCapabilities:
    """El camino de planificación (``_find_nodes_for_capability``) resuelve CADA
    capability de una aplicación con varias capacidades a su/s nodo/s ejecutable,
    aplicando la puerta ``can_execute`` que la trazabilidad de 3.3.3.3 no aplica."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_app_with_several_exposes_more_than_one_capability(self):
        """Premisa: Chrome expone más de una capability canónica."""
        caps = self.planner.get_application_capabilities_as_list("chrome")
        assert caps == CHROME_CAPABILITIES
        assert len(caps) > 1

    def test_each_capability_resolves_to_distinct_executable_nodes(self):
        """En un estado que las habilita, cada capability de Chrome resuelve a su
        nodo ejecutable concreto (varias capabilities → nodos distintos)."""
        chrome_nodes = _chrome_nodes(self.planner)

        open_nodes = [
            getattr(n, "id", None)
            for n in self.planner._find_nodes_for_capability(
                "open", chrome_nodes, CHROME_EXECUTABLE_STATE
            )
        ]
        navigate_nodes = [
            getattr(n, "id", None)
            for n in self.planner._find_nodes_for_capability(
                "navigate", chrome_nodes, CHROME_EXECUTABLE_STATE
            )
        ]
        search_nodes = [
            getattr(n, "id", None)
            for n in self.planner._find_nodes_for_capability(
                "search", chrome_nodes, CHROME_EXECUTABLE_STATE
            )
        ]

        # open se resuelve al nodo ejecutable chrome.open (no a chrome_open,
        # cuyas precondiciones declarativas son contradictorias y no se cumplen).
        assert open_nodes == ["chrome.open"]
        # navigate se resuelve al nodo de conocimiento chrome_navigate.
        assert navigate_nodes == ["chrome_navigate"]
        # search se resuelve a los dos proveedores ejecutables.
        assert set(search_nodes) == {"search_google", "chrome_search"}

    def test_empty_state_excludes_all_providers_via_can_execute(self):
        """Contraste con 3.3.3.3: la planificación aplica ``can_execute`` y, con
        un estado inicial vacío, ninguna capability de Chrome resuelve nodos
        ejecutables (mientras la trazabilidad los documenta aun así)."""
        chrome_nodes = _chrome_nodes(self.planner)
        for capability in CHROME_CAPABILITIES:
            assert (
                self.planner._find_nodes_for_capability(
                    capability, chrome_nodes, {}
                )
                == []
            )

    def test_open_excludes_non_executable_provider_found_by_trace(self):
        """``chrome_open`` es proveedor de 'open' (lo documenta la trazabilidad de
        3.3.3.3), pero no es ejecutable en el estado actual → planificación lo
        descarta, devolviendo exclusivamente ``chrome.open``."""
        all_nodes = self.planner._get_available_nodes()
        result = [
            getattr(n, "id", None)
            for n in self.planner._find_nodes_for_capability(
                "open", all_nodes, CHROME_EXECUTABLE_STATE
            )
        ]
        assert result == ["chrome.open"]
        # Proveedor documentado por la trazabilidad pero no ejecutable: excluido.
        assert "chrome_open" not in result


# ---------------------------------------------------------------------------
# Caso de aplicacion sin capacidades
# ---------------------------------------------------------------------------


def _no_cap_app_nodes(planner: Planner) -> Dict[str, Node]:
    """Nodos cuya aplicación es conocida pero carece de capabilities.

    Equivalente al scoping que ``build_application_aware_plan`` aplica al
    filtrar por aplicación objetivo: solo los nodos cuya
    ``application`` normaliza al nombre de la app objetivo. Para una app
    sin capabilities el único nodo resultante es el nodo APPLICATION
    declarativo (no action/task), que ``_find_nodes_for_capability``
    descarta por tipo.
    """
    nodes = planner._get_available_nodes()
    return {
        nid: node
        for nid, node in nodes.items()
        if str(getattr(node, "application", "")).lower()
        == str(NO_CAP_APP_NAME).lower()
    }


class TestFindNodesForCapabilityNoCapabilities:
    """El camino de planificación ``_find_nodes_for_capability`` debe manejar
    correctamente una aplicación **conocida pero sin capabilities** declaradas.

    Complementario al caso 3.3.4.1 (app con varias capabilities). Para una
    app sin capabilities:

    * ``get_application_capabilities_as_list`` expone ``[]`` (ausente).
    * ``trace_application_capability_to_action`` devuelve ``available: False``
      con lista de capabilities vacía (contrario a 3.3.3.3 donde Chrome sí
      expone capabilities).
    * ``convert_application_to_nodes`` produce **únicamente** el nodo
      APPLICATION declarativo (no action/task), lo que prueba que la app
      *existe* en el modelo aunque no declare capabilities.
    * ``_find_nodes_for_capability`` devuelve ``[]`` para toda capability,
      tanto en estado ejecutable como vacío, porque el único nodo es de tipo
      APPLICATION (excluido por la puerta de tipo ``action/task``) y no
      proporciona ninguna capability.
    """

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_known_app_without_capabilities_exposes_empty_list(self):
        """YouTube (app conocida sin capabilities) expone ``[]`` — distinto de
        Chrome que expone varias. Confirma que la app es conocida pero carece
        de capabilities declaradas."""
        result = self.planner.get_application_capabilities_as_list(NO_CAP_APP)
        assert isinstance(result, list)
        assert result == []
        # La app sí existe en el modelo: get_application no devuelve None.
        manager = getattr(
            self.planner.application_integrator, "application_manager", None
        )
        assert manager is not None
        app = manager.get_application(NO_CAP_APP)
        assert app is not None
        assert getattr(app, "capabilities", None) == []

    def test_known_app_without_capabilities_trace_returns_available_false(self):
        """La trazabilidad (3.3.3.3) devuelve ``available: False`` y capabilities
        vacía para una app conocida sin capabilities — la app existe pero no
        expone capabilities que trazar."""
        result = self.planner.trace_application_capability_to_action(NO_CAP_APP)
        assert result["application"] == NO_CAP_APP
        assert result["available"] is False
        assert result["capabilities"] == []

    def test_known_app_without_capabilities_differs_from_unknown_app(self):
        """La trazabilidad distingue una app conocida sin capabilities de una app
        desconocida: ambas devuelven ``available: False``, pero el campo
        ``application`` refleja el nombre consultado en cada caso."""
        known = self.planner.trace_application_capability_to_action(NO_CAP_APP)
        unknown = self.planner.trace_application_capability_to_action(
            "nonexistent_app_xyz"
        )
        assert known["application"] == NO_CAP_APP
        assert unknown["application"] == "nonexistent_app_xyz"
        assert known["available"] is False
        assert unknown["available"] is False

    def test_convert_app_without_capabilities_creates_only_application_node(self):
        """``convert_application_to_nodes`` para una app conocida sin capabilities
        produce exactamente un nodo de tipo APPLICATION (no action/task),
        demostrando que la app existe en el modelo aunque no declare
        capabilities ni acciones asociadas."""
        nodes = self.planner.application_integrator.convert_application_to_nodes(
            NO_CAP_APP
        )
        assert len(nodes) == 1
        node = nodes[0]
        assert getattr(node, "type", None) == NodeType.APPLICATION
        assert str(getattr(node, "application", "")) == NO_CAP_APP_NAME

    def test_find_nodes_returns_empty_for_all_capabilities(self):
        """``_find_nodes_for_capability`` devuelve ``[]`` para toda capability
        canónica cuando se le pasan los nodos de una app sin capabilities, en un
        estado ejecutable. El nodo APPLICATION es excluido por la puerta de tipo
        ``action/task`` y no proporciona ninguna capability."""
        app_nodes = _no_cap_app_nodes(self.planner)
        assert app_nodes, "La app conocida debe producir al menos su nodo APPLICATION"
        # El único nodo es APPLICATION (no action/task).
        assert all(
            getattr(n, "type", None) == NodeType.APPLICATION for n in app_nodes.values()
        )
        for capability in CANONICAL_CAPABILITIES:
            result = self.planner._find_nodes_for_capability(
                capability, app_nodes, CHROME_EXECUTABLE_STATE
            )
            assert result == []
            assert all(n.type != NodeType.ACTION for n in result)

    def test_find_nodes_returns_empty_with_empty_state(self):
        """Con estado inicial vacío, ``_find_nodes_for_capability`` devuelve ``[]``
        para toda capability de una app sin capabilities (doble filtro: tipo
        APPLICATION + can_execute vacío)."""
        app_nodes = _no_cap_app_nodes(self.planner)
        for capability in CANONICAL_CAPABILITIES:
            assert (
                self.planner._find_nodes_for_capability(capability, app_nodes, {})
                == []
            )

    def test_find_nodes_returns_empty_on_empty_node_set(self):
        """``_find_nodes_for_capability`` devuelve ``[]`` cuando no hay nodos
        disponibles (edge case: app sin capabilities y sin nodes cargados)."""
        for capability in CANONICAL_CAPABILITIES:
            assert (
                self.planner._find_nodes_for_capability(capability, {}, {})
                == []
            )

    def test_node_provides_capability_false_for_application_node(self):
        """``_node_provides_capability`` devuelve ``False`` para el nodo
        APPLICATION de una app sin capabilities, para toda capability canónica:
        el nodo no declara capabilities ni coincide por id/alias/categoría."""
        app_nodes = _no_cap_app_nodes(self.planner)
        app_node = next(iter(app_nodes.values()))
        for capability in CANONICAL_CAPABILITIES:
            assert self.planner._node_provides_capability(app_node, capability) is False


# ---------------------------------------------------------------------------
# Caso de capability desconocida
# ---------------------------------------------------------------------------


class TestFindNodesForCapabilityUnknownCapability:
    """El camino de planificación ``_find_nodes_for_capability`` y las utilidades
    asociadas deben manejar una **capability desconocida** —una capability que no
    es canónica (open/navigate/search), no está en el mapa de aliases de
    ``_node_provides_capability`` y no es declarada por ninguna aplicación ni
    nodo— de forma determinista y segura, devolviendo ausencia de proveedores
    sin falsear disponibilidad.

    Complementario a 3.3.4.1 (app con varias capabilities) y 3.3.4.2 (app
    conocida sin capabilities). Aquí el foco es la **capability** desconocida
    solicitada contra la app más capaz del modelo (Chrome).
    """

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()
        self.chrome_nodes = _chrome_nodes(self.planner)

    def test_unknown_capability_resolves_no_nodes_on_capable_app(self):
        """Una capability desconocida no resuelve ningún nodo, ni siquiera contra
        la app más capaz (Chrome) en un estado que habilita todas sus actions.
        Contrasta con 3.3.4.1 donde 'open'/'navigate'/'search' resuelven nodos."""
        result = self.planner._find_nodes_for_capability(
            UNKNOWN_CAPABILITY, self.chrome_nodes, CHROME_EXECUTABLE_STATE
        )
        assert result == []

    def test_unknown_capability_resolves_no_nodes_with_empty_state(self):
        """Una capability desconocida no resuelve nodos con estado inicial vacío
        tampoco: el doble filtro (tipo action/task + can_execute) y la
        ausencia de matching por capability convergen a ``[]``."""
        result = self.planner._find_nodes_for_capability(
            UNKNOWN_CAPABILITY, self.chrome_nodes, {}
        )
        assert result == []

    def test_unknown_capability_resolves_no_nodes_on_all_nodes(self):
        """Ningún nodo del modelo completo provee una capability desconocida:
        ``_find_nodes_for_capability`` devuelve ``[]`` contra *todos* los nodos
        disponibles en un estado ejecutable."""
        result = self.planner._find_nodes_for_capability(
            UNKNOWN_CAPABILITY,
            self.planner._get_available_nodes(),
            CHROME_EXECUTABLE_STATE,
        )
        assert result == []

    def test_node_provides_capability_false_for_unknown_against_all_chrome_nodes(self):
        """``_node_provides_capability`` devuelve ``False`` para una capability
        desconocida contra TODOS los nodos action/task de Chrome, incluido el
        nodo ejecutable ``chrome.open`` que SÍ provee la capability canónica
        'open'."""
        chrome_action_nodes = {
            nid: n
            for nid, n in self.chrome_nodes.items()
            if self.planner._node_type_value(n) in {"action", "task"}
        }
        assert chrome_action_nodes, "Chrome debe exponer nodos action/task ejecutables"
        for node in chrome_action_nodes.values():
            assert (
                self.planner._node_provides_capability(node, UNKNOWN_CAPABILITY)
                is False
            )
        # Contraste: el mismo nodo chrome.open provee 'open' pero no la
        # capability desconocida.
        open_node = chrome_action_nodes.get("chrome.open")
        if open_node is not None:
            assert self.planner._node_provides_capability(open_node, "open") is True
            assert (
                self.planner._node_provides_capability(open_node, UNKNOWN_CAPABILITY)
                is False
            )

    def test_unknown_capability_not_in_exposed_capabilities(self):
        """``get_application_capabilities_as_list`` solo expone las capabilities
        declaradas por la app; una capability desconocida nunca aparece."""
        caps = self.planner.get_application_capabilities_as_list("chrome")
        assert UNKNOWN_CAPABILITY not in caps
        assert caps == CHROME_CAPABILITIES

    def test_trace_unknown_capability_returns_no_providers(self):
        """Trazando explícitamente una capability desconocida contra Chrome, el
        entry resultante documenta: ``providing_nodes: []``, ``covered: False``,
        ``covering_action: None``, ``implemented_actions: []``.

        Nota semántica verificada: ``available`` es ``True`` porque se trazó una
        capability explícita (la lista ``[capability]`` es no vacía); ``available``
        indica *«se solicitó trazar»*, no *«está cubierta»*. La ausencia de
        proveedores queda reflejada por ``covered: False`` y
        ``providing_nodes: []``.
        """
        result = self.planner.trace_application_capability_to_action(
            "chrome", UNKNOWN_CAPABILITY
        )
        assert result["application"] == "chrome"
        assert result["available"] is True
        caps = result["capabilities"]
        assert len(caps) == 1
        entry = caps[0]
        assert entry["capability"] == UNKNOWN_CAPABILITY
        assert entry["providing_nodes"] == []
        assert entry["covered"] is False
        assert entry["covering_action"] is None
        assert entry["implemented_actions"] == []

    def test_trace_without_capability_never_exposes_unknown(self):
        """Trazando todas las capabilities de Chrome (sin pasar capability),
        ``trace_application_capability_to_action`` solo expone capabilities
        canónicas declaradas, nunca la capability desconocida."""
        result = self.planner.trace_application_capability_to_action("chrome")
        traced = [c["capability"] for c in result["capabilities"]]
        assert UNKNOWN_CAPABILITY not in traced
        assert traced == CHROME_CAPABILITIES

    def test_unknown_capability_contrast_with_known_returns_empty(self):
        """Contraste directo: 'open' (conocida) resuelve nodos ejecutables en
        ``CHROME_EXECUTABLE_STATE``, mientras que la capability desconocida
        'teleportar' devuelve ``[]`` bajo las mismas condiciones."""
        known = self.planner._find_nodes_for_capability(
            "open", self.chrome_nodes, CHROME_EXECUTABLE_STATE
        )
        unknown = self.planner._find_nodes_for_capability(
            UNKNOWN_CAPABILITY, self.chrome_nodes, CHROME_EXECUTABLE_STATE
        )
        assert [getattr(n, "id", None) for n in known] == ["chrome.open"]
        assert unknown == []
