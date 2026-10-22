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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
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


# ==================================================== FORMATO REAL (2.8.8.8.9.6.3)
# Comprobadores de los tipos que declara el FORMATO REAL de la persistencia en
# `ContextualAdaptationEngine._CORRUPTION_CRITERIA` (`real_format.record.fields`).
# Son la MISMA fuente de verdad que usa la vía de carga para descartar lo que se
# aparta del formato, de modo que el formato declarado y el comportamiento real
# no puedan divergir.
_TIPO_COMPROBABLE = {
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "list": lambda value: isinstance(value, list),
    "mapping": lambda value: isinstance(value, dict),
    "boolean": lambda value: isinstance(value, bool),
    "string|null": lambda value: value is None or isinstance(value, str),
    "any": lambda value: True,
}


def _cumple_tipo(value: Any, tipo: str) -> bool:
    """Comprobar que un valor respeta el tipo declarado en el FORMATO REAL."""
    comprobador = _TIPO_COMPROBABLE.get(tipo)
    return True if comprobador is None else bool(comprobador(value))


def _tipo_de_valor(value: Any) -> str:
    """Tipo declarado en el FORMATO REAL que corresponde a un valor concreto."""
    if isinstance(value, bool): return "boolean"
    if isinstance(value, (int, float)): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, list): return "list"
    if isinstance(value, dict): return "mapping"
    return "any"


def _casa_target(declarado: str, observados: List[str]) -> bool:
    """Comprobar si un `target` declarado casa con algún target observado.

    El `target` declarado puede llevar un marcador de comodín (`<contexto>`,
    `<strategy_id>`, `<clave_desconocida>`). En ese caso casa con un target
    observado con el MISMO numero de segmentos, porque el comodín ocupa un
    unico segmento (p. ej. `data.context_patterns.<contexto>`).
    """
    if declarado in observados: return True
    if ".<" not in declarado: return False
    base = declarado.split(".<")[0]
    segmentos_declarados = len(declarado.split("."))
    for observado in observados:
        if not observado.startswith(base + "."): continue
        if len(observado.split(".")) != segmentos_declarados: continue
        return True
    return False


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
        # INFORME de RECUPERACIÓN (2.8.8.9.7.2): lo que el cargador ha
        # recuperado de un fichero corrupto y con que POLITICA lo ha hecho.
        # La recuperación NO reescribe el fichero: es una operacion de CARGA.
        self._recovery_report: List[Dict[str, Any]] = []
        # UNIDADES de datos que la última carga ha OBTENIDO de la persistencia
        # (2.8.8.9.8.2): el fallback DECLARA lo que OCURRIÓ, no lo que se
        # supone. Una carga que no obtiene ninguna unidad NO puede declarar
        # un exito.
        self._unidades_cargadas: Dict[str, int] = {"adaptation_rules": 0, "knowledge_base": 0}
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
        # Vocabulario de la base de conocimiento: las claves que el motor
        # escribe y el tipo que admite cada una. Es la referencia del FORMATO
        # REAL que usa la deteccion de corrupcion (2.8.8.9.6.3) para saber que
        # clave es conocida y que tipo debe tener su contenido.
        self._valores_por_defecto: Dict[str, Any] = copy.deepcopy(self.knowledge_base)

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

    # ============================================== DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3)
    #
    # El FORMATO REAL de cada fichero de persistencia está declarado en
    # `_CORRUPTION_CRITERIA` (`real_format`). Estas comprobaciones comparan el
    # contenido que se carga con ese formato: lo que se aparta de él NO llega
    # al estado del motor.
    #
    # La REACCIÓN al desvío depende de la CONVERSIÓN REAL que el cargador hace
    # del campo afectado:
    #   - conversión ESTRICTA (`int(...)`, `dict(...)`): el valor inválido lanza
    #     `ValueError` y aborta la carga del fichero entero. Es el comportamiento
    #     real del cargador, observado en 2.8.8.9.6.1.
    #   - conversión COERCIVA (`list(...)`, `bool(...)`, `float(...)`): el valor
    #     inválido se deformaría al llegar al estado, así que la fila se
    #     descarta ANTES de construirla.
    _CAMPOS_ESTRICTOS_DE_REGLA = ("priority", "execution_count", "metadata")

    # EVIDENCIA de una estrategia aprendida (2.8.8.9.2.1): sin `confidence`,
    # `success_rate` y `last_updated` la entrada no es una estrategia aprendida
    # y no puede ofrecerse con una confianza inventada. El `strategy_id` no es
    # obligatorio aquí porque en el índice plano lo aporta la propia clave.
    _EVIDENCIA_DE_ESTRATEGIA = ("confidence", "success_rate", "last_updated")

    def _campos_de_formato(self, clave: str) -> Dict[str, str]:
        """Campos del FORMATO REAL de las filas de un fichero de persistencia."""
        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {}).get("real_format", {}) or {}
        return dict((formato.get("record", {}) or {}).get("fields", {}) or {})

    def _campo_de_identidad(self, clave: str) -> Optional[str]:
        """Campo que IDENTIFICA una fila en el FORMATO REAL de un fichero.

        Es el campo que el formato declara como `identity`: sin el, la fila no
        se puede registrar. El FORMATO REAL lo declara ademas como cadena, de
        modo que un valor de otro tipo NO es una identidad.
        """
        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {}).get("real_format", {}) or {}
        return (formato.get("record", {}) or {}).get("identity")

    def _identidad_de_regla(self, row: Any) -> Optional[str]:
        """IDENTIDAD REGISTRABLE de una fila de regla.

        La identidad de una fila es su `rule_id`, y el FORMATO REAL lo declara
        como cadena: la identidad registrable es un `rule_id` que sea una cadena
        NO VACIA. Un `rule_id` de otro tipo (o vacio) NO es una identidad.

        Devuelve `None` cuando la fila no tiene identidad utilizable. El
        cargador NUNCA inventa una identidad: una fila sin identidad no se
        registra y sus HERMANAS sobreviven (2.8.8.9.8.4.2).
        """
        if not isinstance(row, dict): return None
        identidad = row.get("rule_id")
        if not isinstance(identidad, str): return None
        if not identidad.strip(): return None
        return identidad

    def _desviaciones_de_regla(self, row: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Desviaciones de una fila de regla respecto del FORMATO REAL.

        Devuelve pares `(campo, violacion)` con el campo que se aparta del
        formato y la violacion del vocabulario declarado (`wrong_type` o
        `invalid_value`). Los campos de conversión ESTRICTA no se comprueban
        aquí: su desvío lo aborta el propio constructor de la regla.

        El campo de IDENTIDAD no se comprueba aquí: la identidad no se
        RECUPERA, o vale o la fila se descarta entera (2.8.8.9.8.4.2).
        """
        desviaciones: List[Tuple[str, str]] = []
        identidad = self._campo_de_identidad("adaptation_rules")
        for nombre, tipo in self._campos_de_formato("adaptation_rules").items():
            if nombre not in row: continue
            if nombre in self._CAMPOS_ESTRICTOS_DE_REGLA: continue
            if nombre == identidad: continue
            valor = row[nombre]
            if not _cumple_tipo(valor, tipo):
                desviaciones.append((nombre, "wrong_type")); continue
            if nombre == "context_triggers":
                if any(self._coerce_context(trigger) is None for trigger in valor):
                    desviaciones.append(("context_triggers[]", "invalid_value"))
            elif nombre == "last_execution" and valor is not None:
                try: datetime.fromisoformat(str(valor))
                except (TypeError, ValueError): desviaciones.append((nombre, "invalid_value"))
        return desviaciones

    # ==================================================== RECUPERACIÓN (2.8.8.9.7.2)
    # La corrupción se rechaza SOLO en la UNIDAD que corrompe (el campo, el
    # grupo o el contenedor) y el resto de las unidades INDEPENDIENTES
    # sobrevive. La recuperación NO inventa datos: el campo corrupto toma el
    # valor por DEFECTO que declara el FORMATO REAL (`field_defaults`).
    def _desviaciones_estrictas_de_regla(self, row: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Desviaciones de los campos de conversión ESTRICTA de una fila de regla.

        Los campos de conversión ESTRICTA (`_CAMPOS_ESTRICTOS_DE_REGLA`) no se
        comprueban en `_desviaciones_de_regla`: su desvío lo abortaba el propio
        constructor de la regla, y por eso abortaba el FICHERO entero. Aquí se
        comprueban con SU criterio (el valor tiene que ser convertible al tipo
        que el constructor exige), de modo que la corrupción se pueda RECUPERAR
        en el nivel del CAMPO en vez de perder el fichero.
        """
        desviaciones: List[Tuple[str, str]] = []
        for nombre in self._CAMPOS_ESTRICTOS_DE_REGLA:
            if nombre not in row: continue
            valor = row[nombre]
            if nombre == "metadata":
                if not isinstance(valor, dict): desviaciones.append((nombre, "wrong_type"))
            elif not self._es_convertible_a_entero(valor):
                desviaciones.append((nombre, "invalid_value"))
        return desviaciones

    def _valor_por_defecto_de_recuperacion(self, campo: str, regla_id: Any = None) -> Any:
        """Valor por DEFECTO de RECUPERACIÓN de un campo de regla.

        Lo toma del CONTRATO declarado (`field_defaults`): es el único valor que
        la recuperación puede usar sin inventar datos. `$rule_id` se resuelve
        con la identidad de la propia regla.
        """
        declarado = (self._RECOVERABLE_DATA.get("field_defaults", {}) or {}).get(campo) or {}
        valor = declarado.get("value")
        if valor == "$rule_id": return regla_id
        return copy.deepcopy(valor)

    def _recuperar_fila_de_regla(self, row: Dict[str, Any],
                                 desviaciones: List[Tuple[str, str]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """RECUPERA la fila de regla corrupta en el NIVEL del CAMPO.

        La corrupción se rechaza SOLO en el campo que la corrompe: ese campo
        toma el valor por DEFECTO que declara el FORMATO REAL y el resto de la
        fila sobrevive intacto. Los campos de conversión ESTRICTA (que antes
        abortaban el FICHERO entero) se sustituyen aquí por su valor por
        defecto, de modo que la unidad que se rechaza es el CAMPO y no el
        fichero.

        Devuelve `(fila_recuperada, recuperaciones)`.
        """
        recuperada = dict(row)
        recuperaciones: List[Dict[str, Any]] = []
        formato = self._campos_de_formato("adaptation_rules")
        for campo_bruto, violacion in desviaciones:
            campo = campo_bruto.split("[", 1)[0]
            if campo not in formato or campo not in recuperada: continue
            valor = recuperada[campo]
            if campo == "context_triggers" and isinstance(valor, list):
                # `keep_valid_elements`: se conservan los disparadores validos y
                # se descarta SOLO el invalido.
                nuevo = [bruto for bruto in valor if self._coerce_context(bruto) is not None]
                politica = "keep_valid_elements"
            else:
                # `default_the_field`: el campo toma su valor por DEFECTO.
                nuevo = self._valor_por_defecto_de_recuperacion(campo, recuperada.get("rule_id"))
                politica = "default_the_field"
            recuperaciones.append({"campo": campo, "violacion": violacion,
                                   "politica": politica, "valor": nuevo})
            recuperada[campo] = nuevo
        return recuperada, recuperaciones

    def _procesar_fila_de_regla(self, row: Any, identidades: Set[str]
                                ) -> Tuple[Optional[AdaptationRule], List[Dict[str, Any]]]:
        """Procesa UNA fila de regla por el pipeline COMUN a las dos vías.

        El MISMO pipeline sirve a la vía de LISTA y a la de CONTENEDOR
        (2.8.8.9.8.4.2): la IDENTIDAD de la fila se comprueba ANTES de
        registrarla, de modo que una fila sin `rule_id` REGISTRABLE no se
        registra con una identidad INVENTADA y una fila cuya identidad ya usa
        otra fila no la COLISIONA (la primera registrada sobrevive).

        Devuelve `(regla, recuperaciones)`. `regla` es `None` cuando la fila no
        se puede registrar: se RECHAZA ENTERA y sus HERMANAS sobreviven.
        `recuperaciones` son las acciones de RECUPERACIÓN a nivel de CAMPO.
        """
        if not isinstance(row, dict):
            self.logger.warning("Regla descartada: la fila no es un mapeo")
            return None, []
        identidad = self._identidad_de_regla(row)
        if identidad is None:
            # SIN IDENTIDAD REGISTRABLE no hay registro: no se inventa ninguna.
            self.logger.warning("Regla descartada: sin identidad registrable")
            return None, []
        if identidad in identidades:
            # La identidad YA la usa otra fila: registrarla sería una COLISIÓN
            # que perdería una de las dos filas.
            self.logger.warning("Regla descartada: identidad duplicada (%s)", identidad)
            return None, []
        desviaciones = self._desviaciones_de_regla(row)
        desviaciones.extend(self._desviaciones_estrictas_de_regla(row))
        recuperaciones: List[Dict[str, Any]] = []
        if desviaciones:
            # RECUPERACIÓN PARCIAL (2.8.8.9.7.2): la corrupción se rechaza
            # SOLO en el CAMPO que la corrompe: ese campo toma su valor por
            # DEFECTO y el resto de la fila sobrevive.
            fila, recuperaciones = self._recuperar_fila_de_regla(row, desviaciones)
            if not recuperaciones:
                self.logger.warning("Regla descartada: se aparta del formato real (%s)", identidad)
                return None, []
            row = fila
        triggers = [ctx for raw in row.get("context_triggers", []) if (ctx := self._coerce_context(raw)) is not None]
        last = row.get("last_execution")
        try: last = datetime.fromisoformat(last) if last else None
        except (ValueError, TypeError): last = None
        regla = AdaptationRule(identidad, row.get("name", identidad), row.get("description", ""), row.get("condition_pattern", ""), list(row.get("adaptation_actions", [])), triggers, self._safe_float(row.get("confidence_threshold", .7)), int(row.get("priority", 1)), bool(row.get("enabled", True)), self._safe_float(row.get("success_rate", 0.)), int(row.get("execution_count", 0)), last, self._safe_float(row.get("adaptation_score", 0.)), list(row.get("constraints", [])), dict(row.get("metadata", {})), row.get("deadline"))
        return regla, recuperaciones

    def _valores_del_contenedor_de_reglas(self, rows: Any) -> List[Tuple[Any, Dict[str, Any]]]:
        """VALORES del contenedor `rules` cuando el contenedor tiene FORMA de mapeo.

        El contenedor cambió de FORMA (un mapeo en vez de una lista) pero su
        contenido puede seguir siendo válido: se toma cada VALOR del mapeo que
        sea un MAPEO y se pasa por el MISMO pipeline de fila que la vía de LISTA.
        Las claves NO se usan como identidad: sin `rule_id` propio la fila no se
        puede registrar.
        """
        if not isinstance(rows, dict): return []
        return [(clave, valor) for clave, valor in rows.items() if isinstance(valor, dict)]

    def _recuperar_grupos_de_base(self, clave: str, valor: Any) -> Tuple[Any, List[Dict[str, Any]]]:
        """RECUPERA los GRUPOS sanos de una sección con un grupo corrupto.

        El grupo que se aparta del FORMATO REAL se descarta y sus HERMANOS
        sobreviven: son unidades independientes (la ruta del grupo no es un
        prefijo de la ruta de su hermano). Devuelve `(valor, recuperaciones)`;
        `valor` es None cuando la sección no se puede recuperar.

        Una sección cuyo valor por DEFECTO no es un MAPEO (una sección de tipo
        LISTA, como `learning_results`) no tiene GRUPOS que recuperar: se
        rechaza ENTERA en el NIVEL de la SECCIÓN y sus HERMANOS (las demás
        secciones del mismo fichero) sobreviven. Esta vía intentaba iterar los
        grupos de un valor por defecto de tipo lista y lanzaba `AttributeError`,
        lo que abortaba la carga del FICHERO entero y hacía perder las
        secciones sanas del mismo.
        """
        por_defecto = self._valores_por_defecto.get(clave)
        if por_defecto is None or not isinstance(valor, dict): return None, []
        if not isinstance(por_defecto, dict): return None, []
        muestra = next(iter(por_defecto.values()), None)
        if not isinstance(muestra, (list, dict)): return None, []
        tipo_grupo = _tipo_de_valor(muestra)
        recuperaciones: List[Dict[str, Any]] = []
        recuperado: Dict[str, Any] = {}
        for grupo, contenido in valor.items():
            if not _cumple_tipo(contenido, tipo_grupo):
                recuperaciones.append({"grupo": grupo, "politica": "preserve_siblings",
                                       "motivo": "el grupo se aparta del formato real"})
                continue
            if clave == "adaptation_strategies" and tipo_grupo == "list":
                saneado = [entrada for entrada in contenido if isinstance(entrada, dict)]
                if len(saneado) != len(contenido):
                    recuperaciones.append({"grupo": grupo, "politica": "preserve_siblings",
                                           "motivo": "las entradas que no son mapeo se descartan"})
                recuperado[grupo] = saneado
                continue
            recuperado[grupo] = contenido
        if not recuperaciones: return None, []
        return recuperado, recuperaciones

    def _registrar_recuperacion(self, fichero: str, unidad: str,
                                 recuperaciones: List[Dict[str, Any]]) -> None:
        """Anota en el INFORME de recuperación lo que se ha recuperado."""
        for recuperacion in recuperaciones:
            self._recovery_report.append({"fichero": fichero, "unidad": unidad,
                                           "timestamp": datetime.now().isoformat(),
                                           **recuperacion})

    def recovery_report(self) -> Dict[str, Any]:
        """INFORME de lo que el cargador ha RECUPERADO (2.8.8.9.7.2).

        Es de SOLO LECTURA: no crea ficheros, no escribe y no altera el estado
        del motor. Devuelve una COPIA de lo recuperado en las cargas, con la
        UNIDAD recupera, la POLITICA aplicada y el valor por DEFECTO que ha
        ocupado el lugar del dato corrupto.
        """
        return {"recoveries": copy.deepcopy(self._recovery_report),
                "count": len(self._recovery_report),
                "files": sorted({str(item.get("fichero")) for item in self._recovery_report})}


    def _fila_valida(self, fila: Any, clave: str) -> bool:
        """Comprobar que una fila de persistencia respeta el FORMATO REAL.

        Una fila es válida si es un diccionario, si tiene el campo que la
        identifica y si los campos declarados que PRESENTA tienen el tipo que
        el formato exige. Un campo que no aparece no es una desviación: el
        formato no lo declara obligatorio.
        """
        if not isinstance(fila, dict): return False
        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {}).get("real_format", {}) or {}
        registro = formato.get("record", {}) or {}
        identidad = registro.get("identity")
        if identidad and not fila.get(identidad): return False
        for nombre, tipo in (registro.get("fields", {}) or {}).items():
            if nombre not in fila: continue
            if not _cumple_tipo(fila[nombre], tipo): return False
        return True

    def _estrategia_aprendida_valida(self, entrada: Any) -> bool:
        """Comprobar que una entrada de estrategia aprendida aporta EVIDENCIA."""
        if not isinstance(entrada, dict): return False
        for campo in self._EVIDENCIA_DE_ESTRATEGIA:
            if entrada.get(campo) is None: return False
        if not _cumple_tipo(entrada.get("confidence"), "number"): return False
        if not _cumple_tipo(entrada.get("success_rate"), "number"): return False
        return True

    def _seccion_de_conocimiento_valida(self, clave: str, valor: Any) -> bool:
        """Comprobar que una sección de la base respeta el FORMATO REAL.

        Una sección es válida si la clave es una de las que el motor escribe y
        si su contenido tiene el tipo que ese motor produce. En las secciones
        indexadas por contexto, el valor de cada contexto debe respetar
        también el tipo que el motor produce para ese contexto.
        """
        por_defecto = self._valores_por_defecto.get(clave)
        if por_defecto is None: return False
        tipo = _tipo_de_valor(por_defecto)
        if not _cumple_tipo(valor, tipo): return False
        if tipo != "mapping": return True
        muestra = next(iter(por_defecto.values()), None)
        if isinstance(muestra, (list, dict)):
            for sub in valor.values():
                if not isinstance(sub, type(muestra)): return False
        if clave == "adaptation_strategies":
            for entradas in valor.values():
                if not isinstance(entradas, list): return False
                for entrada in entradas:
                    if not isinstance(entrada, dict): return False
        return True

    def load_adaptation_rules(self) -> bool:
        path = self._resolve_path(self.config.get("adaptation_rules_file"), "contextual_adaptation_rules.json")
        self._unidades_cargadas["adaptation_rules"] = 0
        if not os.path.isfile(path): return True
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            rows = payload.get("rules", []) if isinstance(payload, dict) else payload
            candidatas: List[Tuple[Any, Any]] = []
            es_contenedor = not isinstance(rows, list)
            if es_contenedor:
                # RECUPERACIÓN PARCIAL (2.8.8.9.7.2): el CONTENEDOR `rules`
                # cambió de FORMA, pero su contenido puede seguir siendo válido:
                # se RECONSTRUYE con los valores que sean MAPEOS y cada uno pasa
                # por el MISMO pipeline de fila que la vía de LISTA. Las claves
                # NO se usan como identidad.
                candidatas = self._valores_del_contenedor_de_reglas(rows)
            else:
                candidatas = [(None, fila) for fila in rows]
            loaded = {}
            identidades: Set[str] = set()
            recuperadas_contenedor: List[Dict[str, Any]] = []
            for clave, fila in candidatas:
                # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3), RECUPERACIÓN PARCIAL
                # (2.8.8.9.7.2) e IDENTIDAD (2.8.8.9.8.4.2): el pipeline descarta
                # la fila que se aparta del FORMATO REAL o que no tiene
                # identidad REGISTRABLE, y recupera la que solo tiene un CAMPO
                # corrupto. Las HERMANAS de la fila descartada sobreviven.
                regla, recuperaciones = self._procesar_fila_de_regla(fila, identidades)
                if regla is None: continue
                identidades.add(regla.rule_id)
                loaded[regla.rule_id] = regla
                if es_contenedor:
                    recuperadas_contenedor.append({"clave": clave, "politica": "adapt_container",
                                                    "rule_id": regla.rule_id})
                if recuperaciones:
                    self._registrar_recuperacion("adaptation_rules", f"fila:{regla.rule_id}", recuperaciones)
                    self.logger.warning("Regla recuperada: campo corrupto por defecto (%s)", regla.rule_id)
            if recuperadas_contenedor:
                self._registrar_recuperacion("adaptation_rules", "bloque:rules", recuperadas_contenedor)
                self.logger.warning("Contenedor de reglas reconstruido: cambio de forma")
            # FALLBACK por CORRUPCIÓN TOTAL (2.8.8.9.8.2): se REGISTRA lo que
            # la carga ha OBTENIDO, para que la carga aggregate pueda DECIR lo
            # que ocurrio en lugar de suponerlo.
            self._unidades_cargadas["adaptation_rules"] = len(loaded)
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
        self._unidades_cargadas["knowledge_base"] = 0
        if not os.path.isfile(path): return True
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            validas: Dict[str, Any] = {}
            if isinstance(data, dict):
                # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3): solo se aplican las
                # secciones que respetan el FORMATO REAL. Una clave que el motor
                # nunca escribe o una sección corrupta NO llegan al estado: la
                # base conserva sus valores por defecto.
                for clave, valor in data.items():
                    if not self._seccion_de_conocimiento_valida(clave, valor):
                        # RECUPERACIÓN PARCIAL (2.8.8.9.7.2): puede que la
                        # sección sea válida y lo que se aparta del FORMATO
                        # REAL sea un GRUPO (un contexto) de su interior: el
                        # grupo corrupto se descarta y sus HERMANOS sobreviven.
                        recuperado, recuperadas = self._recuperar_grupos_de_base(clave, valor)
                        if not recuperadas:
                            self.logger.warning("Seccion de la base de conocimiento descartada: %s", clave)
                            continue
                        self._registrar_recuperacion("knowledge_base", f"seccion:{clave}", recuperadas)
                        self.logger.warning("Seccion de la base recuperada: grupo corrupto descartado (%s)", clave)
                        valor = recuperado
                    validas[clave] = valor
                self.knowledge_base.update(validas)
                for ctx in ContextType:
                    for key, default in (("context_patterns", []), ("success_patterns", []), ("performance_baselines", {}), ("adaptation_strategies", [])):
                        self.knowledge_base.setdefault(key, {}).setdefault(ctx.value, default.copy())
                self.knowledge_base.setdefault("integration_records", [])
                self.knowledge_base.setdefault("transfer_efficiency", {})
            # FALLBACK por CORRUPCIÓN TOTAL (2.8.8.9.8.2): se REGISTRA lo que
            # la carga ha OBTENIDO, para que la carga aggregate pueda DECIR lo
            # que ocurrio en lugar de suponerlo.
            self._unidades_cargadas["knowledge_base"] = len(validas)
            return True
        except Exception as exc: self.logger.error("Error cargando knowledge base: %s", exc); return False

    def save_all_data(self) -> bool: return self._save_adaptation_rules() and self.save_knowledge_base()

    def load_all_data(self) -> bool:
        """Carga TODA la persistencia que lee esta carga y DECLARA lo que ocurrio.

        FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.2): devuelve FALSO cuando los
        ficheros de persistencia EXISTEN pero NO aportan ninguna unidad de datos
        utilizable. Declarar un exito que no ocurrio haria CREER al consumidor
        que los datos estan cargados, cuando el motor esta operando con los
        defaults del codigo: el fallback NO inventa datos y TAMPOCO declara una
        carga que no ha ocurrido.

        Con el almacenamiento AUSENTE (2.8.8.9.5.1) devuelve VERDADERO: no
        habia nada que cargar y el estado por defecto es el declarado.
        """
        reglas_ok = self.load_adaptation_rules()
        base_ok = self.load_knowledge_base()
        if not (reglas_ok and base_ok): return False
        if not self._hay_que_cargar(): return True
        return self._unidades_obtenidas() > 0

    def _hay_que_cargar(self) -> bool:
        """Hay AL MENOS UNO de los ficheros de persistencia que esta carga LEE.

        La carga aggregate lee el fichero de REGLAS y el de la BASE DE
        CONOCIMIENTO: el de feedback y el de resultados de aprendizaje tienen
        sus PROPIOS cargadores.
        """
        rutas = self.expected_storage_paths()
        return any(os.path.isfile(rutas.get(clave, "")) for clave in ("adaptation_rules", "knowledge_base"))

    def _unidades_obtenidas(self) -> int:
        """Unidades de datos utilizables que la ultima carga ha OBTENIDO."""
        return sum(self._unidades_cargadas.values())

    def backup_data(self, backup_dir: Optional[str] = None) -> bool:
        """Respalda los CUATRO ficheros de persistencia (2.8.8.9.8.2).

        El respaldo cubre TODA la persistencia que el motor declara en
        `expected_storage_paths()`: reglas, base de conocimiento, feedback y
        resultados de aprendizaje. Un respaldo que solo cubre una parte deja
        sin copia justo lo que se necesita recuperar cuando la perdida es
        TOTAL.

        El respaldo es una COPIA: no modifica el fichero de origen, de modo que
        su contenido sigue intacto para su diagnostico.
        """
        try:
            backup_dir = backup_dir or os.path.join(self.data_dir, "backups"); os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); copied = False
            for name, path in self.expected_storage_paths().items():
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
                # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3): una entrada sin
                # EVIDENCIA no es una estrategia aprendida (2.8.8.9.2.1) y no
                # se restaura: ofrecerla con una confianza inventada sería usar
                # el dato corrupto como si fuera válido.
                if not self._estrategia_aprendida_valida(entry): continue
                flat.setdefault(str(entry.get("strategy_id") or key), entry)
                continue
            if not isinstance(value, list): continue
            for position, entry in enumerate(value):
                if not isinstance(entry, dict): continue
                normalized = copy.deepcopy(entry)
                sid = str(normalized.get("strategy_id") or f"strategy_{key}_{position}")
                normalized.setdefault("strategy_id", sid)
                if not self._estrategia_aprendida_valida(normalized): continue
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
        """Contar las observaciones similares acumuladas por cada patrón.

        Solo se cuentan las observaciones que superan el umbral de confianza:
        son exactamente las que el propio guardado conserva. Así el recuento de
        la carga coincide con el del guardado y el ciclo guardar/cargar no
        pierde ningún patrón validado (2.8.8.9.4.4).
        """
        threshold = self._confidence_threshold()
        counts: Dict[Tuple[str, str, str], int] = {}
        for row in learning_results or []:
            if not isinstance(row, dict): continue
            for pattern in row.get("learned_patterns") or []:
                if not isinstance(pattern, dict): continue
                if self._safe_float(pattern.get("confidence", 0.)) < threshold: continue
                identity = self._pattern_identity(pattern)
                counts[identity] = counts.get(identity, 0) + 1
        return counts

    def _confidence_threshold(self) -> float:
        """Umbral de confianza configurado en el motor.

        La configuración se lee con `getattr` porque la validación se usa
        también en la carga, donde el motor puede haber sido construido sin
        inicializar `config` (por ejemplo, en las pruebas que reutilizan una
        instancia creada con `__new__`).
        """
        config = getattr(self, "config", None) or {}
        return self._safe_float(config.get("confidence_threshold", .7), .7)

    def _min_similar_observations(self) -> int:
        """Mínimo de observaciones similares exigido por el motor."""
        config = getattr(self, "config", None) or {}
        return int(self._safe_float(config.get("min_similar_observations", 3), 3))

    def _is_validated_pattern(self, pattern: Dict[str, Any], observations: Dict[Tuple[str, str, str], int]) -> bool:
        """Comprobar si un patrón cumple el contrato de datos validados.

        Exige `confidence >= confidence_threshold` (configurado en el motor) y
        un mínimo de `min_similar_observations` observaciones similares.
        """
        if self._safe_float(pattern.get("confidence", 0.)) < self._confidence_threshold(): return False
        return observations.get(self._pattern_identity(pattern), 0) >= self._min_similar_observations()

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

    def _recover_learning_patterns(self, learning_results: Any) -> Any:
        """Recuperar únicamente los patrones de aprendizaje validados (2.8.8.9.4.4).

        Aplica el mismo contrato de DATOS CRÍTICOS (item 5) que el guardado
        (2.8.8.9.4.3): un patrón solo se recupera si su `confidence` alcanza el
        umbral configurado en el motor y tiene un mínimo de
        `min_similar_observations` observaciones similares.

        El guardado ya escribe el fichero filtrado, de modo que para los
        ficheros que produce el motor esta recuperación es idéntica al
        contenido persistido. El filtro evita que un fichero heredado, escrito
        a mano o por otra herramienta introduzca en la base de conocimiento
        patrones que nunca fueron validados.

        Las filas de resultados de aprendizaje se conservan íntegras: de ellas
        depende la restauración de estrategias (2.8.8.9.3).
        """
        if not isinstance(learning_results, list): return learning_results
        recovered = self._filter_validated_learning_results(learning_results)
        persisted = sum(len(row.get("learned_patterns") or []) for row in learning_results if isinstance(row, dict))
        restored = sum(len(row.get("learned_patterns") or []) for row in recovered if isinstance(row, dict))
        if persisted != restored:
            self.logger.info("Patrones de aprendizaje no validados descartados al cargar: %s de %s",
                             persisted - restored, persisted)
        return recovered

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
            if not isinstance(payload, dict): return
            # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3): la sección corrupta NO
            # llega al estado y las filas que no son filas válidas se
            # descartan; el resto del fichero se carga con normalidad.
            # 2.8.8.9.8.4.4: conservar la sección válida de la base frente al
            # fichero de feedback. Si la base ya tiene una sección sana, no se
            # sobrescribe con una lista del fichero (aunque parcial).
            rows = payload.get("goal_adaptation_feedback", None)
            if isinstance(rows, list):
                base_rows = self.knowledge_base.get("goal_adaptation_feedback")
                if isinstance(base_rows, list) and len(base_rows) > 0:
                    # Conservar lo ya cargado desde la base de conocimiento
                    pass
                else:
                    self.knowledge_base["goal_adaptation_feedback"] = [row for row in rows if self._fila_valida(row, "goal_adaptation_feedback")]
            history = payload.get("adaptation_history", [])
            if isinstance(history, list) and history:
                self.adaptation_history = [_AdaptationHistoryEntry(row) for row in history if isinstance(row, dict)]
        except Exception as exc: self.logger.error("Error cargando feedback Goal: %s", exc)

    def _load_goal_adaptation_learning_results(self) -> None:
        path = os.path.join(self.data_dir, "goal_adaptation_learning_results.json")
        if not os.path.isfile(path): return
        try:
            with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            if not isinstance(payload, dict): return
            # Contrato de DATOS CRÍTICOS (item 5, 2.8.8.9.4.4): la carga aplica
            # el mismo filtro de validación que el guardado, de modo que solo
            # se recuperan los patrones validados (confianza >= umbral y mínimo
            # de observaciones similares).
            # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3): una sección que no es una
            # lista NO llega al estado y las filas que no son filas válidas se
            # descartan; el resto del fichero se carga con normalidad.
            loaded_results = payload.get("learning_results", None)
            if isinstance(loaded_results, list):
                filas = [row for row in loaded_results if self._fila_valida(row, "goal_adaptation_learning_results")]
                self.knowledge_base["learning_results"] = self._recover_learning_patterns(filas)
            elif loaded_results is None:
                self.knowledge_base["learning_results"] = self._recover_learning_patterns(self.knowledge_base.get("learning_results", []))
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

    # Detección de almacenamiento ausente (2.8.8.9.5.1)
    def expected_storage_paths(self) -> Dict[str, str]:
        """Rutas del almacenamiento de persistencia que el motor espera encontrar.

        Solo cubre FICHEROS. La ausencia de una SECCIÓN dentro de un fichero
        existente se detecta aparte, en 2.8.8.9.5.2.
        """
        return {"goal_adaptation_feedback": os.path.join(self.data_dir, "goal_adaptation_feedback.json"),
                "goal_adaptation_learning_results": os.path.join(self.data_dir, "goal_adaptation_learning_results.json"),
                "adaptation_rules": self._resolve_path(self.config.get("adaptation_rules_file"), "contextual_adaptation_rules.json"),
                "knowledge_base": self._resolve_path(self.config.get("knowledge_base_file"), "contextual_knowledge_base.json")}

    def detect_absent_storage(self) -> Dict[str, Any]:
        """Detecta que parte del almacenamiento esperado falta en disco.

        Operacion de SOLO LECTURA: no crea ficheros ni altera el estado del
        motor. Devuelve, por cada almacen ausente, su ruta y el motivo, para
        que el consumidor pueda distinguir entre fichero inexistente y ruta
        que no es un fichero.
        """
        paths = self.expected_storage_paths(); present = []; absent = {}
        for name, path in paths.items():
            if os.path.isfile(path): present.append(name); continue
            absent[name] = {"path": path, "reason": "not_a_file" if os.path.exists(path) else "file_not_found"}
        return {"expected": paths, "present": present, "absent": absent, "absent_count": len(absent), "has_absent": bool(absent)}

    # Detección de sección ausente (2.8.8.9.5.2)
    #
    # Secciones de primer nivel que el motor espera dentro de cada fichero de
    # persistencia. Cada sección tiene su origen real en el motor:
    #   - `goal_adaptation_feedback.json` -> `_save_goal_adaptation_feedback`
    #   - `goal_adaptation_learning_results.json` -> `_save_goal_adaptation_learning_results`
    #   - `contextual_adaptation_rules.json` -> `_save_adaptation_rules`
    #   - `contextual_knowledge_base.json` -> `save_knowledge_base`
    # El valor de cada sección indica su clase:
    #   - `data`: sección que el cargador real consume (`_load_goal_adaptation_*`,
    #     `load_adaptation_rules`, `load_knowledge_base`).
    #   - `metadata`: sección informativa que el escritor produce y que no se
    #     usa para recuperar datos.
    _STORAGE_SECTIONS: Dict[str, Dict[str, str]] = {
        "goal_adaptation_feedback": {"goal_adaptation_feedback": "data", "adaptation_history": "data", "last_updated": "metadata"},
        "goal_adaptation_learning_results": {"learning_results": "data", "adaptation_strategies": "data", "last_updated": "metadata"},
        "adaptation_rules": {"rules": "data", "total_rules": "metadata", "version": "metadata", "last_updated": "metadata"},
        "knowledge_base": {"data": "data", "context_snapshots": "metadata", "adaptation_history": "metadata",
                           "knowledge_transfers": "metadata", "version": "metadata", "last_updated": "metadata"},
    }

    # Formato heredado admitido por `load_adaptation_rules`: el fichero puede
    # contener la lista de reglas en su propia raíz. Esa sección de datos se
    # considera presente aunque el payload no sea un diccionario.
    _STORAGE_ROOT_LIST_SECTION: Dict[str, str] = {"adaptation_rules": "rules"}

    def expected_storage_sections(self) -> Dict[str, Dict[str, str]]:
        """Secciones de primer nivel que el motor espera en cada fichero de persistencia.

        Solo cubre SECCIONES dentro de ficheros EXISTENTES. La ausencia del propio
        fichero se detecta aparte, en 2.8.8.9.5.1 (`detect_absent_storage`).
        """
        return {name: dict(sections) for name, sections in self._STORAGE_SECTIONS.items()}

    def detect_absent_sections(self) -> Dict[str, Any]:
        """Detecta secciones ausentes dentro de los ficheros de persistencia existentes.

        Operacion de SOLO LECTURA: no crea ficheros ni altera el estado del motor.
        Solo se examinan los ficheros que EXISTEN; los ausentes se listan en
        `missing_files` (su deteccion es la de 2.8.8.9.5.1). Un fichero presente
        pero ilegible o con un payload que no es un diccionario se listan en
        `unreadable`: la corrupcion del contenido se detecta en 2.8.8.9.6.

        Cada ausencia informa su `path`, su `reason` y su `kind` (`data` o
        `metadata`), para que el consumidor distinga una seccion de DATOS
        ausente de una seccion informativa ausente.
        """
        paths = self.expected_storage_paths()
        sections = self.expected_storage_sections()
        checked: List[str] = []
        absent: Dict[str, Dict[str, Any]] = {}
        unreadable: Dict[str, Any] = {}
        missing_files: List[str] = []
        for name, path in paths.items():
            if not os.path.isfile(path):
                missing_files.append(name)
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception:
                unreadable[name] = {"path": path, "reason": "unreadable_file"}
                continue
            expected = sections.get(name, {})
            if isinstance(payload, dict):
                found = set(payload.keys())
            elif isinstance(payload, list):
                found = set()
                root_section = self._STORAGE_ROOT_LIST_SECTION.get(name)
                if root_section and root_section in expected: found.add(root_section)
            else:
                unreadable[name] = {"path": path, "reason": "not_a_mapping"}
                continue
            missing = [section for section in expected if section not in found]
            if missing:
                absent[name] = {section: {"path": path, "reason": "section_not_found", "kind": expected[section]}
                                for section in missing}
            checked.append(name)
        absent_count = sum(len(sections_missing) for sections_missing in absent.values())
        return {"expected": sections, "checked": checked, "absent": absent, "absent_count": absent_count,
                "has_absent": bool(absent), "missing_files": missing_files, "unreadable": unreadable}

    # Detección de corrupción (2.8.8.9.6.3)
    #
    # La CORRUPCIÓN es la DESVIACIÓN del FORMATO REAL declarado en
    # `_CORRUPTION_CRITERIA` (2.8.8.9.6.1) en un contenido que está PRESENTE.
    # La AUSENCIA (2.8.8.9.5.1) y la ILEGIBILIDAD (2.8.8.9.5.2) son otros
    # fenómenos: NO se reclasifican como corrupción y se listan aparte, igual
    # que en `detect_absent_sections`.
    #
    # `detect_corruption()` es de SOLO LECTURA: lee los ficheros existentes y
    # NO crea ficheros ni altera el estado del motor.
    def detect_corruption(self) -> Dict[str, Any]:
        """Detecta la corrupción del contenido en los ficheros de persistencia.

        Operacion de SOLO LECTURA: no crea ficheros ni altera el estado del
        motor. Solo se examinan los ficheros que EXISTEN y son LEGIBLES.

        Por cada fichero se informan las CLASES de corrupción DETECTADAS (las
        declaradas en `corruption_criteria()`), con su `id`, `target`,
        `violation`, `severity` y la `location` donde se ha encontrado la
        desviación. Los ficheros ausentes se listan en `missing_files` y los
        ilegibles en `unreadable`: su detección es la de 2.8.8.9.5.1/5.2.
        """
        paths = self.expected_storage_paths()
        corrupted: Dict[str, List[Dict[str, Any]]] = {}
        missing_files: List[str] = []
        unreadable: Dict[str, Any] = {}
        checked: List[str] = []
        for name, path in paths.items():
            if not os.path.isfile(path):
                missing_files.append(name); continue
            try:
                with open(path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            except Exception:
                unreadable[name] = {"path": path, "reason": "unreadable_file"}; continue
            detections = self._detect_corruption_in(name, payload)
            if detections: corrupted[name] = detections
            checked.append(name)
        corruption_count = sum(len(items) for items in corrupted.values())
        return {"expected": paths, "checked": checked, "corrupted": corrupted, "corruption_count": corruption_count,
                "has_corruption": bool(corrupted), "missing_files": missing_files, "unreadable": unreadable}

    def _deteccion(self, class_id: str, location: str) -> Dict[str, Any]:
        """Desviación detectada, con los datos de la clase declarada."""
        for spec in (self._CORRUPTION_CRITERIA.get("files", {}) or {}).values():
            for clase in spec.get("corruptions", []) or []:
                if clase.get("id") == class_id:
                    return {"id": class_id, "target": clase.get("target"), "violation": clase.get("violation"),
                            "severity": clase.get("severity"), "location": location}
        return {"id": class_id, "target": None, "violation": None, "severity": None, "location": location}

    def _detect_corruption_in(self, name: str, payload: Any) -> List[Dict[str, Any]]:
        """Desviaciones detectadas en un fichero de persistencia."""
        detector = {"adaptation_rules": self._detect_corruption_rules,
                    "knowledge_base": self._detect_corruption_knowledge_base,
                    "goal_adaptation_feedback": self._detect_corruption_feedback,
                    "goal_adaptation_learning_results": self._detect_corruption_learning_results}.get(name)
        return list(detector(payload)) if detector else []

    @staticmethod
    def _es_convertible_a_entero(value: Any) -> bool:
        """Comprobar si `int(value)` no lanza, como hace el cargador real."""
        try: int(value); return True
        except (TypeError, ValueError): return False

    @staticmethod
    def _es_marca_iso(value: Any) -> bool:
        """Comprobar si una marca de tiempo se puede leer como ISO."""
        try: datetime.fromisoformat(str(value)); return True
        except (TypeError, ValueError): return False

    def _detect_corruption_rules(self, payload: Any) -> List[Dict[str, Any]]:
        """Desviaciones del FORMATO REAL de `contextual_adaptation_rules.json`."""
        detections: List[Dict[str, Any]] = []
        rows = payload.get("rules", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return [self._deteccion("adaptation_rules.rules_wrong_type", "rules")]
        for index, row in enumerate(rows):
            location = f"rules[{index}]"
            if not isinstance(row, dict):
                detections.append(self._deteccion("adaptation_rules.row_not_mapping", location)); continue
            if self._identidad_de_regla(row) is None:
                detections.append(self._deteccion("adaptation_rules.row_missing_identity", f"{location}.rule_id"))
            if "adaptation_actions" in row and not isinstance(row["adaptation_actions"], list):
                detections.append(self._deteccion("adaptation_rules.actions_string", f"{location}.adaptation_actions"))
            if "enabled" in row and not isinstance(row["enabled"], bool):
                detections.append(self._deteccion("adaptation_rules.enabled_string", f"{location}.enabled"))
            if "confidence_threshold" in row and not _cumple_tipo(row["confidence_threshold"], "number"):
                detections.append(self._deteccion("adaptation_rules.threshold_not_numeric", f"{location}.confidence_threshold"))
            if "success_rate" in row and not _cumple_tipo(row["success_rate"], "number"):
                detections.append(self._deteccion("adaptation_rules.success_rate_not_numeric", f"{location}.success_rate"))
            if "context_triggers" in row and not isinstance(row["context_triggers"], list):
                detections.append(self._deteccion("adaptation_rules.triggers_not_list", f"{location}.context_triggers"))
            else:
                for position, trigger in enumerate(row.get("context_triggers", []) or []):
                    if self._coerce_context(trigger) is None:
                        detections.append(self._deteccion("adaptation_rules.trigger_invalid_value",
                                                           f"{location}.context_triggers[{position}]"))
            if row.get("last_execution") is not None and not self._es_marca_iso(row["last_execution"]):
                detections.append(self._deteccion("adaptation_rules.last_execution_not_iso", f"{location}.last_execution"))
            if "name" in row and not isinstance(row["name"], str):
                detections.append(self._deteccion("adaptation_rules.name_not_string", f"{location}.name"))
            if "priority" in row and not self._es_convertible_a_entero(row["priority"]):
                detections.append(self._deteccion("adaptation_rules.priority_not_castable", f"{location}.priority"))
            if "execution_count" in row and not self._es_convertible_a_entero(row["execution_count"]):
                detections.append(self._deteccion("adaptation_rules.execution_count_not_castable", f"{location}.execution_count"))
            if "metadata" in row and not isinstance(row["metadata"], dict):
                detections.append(self._deteccion("adaptation_rules.metadata_not_mapping", f"{location}.metadata"))
        return detections

    def _detect_corruption_knowledge_base(self, payload: Any) -> List[Dict[str, Any]]:
        """Desviaciones del FORMATO REAL de `contextual_knowledge_base.json`."""
        detections: List[Dict[str, Any]] = []
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return [self._deteccion("knowledge_base.data_not_mapping", "data")]
        for clave, valor in data.items():
            location = f"data.{clave}"
            if clave not in self._valores_por_defecto:
                detections.append(self._deteccion("knowledge_base.unexpected_key", location)); continue
            esperado = self._valores_por_defecto[clave]
            if not _cumple_tipo(valor, _tipo_de_valor(esperado)):
                detections.append(self._deteccion(
                    "knowledge_base.strategies_not_mapping" if clave == "adaptation_strategies" else "knowledge_base.section_not_mapping",
                    location)); continue
            if isinstance(esperado, dict) and isinstance(valor, dict):
                for contexto, sub in valor.items():
                    if contexto not in esperado or not _cumple_tipo(sub, _tipo_de_valor(esperado[contexto])):
                        detections.append(self._deteccion("knowledge_base.section_partial", f"{location}.{contexto}"))
        return detections

    def _detect_corruption_feedback(self, payload: Any) -> List[Dict[str, Any]]:
        """Desviaciones del FORMATO REAL de `goal_adaptation_feedback.json`."""
        detections: List[Dict[str, Any]] = []
        if not isinstance(payload, dict): return detections
        rows = payload.get("goal_adaptation_feedback", [])
        if not isinstance(rows, list):
            detections.append(self._deteccion("goal_adaptation_feedback.section_not_list", "goal_adaptation_feedback"))
        else:
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    detections.append(self._deteccion("goal_adaptation_feedback.row_not_mapping", f"goal_adaptation_feedback[{index}]"))
        history = payload.get("adaptation_history", [])
        if not isinstance(history, list):
            detections.append(self._deteccion("goal_adaptation_feedback.history_not_list", "adaptation_history"))
        return detections

    def _detect_corruption_learning_results(self, payload: Any) -> List[Dict[str, Any]]:
        """Desviaciones del FORMATO REAL de `goal_adaptation_learning_results.json`."""
        detections: List[Dict[str, Any]] = []
        if not isinstance(payload, dict): return detections
        rows = payload.get("learning_results", [])
        if not isinstance(rows, list):
            detections.append(self._deteccion("goal_adaptation_learning_results.learning_results_not_list", "learning_results"))
        else:
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    detections.append(self._deteccion("goal_adaptation_learning_results.row_not_mapping", f"learning_results[{index}]"))
        strategies = payload.get("adaptation_strategies", {})
        if not isinstance(strategies, dict):
            detections.append(self._deteccion("goal_adaptation_learning_results.strategies_not_mapping", "adaptation_strategies"))
            return detections
        for strategy_id, entrada in strategies.items():
            location = f"adaptation_strategies.{strategy_id}"
            if not isinstance(entrada, (dict, list)):
                detections.append(self._deteccion("goal_adaptation_learning_results.strategy_value_not_mapping", location)); continue
            if isinstance(entrada, dict) and not self._estrategia_aprendida_valida(entrada):
                detections.append(self._deteccion("goal_adaptation_learning_results.strategy_missing_identity", location))
        return detections

    # Comportamiento SIN DATOS (2.8.8.9.5.3)
    #
    # Contrato NORMATIVO y DECLARATIVO de lo que el motor hace cuando el
    # almacenamiento de persistencia esta AUSENTE (2.8.8.9.5.1) o le falta una
    # SECCION (2.8.8.9.5.2).
    #
    # Este contrato NO implementa el comportamiento: lo DECLARA. Su valor es
    # que puede contrastarse de forma automatica contra el comportamiento
    # OBSERVADO en runtime, mediante la sonda
    # `tests/utils/contextual_adaptation_engine/no_data_behavior_real.py`.
    # Si lo observado se desvía, el contraste falla y el contrato queda
    # obsoleto: es intencional, un contrato que nunca falla no prueba nada.
    #
    # Es de SOLO LECTURA: no crea ficheros ni modifica el estado del motor.
    _NO_DATA_BEHAVIOR: Dict[str, Any] = {
        "version": "2.8.8.9.5.3",
        "principle": ("La ausencia de datos nunca es un error fatal: el motor arranca, "
                      "expone valores por defecto seguros, la deteccion informa de la ausencia, "
                      "y el almacenamiento se recrea en el momento en que alguien escribe."),
        "startup": {
            "raises": False,
            "creates_data_dir": True,
            "creates_persistence_files": False,
            "defaults": {
                "adaptation_rules": "builtin_rules",
                "knowledge_base": "empty_sections",
                "adaptation_history": "empty",
                "knowledge_transfers": "empty",
            },
        },
        # API de LECTURA: nunca lanzan excepcion con el almacenamiento ausente y
        # devuelven siempre un valor del tipo declarado.
        "read_apis": [
            {"api": "get_engine_status", "returns": "dict", "args": []},
            {"api": "get_adaptation_summary", "returns": "dict", "args": []},
            {"api": "get_context_insights", "returns": "dict", "args": []},
            {"api": "get_adaptation_rules", "returns": "list", "args": []},
            {"api": "list_adaptation_rules", "returns": "list", "args": []},
            {"api": "get_available_strategies", "returns": "list", "args": ["context"]},
            {"api": "get_knowledge_transfers", "returns": "list", "args": []},
            {"api": "load_adaptation_rules", "returns": "bool", "args": []},
            {"api": "load_knowledge_base", "returns": "bool", "args": []},
            {"api": "load_all_data", "returns": "bool", "args": []},
        ],
        # API de ESCRITURA: recrean el almacenamiento ausente.
        "write_apis": [
            {"api": "save_adaptation_rules", "returns": "bool", "creates": "adaptation_rules"},
            {"api": "save_knowledge_base", "returns": "bool", "creates": "knowledge_base"},
            {"api": "save_all_data", "returns": "bool", "creates": ["adaptation_rules", "knowledge_base"]},
            {"api": "_save_goal_adaptation_feedback", "returns": "none", "creates": "goal_adaptation_feedback"},
            {"api": "_save_goal_adaptation_learning_results", "returns": "none", "creates": "goal_adaptation_learning_results"},
        ],
        # API de DETECCION: informan de la ausencia sin escribir nada.
        # `detect_absent_sections` solo examina ficheros EXISTENTES: los
        # ficheros ausentes se listan en `missing_files`, y una seccion ausente
        # solo puede darse dentro de un fichero presente.
        "detection": {
            "detect_absent_storage": "reports_absent",
            "detect_absent_sections": "reports_missing_sections_in_existing_files",
            "detect_absent_sections_missing_files": "reports_absent_files",
            "get_engine_status": ["storage", "storage_sections"],
            "detection_writes": False,
        },
        # Tras escribir, el almacenamiento deja de reportarse como ausente.
        "recovery": {
            "recreates_storage_on_write": True,
            "detect_absent_storage_after_write": "no_absent",
        },
        "invariants": [
            "read_apis_never_raise",
            "detection_never_writes",
            "defaults_are_empty_not_null",
            "writes_recreate_missing_storage",
        ],
    }

    def no_data_behavior(self) -> Dict[str, Any]:
        """Contrato DECLARATIVO del comportamiento del motor SIN DATOS (2.8.8.9.5.3).

        Declara que debe hacer el motor cuando el almacenamiento de persistencia
        esta ausente (2.8.8.9.5.1) o le falta una seccion (2.8.8.9.5.2):
        arranque, valores por defecto, API de lectura, escritura, deteccion y
        recuperacion.

        Es de SOLO LECTURA: no crea ficheros, no escribe y no altera el estado
        del motor. Devuelve una COPIA profunda, de modo que el llamante no pueda
        mutar el contrato de la clase.

        La declaracion NO sustituye a la verificacion: la sonda
        `tests/utils/contextual_adaptation_engine/no_data_behavior_real.py`
        contrasta esta declaracion contra el comportamiento OBSERVADO en runtime.
        """
        return copy.deepcopy(self._NO_DATA_BEHAVIOR)

    # Criterios de CORRUPCIÓN (2.8.8.9.6.1)
    #
    # Contrato NORMATIVO y DECLARATIVO de qué constituye CORRUPCIÓN según el
    # FORMATO REAL de la persistencia.
    #
    # El "formato real" es el que producen y leen los escritores y cargadores
    # reales del motor: `_save_adaptation_rules`/`load_adaptation_rules`,
    # `save_knowledge_base`/`load_knowledge_base`,
    # `_save_goal_adaptation_feedback`/`_load_goal_adaptation_feedback` y
    # `_save_goal_adaptation_learning_results`/`_load_goal_adaptation_learning_results`.
    # No es un formato idealizado: es el que el motor acepta hoy al leer.
    #
    # La CORRUPCIÓN es una DESVIACIÓN de ese formato en un contenido que está
    # PRESENTE. NO es la AUSENCIA de fichero (2.8.8.9.5.1), NO es la AUSENCIA
    # de una sección (2.8.8.9.5.2) y NO es un fichero ILEGIBLE o con raíz no
    # mapeable (también 2.8.8.9.5.2, `unreadable`). Esa frontera queda
    # declarada en `boundary` para que la detección de 2.8.8.9.6.3 no duplique
    # lo que 2.8.8.9.5.1/5.2 ya detectan.
    #
    # Este contrato NO implementa la detección: la DECLARA. La detección es
    # 2.8.8.9.6.3. Su valor es que puede contrastarse de forma automática contra
    # el comportamiento OBSERVADO en runtime, mediante la sonda
    # `tests/utils/contextual_adaptation_engine/corruption_criteria_real.py`.
    # Si lo observado se desvía, el contraste falla y el contrato queda
    # obsoleto: es intencional, un contrato que nunca falla no prueba nada.
    #
    # Es de SOLO LECTURA: no crea ficheros ni modifica el estado del motor.
    _CORRUPTION_CRITERIA: Dict[str, Any] = {
        "version": "2.8.8.9.6.1",
        "principle": (
            "La corrupción es la desviación del FORMATO REAL de la persistencia en un contenido "
            "que está PRESENTE: el dato existe, pero no es el que el motor escribe ni el que el "
            "motor sabe leer. La AUSENCIA de datos es otro fenómeno (2.8.8.9.5.1 y 2.8.8.9.5.2) "
            "y no se considera corrupción."
        ),
        # CRITERIO DE LECTURA del contrato: cada clase declara TRES cosas
        # distintas y no deben confundirse entre si.
        #   - `severity`  clasifica la DESVIACION: lo que el dato corrupto
        #                 significaria si se leyera como valido. Es una propiedad
        #                 de la clase de corrupcion y NO cambia con la deteccion.
        #   - `expected`  describe el EFECTO OBSERVABLE en el motor: lo que el
        #                 dato corrupto produce en el estado una vez aplicada la
        #                 deteccion de 2.8.8.9.6.3.
        #   - `reason`    ancla la clase en el codigo real: que hace ahora el
        #                 cargador y que haria SIN la deteccion.
        "criterio_de_lectura": {
            "severity": "clasifica la DESVIACION por si misma (su gravedad intrinseca), no el efecto que el cargador produce sobre ella",
            "expected": "es el EFECTO OBSERVABLE en el motor despues de la deteccion de 2.8.8.9.6.3: es lo que la sonda contrasta contra el runtime",
            "reason": "ancla la clase en el codigo real: que hace el cargador con el dato corrupto y que haria si la deteccion no existiera",
        },
        # REGISTRO de reconciliaciones del contrato. La `version` identifica la
        # hoja que DECLARO el contrato; cada vez que la realidad del runtime
        # cambia (y el contraste de la sonda deja de pasar) queda aqui la
        # conciliacion que la vuelve a hacer coincidir con lo observado.
        "reconciliation": [
            {"unit": "2.8.8.9.6.3",
             "reason": "la deteccion de corrupcion cambio lo que el cargador hace con el dato corrupto: el contraste por clase de la sonda de 2.8.8.9.6.1 paso a fallar en 17 clases, que son exactamente las clases cuyo efecto observable cambio",
             "changed": ["expected", "reason"],
             "unchanged": ["severity", "violation", "target", "real_format", "boundary", "invariants"],
             "classes": ["adaptation_rules.actions_string", "adaptation_rules.enabled_string",
                         "adaptation_rules.last_execution_not_iso", "adaptation_rules.name_not_string",
                         "adaptation_rules.success_rate_not_numeric", "adaptation_rules.threshold_not_numeric",
                         "adaptation_rules.trigger_invalid_value", "adaptation_rules.triggers_not_list",
                         "goal_adaptation_feedback.row_not_mapping", "goal_adaptation_feedback.section_not_list",
                         "goal_adaptation_learning_results.learning_results_not_list",
                         "goal_adaptation_learning_results.row_not_mapping",
                         "goal_adaptation_learning_results.strategy_missing_identity",
                         "knowledge_base.section_not_mapping", "knowledge_base.section_partial",
                         "knowledge_base.strategies_not_mapping", "knowledge_base.unexpected_key"],
             "vocabulary": ["silently_ignored", "record_dropped"]},
            {"unit": "2.8.8.9.7.2",
             "reason": "la RECUPERACION PARCIAL cambio lo que el cargador hace con el dato corrupto: la corrupcion se rechaza ahora SOLO en la unidad que corrompe (el campo, el grupo o el contenedor) y el resto de las unidades independientes sobrevive. El contraste por clase de la sonda de 2.8.8.9.6.1 paso a fallar en 13 clases, que son exactamente las clases cuyo efecto observable cambio",
             "changed": ["expected", "reason", "effect_vocabulary"],
             "unchanged": ["severity", "violation", "target", "real_format", "boundary", "invariants"],
             "classes": ["adaptation_rules.actions_string", "adaptation_rules.enabled_string",
                         "adaptation_rules.execution_count_not_castable",
                         "adaptation_rules.last_execution_not_iso",
                         "adaptation_rules.metadata_not_mapping",
                         "adaptation_rules.name_not_string",
                         "adaptation_rules.priority_not_castable",
                         "adaptation_rules.rules_wrong_type",
                         "adaptation_rules.success_rate_not_numeric",
                         "adaptation_rules.threshold_not_numeric",
                         "adaptation_rules.trigger_invalid_value",
                         "adaptation_rules.triggers_not_list",
                         "knowledge_base.section_partial"],
             "vocabulary": ["value_recovered"]},
        ],
        # Frontera con 2.8.8.9.5.1/5.2: lo que ya está detectado como ausencia
        # o ilegibilidad NO se declara aquí como corrupción.
        "boundary": {
            "corruption_is": "contenido presente que se aparta del formato real",
            "detection_owner": "2.8.8.9.6.3",
            "not_corruption": [
                {"case": "missing_file", "owner": "2.8.8.9.5.1",
                 "reason": "el fichero no existe: no hay contenido que pueda estar corrupto"},
                {"case": "missing_section", "owner": "2.8.8.9.5.2",
                 "reason": "la sección no está en el fichero: no hay contenido que pueda estar corrupto"},
                {"case": "unreadable_file", "owner": "2.8.8.9.5.2",
                 "reason": "el JSON no se puede parsear: no hay contenido que pueda estar corrupto"},
                {"case": "root_not_a_mapping", "owner": "2.8.8.9.5.2",
                 "reason": "la raíz del payload no es un diccionario: el formato real exige un diccionario"},
            ],
        },
        # Efectos OBSERVABLES con los que se describe el daño real de cada
        # clase de corrupción. El vocabulario es cerrado: un efecto declarado
        # que no está aquí es un contrato mal formado.
        "effect_vocabulary": {
            "rejected_whole_file": "el cargador aborta el fichero entero: avisa por log, devuelve False y se pierden también las filas válidas del mismo fichero",
            "silently_ignored": "el cargador descarta la corrupción: el CONTENIDO afectado (sección, clave o colección) no llega al estado y el motor conserva sus valores por defecto",
            "record_dropped": "el cargador descarta la corrupción: la FILA inválida no llega al estado y el resto de las filas del mismo fichero sí se carga",
            "value_recovered": "el cargador RECUPERA la corrupción: se rechaza SOLO la UNIDAD que corrompe (el campo, el grupo o el contenedor), esa unidad toma el valor por DEFECTO del formato y el resto de las unidades independientes sobrevive. El dato corrupto no llega al estado",
            "value_coerced": "la corrupción llega al estado con un valor DISTINTO del declarado, por conversión silenciosa",
            "state_contaminated": "la corrupción llega al estado TAL CUAL, contaminando la base de conocimiento",
            "read_api_raises": "una API pública de LECTURA lanza excepción con el fichero corrupto",
            "write_api_breaks": "una escritura posterior sobre el estado contaminado lanza excepción",
            "corruption_persisted": "al guardar, la corrupción se escribe en el fichero y se propaga al disco",
        },
        "severity_vocabulary": {
            "critical": "rompe una API del motor o invierte la semántica de una decisión de adaptación",
            "high": "provoca pérdida silenciosa de datos o deja el estado incoherente",
            "medium": "degrada el dato afectado sin romper el motor",
            "low": "el motor lo tolera por diseño; solo afecta a la información",
        },
        "violation_vocabulary": {
            "wrong_type": "el valor existe pero con un tipo distinto del que exige el formato real",
            "invalid_value": "el tipo es correcto pero el valor no es admisible en el campo",
            "missing_identity": "a la fila le falta el campo que la identifica",
            "unexpected_key": "el contenido trae una clave que el motor nunca escribe",
        },
        "files": {
            "adaptation_rules": {
                "file": "contextual_adaptation_rules.json",
                "writer": "_save_adaptation_rules",
                "loader": "load_adaptation_rules",
                "real_format": {
                    "root": "mapping",
                    "legacy_roots": ["list"],
                    "sections": {"version": "string", "last_updated": "string",
                                 "total_rules": "number", "rules": "list"},
                    "record": {
                        "container": "rules",
                        "type": "mapping",
                        "identity": "rule_id",
                        "fields": {
                            "rule_id": "string", "name": "string", "description": "string",
                            "condition_pattern": "string", "adaptation_actions": "list",
                            "context_triggers": "list", "confidence_threshold": "number",
                            "priority": "number", "enabled": "boolean", "success_rate": "number",
                            "execution_count": "number", "last_execution": "string|null",
                            "adaptation_score": "number", "constraints": "list",
                            "metadata": "mapping", "deadline": "any",
                        },
                    },
                },
                "corruptions": [
                    {"id": "adaptation_rules.rules_wrong_type", "target": "rules",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["value_recovered"],
                     "reason": "el CONTENEDOR `rules` cambio de forma y se RECONSTRUYE con los valores que sean filas validas por el FORMATO REAL: las claves no se usan como identidad y el resto de las filas se carga con normalidad"},
                    {"id": "adaptation_rules.row_not_mapping", "target": "rules[]",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["record_dropped"],
                     "reason": "la fila no es un diccionario: el cargador la descarta y carga el resto"},
                    {"id": "adaptation_rules.row_missing_identity", "target": "rules[].rule_id",
                     "violation": "missing_identity", "severity": "medium",
                     "expected": ["record_dropped"],
                     "reason": "la fila no tiene una identidad REGISTRABLE: sin `rule_id` (o con un `rule_id` que no es una cadena no vacia, que no es identidad) no se puede registrar y se descarta; el cargador NUNCA inventa una identidad ni deja que dos filas colisionen con la misma"},
                    {"id": "adaptation_rules.priority_not_castable", "target": "rules[].priority",
                     "violation": "invalid_value", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `priority`: toma su valor por DEFECTO y el resto de la fila y del fichero sobrevive; sin la deteccion, la conversion a entero lanzaba ValueError y abortaba la carga de TODO el fichero"},
                    {"id": "adaptation_rules.execution_count_not_castable", "target": "rules[].execution_count",
                     "violation": "invalid_value", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `execution_count`: toma su valor por DEFECTO y el resto de la fila y del fichero sobrevive; sin la deteccion, la conversion a entero lanzaba ValueError y abortaba la carga de TODO el fichero"},
                    {"id": "adaptation_rules.metadata_not_mapping", "target": "rules[].metadata",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `metadata`: toma su valor por DEFECTO y el resto de la fila y del fichero sobrevive; sin la deteccion, `dict(...)` sobre un valor que no es diccionario lanzaba ValueError y abortaba la carga de TODO el fichero"},
                    {"id": "adaptation_rules.actions_string", "target": "rules[].adaptation_actions",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `adaptation_actions`: la regla se conserva INERTE (sin acciones) y el resto de la fila y del fichero sobrevive; sin la deteccion, `list(\"abc\")` troceaba las acciones en caracteres y el motor las ejecutaba"},
                    {"id": "adaptation_rules.enabled_string", "target": "rules[].enabled",
                     "violation": "wrong_type", "severity": "critical",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `enabled`: la regla se conserva DESACTIVADA (su estado se desconoce) y el resto de la fila y del fichero sobrevive; sin la deteccion, `bool(\"false\")` la activaba e invertia la decision de adaptacion"},
                    {"id": "adaptation_rules.threshold_not_numeric", "target": "rules[].confidence_threshold",
                     "violation": "invalid_value", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `confidence_threshold`: conserva su valor por DEFECTO (0.7) y el resto de la fila y del fichero sobrevive; sin la deteccion, el umbral no numerico se degradaba a 0.0 y la regla se aplicaba sin filtro de confianza"},
                    {"id": "adaptation_rules.success_rate_not_numeric", "target": "rules[].success_rate",
                     "violation": "invalid_value", "severity": "medium",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `success_rate`: la regla se conserva sin exitos (0.0) y el resto de la fila y del fichero sobrevive; sin la deteccion, la tasa no numerica se degradaba a 0.0 y falseaba la evaluacion de la regla"},
                    {"id": "adaptation_rules.triggers_not_list", "target": "rules[].context_triggers",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `context_triggers`: la regla se conserva INERTE (sin disparadores) y el resto de la fila y del fichero sobrevive; sin la deteccion, la cadena se recorria caracter a caracter y la regla nunca disparaba"},
                    {"id": "adaptation_rules.trigger_invalid_value", "target": "rules[].context_triggers[]",
                     "violation": "invalid_value", "severity": "medium",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el DISPARADOR invalido: se conservan los disparadores validos y el resto de la fila y del fichero sobrevive; sin la deteccion, el disparador fuera de `ContextType` se filtraba en silencio y la regla perdia ese disparador"},
                    {"id": "adaptation_rules.last_execution_not_iso", "target": "rules[].last_execution",
                     "violation": "invalid_value", "severity": "low",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `last_execution`: la regla se conserva como nunca ejecutada y el resto de la fila y del fichero sobrevive; sin la deteccion, la marca no ISO se degradaba a None, tolerancia deliberada del cargador"},
                    {"id": "adaptation_rules.name_not_string", "target": "rules[].name",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el CAMPO `name`: la regla se conserva con su propia identidad y el resto de la fila y del fichero sobrevive; sin la deteccion, el nombre no se validaba y el valor corrupto se conservaba tal cual en la regla"},
                ],
            },
            "knowledge_base": {
                "file": "contextual_knowledge_base.json",
                "writer": "save_knowledge_base",
                "loader": "load_knowledge_base",
                "real_format": {
                    "root": "mapping",
                    "legacy_roots": [],
                    "sections": {"version": "string", "last_updated": "string",
                                 "context_snapshots": "number", "adaptation_history": "number",
                                 "knowledge_transfers": "number", "data": "mapping"},
                    "record": {
                        "container": "data",
                        "type": "mapping",
                        "identity": None,
                        "fields": {
                            "context_patterns": "mapping", "success_patterns": "mapping",
                            "performance_baselines": "mapping", "adaptation_strategies": "mapping",
                            "integration_records": "list", "transfer_efficiency": "mapping",
                        },
                    },
                },
                "corruptions": [
                    {"id": "knowledge_base.data_not_mapping", "target": "data",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["silently_ignored"],
                     "reason": "si `data` no es un diccionario el cargador se salta el bloque entero: la base queda con sus valores por defecto y sin aviso"},
                    {"id": "knowledge_base.section_not_mapping", "target": "data.context_patterns",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["silently_ignored"],
                     "reason": "la seccion que no es diccionario se descarta: no llega al estado y la base conserva sus valores por defecto; el resto de las secciones del mismo fichero si se carga"},
                    {"id": "knowledge_base.strategies_not_mapping", "target": "data.adaptation_strategies",
                     "violation": "wrong_type", "severity": "critical",
                     "expected": ["silently_ignored"],
                     "reason": "el mapa de estrategias que no es diccionario se descarta: no llega al estado y la base conserva sus valores por defecto; sin la deteccion, `get_available_strategies` rompia al hacer `.get` sobre un valor que no era diccionario"},
                    {"id": "knowledge_base.unexpected_key", "target": "data.<clave_desconocida>",
                     "violation": "unexpected_key", "severity": "low",
                     "expected": ["silently_ignored"],
                     "reason": "una clave que el motor nunca escribe no se aplica: no llega al estado y el resto de la base se carga con normalidad"},
                    {"id": "knowledge_base.section_partial", "target": "data.context_patterns.<contexto>",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["value_recovered"],
                     "reason": "la corrupcion se rechaza SOLO en el GRUPO (contexto) que se aparta del formato real: ese grupo se descarta y los grupos HERMANOS de la misma seccion sobreviven; antes se descartaba la seccion entera"},
                ],
            },
            "goal_adaptation_feedback": {
                "file": "goal_adaptation_feedback.json",
                "writer": "_save_goal_adaptation_feedback",
                "loader": "_load_goal_adaptation_feedback",
                "real_format": {
                    "root": "mapping",
                    "legacy_roots": [],
                    "sections": {"goal_adaptation_feedback": "list",
                                 "adaptation_history": "list", "last_updated": "string"},
                    "record": {
                        "container": "goal_adaptation_feedback",
                        "type": "mapping",
                        "identity": "adaptation_id",
                        "fields": {"adaptation_id": "string", "success": "boolean",
                                   "original_goal_id": "any", "adapted_goal_id": "any",
                                   "adaptation_context": "mapping", "execution_result": "mapping",
                                   "verification_result": "mapping", "improvement_analysis": "mapping",
                                   "timestamp": "string"},
                    },
                },
                "corruptions": [
                    {"id": "goal_adaptation_feedback.section_not_list", "target": "goal_adaptation_feedback",
                     "violation": "wrong_type", "severity": "critical",
                     "expected": ["silently_ignored"],
                     "reason": "la seccion que no es lista no llega al estado: la base conserva su lista vacia y la escritura posterior ya no revienta; sin la deteccion, el valor se copiaba tal cual y `_capture_feedback` reventaba al hacer `.append` sobre el"},
                    {"id": "goal_adaptation_feedback.row_not_mapping", "target": "goal_adaptation_feedback[]",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["record_dropped"],
                     "reason": "la fila que no es un diccionario se descarta: no llega al estado y el resto de las filas del mismo fichero si se carga"},
                    {"id": "goal_adaptation_feedback.history_not_list", "target": "adaptation_history",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["silently_ignored"],
                     "reason": "un historial que no es lista se recorre por claves y se descarta entero: el historial se pierde sin aviso"},
                ],
            },
            "goal_adaptation_learning_results": {
                "file": "goal_adaptation_learning_results.json",
                "writer": "_save_goal_adaptation_learning_results",
                "loader": "_load_goal_adaptation_learning_results",
                "real_format": {
                    "root": "mapping",
                    "legacy_roots": [],
                    "sections": {"learning_results": "list",
                                 "adaptation_strategies": "mapping", "last_updated": "string"},
                    "record": {
                        "container": "learning_results",
                        "type": "mapping",
                        "identity": "adaptation_id",
                        "fields": {"adaptation_id": "string", "updated_strategies": "mapping",
                                   "convergence_metrics": "mapping", "learned_patterns": "list"},
                    },
                },
                "corruptions": [
                    {"id": "goal_adaptation_learning_results.learning_results_not_list", "target": "learning_results",
                     "violation": "wrong_type", "severity": "critical",
                     "expected": ["silently_ignored"],
                     "reason": "la seccion que no es lista no llega al estado: la base conserva su lista vacia y al guardar ya no se escribe la corrupcion; sin la deteccion, el valor se copiaba tal cual y sus claves se escribian como filas, propagando la corrupcion al disco"},
                    {"id": "goal_adaptation_learning_results.row_not_mapping", "target": "learning_results[]",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["record_dropped"],
                     "reason": "la fila que no es un diccionario se descarta: no llega al estado y el resto de las filas del mismo fichero si se carga; sin la deteccion, el filtro conservaba la fila y se volvia a escribir"},
                    {"id": "goal_adaptation_learning_results.strategies_not_mapping", "target": "adaptation_strategies",
                     "violation": "wrong_type", "severity": "high",
                     "expected": ["silently_ignored"],
                     "reason": "el aplanador devuelve un índice vacío y no se restaura ninguna estrategia aprendida, sin aviso"},
                    {"id": "goal_adaptation_learning_results.strategy_value_not_mapping", "target": "adaptation_strategies.<strategy_id>",
                     "violation": "wrong_type", "severity": "medium",
                     "expected": ["silently_ignored"],
                     "reason": "una entrada que no es diccionario ni lista se ignora en el aplanado y esa estrategia no se restaura"},
                    {"id": "goal_adaptation_learning_results.strategy_missing_identity", "target": "adaptation_strategies.<strategy_id>",
                     "violation": "missing_identity", "severity": "critical",
                     "expected": ["silently_ignored"],
                     "reason": "una estrategia sin evidencia no se restaura: no llega al estado y no se ofrece con una confianza inventada; sin la deteccion, el contrato de identidad de 2.8.8.9.2.1 se exigia al GUARDAR pero no al CARGAR"},
                ],
            },
        },
        "invariants": [
            "corruption_is_never_absence",
            "every_corruption_declares_target_violation_severity_and_effects",
            "every_expected_effect_belongs_to_the_effect_vocabulary",
            "every_corruption_is_covered_by_the_runtime_probe",
            "detection_is_read_only",
        ],
    }

    # ============================================== DATOS RECUPERABLES (2.8.8.9.7.1)
    #
    # La DETECCION de 2.8.8.9.6.3 evita que el dato corrupto se use, pero el
    # rechazo de una unidad no tiene por que arrastrar a las unidades
    # INDEPENDIENTES que la acompanan. Este contrato declara, para cada clase
    # de corrupcion, QUE dato es recuperable, A QUE NIVEL y CON QUE POLITICA.
    #
    # La recuperacion NO inventa datos: el campo corrupto toma el valor por
    # DEFECTO que el FORMATO REAL declara y el resto de la unidad se conserva
    # integro. La IMPLEMENTACION de esta recuperacion es 2.8.8.9.7.2; esta hoja
    # DECLARA el contrato y lo CONTRASTA contra el runtime.
    _RECOVERABLE_DATA: Dict[str, Any] = {
        "version": "2.8.8.9.7.1",
        "principle": (
            "Una corrupcion rechaza SOLO la unidad que corrompe. Todo lo demas que el "
            "FORMATO REAL declara valido y que NO depende de la unidad corrupta debe "
            "SOBREVIVIR. La recuperacion NO inventa datos: el campo corrupto toma el valor "
            "por DEFECTO del formato y el resto de la unidad se conserva integro."
        ),
        # NIVELES: la jerarquia de la unidad que se puede recuperar. Un nivel mas
        # alto contiene a los mas bajos: `campo` esta dentro de `fila`, `fila`
        # dentro de `bloque`/`seccion`, y todo dentro de `fichero`.
        "levels": {
            "fichero": "el fichero de persistencia completo",
            "bloque": "un bloque de primer nivel del fichero (`rules`, `data`)",
            "seccion": "una seccion de la base o del fichero (`context_patterns`, `learning_results`...)",
            "grupo": "un grupo indexado por contexto dentro de una seccion (`context_patterns.<contexto>`)",
            "fila": "un registro de una lista (`rules[]`, `goal_adaptation_feedback[]`...)",
            "entrada": "una entrada de un indice (`adaptation_strategies.<strategy_id>`)",
            "campo": "un campo de un registro",
        },
        # POLITICAS: como se recupera (o no) la unidad corrompida.
        "policies": {
            "none": "la corrupcion ocupa toda la unidad: el motor no puede leer su contenido y no hay nada que recuperar",
            "preserve_siblings": "descartar la unidad corrupta y conservar las unidades independientes que la acompanan",
            "default_the_field": "sustituir el campo corrupto por su valor por defecto del formato y conservar el resto de la unidad",
            "keep_valid_elements": "conservar los elementos validos del campo y descartar solo los invalidos",
            "adapt_container": "el contenedor cambio de forma pero su contenido sigue siendo valido: se reconstruye el contenedor",
        },
        # TOKENS de lo recuperable: vocabulary cerrado que la sonda usa para
        # contrastar la declaracion contra lo observado en runtime.
        "recoverable_tokens": {
            "siblings": "las unidades independientes que acompanan a la unidad corrompida",
            "row_fields": "los campos validos de la fila corrompida: la fila se conserva con el campo corrupto por defecto",
            "elements": "los elementos validos del campo corrompido: se descarta solo el elemento invalido",
            "container_values": "los valores validos del contenedor corrompido: se reconstruye el contenedor",
        },
        # VALOR POR DEFECTO de cada campo de una fila de regla, tal y como lo
        # declara el FORMATO REAL. Son los valores que el cargador usa cuando
        # el campo NO aparece, y por tanto los unicos que puede usar la
        # recuperacion sin inventar nada.
        "field_defaults": {
            "name": {"value": "$rule_id", "type": "string",
                     "note": "el valor por defecto del formato es la propia identidad de la regla"},
            "description": {"value": "", "type": "string", "note": "valor por defecto del formato"},
            "condition_pattern": {"value": "", "type": "string",
                                  "note": "valor por defecto del formato: sin patron la regla no se dispara, pero la fila se conserva integra"},
            "adaptation_actions": {"value": [], "type": "list",
                                   "note": "la regla se conserva pero queda INERTE: no tiene acciones que ejecutar"},
            "context_triggers": {"value": [], "type": "list",
                                 "note": "la regla se conserva pero queda INERTE: no dispara en ningun contexto"},
            "confidence_threshold": {"value": 0.7, "type": "number",
                                     "note": "valor por defecto del formato: evita el 0.0 sin filtro de confianza"},
            "priority": {"value": 1, "type": "number", "note": "valor por defecto del formato"},
            "enabled": {"value": False, "type": "boolean",
                        "note": "EXCEPCION: el cargador usa True, pero recuperar con True ACTIVARIA una regla cuyo estado se desconoce (severidad critica). Se conserva DESACTIVADA"},
            "success_rate": {"value": 0.0, "type": "number", "note": "valor por defecto del formato: la regla aparece sin exitos"},
            "execution_count": {"value": 0, "type": "number", "note": "valor por defecto del formato"},
            "last_execution": {"value": None, "type": "string|null", "note": "valor por defecto del formato: nunca ejecutada"},
            "adaptation_score": {"value": 0.0, "type": "number", "note": "valor por defecto del formato"},
            "constraints": {"value": [], "type": "list", "note": "valor por defecto del formato"},
            "metadata": {"value": {}, "type": "mapping", "note": "valor por defecto del formato"},
            "deadline": {"value": None, "type": "any", "note": "valor por defecto del formato"},
        },
        # Campos cuyo valor por defecto de RECUPERACION difiere del que usa el
        # cargador. Solo puede haber EXCEPCIONES conservadoras: un valor por
        # defecto mas permisivo que el del cargador activaria datos que el
        # motor no puede saber.
        "conservative_defaults": ["enabled"],
        # REGLA DE INDEPENDENCIA: dos unidades son independientes si la ruta de
        # una NO es un prefijo de la ruta de la otra. La corrupcion de una no
        # determina el valor de la otra, asi que la otra debe sobrevivir.
        "independence_rule": (
            "dos unidades son independientes si la ruta de una NO es un prefijo de la ruta "
            "de la otra: la corrupcion de una no determina el valor de la otra, de modo que "
            "la otra debe sobrevivir al rechazo"
        ),
        "files": {
            "adaptation_rules": {
                "file": "contextual_adaptation_rules.json",
                "unit_chain": ["fichero", "bloque:rules", "fila:<rule_id>", "campo:<nombre>"],
                "classes": {
                    "adaptation_rules.rules_wrong_type": {
                        "corrupt_unit": "bloque:rules", "level": "bloque", "policy": "adapt_container",
                        "recovers": ["container_values"],
                        "condition": "los VALORES del mapeo que sean filas validas por el FORMATO REAL",
                        "note": "las claves del mapeo NO se usan como identidad: sin `rule_id` propio la fila no se puede registrar"},
                    "adaptation_rules.row_not_mapping": {
                        "corrupt_unit": "fila:<indice>", "level": "fila", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "una fila que no es un mapeo no contiene ningun dato recuperable"},
                    "adaptation_rules.row_missing_identity": {
                        "corrupt_unit": "fila:<indice>", "level": "fila", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "sin identidad REGISTRABLE no hay registro: sin `rule_id`, o con un `rule_id` que no es una cadena no vacia, la fila no se puede registrar y NO se inventa una; una identidad que ya usa otra fila tampoco identifica a esta, asi que la fila se rechaza y la que ya estaba registrada sobrevive"},
                    "adaptation_rules.priority_not_castable": {
                        "corrupt_unit": "fila:<rule_id>.campo:priority", "level": "campo",
                        "policy": "default_the_field", "field_default": 1,
                        "recovers": ["siblings", "row_fields"],
                        "note": "la conversion a entero es ESTRICTA: el error aborta el FICHERO ENTERO, no solo la fila"},
                    "adaptation_rules.execution_count_not_castable": {
                        "corrupt_unit": "fila:<rule_id>.campo:execution_count", "level": "campo",
                        "policy": "default_the_field", "field_default": 0,
                        "recovers": ["siblings", "row_fields"],
                        "note": "la conversion a entero es ESTRICTA: el error aborta el FICHERO ENTERO, no solo la fila"},
                    "adaptation_rules.metadata_not_mapping": {
                        "corrupt_unit": "fila:<rule_id>.campo:metadata", "level": "campo",
                        "policy": "default_the_field", "field_default": {},
                        "recovers": ["siblings", "row_fields"],
                        "note": "la conversion a mapeo es ESTRICTA: el error aborta el FICHERO ENTERO, no solo la fila"},
                    "adaptation_rules.actions_string": {
                        "corrupt_unit": "fila:<rule_id>.campo:adaptation_actions", "level": "campo",
                        "policy": "default_the_field", "field_default": [],
                        "recovers": ["siblings", "row_fields"],
                        "note": "sin acciones la regla se conserva INERTE: no ejecuta nada pero no se pierde su resto"},
                    "adaptation_rules.enabled_string": {
                        "corrupt_unit": "fila:<rule_id>.campo:enabled", "level": "campo",
                        "policy": "default_the_field", "field_default": False,
                        "recovers": ["siblings", "row_fields"],
                        "note": "se conserva DESACTIVADA: activar una regla cuyo estado se desconoce es la desviacion mas grave"},
                    "adaptation_rules.threshold_not_numeric": {
                        "corrupt_unit": "fila:<rule_id>.campo:confidence_threshold", "level": "campo",
                        "policy": "default_the_field", "field_default": 0.7,
                        "recovers": ["siblings", "row_fields"],
                        "note": "recuperar con 0.7 conserva el filtro de confianza que el 0.0 eliminaba"},
                    "adaptation_rules.success_rate_not_numeric": {
                        "corrupt_unit": "fila:<rule_id>.campo:success_rate", "level": "campo",
                        "policy": "default_the_field", "field_default": 0.0,
                        "recovers": ["siblings", "row_fields"],
                        "note": "la regla se conserva sin exitos: no se inventa ninguna ejecucion"},
                    "adaptation_rules.triggers_not_list": {
                        "corrupt_unit": "fila:<rule_id>.campo:context_triggers", "level": "campo",
                        "policy": "default_the_field", "field_default": [],
                        "recovers": ["siblings", "row_fields"],
                        "note": "sin disparadores la regla se conserva INERTE: no se aplica en ningun contexto"},
                    "adaptation_rules.trigger_invalid_value": {
                        "corrupt_unit": "fila:<rule_id>.campo:context_triggers[]", "level": "campo",
                        "policy": "keep_valid_elements",
                        "recovers": ["siblings", "row_fields", "elements"],
                        "note": "es la clase mas fina: se descarta SOLO el disparador invalido y la regla sigue funcionando con los demas"},
                    "adaptation_rules.last_execution_not_iso": {
                        "corrupt_unit": "fila:<rule_id>.campo:last_execution", "level": "campo",
                        "policy": "default_the_field", "field_default": None,
                        "recovers": ["siblings", "row_fields"],
                        "note": "la regla se conserva como nunca ejecutada"},
                    "adaptation_rules.name_not_string": {
                        "corrupt_unit": "fila:<rule_id>.campo:name", "level": "campo",
                        "policy": "default_the_field", "field_default": "$rule_id",
                        "recovers": ["siblings", "row_fields"],
                        "note": "el nombre se recupera con la identidad de la regla"},
                },
            },
            "knowledge_base": {
                "file": "contextual_knowledge_base.json",
                "unit_chain": ["fichero", "bloque:data", "seccion:<clave>", "grupo:<contexto>", "entrada:<indice>"],
                "classes": {
                    "knowledge_base.data_not_mapping": {
                        "corrupt_unit": "bloque:data", "level": "bloque", "policy": "none",
                        "recovers": [],
                        "note": "el contenido del bloque `data` es opaco para el motor: no hay forma de saber que secciones contiene"},
                    "knowledge_base.section_not_mapping": {
                        "corrupt_unit": "seccion:context_patterns", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "los grupos de la seccion corrupta NO son independientes: estan dentro de ella"},
                    "knowledge_base.strategies_not_mapping": {
                        "corrupt_unit": "seccion:adaptation_strategies", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "las entradas de la seccion corrupta NO son independientes: estan dentro de ella"},
                    "knowledge_base.unexpected_key": {
                        "corrupt_unit": "seccion:<clave_desconocida>", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "una clave que el motor nunca escribe no tiene contenido declarado que recuperar"},
                    "knowledge_base.section_partial": {
                        "corrupt_unit": "seccion:context_patterns.grupo:<contexto>", "level": "grupo", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "los grupos hermanos de la MISMA seccion son independientes del grupo corrupto"},
                },
            },
            "goal_adaptation_feedback": {
                "file": "goal_adaptation_feedback.json",
                "unit_chain": ["fichero", "seccion:<clave>", "fila:<adaptation_id>", "campo:<nombre>"],
                "classes": {
                    "goal_adaptation_feedback.section_not_list": {
                        "corrupt_unit": "seccion:goal_adaptation_feedback", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "las filas de la seccion corrupta NO son independientes: estan dentro de ella"},
                    "goal_adaptation_feedback.row_not_mapping": {
                        "corrupt_unit": "fila:<indice>", "level": "fila", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "una fila que no es un mapeo no contiene ningun dato recuperable"},
                    "goal_adaptation_feedback.history_not_list": {
                        "corrupt_unit": "seccion:adaptation_history", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "las entradas del historial corrupto NO son independientes: estan dentro de el"},
                },
            },
            "goal_adaptation_learning_results": {
                "file": "goal_adaptation_learning_results.json",
                "unit_chain": ["fichero", "seccion:<clave>", "fila:<adaptation_id>", "entrada:<strategy_id>"],
                "classes": {
                    "goal_adaptation_learning_results.learning_results_not_list": {
                        "corrupt_unit": "seccion:learning_results", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "las filas de la seccion corrupta NO son independientes: estan dentro de ella"},
                    "goal_adaptation_learning_results.row_not_mapping": {
                        "corrupt_unit": "fila:<indice>", "level": "fila", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "una fila que no es un mapeo no contiene ningun dato recuperable"},
                    "goal_adaptation_learning_results.strategies_not_mapping": {
                        "corrupt_unit": "seccion:adaptation_strategies", "level": "seccion", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "las entradas de la seccion corrupta NO son independientes: estan dentro de ella"},
                    "goal_adaptation_learning_results.strategy_value_not_mapping": {
                        "corrupt_unit": "entrada:<strategy_id>", "level": "entrada", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "una entrada que no es un mapeo no contiene ningun dato recuperable"},
                    "goal_adaptation_learning_results.strategy_missing_identity": {
                        "corrupt_unit": "entrada:<strategy_id>", "level": "entrada", "policy": "preserve_siblings",
                        "recovers": ["siblings"],
                        "note": "sin EVIDENCIA (confidence, success_rate, last_updated) la entrada no es una estrategia aprendida: no se puede ofrecer con una confianza inventada"},
                },
            },
        },
        "invariants": [
            "el dato corrupto nunca llega al estado",
            "la recuperacion no inventa valores fuera de `field_defaults`",
            "una unidad que no depende de la unidad corrupta sobrevive",
            "la unidad corrupta se rechaza en su NIVEL, no en un nivel superior",
            "la recuperacion no reescribe el fichero: es una operacion de CARGA",
        ],
        "reconciliation": [
            {"unit": "2.8.8.9.7.1",
             "reason": "esta hoja DECLARA el contrato de lo recuperable y lo CONTRASTA contra el runtime. La DETERMINACION que hizo queda aqui: las clases que perdian el dato recuperable eran las que se listan en `pending`, y 2.8.8.9.7.2 las ha implementado",
             "changed": [],
             "unchanged": ["levels", "policies", "recoverable_tokens", "field_defaults", "independence_rule", "invariants"],
             "pending": [],
             "resolved": [
                 "adaptation_rules.priority_not_castable",
                 "adaptation_rules.execution_count_not_castable",
                 "adaptation_rules.metadata_not_mapping",
                 "adaptation_rules.actions_string",
                 "adaptation_rules.enabled_string",
                 "adaptation_rules.threshold_not_numeric",
                 "adaptation_rules.success_rate_not_numeric",
                 "adaptation_rules.triggers_not_list",
                 "adaptation_rules.trigger_invalid_value",
                 "adaptation_rules.last_execution_not_iso",
                 "adaptation_rules.name_not_string",
                 "adaptation_rules.rules_wrong_type",
                 "knowledge_base.section_partial",
             ],
             "implementation_owner": "2.8.8.9.7.2"},
            {"unit": "2.8.8.9.7.2",
             "reason": "la RECUPERACION PARCIAL implementa el contrato declarado: la corrupcion se rechaza SOLO en la unidad que corrompe y el resto de las unidades independientes sobrevive. El runtime ya satisface el contrato en las 27 clases y no queda ninguna pendiente",
             "changed": [],
             "unchanged": ["levels", "policies", "recoverable_tokens", "field_defaults", "independence_rule", "invariants"],
             "pending": [],
             "resolved": [
                 "adaptation_rules.priority_not_castable",
                 "adaptation_rules.execution_count_not_castable",
                 "adaptation_rules.metadata_not_mapping",
                 "adaptation_rules.actions_string",
                 "adaptation_rules.enabled_string",
                 "adaptation_rules.threshold_not_numeric",
                 "adaptation_rules.success_rate_not_numeric",
                 "adaptation_rules.triggers_not_list",
                 "adaptation_rules.trigger_invalid_value",
                 "adaptation_rules.last_execution_not_iso",
                 "adaptation_rules.name_not_string",
                 "adaptation_rules.rules_wrong_type",
                 "knowledge_base.section_partial",
             ],
             "implementation_owner": "2.8.8.9.7.2"},
        ],
    }

    # ============================================== FALLBACK por CORRUPCION TOTAL (2.8.8.9.8.1)
    #
    # La CORRUPCION TOTAL es la perdida de TODOS los datos de persistencia a la
    # vez: los cuatro ficheros de persistencia EXISTEN pero NINGUNO aporta una
    # sola unidad de datos utilizable al estado del motor.
    #
    # Este contrato DECLARA el comportamiento REAL que el motor ofrece HOY ante
    # esa perdida: que capas de fallback existen, que MODOS de perdida total
    # reconoce, que INVARIANTES deben cumplirse para que JARVIS pueda seguir
    # operando, y que queda PENDIENTE.
    #
    # NO lo implementa: la IMPLEMENTACION del fallback es 2.8.8.9.8.2, que ya
    # esta hecha. Su valor es que puede contrastarse de forma automatica
    # contra el comportamiento OBSERVADO en runtime, mediante la sonda
    # `tests/utils/contextual_adaptation_engine/identify_fallback_real.py`.
    # Si lo observado se desvia, el contraste falla y el contrato queda
    # obsoleto: es intencional, un contrato que nunca falla no prueba nada.
    #
    # Es de SOLO LECTURA: no crea ficheros ni modifica el estado del motor.
    _TOTAL_LOSS_FALLBACK: Dict[str, Any] = {
        "version": "2.8.8.9.8.1",
        "principle": (
            "Ante la perdida TOTAL de datos de persistencia JARVIS DEBE poder seguir "
            "operando. El motor conserva su estado por DEFECTO en memoria, el ciclo de "
            "captura-analisis-ejecucion continua, los ficheros corruptos NO se reescriben "
            "(su contenido sigue intacto para su diagnostico), y la perdida se REPORTA de "
            "forma que el consumidor puede saber que esta usando defaults en lugar de "
            "datos reales. El fallback NO inventa datos: el estado por defecto es el que el "
            "motor declara en CODIGO, no un dato inventado a partir del fichero roto."
        ),
        # QUE ES UNA PERDIDA TOTAL: la definicion operativa, para que la sonda y el
        # runtime no midan cosas distintas.
        "definition": {
            "total_loss": "los cuatro ficheros de persistencia existen pero NINGUNO aporta una sola unidad de datos utilizable al estado del motor",
            "not_total_loss": "un fichero que aporta datos utilizables NO es perdida total, aunque los demas esten perdidos: la perdida es TOTAL solo si TODOS han perdido sus datos",
        },
        # MODOS de perdida total: la FORMA en que la perdida se produce. Es un
        # vocabulario CERRADO: la sonda mide estos cuatro modos y ninguno mas.
        "loss_modes": {
            "unreadable_file": "el contenido del fichero no se puede parsear como JSON",
            "non_mapping_root": "el JSON se parsea pero su raiz no es un mapeo",
            "list_root_without_valid_rows": "la raiz es una lista que no aporta ninguna fila valida",
            "empty_mapping_root": "la raiz es un mapeo vacio: el fichero no aporta ninguna seccion de datos",
        },
        # CAPAS de fallback: lo que el motor REALMENTE ofrece hoy. Cada capa es
        # una propiedad OBSERVABLE del runtime, no una intencion.
        "fallback_layers": {
            "defaults_in_memory": "el estado por DEFECTO del motor sobrevive a la perdida total porque los cargadores no vacian el estado cuando no pueden cargar",
            "continuity_of_operation": "el ciclo de captura, analisis y ejecucion sigue funcionando con los defaults",
            "non_destructive_load": "la carga NO reescribe los ficheros corruptos: su contenido queda intacto en disco",
            "detection_available": "las APIs de deteccion (`detect_corruption`, `detect_absent_sections`) informan de la perdida",
            "full_backup": "`backup_data()` copia los CUATRO ficheros de persistencia: reglas, base de conocimiento, feedback y resultados de aprendizaje",
        },
        # INVARIANTES: lo que el fallback DEBE garantizar en cada modo de perdida
        # total. Cada uno declara a que CAPA pertenece y si el runtime lo
        # SATISFACE hoy. Los que no se satisfacen estan en `pending`.
        "invariants": {
            "state_equals_fresh_defaults": {
                "statement": "tras la perdida total el estado del motor es IDENTICO al de un motor recien creado sin ficheros: solo valen los defaults del codigo",
                "layer": "defaults_in_memory", "satisfied": True,
            },
            "operation_continues": {
                "statement": "tras la perdida total el motor puede capturar, analizar y ejecutar, y la ejecucion termina con exito",
                "layer": "continuity_of_operation", "satisfied": True,
            },
            "files_not_overwritten": {
                "statement": "tras la perdida total los ficheros corruptos conservan su contenido byte a byte: la carga no los reescribe",
                "layer": "non_destructive_load", "satisfied": True,
            },
            "loss_is_detectable": {
                "statement": "la perdida total es DETECTABLE por las APIs de deteccion: alguna de ellas informa de los ficheros o secciones afectados",
                "layer": "detection_available", "satisfied": True,
            },
            "loss_visible_in_status": {
                "statement": "el estado AGREGADO del motor (`get_engine_status()`) informa de la perdida total: declara al menos una anomalia",
                "layer": "detection_available", "satisfied": True,
            },
            "load_result_is_truthful": {
                "statement": "`load_all_data()` devuelve FALSO cuando la perdida total impidio cargar datos: no declara un exito que no ocurrio",
                "layer": "detection_available", "satisfied": True,
            },
            "backup_covers_all_persistence": {
                "statement": "`backup_data()` respalda los CUATRO ficheros de persistencia, no solo dos",
                "layer": "full_backup", "satisfied": True,
            },
        },
        # PENDIENTE: los invariantes que el runtime NO satisface hoy. La
        # IMPLEMENTACION de estos es 2.8.8.9.8.2.
        "pending": [],
        "reconciliation": [
            {"unit": "2.8.8.9.8.1",
             "reason": "esta hoja DECLARA el contrato del FALLBACK por corrupcion total y lo CONTRASTA contra el runtime. La DETERMINACION que hizo queda aqui: el motor NO ofrece hoy un fallback COMPLETO, porque el estado agregado no informa de la perdida, la carga declara un exito que no ocurrio y el respaldo solo cubre dos de los cuatro ficheros. Los tres invariantes que fallan estan en `pending`",
             "changed": [],
             "unchanged": ["principle", "definition", "loss_modes", "fallback_layers", "invariants"],
             "pending": [
                 "loss_visible_in_status",
                 "load_result_is_truthful",
                 "backup_covers_all_persistence",
             ],
             "resolved": [],
             "implementation_owner": "2.8.8.9.8.2"},
            {"unit": "2.8.8.9.8.2",
             "reason": "el FALLBACK por corrupcion total queda IMPLEMENTADO: el estado AGREGADO declara la perdida (los ficheros ilegibles se cuentan como anomalia), la carga DECLARA lo que ocurrio (`load_all_data()` devuelve FALSO cuando la persistencia existe pero no aporta ninguna unidad de datos) y el RESPALDO cubre los CUATRO ficheros de persistencia. El runtime satisface los siete invariantes en los cuatro modos de perdida total y no queda ninguno pendiente",
             "changed": ["invariants.loss_visible_in_status", "invariants.load_result_is_truthful", "invariants.backup_covers_all_persistence", "fallback_layers.partial_backup -> fallback_layers.full_backup"],
             "unchanged": ["principle", "definition", "loss_modes", "invariants.state_equals_fresh_defaults", "invariants.operation_continues", "invariants.files_not_overwritten", "invariants.loss_is_detectable"],
             "pending": [],
             "resolved": ["loss_visible_in_status", "load_result_is_truthful", "backup_covers_all_persistence"],
             "implementation_owner": "2.8.8.9.8.2"},
        ],
    }

    def corruption_criteria(self) -> Dict[str, Any]:
        """Contrato DECLARATIVO de los criterios de CORRUPCIÓN (2.8.8.9.6.1).

        Declara qué constituye corrupción según el FORMATO REAL de la
        persistencia: para cada fichero, el formato que el motor escribe y
        sabe leer, y las clases de desviación respecto de ese formato, con el
        efecto observable que cada una provoca y su severidad.

        Es de SOLO LECTURA: no crea ficheros, no escribe y no altera el estado
        del motor. Devuelve una COPIA profunda, de modo que el llamante no pueda
        mutar el contrato de la clase.

        La declaración NO sustituye a la verificación: la sonda
        `tests/utils/contextual_adaptation_engine/corruption_criteria_real.py`
        contrasta esta declaración contra el comportamiento OBSERVADO en runtime.
        La IMPLEMENTACIÓN de la detección es 2.8.8.9.6.3.
        """
        return copy.deepcopy(self._CORRUPTION_CRITERIA)

    def recoverable_data(self) -> Dict[str, Any]:
        """Contrato DECLARATIVO de los DATOS RECUPERABLES (2.8.8.9.7.1).

        Declara, para cada clase de corrupcion de `corruption_criteria()`, QUE
        dato es recuperable, A QUE NIVEL y CON QUE POLITICA: una corrupcion
        rechaza SOLO la unidad que corrompe y el resto de las unidades
        INDEPENDIENTES debe sobrevivir.

        La recuperacion NO inventa datos: el campo corrupto toma el valor por
        defecto que declara el FORMATO REAL (`field_defaults`), salvo en los
        campos con un valor por defecto CONSERVADOR declarado
        (`conservative_defaults`).

        Es de SOLO LECTURA: no crea ficheros, no escribe y no altera el estado
        del motor. Devuelve una COPIA profunda, de modo que el llamante no
        pueda mutar el contrato.

        La declaracion NO sustituye a la verificacion: la sonda
        `tests/utils/contextual_adaptation_engine/identify_recoverable_real.py`
        contrasta esta declaracion contra lo OBSERVADO en runtime. La
        IMPLEMENTACION de la recuperacion es 2.8.8.9.7.2.
        """
        return copy.deepcopy(self._RECOVERABLE_DATA)

    def total_loss_fallback(self) -> Dict[str, Any]:
        """Contrato DECLARATIVO del FALLBACK por CORRUPCIÓN TOTAL (2.8.8.9.8.1).

        Declara el comportamiento REAL que el motor ofrece HOY ante la pérdida
        TOTAL de los datos de persistencia: qué MODOS de pérdida total
        reconoce, qué CAPAS de fallback existen, qué INVARIANTES deben cumplirse
        para que JARVIS pueda seguir operando, y cuáles de esos invariantes
        quedan PENDIENTES.

        El fallback NO inventa datos: el estado por defecto es el que el motor
        declara en CÓDIGO, no un dato inventado a partir del fichero roto.

        Es de SOLO LECTURA: no crea ficheros, no escribe y no altera el estado
        del motor. Devuelve una COPIA profunda, de modo que el llamante no pueda
        mutar el contrato.

        La declaración NO sustituye a la verificación: la sonda
        `tests/utils/contextual_adaptation_engine/identify_fallback_real.py`
        contrasta esta declaración contra lo OBSERVADO en runtime. El fallback
        está IMPLEMENTADO desde 2.8.8.9.8.2: no queda ningún invariante
        pendiente.
        """
        return copy.deepcopy(self._TOTAL_LOSS_FALLBACK)

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
        storage = self.detect_absent_storage()
        sections = self.detect_absent_sections()
        corruption = self.detect_corruption()
        # FALLBACK por CORRUPCIÓN TOTAL (2.8.8.9.8.2): el estado AGREGADO
        # declara las anomalías de la persistencia. Un fichero ILEGIBLE es una
        # anomalía TANTO como una desviación de formato: si no se cuenta, una
        # pérdida TOTAL de los cuatro ficheros se presentaría como un estado
        # limpio. El desglose queda a la vista (`corrupted` e `unreadable`):
        # lo que se cuenta es el TOTAL de anomalías, no su causa.
        ilegibles = len(corruption["unreadable"])
        anomalias = corruption["corruption_count"] + ilegibles
        return {"adaptation_enabled": self.config.get("adaptation_enabled", True), "is_adapting": self.is_adapting,
            "current_context": self.current_context.context_type.value if self.current_context else None, "adaptation_level": self.adaptation_level.value,
            "total_snapshots": len(self.context_snapshots), "total_rules": len(self.adaptation_rules),
            "total_adaptations": len(self.adaptation_history), "total_knowledge_transfers": len(self.knowledge_transfers),
            "active_modes": {"lightweight": self._lightweight_mode, "offline": self._offline_mode, "performance": self._performance_mode, "recovery": self._recovery_mode, "safe": self._safe_mode},
            "knowledge_base_stats": {"context_patterns": len(self.knowledge_base.get("context_patterns", {})), "adaptation_strategies": len(self.knowledge_base.get("adaptation_strategies", {})), "transfer_efficiency": len(self.knowledge_base.get("transfer_efficiency", {}))},
            "storage": {"absent": storage["absent"], "absent_count": storage["absent_count"]},
            "storage_sections": {"absent": sections["absent"], "absent_count": sections["absent_count"]},
            "corruption": {"corrupted": corruption["corrupted"], "corruption_count": anomalias,
                           "unreadable": corruption["unreadable"], "unreadable_count": ilegibles}}

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
