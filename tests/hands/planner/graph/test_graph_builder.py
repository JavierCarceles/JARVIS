# -*- coding: utf-8 -*-
"""Tests para GraphBuilder (src/hands/planner/graph.py)."""

import pytest

from src.hands.planner.graph import GraphBuilder, StateGraph
from src.hands.planner.node import Node, NodeType


def _make_navigation_nodes():
    """Nodes matching the IDs used by build_navigation_graph."""
    return {
        "chrome.closed": Node(id="chrome.closed", type=NodeType.STATE, name="chrome_closed"),
        "chrome.open": Node(id="chrome.open", type=NodeType.STATE, name="chrome_open"),
        "chrome.activate": Node(id="chrome.activate", type=NodeType.STATE, name="chrome_activate"),
        "focus_address_bar": Node(id="focus_address_bar", type=NodeType.ACTION, name="focus_address_bar"),
        "type_url": Node(id="type_url", type=NodeType.ACTION, name="type_url"),
        "press_enter": Node(id="press_enter", type=NodeType.ACTION, name="press_enter"),
        "destination.loaded": Node(id="destination.loaded", type=NodeType.STATE, name="destination_loaded"),
        "click_address_bar": Node(id="click_address_bar", type=NodeType.ACTION, name="click_address_bar"),
        "hotkey_ctrl_l": Node(id="hotkey_ctrl_l", type=NodeType.ACTION, name="hotkey_ctrl_l"),
        "search_google": Node(id="search_google", type=NodeType.ACTION, name="search_google"),
    }


def _make_application_nodes():
    """Nodes matching the IDs used by build_application_graph."""
    return {
        "application.closed": Node(id="application.closed", type=NodeType.STATE, name="app_closed"),
        "application.open": Node(id="application.open", type=NodeType.STATE, name="app_open"),
        "application.active": Node(id="application.active", type=NodeType.STATE, name="app_active"),
        "application.inactive": Node(id="application.inactive", type=NodeType.STATE, name="app_inactive"),
        "element.focused": Node(id="element.focused", type=NodeType.STATE, name="element_focused"),
        "text.typed": Node(id="text.typed", type=NodeType.STATE, name="text_typed"),
        "action.executed": Node(id="action.executed", type=NodeType.STATE, name="action_executed"),
    }


class TestBuildNavigationGraph:
    def test_returns_state_graph(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        assert isinstance(graph, StateGraph)

    def test_contains_all_nodes(self):
        nodes = _make_navigation_nodes()
        graph = GraphBuilder.build_navigation_graph(nodes)
        assert len(graph.nodes) == len(nodes)

    def test_has_edges(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        assert len(graph.edges) > 0

    def test_chrome_closed_to_open_edge_has_precondition(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        edge = graph.get_edge("chrome.closed", "chrome.open")
        assert edge is not None
        assert edge.cost == 10.0
        assert len(edge.preconditions) == 1

    def test_chrome_closed_to_open_edge_has_effect(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        edge = graph.get_edge("chrome.closed", "chrome.open")
        assert edge is not None
        assert len(edge.effects) == 1
        assert edge.effects[0].key == "chrome_open"
        assert edge.effects[0].value is True

    def test_navigation_edge_with_string_condition(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        edge = graph.get_edge("chrome.open", "chrome.activate")
        assert edge is not None
        assert edge.conditions == ["chrome_open"]

    def test_navigation_graph_valid(self):
        graph = GraphBuilder.build_navigation_graph(_make_navigation_nodes())
        errors = graph.validate_graph()
        assert errors == []

    def test_partial_nodes_builds_partial_graph(self):
        """Only edges whose both endpoints exist are created."""
        graph = GraphBuilder.build_navigation_graph({"chrome.closed": Node(id="chrome.closed", type=NodeType.STATE, name="c")})
        assert len(graph.nodes) == 1
        assert len(graph.edges) == 0  # no valid edges

    def test_empty_nodes_dict(self):
        graph = GraphBuilder.build_navigation_graph({})
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0


class TestBuildApplicationGraph:
    def test_returns_state_graph(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        assert isinstance(graph, StateGraph)

    def test_contains_all_nodes(self):
        nodes = _make_application_nodes()
        graph = GraphBuilder.build_application_graph(nodes)
        assert len(graph.nodes) == len(nodes)

    def test_has_edges(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        assert len(graph.edges) > 0

    def test_app_closed_to_open_has_precondition(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        edge = graph.get_edge("application.closed", "application.open")
        assert edge is not None
        assert edge.cost == 5.0
        assert len(edge.preconditions) == 1

    def test_app_closed_to_open_has_effect(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        edge = graph.get_edge("application.closed", "application.open")
        assert edge is not None
        assert len(edge.effects) == 1
        assert edge.effects[0].key == "app_open"
        assert edge.effects[0].value is True

    def test_application_graph_valid(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        errors = graph.validate_graph()
        assert errors == []

    def test_empty_nodes_dict(self):
        graph = GraphBuilder.build_application_graph({})
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_alternative_transition_type(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        edge = graph.get_edge("application.active", "application.inactive")
        assert edge is not None
        assert edge.transition_type == "alternative"

    def test_normal_transition_type(self):
        graph = GraphBuilder.build_application_graph(_make_application_nodes())
        edge = graph.get_edge("application.closed", "application.open")
        assert edge is not None
        assert edge.transition_type == "normal"
