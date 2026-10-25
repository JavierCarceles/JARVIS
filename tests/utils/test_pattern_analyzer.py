# -*- coding: utf-8 -*-
"""Tests de PatternAnalyzer (src/utils/pattern_analyzer.py)."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import numpy as np
import pytest

from utils.pattern_analyzer import (
    PatternType,
    PatternSeverity,
    Pattern,
    TimeSeriesAnalyzer,
    PatternDetector,
    PatternAnalyzer,
    pattern_detector,
)


# ---------------------------------------------------------------------------
#  Factories
# ---------------------------------------------------------------------------

def _make_log(level="INFO", category="system", module="app", message="",
              timestamp=None):
    """Crear un diccionario de log compatible con PatternDetector."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    return {
        "timestamp": timestamp,
        "level": level,
        "category": category,
        "module": module,
        "message": message,
    }


def _make_pattern(**overrides):
    """Crear una instancia de Pattern con defaults."""
    defaults = dict(
        id="pat_001",
        type=PatternType.ANOMALY,
        severity=PatternSeverity.MEDIUM,
        description="test pattern",
        timestamp=datetime.now(),
        confidence=0.8,
        data={"key": "val"},
        affected_components=["comp"],
        suggested_actions=["act"],
    )
    defaults.update(overrides)
    return Pattern(**defaults)


# ---------------------------------------------------------------------------
#  PatternType / PatternSeverity
# ---------------------------------------------------------------------------

class TestPatternType:
    def test_values(self):
        assert PatternType.ERROR_SPIKE.value == "error_spike"
        assert PatternType.PERFORMANCE_DEGRADATION.value == "performance_degradation"
        assert PatternType.ANOMALY.value == "anomaly"
        assert PatternType.TREND.value == "trend"
        assert PatternType.CYCLE.value == "cycle"
        assert PatternType.CORRELATION.value == "correlation"
        assert PatternType.SEASONAL.value == "seasonal"
        assert PatternType.BURST.value == "burst"
        assert PatternType.CHANGEPONT.value == "changepoint"

    def test_count(self):
        assert len(list(PatternType)) == 9


class TestPatternSeverity:
    def test_values(self):
        assert PatternSeverity.LOW.value == "low"
        assert PatternSeverity.MEDIUM.value == "medium"
        assert PatternSeverity.HIGH.value == "high"
        assert PatternSeverity.CRITICAL.value == "critical"

    def test_count(self):
        assert len(list(PatternSeverity)) == 4


# ---------------------------------------------------------------------------
#  Pattern dataclass
# ---------------------------------------------------------------------------

class TestPatternDataclass:
    def test_campos(self):
        p = _make_pattern()
        assert p.id == "pat_001"
        assert p.type == PatternType.ANOMALY
        assert p.severity == PatternSeverity.MEDIUM
        assert p.is_active is True
        assert p.acknowledged is False

    def test_defaults(self):
        p = Pattern(
            id="pat_002",
            type=PatternType.BURST,
            severity=PatternSeverity.HIGH,
            description="burst",
            timestamp=datetime.now(),
            confidence=0.9,
            data={},
            affected_components=[],
            suggested_actions=[],
        )
        assert p.is_active is True
        assert p.acknowledged is False

    def test_to_dict_serializa_enums(self):
        p = _make_pattern(
            type=PatternType.ERROR_SPIKE,
            severity=PatternSeverity.CRITICAL,
        )
        d = p.to_dict()
        assert d["type"] == "error_spike"
        assert d["severity"] == "critical"
        assert d["timestamp"] is not None  # isoformat string
        assert isinstance(d["timestamp"], str)

    def test_to_dict_serializable_to_json(self):
        """to_dict debe producir algo JSON-serializable."""
        p = _make_pattern()
        d = p.to_dict()
        json.dumps(d)  # no debe lanzar


# ---------------------------------------------------------------------------
#  TimeSeriesAnalyzer
# ---------------------------------------------------------------------------

class TestTimeSeriesAnalyzerInit:
    def test_default_window_size(self):
        tsa = TimeSeriesAnalyzer()
        assert tsa.window_size == 1000

    def test_custom_window_size(self):
        tsa = TimeSeriesAnalyzer(window_size=500)
        assert tsa.window_size == 500

    def test_initial_state(self):
        tsa = TimeSeriesAnalyzer()
        assert tsa.is_trained is False
        assert len(tsa.time_series) == 0


class TestTimeSeriesAnalyzerAddDataPoint:
    def test_add_data_point_basic(self):
        tsa = TimeSeriesAnalyzer()
        tsa.add_data_point("metric1", 10.0)
        assert "metric1" in tsa.time_series
        assert len(tsa.time_series["metric1"]) == 1

    def test_add_data_point_with_timestamp(self):
        ts = datetime.now()
        tsa = TimeSeriesAnalyzer()
        tsa.add_data_point("metric1", 10.0, timestamp=ts)
        point = tsa.time_series["metric1"][0]
        assert point["timestamp"] == ts
        assert point["value"] == 10.0

    def test_add_multiple_points(self):
        tsa = TimeSeriesAnalyzer()
        for i in range(10):
            tsa.add_data_point("m", float(i))
        assert len(tsa.time_series["m"]) == 10

    def test_add_trains_model_at_threshold(self):
        """add_data_point entrena el modelo cuando hay >=100 puntos."""
        tsa = TimeSeriesAnalyzer()
        for i in range(100):
            tsa.add_data_point("m", float(i))
        # is_trained depende de si hay suficientes datos de entrenamiento (>=100 total)
        # Con 100 puntos, _train_model se llama pero training_data len == 100 (>=100)
        assert tsa.is_trained is True


class TestTimeSeriesAnalyzerDetectAnomalies:
    def test_detect_anomalies_insufficient_data(self):
        """detect_anomalies retorna [] cuando hay menos puntos que window_size."""
        tsa = TimeSeriesAnalyzer()
        for i in range(50):
            tsa.add_data_point("m", float(i))
        result = tsa.detect_anomalies("m", window_size=100)
        assert result == []

    def test_detect_anomalies_no_metric(self):
        tsa = TimeSeriesAnalyzer()
        result = tsa.detect_anomalies("nonexistent", window_size=10)
        assert result == []

    def test_detect_anomalies_statistical(self):
        """detect_anomalies encuentra anomalias estadisticas con datos suficientes."""
        tsa = TimeSeriesAnalyzer(window_size=200)
        # 100 valores normales entre 10 y 20, luego un outlier
        for i in range(100):
            tsa.add_data_point("m", 10.0 + np.random.random())
        tsa.add_data_point("m", 100.0)  # outlier
        result = tsa.detect_anomalies("m", window_size=101)
        assert len(result) > 0
        assert result[0]["type"] == "statistical_anomaly"


# ---------------------------------------------------------------------------
#  PatternDetector
# ---------------------------------------------------------------------------

class TestPatternDetectorInit:
    def test_init(self):
        detector = PatternDetector()
        assert detector.time_series_analyzer is not None
        assert detector.patterns == []
        assert isinstance(detector.pattern_history, dict)


class TestDetectErrorSpikes:
    def test_detect_error_spikes(self):
        """detect_error_spikes detecta picos cuando > 30% de errores en ventana."""
        logs = []
        ts = datetime.now()
        for i in range(10):
            logs.append(_make_log(
                level="ERROR" if i < 6 else "INFO",  # 60% > 50%
                timestamp=ts.isoformat(),
            ))
        detector = PatternDetector()
        patterns = detector._detect_error_spikes(logs)
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.ERROR_SPIKE
        assert patterns[0].severity == PatternSeverity.CRITICAL  # 60% > 50%

    def test_no_error_spikes(self):
        logs = []
        ts = datetime.now()
        for i in range(10):
            logs.append(_make_log(level="INFO", timestamp=ts.isoformat()))
        detector = PatternDetector()
        patterns = detector._detect_error_spikes(logs)
        assert len(patterns) == 0

    def test_error_spike_high_severity(self):
        """High severity when 30% < rate <= 50%."""
        logs = []
        ts = datetime.now()
        for i in range(10):
            logs.append(_make_log(
                level="ERROR" if i < 4 else "INFO",  # 40%
                timestamp=ts.isoformat(),
            ))
        detector = PatternDetector()
        patterns = detector._detect_error_spikes(logs)
        assert len(patterns) == 1
        assert patterns[0].severity == PatternSeverity.HIGH


class TestDetectPerformanceDegradation:
    def test_degradation_detected(self):
        """detect_performance_degradation encuentra degradacion con >=10 puntos y 50% aumento."""
        logs = []
        ts = datetime.now()
        for i in range(20):
            time_val = 10.0 if i < 10 else 20.0  # 100% aumento
            logs.append(_make_log(
                level="INFO",
                category="performance",
                module="app",
                message=f"time={time_val}",
                timestamp=ts.isoformat(),
            ))
        detector = PatternDetector()
        patterns = detector._detect_performance_degradation(logs)
        assert len(patterns) >= 1
        assert patterns[0].type == PatternType.PERFORMANCE_DEGRADATION

    def test_no_degradation(self):
        logs = []
        ts = datetime.now()
        for i in range(20):
            logs.append(_make_log(
                level="INFO",
                category="performance",
                module="app",
                message="time=10",
                timestamp=ts.isoformat(),
            ))
        detector = PatternDetector()
        patterns = detector._detect_performance_degradation(logs)
        assert len(patterns) == 0


class TestDetectAnomalies:
    def test_detect_anomalies_no_performance_logs(self):
        """detect_anomalies retorna [] sin logs de rendimiento."""
        detector = PatternDetector()
        logs = [_make_log(level="ERROR", timestamp=datetime.now().isoformat())]
        assert detector._detect_anomalies(logs) == []

    def test_detect_anomalies_insufficient_series(self):
        """Necesita >=50 puntos por metrica para detectar anomalias."""
        detector = PatternDetector()
        logs = []
        for i in range(30):
            logs.append(_make_log(
                category="performance",
                module="app",
                message=f"time={10.0 + i}",
                timestamp=datetime.now().isoformat(),
            ))
        assert detector._detect_anomalies(logs) == []


class TestDetectTrends:
    def test_trend_increasing(self):
        """detect_trends encuentra tendencia creciente con slope > 2 y >=6 horas."""
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        logs = []
        # 6 horas, creciendo de 1 a 25 errores (debe haber al menos 1 por hora)
        for hour in range(6):
            count = 1 + hour * 5  # 1, 6, 11, 16, 21, 26
            for _ in range(count):
                ts = (base + timedelta(hours=hour)).isoformat()
                logs.append(_make_log(level="ERROR", timestamp=ts))
        detector = PatternDetector()
        patterns = detector._detect_trends(logs)
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.TREND
        assert patterns[0].severity == PatternSeverity.MEDIUM

    def test_no_trend_insufficient_hours(self):
        """detect_trends necesita >=6 horas de datos."""
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        logs = []
        for hour in range(3):  # Solo 3 horas
            ts = (base + timedelta(hours=hour)).isoformat()
            logs.append(_make_log(level="ERROR", timestamp=ts))
        detector = PatternDetector()
        patterns = detector._detect_trends(logs)
        assert len(patterns) == 0


class TestDetectCycles:
    def test_no_cycles_insufficient_data(self):
        """detect_cycles necesita >=60 minutos recientes."""
        detector = PatternDetector()
        logs = [_make_log(category="system", timestamp=datetime.now().isoformat())]
        patterns = detector._detect_cycles(logs)
        assert len(patterns) == 0

    def test_detect_periodicity_short_data(self):
        """_detect_periodicity retorna None con menos de 30 puntos."""
        detector = PatternDetector()
        result = detector._detect_periodicity([1, 2, 3])
        assert result is None


class TestDetectCorrelations:
    def test_no_correlations_simple(self):
        detector = PatternDetector()
        logs = [_make_log(category="system", timestamp=datetime.now().isoformat())]
        patterns = detector._detect_correlations(logs)
        assert len(patterns) == 0


class TestDetectBursts:
    def test_detect_burst(self):
        """detect_bursts detecta cuando hay >10 logs/segundo."""
        detector = PatternDetector()
        logs = []
        ts = datetime.now()
        for i in range(15):
            logs.append(_make_log(
                level="INFO",
                timestamp=ts.isoformat(),
            ))
        patterns = detector._detect_bursts(logs)
        assert len(patterns) == 1
        assert patterns[0].type == PatternType.BURST
        assert patterns[0].severity == PatternSeverity.MEDIUM  # 15 <= 50
        assert patterns[0].data["log_count"] == 15

    def test_detect_burst_high_severity(self):
        """High severity when count > 50."""
        detector = PatternDetector()
        logs = []
        ts = datetime.now()
        for i in range(60):
            logs.append(_make_log(timestamp=ts.isoformat()))
        patterns = detector._detect_bursts(logs)
        assert len(patterns) == 1
        assert patterns[0].severity == PatternSeverity.HIGH

    def test_no_burst(self):
        detector = PatternDetector()
        logs = [_make_log(timestamp=datetime.now().isoformat())]
        patterns = detector._detect_bursts(logs)
        assert len(patterns) == 0


class TestPatternDetectorAnalyzeLogs:
    def test_analyze_logs_returns_patterns(self):
        detector = PatternDetector()
        logs = []
        ts = datetime.now()
        for i in range(15):
            logs.append(_make_log(
                level="ERROR" if i < 8 else "INFO",
                timestamp=ts.isoformat(),
                category="system",
            ))
        results = detector.analyze_logs(logs)
        assert len(results) > 0
        # Los patrones se almacenan en detector.patterns
        assert len(detector.patterns) > 0

    def test_analyze_logs_empty(self):
        detector = PatternDetector()
        results = detector.analyze_logs([])
        assert results == []

    def test_analyze_logs_stores_in_history(self):
        detector = PatternDetector()
        logs = []
        ts = datetime.now()
        for i in range(15):
            logs.append(_make_log(
                level="ERROR",
                timestamp=ts.isoformat(),
            ))
        detector.analyze_logs(logs)
        # pattern_history usa defaultdict(list) con keys de pattern.type.value
        assert len(detector.pattern_history) > 0


class TestPatternDetectorQuery:
    def test_get_patterns_by_type(self):
        detector = PatternDetector()
        p = _make_pattern(type=PatternType.BURST)
        detector.patterns.append(p)
        results = detector.get_patterns_by_type(PatternType.BURST)
        assert len(results) == 1
        assert results[0].type == PatternType.BURST

    def test_get_patterns_by_type_limit(self):
        detector = PatternDetector()
        for i in range(10):
            detector.patterns.append(_make_pattern(
                id=f"pat_{i}",
                type=PatternType.BURST,
            ))
        results = detector.get_patterns_by_type(PatternType.BURST, limit=5)
        assert len(results) == 5

    def test_get_active_patterns_excludes_acknowledged(self):
        detector = PatternDetector()
        p1 = _make_pattern(id="p1", is_active=True, acknowledged=False)
        p2 = _make_pattern(id="p2", is_active=True, acknowledged=True)
        detector.patterns = [p1, p2]
        active = detector.get_active_patterns()
        assert len(active) == 1
        assert active[0].id == "p1"

    def test_get_active_patterns_excludes_inactive(self):
        detector = PatternDetector()
        p1 = _make_pattern(id="p1", is_active=True)
        p2 = _make_pattern(id="p2", is_active=False)
        detector.patterns = [p1, p2]
        active = detector.get_active_patterns()
        assert len(active) == 1
        assert active[0].id == "p1"

    def test_acknowledge_pattern(self):
        detector = PatternDetector()
        p = _make_pattern(id="pat_ack")
        detector.patterns.append(p)
        detector.acknowledge_pattern("pat_ack")
        assert p.acknowledged is True

    def test_acknowledge_pattern_not_found(self):
        detector = PatternDetector()
        detector.acknowledge_pattern("nonexistent")
        # No exception, no change

    def test_get_pattern_statistics(self):
        detector = PatternDetector()
        p1 = _make_pattern(id="p1", type=PatternType.ANOMALY, severity=PatternSeverity.HIGH)
        p2 = _make_pattern(id="p2", type=PatternType.BURST, severity=PatternSeverity.MEDIUM)
        detector.patterns = [p1, p2]
        stats = detector.get_pattern_statistics()
        assert stats["total_patterns"] == 2
        assert stats["active_patterns"] == 2
        assert stats["patterns_by_type"][PatternType.ANOMALY.value] == 1
        assert stats["patterns_by_type"][PatternType.BURST.value] == 1
        assert stats["patterns_by_severity"][PatternSeverity.HIGH.value] == 1
        assert stats["patterns_by_severity"][PatternSeverity.MEDIUM.value] == 1

    def test_get_pattern_statistics_empty(self):
        detector = PatternDetector()
        stats = detector.get_pattern_statistics()
        assert stats["total_patterns"] == 0
        assert stats["active_patterns"] == 0


# ---------------------------------------------------------------------------
#  PatternAnalyzer (wrapper)
# ---------------------------------------------------------------------------

class TestPatternAnalyzer:
    def test_init(self):
        analyzer = PatternAnalyzer()
        assert analyzer.detector is not None

    def test_analyze_logs_delegates(self):
        analyzer = PatternAnalyzer()
        logs = []
        ts = datetime.now()
        for i in range(15):
            logs.append(_make_log(level="ERROR", timestamp=ts.isoformat()))
        results = analyzer.analyze_logs(logs)
        assert len(results) > 0

    def test_get_pattern_analysis(self):
        analyzer = PatternAnalyzer()
        p = _make_pattern(id="p1")
        analyzer.detector.patterns.append(p)
        analysis = analyzer.get_pattern_analysis()
        assert "statistics" in analysis
        assert "active_patterns" in analysis
        assert analysis["total_patterns"] == 1
        assert analysis["active_count"] == 1
        assert "patterns_by_type" in analysis
        assert "patterns_by_severity" in analysis
        assert "recent_count" in analysis

    def test_get_patterns_by_type_delegates(self):
        analyzer = PatternAnalyzer()
        p = _make_pattern(type=PatternType.ANOMALY)
        analyzer.detector.patterns.append(p)
        results = analyzer.get_patterns_by_type(PatternType.ANOMALY)
        assert len(results) == 1

    def test_get_active_patterns_delegates(self):
        analyzer = PatternAnalyzer()
        assert analyzer.get_active_patterns() == []

    def test_acknowledge_pattern_delegates(self):
        analyzer = PatternAnalyzer()
        p = _make_pattern(id="ack_pat")
        analyzer.detector.patterns.append(p)
        analyzer.acknowledge_pattern("ack_pat")
        assert p.acknowledged is True

    def test_get_pattern_statistics_delegates(self):
        analyzer = PatternAnalyzer()
        stats = analyzer.get_pattern_statistics()
        assert "total_patterns" in stats


class TestGlobalInstance:
    def test_pattern_detector_instance(self):
        """La instancia global pattern_detector existe y es PatternDetector."""
        assert isinstance(pattern_detector, PatternDetector)
