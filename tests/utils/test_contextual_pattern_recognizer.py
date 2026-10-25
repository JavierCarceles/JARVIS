# -*- coding: utf-8 -*-
"""Tests de ContextualPatternRecognizer (src/utils/contextual_pattern_recognizer.py)."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pytest

from utils.contextual_pattern_recognizer import (
    ContextualPatternRecognizer,
    ContextualPatternType,
    ContextualPattern,
)
from utils.contextual_adaptation_engine import (
    ContextSnapshot,
    ContextualFactor,
    ContextType,
    AdaptationLevel,
)
from utils.pattern_analyzer import PatternSeverity


def _make_snapshot(factors=None, hour=None):
    """Crear un ContextSnapshot de prueba."""
    if factors is None:
        factors = {}
    ts = datetime.now()
    if hour is not None:
        ts = ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    return ContextSnapshot(
        snapshot_id="snap_001",
        timestamp=ts,
        context_type=ContextType.PRODUCTION,
        contextual_factors=factors,
        system_metrics={},
        performance_metrics={},
        user_interaction_patterns={},
        environmental_conditions={},
        confidence_score=0.9,
        adaptation_level=AdaptationLevel.MINIMAL,
    )


class TestContextualPatternType:
    def test_values(self):
        assert ContextualPatternType.CONTEXTUAL_ANOMALY.value == "contextual_anomaly"
        assert ContextualPatternType.CONTEXTUAL_TREND.value == "contextual_trend"
        assert ContextualPatternType.CONTEXTUAL_CORRELATION.value == "contextual_correlation"
        assert ContextualPatternType.CONTEXTUAL_SEASONAL.value == "contextual_seasonal"
        assert ContextualPatternType.CONTEXTUAL_BURST.value == "contextual_burst"
        assert ContextualPatternType.CONTEXTUAL_CHANGEPOINT.value == "contextual_changepoint"

    def test_count(self):
        assert len(list(ContextualPatternType)) == 6


class TestContextualPatternDataclass:
    def test_campos(self):
        snap = _make_snapshot()
        p = ContextualPattern(
            id="pat_001",
            type=ContextualPatternType.CONTEXTUAL_ANOMALY,
            severity=PatternSeverity.HIGH,
            description="test anomaly",
            timestamp=datetime.now(),
            confidence=0.8,
            context_snapshot=snap,
            pattern_data={"key": "val"},
            affected_components=["comp"],
            suggested_actions=["action"],
            compatibility_score=0.7,
        )
        assert p.id == "pat_001"
        assert p.type == ContextualPatternType.CONTEXTUAL_ANOMALY
        assert p.compatibility_score == 0.7

    def test_default_compatibility_score(self):
        snap = _make_snapshot()
        p = ContextualPattern(
            id="pat_002",
            type=ContextualPatternType.CONTEXTUAL_TREND,
            severity=PatternSeverity.MEDIUM,
            description="trend",
            timestamp=datetime.now(),
            confidence=0.7,
            context_snapshot=snap,
            pattern_data={},
            affected_components=[],
            suggested_actions=[],
        )
        assert p.compatibility_score == 0.0


class TestInit:
    def test_default_pattern_analyzer(self):
        recognizer = ContextualPatternRecognizer()
        assert recognizer.pattern_analyzer is not None

    def test_injected_pattern_analyzer(self):
        from utils.pattern_analyzer import PatternAnalyzer
        pa = PatternAnalyzer()
        recognizer = ContextualPatternRecognizer(pattern_analyzer=pa)
        assert recognizer.pattern_analyzer is pa

    def test_initial_state(self):
        recognizer = ContextualPatternRecognizer()
        assert recognizer.contextual_patterns == []
        assert recognizer.pattern_history == []
        assert "high" in recognizer.compatibility_thresholds
        assert "medium" in recognizer.compatibility_thresholds
        assert "low" in recognizer.compatibility_thresholds


class TestDetectContextualAnomaly:
    def test_anomaly_system_resources(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_ANOMALY
        assert result.severity == PatternSeverity.MEDIUM  # solo 1 anomaly
        assert "anomalies" in result.pattern_data

    def test_anomaly_user_behavior(self):
        factors = {ContextualFactor.USER_BEHAVIOR: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is not None
        assert result.severity == PatternSeverity.MEDIUM

    def test_anomaly_network_conditions(self):
        factors = {ContextualFactor.NETWORK_CONDITIONS: 0.85}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is not None
        assert result.pattern_data["anomalies"][0]["factor"] == "NETWORK_CONDITIONS"

    def test_anomaly_error_rates(self):
        factors = {ContextualFactor.ERROR_RATES: 0.20}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is not None
        assert result.pattern_data["anomalies"][0]["factor"] == "ERROR_RATES"

    def test_anomaly_alta_severidad(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.95,
            ContextualFactor.USER_BEHAVIOR: 0.95,
            ContextualFactor.NETWORK_CONDITIONS: 0.85,
            ContextualFactor.ERROR_RATES: 0.20,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is not None
        assert result.severity == PatternSeverity.HIGH  # > 2 anomalies

    def test_anomaly_no_anomalia(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.5}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result is None

    def test_anomaly_confidence(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_anomaly(snap)
        assert result.confidence <= 0.9


class TestDetectContextualTrend:
    def test_trend_high_factors(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.85,
            ContextualFactor.USER_BEHAVIOR: 0.82,
            ContextualFactor.WORKLOAD: 0.88,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_trend(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_TREND
        assert result.pattern_data["trend_factors"]  # list with entries
        assert len(result.pattern_data["trend_factors"]) == 3

    def test_trend_low_factors(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.05,
            ContextualFactor.USER_BEHAVIOR: 0.02,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_trend(snap)
        assert result is not None
        assert len(result.pattern_data["trend_factors"]) == 2
        assert all(f["trend_type"] == "low" for f in result.pattern_data["trend_factors"])

    def test_trend_no_trend(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.5}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_trend(snap)
        assert result is None

    def test_trend_mixed(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.85,
            ContextualFactor.USER_BEHAVIOR: 0.50,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_trend(snap)
        assert result is not None
        assert len(result.pattern_data["trend_factors"]) == 1
        assert result.pattern_data["trend_factors"][0]["trend_type"] == "high"


class TestDetectContextualCorrelation:
    def test_correlation_high_high(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.9,
            ContextualFactor.USER_BEHAVIOR: 0.85,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_correlation(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_CORRELATION
        assert len(result.pattern_data["correlations"]) == 1

    def test_correlation_low_low(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.05,
            ContextualFactor.USER_BEHAVIOR: 0.10,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_correlation(snap)
        assert result is not None
        assert result.pattern_data["correlations"][0]["type"] == "low_low"

    def test_no_correlation(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.5,
            ContextualFactor.USER_BEHAVIOR: 0.3,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_correlation(snap)
        assert result is None

    def test_no_correlation_empty(self):
        snap = _make_snapshot(factors={})
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_correlation(snap)
        assert result is None


class TestDetectContextualSeasonal:
    def test_morning_peak(self):
        snap = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.3}, hour=8)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_seasonal(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_SEASONAL
        assert "morning_peak" in result.pattern_data["seasonal_patterns"]

    def test_afternoon_peak(self):
        snap = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.3}, hour=15)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_seasonal(snap)
        assert result is not None
        assert "afternoon_peak" in result.pattern_data["seasonal_patterns"]

    def test_evening_peak(self):
        snap = _make_snapshot(factors={}, hour=20)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_seasonal(snap)
        assert result is not None
        assert "evening_peak" in result.pattern_data["seasonal_patterns"]

    def test_night_low(self):
        snap = _make_snapshot(factors={}, hour=3)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_seasonal(snap)
        assert result is not None
        assert "night_low" in result.pattern_data["seasonal_patterns"]


class TestDetectContextualBurst:
    def test_burst_high(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.8,
            ContextualFactor.USER_BEHAVIOR: 0.5,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_burst(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_BURST
        assert len(result.pattern_data["burst_factors"]) == 2
        assert result.pattern_data["burst_factors"][0]["burst_level"] == "high"

    def test_burst_medium(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.5}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_burst(snap)
        assert result is not None
        assert result.pattern_data["burst_factors"][0]["burst_level"] == "medium"

    def test_no_burst(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.3}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_burst(snap)
        assert result is None


class TestDetectContextualChangepoint:
    def test_changepoint_high(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.95,
            ContextualFactor.USER_BEHAVIOR: 0.92,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_changepoint(snap)
        assert result is not None
        assert result.type == ContextualPatternType.CONTEXTUAL_CHANGEPOINT
        assert len(result.pattern_data["extreme_changes"]) == 2

    def test_changepoint_low(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.05}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_changepoint(snap)
        assert result is not None
        assert result.pattern_data["extreme_changes"][0]["change_type"] == "low"

    def test_changepoint_critical_severity(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.95,
            ContextualFactor.USER_BEHAVIOR: 0.92,
            ContextualFactor.ERROR_RATES: 0.93,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_changepoint(snap)
        assert result is not None
        assert result.severity == PatternSeverity.CRITICAL  # > 2 extreme changes

    def test_no_changepoint(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.5}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_changepoint(snap)
        assert result is None


class TestCalculateContextualCompatibility:
    def test_values(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.8}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._calculate_contextual_compatibility(snap)
        assert result == 0.8

    def test_empty_factors(self):
        snap = _make_snapshot(factors={})
        recognizer = ContextualPatternRecognizer()
        result = recognizer._calculate_contextual_compatibility(snap)
        assert result == 0.0

    def test_multiple_factors(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.6,
            ContextualFactor.USER_BEHAVIOR: 0.4,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._calculate_contextual_compatibility(snap)
        assert result == 0.5  # (0.6 + 0.4) / 2


class TestGetAffectedComponents:
    def test_system_resources(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.9}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        assert "System-intensive" in recognizer._get_affected_components(snap)

    def test_user_behavior(self):
        factors = {ContextualFactor.USER_BEHAVIOR: 0.9}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        assert "User-intensive" in recognizer._get_affected_components(snap)

    def test_network_conditions(self):
        factors = {ContextualFactor.NETWORK_CONDITIONS: 0.9}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        assert "Network-intensive" in recognizer._get_affected_components(snap)

    def test_error_rates(self):
        factors = {ContextualFactor.ERROR_RATES: 0.2}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        assert "Error-prone" in recognizer._get_affected_components(snap)

    def test_no_affectados(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.5}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        comps = recognizer._get_affected_components(snap)
        assert comps == ["General"]


class TestAddContextualPattern:
    def test_add_anomaly(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer.add_contextual_pattern(snap)
        assert result is not None
        assert len(recognizer.contextual_patterns) == 1
        assert len(recognizer.pattern_history) == 1

    def test_add_no_pattern(self):
        # hour=12 esta fuera de todos los rangos estacionales (11-13)
        # y 0.3 no dispara anomalia, tendencia, correlacion o changepoint
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.3}
        snap = _make_snapshot(factors=factors, hour=12)
        recognizer = ContextualPatternRecognizer()
        result = recognizer.add_contextual_pattern(snap)
        assert result is None
        assert len(recognizer.contextual_patterns) == 0

    def test_add_registra_history(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        history = recognizer.pattern_history
        assert len(history) == 1
        assert "timestamp" in history[0]
        assert "pattern_id" in history[0]
        assert "compatibility_score" in history[0]


class TestGetContextualPatterns:
    def test_get_all(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        results = recognizer.get_contextual_patterns()
        assert len(results) == 1

    def test_filter_by_type(self):
        snap = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.95})
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        results = recognizer.get_contextual_patterns(ContextualPatternType.CONTEXTUAL_ANOMALY)
        assert len(results) == 1

    def test_filter_no_match(self):
        snap = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.95})
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        results = recognizer.get_contextual_patterns(ContextualPatternType.CONTEXTUAL_BURST)
        assert len(results) == 0


class TestGetPatternsBySeverity:
    def test_filter_by_severity(self):
        factors = {
            ContextualFactor.SYSTEM_RESOURCES: 0.95,
            ContextualFactor.USER_BEHAVIOR: 0.95,
            ContextualFactor.NETWORK_CONDITIONS: 0.85,
            ContextualFactor.ERROR_RATES: 0.20,
        }
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        results = recognizer.get_patterns_by_severity(PatternSeverity.HIGH)
        assert len(results) == 1

    def test_empty(self):
        recognizer = ContextualPatternRecognizer()
        assert recognizer.get_patterns_by_severity(PatternSeverity.LOW) == []


class TestGetHighCompatibilityPatterns:
    def test_high_compatibility(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.9}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        results = recognizer.get_high_compatibility_patterns(threshold=0.5)
        assert len(results) == 1

    def test_no_match(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.05}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)  # changepoint detected
        results = recognizer.get_high_compatibility_patterns(threshold=0.99)
        assert len(results) == 0


class TestClearPatterns:
    def test_clear_all(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        assert len(recognizer.contextual_patterns) == 1
        # older_than_hours=-1 hace que el cutoff sea futuro → filtra todo
        recognizer.clear_patterns(older_than_hours=-1)
        assert len(recognizer.contextual_patterns) == 0

    def test_clear_old_only(self):
        # ContextualPattern.timestamp se setea a datetime.now() en deteccion,
        # asi que creamos manualmente patrones con timestamps antiguo/reciente
        snap_old = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.3}, hour=12)
        old_pattern = ContextualPattern(
            id="pat_old",
            type=ContextualPatternType.CONTEXTUAL_ANOMALY,
            severity=PatternSeverity.MEDIUM,
            description="old",
            timestamp=datetime.now() - timedelta(hours=48),
            confidence=0.6,
            context_snapshot=snap_old,
            pattern_data={},
            affected_components=[],
            suggested_actions=[],
            compatibility_score=0.5,
        )
        snap_new = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.3}, hour=12)
        new_pattern = ContextualPattern(
            id="pat_new",
            type=ContextualPatternType.CONTEXTUAL_ANOMALY,
            severity=PatternSeverity.MEDIUM,
            description="new",
            timestamp=datetime.now(),
            confidence=0.6,
            context_snapshot=snap_new,
            pattern_data={},
            affected_components=[],
            suggested_actions=[],
            compatibility_score=0.5,
        )
        recognizer = ContextualPatternRecognizer()
        recognizer.contextual_patterns = [old_pattern, new_pattern]
        recognizer.clear_patterns(older_than_hours=24)
        assert len(recognizer.contextual_patterns) == 1
        assert recognizer.contextual_patterns[0].id == "pat_new"


class TestGetPatternSummary:
    def test_empty_summary(self):
        recognizer = ContextualPatternRecognizer()
        summary = recognizer.get_pattern_summary()
        assert summary["total_patterns"] == 0
        assert summary["by_type"] == {}
        assert summary["by_severity"] == {}

    def test_summary_con_patrones(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        recognizer.add_contextual_pattern(snap)
        summary = recognizer.get_pattern_summary()
        assert summary["total_patterns"] == 1
        assert "contextual_anomaly" in summary["by_type"]
        assert "high" in summary["by_severity"] or "medium" in summary["by_severity"]
        assert "avg_compatibility" in summary

    def test_summary_multiple_types(self):
        recognizer = ContextualPatternRecognizer()
        # Anomaly
        snap1 = _make_snapshot(factors={ContextualFactor.SYSTEM_RESOURCES: 0.95})
        recognizer.add_contextual_pattern(snap1)
        # Seasonal (no factors needed, just based on time)
        snap2 = _make_snapshot(factors={}, hour=8)
        recognizer.add_contextual_pattern(snap2)
        summary = recognizer.get_pattern_summary()
        assert summary["total_patterns"] == 2
        assert "contextual_anomaly" in summary["by_type"]
        assert "contextual_seasonal" in summary["by_type"]


class TestExportPatterns:
    def test_export_to_json(self):
        # ContextualFactor enum keys no son JSON-serializables, asi que usamos
        # un snapshot con contextual_factors vacio (JSON-safe) y creamos
        # el patrón manualmente.
        snap = _make_snapshot(factors={}, hour=12)
        pattern = ContextualPattern(
            id="test_pat",
            type=ContextualPatternType.CONTEXTUAL_ANOMALY,
            severity=PatternSeverity.MEDIUM,
            description="test pattern",
            timestamp=datetime.now(),
            confidence=0.8,
            context_snapshot=snap,
            pattern_data={"test": "data"},
            affected_components=["comp"],
            suggested_actions=["action"],
            compatibility_score=0.7,
        )
        recognizer = ContextualPatternRecognizer()
        recognizer.contextual_patterns = [pattern]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            recognizer.export_patterns(tmp_path)
            with open(tmp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert "export_timestamp" in data
            assert "patterns" in data
            assert len(data["patterns"]) == 1
            assert "summary" in data
        finally:
            os.unlink(tmp_path)

    def test_export_empty(self):
        recognizer = ContextualPatternRecognizer()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            recognizer.export_patterns(tmp_path)
            with open(tmp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert len(data["patterns"]) == 0
        finally:
            os.unlink(tmp_path)


class TestDetectContextualPatternChain:
    """Verifica que _detect_contextual_pattern prueba detectores en orden"""

    def test_returns_first_match(self):
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.95}
        snap = _make_snapshot(factors=factors)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_pattern(snap)
        assert result is not None
        # Anomalia es el primer detector
        assert result.type == ContextualPatternType.CONTEXTUAL_ANOMALY

    def test_no_match_returns_none(self):
        # hour=12 fuera de rangos estacionales; 0.3 no dispara burst (>0.4),
        # anomaly (>0.9), trend (>0.8 o <0.1), correlation, changepoint (>0.9 o <0.1)
        factors = {ContextualFactor.SYSTEM_RESOURCES: 0.3}
        snap = _make_snapshot(factors=factors, hour=12)
        recognizer = ContextualPatternRecognizer()
        result = recognizer._detect_contextual_pattern(snap)
        assert result is None
