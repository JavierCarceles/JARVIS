"""Sistema de optimización del planificador de JARVIS.

Responsabilidades:
- Caché LRU de planes válidos por objetivo y estado relevante.
- Comparación y selección de planes alternativos.
- Eliminación conservadora de redundancias.
- Optimización contextual sin mutar el plan de entrada.
- Integración con LearningSystem para ajustes de coste aprendidos.
- Persistencia validada y atómica de los datos de optimización.

Este módulo no ejecuta acciones físicas. Los resultados de ejecución deben
registrarse desde el componente que observe la ejecución real.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from src.hands.planner.node import Goal, Node
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.hands.planner.planner import Planner, PlanningResult

logger = get_logger(__name__)


class OptimizationType(Enum):
    """Tipos de optimización disponibles."""

    ROUTE_CACHE = "route_cache"
    COST_LEARNING = "cost_learning"
    REDUNDANCY_REMOVAL = "redundancy_removal"
    CONTEXT_AWARE = "context_aware"
    ALTERNATIVE_SELECTION = "alternative_selection"
    PERFORMANCE_MONITORING = "performance_monitoring"


def _finite_float(value: Any, default: float = 0.0, minimum: Optional[float] = None) -> float:
    """Convierte a float finito y aplica un límite inferior opcional."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    if minimum is not None:
        number = max(minimum, number)
    return number


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return []


@dataclass
class RouteCacheEntry:
    """Entrada del caché de rutas/planes."""

    goal_id: str
    start_state_hash: str
    plan: List[Dict[str, Any]]
    cost: float
    quality: Any
    timestamp: float
    access_count: int = 0
    success_rate: float = 0.0
    execution_count: int = 0
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "start_state_hash": self.start_state_hash,
            "plan": copy.deepcopy(self.plan),
            "cost": self.cost,
            "quality": getattr(self.quality, "value", self.quality),
            "timestamp": self.timestamp,
            "access_count": self.access_count,
            "success_rate": self.success_rate,
            "execution_count": self.execution_count,
            "execution_time": self.execution_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteCacheEntry":
        if not isinstance(data, dict):
            raise ValueError("La entrada de caché debe ser un diccionario")
        raw_plan = data.get("plan", [])
        if not isinstance(raw_plan, list) or any(not isinstance(item, dict) for item in raw_plan):
            raise ValueError("El plan del caché debe ser una lista de diccionarios")
        return cls(
            goal_id=str(data.get("goal_id", "")),
            start_state_hash=str(data.get("start_state_hash", "")),
            plan=copy.deepcopy(raw_plan),
            cost=_finite_float(data.get("cost", 0.0), 0.0, 0.0),
            quality=data.get("quality"),
            timestamp=_finite_float(data.get("timestamp", 0.0), 0.0, 0.0),
            access_count=max(0, int(_finite_float(data.get("access_count", 0), 0))),
            success_rate=min(1.0, _finite_float(data.get("success_rate", 0.0), 0.0, 0.0)),
            execution_count=max(0, int(_finite_float(data.get("execution_count", 0), 0))),
            execution_time=_finite_float(data.get("execution_time", 0.0), 0.0, 0.0),
        )


@dataclass
class CostLearningData:
    """Muestra individual de aprendizaje de coste."""

    node_id: str
    estimated_cost: float
    actual_cost: float
    execution_time: float
    success: bool
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CostLearningData":
        if not isinstance(data, dict):
            raise ValueError("La muestra de coste debe ser un diccionario")
        context = data.get("context", {})
        return cls(
            node_id=str(data.get("node_id", "")),
            estimated_cost=_finite_float(data.get("estimated_cost", 0.0), 0.0, 0.0),
            actual_cost=_finite_float(data.get("actual_cost", 0.0), 0.0, 0.0),
            execution_time=_finite_float(data.get("execution_time", 0.0), 0.0, 0.0),
            success=bool(data.get("success", False)),
            timestamp=_finite_float(data.get("timestamp", 0.0), 0.0, 0.0),
            context=copy.deepcopy(context) if isinstance(context, dict) else {},
        )


@dataclass
class ContextData:
    """Datos contextuales usados por la optimización."""

    user_preferences: Dict[str, Any] = field(default_factory=dict)
    application_patterns: Dict[str, List[str]] = field(default_factory=dict)
    time_patterns: Dict[str, List[str]] = field(default_factory=dict)
    success_patterns: Dict[str, List[str]] = field(default_factory=dict)


class OptimizationManager:
    """Gestor de optimización que opera sobre un Planner ya existente."""

    def __init__(self, planner: "Planner", max_cache_size: int = 1000) -> None:
        if planner is None:
            raise ValueError("planner es obligatorio")
        try:
            normalized_cache_size = int(max_cache_size)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("max_cache_size debe ser un entero positivo") from exc
        if normalized_cache_size < 1:
            raise ValueError("max_cache_size debe ser >= 1")

        self.planner = planner
        self.max_cache_size = normalized_cache_size
        self.route_cache: OrderedDict[str, RouteCacheEntry] = OrderedDict()
        self.cache_lock = threading.RLock()
        self.data_lock = threading.RLock()

        self.cost_learning: Dict[str, List[CostLearningData]] = defaultdict(list)
        self.cost_models: Dict[str, Dict[str, float]] = {}
        self.external_learning_system: Any = None
        self.context_data = ContextData()

        self.performance_stats: Dict[str, float] = {
            "total_plans": 0.0,
            "cached_plans": 0.0,
            "optimized_plans": 0.0,
            "redundancies_removed": 0.0,
            "alternatives_selected": 0.0,
            "cost_improvements": 0.0,
            "average_improvement": 0.0,
            "optimization_time": 0.0,
        }
        self.optimization_enabled = {kind: True for kind in OptimizationType}

        # Conectar un LearningSystem ya existente sin forzar su importación.
        existing_learning = getattr(planner, "learning_system", None)
        if existing_learning is not None:
            self.external_learning_system = existing_learning

        logger.info("[OPTIMIZATION] Gestor de optimización inicializado (LRU=%s)", self.max_cache_size)

    # ==================================================================
    # INTEGRACIÓN PRINCIPAL
    # ==================================================================

    def set_learning_system(self, learning_system: Any) -> None:
        with self.data_lock:
            self.external_learning_system = learning_system
        logger.info("[OPTIMIZATION] Sistema de aprendizaje externo integrado: %s", learning_system is not None)

    def optimize_planning(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Optional[Dict[str, Node]] = None,
        max_planning_time: float = 30.0,
    ) -> "PlanningResult":
        from src.hands.planner.planner import PlannerStatus, PlanQuality

        start_time = time.perf_counter()
        state = copy.deepcopy(current_state) if isinstance(current_state, dict) else {}
        if self.external_learning_system is None:
            existing_learning = getattr(self.planner, "learning_system", None)
            if existing_learning is not None:
                self.set_learning_system(existing_learning)
        if goal is None:
            raise ValueError("goal es obligatorio")
        budget = _finite_float(max_planning_time, 30.0, 0.0)
        logger.info("[OPTIMIZATION] Iniciando planificación optimizada para: %s", getattr(goal, "id", "unknown"))

        if self.optimization_enabled.get(OptimizationType.ROUTE_CACHE, False):
            cached_result = self._check_route_cache(goal, state)
            if cached_result is not None:
                with self.data_lock:
                    self.performance_stats["cached_plans"] += 1
                    self.performance_stats["total_plans"] += 1
                cached_result.execution_time = time.perf_counter() - start_time
                return cached_result

        planning_result = self.planner.plan(
            goal,
            state,
            available_nodes,
            budget,
            find_alternatives=True,
            use_optimization=False,
        )
        if planning_result is None or not hasattr(planning_result, "status"):
            raise TypeError("Planner.plan() no devolvió un PlanningResult válido")

        # Trabajar siempre con copias; nunca alterar la lista de plan original.
        original_plan = copy.deepcopy(getattr(planning_result, "plan", []) or [])
        optimized_plan = copy.deepcopy(original_plan)

        if planning_result.status == PlannerStatus.COMPLETED:
            if self.optimization_enabled.get(OptimizationType.REDUNDANCY_REMOVAL, False):
                optimized_plan = self._remove_redundancies(optimized_plan, state)
                removed = max(0, len(original_plan) - len(optimized_plan))
                if removed:
                    planning_result.metadata = dict(getattr(planning_result, "metadata", {}) or {})
                    planning_result.metadata["redundancies_removed"] = removed
                    with self.data_lock:
                        self.performance_stats["redundancies_removed"] += removed

            if self.optimization_enabled.get(OptimizationType.ALTERNATIVE_SELECTION, False):
                alternatives = self._select_optimal_alternatives(
                    copy.deepcopy(getattr(planning_result, "alternatives", []) or []), state
                )
                planning_result.alternatives = alternatives
                if alternatives:
                    with self.data_lock:
                        self.performance_stats["alternatives_selected"] += 1

            if self.optimization_enabled.get(OptimizationType.CONTEXT_AWARE, False):
                optimized_plan = self._apply_context_optimization(optimized_plan, state)

            # Una optimización nunca debe transformar un plan no vacío en vacío.
            if original_plan and not optimized_plan:
                logger.warning("[OPTIMIZATION] La optimización produjo un plan vacío; se restaura el plan original")
                optimized_plan = copy.deepcopy(original_plan)

            planning_result.plan = optimized_plan
            planning_result.metadata = dict(getattr(planning_result, "metadata", {}) or {})
            planning_result.metadata.setdefault("optimization", {})
            planning_result.metadata["optimization"].update({
                "applied": True,
                "original_length": len(original_plan),
                "optimized_length": len(optimized_plan),
            })

            if self.optimization_enabled.get(OptimizationType.ROUTE_CACHE, False) and optimized_plan:
                self._add_to_route_cache(goal, state, planning_result)
            with self.data_lock:
                self.performance_stats["optimized_plans"] += 1
        else:
            # Aun en fallo, devolver plan/warnings originales intactos.
            planning_result.plan = original_plan

        elapsed = time.perf_counter() - start_time
        with self.data_lock:
            self.performance_stats["optimization_time"] += elapsed
            self.performance_stats["total_plans"] += 1
        prior_time = _finite_float(getattr(planning_result, "execution_time", 0.0), 0.0, 0.0)
        planning_result.execution_time = prior_time + elapsed
        return planning_result

    # ==================================================================
    # CACHÉ LRU
    # ==================================================================

    def _check_route_cache(self, goal: Goal, current_state: Dict[str, Any]) -> Optional["PlanningResult"]:
        from src.hands.planner.planner import PlannerStatus, PlanQuality, PlanningResult

        state_hash = self._hash_state(current_state)
        cache_key = self._build_cache_key(goal, state_hash)
        with self.cache_lock:
            entry = self.route_cache.get(cache_key)
            if entry is None:
                return None
            entry.access_count += 1
            entry.timestamp = time.time()
            self.route_cache.move_to_end(cache_key)
            quality = entry.quality
            if isinstance(quality, str):
                try:
                    quality = PlanQuality(quality)
                except ValueError:
                    quality = PlanQuality.UNCERTAIN
            return PlanningResult(
                status=PlannerStatus.COMPLETED,
                plan=copy.deepcopy(entry.plan),
                plan_id=f"cached_{getattr(goal, 'id', 'goal')}_{state_hash[:12]}",
                goal=goal,
                current_state=copy.deepcopy(current_state),
                execution_time=0.0,
                quality=quality,
                alternatives=[],
                metadata={
                    "from_cache": True,
                    "cache_access_count": entry.access_count,
                    "cached_route_success_rate": entry.success_rate,
                    "original_cost": entry.cost,
                    "start_state_hash": state_hash,
                },
            )

    def _add_to_route_cache(self, goal: Goal, current_state: Dict[str, Any], result: "PlanningResult") -> None:
        plan = getattr(result, "plan", None)
        if not isinstance(plan, list) or not plan:
            return
        state_hash = self._hash_state(current_state)
        cache_key = self._build_cache_key(goal, state_hash)
        entry = RouteCacheEntry(
            goal_id=str(getattr(goal, "id", "")),
            start_state_hash=state_hash,
            plan=copy.deepcopy(plan),
            cost=sum(self._node_cost(node) for node in plan),
            quality=getattr(result, "quality", None),
            timestamp=time.time(),
            execution_time=_finite_float(getattr(result, "execution_time", 0.0), 0.0, 0.0),
        )
        with self.cache_lock:
            # Replacing an existing entry makes it the most recently used.
            self.route_cache[cache_key] = entry
            self.route_cache.move_to_end(cache_key)
            while len(self.route_cache) > self.max_cache_size:
                self.route_cache.popitem(last=False)

    def record_route_execution(self, goal_id: str, current_state: Dict[str, Any], success: bool, execution_time: float = 0.0) -> bool:
        """Actualiza métricas de la ruta cacheada después de observar su ejecución."""
        state_hash = self._hash_state(current_state)
        dummy_goal = type("_GoalKey", (), {"id": goal_id, "type": None, "target": None, "constraints": []})()
        cache_key = self._build_cache_key(dummy_goal, state_hash)
        with self.cache_lock:
            entry = self.route_cache.get(cache_key)
            if entry is None:
                # Goal signatures pueden contener más campos; buscar por hash/id.
                matches = [e for e in self.route_cache.values() if e.goal_id == str(goal_id) and e.start_state_hash == state_hash]
                if not matches:
                    return False
                entry = matches[-1]
            observations = max(0, entry.execution_count)
            prior_rate = min(1.0, max(0.0, entry.success_rate))
            entry.success_rate = (prior_rate * observations + (1.0 if success else 0.0)) / (observations + 1.0)
            entry.execution_count = observations + 1
            entry.execution_time = _finite_float(execution_time, entry.execution_time, 0.0)
            return True

    def _build_cache_key(self, goal: Goal, state_hash: str) -> str:
        goal_signature = {
            "id": getattr(goal, "id", None),
            "type": getattr(goal, "type", None),
            "target": getattr(goal, "target", None),
            "constraints": getattr(goal, "constraints", []),
            "required_capabilities": self._safe_goal_capabilities(goal),
        }
        return f"{self._stable_hash(goal_signature)}:{state_hash}"

    @staticmethod
    def _safe_goal_capabilities(goal: Any) -> List[str]:
        getter = getattr(goal, "get_required_capabilities", None)
        if callable(getter):
            try:
                result = getter()
                return _string_list(result)
            except Exception:
                pass
        return _string_list(getattr(goal, "required_capabilities", []))

    def _hash_state(self, state: Dict[str, Any]) -> str:
        relevant = self._strip_volatile_state(state if isinstance(state, dict) else {})
        return self._stable_hash(relevant)

    @classmethod
    def _stable_hash(cls, value: Any) -> str:
        normalized = cls._normalize_for_json(value)
        serialized = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_for_json(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return cls._normalize_for_json(value.value)
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        if isinstance(value, dict):
            return {str(k): cls._normalize_for_json(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [cls._normalize_for_json(v) for v in value]
        if isinstance(value, (set, frozenset)):
            normalized = [cls._normalize_for_json(v) for v in value]
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return cls._normalize_for_json(to_dict())
            except Exception:
                pass
        if hasattr(value, "__dict__"):
            try:
                return cls._normalize_for_json(vars(value))
            except Exception:
                pass
        return {"__type__": type(value).__qualname__, "value": str(value)}

    @staticmethod
    def _strip_volatile_state(state: Dict[str, Any]) -> Dict[str, Any]:
        volatile = {"timestamp", "updated_at", "created_at", "last_checked", "last_updated"}
        def strip(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: strip(item) for key, item in value.items() if str(key) not in volatile}
            if isinstance(value, list):
                return [strip(item) for item in value]
            return copy.deepcopy(value)
        return strip(state)

    # ==================================================================
    # REDUNDANCIAS / ALTERNATIVAS
    # ==================================================================

    def _remove_redundancies(self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Elimina repeticiones evidentes, preservando acciones observables."""
        del current_state
        if not isinstance(plan, list) or len(plan) <= 1:
            return copy.deepcopy(plan or [])
        result: List[Dict[str, Any]] = []
        seen_action_ids: set[str] = set()
        for raw_node in plan:
            if not isinstance(raw_node, dict):
                continue
            node = copy.deepcopy(raw_node)
            action_id = self._node_identifier(node)
            if not action_id:
                result.append(node)
                continue
            effects = node.get("effects", [])
            cumulative = bool(node.get("cumulative", False))
            observable = bool(node.get("side_effects", node.get("observable", False)))
            # No quitar nodos con efectos, parámetros distintos o efectos declarados.
            signature = self._stable_hash({
                "action": action_id,
                "parameters": node.get("parameters", {}),
                "application": node.get("application"),
            })
            duplicate = signature in seen_action_ids
            if duplicate and not effects and not cumulative and not observable:
                continue
            result.append(node)
            seen_action_ids.add(signature)
        return result

    def _select_optimal_alternatives(self, alternatives: Optional[List[List[Dict[str, Any]]]], current_state: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        if not alternatives:
            return []
        scored: List[Tuple[float, List[Dict[str, Any]]]] = []
        for raw_plan in alternatives:
            if not isinstance(raw_plan, list) or not raw_plan or any(not isinstance(n, dict) for n in raw_plan):
                continue
            plan = copy.deepcopy(raw_plan)
            total_cost = sum(self._node_cost(node) for node in plan)
            compatibility = self._calculate_state_compatibility(plan, current_state)
            learned_cost = self._get_learned_cost_for_plan(plan)
            # learned_cost is a cost estimate, not an arbitrary bonus.
            score = -learned_cost + compatibility * max(1.0, total_cost * 0.1)
            if learned_cost + 1e-9 < total_cost:
                with self.data_lock:
                    self.performance_stats["cost_improvements"] += 1
            scored.append((score, plan))
        scored.sort(key=lambda item: (-item[0], len(item[1]), self._plan_signature(item[1])))
        best = [plan for _, plan in scored[:3]]
        if len(scored) >= 2:
            improvement = scored[0][0] - scored[1][0]
            with self.data_lock:
                total = self.performance_stats["alternatives_selected"] + 1.0
                previous = self.performance_stats["average_improvement"]
                self.performance_stats["average_improvement"] = (previous * (total - 1.0) + improvement) / total
        return best

    def _apply_context_optimization(self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Ajusta metadatos/costes contextuales sin alterar el plan de entrada."""
        del current_state
        optimized = copy.deepcopy(plan)
        preferences = self.context_data.user_preferences.get("preferred_methods", {})
        available_ids = getattr(self.planner, "available_nodes", {}) or {}
        if isinstance(preferences, dict):
            for index, node in enumerate(optimized):
                action_id = self._node_identifier(node)
                preferred = preferences.get(action_id)
                # No sustituir por un identificador arbitrario que el sistema no conoce.
                if preferred and preferred != action_id and str(preferred) in available_ids:
                    original = node.get("id", action_id)
                    node["id"] = str(preferred)
                    node["action"] = str(preferred)
                    node["original_method"] = original
                    node["optimization_applied"] = True
                    node["cost"] = max(0.0, self._node_cost(node))

        current_hour = str(time.localtime().tm_hour)
        preferred_at_hour = set(self.context_data.time_patterns.get(current_hour, []))
        recent_success = set(self.context_data.success_patterns.get("recent_success", []))
        for node in optimized:
            node_id = self._node_identifier(node)
            if node_id in preferred_at_hour:
                node["cost"] = max(0.0, self._node_cost(node) * 0.95)
            if node_id in recent_success:
                node["cost"] = max(0.0, self._node_cost(node) * 0.98)
        return optimized

    def _create_optimized_node(self, original_id: str, optimized_method: str, original_node: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibilidad legacy para generar una variante de nodo."""
        optimized_node = copy.deepcopy(original_node)
        optimized_node["id"] = optimized_method
        optimized_node["action"] = optimized_method
        optimized_node["original_method"] = original_id
        optimized_node["optimization_applied"] = True
        factors = {"hotkey_ctrl_l": 0.5, "hotkey_ctrl_t": 0.5, "keyboard_shortcut": 0.7, "mouse_click": 1.2, "ui_element": 1.0}
        optimized_node["cost"] = max(0.0, self._node_cost(original_node) * factors.get(optimized_method, 1.0))
        return optimized_node

    # ==================================================================
    # COSTE / COMPATIBILIDAD
    # ==================================================================

    def _calculate_state_compatibility(self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]) -> float:
        checks = 0
        matched = 0
        for node in plan:
            for precondition in node.get("preconditions", []) or []:
                checks += 1
                if self._evaluate_condition_with_state(precondition, current_state):
                    matched += 1
        return matched / checks if checks else 1.0

    def _evaluate_condition_with_state(self, condition: Any, state: Dict[str, Any]) -> bool:
        if callable(condition):
            try:
                return bool(condition(state))
            except Exception:
                return False
        if isinstance(condition, dict):
            key = condition.get("key", condition.get("state"))
            if key is None:
                return all(self._evaluate_condition_with_state({"key": k, "value": v}, state) for k, v in condition.items())
            expected = condition.get("equals", condition.get("value", condition.get("expected", True)))
            return self._get_nested_state_value(state, str(key), object()) == expected
        if not isinstance(condition, str):
            return bool(condition)
        value = self._get_nested_state_value(state, condition, None)
        if value is not None:
            return bool(value)
        if condition.endswith(("_open", "_active")):
            app, suffix = condition.rsplit("_", 1)
            app_states = state.get("application_states", {})
            app_state = app_states.get(app, {}) if isinstance(app_states, dict) else {}
            if isinstance(app_state, dict) and suffix in app_state:
                return bool(app_state[suffix])
        # Unknown conditions are not considered satisfied.
        return False

    @staticmethod
    def _get_nested_state_value(state: Dict[str, Any], key: str, default: Any = None) -> Any:
        if key in state:
            return state[key]
        current: Any = state
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def _get_learned_cost_for_plan(self, plan: List[Dict[str, Any]]) -> float:
        base_cost = sum(self._node_cost(node) for node in plan)
        if not self.optimization_enabled.get(OptimizationType.COST_LEARNING, False):
            return base_cost
        adjustments: Dict[str, float] = {}
        external = self.external_learning_system
        if external is not None:
            try:
                raw = external.get_cost_adjustments()
                if isinstance(raw, dict):
                    adjustments = {str(k): _finite_float(v, 0.0) for k, v in raw.items()}
            except Exception as exc:
                logger.debug("[OPTIMIZATION] Learning externo no disponible: %s", exc)
        total = 0.0
        for node in plan:
            node_id = self._node_identifier(node)
            base = self._node_cost(node)
            if node_id in adjustments:
                # LearningSystem expone deltas; sumarlos al coste base evita tratar
                # una corrección relativa como un coste absoluto.
                total += max(0.0, base + adjustments[node_id])
            else:
                model = self.cost_models.get(node_id, {})
                learned = model.get("average_cost") if model else None
                total += max(0.0, _finite_float(learned, base, 0.0)) if learned is not None else base
        return total

    # ==================================================================
    # APRENDIZAJE
    # ==================================================================

    def record_execution_result(self, plan: List[Dict[str, Any]], execution_time: float, success: bool, context: Optional[Dict[str, Any]] = None) -> None:
        """Registra un resultado observado; este método no ejecuta el plan."""
        if not plan:
            return
        safe_context = copy.deepcopy(context) if isinstance(context, dict) else {}
        duration = _finite_float(execution_time, 0.0, 0.0)
        per_node_time = duration / max(1, len(plan))
        records: List[Tuple[str, CostLearningData]] = []
        for node in plan:
            if not isinstance(node, dict):
                continue
            node_id = self._node_identifier(node)
            if not node_id:
                continue
            estimated = self._node_cost(node)
            # Hasta que el executor proporcione un coste real, la duración media
            # por paso solo actúa como proxy explícito de coste.
            data = CostLearningData(
                node_id=node_id,
                estimated_cost=estimated,
                actual_cost=per_node_time,
                execution_time=per_node_time,
                success=bool(success),
                timestamp=time.time(),
                context=copy.deepcopy(safe_context),
            )
            records.append((node_id, data))

        with self.data_lock:
            for node_id, data in records:
                history = self.cost_learning[node_id]
                history.append(data)
                if len(history) > 1000:
                    del history[:-1000]
                self._update_cost_model(node_id, data)
            self._update_context_patterns(plan, bool(success), safe_context)

        external = self.external_learning_system
        if external is not None:
            method = getattr(external, "record_node_execution", None)
            if callable(method):
                for node in plan:
                    if not isinstance(node, dict):
                        continue
                    node_id = self._node_identifier(node)
                    if not node_id:
                        continue
                    try:
                        method(
                            node_id=node_id,
                            success=bool(success),
                            execution_time=per_node_time,
                            estimated_cost=self._node_cost(node),
                            context=safe_context,
                            application=node.get("application"),
                        )
                    except Exception as exc:
                        logger.debug("[OPTIMIZATION] No se pudo sincronizar LearningSystem para %s: %s", node_id, exc)

    def _update_cost_model(self, node_id: str, learning_data: CostLearningData) -> None:
        model = self.cost_models.setdefault(node_id, {
            "total_executions": 0.0,
            "successful_executions": 0.0,
            "average_cost": 0.0,
            "average_execution_time": 0.0,
            "success_rate": 0.0,
        })
        total = int(model.get("total_executions", 0)) + 1
        successes = int(model.get("successful_executions", 0)) + int(learning_data.success)
        alpha = 0.1
        if total == 1:
            model["average_cost"] = learning_data.actual_cost
            model["average_execution_time"] = learning_data.execution_time
        else:
            model["average_cost"] = (1.0 - alpha) * _finite_float(model.get("average_cost")) + alpha * learning_data.actual_cost
            model["average_execution_time"] = (1.0 - alpha) * _finite_float(model.get("average_execution_time")) + alpha * learning_data.execution_time
        model["total_executions"] = float(total)
        model["successful_executions"] = float(successes)
        model["success_rate"] = successes / total

    def _update_context_patterns(self, plan: List[Dict[str, Any]], success: bool, context: Dict[str, Any]) -> None:
        hour = str(time.localtime().tm_hour)
        bucket = self.context_data.time_patterns.setdefault(hour, [])
        for node in plan:
            node_id = self._node_identifier(node)
            if node_id and node_id not in bucket:
                bucket.append(node_id)
        self.context_data.time_patterns[hour] = bucket[-100:]
        if success:
            recent = self.context_data.success_patterns.setdefault("recent_success", [])
            recent.extend(self._node_identifier(node) for node in plan if self._node_identifier(node))
            self.context_data.success_patterns["recent_success"] = recent[-20:]
        preferences = context.get("user_preferences")
        if isinstance(preferences, dict):
            self.context_data.user_preferences.update(copy.deepcopy(preferences))
        application = context.get("application")
        if application:
            app_bucket = self.context_data.application_patterns.setdefault(str(application), [])
            app_bucket.extend(self._node_identifier(node) for node in plan if self._node_identifier(node))
            self.context_data.application_patterns[str(application)] = app_bucket[-50:]

    # ==================================================================
    # ESTADÍSTICAS / CONFIGURACIÓN
    # ==================================================================

    def get_optimization_stats(self) -> Dict[str, Any]:
        with self.data_lock:
            stats: Dict[str, Any] = dict(self.performance_stats)
            stats["cost_models_count"] = len(self.cost_models)
            stats["total_learning_data"] = sum(len(items) for items in self.cost_learning.values())
            stats["context_patterns_count"] = sum(len(values) for values in self.context_data.time_patterns.values())
            stats["user_preferences_count"] = len(self.context_data.user_preferences)
            stats["optimization_enabled"] = {kind.value: enabled for kind, enabled in self.optimization_enabled.items()}
        with self.cache_lock:
            stats["cache_size"] = len(self.route_cache)
            stats["cache_hit_rate"] = stats["cached_plans"] / max(stats["total_plans"], 1.0)
        return stats

    def clear_cache(self) -> None:
        with self.cache_lock:
            self.route_cache.clear()
        logger.info("[OPTIMIZATION] Caché de rutas limpiado")

    def invalidate_cache_for_goal(self, goal_id: str) -> int:
        """Invalida las entradas cacheadas de un objetivo tras cambios de dominio."""
        target = str(goal_id)
        with self.cache_lock:
            keys = [key for key, entry in self.route_cache.items() if entry.goal_id == target]
            for key in keys:
                self.route_cache.pop(key, None)
        return len(keys)

    def enable_optimization(self, optimization_type: OptimizationType, enabled: bool = True) -> None:
        if isinstance(optimization_type, str):
            try:
                optimization_type = OptimizationType(optimization_type)
            except ValueError as exc:
                raise ValueError(f"Tipo de optimización no soportado: {optimization_type}") from exc
        if not isinstance(optimization_type, OptimizationType):
            raise ValueError("optimization_type debe ser OptimizationType")
        with self.data_lock:
            self.optimization_enabled[optimization_type] = bool(enabled)

    # ==================================================================
    # PERSISTENCIA
    # ==================================================================

    def export_optimization_data(self, filepath: str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_lock, self.data_lock:
            export_data = {
                "schema_version": 2,
                "cache": {key: entry.to_dict() for key, entry in self.route_cache.items()},
                "cost_learning": {key: [item.to_dict() for item in values] for key, values in self.cost_learning.items()},
                "cost_models": copy.deepcopy(self.cost_models),
                "context_data": asdict(self.context_data),
                "performance_stats": copy.deepcopy(self.performance_stats),
                "optimization_enabled": {opt.value: enabled for opt, enabled in self.optimization_enabled.items()},
            }
        fd, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(export_data, handle, indent=2, ensure_ascii=False, default=str, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
        logger.info("[OPTIMIZATION] Datos de optimización exportados a: %s", path)

    def import_optimization_data(self, filepath: str) -> None:
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as handle:
            import_data = json.load(handle)
        if not isinstance(import_data, dict):
            raise ValueError("El archivo de optimización debe contener un objeto JSON")

        # Validar y construir todo en estructuras temporales antes de mutar el estado vivo.
        raw_cache = import_data.get("cache", {})
        if raw_cache is None:
            raw_cache = {}
        if not isinstance(raw_cache, dict):
            raise ValueError("cache debe ser un objeto JSON")
        new_cache: OrderedDict[str, RouteCacheEntry] = OrderedDict()
        for cache_key, cache_data in raw_cache.items():
            if isinstance(cache_data, dict):
                entry = RouteCacheEntry.from_dict(cache_data)
                if entry.goal_id and entry.start_state_hash:
                    new_cache[str(cache_key)] = entry
        while len(new_cache) > self.max_cache_size:
            new_cache.popitem(last=False)

        raw_learning = import_data.get("cost_learning", {})
        if raw_learning is None:
            raw_learning = {}
        if not isinstance(raw_learning, dict):
            raise ValueError("cost_learning debe ser un objeto JSON")
        new_learning: Dict[str, List[CostLearningData]] = defaultdict(list)
        for node_id, values in raw_learning.items():
            if not isinstance(values, list):
                continue
            new_learning[str(node_id)] = [CostLearningData.from_dict(item) for item in values if isinstance(item, dict)][-1000:]

        raw_models = import_data.get("cost_models", {})
        if raw_models is None:
            raw_models = {}
        if not isinstance(raw_models, dict):
            raise ValueError("cost_models debe ser un objeto JSON")
        new_models: Dict[str, Dict[str, float]] = {}
        for node_id, raw_model in raw_models.items():
            if not isinstance(raw_model, dict):
                continue
            total = _finite_float(raw_model.get("total_executions", 0), 0.0, 0.0)
            successes = min(total, _finite_float(raw_model.get("successful_executions", 0), 0.0, 0.0))
            new_models[str(node_id)] = {
                "total_executions": total,
                "successful_executions": successes,
                "average_cost": _finite_float(raw_model.get("average_cost", 0), 0.0, 0.0),
                "average_execution_time": _finite_float(raw_model.get("average_execution_time", 0), 0.0, 0.0),
                "success_rate": min(1.0, successes / total) if total else 0.0,
            }

        context_raw = import_data.get("context_data", {})
        if context_raw is None:
            context_raw = {}
        if not isinstance(context_raw, dict):
            raise ValueError("context_data debe ser un objeto JSON")
        new_context = ContextData(
            user_preferences=copy.deepcopy(context_raw.get("user_preferences", {})) if isinstance(context_raw.get("user_preferences", {}), dict) else {},
            application_patterns={str(k): _string_list(v) for k, v in (context_raw.get("application_patterns", {}) or {}).items()} if isinstance(context_raw.get("application_patterns", {}) or {}, dict) else {},
            time_patterns={str(k): _string_list(v) for k, v in (context_raw.get("time_patterns", {}) or {}).items()} if isinstance(context_raw.get("time_patterns", {}) or {}, dict) else {},
            success_patterns={str(k): _string_list(v) for k, v in (context_raw.get("success_patterns", {}) or {}).items()} if isinstance(context_raw.get("success_patterns", {}) or {}, dict) else {},
        )

        raw_stats = import_data.get("performance_stats", {})
        if raw_stats is None:
            raw_stats = {}
        if not isinstance(raw_stats, dict):
            raise ValueError("performance_stats debe ser un objeto JSON")
        new_stats = dict(self.performance_stats)
        for key in new_stats:
            if key in raw_stats:
                new_stats[key] = _finite_float(raw_stats[key], new_stats[key], 0.0)

        enabled_raw = import_data.get("optimization_enabled", {})
        if enabled_raw is None:
            enabled_raw = {}
        if not isinstance(enabled_raw, dict):
            raise ValueError("optimization_enabled debe ser un objeto JSON")
        new_enabled = dict(self.optimization_enabled)
        for kind in OptimizationType:
            if kind.value in enabled_raw:
                new_enabled[kind] = bool(enabled_raw[kind.value])

        with self.cache_lock, self.data_lock:
            self.route_cache = new_cache
            self.cost_learning = defaultdict(list, new_learning)
            self.cost_models = new_models
            self.context_data = new_context
            self.performance_stats = new_stats
            self.optimization_enabled = new_enabled
        logger.info("[OPTIMIZATION] Datos importados desde: %s", path)

    # ==================================================================
    # UTILIDADES
    # ==================================================================

    @staticmethod
    def _node_identifier(node: Any) -> str:
        if isinstance(node, dict):
            return str(node.get("action", node.get("id", "")) or "").strip()
        return str(getattr(node, "id", "") or "").strip()

    @staticmethod
    def _node_cost(node: Any) -> float:
        try:
            value = node.get("cost", 1.0) if isinstance(node, dict) else getattr(node, "cost", 1.0)
            cost = float(value if value is not None else 1.0)
            return max(0.0, cost) if math.isfinite(cost) else 1.0
        except (TypeError, ValueError, OverflowError):
            return 1.0

    @classmethod
    def _plan_signature(cls, plan: Sequence[Dict[str, Any]]) -> str:
        return cls._stable_hash([
            {"id": cls._node_identifier(node), "cost": cls._node_cost(node), "parameters": node.get("parameters", {}) if isinstance(node, dict) else {}}
            for node in plan
        ])


__all__ = [
    "OptimizationType",
    "RouteCacheEntry",
    "CostLearningData",
    "ContextData",
    "OptimizationManager",
]
