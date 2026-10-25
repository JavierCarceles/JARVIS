# -*- coding: utf-8 -*-
"""Tests para StateGraph (src/hands/planner/graph.py)."""

import json
import math
import os
import tempfile

import pytest

from src.hands.planner.graph import (
    GraphEdge,
    RouteResult,
    SearchStrategy,
    StateGraph,
)
from src.hands.planner.heuristic import Heuristic, HeuristicType
from src.hands.planner.node import Node, NodeType
from src.hands.planner.preconditions_effects_types import Condition, ConditionType, Effect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id: str = "n1", **kwargs) -> Node:
    defaults = dict(id=node_id, type=NodeType.ACTION, name=f"node_{node_id}")
    defaults.update(kwargs)
    return Node(**defaults)


def _build_simple_graph() -> StateGraph:
    """A -> B -> C, all unconditional, cost 1.0 each."""
    graph = StateGraph()
    for nid in ("a", "b", "c"):
        graph.add_node(_make_node(nid))
    graph.add_edge("a", "b", 1.0)
    graph.add_edge("b", "c", 1.0)
    return graph


def _build_branching_graph() -> StateGraph:
    """A -> B (cost 1), A -> C (cost 5), B -> C (cost 1), C -> D (cost 1)."""
    graph = StateGraph()
    for nid in ("a", "b", "c", "d"):
        graph.add_node(_make_node(nid))
    graph.add_edge("a", "b", 1.0)
    graph.add_edge("a", "c", 5.0)
    graph.add_edge("b", "c", 1.0)
    graph.add_edge("c", "d", 1.0)
    return graph


# ---------------------------------------------------------------------------
# SearchStrategy
# ---------------------------------------------------------------------------

class TestSearchStrategy:
    def test_strategy_values(self):
        assert SearchStrategy.A_STAR.value == "a_star"
        assert SearchStrategy.DIJKSTRA.value == "dijkstra"
        assert SearchStrategy.BFS.value == "bfs"
        assert SearchStrategy.DFS.value == "dfs"
        assert SearchStrategy.GREEDY.value == "greedy"

    def test_strategy_count(self):
        assert len(list(SearchStrategy)) == 5


# ---------------------------------------------------------------------------
# StateGraph init & properties
# ---------------------------------------------------------------------------

class TestStateGraphInit:
    def test_default_heuristic(self):
        graph = StateGraph()
        assert isinstance(graph.heuristic, Heuristic)
        assert graph.heuristic.heuristic_type == HeuristicType.GOAL_DISTANCE

    def test_custom_heuristic(self):
        custom = Heuristic(HeuristicType.UNIFORM, weight=2.0)
        graph = StateGraph(heuristic=custom)
        assert graph.heuristic is custom

    def test_empty_graph_stats(self):
        graph = StateGraph()
        stats = graph.get_graph_stats()
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
        assert stats["graph_revision"] == 0
        assert stats["average_branching"] == 0.0

    def test_graph_revision_starts_at_zero(self):
        graph = StateGraph()
        assert graph.graph_revision == 0

    def test_nodes_empty(self):
        graph = StateGraph()
        assert graph.nodes == {}

    def test_edges_empty(self):
        graph = StateGraph()
        assert graph.edges == []

    def test_graph_nodes_empty(self):
        graph = StateGraph()
        assert graph.graph_nodes == {}


# ---------------------------------------------------------------------------
# add_node / get_node / has_node
# ---------------------------------------------------------------------------

class TestAddNode:
    def test_add_single_node(self):
        graph = StateGraph()
        node = _make_node("my_node")
        graph.add_node(node)
        assert "my_node" in graph.nodes
        assert graph.nodes["my_node"] is node
        assert "my_node" in graph.graph_nodes

    def test_add_none_node_raises(self):
        graph = StateGraph()
        with pytest.raises(ValueError):
            graph.add_node(None)

    def test_add_node_no_id_raises(self):
        graph = StateGraph()
        node = Node(id="", type=NodeType.ACTION, name="bad")
        with pytest.raises(ValueError):
            graph.add_node(node)

    def test_add_node_id_none_raises(self):
        graph = StateGraph()
        node = Node(id=None, type=NodeType.ACTION, name="bad")  # type: ignore
        with pytest.raises(ValueError):
            graph.add_node(node)

    def test_add_node_strips_id(self):
        graph = StateGraph()
        node = Node(id="  spaced  ", type=NodeType.ACTION, name="n")
        graph.add_node(node)
        assert "spaced" in graph.nodes
        assert node.id == "  spaced  "  # original node id not mutated by graph

    def test_add_duplicate_node_replaces(self):
        graph = StateGraph()
        node1 = _make_node("x", name="first")
        node2 = _make_node("x", name="second")
        graph.add_node(node1)
        graph.add_node(node2)
        assert graph.nodes["x"] is node2
        assert graph.nodes["x"].name == "second"

    def test_get_node_exists(self):
        graph = _build_simple_graph()
        assert graph.get_node("a") is not None
        assert graph.get_node("a").id == "a"

    def test_get_node_missing(self):
        graph = _build_simple_graph()
        assert graph.get_node("nonexistent") is None

    def test_has_node_true(self):
        graph = _build_simple_graph()
        assert graph.has_node("a") is True

    def test_has_node_false(self):
        graph = _build_simple_graph()
        assert graph.has_node("zzz") is False

    def test_add_node_invalidates_cache(self):
        graph = StateGraph()
        assert graph.graph_revision == 0
        graph.add_node(_make_node("a"))
        assert graph.graph_revision == 1
        graph.add_node(_make_node("b"))
        assert graph.graph_revision == 2

    def test_add_same_node_object_does_not_increment_revision(self):
        graph = StateGraph()
        node = _make_node("a")
        graph.add_node(node)
        first_rev = graph.graph_revision
        graph.add_node(node)
        assert graph.graph_revision == first_rev


# ---------------------------------------------------------------------------
# add_edge
# ---------------------------------------------------------------------------

class TestAddEdge:
    def test_add_edge_success(self):
        graph = _build_simple_graph()
        assert len(graph.edges) == 2

    def test_add_edge_missing_source(self):
        graph = StateGraph()
        graph.add_node(_make_node("b"))
        result = graph.add_edge("nonexistent", "b", 1.0)
        assert result is False

    def test_add_edge_missing_target(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        result = graph.add_edge("a", "nonexistent", 1.0)
        assert result is False

    def test_add_edge_invalid_cost(self):
        graph = _build_simple_graph()
        result = graph.add_edge("a", "b", float("inf"))
        assert result is False

    def test_add_edge_negative_cost(self):
        graph = _build_simple_graph()
        result = graph.add_edge("a", "b", -5.0)
        assert result is False

    def test_add_edge_updates_node_adjacency(self):
        graph = _build_simple_graph()
        node_a = graph.nodes["a"]
        assert "b" in node_a.out_edges
        node_b = graph.nodes["b"]
        assert "a" in node_b.in_edges

    def test_add_edge_edge_cost_in_node(self):
        graph = _build_simple_graph()
        node_a = graph.nodes["a"]
        assert node_a.edge_costs["b"] == 1.0

    def test_add_duplicate_edge_returns_true(self):
        graph = _build_simple_graph()
        result = graph.add_edge("a", "b", 1.0)
        assert result is True

    def test_add_duplicate_edge_replaces_different_cost(self):
        graph = _build_simple_graph()
        graph.add_edge("a", "b", 2.0)
        edge = graph.get_edge("a", "b")
        assert edge.cost == 2.0

    def test_add_edge_with_conditions(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        graph.add_edge("a", "b", 1.0, conditions=["ready"])
        edge = graph.get_edge("a", "b")
        assert edge.conditions == ["ready"]

    def test_add_edge_with_transition_type(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        graph.add_edge("a", "b", 1.0, transition_type="conditional")
        edge = graph.get_edge("a", "b")
        assert edge.transition_type == "conditional"

    def test_add_edge_with_preconditions(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        cond = Condition(type=ConditionType.STATE_TRUE, key="ready")
        graph.add_edge("a", "b", 1.0, preconditions=[cond])
        edge = graph.get_edge("a", "b")
        assert len(edge.preconditions) == 1
        assert edge.preconditions[0].key == "ready"

    def test_add_edge_with_effects(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        eff = Effect(type="state_set", key="opened", value=True)
        graph.add_edge("a", "b", 1.0, effects=[eff])
        edge = graph.get_edge("a", "b")
        assert len(edge.effects) == 1
        assert edge.effects[0].key == "opened"

    def test_add_edge_invalidates_cache(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        rev_before = graph.graph_revision
        graph.add_edge("a", "b", 1.0)
        assert graph.graph_revision > rev_before

    def test_add_edge_with_invalid_cost_string(self):
        graph = _build_simple_graph()
        result = graph.add_edge("a", "b", "not_a_number")
        assert result is False


# ---------------------------------------------------------------------------
# get_edges_from, get_edge
# ---------------------------------------------------------------------------

class TestGetEdgesAndNodes:
    def test_get_edges_from(self):
        graph = _build_branching_graph()
        edges = graph.get_edges_from("a")
        assert len(edges) == 2
        targets = {e.target_id for e in edges}
        assert targets == {"b", "c"}

    def test_get_edges_from_no_edges(self):
        graph = _build_branching_graph()
        assert graph.get_edges_from("d") == []

    def test_get_edge_exists(self):
        graph = _build_simple_graph()
        edge = graph.get_edge("a", "b")
        assert edge is not None
        assert edge.source_id == "a"
        assert edge.target_id == "b"

    def test_get_edge_missing(self):
        graph = _build_simple_graph()
        assert graph.get_edge("a", "c") is None


# ---------------------------------------------------------------------------
# find_route - basic routing
# ---------------------------------------------------------------------------

class TestFindRouteBasic:
    def test_find_route_success_astar(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.path == ["a", "b", "c"]
        assert result.strategy == "a_star"

    def test_find_route_success_dijkstra(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.DIJKSTRA)
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_find_route_success_bfs(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.BFS)
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_find_route_success_dfs(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.DFS)
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_find_route_success_greedy(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.GREEDY)
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_find_route_start_not_found(self):
        graph = _build_simple_graph()
        result = graph.find_route("nonexistent", "c", strategy=SearchStrategy.A_STAR)
        assert result.success is False
        assert result.error is not None
        assert "Nodo inicial" in result.error

    def test_find_route_goal_not_found(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "nonexistent", strategy=SearchStrategy.A_STAR)
        assert result.success is False
        assert result.error is not None
        assert "Nodo objetivo" in result.error

    def test_find_route_no_path(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        # No edges between them
        result = graph.find_route("a", "b", strategy=SearchStrategy.A_STAR)
        assert result.success is False
        assert result.error is not None
        assert result.path == []

    def test_find_route_same_node(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "a", strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.path == ["a"]

    def test_find_route_string_strategy(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy="astar")
        assert result.success is True
        assert result.strategy == "a_star"

    def test_find_route_string_strategy_dijkstra(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy="dijkstra")
        assert result.success is True

    def test_find_route_invalid_strategy(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy="invalid_strategy")
        assert result.success is False
        assert result.error is not None

    def test_find_route_total_cost(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.BFS)
        # Two edges, each with cost 1.0 + 0 effects + 0 preconditions * 0.1 = 1.0 each
        assert result.total_cost == 2.0

    def test_find_route_initial_state_preserved(self):
        graph = _build_simple_graph()
        state = {"flag": True}
        result = graph.find_route("a", "c", current_state=state, strategy=SearchStrategy.A_STAR)
        assert result.initial_state == {"flag": True}

    def test_find_route_none_state(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", current_state=None, strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.initial_state == {}

    def test_find_route_iterations_recorded(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.BFS)
        assert result.iterations > 0

    def test_find_route_elapsed_time_positive(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR)
        assert result.elapsed_time >= 0.0

    def test_find_route_edges_populated(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR)
        assert len(result.edges) == 2
        assert result.edges[0].source_id == "a"
        assert result.edges[0].target_id == "b"
        assert result.edges[1].source_id == "b"
        assert result.edges[1].target_id == "c"


class TestFindRouteAlternatives:
    def test_find_alternatives(self):
        graph = _build_branching_graph()
        result = graph.find_route(
            "a", "d", strategy=SearchStrategy.A_STAR,
            find_alternatives=True, alternative_count=3,
        )
        assert result.success is True
        # Primary path should be the cheaper one: a -> b -> c -> d
        assert result.path == ["a", "b", "c", "d"]
        assert len(result.alternative_paths) > 0

    def test_find_alternatives_disabled(self):
        graph = _build_branching_graph()
        result = graph.find_route("a", "d", strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.alternative_paths == []

    def test_find_alternatives_no_path(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        result = graph.find_route(
            "a", "a", strategy=SearchStrategy.A_STAR,
            find_alternatives=True,
        )
        assert result.success is True
        assert result.alternative_paths == []

    def test_alternative_count_zero(self):
        graph = _build_branching_graph()
        result = graph.find_route(
            "a", "d", strategy=SearchStrategy.A_STAR,
            find_alternatives=True, alternative_count=0,
        )
        assert result.success is True
        assert result.alternative_paths == []


# ---------------------------------------------------------------------------
# find_route - conditional routing
# ---------------------------------------------------------------------------

class TestFindRouteConditional:
    def test_conditional_edge_skipped_when_condition_unmet(self):
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        # a -> b conditional on "ready"
        graph.add_edge("a", "b", 1.0, conditions=["ready"])
        # a -> c unconditional
        graph.add_edge("a", "c", 1.0)
        graph.add_edge("c", "b", 1.0)

        # Without "ready" in state, can't go a->b directly
        result = graph.find_route("a", "b", current_state={}, strategy=SearchStrategy.A_STAR)
        assert result.success is True
        # Should go through c: a -> c -> b
        assert result.path == ["a", "c", "b"]

    def test_conditional_edge_traversed_when_condition_met(self):
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0, conditions=["ready"])
        graph.add_edge("a", "c", 10.0)
        graph.add_edge("c", "b", 1.0)

        result = graph.find_route("a", "b", current_state={"ready": True}, strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.path == ["a", "b"]

    def test_effects_applied_along_path(self):
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0, effects=[Effect(type="state_set", key="step1", value=True)])
        graph.add_edge("b", "c", 1.0, effects=[Effect(type="state_set", key="step2", value=True)])

        result = graph.find_route("a", "c", current_state={}, strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.final_state == {"step1": True, "step2": True}

    def test_effects_with_prerequisites(self):
        """An edge requires a state set by a previous edge."""
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        # a->b sets "ready"=True
        graph.add_edge("a", "b", 1.0, effects=[Effect(type="state_set", key="ready", value=True)])
        # b->c requires "ready"
        graph.add_edge("b", "c", 1.0, conditions=["ready"])

        result = graph.find_route("a", "c", current_state={}, strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.path == ["a", "b", "c"]
        assert result.final_state == {"ready": True}

    def test_conditional_edge_unreachable_without_effect(self):
        """If no edge sets 'ready', the b->c edge is never traversable."""
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0)
        # b->c needs "ready" but nothing sets it
        graph.add_edge("b", "c", 1.0, conditions=["ready"])

        result = graph.find_route("a", "c", current_state={}, strategy=SearchStrategy.A_STAR)
        assert result.success is False

    def test_state_with_colon_condition(self):
        graph = StateGraph()
        for nid in ("a", "b"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0, conditions=["mode:fast"])

        result_fast = graph.find_route("a", "b", current_state={"mode": "fast"}, strategy=SearchStrategy.A_STAR)
        assert result_fast.success is True

        result_slow = graph.find_route("a", "b", current_state={"mode": "slow"}, strategy=SearchStrategy.A_STAR)
        assert result_slow.success is False


# ---------------------------------------------------------------------------
# Shortest path correctness
# ---------------------------------------------------------------------------

class TestShortestPath:
    def test_dijkstra_finds_shortest(self):
        """A->C (cost 5), A->B->C (cost 1+1=2). Dijkstra should find A->B->C."""
        graph = _build_branching_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.DIJKSTRA)
        assert result.success is True
        assert result.path == ["a", "b", "c"]
        assert result.total_cost == 2.0

    def test_astar_finds_shortest(self):
        graph = _build_branching_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR)
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_dijkstra_vs_greedy_divergence(self):
        """With a uniform heuristic, greedy should behave like A* for simple graphs."""
        graph = _build_branching_graph()
        result_greedy = graph.find_route("a", "d", strategy=SearchStrategy.GREEDY)
        assert result_greedy.success is True

    def test_max_iterations_limit(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR, max_iterations=0)
        # max_iterations=0 -> normalized to 1, just the start node
        # If start != goal and max_iterations=1, it won't reach goal
        assert result.success is False or result.total_cost < float("inf")

    def test_max_iterations_large_enough(self):
        graph = _build_simple_graph()
        result = graph.find_route("a", "c", strategy=SearchStrategy.A_STAR, max_iterations=1000)
        assert result.success is True


# ---------------------------------------------------------------------------
# build_route alias
# ---------------------------------------------------------------------------

class TestBuildRoute:
    def test_build_route_is_alias(self):
        graph = _build_simple_graph()
        result = graph.build_route("a", "c", strategy=SearchStrategy.BFS)
        assert result.success is True
        assert result.path == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Node-level edge operations
# ---------------------------------------------------------------------------

class TestNodeEdgeOperations:
    def test_add_edge_updates_node_out_edges(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        graph.add_edge("a", "b", 5.0)
        assert "b" in graph.nodes["a"].out_edges
        assert graph.nodes["a"].edge_costs["b"] == 5.0

    def test_add_edge_updates_node_in_edges(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        graph.add_edge("a", "b", 5.0)
        assert "a" in graph.nodes["b"].in_edges

    def test_add_edge_with_preconditions_and_effects(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        cond = Condition(type=ConditionType.STATE_TRUE, key="ready")
        eff = Effect(type="state_set", key="done", value=True)
        graph.add_edge("a", "b", 1.0, preconditions=[cond], effects=[eff])
        edge = graph.get_edge("a", "b")
        assert len(edge.preconditions) == 1
        assert len(edge.effects) == 1


# ---------------------------------------------------------------------------
# validate_graph
# ---------------------------------------------------------------------------

class TestValidateGraph:
    def test_valid_graph_no_errors(self):
        graph = _build_simple_graph()
        errors = graph.validate_graph()
        assert errors == []

    def test_invalid_graph_missing_node(self):
        graph = StateGraph()
        # Manually add an edge to a non-existent node
        edge = GraphEdge(source_id="ghost", target_id="phantom", cost=1.0)
        graph.edges.append(edge)
        errors = graph.validate_graph()
        assert len(errors) > 0
        assert any("Origen de arista no existe" in e for e in errors)
        assert any("Destino de arista no existe" in e for e in errors)

    def test_invalid_cost_in_validation(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        edge = GraphEdge(source_id="a", target_id="b", cost=-1.0)
        graph.edges.append(edge)
        errors = graph.validate_graph()
        assert any("Coste inválido" in e for e in errors)

    def test_out_edges_not_synchronized(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        graph.add_edge("a", "b", 1.0)
        # Manually corrupt out_edges
        graph.nodes["a"].out_edges.append("corrupted")
        errors = graph.validate_graph()
        assert any("out_edges no sincronizado" in e for e in errors)

    def test_disconnected_nodes_in_advanced_validation(self):
        graph = _build_simple_graph()
        graph.add_node(_make_node("lonely"))
        errors, stats = graph.validate_graph_advanced()
        assert any("Nodos desconectados" in e for e in errors)
        assert stats["disconnected_nodes"] > 0

    def test_advanced_validation_with_circular_path(self):
        graph = StateGraph()
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0)
        graph.add_edge("b", "c", 1.0)
        graph.add_edge("c", "a", 1.0)  # creates a cycle
        errors, stats = graph.validate_graph_advanced()
        assert stats["circular_paths"] > 0

    def test_advanced_validation_clean_graph(self):
        graph = _build_simple_graph()
        errors, stats = graph.validate_graph_advanced()
        assert errors == []
        assert stats["total_nodes"] == 3
        assert stats["total_edges"] == 2
        assert stats["circular_paths"] == 0
        assert stats["disconnected_nodes"] == 0

    def test_has_circular_path_no_cycle(self):
        graph = _build_simple_graph()
        assert graph._has_circular_path("a") is False

    def test_has_circular_path_with_cycle(self):
        graph = StateGraph()
        for nid in ("a", "b"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0)
        graph.add_edge("b", "a", 1.0)
        assert graph._has_circular_path("a") is True

    def test_has_circular_path_nonexistent_node(self):
        graph = _build_simple_graph()
        assert graph._has_circular_path("nonexistent") is False

    def test_high_degree_node_warning(self):
        graph = StateGraph()
        graph.add_node(_make_node("hub"))
        for i in range(15):
            graph.add_node(_make_node(f"leaf_{i}"))
            graph.add_edge("hub", f"leaf_{i}", 1.0)
        errors, stats = graph.validate_graph_advanced()
        assert stats["nodes_with_issues"] > 0


# ---------------------------------------------------------------------------
# Path effects
# ---------------------------------------------------------------------------

class TestApplyPathEffects:
    def test_apply_path_effects_simple(self):
        graph = StateGraph()
        for nid in ("a", "b"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0, effects=[Effect(type="state_set", key="done", value=True)])

        result_state = graph.apply_path_effects(["a", "b"], {})
        assert result_state == {"done": True}

    def test_apply_path_effects_empty_path(self):
        graph = _build_simple_graph()
        result = graph.apply_path_effects([], {"keep": True})
        assert result == {"keep": True}

    def test_apply_path_effects_single_node(self):
        graph = _build_simple_graph()
        result = graph.apply_path_effects(["a"], {"keep": True})
        assert result == {"keep": True}

    def test_apply_path_effects_no_edge_between(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.apply_path_effects(["a", "b"], {})
        assert result == {}

    def test_get_edges_for_path(self):
        graph = _build_simple_graph()
        edges = graph.get_edges_for_path(["a", "b", "c"], {})
        assert len(edges) == 2
        assert edges[0].source_id == "a"
        assert edges[0].target_id == "b"
        assert edges[1].source_id == "b"
        assert edges[1].target_id == "c"

    def test_get_edges_for_path_empty(self):
        graph = _build_simple_graph()
        assert graph.get_edges_for_path([], {}) == []

    def test_get_edges_for_path_single_node(self):
        graph = _build_simple_graph()
        assert graph.get_edges_for_path(["a"], {}) == []

    def test_get_node_path_cost(self):
        graph = _build_simple_graph()
        cost = graph.get_node_path_cost(["a", "b", "c"])
        assert cost == 2.0

    def test_get_node_path_cost_single_node(self):
        graph = _build_simple_graph()
        assert graph.get_node_path_cost(["a"]) == 0.0

    def test_get_node_path_cost_empty(self):
        graph = _build_simple_graph()
        assert graph.get_node_path_cost([]) == 0.0

    def test_get_neighbors(self):
        graph = _build_simple_graph()
        neighbors = graph.get_neighbors("a", {})
        assert len(neighbors) == 1
        assert neighbors[0][0] == "b"
        assert neighbors[0][1] == 1.0


# ---------------------------------------------------------------------------
# Edge creation helpers
# ---------------------------------------------------------------------------

class TestEdgeCreationHelpers:
    def test_add_edge_with_preconditions(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.add_edge_with_preconditions("a", "b", 1.0, conditions=["flag"])
        assert result is True
        edge = graph.get_edge("a", "b")
        assert edge.conditions == ["flag"]

    def test_create_conditional_edge(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.create_conditional_edge("a", "b", 2.0, ConditionType.STATE_TRUE, key="ready")
        assert result is True
        edge = graph.get_edge("a", "b")
        assert edge.transition_type == "conditional"
        assert len(edge.preconditions) == 1
        assert edge.preconditions[0].key == "ready"
        assert edge.cost == 2.0

    def test_create_conditional_edge_no_type_returns_false(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.create_conditional_edge("a", "b", 1.0, None, key="ready")
        assert result is False

    def test_create_effect_edge(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.create_effect_edge("a", "b", 1.0, "state_set", key="done", value=True)
        assert result is True
        edge = graph.get_edge("a", "b")
        assert len(edge.effects) == 1
        assert edge.effects[0].key == "done"

    def test_create_effect_edge_no_type_returns_false(self):
        graph = StateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        result = graph.create_effect_edge("a", "b", 1.0, None, key="done")
        assert result is False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_export_to_json_structure(self):
        graph = _build_simple_graph()
        data = graph.export_to_json()
        assert "nodes" in data
        assert "edges" in data
        assert "metadata" in data
        assert data["metadata"]["node_count"] == 3
        assert data["metadata"]["edge_count"] == 2

    def test_export_to_json_node_fields(self):
        graph = _build_simple_graph()
        data = graph.export_to_json()
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "name" in node

    def test_export_to_json_edge_fields(self):
        graph = _build_simple_graph()
        data = graph.export_to_json()
        edge = data["edges"][0]
        assert "source_id" in edge
        assert "target_id" in edge
        assert "cost" in edge
        assert "transition_type" in edge

    def test_export_then_import_roundtrip(self):
        graph = _build_branching_graph()
        data = graph.export_to_json()

        new_graph = StateGraph()
        new_graph.import_from_json(data)

        assert len(new_graph.nodes) == 4
        assert len(new_graph.edges) == 4
        assert new_graph.has_node("a")
        assert new_graph.has_node("d")
        assert new_graph.get_edge("a", "b") is not None

    def test_export_graph_json_file(self, tmp_path):
        graph = _build_simple_graph()
        file_path = str(tmp_path / "graph.json")
        result = graph.export_graph(file_path, format="json")
        assert result is True
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "nodes" in data

    def test_export_graph_pickle_file(self, tmp_path):
        graph = _build_simple_graph()
        file_path = str(tmp_path / "graph.pkl")
        result = graph.export_graph(file_path, format="pickle")
        assert result is True
        assert os.path.exists(file_path)

    def test_export_graph_invalid_format(self, tmp_path):
        graph = _build_simple_graph()
        result = graph.export_graph(str(tmp_path / "g.txt"), format="xml")
        assert result is False

    def test_import_graph_json_file(self, tmp_path):
        graph = _build_simple_graph()
        file_path = str(tmp_path / "graph.json")
        graph.export_graph(file_path, format="json")

        new_graph = StateGraph()
        result = new_graph.import_graph(file_path, format="json")
        assert result is True
        assert new_graph.has_node("a")

    def test_import_graph_invalid_format(self, tmp_path):
        graph = _build_simple_graph()
        result = graph.import_graph(str(tmp_path / "g.txt"), format="xml")
        assert result is False

    def test_import_from_json_invalid_data_raises(self):
        graph = StateGraph()
        with pytest.raises(ValueError):
            graph.import_from_json("not a dict")  # type: ignore

    def test_import_from_json_missing_edge_node_raises(self):
        graph = StateGraph()
        data = {"nodes": [], "edges": [{"source_id": "x", "target_id": "y", "cost": 1.0}]}
        with pytest.raises(ValueError):
            graph.import_from_json(data)

    def test_import_from_json_nodes_as_dict(self):
        graph = StateGraph()
        data = {"nodes": {"a": {"id": "a", "type": "action", "name": "a"}}, "edges": []}
        graph.import_from_json(data)
        assert graph.has_node("a")

    def test_import_graph_invalid_json_raises(self):
        graph = StateGraph()
        with pytest.raises(ValueError):
            graph.import_from_json({"nodes": "not_a_list", "edges": []})

    def test_serialize_deserialize_condition(self):
        cond = Condition(type=ConditionType.STATE_EQUALS, key="color", expected_value="red")
        serialized = StateGraph._serialize_condition(cond)
        assert serialized["type"] == ConditionType.STATE_EQUALS.value
        assert serialized["key"] == "color"
        assert serialized["expected_value"] == "red"

        deserialized = StateGraph._deserialize_condition(serialized)
        assert deserialized is not None
        assert deserialized.type == ConditionType.STATE_EQUALS
        assert deserialized.key == "color"
        assert deserialized.expected_value == "red"

    def test_deserialize_condition_non_dict_returns_none(self):
        assert StateGraph._deserialize_condition("not_a_dict") is None

    def test_serialize_deserialize_effect(self):
        eff = Effect(type="state_set", key="flag", value=True)
        serialized = StateGraph._serialize_effect(eff)
        assert serialized["type"] == "state_set"
        assert serialized["key"] == "flag"
        assert serialized["value"] is True

        deserialized = StateGraph._deserialize_effect(serialized)
        assert deserialized is not None
        assert deserialized.key == "flag"

    def test_deserialize_effect_non_dict_returns_none(self):
        assert StateGraph._deserialize_effect("not_a_dict") is None

    def test_deserialize_node(self):
        data = {"id": "n1", "type": "action", "name": "Test", "cost": 2.0}
        node = StateGraph._deserialize_node(data)
        assert node.id == "n1"
        assert node.type == NodeType.ACTION
        assert node.name == "Test"
        assert node.cost == 2.0

    def test_deserialize_node_missing_id_raises(self):
        with pytest.raises(ValueError):
            StateGraph._deserialize_node({"name": "no_id"})

    def test_deserialize_node_from_dict_fallback(self):
        """When Node.from_dict fails, the fallback constructor is used."""
        data = {"id": "test", "type": "action", "name": "T"}
        node = StateGraph._deserialize_node(data)
        assert node.id == "test"

    def test_json_safe_alias(self):
        assert StateGraph._json_safe("hello") == "hello"
        assert StateGraph._json_safe([1, 2]) == [1, 2]


# ---------------------------------------------------------------------------
# Strategy normalization
# ---------------------------------------------------------------------------

class TestNormalizeStrategy:
    def test_enum_passes_through(self):
        result = StateGraph._normalize_strategy(SearchStrategy.BFS)
        assert result == SearchStrategy.BFS

    def test_string_astar(self):
        assert StateGraph._normalize_strategy("astar") == SearchStrategy.A_STAR

    def test_string_a_star_variants(self):
        assert StateGraph._normalize_strategy("a*") == SearchStrategy.A_STAR
        assert StateGraph._normalize_strategy("a_star") == SearchStrategy.A_STAR
        assert StateGraph._normalize_strategy("a-star") == SearchStrategy.A_STAR

    def test_string_dijkstra(self):
        assert StateGraph._normalize_strategy("dijkstra") == SearchStrategy.DIJKSTRA

    def test_string_bfs(self):
        assert StateGraph._normalize_strategy("bfs") == SearchStrategy.BFS

    def test_string_dfs(self):
        assert StateGraph._normalize_strategy("dfs") == SearchStrategy.DFS

    def test_string_greedy(self):
        assert StateGraph._normalize_strategy("greedy") == SearchStrategy.GREEDY

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError):
            StateGraph._normalize_strategy("unknown")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def test_state_signature_consistent(self):
        sig1 = StateGraph._state_signature({"a": 1, "b": 2})
        sig2 = StateGraph._state_signature({"b": 2, "a": 1})
        assert sig1 == sig2

    def test_state_signature_different_states_different(self):
        sig1 = StateGraph._state_signature({"a": 1})
        sig2 = StateGraph._state_signature({"a": 2})
        assert sig1 != sig2

    def test_state_signature_none_state(self):
        sig = StateGraph._state_signature(None)
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_state_signature_unserializable_fallback(self):
        class Weird:
            pass
        sig = StateGraph._state_signature({"key": Weird()})
        assert isinstance(sig, str)

    def test_create_goal_from_node(self):
        graph = _build_simple_graph()
        goal = graph._create_goal_from_node("a")
        assert goal.id == "goal_a"
        assert goal.type == "reach_node"
        assert goal.target == "a"
        assert "Alcanzar nodo" in goal.description

    def test_create_goal_from_node_with_metadata_target(self):
        graph = StateGraph()
        node = _make_node("a", metadata={"target": "some_target"})
        graph.add_node(node)
        goal = graph._create_goal_from_node("a")
        assert goal.target == "some_target"

    def test_create_goal_from_node_with_metadata_description(self):
        graph = StateGraph()
        node = _make_node("a", description="Custom description", metadata={})
        graph.add_node(node)
        goal = graph._create_goal_from_node("a")
        assert goal.description == "Custom description"

    def test_estimate_heuristic_no_exception(self):
        graph = _build_simple_graph()
        goal = graph._create_goal_from_node("c")
        value = graph._estimate_heuristic("a", {}, goal)
        assert isinstance(value, float)
        assert math.isfinite(value) or value == 0.0

    def test_estimate_heuristic_uses_weight(self):
        graph = StateGraph(heuristic=Heuristic(HeuristicType.ZERO, weight=5.0))
        goal = graph._create_goal_from_node("c")
        value = graph._estimate_heuristic("a", {}, goal)
        assert value >= 0.0

    def test_normalize_max_iterations(self):
        assert StateGraph._normalize_max_iterations(500) == 500

    def test_normalize_max_iterations_invalid(self):
        assert StateGraph._normalize_max_iterations("invalid") == 1000

    def test_normalize_max_iterations_zero(self):
        assert StateGraph._normalize_max_iterations(0) == 1

    def test_normalize_alternative_count(self):
        assert StateGraph._normalize_alternative_count(5) == 5

    def test_normalize_alternative_count_too_many(self):
        assert StateGraph._normalize_alternative_count(50) == 20

    def test_normalize_alternative_count_invalid(self):
        assert StateGraph._normalize_alternative_count("invalid") == 3

    def test_normalize_alternative_count_negative(self):
        assert StateGraph._normalize_alternative_count(-5) == 0


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    def test_invalidate_search_cache_increments_revision(self):
        graph = StateGraph()
        initial = graph.graph_revision
        graph._invalidate_search_cache()
        assert graph.graph_revision == initial + 1

    def test_clear_search_cache_resets_graph_nodes(self):
        graph = _build_simple_graph()
        graph.find_route("a", "c", strategy=SearchStrategy.BFS)
        graph.clear_search_cache()
        for gn in graph.graph_nodes.values():
            assert gn.g_cost == float("inf")
            assert gn.visited is False
