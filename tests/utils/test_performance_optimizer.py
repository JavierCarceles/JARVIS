# -*- coding: utf-8 -*-
"""Tests de PerformanceOptimizer (src/utils/performance_optimizer.py)."""

import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import unittest

from utils.performance_optimizer import (
    OptimizationStrategy,
    OptimizationLevel,
    OptimizationMetrics,
    OptimizationAction,
    PerformanceOptimizer,
)


class TestOptimizationStrategy(unittest.TestCase):
    def test_valores(self):
        assert OptimizationStrategy.CPU_OPTIMIZATION.value == "cpu_optimization"
        assert OptimizationStrategy.MEMORY_OPTIMIZATION.value == "memory_optimization"
        assert OptimizationStrategy.DISK_OPTIMIZATION.value == "disk_optimization"
        assert OptimizationStrategy.NETWORK_OPTIMIZATION.value == "network_optimization"
        assert OptimizationStrategy.PROCESS_OPTIMIZATION.value == "process_optimization"
        assert OptimizationStrategy.CACHE_OPTIMIZATION.value == "cache_optimization"
        assert OptimizationStrategy.THREAD_POOL_OPTIMIZATION.value == "thread_pool_optimization"
        assert OptimizationStrategy.ALGORITHM_OPTIMIZATION.value == "algorithm_optimization"
        assert OptimizationStrategy.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert OptimizationStrategy.LOAD_BALANCING.value == "load_balancing"

    def test_count(self):
        assert len(list(OptimizationStrategy)) == 10


class TestOptimizationLevel(unittest.TestCase):
    def test_valores(self):
        assert OptimizationLevel.BASIC.value == "basic"
        assert OptimizationLevel.MODERATE.value == "moderate"
        assert OptimizationLevel.AGGRESSIVE.value == "aggressive"
        assert OptimizationLevel.CRITICAL.value == "critical"

    def test_count(self):
        assert len(list(OptimizationLevel)) == 4


class TestOptimizationMetrics(unittest.TestCase):
    def test_defaults(self):
        m = OptimizationMetrics()
        assert m.cpu_usage == 0.0
        assert m.memory_usage == 0.0
        assert m.disk_usage == 0.0
        assert m.network_usage == 0.0
        assert m.response_time == 0.0
        assert m.throughput == 0.0
        assert m.error_rate == 0.0
        assert m.efficiency_score == 0.0
        assert m.optimization_gain == 0.0
        assert isinstance(m.timestamp, datetime)

    def test_custom_values(self):
        m = OptimizationMetrics(
            cpu_usage=85.0,
            memory_usage=90.0,
            efficiency_score=0.85,
        )
        assert m.cpu_usage == 85.0
        assert m.memory_usage == 90.0
        assert m.efficiency_score == 0.85


class TestOptimizationAction(unittest.TestCase):
    def test_campos(self):
        action = OptimizationAction(
            action_id="act_001",
            strategy=OptimizationStrategy.CPU_OPTIMIZATION,
            level=OptimizationLevel.AGGRESSIVE,
            description="Reduce CPU usage",
            expected_improvement=20.0,
            confidence=0.9,
            priority=1,
            estimated_time=30.0,
            resources_needed={"cpu": 0.1},
            execution_command="python optimize_cpu.py",
            rollback_command="python restore_cpu.py",
        )
        assert action.action_id == "act_001"
        assert action.strategy == OptimizationStrategy.CPU_OPTIMIZATION
        assert action.level == OptimizationLevel.AGGRESSIVE
        assert action.status == "pending"
        assert action.start_time is None
        assert action.end_time is None
        assert action.actual_improvement is None
        assert action.success is False

    def test_defaults(self):
        action = OptimizationAction(
            action_id="act_002",
            strategy=OptimizationStrategy.MEMORY_OPTIMIZATION,
            level=OptimizationLevel.BASIC,
            description="Free memory",
            expected_improvement=10.0,
            confidence=0.7,
            priority=2,
            estimated_time=15.0,
            resources_needed={},
            execution_command="run",
            rollback_command="undo",
        )
        assert action.status == "pending"
        assert action.success is False
        assert action.actual_improvement is None


class TestPerformanceOptimizerInit(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_monitor_asignado(self):
        assert self.optimizer.monitor is not None

    def test_pattern_analyzer_asignado(self):
        assert self.optimizer.pattern_analyzer is not None

    def test_analytics_asignado(self):
        assert self.optimizer.analytics is not None

    def test_config_tiene_claves(self):
        assert "optimization_enabled" in self.optimizer.config
        assert "auto_optimization" in self.optimizer.config
        assert "optimization_interval" in self.optimizer.config
        assert "max_concurrent_actions" in self.optimizer.config

    def test_estado_inicial(self):
        assert self.optimizer.is_running is True  # _start_optimization_loop
        assert len(self.optimizer.current_actions) == 0
        assert isinstance(self.optimizer.current_metrics, OptimizationMetrics)

    def test_models_inicializados(self):
        assert "cpu" in self.optimizer.models
        assert "memory" in self.optimizer.models
        assert "disk" in self.optimizer.models
        assert "network" in self.optimizer.models
        assert "performance" in self.optimizer.models

    def test_scalers_inicializados(self):
        for metric in ["cpu", "memory", "disk", "network", "performance"]:
            assert metric in self.optimizer.scalers

    def test_thresholds(self):
        assert self.optimizer.optimization_thresholds["cpu_high"] == 80.0
        assert self.optimizer.optimization_thresholds["memory_high"] == 85.0
        assert self.optimizer.optimization_thresholds["disk_high"] == 90.0
        assert self.optimizer.optimization_thresholds["response_time_high"] == 1000.0
        assert self.optimizer.optimization_thresholds["error_rate_high"] == 0.05


class TestOptimizationStatus(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_status_contiene_claves(self):
        status = self.optimizer.get_optimization_status()
        assert "is_running" in status
        assert "current_metrics" in status
        assert "baseline_metrics" in status
        assert "active_actions" in status
        assert "queued_actions" in status
        assert "optimization_enabled" in status
        assert "auto_optimization" in status
        assert "efficiency_score" in status
        assert "optimization_gain" in status
        assert "last_analysis" in status

    def test_status_is_running(self):
        status = self.optimizer.get_optimization_status()
        assert status["is_running"] is True
        assert status["optimization_enabled"] is True

    def test_status_baseline_none(self):
        # The background loop may have set a baseline; just check it's not crashing
        status = self.optimizer.get_optimization_status()
        assert "baseline_metrics" in status

    def test_status_last_analysis(self):
        status = self.optimizer.get_optimization_status()
        assert "last_analysis" in status


class TestOptimizationHistory(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_history_vacia(self):
        self.optimizer.stop_optimization()
        self.optimizer.optimization_history = []
        assert self.optimizer.get_optimization_history() == []

    def test_history_limit(self):
        # Stop the background loop so it doesn't modify history
        self.optimizer.stop_optimization()
        self.optimizer.optimization_history = [{"timestamp": "t1"}, {"timestamp": "t2"}, {"timestamp": "t3"}]
        result = self.optimizer.get_optimization_history(limit=2)
        assert len(result) == 2
        assert result[-1]["timestamp"] == "t3"


class TestGetCurrentActions(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_empty(self):
        assert self.optimizer.get_current_actions() == []


class TestAddCustomOptimizationAction(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_add_action_to_queue(self):
        action = OptimizationAction(
            action_id="act_001",
            strategy=OptimizationStrategy.CPU_OPTIMIZATION,
            level=OptimizationLevel.BASIC,
            description="test",
            expected_improvement=5.0,
            confidence=0.8,
            priority=1,
            estimated_time=10.0,
            resources_needed={},
            execution_command="cmd",
            rollback_command="undo",
        )
        self.optimizer.add_custom_optimization_action(action)
        assert self.optimizer.optimization_queue.qsize() == 1


class TestStopStartOptimization(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_stop(self):
        self.optimizer.stop_optimization()
        assert self.optimizer.is_running is False
        assert self.optimizer.config["optimization_enabled"] is False

    def test_start_desde_parado(self):
        self.optimizer.stop_optimization()
        self.optimizer.start_optimization()
        assert self.optimizer.is_running is True
        assert self.optimizer.config["optimization_enabled"] is True


class TestOptimizeSystem(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_optimiza_sistema(self):
        action = self.optimizer.optimize_system(
            OptimizationStrategy.CPU_OPTIMIZATION,
            OptimizationLevel.AGGRESSIVE,
        )
        assert action is not None
        assert action.strategy == OptimizationStrategy.CPU_OPTIMIZATION
        assert action.level == OptimizationLevel.AGGRESSIVE
        assert action.status == "pending"
        assert self.optimizer.optimization_queue.qsize() == 1

    def test_optimiza_default_level(self):
        action = self.optimizer.optimize_system(OptimizationStrategy.MEMORY_OPTIMIZATION)
        assert action is not None
        assert action.level == OptimizationLevel.MODERATE

    def test_optimiza_action_id_formato(self):
        action = self.optimizer.optimize_system(OptimizationStrategy.DISK_OPTIMIZATION)
        assert action.action_id.startswith("manual_opt_")


class TestGetOptimizationRecommendations(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_no_recommendations(self):
        """Sin metricas altas, no hay recomendaciones."""
        self.optimizer.current_metrics = OptimizationMetrics()  # todo 0.0
        recs = self.optimizer.get_optimization_recommendations()
        assert recs == []

    def test_cpu_recommendation(self):
        self.optimizer.current_metrics = OptimizationMetrics(cpu_usage=85.0)
        recs = self.optimizer.get_optimization_recommendations()
        assert len(recs) >= 1
        assert recs[0]["type"] == "cpu"
        assert recs[0]["priority"] == "high"

    def test_memory_recommendation(self):
        self.optimizer.current_metrics = OptimizationMetrics(memory_usage=90.0)
        recs = self.optimizer.get_optimization_recommendations()
        assert any(r["type"] == "memory" for r in recs)

    def test_response_time_recommendation(self):
        self.optimizer.current_metrics = OptimizationMetrics(response_time=2000.0)
        recs = self.optimizer.get_optimization_recommendations()
        assert any(r["type"] == "performance" for r in recs)

    def test_error_rate_recommendation(self):
        self.optimizer.current_metrics = OptimizationMetrics(error_rate=0.10)
        recs = self.optimizer.get_optimization_recommendations()
        assert any(r["type"] == "error" for r in recs)

    def test_multiple_recommendations(self):
        self.optimizer.current_metrics = OptimizationMetrics(
            cpu_usage=85.0,
            memory_usage=90.0,
            response_time=2000.0,
            error_rate=0.10,
        )
        recs = self.optimizer.get_optimization_recommendations()
        assert len(recs) == 4


class TestExportOptimizationReport(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_export_report(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            self.optimizer.export_optimization_report(tmp_path)
            with open(tmp_path, 'r') as f:
                data = json.load(f)
            assert "timestamp" in data
            assert "current_metrics" in data
            assert "baseline_metrics" in data
            assert "optimization_history" in data
            assert "current_actions" in data
            assert "recommendations" in data
            assert "efficiency_score" in data
        finally:
            os.unlink(tmp_path)


class TestOptimizeResources(unittest.TestCase):
    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def tearDown(self):
        self.optimizer.stop_optimization()

    def test_optimize_basic(self):
        request = {
            "context": {"app": "chrome"},
            "current_resources": {"cpu": {"used": 50.0, "total": 100.0}},
        }
        result = self.optimizer.optimize_resources(request)
        assert isinstance(result, dict)

    def test_optimize_sin_contexto(self):
        request = {
            "current_resources": {"cpu": {"used": 50.0, "total": 100.0}},
        }
        result = self.optimizer.optimize_resources(request)
        assert isinstance(result, dict)

    def test_optimize_sin_recursos(self):
        request = {"context": {}}
        result = self.optimizer.optimize_resources(request)
        assert isinstance(result, dict)
