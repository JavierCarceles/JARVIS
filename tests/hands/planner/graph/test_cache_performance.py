# -*- coding: utf-8 -*-
"""Tests para CacheEntry y PerformanceMetrics (src/hands/planner/graph.py)."""

import time

import pytest

from src.hands.planner.graph import CacheEntry, PerformanceMetrics, _safe_float


class TestCacheEntry:
    def test_default_values(self):
        entry = CacheEntry(
            path=["a", "b"],
            cost=5.0,
            state={"key": "value"},
            timestamp=1000.0,
        )
        assert entry.path == ["a", "b"]
        assert entry.cost == 5.0
        assert entry.state == {"key": "value"}
        assert entry.timestamp == 1000.0
        assert entry.final_state == {}
        assert entry.strategy is None
        assert entry.alternative_paths == []
        assert entry.graph_revision is None
        assert entry.access_count == 0
        assert entry.last_access == 1000.0

    def test_path_is_copy(self):
        original = ["a", "b"]
        entry = CacheEntry(path=original, cost=1.0, state={}, timestamp=0.0)
        entry.path.append("c")
        assert original == ["a", "b"]

    def test_state_is_copy(self):
        original = {"key": "value"}
        entry = CacheEntry(path=[], cost=1.0, state=original, timestamp=0.0)
        entry.state["new"] = True
        assert original == {"key": "value"}

    def test_final_state_is_copy(self):
        original = {"key": "value"}
        entry = CacheEntry(
            path=[], cost=1.0, state={}, timestamp=0.0, final_state=original,
        )
        entry.final_state["new"] = True
        assert original == {"key": "value"}

    def test_final_state_none_becomes_empty(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=0.0, final_state=None)
        assert entry.final_state == {}

    def test_alternative_paths_are_copied(self):
        original = [["a", "b"], ["c", "d"]]
        entry = CacheEntry(
            path=[], cost=1.0, state={}, timestamp=0.0,
            alternative_paths=original,
        )
        entry.alternative_paths[0].append("z")
        assert original[0] == ["a", "b"]

    def test_alternative_paths_none_becomes_empty(self):
        entry = CacheEntry(
            path=[], cost=1.0, state={}, timestamp=0.0,
            alternative_paths=None,
        )
        assert entry.alternative_paths == []

    def test_cost_string_normalized(self):
        entry = CacheEntry(path=[], cost="3.14", state={}, timestamp=0.0)
        assert entry.cost == 3.14

    def test_cost_inf_string_becomes_inf(self):
        entry = CacheEntry(path=[], cost=float("inf"), state={}, timestamp=0.0)
        assert entry.cost == float("inf")

    def test_cost_invalid_becomes_inf(self):
        entry = CacheEntry(path=[], cost="invalid", state={}, timestamp=0.0)
        assert entry.cost == float("inf")

    def test_timestamp_string_normalized(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp="1000")
        assert entry.timestamp == 1000.0

    def test_timestamp_invalid_uses_current_time(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=None)
        assert entry.timestamp > 0.0

    def test_graph_revision_stored(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=0.0, graph_revision=5)
        assert entry.graph_revision == 5

    def test_is_not_expired(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time())
        assert entry.is_expired(max_age_seconds=300) is False

    def test_is_expired(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time() - 400)
        assert entry.is_expired(max_age_seconds=300) is True

    def test_is_expired_custom_max_age(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time() - 10)
        assert entry.is_expired(max_age_seconds=5) is True
        assert entry.is_expired(max_age_seconds=20) is False

    def test_is_expired_invalid_max_age_uses_default(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time() - 400)
        assert entry.is_expired(max_age_seconds="invalid") is True

    def test_is_expired_zero_max_age(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time() - 1)
        assert entry.is_expired(max_age_seconds=0) is True

    def test_increment_access(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=time.time())
        assert entry.access_count == 0
        entry.increment_access()
        assert entry.access_count == 1
        entry.increment_access()
        assert entry.access_count == 2

    def test_increment_access_updates_last_access(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=1000.0)
        old_last_access = entry.last_access
        time.sleep(0.001)
        entry.increment_access()
        assert entry.last_access > old_last_access

    def test_strategy_stored(self):
        entry = CacheEntry(path=[], cost=1.0, state={}, timestamp=0.0, strategy="astar")
        assert entry.strategy == "astar"


class TestPerformanceMetrics:
    def test_default_values(self):
        metrics = PerformanceMetrics()
        assert metrics.search_count == 0
        assert metrics.total_search_time == 0.0
        assert metrics.successful_searches == 0
        assert metrics.average_path_length == 0.0
        assert metrics.average_cost == 0.0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.max_iterations == 0
        assert metrics.min_iterations == float("inf")

    def test_record_search_increments_count(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=3, cost=5.0, search_time=0.1, iterations=10)
        assert metrics.search_count == 1

    def test_record_search_successful(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=3, cost=5.0, search_time=0.1, iterations=10)
        assert metrics.successful_searches == 1

    def test_record_search_unsuccessful(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=False, path_length=0, cost=float("inf"), search_time=0.1, iterations=5)
        assert metrics.successful_searches == 0
        assert metrics.search_count == 1

    def test_record_search_multiple_updates_average(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=2, cost=2.0, search_time=0.1, iterations=5)
        metrics.record_search(success=True, path_length=4, cost=4.0, search_time=0.2, iterations=10)
        assert metrics.search_count == 2
        assert metrics.successful_searches == 2
        # average path length = (2 + 4) / 2 = 3.0
        assert metrics.average_path_length == 3.0
        # average cost = (2.0 + 4.0) / 2 = 3.0
        assert metrics.average_cost == 3.0

    def test_record_search_updates_min_max_iterations(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.1, iterations=5)
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.1, iterations=20)
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.1, iterations=10)
        assert metrics.max_iterations == 20
        assert metrics.min_iterations == 5

    def test_record_search_negative_iterations(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.1, iterations=-5)
        assert metrics.max_iterations == 0
        assert metrics.min_iterations == 0

    def test_record_search_invalid_search_time(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time="invalid", iterations=5)
        assert metrics.total_search_time == 0.0

    def test_record_cache_hit(self):
        metrics = PerformanceMetrics()
        metrics.record_cache_hit()
        metrics.record_cache_hit()
        assert metrics.cache_hits == 2

    def test_record_cache_miss(self):
        metrics = PerformanceMetrics()
        metrics.record_cache_miss()
        metrics.record_cache_miss()
        metrics.record_cache_miss()
        assert metrics.cache_misses == 3

    def test_get_hit_rate_with_hits_and_misses(self):
        metrics = PerformanceMetrics()
        metrics.record_cache_hit()
        metrics.record_cache_hit()
        metrics.record_cache_miss()
        assert metrics.get_hit_rate() == 2 / 3

    def test_get_hit_rate_no_data(self):
        metrics = PerformanceMetrics()
        assert metrics.get_hit_rate() == 0.0

    def test_get_hit_rate_all_misses(self):
        metrics = PerformanceMetrics()
        metrics.record_cache_miss()
        assert metrics.get_hit_rate() == 0.0

    def test_get_hit_rate_all_hits(self):
        metrics = PerformanceMetrics()
        metrics.record_cache_hit()
        assert metrics.get_hit_rate() == 1.0

    def test_get_average_search_time(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.2, iterations=5)
        metrics.record_search(success=True, path_length=1, cost=1.0, search_time=0.4, iterations=5)
        assert metrics.get_average_search_time() == pytest.approx(0.3)

    def test_get_average_search_time_no_data(self):
        metrics = PerformanceMetrics()
        assert metrics.get_average_search_time() == 0.0

    def test_to_dict_structure(self):
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=3, cost=5.0, search_time=0.1, iterations=10)
        metrics.record_cache_hit()
        metrics.record_cache_miss()
        d = metrics.to_dict()
        assert d["search_count"] == 1
        assert d["successful_searches"] == 1
        assert d["success_rate"] == 1.0
        assert d["cache_hits"] == 1
        assert d["cache_misses"] == 1
        assert d["cache_hit_rate"] == 0.5
        assert d["max_iterations"] == 10
        assert d["min_iterations"] == 10
        assert "average_search_time" in d
        assert "average_path_length" in d
        assert "average_cost" in d

    def test_to_dict_min_iterations_inf_becomes_zero(self):
        metrics = PerformanceMetrics()
        d = metrics.to_dict()
        assert d["min_iterations"] == 0

    def test_to_dict_no_searches_success_rate(self):
        metrics = PerformanceMetrics()
        d = metrics.to_dict()
        assert d["success_rate"] == 0.0

    def test_unsuccessful_search_not_included_in_averages(self):
        """min/max iterations are updated for ALL searches; averages only for successful."""
        metrics = PerformanceMetrics()
        metrics.record_search(success=True, path_length=3, cost=5.0, search_time=0.1, iterations=10)
        metrics.record_search(success=False, path_length=0, cost=float("inf"), search_time=0.1, iterations=5)
        # Only 1 successful search, so averages reflect only that
        assert metrics.successful_searches == 1
        assert metrics.average_path_length == 3.0
        assert metrics.average_cost == 5.0
        # min/max are updated for all searches
        assert metrics.max_iterations == 10
        assert metrics.min_iterations == 5
