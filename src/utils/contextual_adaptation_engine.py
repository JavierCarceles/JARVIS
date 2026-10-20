"""Motor de adaptación contextual revisado de JARVIS.

Integra captura/análisis de contexto, reglas de adaptación, transferencia de
conocimiento, validación de Goals y persistencia tolerante con archivos legacy.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import numpy as np
except ImportError:
    class _NP:
        @staticmethod
        def mean(v): return sum(v) / len(v) if v else 0.0
        @staticmethod
        def std(v):
            if not v: return 0.0
            m = sum(v) / len(v)
            return (sum((x-m)**2 for x in v) / len(v))**0.5
    np = _NP()

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
except ImportError:
    RandomForestClassifier = GradientBoostingRegressor = StandardScaler = None

from .advanced_logger import AdvancedLogger
from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy, OptimizationLevel
from .self_improvement_system import SelfImprovementSystem, LearningMode
from .adaptive_learning_engine import AdaptiveLearningEngine, LearningTask, LearningTaskConfig
from .pattern_analyzer import PatternAnalyzer
from .log_analytics import LogAnalytics

try:
    from src.hands.planner.planner import Planner, PlannerStatus
except Exception:
    Planner = PlannerStatus = None


class ContextType(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"
    MAINTENANCE = "maintenance"
    EMERGENCY = "emergency"
    OPTIMIZATION = "optimization"
    LEARNING = "learning"
    IDLE = "idle"
    RECOVERY = "recovery"


class AdaptationLevel(Enum):
    MINIMAL = "minimal"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    RADICAL = "radical"


class ContextualFactor(Enum):
    SYSTEM_RESOURCES = "system_resources"
    USER_BEHAVIOR = "user_behavior"
    ENVIRONMENTAL_CONDITIONS = "environmental_conditions"
    PERFORMANCE_REQUIREMENTS = "performance_requirements"
    ERROR_RATES = "error_rates"
    USAGE_PATTERNS = "usage_patterns"
    TIME_OF_DAY = "time_of_day"
    WORKLOAD = "workload"
    NETWORK_CONDITIONS = "network_conditions"
    HARDWARE_CAPABILITIES = "hardware_capabilities"


@dataclass
class ContextSnapshot:
    snapshot_id: str
    timestamp: datetime
    context_type: ContextType
    contextual_factors: Dict[ContextualFactor, float]
    system_metrics: Dict[str, float]
    performance_metrics: Dict[str, float]
    user_interaction_patterns: Dict[str, float]
    environmental_conditions: Dict[str, float]
    confidence_score: float = 0.0
    adaptation_level: AdaptationLevel = AdaptationLevel.MINIMAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id, "timestamp": self.timestamp.isoformat(),
            "context_type": self.context_type.value,
            "contextual_factors": {getattr(k, "value", str(k)): v for k, v in self.contextual_factors.items()},
            "system_metrics": dict(self.system_metrics), "performance_metrics": dict(self.performance_metrics),
            "user_interaction_patterns": dict(self.user_interaction_patterns),
            "environmental_conditions": dict(self.environmental_conditions),
            "confidence_score": self.confidence_score, "adaptation_level": self.adaptation_level.value,
        }


@dataclass
class AdaptationRule:
    rule_id: str
    name: str
    description: str
    condition_pattern: str
    adaptation_actions: List[str]
    context_triggers: List[ContextType]
    confidence_threshold: float
    priority: int
    enabled: bool = True
    success_rate: float = 0.0
    execution_count: int = 0
    last_execution: Optional[datetime] = None
    adaptation_score: float = 0.0
    constraints: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    deadline: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id, "name": self.name, "description": self.description,
            "condition_pattern": self.condition_pattern, "adaptation_actions": list(self.adaptation_actions),
            "context_triggers": [getattr(c, "value", str(c)) for c in self.context_triggers],
            "confidence_threshold": self.confidence_threshold, "priority": self.priority,
            "enabled": self.enabled, "success_rate": self.success_rate, "execution_count": self.execution_count,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "adaptation_score": self.adaptation_score, "constraints": list(self.constraints),
            "metadata": dict(self.metadata),
            "deadline": self.deadline.isoformat() if isinstance(self.deadline, datetime) else self.deadline,
        }


@dataclass
class KnowledgeTransfer:
    transfer_id: str
    source_context: ContextType
    target_context: ContextType
    knowledge_type: str
    knowledge_data: Dict[str, Any] = field(default_factory=dict)
    transfer_efficiency: float = 0.0
    success_rate: float = 0.0
    last_transfer: Optional[datetime] = None
    transfer_strategy: str = "adaptive"
    confidence_score: float = 0.0
    last_feedback: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"transfer_id": self.transfer_id, "source_context": self.source_context.value,
                "target_context": self.target_context.value, "knowledge_type": self.knowledge_type,
                "knowledge_data": self.knowledge_data, "transfer_efficiency": self.transfer_efficiency,
                "success_rate": self.success_rate, "last_transfer": self.last_transfer.isoformat() if self.last_transfer else None,
                "transfer_strategy": self.transfer_strategy, "confidence_score": self.confidence_score,
                "last_feedback": self.last_feedback.isoformat() if self.last_feedback else None}


class TransferEvaluation(dict):
    """Evaluación de una transferencia.

    Es un `dict` estructurado (claves `success`, `confidence_score`, `feedback_summary`, ...)
    que además se desempaqueta como la tupla ``(is_successful, score, message)``.
    """

    def __iter__(self):
        yield bool(self.get("is_successful", self.get("success", False)))
        yield float(self.get("evaluation_score", 0.0) or 0.0)
        yield str(self.get("message", ""))


@dataclass
class AdaptationResult:
    adaptation_id: str
    context_snapshot: ContextSnapshot
    applied_rules: List[AdaptationRule]
    adaptation_level: AdaptationLevel
    performance_impact: Dict[str, float]
    resource_impact: Dict[str, float]
    confidence_score: float
    execution_time: float
    success: bool
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"adaptation_id": self.adaptation_id, "context_snapshot": self.context_snapshot.to_dict(),
                "applied_rules": [r.to_dict() for r in self.applied_rules],
                "adaptation_level": self.adaptation_level.value, "performance_impact": self.performance_impact,
                "resource_impact": self.resource_impact, "confidence_score": self.confidence_score,
                "execution_time": self.execution_time, "success": self.success, "error_message": self.error_message}


class _AdaptationHistoryEntry(dict):
    """Mantiene compatibilidad con el historial legado que se lee por atributo."""
    def __getattr__(self, name):
        try: return self[name]
        except KeyError as exc: raise AttributeError(name) from exc
    def to_dict(self): return dict(self)


class ContextualAdaptationEngine:
    """Motor de adaptación contextual y transferencia de conocimiento de JARVIS."""

    def __init__(self, config_path: Optional[str] = None, data_dir: Optional[str] = None):
        self.logger = AdvancedLogger("ContextualAdaptationEngine")
        self.performance_optimizer = PerformanceOptimizer()
        self.self_improvement_system = SelfImprovementSystem()
        self.adaptive_learning_engine = AdaptiveLearningEngine()
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        self.meta_learning_system = None
        self.architecture_manager = None
        self.architecture_state: Dict[str, Any] = {}
        self.recent_components: List[Dict[str, Any]] = []
        self.config = self._load_config(config_path)
        self.data_dir = os.path.abspath(data_dir or os.path.join(os.path.dirname(__file__), "..", "..", "data"))
        self.context_snapshots: Dict[str, ContextSnapshot] = {}
        self.adaptation_rules: Dict[str, AdaptationRule] = {}
        self.knowledge_transfers: Dict[str, KnowledgeTransfer] = {}
        self._recorded_confidence: Dict[str, float] = {}
        self.adaptation_history: List[Any] = []
        self.proposals: Dict[str, Dict[str, Any]] = {}
        self.current_context: Optional[ContextSnapshot] = None
        self.adaptation_level = AdaptationLevel.MINIMAL
        self.is_adapting = False
        self.adaptation_queue: queue.Queue = queue.Queue()
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_stop = threading.Event()
        self._lightweight_mode = self._offline_mode = self._performance_mode = False
        self._recovery_mode = self._safe_mode = False
        self.last_integration_timestamp: Optional[datetime] = None
        self.integration_success_rate = 0.0
        self.context_classifier = RandomForestClassifier(n_estimators=100, random_state=42) if RandomForestClassifier else None
        self.adaptation_predictor = GradientBoostingRegressor(random_state=42) if GradientBoostingRegressor else None
        self.scaler = StandardScaler() if StandardScaler else None
        self._initialize_adaptation_rules()
        self._initialize_knowledge_base()
        self.load_adaptation_rules()
        self.load_knowledge_base()
        self._initialize_goal_adaptation_persistence()

    # Configuración
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        config = {"adaptation_enabled": True, "minimal_adaptation_threshold": .3,
                  "moderate_adaptation_threshold": .6, "significant_adaptation_threshold": .8,
                  "radical_adaptation_threshold": .95, "context_analysis_interval": 30.0,
                  "adaptation_execution_timeout": 300.0, "knowledge_transfer_enabled": True,
                  "max_context_snapshots": 1000, "adaptation_rules_file": "data/contextual_adaptation_rules.json",
                  "knowledge_base_file": "data/contextual_knowledge_base.json", "performance_impact_threshold": .1,
                  "confidence_threshold": .7, "max_concurrent_adaptations": 3, "learning_enabled": True,
                  "min_transfer_compatibility": .5, "min_similar_observations": 3}
        if config_path and os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as handle:
                    user_config = json.load(handle)
                if isinstance(user_config, dict): config.update(user_config)
            except Exception as exc: logging.getLogger(__name__).warning("No se pudo leer config %s: %s", config_path, exc)
        return config

    def _resolve_path(self, configured_path: Optional[str], default_name: str) -> str:
        path = Path(configured_path or os.path.join("data", default_name)).expanduser()
        if not path.is_absolute():
            if path.parts and path.parts[0].lower() == "data": path = Path(self.data_dir).joinpath(*path.parts[1:])
            else: path = Path(self.data_dir) / path
        return str(path.resolve())

    def _initialize_adaptation_rules(self) -> None:
        rules = [
            AdaptationRule("rule_001", "Optimización de recursos en alto uso", "Reduce recursos cuando el sistema está sobrecargado", "contextual_factors.system_resources > 0.8", ["reduce_resource_allocation", "optimize_memory_usage", "enable_lightweight_mode"], [ContextType.PRODUCTION, ContextType.EMERGENCY], .8, 1),
            AdaptationRule("rule_002", "Aprendizaje intensivo", "Activa el aprendizaje contextual", "contextual_factors.user_behavior > 0.5", ["enable_learning_mode", "increase_model_training", "collect_feedback"], [ContextType.DEVELOPMENT, ContextType.LEARNING], .7, 2),
            AdaptationRule("rule_003", "Optimización de rendimiento", "Optimiza el rendimiento en periodos de uso elevado", "contextual_factors.performance_requirements < 0.6 and contextual_factors.usage_patterns > 0.5", ["enable_performance_mode", "preload_frequently_used_components", "cache_optimization"], [ContextType.PRODUCTION, ContextType.OPTIMIZATION], .9, 3),
            AdaptationRule("rule_004", "Recuperación ante errores", "Activa recuperación cuando los errores son frecuentes", "performance_metrics.error_rate > 0.1", ["enable_recovery_mode", "isolate_problematic_components", "enable_safe_mode"], [ContextType.EMERGENCY, ContextType.MAINTENANCE], .95, 4),
            AdaptationRule("rule_005", "Adaptación a la red", "Adapta el sistema a condiciones de red variables", "environmental_conditions.stability < 0.5", ["enable_offline_mode", "reduce_data_transfer", "enable_compression"], [ContextType.PRODUCTION, ContextType.EMERGENCY], .8, 2),
        ]
        self.adaptation_rules = {rule.rule_id: rule for rule in rules}

    def _initialize_knowledge_base(self) -> None:
        self.knowledge_base: Dict[str, Any] = {
            "context_patterns": {}, "adaptation_strategies": {}, "goal_adaptation_feedback": [],
            "learning_results": [], "goal_adaptation_proposals": [], "goal_validations": [],
            "performance_baselines": {}, "success_patterns": {}, "failure_patterns": [],
            "transfer_efficiency": {}, "transfer_patterns": {}, "applied_patterns": [],
            "applied_strategies": [], "applied_baselines": {}, "batch_transfer_summary": [],
            "auto_transfer_stats": [], "transfer_recommendations": [], "integration_records": [],
            "global_confidence_metrics": {"total_feedback": 0, "successful_transfers": 0,
                "average_feedback_score": 0.0, "confidence_trend": []},
        }
        for ctx in ContextType:
            for key, default in (("context_patterns", []), ("success_patterns", []),
                                 ("performance_baselines", {}), ("adaptation_strategies", [])):
                self.knowledge_base[key].setdefault(ctx.value, default.copy())

    # Captura y análisis contextual
    def capture_context_snapshot(self) -> ContextSnapshot:
        now = datetime.now()
        sid = f"snapshot_{int(time.time() * 1000)}_{len(self.context_snapshots)}"
        system = self._collect_system_metrics()
        performance = self._collect_performance_metrics()
        user = self._collect_user_patterns()
        environment = self._collect_environmental_conditions()
        kind = self._determine_context_type(system, performance, user)
        factors = self._evaluate_contextual_factors(system, performance, user, environment)
        confidence = self._calculate_context_confidence(factors, system, performance)
        snapshot = ContextSnapshot(sid, now, kind, factors, system, performance, user, environment, confidence)
        self.context_snapshots[sid] = snapshot
        limit = max(1, int(self.config.get("max_context_snapshots", 1000)))
        while len(self.context_snapshots) > limit:
            oldest = min(self.context_snapshots, key=lambda key: self.context_snapshots[key].timestamp)
            del self.context_snapshots[oldest]
        self._record_context_pattern(snapshot)
        return snapshot

    def _collect_system_metrics(self) -> Dict[str, float]:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=.1) / 100.0
            memory = psutil.virtual_memory().percent / 100.0
            disk = psutil.disk_usage(os.path.abspath(os.sep)).percent / 100.0
            net = psutil.net_io_counters()
            return {"cpu_usage": cpu, "memory_usage": memory, "disk_usage": disk,
                    "process_count": float(len(psutil.pids())), "network_bytes_sent": float(net.bytes_sent),
                    "network_bytes_recv": float(net.bytes_recv), "system_load": cpu*.4 + memory*.4 + disk*.2}
        except Exception as exc:
            self.logger.warning("Error recogiendo métricas del sistema: %s", exc)
            return {"cpu_usage": 0., "memory_usage": 0., "disk_usage": 0., "process_count": 0.,
                    "network_bytes_sent": 0., "network_bytes_recv": 0., "system_load": 0.}

    def _collect_performance_metrics(self) -> Dict[str, float]:
        try:
            status = self.performance_optimizer.get_optimization_status() or {}
            current = status.get("current_metrics", {}) or {}
            errors = self._bounded_float(current.get("error_rate", 0.), 0., 1.)
            return {"response_time": self._safe_float(current.get("response_time", 0.)),
                    "throughput": self._safe_float(current.get("throughput", 0.)), "error_rate": errors,
                    "success_rate": 1. - errors,
                    "cpu_efficiency": max(0., 100. - self._safe_float(current.get("cpu_usage", 0.))) / 100.,
                    "memory_efficiency": max(0., 100. - self._safe_float(current.get("memory_usage", 0.))) / 100.,
                    "overall_efficiency": self._safe_float(current.get("efficiency_score", 0.)) / 100.}
        except Exception as exc:
            self.logger.warning("Error recogiendo métricas de rendimiento: %s", exc)
            return {"response_time": 0., "throughput": 0., "error_rate": 0., "success_rate": 1.,
                    "cpu_efficiency": 0., "memory_efficiency": 0., "overall_efficiency": 0.}

    def _collect_user_patterns(self) -> Dict[str, float]:
        try:
            status = self.self_improvement_system.get_learning_status() or {}
            efficiency = self._bounded_float(self._safe_float(status.get("efficiency_score", 0.)) / 100., 0., 1.)
            gain = self._bounded_float(self._safe_float(status.get("optimization_gain", 0.)) / 100., 0., 1.)
            rules = self._safe_float(status.get("active_rules", 0))
            return {"learning_requests": efficiency, "optimization_requests": gain, "error_reports": 0.,
                    "feature_requests": 0., "interaction_frequency": min(1., rules / 50.),
                    "session_duration": self._safe_float(status.get("total_sessions", 0)),
                    "user_satisfaction": efficiency}
        except Exception as exc:
            self.logger.warning("Error recogiendo patrones de usuario: %s", exc)
            return {key: 0. for key in ("learning_requests", "optimization_requests", "error_reports",
                                       "feature_requests", "interaction_frequency", "session_duration", "user_satisfaction")}

    def _collect_environmental_conditions(self) -> Dict[str, float]:
        import platform
        hour = datetime.now().hour
        try:
            import psutil
            net = psutil.net_io_counters()
            activity = min(1., (net.bytes_sent + net.bytes_recv) / (100 * 1024 * 1024))
        except Exception:
            activity = 0.
        return {"time_of_day": float(hour), "is_business_hours": float(9 <= hour <= 17),
                "os_info": float(sum(map(ord, platform.system())) % 100) / 100., "os_version": .5,
                "latency": .3, "bandwidth": 50., "stability": .85, "packet_loss": .02,
                "network_activity": activity}

    def _determine_context_type(self, system_metrics, performance_metrics, user_patterns) -> ContextType:
        errors = performance_metrics.get("error_rate", 0.)
        if errors > .2 or self._recovery_mode: return ContextType.EMERGENCY
        if system_metrics.get("cpu_usage", 0.) > .8 or system_metrics.get("memory_usage", 0.) > .8: return ContextType.PRODUCTION
        if errors > .05: return ContextType.MAINTENANCE
        learning = user_patterns.get("learning_requests", 0.)
        if learning > .7: return ContextType.LEARNING
        if learning > .3: return ContextType.DEVELOPMENT
        if self._performance_mode: return ContextType.OPTIMIZATION
        return ContextType.IDLE

    def _evaluate_contextual_factors(self, system, performance, user, environment) -> Dict[ContextualFactor, float]:
        cpu, memory, disk = (system.get(k, 0.) for k in ("cpu_usage", "memory_usage", "disk_usage"))
        errors = performance.get("error_rate", 0.)
        return {
            ContextualFactor.SYSTEM_RESOURCES: self._bounded_float(cpu*.4 + memory*.4 + disk*.2, 0., 1.),
            ContextualFactor.ERROR_RATES: self._bounded_float(errors, 0., 1.),
            ContextualFactor.USER_BEHAVIOR: self._bounded_float(user.get("learning_requests", 0.)*.3 + user.get("optimization_requests", 0.)*.3 + user.get("interaction_frequency", 0.)*.4, 0., 1.),
            ContextualFactor.PERFORMANCE_REQUIREMENTS: self._bounded_float(performance.get("response_time", 0.)*.3 + (1.-errors)*.4 + performance.get("overall_efficiency", 0.)*.3, 0., 1.),
            ContextualFactor.ENVIRONMENTAL_CONDITIONS: self._bounded_float(environment.get("latency", .5)*.3 + environment.get("stability", .7)*.4 + environment.get("bandwidth", 50.)/100.*.3, 0., 1.),
            ContextualFactor.WORKLOAD: min(1., system.get("process_count", 0.)/200.*.5 + user.get("interaction_frequency", 0.)*.5),
            ContextualFactor.NETWORK_CONDITIONS: self._bounded_float((1.-environment.get("packet_loss", .02))*.5 + environment.get("stability", .85)*.5, 0., 1.),
            ContextualFactor.TIME_OF_DAY: self._bounded_float(environment.get("time_of_day", 12.)/24., 0., 1.),
            ContextualFactor.USAGE_PATTERNS: self._bounded_float(user.get("interaction_frequency", 0.), 0., 1.),
            ContextualFactor.HARDWARE_CAPABILITIES: self._bounded_float(1.-system.get("system_load", 0.), 0., 1.),
        }

    def _calculate_context_confidence(self, factors, system, performance) -> float:
        resource = 1. - abs(factors.get(ContextualFactor.SYSTEM_RESOURCES, .5) - system.get("system_load", .5))
        perf = 1. - abs(performance.get("success_rate", .5) - (1. - performance.get("error_rate", .5)))
        average = float(np.mean(list(factors.values()))) if factors else .5
        return self._bounded_float(resource*.4 + perf*.4 + average*.2, 0., 1.)

    def _record_context_pattern(self, snapshot: ContextSnapshot) -> None:
        patterns = self.knowledge_base.setdefault("context_patterns", {}).setdefault(snapshot.context_type.value, [])
        patterns.append({"timestamp": snapshot.timestamp.isoformat(), "confidence": snapshot.confidence_score,
                         "factors": {f.value: v for f, v in snapshot.contextual_factors.items()},
                         "metrics": {"cpu_usage": snapshot.system_metrics.get("cpu_usage", 0.),
                                     "memory_usage": snapshot.system_metrics.get("memory_usage", 0.),
                                     "error_rate": snapshot.performance_metrics.get("error_rate", 0.)}})
        del patterns[:-50]

    def analyze_contextual_patterns(self, snapshot: ContextSnapshot) -> List[AdaptationRule]:
        rules = [rule for rule in self.adaptation_rules.values() if rule.enabled and
                 (not rule.context_triggers or snapshot.context_type in rule.context_triggers) and
                 self._evaluate_rule_condition(rule, snapshot)]
        return sorted(rules, key=lambda r: r.priority, reverse=True)

    def _evaluate_rule_condition(self, rule: AdaptationRule, snapshot: ContextSnapshot) -> bool:
        try:
            parts = [p.strip() for p in (rule.condition_pattern or "").replace(" and ", "|").split("|") if p.strip()]
            for token in parts:
                for op in (">=", "<=", "==", "!=", ">", "<"):
                    if op in token:
                        left, right = (x.strip() for x in token.split(op, 1))
                        lv, rv = self._get_contextual_value(left, snapshot), self._parse_value(right)
                        passed = {">": lv > rv, "<": lv < rv, ">=": lv >= rv, "<=": lv <= rv, "==": lv == rv, "!=": lv != rv}[op]
                        if not passed: return False
                        break
                else:
                    # Condición no reconocida: no se aplica por seguridad.
                    return False
            return snapshot.confidence_score >= rule.confidence_threshold
        except Exception as exc:
            self.logger.error("Error evaluando regla %s: %s", rule.rule_id, exc)
            return False

    def _get_contextual_value(self, key: str, snapshot: ContextSnapshot) -> float:
        mappings = {"contextual_factors": {k.value: v for k, v in snapshot.contextual_factors.items()},
                    "system_metrics": snapshot.system_metrics, "performance_metrics": snapshot.performance_metrics,
                    "user_interaction_patterns": snapshot.user_interaction_patterns,
                    "environmental_conditions": snapshot.environmental_conditions}
        for prefix, data in mappings.items():
            if key.startswith(prefix + "."): return self._safe_float(data.get(key[len(prefix)+1:], 0.))
        if key == "context_type": return float(snapshot.context_type == ContextType.DEVELOPMENT)
        return 0.

    @staticmethod
    def _parse_value(value: str) -> float:
        if value.strip().lower() == "true": return 1.
        if value.strip().lower() == "false": return 0.
        try: return float(value.strip())
        except (ValueError, TypeError): return 0.

    # Ejecución de adaptaciones
    def execute_adaptation(self, snapshot: ContextSnapshot, rules: List[AdaptationRule]) -> AdaptationResult:
        adaptation_id = f"adaptation_{int(time.time()*1000)}_{len(self.adaptation_history)}"
        started = time.time(); self.is_adapting = True
        applied, performance, resources, errors = [], {}, {}, []
        try:
            level = self._determine_adaptation_level(rules)
            for rule in rules or []:
                succeeded = True
                try:
                    action_result = self._execute_adaptation_actions(rule, snapshot)
                    applied.append(rule); performance.update(action_result["performance_impact"]); resources.update(action_result["resource_impact"])
                except Exception as exc:
                    succeeded = False; errors.append(f"{rule.rule_id}: {exc}"); self.logger.error("Error ejecutando regla %s: %s", rule.rule_id, exc)
                rule.execution_count += 1; rule.last_execution = datetime.now(); rule.success_rate = self._update_rule_success_rate(rule, succeeded)
            performance = self._calculate_overall_impact(performance); resources = self._calculate_overall_impact(resources)
            confidence = self._calculate_adaptation_confidence(applied, snapshot, performance)
            self._record_adaptation_result(adaptation_id, snapshot, applied, confidence)
            result = AdaptationResult(adaptation_id, snapshot, applied, level, performance, resources, confidence, time.time()-started, not errors, "; ".join(errors) if errors else None)
            self.adaptation_history.append(result); self.current_context = snapshot; self.adaptation_level = level
            return result
        except Exception as exc:
            self.logger.exception("Error durante adaptación %s", adaptation_id)
            result = AdaptationResult(adaptation_id, snapshot, [], AdaptationLevel.MINIMAL, {}, {}, 0., time.time()-started, False, str(exc))
            self.adaptation_history.append(result); return result
        finally: self.is_adapting = False

    @staticmethod
    def _determine_adaptation_level(rules: List[AdaptationRule]) -> AdaptationLevel:
        if not rules: return AdaptationLevel.MINIMAL
        average = sum(r.priority for r in rules)/len(rules)
        if average >= 4: return AdaptationLevel.RADICAL
        if average >= 3: return AdaptationLevel.SIGNIFICANT
        if average >= 2: return AdaptationLevel.MODERATE
        return AdaptationLevel.MINIMAL

    def _execute_adaptation_actions(self, rule: AdaptationRule, snapshot: ContextSnapshot) -> Dict[str, Any]:
        result = {"performance_impact": {}, "resource_impact": {}, "actions_executed": []}
        for action in rule.adaptation_actions:
            item = self._execute_single_action(action, snapshot)
            result["actions_executed"].append(action); result["performance_impact"].update(item["performance_impact"]); result["resource_impact"].update(item["resource_impact"])
        return result

    def _execute_single_action(self, action: str, snapshot: ContextSnapshot) -> Dict[str, Any]:
        result = {"performance_impact": {}, "resource_impact": {}}
        if action == "reduce_resource_allocation":
            self.performance_optimizer.optimize_system(OptimizationStrategy.RESOURCE_ALLOCATION, OptimizationLevel.AGGRESSIVE); result["resource_impact"].update(cpu_reduction=.2, memory_reduction=.15); result["performance_impact"]["response_time_increase"] = .1
        elif action == "optimize_memory_usage":
            self.performance_optimizer.optimize_system(OptimizationStrategy.MEMORY_OPTIMIZATION, OptimizationLevel.MODERATE); result["resource_impact"]["memory_optimization"] = .25; result["performance_impact"]["memory_efficiency_improvement"] = .3
        elif action == "enable_lightweight_mode": self._lightweight_mode = True; self._set_optimization_interval(120); result["resource_impact"]["resource_saving"] = .3
        elif action == "enable_learning_mode": self.self_improvement_system.enable_learning_mode(LearningMode.ACTIVE_LEARNING); self.adaptive_learning_engine.start_learning_engine(); result["performance_impact"]["learning_speed_increase"] = .4
        elif action == "increase_model_training":
            task = LearningTaskConfig(task_id=f"train_{int(time.time()*1000)}", task_type=LearningTask.MODEL_TRAINING, model_name="random_forest", hyperparameters={"n_estimators": 200}, max_epochs=50); self.adaptive_learning_engine.add_learning_task(task); result["resource_impact"]["training_resource_increase"] = .4
        elif action == "collect_feedback":
            patterns = self.pattern_analyzer.get_pattern_analysis() or {}; result["performance_impact"]["feedback_quality"] = min(.5, self._safe_float(patterns.get("anomaly_count", 0))*.05)
        elif action == "enable_performance_mode":
            self._performance_mode = True; self._set_optimization_interval(30); self.performance_optimizer.optimize_system(OptimizationStrategy.CPU_OPTIMIZATION, OptimizationLevel.AGGRESSIVE); result["performance_impact"]["response_time_improvement"] = .4
        elif action == "preload_frequently_used_components":
            status = self._call_optional(self.adaptive_learning_engine, "get_learning_engine_status", default={}) or {}; best = status.get("best_model") if isinstance(status, dict) else None; result["performance_impact"]["loading_time_reduction"] = .3; result["performance_impact"]["best_model"] = best.get("model_name", "none") if isinstance(best, dict) else "none"
        elif action == "cache_optimization": self.performance_optimizer.optimize_system(OptimizationStrategy.CACHE_OPTIMIZATION, OptimizationLevel.MODERATE); result["performance_impact"]["cache_hit_rate_improvement"] = .4
        elif action == "enable_recovery_mode": self._recovery_mode = True; self.performance_optimizer.optimize_system(OptimizationStrategy.PROCESS_OPTIMIZATION, OptimizationLevel.CRITICAL); result["performance_impact"]["recovery_speed_improvement"] = .5
        elif action == "isolate_problematic_components": self.pattern_analyzer.get_pattern_analysis(); result["performance_impact"]["system_stability_improvement"] = .3
        elif action == "enable_safe_mode": self._safe_mode = True; result["performance_impact"]["safety_improvement"] = .6
        elif action == "enable_offline_mode": self._offline_mode = True; result["performance_impact"]["offline_capability"] = .5
        elif action == "reduce_data_transfer": self._reduce_data_transfer_real(); result["performance_impact"]["data_transfer_reduction"] = .3
        elif action == "enable_compression": result["performance_impact"]["compression_ratio_improvement"] = .3
        else: raise ValueError(f"Acción de adaptación desconocida: {action}")
        return result

    def _set_optimization_interval(self, interval: int) -> None:
        try:
            config = getattr(self.performance_optimizer, "config", None)
            if isinstance(config, dict): config["optimization_interval"] = max(1, int(interval))
        except Exception as exc: self.logger.warning("No se pudo actualizar intervalo: %s", exc)

    def _reduce_data_transfer_real(self) -> None:
        try: self.analytics.get_analytics_summary()
        except Exception as exc: self.logger.warning("Error al consultar analíticas: %s", exc)

    @staticmethod
    def _update_rule_success_rate(rule: AdaptationRule, success: bool) -> float:
        if rule.execution_count <= 1: return 1. if success else 0.
        return .1*float(success) + .9*rule.success_rate

    @staticmethod
    def _calculate_overall_impact(data: Dict[str, float]) -> Dict[str, float]:
        """Normalizar el signo de los impactos sin confundir aumentos buenos y malos."""
        output: Dict[str, float] = {}
        negative_tokens = (
            "reduction", "decrease", "increase_time", "time_increase", "latency_increase",
            "response_time_increase", "throughput_reduction", "resource_increase", "overhead",
            "cost_increase", "error_increase",
        )
        positive_tokens = ("improvement", "optimization", "saving", "reduction_saving")
        for key, raw in (data or {}).items():
            value = ContextualAdaptationEngine._safe_float(raw)
            lowered = str(key).lower()
            if any(token in lowered for token in negative_tokens):
                output[key] = -abs(value)
            elif any(token in lowered for token in positive_tokens):
                output[key] = abs(value)
            else:
                output[key] = value
        return output

    def _calculate_adaptation_confidence(self, rules: List[AdaptationRule], snapshot: ContextSnapshot, impact: Dict[str, float]) -> float:
        if not rules: return 0.
        rule_score = sum(self._bounded_float(r.success_rate, 0., 1.) for r in rules)/len(rules)
        impact_score = min(1., abs(float(np.mean(list(impact.values()))))) if impact else .5
        return self._bounded_float(rule_score*.3 + snapshot.confidence_score*.4 + impact_score*.3, 0., 1.)

    def _record_adaptation_result(self, adaptation_id: str, snapshot: ContextSnapshot, rules: List[AdaptationRule], confidence: float) -> None:
        entries = self.knowledge_base.setdefault("adaptation_strategies", {}).setdefault(snapshot.context_type.value, [])
        entries.append({"adaptation_id": adaptation_id, "timestamp": snapshot.timestamp.isoformat(), "applied_rules": [r.rule_id for r in rules], "confidence": confidence}); del entries[:-50]

    # Transferencia de conocimiento: aquí cada método tiene una única definición.
    def transfer_knowledge(self, source_context: ContextType, target_context: ContextType,
                          knowledge_type: str, transfer_strategy: str = "adaptive",
                          include_patterns: bool = True, include_strategies: bool = True,
                          include_baselines: bool = True, include_metrics: bool = True) -> Optional[KnowledgeTransfer]:
        if not self.config.get("knowledge_transfer_enabled", True): return None
        source, target = self._coerce_context(source_context), self._coerce_context(target_context)
        if source is None or target is None or not knowledge_type or source == target: return None
        strategy = transfer_strategy if transfer_strategy in ("adaptive", "conservative", "aggressive") else "adaptive"
        compatibility = self._validate_context_compatibility(source, target)
        min_compatibility = self.config.get("min_transfer_compatibility", .5)
        try: min_compatibility = float(min_compatibility)
        except (TypeError, ValueError): min_compatibility = .5
        if compatibility < min_compatibility:
            self.logger.warning("Compatibilidad baja en transferencia %s -> %s (%.2f)", source.value, target.value, compatibility)
            return None
        try:
            data: Dict[str, Any] = {}
            # Tipos concretos transfieren ese conocimiento; los alias compuestos permiten incluir varios.
            if knowledge_type in ("success_patterns", "all", "contextual_knowledge") and include_patterns:
                data["success_patterns"] = self._filter_patterns_by_compatibility(self.knowledge_base.get("success_patterns", {}).get(source.value, []), target, strategy)
            if knowledge_type in ("adaptation_strategies", "success_patterns", "all", "contextual_knowledge") and include_strategies:
                data["successful_strategies"] = self._filter_strategies_by_compatibility(self.knowledge_base.get("adaptation_strategies", {}).get(source.value, []), target, strategy)
            if knowledge_type in ("performance_baselines", "success_patterns", "all", "contextual_knowledge") and include_baselines:
                baselines = self.knowledge_base.get("performance_baselines", {}).get(source.value, {})
                data["performance_baselines"] = self._adapt_baselines_to_context(baselines, source, target) if isinstance(baselines, dict) else {}
            if knowledge_type in ("contextual_metrics", "all", "contextual_knowledge") and include_metrics:
                data["contextual_metrics"] = self._extract_relevant_metrics(source)
            if not data:
                extracted = self._extract_knowledge_from_context(source, knowledge_type)
                if isinstance(extracted, dict): data.update(extracted)
                elif extracted: data[knowledge_type] = extracted
            if not data: return None
            transformed = self._transform_knowledge_for_target(data, source, target, strategy)
            efficiency = self._calculate_transfer_efficiency_with_strategy(source, target, knowledge_type, strategy)
            transfer_id = f"transfer_{int(time.time()*1000)}_{len(self.knowledge_transfers)}"
            transfer = KnowledgeTransfer(transfer_id, source, target, knowledge_type, transformed, efficiency,
                                         efficiency, datetime.now(), strategy, efficiency)
            self.knowledge_transfers[transfer_id] = transfer
            self._update_transfer_patterns(transfer)
            return transfer
        except Exception as exc:
            self.logger.exception("Error transfiriendo conocimiento: %s", exc)
            return None

    def _extract_knowledge_from_context(self, context: ContextType, knowledge_type: str) -> Dict[str, Any]:
        ctx = self._coerce_context(context)
        if ctx is None: return {}
        value = ctx.value
        if knowledge_type == "success_patterns": return {"success_patterns": copy.deepcopy(self.knowledge_base.get("success_patterns", {}).get(value, []))}
        if knowledge_type == "adaptation_strategies": return {"adaptation_strategies": copy.deepcopy(self.knowledge_base.get("adaptation_strategies", {}).get(value, []))}
        if knowledge_type == "performance_baselines": return {"performance_baselines": copy.deepcopy(self.knowledge_base.get("performance_baselines", {}).get(value, {}))}
        if knowledge_type == "contextual_metrics": return {"contextual_metrics": self._extract_contextual_metrics(ctx)}
        base = self.knowledge_base.get(knowledge_type, {})
        return {knowledge_type: copy.deepcopy(base.get(value, base) if isinstance(base, dict) else base)}

    def _extract_contextual_metrics(self, context: ContextType) -> Dict[str, Any]:
        ctx = self._coerce_context(context)
        snapshots = [s for s in self.context_snapshots.values() if s.context_type == ctx]
        output: Dict[str, Any] = {"context_type": ctx.value, "snapshot_count": len(snapshots), "timestamp": datetime.now().isoformat()}
        for group, attr in (("system", "system_metrics"), ("performance", "performance_metrics")):
            recent = [getattr(s, attr) for s in snapshots[-10:]]
            keys = set().union(*(d.keys() for d in recent)) if recent else set()
            for key in keys:
                vals = [self._safe_float(d[key]) for d in recent if isinstance(d.get(key), (int, float))]
                if vals:
                    output[f"{group}_{key}_avg"] = float(np.mean(vals))
                    output[f"{group}_{key}_min"] = min(vals)
                    output[f"{group}_{key}_max"] = max(vals)
        return output

    def _extract_relevant_metrics(self, context: ContextType) -> Dict[str, Any]:
        return self._extract_contextual_metrics(context)

    def _validate_context_compatibility(self, source_context: ContextType, target_context: ContextType) -> float:
        source, target = self._coerce_context(source_context), self._coerce_context(target_context)
        if source is None or target is None or source == target: return 0.
        base = {
            (ContextType.DEVELOPMENT, ContextType.LEARNING): .95,
            (ContextType.DEVELOPMENT, ContextType.TESTING): .85,
            (ContextType.DEVELOPMENT, ContextType.PRODUCTION): .60,
            (ContextType.DEVELOPMENT, ContextType.EMERGENCY): .40,
            (ContextType.PRODUCTION, ContextType.OPTIMIZATION): .90,
            (ContextType.PRODUCTION, ContextType.MAINTENANCE): .75,
            (ContextType.PRODUCTION, ContextType.TESTING): .70,
            (ContextType.LEARNING, ContextType.DEVELOPMENT): .90,
            (ContextType.LEARNING, ContextType.PRODUCTION): .50,
            (ContextType.TESTING, ContextType.PRODUCTION): .70,
            (ContextType.TESTING, ContextType.MAINTENANCE): .70,
            (ContextType.MAINTENANCE, ContextType.EMERGENCY): .80,
            (ContextType.EMERGENCY, ContextType.RECOVERY): .85,
            (ContextType.EMERGENCY, ContextType.PRODUCTION): .40,
            (ContextType.IDLE, ContextType.DEVELOPMENT): .60,
            (ContextType.IDLE, ContextType.LEARNING): .65,
            (ContextType.OPTIMIZATION, ContextType.PRODUCTION): .90,
        }.get((source, target), .5)
        similarity = self._calculate_factor_similarity(source, target)
        if self._has_transfer_history(source, target):
            historic = self._get_historical_compatibility(source, target)
            value = base*.85 + historic*.10 + similarity*.05
        else:
            value = base*.9 + similarity*.1
        return self._bounded_float(value, 0., 1.)

    def _has_transfer_history(self, source: ContextType, target: ContextType) -> bool:
        return any(t.source_context == source and t.target_context == target for t in self.knowledge_transfers.values())

    def _get_historical_compatibility(self, source: ContextType, target: ContextType, use_fallback: bool = True) -> float:
        values = [t.transfer_efficiency for t in self.knowledge_transfers.values() if t.source_context == source and t.target_context == target]
        if not values:
            records = self.knowledge_base.get("transfer_efficiency", {}).get(f"{source.value}->{target.value}", [])
            if isinstance(records, list): values = [self._safe_float(x.get("efficiency", 0.)) for x in records if isinstance(x, dict) and "efficiency" in x]
        return self._bounded_float(float(np.mean(values)), 0., 1.) if values else (.5 if use_fallback else .5)

    def _calculate_factor_similarity(self, source: ContextType, target: ContextType) -> float:
        source_rows = self.knowledge_base.get("context_patterns", {}).get(source.value, [])
        target_rows = self.knowledge_base.get("context_patterns", {}).get(target.value, [])
        if source_rows and target_rows:
            a, b = source_rows[-1].get("factors", {}), target_rows[-1].get("factors", {})
            common = set(a) & set(b)
            if common: return self._bounded_float(float(np.mean([1.-min(1., abs(self._safe_float(a[k])-self._safe_float(b[k]))) for k in common])), 0., 1.)
        source_snapshots = [s for s in self.context_snapshots.values() if s.context_type == source]
        target_snapshots = [s for s in self.context_snapshots.values() if s.context_type == target]
        if not source_snapshots or not target_snapshots: return .5
        a = max(source_snapshots, key=lambda s: s.timestamp); b = max(target_snapshots, key=lambda s: s.timestamp)
        return self._bounded_float(float(np.mean([1.-min(1., abs(a.contextual_factors.get(f, 0.)-b.contextual_factors.get(f, 0.))) for f in ContextualFactor])), 0., 1.)

    def _calculate_transfer_efficiency(self, source_context: ContextType, target_context: ContextType,
                                       knowledge_type: str, transfer_strategy: str) -> float:
        return self._calculate_transfer_efficiency_with_strategy(source_context, target_context, knowledge_type, transfer_strategy)

    def _calculate_transfer_efficiency_with_strategy(self, source_context: Any, target_context: Optional[ContextType] = None,
                                                     knowledge_type: Optional[str] = None, transfer_strategy: Optional[str] = None) -> float:
        if isinstance(source_context, KnowledgeTransfer):
            transfer = source_context; source_context = transfer.source_context
            target_context = target_context or transfer.target_context; knowledge_type = knowledge_type or transfer.knowledge_type
            transfer_strategy = transfer_strategy or transfer.transfer_strategy
        source, target = self._coerce_context(source_context), self._coerce_context(target_context)
        if source is None or target is None: return 0.
        compatibility = self._validate_context_compatibility(source, target)
        strategy_factor = {"conservative": .95, "adaptive": 1., "aggressive": .9}.get(transfer_strategy, 1.)
        type_factor = {"success_patterns": 1., "adaptation_strategies": .9, "performance_baselines": .85, "contextual_metrics": .9}.get(knowledge_type, .8)
        historical = self._get_historical_compatibility(source, target)
        base = compatibility*.7 + historical*.3 if self._has_transfer_history(source, target) else compatibility
        return self._bounded_float(base*strategy_factor*type_factor, 0., 1.)

    def _get_context_adjustment_factor(self, source: ContextType, target: ContextType) -> float:
        return {(ContextType.DEVELOPMENT, ContextType.PRODUCTION): 1.2,
                (ContextType.DEVELOPMENT, ContextType.LEARNING): .9,
                (ContextType.PRODUCTION, ContextType.TESTING): .8,
                (ContextType.PRODUCTION, ContextType.MAINTENANCE): .7,
                (ContextType.LEARNING, ContextType.DEVELOPMENT): 1.1,
                (ContextType.TESTING, ContextType.PRODUCTION): 1.3,
                (ContextType.MAINTENANCE, ContextType.EMERGENCY): 1.4}.get((source, target), 1.)

    def _adapt_baselines_to_context(self, baselines: Dict[str, Any], source_context: ContextType, target_context: ContextType) -> Dict[str, Any]:
        compatibility = self._validate_context_compatibility(source_context, target_context)
        factor = 1. if compatibility >= .8 else 1.05 if compatibility >= .6 else self._get_context_adjustment_factor(source_context, target_context)
        output: Dict[str, Any] = {}
        for key, value in (baselines or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                output[f"{key}_adapted"] = value*factor; output[f"{key}_original"] = value; output[f"{key}_adjustment"] = factor
            else: output[key] = copy.deepcopy(value)
        output["adaptation_metadata"] = {"source_context": source_context.value, "target_context": target_context.value,
                                         "compatibility": compatibility, "adaptation_timestamp": datetime.now().isoformat()}
        return output

    def _get_context_knowledge_amount(self, context: ContextType) -> int:
        ctx = self._coerce_context(context)
        if ctx is None:
            return 0
        key = ctx.value
        return (
            len(self.knowledge_base.get("success_patterns", {}).get(key, []) or [])
            + len(self.knowledge_base.get("adaptation_strategies", {}).get(key, []) or [])
            + len(self.knowledge_base.get("performance_baselines", {}).get(key, {}) or {})
        )

    def _calculate_transfer_potential(self, source_context: ContextType, target_context: ContextType) -> float:
        source, target = self._coerce_context(source_context), self._coerce_context(target_context)
        if source is None or target is None or source == target:
            return 0.0
        compatibility = self._validate_context_compatibility(source, target)
        historical = self._get_historical_compatibility(source, target, use_fallback=False)
        similarity = self._calculate_factor_similarity(source, target)
        source_n, target_n = self._get_context_knowledge_amount(source), self._get_context_knowledge_amount(target)
        available = min(1., source_n/20.) if source_n else .25
        need = max(0., 1.-min(1., target_n/20.))
        return self._bounded_float(compatibility*.4 + historical*.2 + similarity*.2 + available*.1 + need*.1, 0., 1.)

    def _filter_patterns_by_compatibility(self, patterns: List[Dict[str, Any]], target_context: ContextType, strategy: str) -> List[Dict[str, Any]]:
        modifier = {"adaptive": 1., "conservative": .8, "aggressive": 1.1}.get(strategy, 1.)
        output = []
        for pattern in patterns or []:
            if not isinstance(pattern, dict): continue
            score = self._bounded_float(self._safe_float(pattern.get("confidence", .5))*modifier, 0., 1.)
            if score >= .1:
                item = copy.deepcopy(pattern); item["transfer_compatibility"] = score; item["transfer_strategy"] = strategy; output.append(item)
        return sorted(output, key=lambda x: x["transfer_compatibility"], reverse=True)

    def _filter_strategies_by_compatibility(self, strategies: List[Dict[str, Any]], target_context: ContextType, strategy: str) -> List[Dict[str, Any]]:
        thresholds = {"adaptive": .5, "conservative": .7, "aggressive": .3}; output = []
        for row in strategies or []:
            if not isinstance(row, dict): continue
            score = self._calculate_strategy_applicability(row, target_context)
            if score >= thresholds.get(strategy, .5):
                item = copy.deepcopy(row); item["transfer_applicability"] = score; output.append(item)
        return sorted(output, key=lambda x: x["transfer_applicability"], reverse=True)[:10]

    def _calculate_pattern_compatibility(self, pattern: Dict[str, Any], target_context: ContextType, strategy: str) -> float:
        return self._bounded_float(self._safe_float((pattern or {}).get("confidence", .5))*{"adaptive": 1., "conservative": .8, "aggressive": 1.2}.get(strategy, 1.), 0., 1.)

    def _calculate_strategy_applicability(self, strategy: Dict[str, Any], target_context: ContextType) -> float:
        strategy = strategy if isinstance(strategy, dict) else {}; target = self._coerce_context(target_context)
        applied = strategy.get("applied_rules", [])
        known = [self.adaptation_rules[r] for r in applied if r in self.adaptation_rules] if isinstance(applied, list) else []
        if known: return sum(target in r.context_triggers for r in known)/len(known)
        modifier = {ContextType.DEVELOPMENT: 1., ContextType.PRODUCTION: .8, ContextType.TESTING: .9,
                    ContextType.LEARNING: 1.1, ContextType.MAINTENANCE: .7, ContextType.EMERGENCY: .6}.get(target, .8)
        return self._bounded_float(self._safe_float(strategy.get("confidence", .5))*modifier, 0., 1.)

    def _transform_knowledge_for_target(self, knowledge_data: Any, source_context: ContextType, target_context: ContextType,
                                        strategy: Optional[str] = None, transfer_strategy: Optional[str] = None) -> Dict[str, Any]:
        strategy = strategy or transfer_strategy
        if isinstance(knowledge_data, list): data = {"patterns": copy.deepcopy(knowledge_data)}
        elif isinstance(knowledge_data, dict): data = copy.deepcopy(knowledge_data)
        else: data = {"value": knowledge_data}
        if "adaptation_strategies" in data and "successful_strategies" not in data and isinstance(data["adaptation_strategies"], list):
            data["successful_strategies"] = [{**copy.deepcopy(x), "transfer_applicability": self._calculate_strategy_applicability(x, target_context)} for x in data["adaptation_strategies"] if isinstance(x, dict)]
        if isinstance(data.get("performance_baselines"), dict):
            data["performance_baselines"] = self._adapt_baselines_to_context(data["performance_baselines"], source_context, target_context)
        data["transfer_metadata"] = {"source_context": source_context.value, "target_context": target_context.value,
                                      "transfer_strategy": strategy, "transformation_timestamp": datetime.now().isoformat(),
                                      "original_data_size": len(str(knowledge_data))}
        data["adaptation_level"] = {"conservative": "minimal", "adaptive": "moderate", "aggressive": "significant"}.get(strategy, "moderate")
        data["transformation_type"] = strategy
        return data

    def _update_transfer_patterns(self, transfer: KnowledgeTransfer) -> None:
        """Registrar una transferencia sin romper historiales JSON de versiones anteriores."""
        pair = f"{transfer.source_context.value}->{transfer.target_context.value}"
        history = self.knowledge_base.setdefault("transfer_efficiency", {})
        if not isinstance(history, dict):
            history = {}
            self.knowledge_base["transfer_efficiency"] = history
        rows = history.get(pair, [])
        # Algunas versiones antiguas almacenaban un solo dict en vez de una lista.
        if isinstance(rows, dict):
            rows = [rows]
        elif not isinstance(rows, list):
            rows = []
        rows.append({
            "transfer_id": transfer.transfer_id,
            "timestamp": transfer.last_transfer.isoformat() if transfer.last_transfer else datetime.now().isoformat(),
            "efficiency": self._bounded_float(transfer.transfer_efficiency, 0.0, 1.0),
            "success_rate": self._bounded_float(transfer.success_rate, 0.0, 1.0),
            "strategy": transfer.transfer_strategy,
            "knowledge_type": transfer.knowledge_type,
        })
        history[pair] = rows[-50:]
        summary = self.knowledge_base.setdefault("batch_transfer_summary", [])
        summary.append({"transfer_id": transfer.transfer_id, "source_context": transfer.source_context.value,
                        "target_context": transfer.target_context.value, "knowledge_type": transfer.knowledge_type,
                        "transfer_strategy": transfer.transfer_strategy, "transfer_efficiency": transfer.transfer_efficiency,
                        "timestamp": datetime.now().isoformat(), "success": True})
        del summary[:-100]

    def _apply_success_patterns(self, patterns: List[Dict[str, Any]], transfer: Optional[KnowledgeTransfer] = None) -> None:
        rows = self.knowledge_base.setdefault("applied_patterns", [])
        for pattern in patterns or []:
            if isinstance(pattern, dict): rows.append({"pattern_data": copy.deepcopy(pattern), "transfer_id": transfer.transfer_id if transfer else None,
                "source_context": transfer.source_context.value if transfer else None, "target_context": transfer.target_context.value if transfer else None,
                "application_timestamp": datetime.now().isoformat(), "application_confidence": self._bounded_float(pattern.get("confidence", 0.), 0., 1.)})
        del rows[:-200]

    def _apply_adaptation_strategies(self, strategies: List[Dict[str, Any]], transfer: Optional[KnowledgeTransfer] = None) -> None:
        rows = self.knowledge_base.setdefault("applied_strategies", [])
        for strategy in strategies or []:
            if isinstance(strategy, dict): rows.append({"strategy_id": strategy.get("strategy_id"), "strategy_data": copy.deepcopy(strategy),
                "transfer_id": transfer.transfer_id if transfer else None, "source_context": transfer.source_context.value if transfer else strategy.get("source_context"),
                "target_context": transfer.target_context.value if transfer else strategy.get("target_context"),
                "application_timestamp": datetime.now().isoformat(), "application_confidence": self._bounded_float(strategy.get("confidence", .5), 0., 1.)})
        del rows[:-200]

    def _apply_performance_baselines(self, baselines: Dict[str, Any], transfer: Optional[KnowledgeTransfer] = None) -> None:
        entries = self.knowledge_base.setdefault("applied_baselines", {})
        for key, value in (baselines or {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or key.endswith(("_original", "_adjustment")): continue
            rows = entries.setdefault(key, []); rows.append({"baseline_value": value, "transfer_id": transfer.transfer_id if transfer else None,
                "target_context": transfer.target_context.value if transfer else None, "application_timestamp": datetime.now().isoformat()}); del rows[:-10]

    def _apply_transferred_knowledge(self, transfer: KnowledgeTransfer) -> Dict[str, Any]:
        data = transfer.knowledge_data or {}; stats = {"patterns_applied": 0, "strategies_applied": 0, "baselines_applied": 0, "metrics_applied": 0}
        patterns = data.get("success_patterns", []); strategies = data.get("successful_strategies", data.get("adaptation_strategies", [])); baselines = data.get("performance_baselines", {})
        if isinstance(patterns, list): self._apply_success_patterns(patterns, transfer); stats["patterns_applied"] = len(patterns)
        if isinstance(strategies, list): self._apply_adaptation_strategies(strategies, transfer); stats["strategies_applied"] = len(strategies)
        if isinstance(baselines, dict): self._apply_performance_baselines(baselines, transfer); stats["baselines_applied"] = sum(isinstance(v, (int, float)) for v in baselines.values())
        if isinstance(data.get("contextual_metrics"), dict): stats["metrics_applied"] = len(data["contextual_metrics"])
        total = sum(stats.values()); success = total > 0 and transfer.transfer_efficiency >= .3
        score = self._bounded_float(.4*min(1., total/5.) + .6*transfer.transfer_efficiency if success else 0., 0., 1.)
        self.knowledge_base.setdefault("applied_knowledge", []).append({"transfer_id": transfer.transfer_id, "timestamp": datetime.now().isoformat(), "application_results": stats, "success": success, "success_rate": score})
        return {"success": success, "success_rate": score, "metrics": stats, "application_results": stats, "applied_count": total, "total_count": total}

    def _evaluate_knowledge_application(self, transfer: KnowledgeTransfer) -> bool:
        if not transfer or not transfer.knowledge_data or transfer.transfer_efficiency < .3: return False
        return any(bool(transfer.knowledge_data.get(key)) for key in ("success_patterns", "successful_strategies", "adaptation_strategies", "performance_baselines", "contextual_metrics", "patterns"))

    def get_transfer_confidence(self, transfer_id: str, result: Optional[Dict[str, Any]] = None) -> Optional[float]:
        """Obtener una confianza acotada usando primero la transferencia viva y después el historial persistido.

        `result` permite ponderar la confianza con el resultado de aplicación de la transferencia
        (tasa de éxito, indicadores de mejora) sin perder la eficiencia base de la transferencia.
        """
        if not isinstance(transfer_id, str) or not transfer_id.strip():
            return None

        transfer = self.knowledge_transfers.get(transfer_id)
        if transfer is not None:
            efficiency = self._bounded_float(transfer.transfer_efficiency, 0.0, 1.0)
            base = self._resolve_transfer_confidence(transfer_id, transfer, efficiency)
            if not isinstance(result, dict):
                return base
            rate = result.get("success_rate")
            rate = None if rate is None else self._bounded_float(rate, 0.0, 1.0)
            success = result.get("success")
            success = bool(success) if success is not None else bool(rate is not None and rate >= .5)
            if rate is None:
                return self._bounded_float(max(base, .5 if success else base), 0.0, 1.0)
            historical = self._bounded_float(getattr(transfer, "success_rate", 0.0), 0.0, 1.0)
            blended = .5 * rate + .3 * efficiency + .2 * historical
            if success:
                blended = max(blended, min(1., rate + .05))
            return self._bounded_float(blended, 0.0, 1.0)

        records_by_pair = self.knowledge_base.get("transfer_efficiency", {})
        if isinstance(records_by_pair, dict):
            for records in records_by_pair.values():
                # El formato legacy puede ser una lista o un único registro.
                if isinstance(records, dict):
                    records = [records]
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict) or record.get("transfer_id") != transfer_id:
                        continue
                    efficiency = self._bounded_float(record.get("efficiency", 0.5), 0.0, 1.0)
                    success = self._bounded_float(record.get("success_rate", 0.5), 0.0, 1.0)
                    score = record.get("feedback_score")
                    if score is not None:
                        return self._bounded_float(score, 0.0, 1.0)
                    return self._bounded_float(0.6 * efficiency + 0.4 * success, 0.0, 1.0)

        # Sin transferencia viva ni historial: no hay confianza que reportar.
        return 0.0

    def _resolve_transfer_confidence(self, transfer_id: str, transfer: Any, efficiency: float) -> float:
        """Resolver la confianza de una transferencia viva: feedback explícito > atributo > eficiencia."""
        recorded = self._recorded_confidence.get(transfer_id)
        if recorded is not None:
            return self._bounded_float(recorded, 0.0, 1.0)
        attribute = self._safe_float(getattr(transfer, "confidence_score", 0.0), -1.0)
        if attribute > 0.0:
            return self._bounded_float(attribute, 0.0, 1.0)
        return self._bounded_float(efficiency, 0.0, 1.0)


    def register_feedback(
        self,
        transfer_id: str,
        feedback_data: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Registrar feedback y sincronizar el objeto de transferencia con su historial."""
        try:
            if not isinstance(transfer_id, str) or not transfer_id.strip():
                raise ValueError("Transfer ID cannot be empty")
            if not isinstance(feedback_data, dict):
                raise TypeError("feedback_data debe ser un diccionario")

            transfer = self.knowledge_transfers.get(transfer_id)
            if transfer is None:
                self.logger.warning("No existe transferencia activa para feedback: %s", transfer_id)

            score_raw = feedback_data.get("quality", feedback_data.get("score", feedback_data.get("feedback_score", None)))
            score = None if score_raw is None else self._bounded_float(score_raw, 0.0, 1.0)
            success_raw = feedback_data.get("success", result.get("success") if isinstance(result, dict) else None)
            success = bool(success_raw) if success_raw is not None else None
            timestamp = datetime.now()

            if transfer is not None:
                if score is not None:
                    transfer.confidence_score = score
                    self._recorded_confidence[transfer_id] = score
                result_rate = result.get("success_rate") if isinstance(result, dict) else None
                if result_rate is not None:
                    transfer.success_rate = self._bounded_float(result_rate, 0.0, 1.0)
                elif success is not None:
                    transfer.success_rate = 1.0 if success else 0.0
                transfer.last_feedback = timestamp

            transfer_efficiency = self.knowledge_base.setdefault("transfer_efficiency", {})
            matched = False
            for pair, records in list(transfer_efficiency.items()):
                if isinstance(records, dict):
                    records = [records]
                    transfer_efficiency[pair] = records
                if not isinstance(records, list):
                    continue
                for record in records:
                    if isinstance(record, dict) and record.get("transfer_id") == transfer_id:
                        record.update({
                            "feedback_received": True,
                            "feedback_success": success,
                            "feedback_score": score,
                            "feedback_comments": feedback_data.get("comments", feedback_data.get("feedback_comments", "")),
                            "feedback_timestamp": timestamp.isoformat(),
                        })
                        if transfer is not None:
                            record["success_rate"] = transfer.success_rate
                            record["efficiency"] = transfer.transfer_efficiency
                        matched = True

            if not matched:
                pair = (
                    f"{transfer.source_context.value}->{transfer.target_context.value}"
                    if transfer is not None else "unknown->unknown"
                )
                records = transfer_efficiency.setdefault(pair, [])
                if not isinstance(records, list):
                    records = [records] if isinstance(records, dict) else []
                    transfer_efficiency[pair] = records
                records.append({
                    "transfer_id": transfer_id,
                    "efficiency": transfer.transfer_efficiency if transfer is not None else (score or 0.0),
                    "success_rate": transfer.success_rate if transfer is not None else float(bool(success)),
                    "strategy": transfer.transfer_strategy if transfer is not None else "feedback_only",
                    "feedback_received": True,
                    "feedback_success": success,
                    "feedback_score": score,
                    "feedback_comments": feedback_data.get("comments", feedback_data.get("feedback_comments", "")),
                    "timestamp": timestamp.isoformat(),
                    "feedback_timestamp": timestamp.isoformat(),
                })
                del records[:-100]

            if success is not None or score is not None:
                self._update_global_confidence_metrics(bool(success), score if score is not None else float(bool(success)))
            if transfer is not None and success and transfer.success_rate >= 0.7:
                self._record_successful_transfer_pattern(
                    transfer.source_context, transfer.target_context, transfer.knowledge_type
                )
            # El feedback solo es válido si existe la transferencia destino.
            return transfer is not None
        except Exception as exc:
            self.logger.error("Error registrando feedback de transferencia %s: %s", transfer_id, exc)
            return False


    def register_transfer_feedback(
        self,
        transfer_id: str,
        success: bool,
        feedback_score: float = 0.0,
        feedback_comments: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Alias compatible que acepta el contrato público de feedback de transferencia."""
        timestamp = datetime.now().isoformat()
        try:
            if not isinstance(success, bool):
                raise ValueError("Success must be a boolean")
            if isinstance(feedback_score, bool) or not isinstance(feedback_score, (int, float)):
                raise ValueError("Feedback score must be numeric")
            if not 0.0 <= float(feedback_score) <= 1.0:
                raise ValueError("Feedback score must be between 0.0 and 1.0")
            data = {"success": success, "score": float(feedback_score), "comments": feedback_comments, **kwargs}
            ok = self.register_feedback(transfer_id, data)
            if not ok:
                raise RuntimeError("No se pudo registrar el feedback")
            return {"success": True, "transfer_id": transfer_id, "feedback_registered": True,
                    "feedback_data": data, "timestamp": timestamp}
        except Exception as exc:
            self.logger.error("Error en register_transfer_feedback(%s): %s", transfer_id, exc)
            return {"success": False, "transfer_id": transfer_id, "error": str(exc), "timestamp": timestamp}


    def _update_global_confidence_metrics(self, success: bool, feedback_score: float) -> None:
        data = self.knowledge_base.setdefault("global_confidence_metrics", {"total_feedback": 0, "successful_transfers": 0, "average_feedback_score": 0., "confidence_trend": []})
        count = int(data.get("total_feedback", 0)) + 1; old_avg = self._safe_float(data.get("average_feedback_score", 0.))
        score = self._bounded_float(feedback_score, 0., 1.); average = (old_avg*(count-1)+score)/count
        data["total_feedback"] = count; data["successful_transfers"] = int(data.get("successful_transfers", 0))+int(success); data["average_feedback_score"] = average
        trend = data.setdefault("confidence_trend", []); trend.append({"timestamp": datetime.now().isoformat(), "success": success, "score": score, "running_average": average}); del trend[:-50]

    def adjust_transfer_confidence(self, transfer_id: str, adjustment_factor: Optional[float] = None,
                                   feedback_success: Optional[bool] = None, feedback_score: Optional[float] = None,
                                   reason: Optional[str] = None) -> bool:
        transfer = self.knowledge_transfers.get(transfer_id)
        if not transfer: return False
        adjustment = self._safe_float(adjustment_factor) if adjustment_factor is not None else 0.
        if feedback_success is not None: adjustment += .1 if feedback_success else -.1
        if feedback_score is not None:
            if not 0 <= feedback_score <= 1: return False
            adjustment += (float(feedback_score)-.5)*.2
        old = self.get_transfer_confidence(transfer_id); new = self._bounded_float(old+adjustment, 0., 1.)
        transfer.confidence_score = new; transfer.last_feedback = datetime.now()
        self._recorded_confidence[transfer_id] = new
        self.knowledge_base.setdefault("confidence_adjustments", {})[f"{transfer_id}_{int(time.time()*1000)}"] = {"transfer_id": transfer_id, "old_confidence": old, "new_confidence": new, "adjustment_factor": adjustment, "feedback_success": feedback_success, "feedback_score": feedback_score, "reason": reason or "Manual adjustment", "timestamp": datetime.now().isoformat()}
        return True

    def evaluate_transfer_result(
        self,
        transfer: Any,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> TransferEvaluation:
        """Evaluar una transferencia; acepta un KnowledgeTransfer o su identificador legacy.

        El resultado es un dict estructurado que además se desempaqueta como
        ``(is_successful, score, message)``.
        """
        transfer_obj: Optional[KnowledgeTransfer]
        if isinstance(transfer, KnowledgeTransfer):
            transfer_obj = transfer
        else:
            transfer_obj = self.knowledge_transfers.get(str(transfer))
        transfer_id = transfer_obj.transfer_id if transfer_obj is not None else (str(transfer) if transfer else "unknown")
        if transfer_obj is None:
            return TransferEvaluation({
                "success": False,
                "is_successful": False,
                "evaluation_score": 0.0,
                "score": 0.0,
                "confidence_score": 0.0,
                "message": f"Transfer not found: {transfer_id}",
                "feedback_summary": {"success": False, "error": "transfer_not_found",
                                     "evaluation_timestamp": datetime.now().isoformat()},
                "transfer_id": transfer_id,
                "timestamp": datetime.now().isoformat(),
            })
        payload = execution_result if isinstance(execution_result, dict) else {}
        if not payload:
            # No suponer éxito si no se ha ejecutado nada: se devuelve una evaluación neutral.
            payload = {"success": False, "execution_time": 0.0, "error_count": 0, "quality_score": 0.5}

        success = bool(payload.get("success", False))
        rate_raw = payload.get("success_rate")
        rate = 0.0 if rate_raw is None else self._bounded_float(rate_raw, 0.0, 1.0)
        execution_time = max(0.0, self._safe_float(payload.get("execution_time", 0.0)))
        error_count = max(0.0, self._safe_float(payload.get("error_count", 0.0)))
        quality_score = self._bounded_float(payload.get("quality_score", payload.get("feedback_score", 0.5)), 0.0, 1.0)
        time_component = max(0.0, 1.0 - min(1.0, execution_time / 60.0))
        error_component = max(0.0, 1.0 - min(1.0, error_count / 5.0))
        metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
        improvement = self._safe_float(metrics.get("performance_improvement", metrics.get("resource_savings", 0.0)))
        score = self._bounded_float(
            .5 * rate
            + .2 * (1.0 if success else 0.0)
            + .1 * quality_score
            + .1 * time_component
            + .05 * error_component
            + .05 * min(1.0, max(0.0, improvement) / .3),
            0.0, 1.0,
        )
        is_successful = bool(success and rate >= .7 and score >= .7)
        if is_successful:
            message = f"Transfer successful (success rate {rate:.2f})"
        elif success:
            message = f"Transfer partial: success rate {rate:.2f} below the 0.70 threshold"
        else:
            message = f"Transfer failed: success rate {rate:.2f}"

        transfer_obj.success_rate = score
        transfer_obj.confidence_score = score
        transfer_obj.last_transfer = datetime.now()
        self._recorded_confidence[transfer_id] = score
        feedback_ok = self.register_transfer_feedback(
            transfer_id, success=success, feedback_score=score,
            feedback_comments=f"Auto-evaluated: execution_time={execution_time}s, errors={error_count}",
        )
        confidence = self.get_transfer_confidence(transfer_id)
        return TransferEvaluation({
            "success": bool(success and feedback_ok.get("success", False)),
            "is_successful": is_successful,
            "evaluation_score": score,
            "score": score,
            "message": message,
            "confidence_score": self._bounded_float(confidence if confidence is not None else score, 0.0, 1.0),
            "feedback_summary": {"success": success, "execution_time": execution_time, "error_count": error_count,
                                 "quality_score": quality_score, "success_rate": rate, "final_score": score,
                                 "evaluation_timestamp": datetime.now().isoformat()},
            "transfer_id": transfer_id,
            "timestamp": datetime.now().isoformat(),
        })


    def _record_successful_transfer_pattern(self, source_context: ContextType, target_context: ContextType, knowledge_type: str) -> None:
        key = f"{source_context.value}->{target_context.value}"; rows = self.knowledge_base.setdefault("transfer_patterns", {})
        pattern = rows.setdefault(key, {"source": source_context.value, "target": target_context.value, "knowledge_types": [], "success_count": 0, "total_count": 0, "avg_success_rate": 0.})
        pattern["knowledge_types"].append(knowledge_type); pattern["success_count"] += 1; pattern["total_count"] += 1
        pattern["avg_success_rate"] = (pattern["avg_success_rate"]*(pattern["total_count"]-1)+1.)/pattern["total_count"]
        pattern["last_success"] = datetime.now().isoformat()

    # Transferencias por lotes, automáticas y recomendaciones
    @property
    def knowledge_transaptors(self) -> Dict[str, KnowledgeTransfer]:
        """Alias de `knowledge_transfers` para los consumidores que expected este nombre."""
        return self.knowledge_transfers

    def get_knowledge_transfer_objects(
        self,
        context_type: Optional[ContextType] = None,
        knowledge_type: Optional[str] = None,
        min_efficiency: float = 0.0,
    ) -> List[KnowledgeTransfer]:
        """Devolver objetos KnowledgeTransfer; complemento al resumen serializable legacy."""
        ctx = self._coerce_context(context_type) if context_type is not None else None
        threshold = self._bounded_float(min_efficiency, 0.0, 1.0)
        results = []
        for item in self.knowledge_transfers.values():
            if ctx is not None and item.source_context != ctx and item.target_context != ctx:
                continue
            if knowledge_type and item.knowledge_type != knowledge_type:
                continue
            if self._safe_float(item.transfer_efficiency) < threshold:
                continue
            results.append(item)
        return results

    def get_knowledge_transfers(
        self,
        context_type: Optional[ContextType] = None,
        knowledge_type: Optional[str] = None,
        min_efficiency: float = 0.0,
        *,
        as_objects: bool = False,
    ) -> List[Any]:
        """Obtener transferencias filtradas.

        Por compatibilidad, devuelve diccionarios serializables por defecto, tal
        como hacía la API pública original. Usa ``as_objects=True`` para obtener
        instancias ``KnowledgeTransfer``; también está disponible el alias
        explícito ``get_knowledge_transfer_objects``.
        """
        objects = self.get_knowledge_transfer_objects(
            context_type=context_type,
            knowledge_type=knowledge_type,
            min_efficiency=min_efficiency,
        )
        if as_objects:
            return objects
        result: List[Dict[str, Any]] = []
        for transfer in objects:
            result.append({
                "transfer_id": transfer.transfer_id,
                "source_context": transfer.source_context.value,
                "target_context": transfer.target_context.value,
                "knowledge_type": transfer.knowledge_type,
                "transfer_efficiency": transfer.transfer_efficiency,
                "success_rate": transfer.success_rate,
                "last_transfer": transfer.last_transfer.isoformat() if transfer.last_transfer else None,
                "transfer_timestamp": transfer.last_transfer.isoformat() if transfer.last_transfer else None,
                "knowledge_data_size": len(str(transfer.knowledge_data)),
                "transfer_strategy": transfer.transfer_strategy,
                "confidence_score": transfer.confidence_score,
            })
        return result

    def batch_knowledge_transfer(self, transfer_requests: List[Dict[str, Any]]) -> List[Optional[KnowledgeTransfer]]:
        requests = list(transfer_requests or []); results: List[Optional[KnowledgeTransfer]] = [None] * len(requests)
        ordered = sorted(enumerate(requests), key=lambda x: self._safe_float(x[1].get("priority", 1)) if isinstance(x[1], dict) else 0., reverse=True)
        succeeded = 0
        for index, request in ordered:
            if not isinstance(request, dict): continue
            source = self._coerce_context(request.get("source_context")); target = self._coerce_context(request.get("target_context")); kind = request.get("knowledge_type")
            if source is None or target is None or not kind:
                self.logger.warning("Solicitud batch inválida en índice %s", index); continue
            result = self.transfer_knowledge(source, target, str(kind), request.get("transfer_strategy", "adaptive"))
            results[index] = result; succeeded += int(result is not None)
        self.knowledge_base.setdefault("batch_transfer_runs", []).append({"total_requests": len(requests), "successful_transfers": succeeded, "failed_transfers": len(requests)-succeeded, "success_rate": succeeded/len(requests) if requests else 0., "timestamp": datetime.now().isoformat()})
        del self.knowledge_base["batch_transfer_runs"][:-10]
        return results

    def auto_transfer_knowledge(self, target_context: ContextType, knowledge_types: Optional[List[str]] = None,
                                min_compatibility: float = .6, max_transfers: int = 10) -> List[KnowledgeTransfer]:
        target = self._coerce_context(target_context)
        if target is None: return []
        kinds = list(knowledge_types or ["success_patterns", "adaptation_strategies", "performance_baselines", "contextual_metrics"])
        ranked = []
        for source in ContextType:
            if source == target: continue
            compatibility = self._validate_context_compatibility(source, target)
            if compatibility >= min_compatibility:
                ranked.append((compatibility*self._calculate_transfer_potential(source, target), source, compatibility))
        ranked.sort(key=lambda x: x[0], reverse=True); ranked = ranked[:max(0, int(max_transfers))]
        transfers = []
        attempts = 0
        for _, source, _ in ranked:
            for kind in kinds:
                attempts += 1; result = self.transfer_knowledge(source, target, kind, "adaptive")
                if result: transfers.append(result)
        self.knowledge_base.setdefault("auto_transfer_stats", []).append({"target_context": target.value, "total_attempts": attempts,
            "successful_transfers": len(transfers), "success_rate": len(transfers)/attempts if attempts else 0.,
            "average_compatibility": float(np.mean([x[2] for x in ranked])) if ranked else 0., "timestamp": datetime.now().isoformat()})
        del self.knowledge_base["auto_transfer_stats"][:-20]
        return transfers

    def transfer_knowledge_with_feedback(self, source_context: ContextType, target_context: ContextType,
                                         knowledge_type: str, feedback_callback: Optional[Callable] = None) -> Optional[KnowledgeTransfer]:
        source, target = self._coerce_context(source_context), self._coerce_context(target_context)
        if source is None or target is None: return None
        def notify(payload):
            if callable(feedback_callback):
                try: feedback_callback(payload)
                except Exception as exc: self.logger.warning("Callback de transferencia falló: %s", exc)
        notify({"transfer_id": None, "source_context": source.value, "target_context": target.value,
                "knowledge_type": knowledge_type, "status": "starting", "timestamp": datetime.now().isoformat()})
        transfer = self.transfer_knowledge(source, target, knowledge_type, "adaptive")
        if transfer is None:
            notify({"transfer_id": None, "status": "failed", "message": "No se pudo transferir el conocimiento", "timestamp": datetime.now().isoformat()})
            return None
        notify({"transfer_id": transfer.transfer_id, "status": "transferring", "transfer_efficiency": transfer.transfer_efficiency, "timestamp": datetime.now().isoformat()})
        applied = self._apply_transferred_knowledge(transfer)
        transfer.success_rate = self._bounded_float(applied.get("success_rate", 0.), 0., 1.)
        transfer.last_transfer = datetime.now()
        notify({"transfer_id": transfer.transfer_id, "status": "completed", "transfer_efficiency": transfer.transfer_efficiency,
                "success_rate": transfer.success_rate, "application_success": applied.get("success", False),
                "application_metrics": applied.get("metrics", {}), "timestamp": datetime.now().isoformat()})
        return transfer

    def get_transfer_recommendations(self, target_context: ContextType, max_recommendations: int = 5,
                                    min_efficiency: float = .6) -> List[Dict[str, Any]]:
        target = self._coerce_context(target_context)
        if target is None or max_recommendations <= 0: return []
        recommendations = []
        knowledge_types = ("success_patterns", "adaptation_strategies", "performance_baselines", "contextual_metrics")
        for source in ContextType:
            if source == target: continue
            try:
                compatibility = self._validate_context_compatibility(source, target)
                if compatibility < min_efficiency: continue
                potential = self._calculate_transfer_potential(source, target)
                for kind in knowledge_types:
                    efficiency = self._calculate_transfer_efficiency_with_strategy(source, target, kind, "adaptive")
                    urgency = self._calculate_transfer_urgency(target, kind)
                    priority = compatibility*.4 + potential*.3 + efficiency*.2 + urgency*.1
                    if priority < min_efficiency: continue
                    recommendations.append({"source_context": source.value, "target_context": target.value, "knowledge_type": kind,
                        "compatibility": compatibility, "transfer_potential": potential, "expected_efficiency": efficiency,
                        "urgency": urgency, "priority": priority, "recommended_strategy": "adaptive",
                        "confidence": min(1., priority+.1), "reasoning": self._generate_recommendation_reasoning(source, target, kind, compatibility, priority),
                        "timestamp": datetime.now().isoformat(), "generated_timestamp": datetime.now().isoformat()})
            except Exception as exc:
                self.logger.warning("No se pudo recomendar la transferencia %s -> %s: %s", source.value, target.value, exc)
                continue
        recommendations.sort(key=lambda x: x["priority"], reverse=True); recommendations = recommendations[:max_recommendations]
        stored = self.knowledge_base.setdefault("transfer_recommendations", []); stored.extend(copy.deepcopy(recommendations)); del stored[:-50]
        return recommendations

    def _calculate_transfer_urgency(self, target_context: ContextType, knowledge_type: str) -> float:
        context = self._coerce_context(target_context)
        base = {ContextType.EMERGENCY: 1., ContextType.MAINTENANCE: .8, ContextType.PRODUCTION: .6,
                ContextType.OPTIMIZATION: .5, ContextType.LEARNING: .4, ContextType.DEVELOPMENT: .3, ContextType.IDLE: .1}.get(context, .5)
        modifier = {"success_patterns": .8, "adaptation_strategies": .9, "performance_baselines": .7, "contextual_metrics": .6}.get(knowledge_type, .5)
        return self._bounded_float(base*modifier, 0., 1.)

    def _generate_recommendation_reasoning(self, source_context: ContextType, target_context: ContextType,
                                           knowledge_type: str, compatibility: float, priority: float) -> str:
        compatibility_text = "alta compatibilidad" if compatibility >= .8 else "buena compatibilidad" if compatibility >= .6 else "compatibilidad moderada"
        potential_text = "alto potencial de mejora" if priority >= .8 else "buen potencial de mejora" if priority >= .6 else "potencial de mejora moderado"
        type_text = {"success_patterns": "patrones de éxito", "adaptation_strategies": "estrategias de adaptación",
                     "performance_baselines": "líneas base de rendimiento", "contextual_metrics": "métricas contextuales"}.get(knowledge_type, knowledge_type)
        return (f"Transferencia de {knowledge_type} desde {source_context.value} hacia {target_context.value}: "
                f"{compatibility_text} ({compatibility:.2f}), {potential_text}, {type_text}")

    def _estimate_transfer_efficiency(self, source: ContextType, target: ContextType, knowledge_type: str) -> float:
        return self._calculate_transfer_efficiency_with_strategy(source, target, knowledge_type, "adaptive")

    def _identify_relevant_knowledge_types(self, source: ContextType, target: ContextType) -> List[str]:
        available = []
        for kind in ("success_patterns", "adaptation_strategies", "performance_baselines", "contextual_metrics"):
            values = self._extract_knowledge_from_context(source, kind)
            if values and any(bool(v) for v in values.values()): available.append(kind)
        return available

    def _generate_transfer_reasoning(self, source: ContextType, target: ContextType, knowledge_type: str) -> str:
        compatibility = self._validate_context_compatibility(source, target)
        return f"Compatibilidad {compatibility:.2f}; conocimiento '{knowledge_type}' desde {source.value} hacia {target.value}"

    def _calculate_transfer_priority(self, compatibility: float, potential: float, knowledge_type: str) -> float:
        multiplier = {"success_patterns": 1., "adaptation_strategies": 1.1, "performance_baselines": .9, "contextual_metrics": 1.2}.get(knowledge_type, 1.)
        return self._bounded_float((compatibility+potential)/2.*multiplier, 0., 1.)

    def _get_available_knowledge_types(self, context: ContextType) -> List[str]:
        return self._identify_relevant_knowledge_types(context, ContextType.IDLE)

    # Feedback alternativo y asignación de recursos
    def record_resource_allocation(self, allocation_data: Dict[str, Any]) -> None:
        if not isinstance(allocation_data, dict) or not allocation_data.get("resource_type"):
            self.logger.warning("Falta resource_type en la asignación"); return
        resource = str(allocation_data["resource_type"]); context = allocation_data.get("context", {}) or {}
        priority = self._safe_float(allocation_data.get("priority", 0)); status = str(allocation_data.get("status", "unknown"))
        signature = abs(hash(json.dumps(context, sort_keys=True, default=str))) % 1000
        rows = self.knowledge_base.setdefault("resource_allocations", {}).setdefault(f"{resource}_{signature}", [])
        rows.append({"allocation_id": allocation_data.get("allocation_id"), "resource_type": resource,
                     "priority": priority, "status": status, "context": context,
                     "timestamp": allocation_data.get("timestamp") or datetime.now().isoformat(), "amount": allocation_data.get("amount")})
        del rows[:-50]; self._update_resource_usage_patterns(resource, context, priority, status)

    def _update_resource_usage_patterns(self, resource_type: str, context: Dict[str, Any], priority: float, status: str) -> None:
        all_patterns = self.knowledge_base.setdefault("resource_patterns", {}); key = f"{resource_type}_usage"
        data = all_patterns.setdefault(key, {"total_allocations": 0, "high_priority_allocations": 0, "context_patterns": {}, "status_distribution": {}, "last_updated": datetime.now().isoformat()})
        data["total_allocations"] += 1
        if priority >= 3: data["high_priority_allocations"] += 1
        statuses = data.setdefault("status_distribution", {}); statuses[status] = statuses.get(status, 0)+1
        signature = json.dumps(context, sort_keys=True, default=str); contexts = data.setdefault("context_patterns", {}); contexts[signature] = contexts.get(signature, 0)+1
        data["last_updated"] = datetime.now().isoformat()

    # Gestión de reglas
    def add_adaptation_rule(self, rule: AdaptationRule) -> bool:
        if not isinstance(rule, AdaptationRule): return False
        self.adaptation_rules[rule.rule_id] = rule
        return self._save_adaptation_rules()

    def remove_adaptation_rule(self, rule_id: str) -> bool:
        if rule_id not in self.adaptation_rules: return False
        del self.adaptation_rules[rule_id]; self._save_adaptation_rules(); return True

    def enable_rule(self, rule_id: str) -> bool:
        if rule_id not in self.adaptation_rules: return False
        self.adaptation_rules[rule_id].enabled = True; self._save_adaptation_rules(); return True

    def disable_rule(self, rule_id: str) -> bool:
        if rule_id not in self.adaptation_rules: return False
        self.adaptation_rules[rule_id].enabled = False; self._save_adaptation_rules(); return True

    def get_adaptation_rule(self, rule_id: str) -> Optional[AdaptationRule]: return self.adaptation_rules.get(rule_id)
    def get_adaptation_rules(self) -> List[Dict[str, Any]]: return [r.to_dict() for r in self.list_adaptation_rules()]
    def list_adaptation_rules(self, enabled_only: bool = False) -> List[AdaptationRule]:
        return sorted([r for r in self.adaptation_rules.values() if not enabled_only or r.enabled], key=lambda r: r.priority, reverse=True)

    # Persistencia compatible con los dos formatos JSON usados por las versiones anteriores.
    def save_adaptation_rules(self) -> bool: return self._save_adaptation_rules()

    def _save_adaptation_rules(self) -> bool:
        path = self._resolve_path(self.config.get("adaptation_rules_file"), "contextual_adaptation_rules.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {"version": "2.0", "last_updated": datetime.now().isoformat(),
                       "total_rules": len(self.adaptation_rules), "rules": [r.to_dict() for r in self.adaptation_rules.values()]}
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
            os.replace(tmp, path); return True
        except Exception as exc: self.logger.error("Error guardando reglas: %s", exc); return False

    def load_adaptation_rules(self) -> bool:
        path = self._resolve_path(self.config.get("adaptation_rules_file"), "contextual_adaptation_rules.json")
        if not os.path.isfile(path): return True
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            rows = payload.get("rules", []) if isinstance(payload, dict) else payload
            loaded = {}
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or not row.get("rule_id"): continue
                triggers = [ctx for raw in row.get("context_triggers", []) if (ctx := self._coerce_context(raw)) is not None]
                last = row.get("last_execution")
                try: last = datetime.fromisoformat(last) if last else None
                except (ValueError, TypeError): last = None
                loaded[row["rule_id"]] = AdaptationRule(row["rule_id"], row.get("name", row["rule_id"]), row.get("description", ""), row.get("condition_pattern", ""), list(row.get("adaptation_actions", [])), triggers, self._safe_float(row.get("confidence_threshold", .7)), int(row.get("priority", 1)), bool(row.get("enabled", True)), self._safe_float(row.get("success_rate", 0.)), int(row.get("execution_count", 0)), last, self._safe_float(row.get("adaptation_score", 0.)), list(row.get("constraints", [])), dict(row.get("metadata", {})), row.get("deadline"))
            if loaded: self.adaptation_rules = loaded
            return True
        except Exception as exc: self.logger.error("Error cargando reglas: %s", exc); return False

    def _load_adaptation_rules(self) -> bool:
        """Alias privado legacy de load_adaptation_rules."""
        return self.load_adaptation_rules()

    def save_knowledge_base(self) -> bool:
        path = self._resolve_path(self.config.get("knowledge_base_file"), "contextual_knowledge_base.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {"version": "2.0", "last_updated": datetime.now().isoformat(), "context_snapshots": len(self.context_snapshots), "adaptation_history": len(self.adaptation_history), "knowledge_transfers": len(self.knowledge_transfers), "data": self.knowledge_base}
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
            os.replace(tmp, path); return True
        except Exception as exc: self.logger.error("Error guardando knowledge base: %s", exc); return False

    def load_knowledge_base(self) -> bool:
        path = self._resolve_path(self.config.get("knowledge_base_file"), "contextual_knowledge_base.json")
        if not os.path.isfile(path): return True
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            if isinstance(data, dict):
                self.knowledge_base.update(data)
                for ctx in ContextType:
                    for key, default in (("context_patterns", []), ("success_patterns", []), ("performance_baselines", {}), ("adaptation_strategies", [])):
                        self.knowledge_base.setdefault(key, {}).setdefault(ctx.value, default.copy())
                self.knowledge_base.setdefault("integration_records", [])
                self.knowledge_base.setdefault("transfer_efficiency", {})
            return True
        except Exception as exc: self.logger.error("Error cargando knowledge base: %s", exc); return False

    def save_all_data(self) -> bool: return self._save_adaptation_rules() and self.save_knowledge_base()
    def load_all_data(self) -> bool: return self.load_adaptation_rules() and self.load_knowledge_base()

    def backup_data(self, backup_dir: Optional[str] = None) -> bool:
        try:
            backup_dir = backup_dir or os.path.join(self.data_dir, "backups"); os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); copied = False
            for configured, name in ((self.config.get("adaptation_rules_file"), "adaptation_rules"), (self.config.get("knowledge_base_file"), "knowledge_base")):
                path = self._resolve_path(configured, f"{name}.json")
                if os.path.isfile(path): shutil.copy2(path, os.path.join(backup_dir, f"{name}_backup_{stamp}.json")); copied = True
            return copied
        except Exception as exc: self.logger.error("Error creando backup: %s", exc); return False

    def export_adaptation_history(self, export_file: Optional[str] = None) -> bool:
        try:
            if not export_file:
                folder = os.path.join(self.data_dir, "exports"); os.makedirs(folder, exist_ok=True)
                export_file = os.path.join(folder, f"adaptation_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            os.makedirs(os.path.dirname(os.path.abspath(export_file)), exist_ok=True)
            payload = {"version": "2.0", "exported_at": datetime.now().isoformat(), "total_adaptations": len(self.adaptation_history), "adaptations": [self._serializable_history(x) for x in self.adaptation_history]}
            with open(export_file, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
            return True
        except Exception as exc: self.logger.error("Error exportando historial: %s", exc); return False

    # Integraciones con los subsistemas existentes
    def integrate_with_performance_optimizer(self) -> Dict[str, Any]:
        try:
            status = self.performance_optimizer.get_optimization_status() or {}
            recommendations = self._call_optional(self.performance_optimizer, "get_optimization_recommendations", default=[]) or []
            actions = [x for rec in recommendations if isinstance(rec, dict) and (x := self._map_optimization_to_adaptation(rec))]
            if self.current_context:
                self.performance_optimizer.update_context_info({"context_type": self.current_context.context_type.value,
                    "contextual_factors": {k.value: v for k, v in self.current_context.contextual_factors.items()},
                    "adaptation_level": self.adaptation_level.value, "confidence_score": self.current_context.confidence_score})
            record = {"timestamp": datetime.now().isoformat(), "system": "performance_optimizer", "status": "success",
                      "applied_adaptations": actions, "performance_metrics": status.get("current_metrics", {}),
                      "efficiency_score": status.get("efficiency_score", 0.)}
            self.knowledge_base.setdefault("integration_records", []).append(record)
            return {"success": True, "applied_adaptations": actions, "performance_status": status, "integration_record": record}
        except Exception as exc:
            self.logger.error("Error integrando PerformanceOptimizer: %s", exc)
            return {"success": False, "error": str(exc), "applied_adaptations": []}

    def integrate_with_self_improvement_system(self) -> Dict[str, Any]:
        try:
            status = self.self_improvement_system.get_learning_status() or {}
            raw_rules = self._call_optional(self.self_improvement_system, "get_improvement_rules", default=[]) or []
            if self.current_context:
                self._call_optional(self.self_improvement_system, "set_context_aware_config", {
                    "context_type": self.current_context.context_type.value, "learning_mode": self._determine_learning_mode(),
                    "confidence_threshold": self.current_context.confidence_score, "adaptation_level": self.adaptation_level.value})
            synced = self._sync_adaptation_rules(raw_rules if isinstance(raw_rules, list) else [])
            if self.config.get("learning_enabled", True):
                session = self._call_optional(self.self_improvement_system, "start_contextual_learning", default=None,
                    context_type=self.current_context.context_type if self.current_context else ContextType.IDLE,
                    adaptation_level=self.adaptation_level,
                    contextual_factors=self.current_context.contextual_factors if self.current_context else {})
                self.knowledge_base.setdefault("learning_sessions", []).append({"session_id": getattr(session, "session_id", None),
                    "timestamp": datetime.now().isoformat(), "context_type": self.current_context.context_type.value if self.current_context else "idle",
                    "adaptation_level": self.adaptation_level.value, "synchronized_rules": len(synced)})
            record = {"timestamp": datetime.now().isoformat(), "system": "self_improvement_system", "status": "success",
                      "learning_status": status, "synchronized_rules": len(synced), "success": True}
            self.knowledge_base.setdefault("integration_records", []).append(record)
            return {"success": True, "synchronized_rules": synced, "learning_status": status, "integration_record": record}
        except Exception as exc:
            self.logger.error("Error integrando SelfImprovementSystem: %s", exc)
            return {"success": False, "error": str(exc), "synchronized_rules": []}

    def integrate_with_adaptive_learning_engine(self) -> Dict[str, Any]:
        try:
            status = self._call_optional(self.adaptive_learning_engine, "get_learning_engine_status", default=None)
            if status is None: status = self._call_optional(self.adaptive_learning_engine, "get_engine_status", default={})
            active = self._call_optional(self.adaptive_learning_engine, "get_active_tasks", default=[]) or []
            tasks = []
            if self.current_context:
                task = self._call_optional(self.adaptive_learning_engine, "create_contextual_learning_task", default=None,
                    context_type=self.current_context.context_type, adaptation_level=self.adaptation_level,
                    contextual_factors=self.current_context.contextual_factors, performance_metrics=self.current_context.performance_metrics)
                if task is not None: tasks.append(task)
                self._call_optional(self.adaptive_learning_engine, "set_adaptive_config", {
                    "learning_rate": self._calculate_adaptive_learning_rate(), "batch_size": self._calculate_adaptive_batch_size(),
                    "max_epochs": self._calculate_adaptive_max_epochs(), "patience": self._calculate_adaptive_patience()}, default=None)
            for transfer in self.knowledge_transfers.values():
                if transfer.success_rate > .7:
                    task = self._call_optional(self.adaptive_learning_engine, "apply_knowledge_transfer", default=None, transfer=transfer, context=self.current_context)
                    if task is not None: tasks.append(task)
            record = {"timestamp": datetime.now().isoformat(), "system": "adaptive_learning_engine", "status": "success",
                      "active_tasks": len(active), "contextual_tasks_created": len(tasks), "learning_status": status}
            self.knowledge_base.setdefault("integration_records", []).append(record)
            return {"success": True, "contextual_tasks": tasks, "active_tasks": active, "learning_status": status, "integration_record": record}
        except Exception as exc:
            self.logger.error("Error integrando AdaptiveLearningEngine: %s", exc)
            return {"success": False, "error": str(exc), "contextual_tasks": []}

    def integrate_with_pattern_analyzer(self) -> Dict[str, Any]:
        try:
            detected = self._call_optional(self.pattern_analyzer, "get_detected_patterns", default=[]) or []
            patterns = []
            if self.current_context:
                calls = (("analyze_performance_patterns", {"metrics": self.current_context.performance_metrics, "context_type": self.current_context.context_type}),
                         ("analyze_behavior_patterns", {"user_patterns": self.current_context.user_interaction_patterns, "context_type": self.current_context.context_type}),
                         ("analyze_system_patterns", {"system_metrics": self.current_context.system_metrics, "context_type": self.current_context.context_type}))
                for method, kwargs in calls:
                    result = self._call_optional(self.pattern_analyzer, method, default=[], **kwargs)
                    if isinstance(result, list): patterns.extend(p for p in result if isinstance(p, dict))
            added = 0
            for pattern in patterns:
                rule = self._create_adaptation_rule_from_pattern(pattern)
                if rule and rule.rule_id not in self.adaptation_rules: self.adaptation_rules[rule.rule_id] = rule; added += 1
            record = {"timestamp": datetime.now().isoformat(), "system": "pattern_analyzer", "status": "success",
                      "detected_patterns": len(detected), "contextual_patterns": len(patterns), "rules_added": added}
            self.knowledge_base.setdefault("pattern_analysis", []).append(record); self.knowledge_base.setdefault("integration_records", []).append(record)
            return {"success": True, "detected_patterns": detected, "contextual_patterns": patterns, "integration_record": record}
        except Exception as exc:
            self.logger.error("Error integrando PatternAnalyzer: %s", exc)
            return {"success": False, "error": str(exc), "detected_patterns": [], "contextual_patterns": []}

    def set_meta_learning_system(self, meta_learning_system) -> bool:
        if meta_learning_system is None:
            self.meta_learning_system = None; return False
        if not callable(getattr(meta_learning_system, "get_meta_learning_metrics", None)): return False
        self.meta_learning_system = meta_learning_system; return True

    def integrate_with_meta_learning_system(self, meta_learning_system=None) -> Dict[str, Any]:
        try:
            if meta_learning_system is not None and not self.set_meta_learning_system(meta_learning_system):
                return {"success": False, "error": "API de MetaLearningSystem incompatible", "meta_learning_record": None}
            system = self.meta_learning_system
            if system is None: return {"success": False, "error": "MetaLearningSystem no conectado", "meta_learning_record": None}
            metrics = system.get_meta_learning_metrics() or {}
            recommendations = self._call_optional(system, "get_recommendations", default=[]) or []
            evaluations = self._call_optional(system, "get_learning_evaluations", default=[]) or []
            rules = self._call_optional(system, "get_meta_rules", default=[]) or []
            record = {"timestamp": datetime.now().isoformat(), "total_experiences": metrics.get("total_experiences", 0),
                "applied_insights": metrics.get("applied_insights", 0), "recommendations": len(recommendations),
                "evaluations": len(evaluations), "meta_rules": len(rules), "system_coverage": metrics.get("system_coverage", {}),
                "context_type": self.current_context.context_type.value if self.current_context else "unknown",
                "adaptation_level": self.adaptation_level.value, "top_recommendations": recommendations[:5]}
            self.knowledge_base.setdefault("meta_learning_records", []).append(record)
            integration = {"timestamp": record["timestamp"], "system": "meta_learning_system", "status": "success",
                           "total_experiences": record["total_experiences"], "recommendations": record["recommendations"], "meta_rules": record["meta_rules"]}
            self.knowledge_base.setdefault("integration_records", []).append(integration)
            return {"success": True, "meta_learning_record": record, "integration_record": integration}
        except Exception as exc:
            self.logger.error("Error integrando MetaLearningSystem: %s", exc)
            return {"success": False, "error": str(exc), "meta_learning_record": None}

    def full_system_integration(self) -> Dict[str, Any]:
        results = {"performance_optimizer": self.integrate_with_performance_optimizer(),
                   "self_improvement_system": self.integrate_with_self_improvement_system(),
                   "adaptive_learning_engine": self.integrate_with_adaptive_learning_engine(),
                   "pattern_analyzer": self.integrate_with_pattern_analyzer()}
        succeeded = sum(bool(x.get("success")) for x in results.values()); total = len(results); rate = succeeded/total if total else 0.
        record = {"timestamp": datetime.now().isoformat(), "total_integrations": total, "successful_integrations": succeeded,
                  "success_rate": rate, "integration_results": results,
                  "current_context": self.current_context.to_dict() if self.current_context else None,
                  "adaptation_level": self.adaptation_level.value}
        self.knowledge_base.setdefault("full_integration_records", []).append(record)
        self.last_integration_timestamp = datetime.now(); self.integration_success_rate = rate
        return {"success": succeeded == total, "success_rate": rate, "successful_integrations": succeeded,
                "total_integrations": total, "integration_results": results, "integration_record": record}

    def _map_optimization_to_adaptation(self, recommendation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        mapping = {"cpu": "optimize_cpu_resources", "memory": "optimize_memory_usage", "performance": "enhance_performance",
                   "error": "reduce_error_rate", "disk": "optimize_disk_usage", "network": "optimize_network_conditions"}
        return {"action": mapping.get(recommendation.get("type", "performance"), "general_optimization"),
                "priority": recommendation.get("priority", "medium"), "expected_improvement": recommendation.get("expected_improvement", 0.),
                "confidence": recommendation.get("confidence", 0.), "description": recommendation.get("description", ""),
                "timestamp": datetime.now().isoformat()}

    def _determine_learning_mode(self) -> str:
        if not self.current_context: return "passive"
        kind = self.current_context.context_type
        if kind == ContextType.DEVELOPMENT: return "active"
        if kind in (ContextType.LEARNING, ContextType.EMERGENCY): return "reinforcement"
        if kind == ContextType.PRODUCTION: return "passive" if self.current_context.confidence_score > .8 else "active"
        return "passive"

    def _sync_adaptation_rules(self, improvement_rules: List[Any]) -> List[Dict[str, Any]]:
        synchronized = []
        for raw in improvement_rules:
            try:
                data = raw if isinstance(raw, dict) else {k: getattr(raw, k, default) for k, default in
                    (("rule_id", "unknown"), ("name", "Unknown"), ("description", ""), ("condition", ""), ("action", []), ("confidence_threshold", .7), ("priority", 1), ("enabled", True))}
                actions = data.get("action", []); actions = [actions] if isinstance(actions, str) else list(actions or [])
                rule = AdaptationRule(f"sync_{data.get('rule_id', 'unknown')}", f"Sincronizado: {data.get('name', 'Unknown')}",
                    data.get("description", ""), data.get("condition", ""), actions, [ContextType.PRODUCTION],
                    self._safe_float(data.get("confidence_threshold", .7)), int(data.get("priority", 1)), bool(data.get("enabled", True)))
                self.adaptation_rules[rule.rule_id] = rule; synchronized.append(rule.to_dict())
            except Exception as exc: self.logger.warning("No se pudo sincronizar regla: %s", exc)
        return synchronized

    def _calculate_adaptive_learning_rate(self) -> float:
        if not self.current_context: return .01
        factor = {AdaptationLevel.MINIMAL: 1., AdaptationLevel.MODERATE: .8, AdaptationLevel.SIGNIFICANT: .6, AdaptationLevel.RADICAL: .4}.get(self.adaptation_level, 1.)
        return self._bounded_float(.01*self.current_context.confidence_score*factor, .001, .1)

    def _calculate_adaptive_batch_size(self) -> int:
        if not self.current_context: return 32
        cpu = self.current_context.system_metrics.get("cpu_usage", .5); memory = self.current_context.system_metrics.get("memory_usage", .5)
        return max(8, min(128, int(32*(1.-cpu)*(1.-memory))))

    def _calculate_adaptive_max_epochs(self) -> int:
        if not self.current_context: return 100
        base = {ContextType.DEVELOPMENT: 200, ContextType.LEARNING: 150, ContextType.PRODUCTION: 50,
                ContextType.EMERGENCY: 20, ContextType.OPTIMIZATION: 100}.get(self.current_context.context_type, 100)
        return max(10, min(500, int(base*self.current_context.confidence_score)))

    def _calculate_adaptive_patience(self) -> int:
        if not self.current_context: return 10
        if self.current_context.context_type in (ContextType.EMERGENCY, ContextType.MAINTENANCE): return 5
        if self.current_context.context_type == ContextType.DEVELOPMENT: return 20
        return 10

    def _create_adaptation_rule_from_pattern(self, pattern: Dict[str, Any]) -> Optional[AdaptationRule]:
        mapping = {"error_spike": ["enable_recovery_mode", "isolate_problematic_components"],
                   "performance_degradation": ["optimize_memory_usage", "enable_performance_mode"],
                   "anomaly": ["enable_safe_mode"], "trend": ["collect_feedback"], "cycle": ["cache_optimization"]}
        kind = pattern.get("type", "unknown"); actions = mapping.get(kind)
        if not actions: return None
        return AdaptationRule(f"pattern_{pattern.get('id', int(time.time()*1000))}", f"Adaptación por {kind}",
            f"Adaptación basada en patrón: {pattern.get('description', '')}", "", actions,
            [ContextType.PRODUCTION, ContextType.OPTIMIZATION], self._bounded_float(pattern.get("confidence", .7), 0., 1.), int(pattern.get("priority", 3)))

    def get_integration_status(self) -> Dict[str, Any]:
        records = self.knowledge_base.get("integration_records", [])
        return {"last_integration_timestamp": self.last_integration_timestamp.isoformat() if self.last_integration_timestamp else None,
                "integration_success_rate": self.integration_success_rate, "total_integrations": len(records),
                "successful_integrations": sum(bool(r.get("success", r.get("status") == "success")) for r in records if isinstance(r, dict)),
                "system_connections": {"performance_optimizer": self.performance_optimizer is not None,
                    "self_improvement_system": self.self_improvement_system is not None,
                    "adaptive_learning_engine": self.adaptive_learning_engine is not None,
                    "pattern_analyzer": self.pattern_analyzer is not None, "meta_learning_system": self.meta_learning_system is not None},
                "current_context": self.current_context.to_dict() if self.current_context else None,
                "adaptation_level": self.adaptation_level.value}

    def update_system_configs(self) -> Dict[str, Any]:
        updated = []
        try:
            if self.current_context:
                confidence = self.current_context.confidence_score; emergency = self.current_context.context_type == ContextType.EMERGENCY
                configs = ((self.performance_optimizer, {"optimization_enabled": confidence > .5, "auto_optimization": not emergency, "optimization_interval": max(10, int(60*(1-confidence)))}),
                           (self.self_improvement_system, {"learning_enabled": confidence > .6, "auto_learning": not emergency, "learning_interval": max(60, int(300*(1-confidence)))}),
                           (self.adaptive_learning_engine, {"learning_enabled": confidence > .7, "auto_learning": not emergency, "engine_interval": max(5, int(60*(1-confidence)))}),
                           (self.pattern_analyzer, {"detection_sensitivity": max(.1, confidence), "analysis_interval": max(5, int(30*(1-confidence)))}))
                for obj, config in configs:
                    if callable(getattr(obj, "update_config", None)): obj.update_config(config); updated.append(type(obj).__name__)
            record = {"timestamp": datetime.now().isoformat(), "systems_updated": updated,
                      "context_applied": self.current_context.to_dict() if self.current_context else None, "adaptation_level": self.adaptation_level.value}
            self.knowledge_base.setdefault("config_updates", []).append(record)
            return {"success": True, "systems_updated": updated, "update_record": record}
        except Exception as exc: return {"success": False, "error": str(exc), "systems_updated": updated}

    # Gestión/evolución de estrategias
    def get_available_strategies(self, context: ContextType) -> List[Dict[str, Any]]:
        ctx = self._coerce_context(context)
        entries = self.knowledge_base.get("adaptation_strategies", {}).get(ctx.value, []) or []
        result = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict): continue
            name = entry.get("strategy") or entry.get("name") or f"strategy_{index}"
            result.append({"strategy_id": entry.get("strategy_id", f"strategy_{ctx.value}_{index}"),
                "strategy_type": entry.get("strategy_type", "adaptation_strategies"), "name": name,
                "confidence": self._bounded_float(entry.get("confidence", .5), 0., 1.),
                "description": entry.get("description", f"Estrategia {name} para {ctx.value}"),
                "source_context": ctx.value, "knowledge_data": entry.get("knowledge_data", {"adaptation_strategies": [entry]})})
        for entry in self.knowledge_base.get("applied_strategies", []) or []:
            if not isinstance(entry, dict) or not entry.get("strategy_id"): continue
            if any(x["strategy_id"] == entry["strategy_id"] for x in result): continue
            result.append({"strategy_id": entry["strategy_id"], "strategy_type": "adaptation_strategies",
                "name": entry.get("strategy_name") or entry["strategy_id"],
                "confidence": self._bounded_float(entry.get("confidence", .7), 0., 1.),
                "description": entry.get("description", f"Estrategia aplicada {entry['strategy_id']}"),
                "source_context": entry.get("source_context"), "knowledge_data": entry.get("knowledge_data", {})})
        return result

    def generate_strategy_candidates(self, target_context: ContextType, max_candidates: int = 5, min_confidence: float = .5) -> List[Dict[str, Any]]:
        target = self._coerce_context(target_context); candidates = []
        if target is None: return candidates
        for strategy in self.get_available_strategies(target):
            confidence = self._safe_float(strategy.get("confidence", 0.))
            if confidence < min_confidence: continue
            candidates.append({**strategy, "strategy_id": f"cand_{int(time.time()*1000000)}_{strategy['strategy_id']}", "target_context": target.value})
            if len(candidates) >= max(0, int(max_candidates)): break
        return candidates

    def validate_candidate_strategy(self, candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validar estructura y rangos de un candidato de estrategia."""
        if not isinstance(candidate, dict):
            return False, ["El candidato debe ser un diccionario"]
        errors: List[str] = []
        for field_name in ("strategy_id", "strategy_type", "name", "description"):
            if not candidate.get(field_name):
                errors.append(f"Campo requerido ausente o vacío: {field_name}")
        confidence = candidate.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append(f"Confianza inválida: {confidence}")
        elif not 0.0 <= float(confidence) <= 1.0:
            errors.append(f"Confianza fuera de rango [0, 1]: {confidence}")
        if "knowledge_data" in candidate and not isinstance(candidate["knowledge_data"], (dict, list)):
            errors.append("knowledge_data debe ser un diccionario o una lista")
        return not errors, errors


    def evaluate_candidate_strategy(
        self,
        candidate: Dict[str, Any],
        target_context: ContextType,
    ) -> Dict[str, Any]:
        """Evaluar una estrategia en su contexto destino sin comparar un contexto consigo mismo como transferencia."""
        candidate = candidate if isinstance(candidate, dict) else {}
        target = self._coerce_context(target_context)
        valid, errors = self.validate_candidate_strategy(candidate)
        confidence = self._bounded_float(candidate.get("confidence", 0.0), 0.0, 1.0)
        knowledge_data = candidate.get("knowledge_data", {}) or {}
        result: Dict[str, Any] = {
            "valid": valid, "errors": errors, "strategy_id": candidate.get("strategy_id"),
            "strategy_name": candidate.get("name", candidate.get("strategy_name")),
            "strategy_type": candidate.get("strategy_type", "adaptation_strategies"),
            "description": candidate.get("description"), "confidence": confidence,
            "knowledge_data": knowledge_data,
            "target_context": target.value if target else str(target_context),
            "overall_score": 0.0, "applicability": 0.0, "efficiency": 0.0,
        }
        if not valid or target is None:
            return result

        strategy_payload = dict(candidate)
        if isinstance(knowledge_data, dict):
            strategy_payload.setdefault("applied_rules", knowledge_data.get("applied_rules", []))
            strategy_payload.setdefault("confidence", confidence)
        result["applicability"] = self._bounded_float(
            self._calculate_strategy_applicability(strategy_payload, target), 0.0, 1.0
        )

        source = self._coerce_context(candidate.get("source_context"))
        if source is not None and source != target:
            result["efficiency"] = self._calculate_transfer_efficiency_with_strategy(
                source, target, str(result["strategy_type"]), "adaptive"
            )
        else:
            # Es una evaluación de aplicabilidad, no una transferencia entre contextos.
            type_factor = {"success_patterns": 1.0, "adaptation_strategies": 0.9,
                           "performance_baselines": 0.85, "contextual_metrics": 0.9}.get(result["strategy_type"], 0.8)
            result["efficiency"] = self._bounded_float((0.5 + 0.5 * result["applicability"]) * type_factor, 0.0, 1.0)

        result["overall_score"] = round(
            confidence * 0.4 + result["applicability"] * 0.3 + result["efficiency"] * 0.3, 4
        )
        return result


    def select_strategy(self, evaluated_strategies: List[Dict[str, Any]], current_strategy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = list(evaluated_strategies or []); valid = [x for x in rows if isinstance(x, dict) and x.get("valid")]
        details = {"total_candidates": len(rows), "valid_candidates": len(valid), "ranking": [], "comparisons": []}
        if not valid: return {"selected": False, "reason": "No hay estrategias válidas para seleccionar", "selected_strategy": None,
            "comparison_details": details, "selection_decision": {"change_strategy": False, "improvement_amount": 0.}}
        ranked = sorted(valid, key=lambda x: self._safe_float(x.get("overall_score", 0.)), reverse=True); best = ranked[0]
        details["ranking"] = [{"strategy_id": x.get("strategy_id"), "strategy_name": x.get("strategy_name"), "overall_score": self._safe_float(x.get("overall_score", 0.))} for x in ranked]
        score = self._safe_float(best.get("overall_score", 0.))
        if current_strategy:
            delta = score-self._safe_float(current_strategy.get("overall_score", 0.)); change = delta > .1
            decision = {"change_strategy": change, "improvement_amount": delta if change else 0., "reason": "Mejora significativa" if change else "No hay mejora significativa"}
        else: decision = {"change_strategy": True, "improvement_amount": score, "reason": "Mejor estrategia disponible"}
        return {"selected": True, "selected_strategy": best, "comparison_details": details, "selection_decision": decision}

    def compare_strategies(self, strategy1: Dict[str, Any], strategy2: Dict[str, Any]) -> Dict[str, Any]:
        a = self._safe_float((strategy1 or {}).get("overall_score", 0.)); b = self._safe_float((strategy2 or {}).get("overall_score", 0.)); delta = a-b
        if abs(delta) < 1e-9: better, improvement = "tie", 0.
        elif delta > 0: better, improvement = (strategy1 or {}).get("strategy_id"), (delta/b*100.) if b else 100.
        else: better, improvement = (strategy2 or {}).get("strategy_id"), (-delta/a*100.) if a else 100.
        return {"better_strategy": better, "score_difference": abs(delta), "improvement_percentage": improvement,
                "strategy1_score": a, "strategy2_score": b, "comparison_details": {"strategy1_id": (strategy1 or {}).get("strategy_id"), "strategy2_id": (strategy2 or {}).get("strategy_id")}}

    def apply_strategy(self, strategy: Dict[str, Any], target_context: ContextType) -> Dict[str, Any]:
        strategy = strategy if isinstance(strategy, dict) else {}; target = self._coerce_context(target_context)
        if target is None: return {"applied": False, "error": "Contexto destino inválido"}
        started = time.time(); sid = strategy.get("strategy_id")
        record = {"strategy_id": sid, "strategy_name": strategy.get("strategy_name") or strategy.get("name"),
            "target_context": target.value, "knowledge_data": copy.deepcopy(strategy.get("knowledge_data", {}) or {}),
            "confidence": self._safe_float(strategy.get("confidence", .7)), "application_timestamp": datetime.now().isoformat(),
            "application_duration": 0., "reverted": False}
        self.knowledge_base.setdefault("applied_strategies", []).append(record)
        self.knowledge_base.setdefault("adaptation_strategies", {}).setdefault(target.value, []).append({"strategy": record["strategy_name"] or sid,
            "confidence": record["confidence"], "strategy_id": sid, "description": strategy.get("description", ""), "knowledge_data": record["knowledge_data"]})
        record["application_duration"] = round(time.time()-started, 6)
        verification = self._verify_strategy_application(strategy, target)
        if not verification["verified"]: verification["revert_result"] = self._revert_strategy_application(strategy, target)
        # La estrategia se aplica siempre; la verificación aparte indica si fue consistente
        return {"applied": True, "verified": verification["verified"], "strategy_id": sid, "strategy_name": record["strategy_name"],
            "target_context": target.value, "application_timestamp": record["application_timestamp"],
            "application_duration": record["application_duration"], "verification_result": verification}

    def _verify_strategy_application(self, strategy: Dict[str, Any], target_context: ContextType) -> Dict[str, Any]:
        strategy = strategy or {}; sid = strategy.get("strategy_id"); data = strategy.get("knowledge_data", {}) or {}; details = {}; consistent = True
        for key, values in data.items() if isinstance(data, dict) else []:
            if isinstance(values, list): details[key] = {"expected_count": len(values), "consistent": bool(values)}; consistent = consistent and bool(values)
        records = [r for r in self.knowledge_base.get("applied_strategies", []) if isinstance(r, dict) and r.get("strategy_id") == sid and not r.get("reverted")]
        applicability = self._calculate_strategy_applicability(data if isinstance(data, dict) else {}, target_context)
        verified = bool(records) and consistent
        return {"verified": verified, "strategy_id": sid, "verification_timestamp": datetime.now().isoformat(),
                "applicability": applicability, "consistency_check": consistent, "consistency_details": details, "revert_needed": not verified}

    def _revert_strategy_application(self, strategy: Dict[str, Any], target_context: ContextType) -> Dict[str, Any]:
        sid = (strategy or {}).get("strategy_id"); stamp = datetime.now().isoformat(); changed = False; applied = False
        for row in self.knowledge_base.get("applied_strategies", []) or []:
            if isinstance(row, dict) and row.get("strategy_id") == sid:
                applied = True
                if not row.get("reverted"):
                    row.update({"reverted": True, "revert_timestamp": stamp, "revert_reason": "strategy_verification_failed"}); changed = True
                else:
                    stamp = row.get("revert_timestamp", stamp)
        target = self._coerce_context(target_context)
        # La reversión es idempotente: una estrategia ya revertida sigue reportándose como revertida
        return {"reverted": bool(changed or applied), "strategy_id": sid, "revert_timestamp": stamp, "reason": "strategy_verification_failed", "target_context": target.value if target else str(target_context)}

    # Representación, propuestas y validación de Goals
    def represent_adaptation(self, original_goal, context_snapshot, adaptation_rules):
        """Crear una copia adaptada del Goal; acepta objetos y diccionarios."""
        get = lambda obj, key, default=None: obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
        set_value = lambda obj, key, value: obj.__setitem__(key, value) if isinstance(obj, dict) else setattr(obj, key, value)
        context = get(context_snapshot, "context_type")
        context = context.value if isinstance(context, ContextType) else context
        metadata = {"original_goal_id": get(original_goal, "id"), "original_goal_type": get(original_goal, "type"),
                    "original_target": get(original_goal, "target"), "adaptation_trigger": context,
                    "applied_rules": [], "changes_made": [], "timestamp": datetime.now().isoformat(),
                    "adapted_goal_id": None}
        rules = [r for r in (adaptation_rules or []) if (r.get("enabled", True) if isinstance(r, dict) else getattr(r, "enabled", True))]
        if original_goal is None or not rules:
            return None, metadata
        adapted = copy.deepcopy(original_goal)
        original_id = get(original_goal, "id", "goal")
        new_id = f"{original_id}_adapted_{int(time.time()*1000)}"
        set_value(adapted, "id", new_id)
        changes = []
        # La prioridad del Goal adaptado la determina la última regla aplicable
        original_priority = get(original_goal, "priority")
        target_priority = None
        for rule in rules:
            rget = lambda key, default=None: rule.get(key, default) if isinstance(rule, dict) else getattr(rule, key, default)
            actions = rget("adaptation_actions", []) or []
            rule_priority = rget("priority")
            if rule_priority is not None and rule_priority != original_priority:
                changes.append(f"priority: {original_priority} -> {rule_priority}")
                target_priority = rule_priority
            if "add_constraints" in actions:
                current = list(get(adapted, "constraints", []) or [])
                additions = [item for item in (rget("constraints", []) or []) if item not in current]
                if additions:
                    set_value(adapted, "constraints", current + additions)
                    changes.append(f"constraints_added: {len(additions)}")
            if "add_metadata" in actions:
                incoming = rget("metadata", {}) or {}
                if incoming:
                    merged = dict(get(adapted, "metadata", {}) or {}); merged.update(incoming)
                    set_value(adapted, "metadata", merged)
                    changes.append("metadata_updated: " + ", ".join(sorted(incoming)))
            if "add_deadline" in actions and rget("deadline") is not None:
                set_value(adapted, "deadline", rget("deadline")); changes.append("deadline_added")
            metadata["applied_rules"].append(rget("rule_id", "unknown"))
        if target_priority is not None:
            set_value(adapted, "priority", target_priority)
        metadata["changes_made"] = changes
        metadata["adapted_goal_id"] = new_id
        return adapted, metadata

    @staticmethod
    def _goal_to_dict(goal) -> Dict[str, Any]:
        if goal is None: return {}
        if isinstance(goal, dict): return copy.deepcopy(goal)
        deadline = getattr(goal, "deadline", None)
        if isinstance(deadline, datetime): deadline = deadline.isoformat()
        return {"id": getattr(goal, "id", None), "type": getattr(goal, "type", None), "target": getattr(goal, "target", None),
                "description": getattr(goal, "description", None), "priority": getattr(goal, "priority", None),
                "constraints": list(getattr(goal, "constraints", None) or []), "metadata": dict(getattr(goal, "metadata", None) or {}), "deadline": deadline}

    @staticmethod
    def _rule_to_dict(rule) -> Dict[str, Any]:
        if rule is None: return {}
        if isinstance(rule, dict): return dict(rule)
        fn = getattr(rule, "to_dict", None)
        if callable(fn):
            try: return fn()
            except Exception: pass
        return {"rule_id": getattr(rule, "rule_id", None), "name": getattr(rule, "name", None), "description": getattr(rule, "description", None),
                "adaptation_actions": list(getattr(rule, "adaptation_actions", []) or []), "priority": getattr(rule, "priority", None),
                "confidence_threshold": getattr(rule, "confidence_threshold", None)}

    @staticmethod
    def _snapshot_to_dict(snapshot) -> Dict[str, Any]:
        if snapshot is None: return {}
        if isinstance(snapshot, dict): return dict(snapshot)
        fn = getattr(snapshot, "to_dict", None)
        if callable(fn):
            try: return fn()
            except Exception: pass
        ctx = getattr(snapshot, "context_type", None)
        return {"snapshot_id": getattr(snapshot, "snapshot_id", None), "context_type": ctx.value if isinstance(ctx, ContextType) else ctx,
                "timestamp": str(getattr(snapshot, "timestamp", "")), "confidence_score": getattr(snapshot, "confidence_score", None)}

    def create_goal_adaptation_proposal(self, original_goal, context_snapshot, adaptation_rules) -> Dict[str, Any]:
        adapted, metadata = self.represent_adaptation(original_goal, context_snapshot, adaptation_rules)
        pid = f"goal_adaptation_{int(time.time()*1000)}"
        proposal = {"proposal_id": pid, "original_goal": self._goal_to_dict(original_goal),
            "adapted_goal": self._goal_to_dict(adapted) if adapted is not None else None,
            "context_snapshot": self._snapshot_to_dict(context_snapshot), "adaptation_rules": [self._rule_to_dict(r) for r in (adaptation_rules or [])],
            "changes_proposed": metadata.get("changes_made", []), "intention_preserved": self._check_intention_preservation(original_goal, adapted),
            "adaptation_metadata": metadata, "proposal_timestamp": datetime.now().isoformat(), "proposal_status": "PENDING", "validation_required": True}
        self.proposals[pid] = proposal; self.knowledge_base.setdefault("goal_adaptation_proposals", []).append(proposal)
        return proposal

    def _validate_adaptation_constraints(self, original_goal, adapted_goal, adaptation_rules) -> List[str]:
        errors: List[str] = []
        data = self._goal_to_dict(adapted_goal)
        constraints = list(data.get("constraints", []) or [])
        for index, left in enumerate(constraints):
            for right in constraints[index + 1:]:
                if self._are_constraints_contradictory(left, right):
                    errors.append(f"Restricciones contradictorias (contradictory constraints): '{left}' y '{right}'")
        priority = data.get("priority")
        if priority is not None:
            try:
                if not 1 <= float(priority) <= 10:
                    errors.append(f"Prioridad fuera de rango (priority out of range 1-10): {priority}")
            except (TypeError, ValueError):
                errors.append(f"Prioridad inválida (invalid priority): {priority}")
        deadline = data.get("deadline")
        if deadline is not None:
            try:
                if isinstance(deadline, datetime): value = deadline.timestamp()
                elif isinstance(deadline, str): value = datetime.fromisoformat(deadline).timestamp()
                else: value = float(deadline)
                if value < time.time(): errors.append(f"Deadline en el pasado (deadline in the past): {deadline}")
            except (TypeError, ValueError, OSError):
                errors.append(f"Deadline no comparable (deadline not comparable): {deadline}")
        if not self._check_intention_preservation(original_goal, adapted_goal):
            errors.append("La adaptación no preserva la intención original del Goal (intention not preserved)")
        return errors

    @staticmethod
    def _are_constraints_contradictory(constraint_a, constraint_b) -> bool:
        if not constraint_a or not constraint_b: return False
        pair = {str(constraint_a).strip().lower(), str(constraint_b).strip().lower()}
        return pair in ({"maximize", "minimize"}, {"show", "hide"}, {"enable", "disable"})

    def _check_intention_preservation(self, original_goal, adapted_goal) -> bool:
        if original_goal is None or adapted_goal is None: return adapted_goal is None
        original, adapted = self._goal_to_dict(original_goal), self._goal_to_dict(adapted_goal)
        if original.get("type") != adapted.get("type"): return False
        a, b = original.get("target"), adapted.get("target")
        if original.get("type") == "navigate": return self._targets_equivalent(a, b)
        if isinstance(a, dict) and isinstance(b, dict) and ("app_name" in a or "app_name" in b): return a.get("app_name") == b.get("app_name")
        return a == b

    @staticmethod
    def _targets_equivalent(a, b) -> bool:
        if a == b: return True
        if not isinstance(a, str) or not isinstance(b, str): return False
        try: ua, ub = urlparse(a), urlparse(b)
        except Exception: return False
        if not ua.netloc or not ub.netloc: return False
        return (ua.netloc.lower(), ua.path.rstrip("/"), ua.params, ua.query) == (ub.netloc.lower(), ub.path.rstrip("/"), ub.params, ub.query)

    def _validate_goal_structure(self, goal) -> Dict[str, Any]:
        data = self._goal_to_dict(goal); errors = []; warnings = []
        if not data.get("id"): errors.append("El Goal no tiene identificador")
        if not data.get("type"): errors.append("El Goal no tiene tipo")
        if data.get("target") in (None, ""): errors.append("El Goal no tiene objetivo (target)")
        if not data.get("description"): warnings.append("El Goal no tiene descripción")
        priority = data.get("priority")
        if priority is not None:
            try:
                if not 1 <= float(priority) <= 10: errors.append(f"Prioridad fuera de rango (priority out of range): {priority}")
            except (TypeError, ValueError): errors.append(f"Prioridad inválida (invalid priority): {priority}")
        return {"valid": not errors, "errors": errors, "warnings": warnings}

    def _validate_current_state(self, state) -> Dict[str, Any]:
        if not isinstance(state, dict): return {"valid": False, "errors": ["State debe ser un diccionario"], "warnings": []}
        warnings = [f"Clave ausente en el State: {key}" for key in ("current_url", "active_applications", "system_resources") if key not in state]
        return {"valid": True, "errors": [], "warnings": warnings}

    @staticmethod
    def _required_capabilities_for_goal(goal) -> List[str]:
        kind = goal.get("type") if isinstance(goal, dict) else getattr(goal, "type", None)
        return {"navigate": ["navigate"], "open_application": ["open_application"], "focus_element": ["focus_element"],
                "click": ["focus_element"], "type_text": ["type_text"], "press_key": ["press_key"]}.get(kind, [kind] if kind else [])

    def _validate_capabilities(self, goal, available_capabilities) -> Dict[str, Any]:
        available = list(available_capabilities or []); required = self._required_capabilities_for_goal(goal)
        missing = [item for item in required if item not in available]; errors = ["Capacidades faltantes: " + ", ".join(missing)] if missing else []
        return {"valid": not errors, "errors": errors, "warnings": [], "required": required, "available": available}

    def _validate_goal_preconditions(self, goal, current_state) -> Dict[str, Any]:
        data = self._goal_to_dict(goal); errors = []; warnings = []
        if data.get("type") == "navigate":
            target = data.get("target")
            if not isinstance(target, str) or not target.startswith(("http://", "https://")): errors.append("URL de navegación inválida")
            else:
                current_url = current_state.get("current_url") if isinstance(current_state, dict) else None
                if current_url:
                    if self._targets_equivalent(current_url, target): warnings.append("Ya estamos en la URL destino")
                    else: warnings.append("No estamos en la URL destino")
        return {"valid": not errors, "errors": errors, "warnings": warnings}

    def _validate_planner_can_solve(self, goal, current_state) -> Dict[str, Any]:
        result = {"status": None, "plan_id": None, "execution_time": 0., "quality": None, "warnings": [], "metadata": {}}
        if Planner is None: result["error"] = "Planner no disponible"; return result
        try:
            plan = Planner().plan_with_htn_integration(goal, current_state); status = getattr(plan, "status", None)
            normalized_status = getattr(status, "value", status)
            result.update({"status": status if (PlannerStatus is not None and isinstance(status, PlannerStatus)) else normalized_status,
                "plan_id": getattr(plan, "plan_id", None),
                "execution_time": getattr(plan, "execution_time", 0.), "quality": getattr(getattr(plan, "quality", None), "value", getattr(plan, "quality", None)),
                "warnings": list(getattr(plan, "warnings", None) or []), "metadata": dict(getattr(plan, "metadata", None) or {})})
            completed_status = getattr(PlannerStatus, "COMPLETED", None) if PlannerStatus is not None else None
            completed_value = getattr(completed_status, "value", completed_status)
            if status is None or (completed_value is not None and normalized_status != completed_value):
                result["error"] = "El Planner no pudo verificar el plan: Goal no puede resolver el Goal adaptado"
        except Exception as exc: result["error"] = f"El Planner no pudo verificar el plan: Goal no puede resolver el Goal adaptado ({exc})"
        return result

    def validate_adapted_goal(self, original_goal, adapted_goal, current_state, available_capabilities) -> Dict[str, Any]:
        """Validar estructura, intención, capacidades, precondiciones y resolubilidad del Goal adaptado."""
        structure = self._validate_goal_structure(adapted_goal)
        state_validation = self._validate_current_state(current_state)
        capabilities_validation = self._validate_capabilities(adapted_goal, available_capabilities)
        preconditions_validation = self._validate_goal_preconditions(adapted_goal, current_state)
        planner_result = self._validate_planner_can_solve(adapted_goal, current_state)
        constraints = self._validate_adaptation_constraints(original_goal, adapted_goal, [])
        errors: List[str] = []
        warnings: List[str] = []
        for result in (structure, state_validation, capabilities_validation, preconditions_validation):
            errors.extend(result.get("errors", []))
            warnings.extend(result.get("warnings", []))
        intention_preserved = self._check_intention_preservation(original_goal, adapted_goal)
        if not intention_preserved:
            errors.append("La adaptación no preserva la intención original del Goal")
        errors.extend(constraints)
        if planner_result.get("error"):
            # La ausencia del Planner impide certificar resolubilidad, pero se informa
            # como advertencia para mantener compatibles instalaciones que no lo incluyen.
            warnings.append(planner_result["error"])
        status = planner_result.get("status")
        normalized_status = getattr(status, "value", status)
        completed_status = getattr(PlannerStatus, "COMPLETED", None) if PlannerStatus is not None else None
        completed_value = getattr(completed_status, "value", completed_status)
        if status is not None and completed_value is not None and normalized_status != completed_value:
            errors.append("El Planner no pudo completar un plan para el Goal adaptado")
        details = {"goal_structure": structure, "intention_preserved": intention_preserved,
                   "adaptation_constraints": constraints, "planner_resolvable": not bool(planner_result.get("error")) and (status is None or completed_value is None or normalized_status == completed_value)}
        return {"valid": not errors, "errors": errors, "warnings": warnings,
                "validation_details": details, "state_validation": state_validation,
                "capabilities_validation": capabilities_validation,
                "preconditions_validation": preconditions_validation, "planner_result": planner_result}


    def _register_validation_result(self, original_goal_id, adapted_goal_id, validation_result) -> None:
        self.knowledge_base.setdefault("goal_validations", []).append({"original_goal_id": original_goal_id,
            "adapted_goal_id": adapted_goal_id, "validation_result": validation_result, "timestamp": datetime.now().isoformat()})

    # Feedback persistente de adaptación de Goal
    def _capture_feedback(self, adaptation_result: Dict[str, Any]) -> Dict[str, Any]:
        data = adaptation_result or {}
        feedback = {"success": True, "adaptation_id": data.get("adaptation_id"),
            "original_goal_id": data.get("original_goal_id"), "adapted_goal_id": data.get("adapted_goal_id"),
            "adaptation_context": data.get("adaptation_context", {}) or {}, "execution_result": data.get("execution_result", {}) or {},
            "verification_result": data.get("verification_result", {}) or {}, "improvement_analysis": self._analyze_adaptation_improvement(data),
            "timestamp": datetime.now().isoformat()}
        self.knowledge_base.setdefault("goal_adaptation_feedback", []).append(feedback)
        return feedback

    def _analyze_adaptation_improvement(self, adaptation_result: Dict[str, Any]) -> Dict[str, Any]:
        data = adaptation_result or {}; expected = (data.get("adaptation_context", {}) or {}).get("expected_metrics", {}) or {}
        actual = (data.get("execution_result", {}) or {}).get("performance_metrics", {}) or {}; improvements = {}; evidence = []
        for metric in ("response_time", "accuracy"):
            if metric not in expected or metric not in actual: continue
            try: before, after = float(expected[metric]), float(actual[metric])
            except (TypeError, ValueError): continue
            if before == 0: continue
            delta = ((before-after)/abs(before)*100.) if metric == "response_time" else ((after-before)/abs(before)*100.)
            improvements[metric] = round(delta, 2); evidence.append(f"{metric} mejorado en {delta:.2f}%" if delta > 0 else f"{metric} no mejorado ({delta:.2f}%)")
        return {"improved": any(value > 0 for value in improvements.values()), "improvements": improvements, "evidence": evidence}

    def _capture_goal_adaptation_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            required = ("adaptation_id", "original_goal_id", "adapted_goal_id", "adaptation_context", "execution_result", "verification_result")
            if not isinstance(feedback_data, dict) or not all(key in feedback_data for key in required): raise ValueError("Datos de feedback incompletos")
            execution = feedback_data["execution_result"] or {}; verification = feedback_data["verification_result"] or {}
            raw = execution.get("performance_metrics", {}) or {}
            metrics = {"response_time": self._safe_float(raw.get("response_time", 0.)), "accuracy": self._safe_float(raw.get("accuracy", 0.)),
                       "success": bool(execution.get("success", False)), "verified": bool(verification.get("verified", False)),
                       "impact_score": self._safe_float(verification.get("impact_score", 0.))}
            originals = feedback_data.get("original_metrics") or (feedback_data.get("adaptation_context", {}) or {}).get("expected_metrics", {}) or {}
            changes = {}
            for metric in ("response_time", "accuracy"):
                before, after = self._safe_float(originals.get(metric, 0.)), self._safe_float(metrics.get(metric, 0.))
                if before: changes[metric] = (before-after)/abs(before)*100. if metric == "response_time" else (after-before)/abs(before)*100.
            improvement_values = list(changes.values())
            analysis = {"performance_improvement": sum(improvement_values)/len(improvement_values) if improvement_values else 0.,
                        "resource_efficiency": 0., "response_time_improvement": changes.get("response_time", 0.),
                        "accuracy_improvement": changes.get("accuracy", 0.), "pattern_recognition": [], "strategic_insights": []}
            is_success = metrics["success"] and metrics["verified"]
            analysis["pattern_recognition"].append({"pattern_type": "goal_adaptation_success" if is_success else "goal_adaptation_failure",
                "context": feedback_data["adaptation_context"], "metrics": metrics, "timestamp": datetime.now().isoformat(), "confidence": .9 if is_success else .8})
            if metrics["impact_score"] > .7:
                analysis["strategic_insights"].append({"strategy_type": "adaptation_strategies", "context": feedback_data["adaptation_context"],
                    "metrics": metrics, "timestamp": datetime.now().isoformat(), "confidence": .85})
            self._record_feedback_analysis(feedback_data["adaptation_id"], analysis)
            self._record_adaptation_history(feedback_data["adaptation_id"], analysis, feedback_data["adaptation_context"])
            return {"success": True, "adaptation_id": feedback_data["adaptation_id"], "original_goal_id": feedback_data["original_goal_id"],
                "adapted_goal_id": feedback_data["adapted_goal_id"], "improvement_analysis": analysis, "feedback_metrics": metrics,
                "adaptation_context": feedback_data["adaptation_context"], "timestamp": datetime.now().isoformat()}
        except Exception as exc:
            self.logger.error("Error capturando feedback de Goal: %s", exc)
            return {"success": False, "adaptation_id": feedback_data.get("adaptation_id") if isinstance(feedback_data, dict) else None,
                    "error_message": str(exc), "feedback_metrics": {}, "adaptation_context": feedback_data.get("adaptation_context", {}) if isinstance(feedback_data, dict) else {}}

    def _execute_goal_adaptation_learning_loop(self, feedback_result: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not feedback_result.get("success"):
                return {"success": False, "message": "No se puede aprender de un feedback fallido", "learned_patterns": [], "adaptation_strategies": {}}
            analysis = feedback_result.get("improvement_analysis", {})
            patterns = self._analyze_learning_patterns(analysis.get("pattern_recognition", []), feedback_result.get("feedback_metrics", {}))
            strategies = self._update_adaptive_strategies(patterns, self.knowledge_base.get("adaptation_strategies", {}))
            convergence = self._calculate_learning_convergence(feedback_result.get("feedback_metrics", {}), self._safe_float(analysis.get("performance_improvement", 0.)))
            self._record_learning_results(feedback_result.get("adaptation_id", "unknown"), patterns, strategies, convergence)
            return {"success": True, "learned_patterns": patterns, "adaptation_strategies": strategies, "convergence_metrics": convergence, "timestamp": datetime.now().isoformat()}
        except Exception as exc:
            self.logger.error("Error en bucle de aprendizaje Goal: %s", exc)
            return {"success": False, "error_message": str(exc), "learned_patterns": [], "adaptation_strategies": {}, "convergence_metrics": {}}

    def _analyze_learning_patterns(self, patterns: List[Dict[str, Any]], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        output = []
        for pattern in patterns or []:
            if not isinstance(pattern, dict): continue
            confidence = self._safe_float(pattern.get("confidence", 0.)); impact = self._safe_float(metrics.get("impact_score", 0.))
            if impact > .7: confidence = min(1., confidence*1.2)
            elif impact < .3: confidence = max(0., confidence*.8)
            output.append({"pattern_id": f"pattern_{len(output)+1}_{int(time.time()*1000)}", "pattern_type": pattern.get("pattern_type", "unknown"),
                "context": pattern.get("context", {}), "metrics": pattern.get("metrics", {}), "confidence": confidence,
                "timestamp": pattern.get("timestamp", datetime.now().isoformat()), "description": self._generate_pattern_description(pattern)})
        return output

    def _update_adaptive_strategies(
        self,
        learned_patterns: List[Dict[str, Any]],
        current_strategies: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Actualizar estrategias manteniendo el contrato ``contexto -> lista``.

        Las versiones anteriores añadían IDs de estrategias en la raíz del mapa,
        que se interpreta en otros métodos como un mapa de contextos. Esta versión
        normaliza datos heredados y modifica solo la lista del contexto pertinente.
        """
        updated: Dict[str, Any] = {}
        if isinstance(current_strategies, dict):
            for key, value in current_strategies.items():
                if isinstance(value, list):
                    updated[str(key)] = copy.deepcopy([x for x in value if isinstance(x, dict)])
                elif isinstance(value, dict):
                    # Migrar entradas planas antiguas al contexto indicado en la entrada.
                    # Sin ``strategy_id`` la estrategia se descarta al reiniciar el motor.
                    strategy = copy.deepcopy(value)
                    strategy.setdefault("strategy_id", str(key))
                    context_info = strategy.get("context", {})
                    ctx = context_info.get("context_type") if isinstance(context_info, dict) else None
                    ctx = self._coerce_context(ctx)
                    updated.setdefault(ctx.value if ctx else ContextType.IDLE.value, []).append(strategy)

        for pattern in learned_patterns or []:
            if not isinstance(pattern, dict):
                continue
            pattern_type = pattern.get("pattern_type")
            context_info = pattern.get("context", {})
            context_name = context_info.get("context_type") if isinstance(context_info, dict) else None
            context = self._coerce_context(context_name) or (
                self.current_context.context_type if self.current_context else ContextType.IDLE
            )
            rows = updated.setdefault(context.value, [])

            if pattern_type == "goal_adaptation_success":
                stamp = int(time.time() * 1000)
                strategy_id = f"strategy_{stamp}_{len(rows)}"
                rows.append({
                    "strategy_id": strategy_id,
                    "strategy_type": "adaptation_strategies",
                    "strategy": f"goal_adaptation_{context.value}",
                    "context": copy.deepcopy(context_info) if isinstance(context_info, dict) else {"context_type": context.value},
                    "pattern_id": pattern.get("pattern_id"),
                    "metrics": copy.deepcopy(pattern.get("metrics", {})),
                    "confidence": self._bounded_float(pattern.get("confidence", 0.0), 0.0, 1.0),
                    "success_rate": 0.9,
                    "last_updated": datetime.now().isoformat(),
                    "description": self._generate_strategy_description(pattern),
                    "applied_rules": [],
                    "failure_count": 0,
                })
            elif pattern_type == "goal_adaptation_failure":
                pattern_id = pattern.get("pattern_id")
                for strategies in updated.values():
                    for strategy in strategies:
                        if strategy.get("pattern_id") == pattern_id:
                            strategy["failure_count"] = int(strategy.get("failure_count", 0)) + 1
                            strategy["confidence"] = self._bounded_float(
                                self._safe_float(strategy.get("confidence", 0.5)) * 0.9, 0.0, 1.0
                            )
        return updated

    def _calculate_learning_convergence(self, metrics: Dict[str, Any], improvement: float) -> Dict[str, Any]:
        result = {"convergence_status": "incomplete", "convergence_score": 0., "learning_rate": 0., "stability": 0., "trend": "unknown", "timestamp": datetime.now().isoformat()}
        if metrics.get("success") and metrics.get("verified"):
            result["convergence_status"] = "partial"; result["convergence_score"] = self._bounded_float(improvement/100., 0., 1.)
            recent = [self._extract_performance_improvement(x) for x in self.adaptation_history[-10:]]
            result["learning_rate"] = sum(recent)/len(recent)/10. if recent else 0.
            values = recent[-5:]
            if values:
                scale = max(abs(x) for x in values); result["stability"] = self._bounded_float(1.-float(np.std(values))/scale if scale else 1., 0., 1.)
            result["trend"] = "improving" if improvement > .2 else "deteriorating" if improvement < -.2 else "stable"
        return result

    def _record_feedback_analysis(self, adaptation_id: str, analysis: Dict[str, Any]) -> None:
        records = self.knowledge_base.setdefault("goal_adaptation_feedback", [])
        records.append({"adaptation_id": adaptation_id, "analysis": analysis, "timestamp": datetime.now().isoformat(), "status": "processed"})
        del records[:-1000]; self._save_goal_adaptation_feedback()

    def _record_adaptation_history(self, adaptation_id: str, analysis: Dict[str, Any], adaptation_context: Dict[str, Any]) -> None:
        entry = _AdaptationHistoryEntry({"adaptation_id": adaptation_id,
            "performance_impact": {"performance_improvement": self._safe_float(analysis.get("performance_improvement", 0.)),
                "response_time_improvement": self._safe_float(analysis.get("response_time_improvement", 0.)),
                "accuracy_improvement": self._safe_float(analysis.get("accuracy_improvement", 0.))},
            "context": adaptation_context, "timestamp": datetime.now().isoformat(),
            "success": bool((analysis.get("pattern_recognition") or [{}])[0].get("pattern_type") == "goal_adaptation_success")})
        self.adaptation_history.append(entry); del self.adaptation_history[:-1000]; self._save_goal_adaptation_feedback()

    @staticmethod
    def _extract_performance_improvement(entry: Dict[str, Any]) -> float:
        try:
            impact = entry.get("performance_impact", 0.)
            return float(impact.get("performance_improvement", 0.) or 0.) if isinstance(impact, dict) else float(impact or 0.)
        except (TypeError, ValueError): return 0.

    def _record_learning_results(self, adaptation_id: str, patterns: List[Dict[str, Any]], strategies: Dict[str, Any], convergence: Dict[str, Any]) -> None:
        if strategies: self.knowledge_base["adaptation_strategies"] = strategies
        rows = self.knowledge_base.setdefault("learning_results", [])
        rows.append({"adaptation_id": adaptation_id, "learned_patterns": patterns, "updated_strategies": strategies,
                     "convergence_metrics": convergence, "timestamp": datetime.now().isoformat(), "status": "completed"})
        del rows[:-500]; self._save_goal_adaptation_learning_results()

    def _generate_pattern_description(self, pattern: Dict[str, Any]) -> str:
        pattern = pattern if isinstance(pattern, dict) else {}
        context = pattern.get("context", {})
        context = context if isinstance(context, dict) else {}
        metrics = pattern.get("metrics", {})
        metrics = metrics if isinstance(metrics, dict) else {}
        return (
            f"Patrón {pattern.get('pattern_type', 'desconocido')} para "
            f"{context.get('goal_type', 'Goal')} en {context.get('context_type', 'contexto')}; "
            f"tiempo={self._safe_float(metrics.get('response_time', 0.)):.2f}, "
            f"precisión={self._safe_float(metrics.get('accuracy', 0.)):.2f}"
        )

    def _generate_strategy_description(self, pattern: Dict[str, Any]) -> str:
        pattern = pattern if isinstance(pattern, dict) else {}
        context = pattern.get("context", {})
        context = context if isinstance(context, dict) else {}
        metrics = pattern.get("metrics", {})
        metrics = metrics if isinstance(metrics, dict) else {}
        return (
            f"Estrategia para {context.get('goal_type', 'Goal')} en {context.get('context_type', 'contexto')}; "
            f"tiempo={self._safe_float(metrics.get('response_time', 0.)):.2f}, "
            f"precisión={self._safe_float(metrics.get('accuracy', 0.)):.2f}"
        )

    # --- Persistencia de estrategias aprendidas (2.8.8.9.2.6) ---
    def _flatten_strategy_map(self, strategies: Any) -> Dict[str, Dict[str, Any]]:
        """Normalizar el mapa de estrategias al índice plano ``strategy_id -> entrada``.

        Acepta el mapa por contexto (``contexto -> lista``) que el motor mantiene en
        memoria y el índice plano que se persiste en disco, de modo que ambos
        formatos produzcan la misma representación plana.
        """
        flat: Dict[str, Dict[str, Any]] = {}
        if not isinstance(strategies, dict): return flat
        for key, value in strategies.items():
            if isinstance(value, dict):
                if not value: continue
                entry = copy.deepcopy(value)
                flat.setdefault(str(entry.get("strategy_id") or key), entry)
                continue
            if not isinstance(value, list): continue
            for position, entry in enumerate(value):
                if not isinstance(entry, dict): continue
                normalized = copy.deepcopy(entry)
                sid = str(normalized.get("strategy_id") or f"strategy_{key}_{position}")
                normalized.setdefault("strategy_id", sid)
                flat.setdefault(sid, normalized)
        return flat

    def _known_strategy_ids(self) -> set:
        """Identificadores de estrategias ya presentes en el mapa ``contexto -> lista``."""
        target = self.knowledge_base.get("adaptation_strategies", {})
        if not isinstance(target, dict): return set()
        return {str(x.get("strategy_id")) for rows in target.values() if isinstance(rows, list)
                for x in rows if isinstance(x, dict) and x.get("strategy_id")}

    def _project_strategies_by_context(self, flat: Dict[str, Dict[str, Any]]) -> None:
        """Proyectar el índice plano de estrategias sobre el mapa ``contexto -> lista`` del motor.

        El mapa ``adaptation_strategies`` sigue el contrato ``contexto -> lista``
        (2.8.5/2.8.6); el índice plano es solo la forma de persistencia. La
        proyección evita duplicar entradas ya presentes en el motor.
        """
        if not flat: return
        target = self.knowledge_base.setdefault("adaptation_strategies", {})
        if not isinstance(target, dict): return
        known = self._known_strategy_ids()
        for sid, entry in flat.items():
            if not isinstance(entry, dict): continue
            if str(sid) in known: continue
            context_info = entry.get("context") if isinstance(entry.get("context"), dict) else {}
            ctx = self._coerce_context(context_info.get("context_type")) or ContextType.IDLE
            rows = target.get(ctx.value)
            if not isinstance(rows, list): rows = []; target[ctx.value] = rows
            normalized = copy.deepcopy(entry); normalized.setdefault("strategy_id", str(sid))
            rows.append(normalized); known.add(str(sid))

    def _merge_strategies_by_context(self, source: Any) -> None:
        """Integrar un mapa ``contexto -> lista`` de estrategias en el mapa del motor.

        Se usa al cargar para restaurar el contexto exacto con el que se aprendió
        cada estrategia, que el índice plano no puede expresar por sí solo.
        """
        if not isinstance(source, dict): return
        target = self.knowledge_base.setdefault("adaptation_strategies", {})
        if not isinstance(target, dict): return
        for ctx, rows in source.items():
            if not isinstance(rows, list): continue
            bucket = target.get(str(ctx))
            if not isinstance(bucket, list): bucket = []; target[str(ctx)] = bucket
            known = {str(x.get("strategy_id")) for x in bucket if isinstance(x, dict) and x.get("strategy_id")}
            for entry in rows:
                if not isinstance(entry, dict): continue
                sid = str(entry.get("strategy_id") or "")
                if sid and sid in known: continue
                if sid: known.add(sid)
                bucket.append(copy.deepcopy(entry))

    def _save_goal_adaptation_feedback(self) -> None:
        try:
            path = os.path.join(self.data_dir, "goal_adaptation_feedback.json"); os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {"goal_adaptation_feedback": self.knowledge_base.get("goal_adaptation_feedback", []),
                       "adaptation_history": [self._serializable_history(x) for x in self.adaptation_history], "last_updated": datetime.now().isoformat()}
            with open(path, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
        except Exception as exc: self.logger.error("Error guardando feedback Goal: %s", exc)

    # Contrato de DATOS CRÍTICOS (item 5): un patrón de aprendizaje solo se
    # persiste si está VALIDADO, es decir si (a) su `confidence` alcanza el
    # umbral configurado en el motor y (b) tiene un mínimo de observaciones
    # similares. La identidad real de un patrón es `pattern_type` junto al
    # contexto que lo produjo (`goal_type` + `context_type`): el `pattern_id`
    # NO sirve para agrupar porque se regenera en cada llamada
    # (`f"pattern_{n}_{int(time.time()*1000)}"`).
    @staticmethod
    def _pattern_identity(pattern: Dict[str, Any]) -> Tuple[str, str, str]:
        """Identidad estable de un patrón de aprendizaje.

        Agrupa las observaciones que describen el mismo patrón: mismo
        `pattern_type` y mismo contexto (`goal_type` + `context_type`).
        """
        context = pattern.get("context") or {}
        if not isinstance(context, dict): context = {}
        return (str(pattern.get("pattern_type", "unknown")),
                str(context.get("goal_type", "unknown")),
                str(context.get("context_type", "unknown")))

    def _count_pattern_observations(self, learning_results: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], int]:
        """Contar las observaciones similares acumuladas por cada patrón."""
        counts: Dict[Tuple[str, str, str], int] = {}
        for row in learning_results or []:
            if not isinstance(row, dict): continue
            for pattern in row.get("learned_patterns") or []:
                if not isinstance(pattern, dict): continue
                identity = self._pattern_identity(pattern)
                counts[identity] = counts.get(identity, 0) + 1
        return counts

    def _is_validated_pattern(self, pattern: Dict[str, Any], observations: Dict[Tuple[str, str, str], int]) -> bool:
        """Comprobar si un patrón cumple el contrato de datos validados.

        Exige `confidence >= confidence_threshold` (configurado en el motor) y
        un mínimo de `min_similar_observations` observaciones similares.
        """
        threshold = self._safe_float(self.config.get("confidence_threshold", .7), .7)
        if self._safe_float(pattern.get("confidence", 0.)) < threshold: return False
        minimum = int(self._safe_float(self.config.get("min_similar_observations", 3), 3))
        return observations.get(self._pattern_identity(pattern), 0) >= minimum

    def _filter_validated_learning_results(self, learning_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dejar en `learning_results` únicamente los patrones validados.

        Se conservan las filas con su `adaptation_id`, `updated_strategies` y
        `convergence_metrics`: la regla de datos que no deben persistir
        afecta solo a los patrones no validados, no a las filas de resultados
        de aprendizaje (de las que depende la restauración de estrategias).
        """
        observations = self._count_pattern_observations(learning_results)
        filtered: List[Dict[str, Any]] = []
        for row in learning_results or []:
            if not isinstance(row, dict):
                filtered.append(row); continue
            row = copy.deepcopy(row)
            row["learned_patterns"] = [pattern for pattern in (row.get("learned_patterns") or [])
                                       if isinstance(pattern, dict) and self._is_validated_pattern(pattern, observations)]
            filtered.append(row)
        return filtered

    def _save_goal_adaptation_learning_results(self) -> None:
        try:
            path = os.path.join(self.data_dir, "goal_adaptation_learning_results.json"); os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Contrato de DATOS CRÍTICOS (2.8.8.9.2.1): una estrategia aprendida se
            # identifica por ``strategy_id`` y aporta evidencia en ``confidence``,
            # ``success_rate`` y ``last_updated``. ``failure_count`` es un contador y no
            # un identificador: su ausencia significa "cero fallos" (misma semántica que
            # aplica el motor al incrementarlo en ``_update_adaptive_strategies``), por
            # lo que se normaliza a 0 en vez de descartar la estrategia aprendida.
            IDENTITY_FIELDS = ("strategy_id", "confidence", "success_rate", "last_updated")
            COUNTER_DEFAULTS = {"failure_count": 0}
            
            strategies_map = self.knowledge_base.get("adaptation_strategies", {})
            learned_strategies = {}
            
            for context, entries in strategies_map.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    # Solo persistir entradas que cumplan el contrato de estrategias aprendidas
                    if not all(entry.get(field) is not None for field in IDENTITY_FIELDS):
                        continue
                    normalized = copy.deepcopy(entry)
                    for field, default in COUNTER_DEFAULTS.items():
                        if normalized.get(field) is None:
                            normalized[field] = default
                    # Asegurar que el contexto se preserva correctamente
                    if "context" not in normalized:
                        normalized["context"] = {
                            "goal_type": normalized.get("goal_type", "unknown"),
                            "context_type": context,
                            "expected_metrics": normalized.get("expected_metrics", {})
                        }
                    learned_strategies[str(normalized["strategy_id"])] = normalized
            
            # Contrato de DATOS CRÍTICOS (item 5, 2.8.8.9.4.3): `learning_results`
            # se persiste con los patrones validados únicamente. Un patrón está
            # validado si su `confidence` alcanza `confidence_threshold` y tiene
            # un mínimo de `min_similar_observations` observaciones similares.
            # `adaptation_strategies` NO se toca (contrato del item 4, cerrado en
            # 2.8.8.9.3.6).
            payload = {"learning_results": self._filter_validated_learning_results(self.knowledge_base.get("learning_results", [])),
                       "adaptation_strategies": learned_strategies,
                       "last_updated": datetime.now().isoformat()}
            with open(path, "w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
        except Exception as exc: self.logger.error("Error guardando resultados de aprendizaje: %s", exc)

    def _load_goal_adaptation_feedback(self) -> None:
        path = os.path.join(self.data_dir, "goal_adaptation_feedback.json")
        if not os.path.isfile(path): return
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            self.knowledge_base["goal_adaptation_feedback"] = payload.get("goal_adaptation_feedback", [])
            history = payload.get("adaptation_history", [])
            if history: self.adaptation_history = [_AdaptationHistoryEntry(row) for row in history if isinstance(row, dict)]
        except Exception as exc: self.logger.error("Error cargando feedback Goal: %s", exc)

    def _load_goal_adaptation_learning_results(self) -> None:
        path = os.path.join(self.data_dir, "goal_adaptation_learning_results.json")
        if not os.path.isfile(path): return
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            if not isinstance(payload, dict): return
            self.knowledge_base["learning_results"] = payload.get("learning_results", self.knowledge_base.get("learning_results", []))
            # El contexto exacto con el que se aprendieron las estrategias solo
            # consta en `updated_strategies` de cada resultado de aprendizaje, así
            # que se restaura primero; el índice plano completa las que falten.
            for record in self.knowledge_base.get("learning_results", []) or []:
                if isinstance(record, dict): self._merge_strategies_by_context(record.get("updated_strategies"))
            strategies = payload.get("adaptation_strategies", {})
            flat = self._flatten_strategy_map(strategies)
            if flat: self._project_strategies_by_context(flat)
        except Exception as exc: self.logger.error("Error cargando aprendizaje Goal: %s", exc)

    def _initialize_goal_adaptation_persistence(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True); self._load_goal_adaptation_feedback(); self._load_goal_adaptation_learning_results()
        self.knowledge_base.setdefault("goal_adaptation_feedback", []); self.knowledge_base.setdefault("learning_results", []); self.knowledge_base.setdefault("adaptation_strategies", {})

    # Integración de evolución arquitectónica
    def set_architecture_manager(self, architecture_manager) -> None:
        self.architecture_manager = architecture_manager
        self.logger.info("ContextualAdaptationEngine conectado al ArchitecturalEvolutionManager")

    def update_architecture_state(self, architecture_state: Dict[str, Any]) -> None:
        self.architecture_state = dict(architecture_state) if isinstance(architecture_state, dict) else {}

    def update_components(self, components: List[Dict[str, Any]]) -> None:
        self.recent_components = list(components or [])

    def process_architectural_result(self, architectural_result: Dict[str, Any]) -> Dict[str, Any]:
        stamp = datetime.now().isoformat(); self.knowledge_base.setdefault("architectural_results", []).append({"result": architectural_result, "timestamp": stamp, "context_type": self.current_context.context_type.value if self.current_context else None}); return {"processed": True, "timestamp": stamp}

    def process_evidence_registration(self, verification_id: str, evidence_record: Dict[str, Any]) -> Dict[str, Any]:
        stamp = datetime.now().isoformat(); self.knowledge_base.setdefault("evidence_registrations", []).append({"verification_id": verification_id, "evidence": evidence_record, "timestamp": stamp}); return {"processed": True, "verification_id": verification_id, "timestamp": stamp}

    def on_proposal_created(self, proposal) -> Dict[str, Any]:
        pid = proposal.get("proposal_id") if isinstance(proposal, dict) else str(proposal); stamp = datetime.now().isoformat(); ctx = self.current_context.context_type.value if self.current_context else None
        self.knowledge_base.setdefault("proposals_notified", []).append({"proposal_id": pid, "timestamp": stamp, "context_type": ctx})
        return {"received": True, "proposal_id": pid, "timestamp": stamp, "context_type": ctx}

    # Bucle, estado y resúmenes
    def start_contextual_adaptation_loop(self) -> None:
        if self._loop_thread and self._loop_thread.is_alive(): return
        self._loop_stop.clear(); self.config["adaptation_enabled"] = True
        def loop():
            while not self._loop_stop.is_set() and self.config.get("adaptation_enabled", True):
                try:
                    snapshot = self.capture_context_snapshot(); rules = self.analyze_contextual_patterns(snapshot)
                    if rules: self.execute_adaptation(snapshot, rules)
                except Exception as exc: self.logger.error("Error en bucle de adaptación: %s", exc)
                self._loop_stop.wait(max(1., self._safe_float(self.config.get("context_analysis_interval", 30.))))
        self._loop_thread = threading.Thread(target=loop, name="ContextualAdaptationLoop", daemon=True); self._loop_thread.start()

    def stop_contextual_adaptation_loop(self) -> None:
        self.config["adaptation_enabled"] = False; self._loop_stop.set(); self.logger.info("Bucle de adaptación contextual detenido")

    def get_adaptation_summary(self) -> Dict[str, Any]:
        if not self.adaptation_history: return {"message": "No adaptations performed yet", "total_adaptations": 0}
        results = self.adaptation_history
        def value(row, name, default=None): return getattr(row, name, row.get(name, default) if isinstance(row, dict) else default)
        success = sum(bool(value(row, "success", False)) for row in results); levels = {}
        for row in results:
            level = value(row, "adaptation_level"); level = level.value if isinstance(level, AdaptationLevel) else str(level or "unknown"); levels[level] = levels.get(level, 0)+1
        confidence = [self._safe_float(value(row, "confidence_score", 0.)) for row in results]
        impacts = [self._extract_performance_improvement(row if isinstance(row, dict) else {"performance_impact": value(row, "performance_impact", {})}) for row in results]
        return {"total_adaptations": len(results), "successful_adaptations": success, "failed_adaptations": len(results)-success,
                "success_rate": success/len(results), "adaptation_levels": levels, "average_confidence": float(np.mean(confidence)),
                "average_performance_impact": float(np.mean(impacts)), "current_context": self.current_context.context_type.value if self.current_context else None,
                "current_adaptation_level": self.adaptation_level.value, "last_adaptation": value(results[-1], "adaptation_id"),
                "active_modes": {"lightweight": self._lightweight_mode, "offline": self._offline_mode, "performance": self._performance_mode, "recovery": self._recovery_mode, "safe": self._safe_mode}}

    def get_context_insights(self) -> Dict[str, Any]:
        snapshots = list(self.context_snapshots.values())
        if not snapshots: return {"message": "No context snapshots available", "total_snapshots": 0}
        counts = {}
        for snapshot in snapshots: counts[snapshot.context_type.value] = counts.get(snapshot.context_type.value, 0)+1
        average_confidence = float(np.mean([s.confidence_score for s in snapshots]))
        return {"total_snapshots": len(snapshots), "context_distribution": counts, "average_confidence": average_confidence,
                "average_system_load": float(np.mean([s.system_metrics.get("system_load", 0.) for s in snapshots])),
                "average_error_rate": float(np.mean([s.performance_metrics.get("error_rate", 0.) for s in snapshots])),
                "most_common_context": max(counts, key=counts.get), "adaptation_readiness": average_confidence > self.config.get("confidence_threshold", .7)}

    def get_engine_status(self) -> Dict[str, Any]:
        return {"adaptation_enabled": self.config.get("adaptation_enabled", True), "is_adapting": self.is_adapting,
            "current_context": self.current_context.context_type.value if self.current_context else None, "adaptation_level": self.adaptation_level.value,
            "total_snapshots": len(self.context_snapshots), "total_rules": len(self.adaptation_rules),
            "total_adaptations": len(self.adaptation_history), "total_knowledge_transfers": len(self.knowledge_transfers),
            "active_modes": {"lightweight": self._lightweight_mode, "offline": self._offline_mode, "performance": self._performance_mode, "recovery": self._recovery_mode, "safe": self._safe_mode},
            "knowledge_base_stats": {"context_patterns": len(self.knowledge_base.get("context_patterns", {})), "adaptation_strategies": len(self.knowledge_base.get("adaptation_strategies", {})), "transfer_efficiency": len(self.knowledge_base.get("transfer_efficiency", {}))}}

    # Persistencia adicional y helpers
    @staticmethod
    def _safe_float(value: Any, default: float = 0.) -> float:
        try:
            result = float(value)
            return result if result == result and abs(result) != float("inf") else default
        except (TypeError, ValueError, OverflowError): return default

    @classmethod
    def _bounded_float(cls, value: Any, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, cls._safe_float(value, minimum)))

    @staticmethod
    def _coerce_context(value: Any) -> Optional[ContextType]:
        if isinstance(value, ContextType): return value
        if isinstance(value, str):
            try: return ContextType(value.lower())
            except ValueError:
                try: return ContextType[value.upper()]
                except KeyError: return None
        return None

    @staticmethod
    def _call_optional(obj: Any, method_name: str, *args, default=None, **kwargs):
        method = getattr(obj, method_name, None)
        if not callable(method): return default
        try: return method(*args, **kwargs)
        except Exception: return default

    @staticmethod
    def _json_default(value: Any):
        if isinstance(value, Enum): return value.value
        if isinstance(value, datetime): return value.isoformat()
        if isinstance(value, Path): return str(value)
        if hasattr(value, "to_dict") and callable(value.to_dict): return value.to_dict()
        if hasattr(value, "__dict__"): return value.__dict__
        return str(value)

    @classmethod
    def _serializable_history(cls, item: Any):
        if isinstance(item, AdaptationResult): return item.to_dict()
        if isinstance(item, dict): return dict(item)
        return {"adaptation_id": getattr(item, "adaptation_id", None),
                "performance_impact": getattr(item, "performance_impact", {}),
                "confidence_score": getattr(item, "confidence_score", 0.), "success": getattr(item, "success", False),
                "timestamp": getattr(item, "timestamp", None)}


def main() -> None:
    """Demostración breve; los métodos de la clase permanecen fuera de main."""
    engine = ContextualAdaptationEngine()
    snapshot = engine.capture_context_snapshot()
    print(f"Context type: {snapshot.context_type.value}")
    print(f"Confidence: {snapshot.confidence_score:.2f}")
    rules = engine.analyze_contextual_patterns(snapshot)
    print(f"Applicable rules: {len(rules)}")
    if rules:
        result = engine.execute_adaptation(snapshot, rules)
        print(f"Adaptation: {result.adaptation_id} - {result.adaptation_level.value}")
    else:
        print("No applicable rules")
    print(f"Summary: {engine.get_adaptation_summary()}")


if __name__ == "__main__":
    main()
