import sys
sys.path.insert(0, r"C:\Informatica\PROYECTOS\BUGEND".replace("BUGEND", "BACKEND") + r"\IA_PYTHON\IA\JARVIS")

from src.utils.self_improvement_system import SelfImprovementSystem
from src.utils.log_predictor import Prediction, PredictionType, PredictionConfidence
from datetime import datetime, timedelta

sis = SelfImprovementSystem()

# --- Test 1: el caso que fallaba: predictions es LISTA ---
data = sis._collect_system_data()
print("T1 predictions type:", type(data['predictions']).__name__)
assert isinstance(data['predictions'], dict), "predictions debe ser dict"
feats = sis._extract_learning_features(data)
print("T1 features:", len(feats), "->", [round(f, 3) for f in feats])
assert len(feats) == 22

# --- Test 2: predictions lista NO vacia (el caso real del bug) ---
preds = [
    Prediction(id="p1", type=PredictionType.ERROR_RATE, timestamp=datetime.now(),
               predicted_value=0.42, confidence=PredictionConfidence.MEDIUM, confidence_score=0.9, time_horizon=timedelta(minutes=5),
               features={}, model_used="rf", accuracy_metrics={}, suggested_actions=[]),
    Prediction(id="p2", type=PredictionType.RESOURCE_USAGE, timestamp=datetime.now(),
               predicted_value=0.77, confidence=PredictionConfidence.MEDIUM, confidence_score=0.8, time_horizon=timedelta(minutes=5),
               features={}, model_used="rf", accuracy_metrics={}, suggested_actions=[]),
]
summary = sis._summarize_predictions(preds)
print("T2 summary:", summary)
assert summary['error_probability'] == 0.42
assert summary['resource_demand'] == 0.77
assert summary['prediction_count'] == 2

# --- Test 3: shapes hostiles no deben romper ---
hostile = {'performance': [1, 2, 3], 'patterns': None, 'analytics': 'x', 'predictions': preds}
f = sis._extract_learning_features(hostile)
print("T3 features ok:", len(f))
assert len(f) == 22

# --- Test 4: metricas reales mapeadas desde las fuentes ---
perf = sis._flatten_performance(sis.performance_optimizer.get_optimization_status())
ana = sis._flatten_analytics(sis.analytics.get_analytics_summary())
pat = sis._flatten_patterns(sis.pattern_analyzer.get_pattern_analysis())
print("T4 perf:", perf)
print("T4 analytics:", ana)
print("T4 patterns:", pat)
assert 'cpu_usage' in perf and 'error_rate' in perf
assert 'total_logs' in ana and 'info_count' in ana
assert 'anomaly_count' in pat

# --- Test 5: labels y oportunidades no rompen con shapes raros ---
print("T5 labels:", sis._determine_learning_labels(hostile))
print("T5 opportunities:", len(sis._identify_improvement_opportunities(hostile)))

print("\nTODOS LOS TESTS PASARON")


