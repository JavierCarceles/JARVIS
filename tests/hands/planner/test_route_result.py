# -*- coding: utf-8 -*-
"""Tests para RouteResult (src/hands/planner/graph.py)."""

import math

import pytest

from src.hands.planner.graph import GraphEdge, RouteResult, SearchStrategy


class TestRouteResultDefaults:
    def test_default_values(self):
        result = RouteResult(success=True, start_node_id="a", goal_node_id="b")
        assert result.success is True
        assert result.start_node_id == "a"
        assert result.goal_node_id == "b"
        assert result.path == []
        assert result.edges == []
        assert result.alternative_paths == []
        assert result.strategy == SearchStrategy.A_STAR.value
        assert result.iterations == 0
        assert result.elapsed_time == 0.0
        assert result.initial_state == {}
        assert result.final_state == {}
        assert result.error is None
        assert result.total_cost == float("inf")

    def test_total_cost_default_is_inf(self):
        result = RouteResult(success=False, start_node_id=None, goal_node_id=None, total_cost=None)
        assert result.total_cost == float("inf")


class TestRouteResultPostInit:
    def test_none_path_becomes_empty_list(self):
        result = RouteResult(success=True, start_node_id="a", goal_node_id="b", path=None)
        assert result.path == []

    def test_none_edges_becomes_empty_list(self):
        result = RouteResult(success=True, start_node_id="a", goal_node_id="b", edges=None)
        assert result.edges == []

    def test_none_alternative_paths_becomes_empty(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            alternative_paths=None,
        )
        assert result.alternative_paths == []

    def test_alternative_paths_are_defensive_copies(self):
        original = [["a", "b"], ["c", "d"]]
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            alternative_paths=original,
        )
        result.alternative_paths[0].append("z")
        assert original[0] == ["a", "b"]

    def test_initial_state_copied(self):
        state = {"key": "value"}
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            initial_state=state,
        )
        assert result.initial_state == {"key": "value"}
        assert result.initial_state is not state

    def test_final_state_copied(self):
        state = {"key": "value"}
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            final_state=state,
        )
        assert result.final_state is not state

    def test_non_dict_initial_state_becomes_empty(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            initial_state=[1, 2, 3],
        )
        assert result.initial_state == {}

    def test_iterations_normalized(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            iterations="100",
        )
        assert result.iterations == 100

    def test_iterations_negative_becomes_zero(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            iterations=-5,
        )
        assert result.iterations == 0

    def test_iterations_invalid_becomes_zero(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            iterations=None,
        )
        assert result.iterations == 0

    def test_elapsed_time_normalized(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            elapsed_time="1.5",
        )
        assert result.elapsed_time == 1.5

    def test_elapsed_time_negative_becomes_zero(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            elapsed_time=-1.0,
        )
        assert result.elapsed_time == 0.0

    def test_total_cost_string_normalized(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            total_cost="3.14",
        )
        assert result.total_cost == 3.14

    def test_total_cost_nan_becomes_inf(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            total_cost=float("nan"),
        )
        assert result.total_cost == float("inf")


class TestRouteResultProperties:
    def test_length_empty_path(self):
        result = RouteResult(success=True, start_node_id="a", goal_node_id="b")
        assert result.length == 0

    def test_length_with_path(self):
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b",
            path=["a", "mid", "b"],
        )
        assert result.length == 3

    def test_edge_count_empty(self):
        result = RouteResult(success=True, start_node_id="a", goal_node_id="b")
        assert result.edge_count == 0

    def test_edge_count_with_edges(self):
        edges = [
            GraphEdge(source_id="a", target_id="mid", cost=1.0),
            GraphEdge(source_id="mid", target_id="b", cost=2.0),
        ]
        result = RouteResult(
            success=True, start_node_id="a", goal_node_id="b", edges=edges,
        )
        assert result.edge_count == 2


class TestRouteResultToDict:
    def test_to_dict_structure(self):
        result = RouteResult(
            success=True,
            start_node_id="a",
            goal_node_id="b",
            path=["a", "b"],
            total_cost=5.0,
            error=None,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["start_node_id"] == "a"
        assert d["goal_node_id"] == "b"
        assert d["path"] == ["a", "b"]
        assert d["total_cost"] == 5.0
        assert d["strategy"] == SearchStrategy.A_STAR.value
        assert d["error"] is None

    def test_to_dict_with_edges(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, transition_type="normal")
        result = RouteResult(
            success=True,
            start_node_id="a",
            goal_node_id="b",
            path=["a", "b"],
            edges=[edge],
        )
        d = result.to_dict()
        assert len(d["edges"]) == 1
        serialized_edge = d["edges"][0]
        assert serialized_edge["source_id"] == "a"
        assert serialized_edge["target_id"] == "b"
        assert serialized_edge["cost"] == 1.0
        assert serialized_edge["transition_type"] == "normal"

    def test_to_dict_with_initial_state(self):
        result = RouteResult(
            success=True,
            start_node_id="a",
            goal_node_id="b",
            initial_state={"ready": True},
            final_state={"done": True},
        )
        d = result.to_dict()
        assert d["initial_state"] == {"ready": True}
        assert d["final_state"] == {"done": True}

    def test_to_dict_with_alternative_paths(self):
        result = RouteResult(
            success=True,
            start_node_id="a",
            goal_node_id="b",
            alternative_paths=[["a", "c", "b"], ["a", "d", "b"]],
        )
        d = result.to_dict()
        assert len(d["alternative_paths"]) == 2
        assert d["alternative_paths"][0] == ["a", "c", "b"]
