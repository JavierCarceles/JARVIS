# -*- coding: utf-8 -*-
"""Tests para AdvancedStateGraph (src/hands/planner/graph.py)."""

import math
import time

import pytest

from src.hands.planner.graph import (
    AdvancedStateGraph,
    CacheEntry,
    GraphEdge,
    PerformanceMetrics,
    RouteResult,
    SearchStrategy,
    StateGraph,
)
from src.hands.planner.heuristic import Heuristic, HeuristicType
from src.hands.planner.node import Node, NodeType
from src.hands.planner.preconditions_effects_types import ConditionType, Effect


def _make_node(node_id: str = "n1", **kwargs) -> Node:
    defaults = dict(id=node_id, type=NodeType.ACTION, name=f"node_{node_id}")
    defaults.update(kwargs)
    return Node(**defaults)


def _build_chain_graph() -> AdvancedStateGraph:
    """A -> B -> C, all unconditional, cost 1.0 each."""
    graph = AdvancedStateGraph()
    for nid in ("a", "b", "c"):
        graph.add_node(_make_node(nid))
    graph.add_edge("a", "b", 1.0)
    graph.add_edge("b", "c", 1.0)
    return graph


class TestAdvancedStateGraphInit:
    def test_is_state_graph_subclass(self):
        graph = AdvancedStateGraph()
        assert isinstance(graph, StateGraph)

    def test_default_cache_size(self):
        graph = AdvancedStateGraph()
        assert graph.cache_size == 100

    def test_custom_cache_size(self):
        graph = AdvancedStateGraph(cache_size=50)
        assert graph.cache_size == 50

    def test_custom_cache_size_invalid_becomes_100(self):
        graph = AdvancedStateGraph(cache_size="invalid")
        assert graph.cache_size == 100

    def test_cache_size_minimum_is_1(self):
        graph = AdvancedStateGraph(cache_size=0)
        assert graph.cache_size == 1

    def test_default_max_cache_age(self):
        graph = AdvancedStateGraph()
        assert graph.max_cache_age == 300

    def test_custom_max_cache_age(self):
        graph = AdvancedStateGraph(max_cache_age=600)
        assert graph.max_cache_age == 600

    def test_custom_max_cache_age_invalid(self):
        graph = AdvancedStateGraph(max_cache_age="invalid")
        assert graph.max_cache_age == 300.0

    def test_search_cache_initialized_empty(self):
        graph = AdvancedStateGraph()
        assert graph.search_cache == {}

    def test_performance_metrics_initialized(self):
        graph = AdvancedStateGraph()
        assert isinstance(graph.performance_metrics, PerformanceMetrics)

    def test_default_search_strategy(self):
        graph = AdvancedStateGraph()
        assert graph.search_strategy == SearchStrategy.A_STAR

    def test_custom_heuristic_propagated(self):
        custom = Heuristic(HeuristicType.UNIFORM, weight=3.0)
        graph = AdvancedStateGraph(heuristic=custom)
        assert graph.heuristic is custom


class TestFindPathWithStrategy:
    def test_finds_path(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("a", "c", {})
        assert path == ["a", "b", "c"]
        assert cost == 2.0
        assert alternatives == []

    def test_missing_start_node(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("nonexistent", "c", {})
        assert path == []
        assert cost == float("inf")

    def test_missing_goal_node(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("a", "nonexistent", {})
        assert path == []
        assert cost == float("inf")

    def test_invalid_strategy_returns_empty(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("a", "c", {}, strategy="invalid")
        assert path == []
        assert cost == float("inf")

    def test_string_strategy(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("a", "c", {}, strategy="dijkstra")
        assert path == ["a", "b", "c"]

    def test_default_strategy_is_astar(self):
        graph = _build_chain_graph()
        path, cost, _ = graph.find_path_with_strategy("a", "c", {})
        assert path == ["a", "b", "c"]

    def test_no_path(self):
        graph = AdvancedStateGraph()
        graph.add_node(_make_node("a"))
        graph.add_node(_make_node("b"))
        path, cost, alternatives = graph.find_path_with_strategy("a", "b", {})
        assert path == []
        assert cost == float("inf")

    def test_same_node(self):
        graph = _build_chain_graph()
        path, cost, _ = graph.find_path_with_strategy("a", "a", {})
        assert path == ["a"]
        assert cost == 0.0

    def test_alternatives_requested(self):
        graph = AdvancedStateGraph()
        for nid in ("a", "b", "c", "d"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0)
        graph.add_edge("a", "c", 5.0)
        graph.add_edge("b", "c", 1.0)
        graph.add_edge("c", "d", 1.0)

        path, cost, alternatives = graph.find_path_with_strategy(
            "a", "d", {}, strategy=SearchStrategy.A_STAR,
            find_alternatives=True, alternative_count=3,
        )
        assert path == ["a", "b", "c", "d"]
        assert len(alternatives) > 0

    def test_no_alternatives_when_disabled(self):
        graph = _build_chain_graph()
        path, cost, alternatives = graph.find_path_with_strategy("a", "c", {})
        assert alternatives == []

    def test_executes_all_strategies(self):
        graph = _build_chain_graph()
        for strategy in SearchStrategy:
            path, cost, alternatives = graph.find_path_with_strategy("a", "c", {}, strategy=strategy)
            assert path == ["a", "b", "c"], f"Strategy {strategy} failed"
            assert alternatives == []


class TestCacheFunctionality:
    def test_first_search_is_miss(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        assert graph.performance_metrics.cache_misses >= 1

    def test_cached_search_returns_cached_path(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        # After successful search, it should be cached
        assert len(graph.search_cache) > 0

    def test_cache_hit_returns_path(self):
        graph = _build_chain_graph()
        path1, cost1, _ = graph.find_path_with_strategy("a", "c", {})
        path2, cost2, _ = graph.find_path_with_strategy("a", "c", {})
        assert path1 == path2
        assert cost1 == cost2

    def test_cache_hit_increments_metrics(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        hits_before = graph.performance_metrics.cache_hits
        graph.find_path_with_strategy("a", "c", {})
        assert graph.performance_metrics.cache_hits > hits_before

    def test_cache_miss_increments_metrics(self):
        graph = _build_chain_graph()
        misses_before = graph.performance_metrics.cache_misses
        graph.find_path_with_strategy("a", "c", {})
        assert graph.performance_metrics.cache_misses > misses_before

    def test_cache_invalidated_on_graph_change(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        cache_before = len(graph.search_cache)
        assert cache_before > 0
        # Adding a new node invalidates cache
        graph.add_node(_make_node("new_node"))
        assert len(graph.search_cache) == 0

    def test_cache_entry_graph_revision_mismatch_invalidates(self):
        """Cache entries are invalidated when graph_revision changes."""
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        # Manually corrupt cache entry with old revision
        for key, entries in graph.search_cache.items():
            for entry in entries:
                entry.graph_revision = graph.graph_revision - 1
        # Next search should be a miss
        misses_before = graph.performance_metrics.cache_misses
        graph.find_path_with_strategy("a", "c", {})
        assert graph.performance_metrics.cache_misses > misses_before

    def test_expired_cache_entry_not_used(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {})
        # Manually expire the cache entry
        for key, entries in graph.search_cache.items():
            for entry in entries:
                entry.timestamp = time.time() - 10000  # very old
        # Next search should be a miss
        misses_before = graph.performance_metrics.cache_misses
        graph.find_path_with_strategy("a", "c", {})
        assert graph.performance_metrics.cache_misses > misses_before

    def test_cache_size_limit_enforced(self):
        graph = AdvancedStateGraph(cache_size=2)
        for i in range(10):
            graph.add_node(_make_node(f"start_{i}"))
            graph.add_node(_make_node(f"end_{i}"))
            graph.add_edge(f"start_{i}", f"end_{i}", 1.0)
            graph.find_path_with_strategy(f"start_{i}", f"end_{i}", {})
        assert len(graph.search_cache) <= 2

    def test_cache_strategy_agnostic(self):
        """Different strategies produce different cache keys."""
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {}, strategy=SearchStrategy.A_STAR)
        graph.find_path_with_strategy("a", "c", {}, strategy=SearchStrategy.BFS)
        # Should have 2 cache entries (different strategies)
        assert len(graph.search_cache) == 2

    def test_cache_different_state_different_key(self):
        graph = _build_chain_graph()
        graph.find_path_with_strategy("a", "c", {"flag": True})
        graph.find_path_with_strategy("a", "c", {"flag": False})
        assert len(graph.search_cache) == 2

    def test_find_route_records_performance_metrics(self):
        graph = _build_chain_graph()
        graph.find_route("a", "c")
        assert graph.performance_metrics.search_count >= 1

    def test_find_route_uses_default_strategy(self):
        graph = _build_chain_graph()
        result = graph.find_route("a", "c")
        assert result.success is True
        assert result.strategy == "a_star"

    def test_find_route_with_alternatives(self):
        graph = AdvancedStateGraph()
        for nid in ("a", "b", "c", "d"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0)
        graph.add_edge("a", "c", 5.0)
        graph.add_edge("b", "c", 1.0)
        graph.add_edge("c", "d", 1.0)

        result = graph.find_route(
            "a", "d", find_alternatives=True, alternative_count=3,
        )
        assert result.success is True
        assert len(result.alternative_paths) > 0

    def test_build_route_alias(self):
        graph = _build_chain_graph()
        result = graph.build_route("a", "c")
        assert result.success is True
        assert result.path == ["a", "b", "c"]

    def test_find_route_final_state_has_effects(self):
        graph = AdvancedStateGraph()
        for nid in ("a", "b"):
            graph.add_node(_make_node(nid))
        graph.add_edge("a", "b", 1.0, effects=[Effect(type="state_set", key="done", value=True)])

        result = graph.find_route("a", "b")
        assert result.success is True
        assert result.final_state == {"done": True}


class TestAdvancedStatsAndOptimization:
    def test_get_advanced_stats_structure(self):
        graph = _build_chain_graph()
        stats = graph.get_advanced_stats()
        assert "total_nodes" in stats
        assert "total_edges" in stats
        assert "search_cache_keys" in stats
        assert "cache_hit_rate" in stats
        assert "performance_metrics" in stats
        assert "search_strategies" in stats
        assert "current_strategy" in stats
        assert "cache_config" in stats

    def test_get_advanced_stats_values(self):
        graph = _build_chain_graph()
        stats = graph.get_advanced_stats()
        assert stats["total_nodes"] == 3
        assert stats["total_edges"] == 2
        assert stats["search_cache_keys"] == 0
        assert stats["cache_hit_rate"] == 0.0
        assert stats["current_strategy"] == "a_star"
        assert stats["cache_config"]["max_size"] == 100
        assert stats["cache_config"]["max_age_seconds"] == 300

    def test_get_advanced_stats_search_strategies(self):
        graph = _build_chain_graph()
        stats = graph.get_advanced_stats()
        strategies = stats["search_strategies"]
        assert "a_star" in strategies
        assert "dijkstra" in strategies
        assert "bfs" in strategies
        assert "dfs" in strategies
        assert "greedy" in strategies

    def test_get_advanced_stats_includes_performance_metrics(self):
        graph = _build_chain_graph()
        graph.find_route("a", "c")
        stats = graph.get_advanced_stats()
        pm = stats["performance_metrics"]
        assert pm["search_count"] >= 1

    def test_optimize_graph_for_performance_returns_changes(self):
        graph = _build_chain_graph()
        changes = graph.optimize_graph_for_performance()
        assert isinstance(changes, list)

    def test_optimize_graph_for_performance_clears_expired_cache(self):
        """Expired cache entries are removed by optimize_graph_for_performance."""
        graph = _build_chain_graph()
        graph.find_route("a", "c")
        assert len(graph.search_cache) > 0
        # Expire all entries
        for key, entries in graph.search_cache.items():
            for entry in entries:
                entry.timestamp = time.time() - 10000
        graph.optimize_graph_for_performance()
        assert len(graph.search_cache) == 0

    def test_optimize_graph_for_performance_adjusts_cache_size(self):
        graph = AdvancedStateGraph(cache_size=10)
        graph.optimize_graph_for_performance()
        # With <= 3 nodes, cache_size should be 100
        assert graph.cache_size == 100

    def test_optimize_graph_for_performance_large_graph(self):
        graph = AdvancedStateGraph(cache_size=10)
        for i in range(120):
            graph.add_node(_make_node(f"n{i}"))
        graph.optimize_graph_for_performance()
        # With > 100 nodes, cache_size should be 200
        assert graph.cache_size == 200

    def test_optimize_graph_for_performance_medium_graph(self):
        graph = AdvancedStateGraph(cache_size=10)
        for i in range(60):
            graph.add_node(_make_node(f"n{i}"))
        graph.optimize_graph_for_performance()
        # With > 50 nodes, cache_size should be 150
        assert graph.cache_size == 150

    def test_build_cache_key_deterministic(self):
        graph = _build_chain_graph()
        key1 = graph._build_cache_key("a", "c", {}, SearchStrategy.A_STAR, False, 3, 1000)
        key2 = graph._build_cache_key("a", "c", {}, SearchStrategy.A_STAR, False, 3, 1000)
        assert key1 == key2

    def test_build_cache_key_different_strategy_different(self):
        graph = _build_chain_graph()
        key1 = graph._build_cache_key("a", "c", {}, SearchStrategy.A_STAR, False, 3, 1000)
        key2 = graph._build_cache_key("a", "c", {}, SearchStrategy.BFS, False, 3, 1000)
        assert key1 != key2

    def test_build_cache_key_different_state_different(self):
        graph = _build_chain_graph()
        key1 = graph._build_cache_key("a", "c", {"flag": True}, SearchStrategy.A_STAR, False, 3, 1000)
        key2 = graph._build_cache_key("a", "c", {"flag": False}, SearchStrategy.A_STAR, False, 3, 1000)
        assert key1 != key2

    def test_get_from_cache_no_entry(self):
        graph = _build_chain_graph()
        result = graph._get_from_cache("nonexistent", {})
        assert result is None

    def test_get_from_cache_expired_entry(self):
        graph = _build_chain_graph()
        entry = CacheEntry(
            path=["a", "b"], cost=2.0, state={}, timestamp=time.time() - 10000,
        )
        graph.search_cache["test_key"] = [entry]
        result = graph._get_from_cache("test_key", {})
        assert result is None
        assert "test_key" not in graph.search_cache

    def test_get_from_cache_revision_mismatch(self):
        graph = _build_chain_graph()
        entry = CacheEntry(
            path=["a", "b"], cost=2.0, state={}, timestamp=time.time(),
            graph_revision=graph.graph_revision - 1,
        )
        graph.search_cache["test_key"] = [entry]
        result = graph._get_from_cache("test_key", {})
        assert result is None

    def test_get_from_cache_revision_match(self):
        graph = _build_chain_graph()
        entry = CacheEntry(
            path=["a", "b"], cost=2.0, state={}, timestamp=time.time(),
            graph_revision=graph.graph_revision,
        )
        graph.search_cache["test_key"] = [entry]
        result = graph._get_from_cache("test_key", {})
        assert result is not None
        assert result.path == ["a", "b"]

    def test_get_from_cache_none_revision_always_valid(self):
        graph = _build_chain_graph()
        entry = CacheEntry(
            path=["a", "b"], cost=2.0, state={}, timestamp=time.time(),
            graph_revision=None,
        )
        graph.search_cache["test_key"] = [entry]
        result = graph._get_from_cache("test_key", {})
        assert result is not None

    def test_get_from_cache_selects_most_recent(self):
        graph = _build_chain_graph()
        entry1 = CacheEntry(
            path=["a", "b", "c"], cost=2.0, state={}, timestamp=time.time() - 100,
        )
        entry2 = CacheEntry(
            path=["a", "x", "c"], cost=2.0, state={}, timestamp=time.time(),
        )
        # access_count is set to 0 in __init__, must be set manually
        entry1.access_count = 5
        entry2.access_count = 10
        graph.search_cache["test_key"] = [entry1, entry2]
        result = graph._get_from_cache("test_key", {})
        assert result is not None
        assert result.path == ["a", "x", "c"]

    def test_add_to_cache_under_limit(self):
        graph = AdvancedStateGraph(cache_size=5)
        entry = CacheEntry(path=["a"], cost=1.0, state={}, timestamp=time.time())
        graph._add_to_cache("key1", entry)
        assert "key1" in graph.search_cache

    def test_add_to_cache_exceeds_limit_evicts_oldest(self):
        graph = AdvancedStateGraph(cache_size=2)
        entry1 = CacheEntry(path=["a"], cost=1.0, state={}, timestamp=time.time() - 100)
        entry2 = CacheEntry(path=["b"], cost=1.0, state={}, timestamp=time.time() - 50)
        entry3 = CacheEntry(path=["c"], cost=1.0, state={}, timestamp=time.time())
        graph._add_to_cache("k1", entry1)
        graph._add_to_cache("k2", entry2)
        graph._add_to_cache("k3", entry3)
        # cache_size=2, so k1 (oldest) should be evicted
        assert "k1" not in graph.search_cache
        assert "k3" in graph.search_cache

    def test_cleanup_cache_removes_expired(self):
        graph = _build_chain_graph()
        old_entry = CacheEntry(path=["a"], cost=1.0, state={}, timestamp=time.time() - 10000)
        fresh_entry = CacheEntry(path=["b"], cost=1.0, state={}, timestamp=time.time())
        graph.search_cache["old"] = [old_entry]
        graph.search_cache["fresh"] = [fresh_entry]
        graph._cleanup_cache()
        assert "old" not in graph.search_cache
        assert "fresh" in graph.search_cache

    def test_cleanup_cache_removes_revision_mismatch(self):
        graph = _build_chain_graph()
        mismatched = CacheEntry(
            path=["a"], cost=1.0, state={}, timestamp=time.time(),
            graph_revision=graph.graph_revision - 1,
        )
        graph.search_cache["mismatch"] = [mismatched]
        graph._cleanup_cache()
        assert "mismatch" not in graph.search_cache

    def test_cache_hit_rate_after_search(self):
        graph = _build_chain_graph()
        # First search: miss
        graph.find_route("a", "c")
        # Second search: hit
        graph.find_route("a", "c")
        metrics = graph.performance_metrics
        assert metrics.cache_hits >= 1
        assert metrics.cache_misses >= 1
        assert metrics.get_hit_rate() > 0.0

    def test_search_with_all_strategies_records_metrics(self):
        graph = _build_chain_graph()
        for strategy in SearchStrategy:
            graph.find_path_with_strategy("a", "c", {}, strategy=strategy)
        assert graph.performance_metrics.search_count >= len(list(SearchStrategy))
