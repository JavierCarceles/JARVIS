# -*- coding: utf-8 -*-
"""Tests de verificación de la hoja 3.3.3.3 — "Verificar trazabilidad
aplicacion -> capability -> accion".

La trazabilidad documenta, para cada capability expuesta por una aplicación,
los nodos de acción que la proporcionan y si la acción efectiva está registrada
en el ``ActionRegistry``.  Se ejerce contra el modelo REAL: el ``ActionRegistry``
global registrado durante la importación de ``src.hands``.

La trazabilidad reutiliza los mecanismos de 3.3.3.1 (``get_application_capabilities_as_list``)
y 3.3.3.2 (``action_exists`` / ``_resolve_node_action_name`` /
``_node_provides_capability``), sin duplicar lógica ni tocar el estado de
planificación (no aplica el filtro ``can_execute`` de `_find_nodes_for_capability`).
"""

import json
import logging
from unittest.mock import patch

# ---------------------------------------------------------------------------
# SUPRESIÓN DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.planner.planner import Planner  # noqa: E402

# ---------------------------------------------------------------------------
# Capacidades verificables contra el modelo real
# ---------------------------------------------------------------------------
CHROME_CAPABILITIES = ["open", "navigate", "search"]
# Acción registrada que respalda la capability "open" de Chrome (nodo de
# compatibilidad chrome.open tiene action_category == "open_application").
OPEN_REGISTERED_ACTION = "open_application"
# Nodo de conocimiento de aplicación cuyo id no es una acción registrada.
CHROME_OPEN_KNOWN_NODE_ID = "chrome_open"
CHROME_OPEN_COMPAT_NODE_ID = "chrome.open"


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    logging.disable(logging.CRITICAL)
    yield


def _planner() -> Planner:
    return Planner()


# ---------------------------------------------------------------------------
# Estructura de la trazabilidad
# ---------------------------------------------------------------------------


class TestTraceStructure:
    """``trace_application_capability_to_action`` produce una estructura
    establecida y serializable."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_top_level_keys(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        assert set(result.keys()) == {"application", "available", "capabilities"}

    def test_application_echoed(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        assert result["application"] == "chrome"

    def test_available_true_for_known_app(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        assert result["available"] is True

    def test_capability_entry_shape(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        for entry in result["capabilities"]:
            assert set(entry.keys()) == {
                "capability",
                "providing_nodes",
                "implemented_actions",
                "covered",
                "covering_action",
            }
            assert isinstance(entry["providing_nodes"], list)
            assert isinstance(entry["implemented_actions"], list)
            assert isinstance(entry["covered"], bool)

    def test_providing_node_shape(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        for entry in result["capabilities"]:
            for node in entry["providing_nodes"]:
                assert set(node.keys()) == {
                    "node_id",
                    "action_name",
                    "action_exists",
                    "action_category",
                    "category_action_exists",
                    "source",
                }

    def test_result_is_json_serializable(self):
        """La trazabilidad no debe contener objetos ``Node`` ni estructuras no
        serializables, ya que puede persistirse como JSON."""
        result = self.planner.trace_application_capability_to_action("chrome")
        # No debe lanzar TypeError por sets o Node.
        json.dumps(result)


# ---------------------------------------------------------------------------
# Trazabilidad aplicacion -> capability -> accion (Chrome)
# ---------------------------------------------------------------------------


class TestTraceChromeCapabilities:
    """La cadena aplicacion -> capability -> accion se verifica realmente
    contra el ActionRegistry global."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_chrome_capabilities_in_canonical_order(self):
        result = self.planner.trace_application_capability_to_action("chrome")
        assert [c["capability"] for c in result["capabilities"]] == CHROME_CAPABILITIES

    def test_open_capability_is_covered_by_registered_action(self):
        """La capability 'open' de Chrome está cubierta por la acción registrada
        'open_application' (nodo chrome.open, action_category registrada)."""
        entry = self._entry("open")
        assert entry["covered"] is True
        assert OPEN_REGISTERED_ACTION in entry["implemented_actions"]
        assert entry["covering_action"] == OPEN_REGISTERED_ACTION

    def test_open_providing_nodes_are_chrome_only(self):
        """No hay fuga entre aplicaciones: spotify_open no aparece al trazar
        la capability 'open' de Chrome."""
        entry = self._entry("open")
        node_ids = {n["node_id"] for n in entry["providing_nodes"]}
        assert node_ids == {CHROME_OPEN_COMPAT_NODE_ID, CHROME_OPEN_KNOWN_NODE_ID}

    def test_open_compat_node_category_is_registered(self):
        """chrome.open: action_category 'open_application' está registrada, el
        propio id 'chrome.open' no (verificado read-only contra el registry)."""
        entry = self._entry("open")
        compat = next(
            n for n in entry["providing_nodes"] if n["node_id"] == CHROME_OPEN_COMPAT_NODE_ID
        )
        assert compat["action_category"] == OPEN_REGISTERED_ACTION
        assert compat["category_action_exists"] is True
        # El id del nodo con '.' no es el nombre de una acción registrada.
        assert self.planner.action_exists(compat["action_name"]) is False
        assert compat["action_exists"] is False

    def test_open_known_node_not_registered(self):
        """chrome_open: el id no es una acción registrada; su categoría
        'application_capability' tampoco lo es."""
        entry = self._entry("open")
        known = next(
            n for n in entry["providing_nodes"] if n["node_id"] == CHROME_OPEN_KNOWN_NODE_ID
        )
        assert known["action_name"] == CHROME_OPEN_KNOWN_NODE_ID
        assert known["action_exists"] is False
        assert known["action_category"] == "application_capability"
        assert known["category_action_exists"] is False
        assert known["source"] == "application_knowledge"

    def test_navigate_capability_not_backed_by_registered_action(self):
        """Hecho real verificable: la capability 'navigate' de Chrome sólo está
        provista por el nodo declarativo chrome_navigate cuya categoría
        'application_capability' no está registrada → no cubierta."""
        entry = self._entry("navigate")
        assert entry["covered"] is False
        assert entry["implemented_actions"] == []
        assert entry["covering_action"] is None
        assert [n["node_id"] for n in entry["providing_nodes"]] == ["chrome_navigate"]

    def test_search_capability_not_backed_by_registered_action(self):
        """Hecho real verificable: 'search' está provista por search_google
        (categoría 'search', no registrada) y chrome_search → no cubierta."""
        entry = self._entry("search")
        assert entry["covered"] is False
        assert entry["implemented_actions"] == []
        assert entry["covering_action"] is None
        node_ids = {n["node_id"] for n in entry["providing_nodes"]}
        assert node_ids == {"search_google", "chrome_search"}

    def _entry(self, capability: str) -> dict:
        result = self.planner.trace_application_capability_to_action("chrome")
        return next(c for c in result["capabilities"] if c["capability"] == capability)


# ---------------------------------------------------------------------------
# Trazabilidad de una capability concreta
# ---------------------------------------------------------------------------


class TestTraceSingleCapability:
    """El parámetro ``capability`` restringe la trazabilidad a una sola
    capability sin alterar el resto de la estructura."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_single_capability_returns_only_that_one(self):
        result = self.planner.trace_application_capability_to_action("chrome", "open")
        assert [c["capability"] for c in result["capabilities"]] == ["open"]

    def test_single_capability_consistent_with_full(self):
        full = self.planner.trace_application_capability_to_action("chrome")
        single = self.planner.trace_application_capability_to_action("chrome", "open")
        assert single["capabilities"][0] == next(
            c for c in full["capabilities"] if c["capability"] == "open"
        )

    def test_unknown_capability_yields_empty_providers(self):
        result = self.planner.trace_application_capability_to_action(
            "chrome", "nonexistent_cap"
        )
        assert result["available"] is True
        assert len(result["capabilities"]) == 1
        entry = result["capabilities"][0]
        assert entry["capability"] == "nonexistent_cap"
        assert entry["providing_nodes"] == []
        assert entry["implemented_actions"] == []
        assert entry["covered"] is False
        assert entry["covering_action"] is None


# ---------------------------------------------------------------------------
# Aplicación ausente
# ---------------------------------------------------------------------------


class TestTraceNonexistentApplication:
    """Una aplicación desconocida no expone capabilities."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_unknown_app_available_false(self):
        result = self.planner.trace_application_capability_to_action("nonexistent_app")
        assert result["application"] == "nonexistent_app"
        assert result["available"] is False
        assert result["capabilities"] == []

    def test_empty_app_name_available_false(self):
        result = self.planner.trace_application_capability_to_action("")
        assert result["available"] is False
        assert result["capabilities"] == []


# ---------------------------------------------------------------------------
# Reutilización del ActionRegistry (3.3.3.2)
# ---------------------------------------------------------------------------


class TestTraceReusesActionRegistry:
    """La trazabilidad depende directamente de ``action_exists`` (3.3.3.2):
    los nodos cuya acción/categoría está registrada se marcan como existentes
    y aparecen en ``implemented_actions``."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_registered_action_reflected_in_trace(self):
        """'open_application' está registrada → la capability 'open' se marca
        cubierta y la acción aparece en implemented_actions."""
        assert self.planner.action_exists(OPEN_REGISTERED_ACTION) is True
        entry = self._entry("open")
        assert OPEN_REGISTERED_ACTION in entry["implemented_actions"]
        assert entry["covered"] is True

    def test_nonexistent_action_reflected_in_trace(self):
        """'chrome_open' no está registrada → action_exists False y no aparece
        en implemented_actions (solo como nodo proveedor no registrado)."""
        assert self.planner.action_exists(CHROME_OPEN_KNOWN_NODE_ID) is False
        entry = self._entry("open")
        known = next(
            n for n in entry["providing_nodes"] if n["node_id"] == CHROME_OPEN_KNOWN_NODE_ID
        )
        assert known["action_exists"] is False
        assert CHROME_OPEN_KNOWN_NODE_ID not in entry["implemented_actions"]

    def test_action_exists_called_for_resolution(self):
        """Se comprueba que la trazabilidad delega en action_exists (no en un
        lookup paralelo del registry): forzando action_exists a devolver True
        para un nodo no registrado, ese nodo pasa a implemented_actions."""
        with patch.object(self.planner, "action_exists", return_value=True) as mocked:
            result = self.planner.trace_application_capability_to_action("chrome", "open")
        assert mocked.called
        entry = result["capabilities"][0]
        # Con action_exists forzada a True, la categoría 'open_application' y el
        # id 'chrome.open' aparecen como acciones implementadas.
        assert OPEN_REGISTERED_ACTION in entry["implemented_actions"]
        assert "chrome.open" in entry["implemented_actions"]
        assert entry["covered"] is True

    def _entry(self, capability: str) -> dict:
        result = self.planner.trace_application_capability_to_action("chrome")
        return next(c for c in result["capabilities"] if c["capability"] == capability)


# ---------------------------------------------------------------------------
# Idempotencia y no mutación
# ---------------------------------------------------------------------------


class TestTraceIdempotentAndPure:
    """La trazabilidad es un método de solo-lectura: no muta el modelo de
    nodos y produce resultados idénticos entre invocaciones."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_two_calls_produce_equal_results(self):
        first = self.planner.trace_application_capability_to_action("chrome")
        second = self.planner.trace_application_capability_to_action("chrome")
        assert first == second

    def test_does_not_mutate_available_nodes(self):
        self.planner._get_available_nodes()  # calienta la caché de nodos
        before = set(self.planner.available_nodes.keys())
        self.planner.trace_application_capability_to_action("chrome")
        after = set(self.planner.available_nodes.keys())
        assert before == after
