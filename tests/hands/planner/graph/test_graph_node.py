# -*- coding: utf-8 -*-
"""Tests para GraphNode (src/hands/planner/graph.py)."""

import math

import pytest

from src.hands.planner.graph import GraphNode, SearchStrategy
from src.hands.planner.node import Node, NodeType


def _make_node(node_id: str = "n1", **kwargs) -> Node:
    defaults = dict(id=node_id, type=NodeType.ACTION, name=f"node_{node_id}")
    defaults.update(kwargs)
    return Node(**defaults)


class TestGraphNodeDataclass:
    def test_default_values(self):
        node = _make_node("a")
        gn = GraphNode(node=node)
        assert gn.g_cost == float("inf")
        assert gn.h_cost == 0.0
        assert gn.f_cost == float("inf")
        assert gn.parent is None
        assert gn.visited is False
        assert gn.state is None

    def test_custom_values(self):
        node = _make_node("b")
        gn = GraphNode(node=node, g_cost=5.0, h_cost=3.0, f_cost=8.0, parent="start", visited=True, state={"flag": True})
        assert gn.g_cost == 5.0
        assert gn.h_cost == 3.0
        assert gn.f_cost == 8.0
        assert gn.parent == "start"
        assert gn.visited is True
        assert gn.state == {"flag": True}


class TestGraphNodeComparison:
    def test_lt_by_f_cost(self):
        node1 = _make_node("a")
        node2 = _make_node("b")
        gn1 = GraphNode(node=node1, f_cost=1.0)
        gn2 = GraphNode(node=node2, f_cost=2.0)
        assert gn1 < gn2
        assert not (gn2 < gn1)

    def test_lt_same_f_cost_by_node_id(self):
        node1 = _make_node("alpha")
        node2 = _make_node("beta")
        gn1 = GraphNode(node=node1, f_cost=1.0)
        gn2 = GraphNode(node=node2, f_cost=1.0)
        # "alpha" < "beta" lexicographically
        assert gn1 < gn2
        assert not (gn2 < gn1)

    def test_lt_same_f_cost_same_node_id_is_not_less(self):
        node1 = _make_node("x")
        node2 = _make_node("x")  # same id
        gn1 = GraphNode(node=node1, f_cost=1.0)
        gn2 = GraphNode(node=node2, f_cost=1.0)
        assert not (gn1 < gn2)
        assert not (gn2 < gn1)
        assert gn1 == gn2 or gn1 is not gn2  # not the same object necessarily

    def test_lt_against_non_graph_node_returns_not_implemented(self):
        node = _make_node("x")
        gn = GraphNode(node=node, f_cost=1.0)
        # Comparing with a non-GraphNode should not raise directly
        with pytest.raises(TypeError):
            _ = gn < 5

    def test_node_id_comparison_uses_str(self):
        """GraphNode.__lt__ uses str(getattr(self.node, 'id', ''))."""
        node1 = _make_node("10_node")
        node2 = _make_node("2_node")
        gn1 = GraphNode(node=node1, f_cost=1.0)
        gn2 = GraphNode(node=node2, f_cost=1.0)
        # "10_node" < "2_node" because '1' < '2' in string comparison
        assert gn1 < gn2
