"""Sistema de aprendizaje de JARVIS (FASE 18).

Registra resultados observados de acciones, nodos, planes y replanificaciones.
Este módulo persiste métricas y genera señales históricas; no ejecuta acciones
ni considera que una planificación equivalga a una ejecución satisfactoria.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.utils.logger import get_logger

logger = get_logger(__name__)


class LearningEventType(Enum):
    ACTION_EXECUTION = "action_execution"
    PLAN_EXECUTION = "plan_execution"
    NODE_EXECUTION = "node_execution"
    REPLANIFICATION = "replanification"
    ALTERNATIVE_FOUND = "alternative_found"
    GOAL_ACHIEVED = "goal_achieved"
    GOAL_FAILED = "goal_failed"
    COST_ADJUSTMENT = "cost_adjustment"


@dataclass
class LearningEvent:
    event_type: LearningEventType
    timestamp: float
    success: bool
    execution_time: float
    estimated_cost: float
    actual_cost: float
    context: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    plan_id: Optional[str] = None
    goal_id: Optional[str] = None
    node_id: Optional[str] = None
    application: Optional[str] = None
    screen_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningEvent":
        if not isinstance(data, dict):
            raise TypeError("Cada evento importado debe ser un diccionario")

        allowed = {
            "event_type", "timestamp", "success", "execution_time",
            "estimated_cost", "actual_cost", "context", "details",
            "plan_id", "goal_id", "node_id", "application", "screen_state",
        }
        payload = {key: value for key, value in data.items() if key in allowed}

        raw_type = payload.get("event_type", LearningEventType.ACTION_EXECUTION)
        if isinstance(raw_type, LearningEventType):
            event_type = raw_type
        else:
            try:
                event_type = LearningEventType(str(raw_type))
            except (TypeError, ValueError):
                event_type = LearningEventType.ACTION_EXECUTION

        def finite_nonnegative(key: str, default: float = 0.0) -> float:
            try:
                value = float(payload.get(key, default))
                return max(0.0, value) if math.isfinite(value) else default
            except (TypeError, ValueError):
                return default

        timestamp = finite_nonnegative("timestamp", time.time())
        context = payload.get("context", {})
        details = payload.get("details", {})
        screen_state = payload.get("screen_state")
        return cls(
            event_type=event_type,
            timestamp=timestamp or time.time(),
            success=cls._coerce_bool(payload.get("success", False)),
            execution_time=finite_nonnegative("execution_time"),
            estimated_cost=finite_nonnegative("estimated_cost"),
            actual_cost=finite_nonnegative("actual_cost"),
            context=dict(context) if isinstance(context, dict) else {},
            details=dict(details) if isinstance(details, dict) else {},
            plan_id=cls._optional_string(payload.get("plan_id")),
            goal_id=cls._optional_string(payload.get("goal_id")),
            node_id=cls._optional_string(payload.get("node_id")),
            application=cls._optional_string(payload.get("application")),
            screen_state=dict(screen_state) if isinstance(screen_state, dict) else None,
        )

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "si", "sí", "success", "completed", "ok"}:
                return True
            if normalized in {"false", "0", "no", "failed", "failure", "error", ""}:
                return False
        return False

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


@dataclass
class LearningStatistics:
    total_events: int = 0
    successful_events: int = 0
    failed_events: int = 0
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    cost_accuracy_ratio: float = 1.0
    learning_rate: float = 0.1
    patterns_discovered: int = 0
    adaptations_made: int = 0


class LearningSystem:
    """Sistema centralizado, acotado y thread-safe de aprendizaje histórico."""

    def __init__(self, max_memory_size: int = 10000, learning_rate: float = 0.1):
        try:
            self.max_memory_size = max(1, int(max_memory_size))
        except (TypeError, ValueError, OverflowError):
            self.max_memory_size = 10000
        rate = self._safe_float(learning_rate, 0.1)
        self.learning_rate = min(max(rate, 0.0), 1.0)

        self.events: List[LearningEvent] = []
        self.events_lock = threading.RLock()
        self.app_stats: Dict[str, LearningStatistics] = defaultdict(LearningStatistics)
        self.action_stats: Dict[str, LearningStatistics] = defaultdict(LearningStatistics)
        self.node_stats: Dict[str, LearningStatistics] = defaultdict(LearningStatistics)
        self.learned_costs: Dict[str, float] = {}
        self.cost_adjustments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.success_patterns: Dict[str, List[str]] = defaultdict(list)
        self.failure_patterns: Dict[str, List[str]] = defaultdict(list)
        self.temporal_patterns: Dict[int, Dict[str, float]] = defaultdict(dict)
        self.optimal_routes: Dict[str, List[str]] = {}
        self.route_performance: Dict[str, Dict[str, float]] = defaultdict(self._empty_route_performance)

        self.learning_enabled = True
        self.cost_learning_enabled = True
        self.pattern_learning_enabled = True
        self.route_learning_enabled = True
        self.statistics = LearningStatistics(learning_rate=self.learning_rate)

        logger.info("[LEARNING] Sistema de aprendizaje inicializado (memoria=%s, tasa=%.3f)", self.max_memory_size, self.learning_rate)

    # ------------------------------------------------------------------
    # Registro público
    # ------------------------------------------------------------------
    def record_action_execution(
        self,
        action_name: str,
        success: bool,
        execution_time: float,
        estimated_cost: float,
        context: Optional[Dict[str, Any]] = None,
        application: Optional[str] = None,
        screen_state: Optional[Dict[str, Any]] = None,
        actual_cost: Optional[float] = None,
    ) -> None:
        if not self.learning_enabled:
            return
        name = str(action_name or "unknown_action")
        event = self._build_event(
            LearningEventType.ACTION_EXECUTION,
            success=success,
            execution_time=execution_time,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            context=context,
            details={"action_name": name},
            application=application,
            screen_state=screen_state,
        )
        with self.events_lock:
            self._store_event(event)
            self._update_statistics(self.action_stats[name], event)
            if event.application:
                self._update_statistics(self.app_stats[event.application], event)
            self._learn_action_cost(name, event)
            self._discover_patterns(event)

    def record_plan_execution(
        self,
        plan_id: str,
        goal_id: str,
        plan: Sequence[str],
        success: bool,
        execution_time: float,
        total_estimated_cost: float,
        context: Optional[Dict[str, Any]] = None,
        actual_cost: Optional[float] = None,
    ) -> None:
        """Registra el resultado real del plan; el caller debe aportar ``success`` observado."""
        if not self.learning_enabled:
            return
        plan_list = [str(item) for item in (plan or [])]
        event = self._build_event(
            LearningEventType.PLAN_EXECUTION,
            success=success,
            execution_time=execution_time,
            estimated_cost=total_estimated_cost,
            actual_cost=actual_cost,
            context=context,
            details={"plan": plan_list, "plan_length": len(plan_list)},
            plan_id=plan_id,
            goal_id=goal_id,
        )
        with self.events_lock:
            self._store_event(event)
            if self.route_learning_enabled:
                self._update_route_performance(str(goal_id or ""), plan_list, event)
                if event.success:
                    self._register_optimal_route(str(goal_id or ""), plan_list, event)

    def record_node_execution(
        self,
        node_id: str,
        success: bool,
        execution_time: float,
        estimated_cost: float,
        context: Optional[Dict[str, Any]] = None,
        application: Optional[str] = None,
        actual_cost: Optional[float] = None,
    ) -> None:
        if not self.learning_enabled:
            return
        identifier = str(node_id or "unknown_node")
        event = self._build_event(
            LearningEventType.NODE_EXECUTION,
            success=success,
            execution_time=execution_time,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            context=context,
            details={"node_id": identifier},
            node_id=identifier,
            application=application,
        )
        with self.events_lock:
            self._store_event(event)
            self._update_statistics(self.node_stats[identifier], event)
            if event.application:
                self._update_statistics(self.app_stats[event.application], event)
            self._discover_patterns(event)

    def record_replanification(
        self,
        original_plan: Sequence[str],
        new_plan: Sequence[str],
        reason: str,
        success: bool,
        execution_time: float,
    ) -> None:
        if not self.learning_enabled:
            return
        original = [str(item) for item in (original_plan or [])]
        new = [str(item) for item in (new_plan or [])]
        event = self._build_event(
            LearningEventType.REPLANIFICATION,
            success=success,
            execution_time=execution_time,
            estimated_cost=float(len(new)),
            actual_cost=float(len(new)),
            context={"reason": str(reason or "unknown")},
            details={"original_plan": original, "new_plan": new, "plan_change": len(new) - len(original)},
        )
        with self.events_lock:
            self._store_event(event)
            self._learn_from_replanification(event)

    def record_goal_result(
        self, goal_id: str, success: bool, context: Optional[Dict[str, Any]] = None,
        execution_time: float = 0.0,
    ) -> None:
        """Registra explícitamente el resultado observado de un objetivo."""
        if not self.learning_enabled:
            return
        event_type = LearningEventType.GOAL_ACHIEVED if success else LearningEventType.GOAL_FAILED
        event = self._build_event(
            event_type, success=success, execution_time=execution_time,
            estimated_cost=0.0, actual_cost=0.0, context=context, goal_id=goal_id,
        )
        with self.events_lock:
            self._store_event(event)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def get_action_insights(self, action_name: str) -> Dict[str, Any]:
        with self.events_lock:
            action_events = [e for e in self.events if e.event_type == LearningEventType.ACTION_EXECUTION and e.details.get("action_name") == action_name]
            learned_cost = self.learned_costs.get(action_name)
        if not action_events:
            return {"error": "No hay datos para esta acción"}

        successes = sum(1 for event in action_events if event.success)
        total_time = sum(event.execution_time for event in action_events)
        cost_errors = [self._cost_error(event) for event in action_events if event.estimated_cost > 0]
        average_estimated = sum(e.estimated_cost for e in action_events) / len(action_events)
        return {
            "action_name": action_name,
            "total_executions": len(action_events),
            "successful_executions": successes,
            "failed_executions": len(action_events) - successes,
            "success_rate": successes / len(action_events),
            "average_execution_time": total_time / len(action_events),
            "total_execution_time": total_time,
            "average_estimated_cost": average_estimated,
            "learned_cost": learned_cost if learned_cost is not None else average_estimated,
            "cost_accuracy": max(0.0, 1.0 - (sum(cost_errors) / len(cost_errors) if cost_errors else 0.0)),
            "recent_performance": [event.success for event in action_events[-10:]],
            "applications_used": sorted({event.application for event in action_events if event.application}),
            "improvement_trend": self._calculate_improvement_trend(action_events),
        }

    def get_system_insights(self) -> Dict[str, Any]:
        with self.events_lock:
            events = list(self.events)
            routes = {key: list(value) for key, value in self.optimal_routes.items()}
        if not events:
            return {"error": "No hay eventos registrados"}

        successes = sum(1 for event in events if event.success)
        total_time = sum(event.execution_time for event in events)
        cost_errors = [self._cost_error(e) for e in events if e.estimated_cost > 0]
        cost_accuracy = max(0.0, 1.0 - (sum(cost_errors) / len(cost_errors) if cost_errors else 0.0))
        cutoff = time.time() - 3600.0
        recent = [event for event in events if event.timestamp >= cutoff]
        recent_success_rate = sum(event.success for event in recent) / len(recent) if recent else 0.0
        app_stats = self._build_application_insights(events)
        action_stats = self._build_action_insights_summary(events)
        return {
            "total_events": len(events),
            "successful_events": successes,
            "failed_events": len(events) - successes,
            "overall_success_rate": successes / len(events),
            "average_execution_time": total_time / len(events),
            "total_execution_time": total_time,
            "applications_analyzed": len(app_stats),
            "top_applications": sorted(app_stats.items(), key=lambda item: item[1]["success_rate"], reverse=True)[:5],
            "best_actions": sorted(((name, data["success_rate"]) for name, data in action_stats.items()), key=lambda item: item[1], reverse=True)[:10],
            "optimal_routes_discovered": sum(1 for route in routes.values() if route),
            "learning_events_by_type": self._count_events_by_type(),
            "system_health": self._assess_system_health(events),
        }

    def get_cost_adjustments(self) -> Dict[str, float]:
        """Devuelve deltas respecto al último coste estimado (no costes absolutos).

        Planner suma estos valores al coste base; devolver aquí el coste absoluto
        aprendido lo sumaría dos veces y distorsionaría la comparación de rutas.
        """
        with self.events_lock:
            adjustments: Dict[str, float] = {}
            for action, learned_cost in self.learned_costs.items():
                history = self.cost_adjustments.get(action, [])
                if history:
                    last = history[-1]
                    baseline = self._safe_float(last.get("estimated_cost"), self._safe_float(last.get("old_cost", 0.0)))
                else:
                    historical_events = [
                        event for event in self.events
                        if event.event_type == LearningEventType.ACTION_EXECUTION
                        and event.details.get("action_name") == action
                    ]
                    baseline = historical_events[-1].estimated_cost if historical_events else learned_cost
                adjustments[action] = self._safe_float(learned_cost) - baseline
            return adjustments

    def get_learned_costs(self) -> Dict[str, float]:
        """Devuelve los costes absolutos aprendidos por acción."""
        with self.events_lock:
            return dict(self.learned_costs)

    def get_route_performance(self, goal_id: Optional[str] = None) -> Dict[str, Any]:
        with self.events_lock:
            if goal_id is not None:
                return dict(self.route_performance.get(str(goal_id), self._empty_route_performance()))
            return {key: dict(value) for key, value in self.route_performance.items()}

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def export_learning_data(self, filepath: str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_lock:
            export_data = {
                "schema_version": 2,
                "events": [event.to_dict() for event in self.events],
                "learned_costs": dict(self.learned_costs),
                "cost_adjustments": {key: list(value) for key, value in self.cost_adjustments.items()},
                "optimal_routes": {key: list(value) for key, value in self.optimal_routes.items()},
                "route_performance": {key: dict(value) for key, value in self.route_performance.items()},
                "app_statistics": {key: asdict(value) for key, value in self.app_stats.items()},
                "action_statistics": {key: asdict(value) for key, value in self.action_stats.items()},
                "node_statistics": {key: asdict(value) for key, value in self.node_stats.items()},
                "success_patterns": {key: list(value) for key, value in self.success_patterns.items()},
                "failure_patterns": {key: list(value) for key, value in self.failure_patterns.items()},
                "temporal_patterns": {str(key): dict(value) for key, value in self.temporal_patterns.items()},
                "system_config": {
                    "learning_enabled": self.learning_enabled,
                    "cost_learning_enabled": self.cost_learning_enabled,
                    "pattern_learning_enabled": self.pattern_learning_enabled,
                    "route_learning_enabled": self.route_learning_enabled,
                    "learning_rate": self.learning_rate,
                    "max_memory_size": self.max_memory_size,
                },
            }

        # Escritura atómica: un cierre inesperado no deja el JSON parcialmente escrito.
        temp_name: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
                temp_name = handle.name
                json.dump(export_data, handle, indent=2, ensure_ascii=False, default=str, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
        logger.info("[LEARNING] Datos exportados a: %s", filepath)

    def import_learning_data(self, filepath: str) -> None:
        path = Path(filepath)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("El fichero de aprendizaje debe contener un objeto JSON")

            raw_events = data.get("events", [])
            if not isinstance(raw_events, list):
                raise ValueError("El campo 'events' debe ser una lista")
            imported_events = [LearningEvent.from_dict(item) for item in raw_events if isinstance(item, dict)]
            imported_events = imported_events[-self.max_memory_size:]

            learned_raw = data.get("learned_costs", {})
            if not isinstance(learned_raw, dict):
                learned_raw = {}
            learned_costs = {
                str(k): max(0.0, self._safe_float(v))
                for k, v in learned_raw.items()
                if isinstance(v, (int, float, str))
                and not isinstance(v, bool)
                and str(v).strip() != ""
                and math.isfinite(self._safe_float(v, float("nan")))
                and self._safe_float(v) >= 0
            }

            cost_raw = data.get("cost_adjustments", {})
            if not isinstance(cost_raw, dict):
                cost_raw = {}
            cost_adjustments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for key, items in cost_raw.items():
                if isinstance(items, list):
                    cost_adjustments[str(key)] = [dict(item) for item in items if isinstance(item, dict)][-100:]

            routes_raw = data.get("optimal_routes", {})
            routes = {str(k): [str(x) for x in v] for k, v in routes_raw.items() if isinstance(v, list)} if isinstance(routes_raw, dict) else {}
            performance_raw = data.get("route_performance", {})
            route_performance: Dict[str, Dict[str, float]] = defaultdict(self._empty_route_performance)
            if isinstance(performance_raw, dict):
                for key, value in performance_raw.items():
                    if isinstance(value, dict):
                        route_performance[str(key)] = {
                            metric: max(0.0, self._safe_float(value.get(metric), 0.0))
                            for metric in ("success_rate", "average_time", "average_cost", "executions")
                        }
                        route_performance[str(key)]["success_rate"] = min(1.0, route_performance[str(key)]["success_rate"])

            success_patterns = self._load_pattern_dict(data.get("success_patterns", {}))
            failure_patterns = self._load_pattern_dict(data.get("failure_patterns", {}))
            temporal_patterns = self._load_temporal_patterns(data.get("temporal_patterns", {}))
            config = data.get("system_config", {})
            if not isinstance(config, dict):
                config = {}

            with self.events_lock:
                self.events = imported_events
                self.learned_costs = learned_costs
                self.cost_adjustments = cost_adjustments
                self.optimal_routes = routes
                self.route_performance = route_performance
                self.success_patterns = success_patterns
                self.failure_patterns = failure_patterns
                self.temporal_patterns = temporal_patterns
                if "learning_rate" in config:
                    self.learning_rate = min(max(self._safe_float(config["learning_rate"], self.learning_rate), 0.0), 1.0)
                for key in ("learning_enabled", "cost_learning_enabled", "pattern_learning_enabled", "route_learning_enabled"):
                    if key in config:
                        setattr(self, key, LearningEvent._coerce_bool(config[key]))
                self.statistics.learning_rate = self.learning_rate
                self._rebuild_statistics_from_events()

            logger.info("[LEARNING] Datos importados desde: %s (%s eventos)", filepath, len(imported_events))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("[LEARNING] No se pudieron importar los datos de %s: %s", filepath, exc)
            raise

    def clear_learning_data(self) -> None:
        with self.events_lock:
            self.events.clear()
            self.app_stats.clear()
            self.action_stats.clear()
            self.node_stats.clear()
            self.learned_costs.clear()
            self.cost_adjustments.clear()
            self.success_patterns.clear()
            self.failure_patterns.clear()
            self.temporal_patterns.clear()
            self.optimal_routes.clear()
            self.route_performance.clear()
            self.statistics = LearningStatistics(learning_rate=self.learning_rate)
        logger.info("[LEARNING] Datos de aprendizaje limpiados")

    def enable_learning(self, enabled: bool = True) -> None:
        self.learning_enabled = bool(enabled)
        logger.info("[LEARNING] Aprendizaje %s", "habilitado" if enabled else "deshabilitado")

    def enable_cost_learning(self, enabled: bool = True) -> None:
        self.cost_learning_enabled = bool(enabled)

    def enable_pattern_learning(self, enabled: bool = True) -> None:
        self.pattern_learning_enabled = bool(enabled)

    def enable_route_learning(self, enabled: bool = True) -> None:
        self.route_learning_enabled = bool(enabled)

    # ------------------------------------------------------------------
    # Núcleo de aprendizaje
    # ------------------------------------------------------------------
    def _build_event(self, event_type: LearningEventType, **kwargs: Any) -> LearningEvent:
        execution_time = max(0.0, self._safe_float(kwargs.pop("execution_time", 0.0)))
        estimated_cost = max(0.0, self._safe_float(kwargs.pop("estimated_cost", 0.0)))
        actual_raw = kwargs.pop("actual_cost", None)
        # Compatibilidad heredada: si no hay medida de coste real, usamos el tiempo
        # de ejecución como proxy. No se interpreta como una unidad monetaria.
        actual_cost = max(0.0, self._safe_float(execution_time if actual_raw is None else actual_raw))
        timestamp = self._safe_float(kwargs.pop("timestamp", time.time()), time.time())
        success_value = LearningEvent._coerce_bool(kwargs.pop("success", False))
        context = kwargs.pop("context", {})
        details = kwargs.pop("details", {})
        screen_state = kwargs.pop("screen_state", None)
        return LearningEvent(
            event_type=event_type,
            timestamp=timestamp if timestamp > 0 else time.time(),
            success=success_value,
            execution_time=execution_time,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            context=dict(context) if isinstance(context, dict) else {},
            details=dict(details) if isinstance(details, dict) else {},
            plan_id=LearningEvent._optional_string(kwargs.pop("plan_id", None)),
            goal_id=LearningEvent._optional_string(kwargs.pop("goal_id", None)),
            node_id=LearningEvent._optional_string(kwargs.pop("node_id", None)),
            application=LearningEvent._optional_string(kwargs.pop("application", None)),
            screen_state=dict(screen_state) if isinstance(screen_state, dict) else None,
        )

    def _store_event(self, event: LearningEvent) -> None:
        """Almacena evento e incrementa contadores agregados en la misma sección crítica."""
        with self.events_lock:
            self.events.append(event)
            if len(self.events) > self.max_memory_size:
                del self.events[: len(self.events) - self.max_memory_size]
            self.statistics.total_events += 1
            self.statistics.successful_events += int(event.success)
            self.statistics.failed_events += int(not event.success)
            self.statistics.total_execution_time += event.execution_time
            self.statistics.average_execution_time = self.statistics.total_execution_time / max(1, self.statistics.total_events)
            valid_cost_events = [item for item in self.events if item.estimated_cost > 0]
            self.statistics.cost_accuracy_ratio = (
                sum(max(0.0, 1.0 - self._cost_error(item)) for item in valid_cost_events)
                / len(valid_cost_events)
                if valid_cost_events else 1.0
            )

    @staticmethod
    def _update_statistics(stats: LearningStatistics, event: LearningEvent) -> None:
        stats.total_events += 1
        stats.total_execution_time += event.execution_time
        stats.average_execution_time = stats.total_execution_time / stats.total_events
        if event.success:
            stats.successful_events += 1
        else:
            stats.failed_events += 1

    def _learn_action_cost(self, action_name: str, event: LearningEvent) -> None:
        if not self.cost_learning_enabled:
            return
        current_cost = self.learned_costs.get(action_name, event.estimated_cost)
        alpha = self.learning_rate
        learned_cost = max(0.0, (1.0 - alpha) * current_cost + alpha * event.actual_cost)
        self.learned_costs[action_name] = learned_cost
        history = self.cost_adjustments[action_name]
        history.append({
            "timestamp": event.timestamp,
            "old_cost": current_cost,
            "new_cost": learned_cost,
            "actual_cost": event.actual_cost,
            "estimated_cost": event.estimated_cost,
            "success": event.success,
        })
        if len(history) > 100:
            del history[:-100]
        self.statistics.adaptations_made += 1

    def _discover_patterns(self, event: LearningEvent) -> None:
        if not self.pattern_learning_enabled:
            return
        action_name = event.details.get("action_name") or event.details.get("node_id") or event.node_id
        if not action_name:
            return
        action_name = str(action_name)
        hour = time.localtime(event.timestamp).tm_hour
        self.temporal_patterns[hour][action_name] = self.temporal_patterns[hour].get(action_name, 0.0) + 1.0
        suffix = "success" if event.success else "failure"
        key = f"{event.application}_{suffix}" if event.application else f"global_{suffix}"
        target = self.success_patterns if event.success else self.failure_patterns
        target[key].append(action_name)
        if len(target[key]) > 1000:
            del target[key][:-1000]
        self.statistics.patterns_discovered = self._count_unique_patterns()

    def _update_route_performance(self, route_key: str, plan: List[str], event: LearningEvent) -> None:
        if not route_key or not plan:
            return
        performance = self.route_performance[route_key]
        previous_executions = max(0.0, performance.get("executions", 0.0))
        new_executions = previous_executions + 1.0
        performance["success_rate"] = ((performance.get("success_rate", 0.0) * previous_executions) + float(event.success)) / new_executions
        performance["average_time"] = ((performance.get("average_time", 0.0) * previous_executions) + event.execution_time) / new_executions
        performance["average_cost"] = ((performance.get("average_cost", 0.0) * previous_executions) + event.actual_cost) / new_executions
        performance["executions"] = new_executions

    def _register_optimal_route(self, goal_id: str, plan: List[str], event: LearningEvent) -> None:
        if not goal_id or not plan or not event.success:
            return
        existing = self.optimal_routes.get(goal_id)
        if existing is None:
            self.optimal_routes[goal_id] = list(plan)
            return
        # Se comparan rutas exitosas; el coste/timing observado tiene prioridad,
        # y la longitud sirve como desempate conservador.
        existing_events = [e for e in self.events if e.event_type == LearningEventType.PLAN_EXECUTION and e.goal_id == goal_id and e.success and e.details.get("plan") == existing]
        if not existing_events:
            self.optimal_routes[goal_id] = list(plan)
            return
        best_existing = min(existing_events, key=lambda e: (e.actual_cost, e.execution_time, len(e.details.get("plan", []))))
        new_score = (event.actual_cost, event.execution_time, len(plan))
        old_score = (best_existing.actual_cost, best_existing.execution_time, len(existing))
        if new_score < old_score:
            self.optimal_routes[goal_id] = list(plan)

    def _learn_from_replanification(self, event: LearningEvent) -> None:
        if not event.success or not self.pattern_learning_enabled:
            return
        original = event.details.get("original_plan", [])
        new = event.details.get("new_plan", [])
        reason = str(event.context.get("reason", "unknown"))
        if len(new) < len(original):
            logger.info("[LEARNING] Ruta más corta descubierta: %s -> %s acciones", len(original), len(new))
        bucket = self.success_patterns[f"replanification_{reason}"]
        bucket.extend(str(item) for item in new)
        if len(bucket) > 1000:
            del bucket[:-1000]
        self.statistics.patterns_discovered = self._count_unique_patterns()

    # ------------------------------------------------------------------
    # Agregación y salud del sistema
    # ------------------------------------------------------------------
    def _calculate_improvement_trend(self, events: List[LearningEvent]) -> str:
        if len(events) < 5:
            return "insufficient_data"
        recent = events[-min(10, len(events)):]
        older = events[: max(1, len(events) // 2)]
        recent_rate = sum(event.success for event in recent) / len(recent)
        older_rate = sum(event.success for event in older) / len(older)
        if recent_rate > older_rate + 0.1:
            return "improving"
        if recent_rate < older_rate - 0.1:
            return "declining"
        return "stable"

    def _count_events_by_type(self) -> Dict[str, int]:
        with self.events_lock:
            counts: Dict[str, int] = defaultdict(int)
            for event in self.events:
                counts[event.event_type.value] += 1
            return dict(counts)

    def _assess_system_health(self, events: List[LearningEvent]) -> Dict[str, Any]:
        cutoff = time.time() - 3600.0
        recent = [event for event in events if event.timestamp >= cutoff]
        recent_success_rate = sum(event.success for event in recent) / len(recent) if recent else 0.0
        cost_events = [event for event in events if event.estimated_cost > 0]
        cost_accuracy = max(0.0, 1.0 - (sum(self._cost_error(e) for e in cost_events) / len(cost_events))) if cost_events else 1.0
        if recent_success_rate > 0.8 and cost_accuracy > 0.7:
            status = "excellent"
        elif recent_success_rate > 0.6 and cost_accuracy > 0.5:
            status = "good"
        elif recent_success_rate > 0.4:
            status = "fair"
        else:
            status = "needs_attention"
        return {
            "status": status,
            "recent_success_rate": recent_success_rate,
            "cost_accuracy": cost_accuracy,
            "data_diversity": {
                "unique_actions": len({e.details.get("action_name") for e in events if e.details.get("action_name")}),
                "unique_applications": len({e.application for e in events if e.application}),
                "total_events": len(events),
            },
            "recommendations": self._generate_health_recommendations(status, recent_success_rate, cost_accuracy),
        }

    def _generate_health_recommendations(self, status: str, success_rate: float, cost_accuracy: float) -> List[str]:
        recommendations: List[str] = []
        if status == "needs_attention":
            if success_rate < 0.3:
                recommendations.append("Considerar revisar precondiciones de acciones frecuentes")
            if cost_accuracy < 0.3:
                recommendations.append("Los costes estimados están muy alejados de la realidad, recalibrar")
            recommendations.append("El sistema necesita más datos para mejorar")
        elif status == "fair":
            if success_rate < 0.5:
                recommendations.append("Analizar patrones de fallo para acciones específicas")
            recommendations.append("Continuar recopilando datos")
        elif status == "good":
            recommendations.append("Mantener la actual configuración")
            if success_rate < 0.7:
                recommendations.append("Buscar oportunidades de optimización")
        elif status == "excellent":
            recommendations.extend(["Sistema funcionando óptimamente", "Considerar exportar datos para backup"])
        return recommendations

    def _build_application_insights(self, events: List[LearningEvent]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for application in sorted({event.application for event in events if event.application}):
            related = [event for event in events if event.application == application]
            result[application] = {
                "total_events": len(related),
                "success_rate": sum(event.success for event in related) / len(related),
                "average_time": sum(event.execution_time for event in related) / len(related),
            }
        return result

    def _build_action_insights_summary(self, events: List[LearningEvent]) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for event in events:
            name = event.details.get("action_name")
            if not name:
                continue
            data = result.setdefault(str(name), {"success": 0.0, "total": 0.0, "time": 0.0})
            data["total"] += 1.0
            data["success"] += float(event.success)
            data["time"] += event.execution_time
        for data in result.values():
            data["success_rate"] = data["success"] / data["total"] if data["total"] else 0.0
        return result

    def _rebuild_statistics_from_events(self) -> None:
        self.app_stats.clear()
        self.action_stats.clear()
        self.node_stats.clear()
        self.statistics = LearningStatistics(learning_rate=self.learning_rate)
        for event in self.events:
            name = event.details.get("action_name")
            if name:
                self._update_statistics(self.action_stats[str(name)], event)
            if event.node_id:
                self._update_statistics(self.node_stats[event.node_id], event)
            elif event.details.get("node_id"):
                self._update_statistics(self.node_stats[str(event.details["node_id"])], event)
            if event.application:
                self._update_statistics(self.app_stats[event.application], event)
            self.statistics.total_events += 1
            self.statistics.successful_events += int(event.success)
            self.statistics.failed_events += int(not event.success)
            self.statistics.total_execution_time += event.execution_time
        if self.statistics.total_events:
            self.statistics.average_execution_time = self.statistics.total_execution_time / self.statistics.total_events
            valid_cost_events = [event for event in self.events if event.estimated_cost > 0]
            self.statistics.cost_accuracy_ratio = (
                sum(max(0.0, 1.0 - self._cost_error(event)) for event in valid_cost_events)
                / len(valid_cost_events)
                if valid_cost_events else 1.0
            )
        self.statistics.patterns_discovered = self._count_unique_patterns()
        self.statistics.adaptations_made = sum(len(values) for values in self.cost_adjustments.values())

    def _count_unique_patterns(self) -> int:
        # Cuenta patrones distintos, no todas las apariciones de cada patrón.
        unique_success = {(key, item) for key, values in self.success_patterns.items() for item in values}
        unique_failure = {(key, item) for key, values in self.failure_patterns.items() for item in values}
        return len(unique_success | unique_failure)

    # ------------------------------------------------------------------
    # Normalización
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
            return result if math.isfinite(result) else default
        except (TypeError, ValueError, OverflowError):
            return default

    def _cost_error(self, event: LearningEvent) -> float:
        estimated = self._safe_float(event.estimated_cost)
        actual = self._safe_float(event.actual_cost)
        if estimated <= 0:
            return 0.0
        return abs(actual - estimated) / max(estimated, 1e-12)

    @staticmethod
    def _empty_route_performance() -> Dict[str, float]:
        return {"success_rate": 0.0, "average_time": 0.0, "average_cost": 0.0, "executions": 0.0}

    @staticmethod
    def _load_pattern_dict(value: Any) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = defaultdict(list)
        if isinstance(value, dict):
            for key, items in value.items():
                if isinstance(items, list):
                    result[str(key)] = [str(item) for item in items][-1000:]
        return result

    @staticmethod
    def _load_temporal_patterns(value: Any) -> Dict[int, Dict[str, float]]:
        result: Dict[int, Dict[str, float]] = defaultdict(dict)
        if not isinstance(value, dict):
            return result
        for raw_hour, data in value.items():
            try:
                hour = int(raw_hour)
            except (TypeError, ValueError):
                continue
            if hour < 0 or hour > 23 or not isinstance(data, dict):
                continue
            result[hour] = {str(key): max(0.0, LearningSystem._safe_float(count)) for key, count in data.items()}
        return result


_learning_system: Optional[LearningSystem] = None
_learning_system_lock = threading.Lock()


def get_learning_system() -> LearningSystem:
    """Obtiene la instancia global del sistema de aprendizaje con inicialización segura."""
    global _learning_system
    if _learning_system is None:
        with _learning_system_lock:
            if _learning_system is None:
                _learning_system = LearningSystem()
    return _learning_system


__all__ = [
    "LearningEventType",
    "LearningEvent",
    "LearningStatistics",
    "LearningSystem",
    "get_learning_system",
]
