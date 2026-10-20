"""

Única fuente de verdad para:
- NodeType: Tipos de nodos en el sistema de planificación
- Node: Modelo conceptual común para todos los elementos
- Goal: Objetivos que el sistema debe alcanzar
- Task: Tareas jerárquicas descomponibles
- TaskStatus: Estados de ejecución de tareas

Las funciones/callbacks no se serializan. Las reglas declarativas sí.
"""

from __future__ import annotations

import math
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from src.utils.logger import get_logger

logger = get_logger(__name__)


ConditionLike = Union[str, Dict[str, Any], Any]
EffectLike = Union[str, Dict[str, Any], Any]


class NodeType(Enum):
    """Tipos de nodos en el sistema de planificación."""

    INTENTION = "intention"
    GOAL = "goal"
    TASK = "task"
    ACTION = "action"
    CONDITION = "condition"
    STATE = "state"
    RESOURCE = "resource"
    APPLICATION = "application"
    UI_ELEMENT = "ui_element"
    RESULT = "result"
    PLAN = "plan"


class TaskStatus(Enum):
    """Estado de ejecución de tareas."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"



def _copy_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Copia el estado sin permitir que los efectos muten accidentalmente el original."""
    if not isinstance(state, dict):
        return {}
    try:
        return deepcopy(state)
    except Exception:
        # Algunos estados pueden contener objetos externos no copiables. En ese caso
        # conservamos al menos una copia del nivel superior en vez de abortar la acción.
        logger.debug("No se pudo copiar profundamente el estado; se usará una copia superficial.")
        return dict(state)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convierte un valor a float finito y devuelve el valor por defecto si no es válido."""
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _serialize_value(value: Any, _seen: Optional[Set[int]] = None) -> Any:
    """Convierte valores habituales a datos serializables y evita ciclos de referencias."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Enum):
        return _serialize_value(value.value, _seen)

    seen = _seen if _seen is not None else set()
    identity = id(value)
    if identity in seen:
        return "<circular-reference>"

    if isinstance(value, dict):
        seen.add(identity)
        try:
            return {str(key): _serialize_value(item, seen) for key, item in value.items()}
        finally:
            seen.discard(identity)

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(identity)
        try:
            items = value
            if isinstance(value, (set, frozenset)):
                items = sorted(value, key=repr)
            return [_serialize_value(item, seen) for item in items]
        finally:
            seen.discard(identity)

    # Los callbacks no se guardan como texto repr (que puede contener direcciones de
    # memoria y nunca permitiría reconstruir la función).
    if callable(value):
        return "<non-serializable-callable>"

    # Los objetos externos no tienen un contrato común de reconstrucción.
    return repr(value)


@dataclass
class Node:
    """
    Modelo conceptual común para todos los elementos del sistema.

    Un nodo puede representar objetivo, tarea, acción, condición, estado,
    recurso, aplicación, elemento UI, resultado o plan.
    """

    id: str
    type: NodeType
    name: str
    description: str = ""
    preconditions: List[ConditionLike] = field(default_factory=list)
    effects: List[EffectLike] = field(default_factory=list)
    cost: float = 1.0
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    application: Optional[str] = None
    ui_element: Optional[str] = None
    execute_callback: Optional[Callable[..., Any]] = None
    success_criteria: Optional[Callable[..., bool]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)

    # FASE 6 - Grafo de Acciones
    in_edges: List[str] = field(default_factory=list)
    out_edges: List[str] = field(default_factory=list)
    edge_costs: Dict[str, float] = field(default_factory=dict)

    # FASE 10 - Precondiciones y Efectos avanzados
    preconditions_functions: List[Callable[[Dict[str, Any]], bool]] = field(default_factory=list)
    effects_functions: List[Callable[..., Dict[str, Any]]] = field(default_factory=list)

    # FASE 3 - Estado del mundo
    state_requirements: Dict[str, Any] = field(default_factory=dict)
    state_modifications: Dict[str, Any] = field(default_factory=dict)

    # FASE 14 - Acciones reutilizables
    reusable_action: bool = False
    action_category: Optional[str] = None

    # FASE 18 - Aprendizaje
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    success_rate: float = 0.0
    average_execution_time: float = 0.0
    last_executed: Optional[float] = None

    def __post_init__(self) -> None:
        if isinstance(self.type, str):
            self.type = NodeType(self.type.strip().lower())

        self.cost = max(0.0, _safe_float(self.cost, 1.0))
        self.success_rate = min(1.0, max(0.0, _safe_float(self.success_rate)))
        self.average_execution_time = max(0.0, _safe_float(self.average_execution_time))
        if self.last_executed is not None:
            self.last_executed = _safe_float(self.last_executed, 0.0) or None

        for field_name in (
            "preconditions",
            "effects",
            "dependencies",
            "children",
            "in_edges",
            "out_edges",
            "preconditions_functions",
            "effects_functions",
            "execution_history",
        ):
            value = getattr(self, field_name)
            if value is None:
                setattr(self, field_name, [])
            elif isinstance(value, list):
                continue
            elif isinstance(value, (tuple, set, frozenset)):
                setattr(self, field_name, list(value))
            else:
                setattr(self, field_name, [value])

        for field_name in (
            "parameters",
            "metadata",
            "edge_costs",
            "state_requirements",
            "state_modifications",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, dict):
                setattr(self, field_name, {})

    def _evaluate_precondition(self, precondition: ConditionLike, current_state: Dict[str, Any]) -> bool:
        """Evalúa una precondición declarativa o funcional sin acoplarse a otro módulo."""
        if isinstance(precondition, str):
            return bool(current_state.get(precondition, False))

        if isinstance(precondition, dict):
            condition_type = precondition.get("type", "state_true")
            if isinstance(condition_type, Enum):
                condition_type = condition_type.value
            key = precondition.get("key", precondition.get("state"))
            expected = precondition.get("value", precondition.get("expected_value"))

            if condition_type in {"state_equals", "state_exists", "state_true", "state_greater_than", "state_less_than"} and key is None:
                return False
            if condition_type == "state_equals":
                return current_state.get(key) == expected
            if condition_type == "state_exists":
                return key in current_state and current_state.get(key) is not None
            if condition_type == "state_true":
                return bool(current_state.get(key, False))
            if condition_type == "state_greater_than":
                return _safe_float(current_state.get(key, 0)) > _safe_float(expected)
            if condition_type == "state_less_than":
                return _safe_float(current_state.get(key, 0)) < _safe_float(expected)
            if condition_type in {"application_open", "application_active"}:
                app_name = precondition.get("parameters", {}).get("app_name") or key or ""
                suffix = "_open" if condition_type == "application_open" else "_active"
                return bool(current_state.get(f"{str(app_name).lower()}{suffix}", False))
            if condition_type in {"ui_element_available", "ui_element_calibrated"}:
                params = precondition.get("parameters", {})
                app_name = params.get("app_name") or ""
                element_name = params.get("element_name") or ""
                suffix = "_available" if condition_type == "ui_element_available" else "_calibrated"
                key_name = f"{str(app_name).lower()}_{str(element_name).lower()}{suffix}"
                return bool(current_state.get(key_name, False))
            if condition_type == "custom_function":
                function = precondition.get("function")
                return bool(function(current_state)) if callable(function) else False
            if condition_type == "composite_and":
                return all(self._evaluate_precondition(item, current_state) for item in precondition.get("parameters", {}).get("conditions", []))
            if condition_type == "composite_or":
                return any(self._evaluate_precondition(item, current_state) for item in precondition.get("parameters", {}).get("conditions", []))
            return False

        evaluate = getattr(precondition, "evaluate", None)
        if callable(evaluate):
            return bool(evaluate(current_state))

        if callable(precondition):
            return bool(precondition(current_state))

        return False

    def can_execute(self, current_state: Dict[str, Any]) -> bool:
        """Verifica las precondiciones declarativas, funcionales y de estado del nodo."""
        state = current_state if isinstance(current_state, dict) else {}
        try:
            if not all(self._evaluate_precondition(condition, state) for condition in self.preconditions):
                return False

            if not all(bool(func(state)) for func in self.preconditions_functions):
                return False

            return all(state.get(key) == expected for key, expected in self.state_requirements.items())
        except Exception:
            logger.debug("No se pudieron evaluar las precondiciones del nodo %s.", self.id, exc_info=True)
            return False

    def _apply_effect(self, effect: EffectLike, state: Dict[str, Any], execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica un efecto declarativo/objeto manteniendo compatibilidad con Effect."""
        new_state = state

        if isinstance(effect, str):
            new_state[effect] = True
            return new_state

        if isinstance(effect, dict):
            effect_type = effect.get("type", "state_set")
            if isinstance(effect_type, Enum):
                effect_type = effect_type.value
            key = effect.get("key", effect.get("state"))
            value = effect.get("value")

            parameter_only_effects = {
                "application_open",
                "application_close",
                "application_activate",
                "ui_element_calibrate",
                "ui_element_focus",
                "custom_function",
            }
            if effect_type != "composite" and key is None and effect_type not in parameter_only_effects:
                return new_state
            if key is not None:
                key = str(key)
            if effect_type == "state_set":
                new_state[key] = value
            elif effect_type == "state_increment":
                new_state[key] = _safe_float(new_state.get(key, 0)) + _safe_float(value, 1.0)
            elif effect_type == "state_decrement":
                new_state[key] = _safe_float(new_state.get(key, 0)) - _safe_float(value, 1.0)
            elif effect_type == "state_append":
                current = list(new_state.get(key, [])) if isinstance(new_state.get(key, []), list) else []
                current.append(value)
                new_state[key] = current
            elif effect_type == "state_remove":
                current = list(new_state.get(key, [])) if isinstance(new_state.get(key, []), list) else []
                if value in current:
                    current.remove(value)
                new_state[key] = current
            elif effect_type == "application_open":
                params = effect.get("parameters", {})
                app_name = params.get("app_name") or key or ""
                if app_name:
                    prefix = str(app_name).strip().lower()
                    new_state[f"{prefix}_open"] = True
                    new_state[f"{prefix}_active"] = True
            elif effect_type == "application_close":
                params = effect.get("parameters", {})
                app_name = params.get("app_name") or key or ""
                if app_name:
                    prefix = str(app_name).strip().lower()
                    new_state[f"{prefix}_open"] = False
                    new_state[f"{prefix}_active"] = False
            elif effect_type == "application_activate":
                params = effect.get("parameters", {})
                app_name = params.get("app_name") or key or ""
                if app_name:
                    new_state[f"{str(app_name).strip().lower()}_active"] = True
            elif effect_type in {"ui_element_calibrate", "ui_element_focus"}:
                params = effect.get("parameters", {})
                app_name = str(params.get("app_name") or "").strip().lower()
                element_name = str(params.get("element_name") or "").strip().lower()
                if app_name and element_name:
                    prefix = f"{app_name}_{element_name}"
                    if effect_type == "ui_element_calibrate":
                        new_state[f"{prefix}_calibrated"] = True
                        new_state[f"{prefix}_available"] = True
                    else:
                        new_state[f"{prefix}_focused"] = True
            elif effect_type == "custom_function":
                function = effect.get("function")
                if callable(function):
                    result = function(new_state, execution_result)
                    if isinstance(result, dict):
                        new_state = result
            elif effect_type == "composite":
                for item in effect.get("parameters", {}).get("effects", []):
                    new_state = self._apply_effect(item, new_state, execution_result)
            return new_state

        apply_method = getattr(effect, "apply", None)
        if callable(apply_method):
            result = apply_method(new_state, execution_result)
            return result if isinstance(result, dict) else new_state

        return new_state

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Ejecuta el callback y devuelve el resultado y el estado candidato actualizado."""
        start_time = time.perf_counter()
        attempted_at = time.time()
        current_state = _copy_state(kwargs.get("current_state", kwargs.get("state", {})))

        def record_attempt(record: Dict[str, Any]) -> Dict[str, Any]:
            self.execution_history.append(record)
            self._update_learning_metrics(record)
            self.last_executed = _safe_float(record.get("timestamp"), attempted_at)
            return record

        if self.execute_callback is None:
            record = {
                "success": False,
                "error": "No execute callback",
                "execution_time": 0.0,
                "timestamp": attempted_at,
                "node_id": self.id,
                "node_type": self.type.value,
                "parameters_used": _serialize_value(kwargs),
                "final_state": _serialize_value(current_state),
            }
            record_attempt(record)
            return {**record, "new_state": current_state}

        try:
            result = self.execute_callback(**kwargs)
            execution_time = max(0.0, time.perf_counter() - start_time)
            execution_result = result if isinstance(result, dict) else {"result": result}

            # Los callbacks legacy suelen devolver un diccionario con "success".
            # Un resultado explícitamente fallido no debe aplicar efectos ni cambiar estado.
            callback_success = result is not False
            if isinstance(result, dict) and "success" in result:
                success_value = result["success"]
                if isinstance(success_value, str):
                    callback_success = success_value.strip().lower() not in {"", "0", "false", "no", "failed", "error"}
                else:
                    callback_success = bool(success_value)

            if not callback_success:
                record = {
                    "success": False,
                    "result": result,
                    "error": (
                        str(result.get("error") or "El callback indicó que la ejecución falló.")
                        if isinstance(result, dict)
                        else "El callback devolvió False."
                    ),
                    "execution_time": execution_time,
                    "timestamp": time.time(),
                    "node_id": self.id,
                    "node_type": self.type.value,
                    "parameters_used": _serialize_value(kwargs),
                    "final_state": _serialize_value(current_state),
                }
                record_attempt(record)
                return {**record, "new_state": current_state}

            new_state = _copy_state(current_state)

            for effect in self.effects:
                new_state = self._apply_effect(effect, new_state, execution_result)

            for effect_func in self.effects_functions:
                candidate = effect_func(new_state)
                if isinstance(candidate, dict):
                    new_state = candidate

            # Las modificaciones declarativas son el último paso y prevalecen.
            if self.state_modifications:
                new_state.update(self.state_modifications)

            record = {
                "success": True,
                "result": result,
                "effects_applied": _serialize_value(self.effects),
                "state_modifications": _serialize_value(self.state_modifications),
                "execution_time": execution_time,
                "timestamp": time.time(),
                "node_id": self.id,
                "node_type": self.type.value,
                "parameters_used": _serialize_value(kwargs),
                "final_state": _serialize_value(new_state),
            }
            record_attempt(record)
            return {**record, "new_state": new_state}

        except Exception as exc:
            execution_time = max(0.0, time.perf_counter() - start_time)
            record = {
                "success": False,
                "error": str(exc),
                "execution_time": execution_time,
                "timestamp": time.time(),
                "node_id": self.id,
                "node_type": self.type.value,
                "parameters_used": _serialize_value(kwargs),
                "final_state": _serialize_value(current_state),
            }
            logger.exception("Falló la ejecución del nodo %s (%s).", self.id, self.name)
            record_attempt(record)
            return {**record, "new_state": current_state}

    def _update_learning_metrics(self, execution_record: Dict[str, Any]) -> None:
        """Recalcula métricas desde los registros válidos del histórico acumulado."""
        records = [record for record in self.execution_history if isinstance(record, dict)]
        if not records:
            self.success_rate = 0.0
            self.average_execution_time = 0.0
            return

        total = len(records)
        successful = sum(1 for record in records if bool(record.get("success", False)))
        durations = [
            max(0.0, _safe_float(record.get("execution_time")))
            for record in records
            if "execution_time" in record
        ]

        self.success_rate = successful / total
        self.average_execution_time = sum(durations) / len(durations) if durations else 0.0

    def verify_success(self, result: Any = None, **kwargs) -> bool:
        """Verifica el éxito mediante el criterio configurado."""
        if self.success_criteria is None:
            return True
        try:
            return bool(self.success_criteria(result, **kwargs))
        except Exception:
            logger.debug("Falló el criterio de éxito del nodo %s.", self.id, exc_info=True)
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el nodo a un diccionario serializable."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "preconditions": _serialize_value(self.preconditions),
            "effects": _serialize_value(self.effects),
            "cost": self.cost,
            "dependencies": list(self.dependencies),
            "parameters": _serialize_value(self.parameters),
            "application": self.application,
            "ui_element": self.ui_element,
            "metadata": _serialize_value(self.metadata),
            "parent": self.parent,
            "children": list(self.children),
            "in_edges": list(self.in_edges),
            "out_edges": list(self.out_edges),
            "edge_costs": {str(k): _safe_float(v) for k, v in self.edge_costs.items()},
            "preconditions_functions": "FUNCIONES_NO_SERIALIZABLES",
            "effects_functions": "FUNCIONES_NO_SERIALIZABLES",
            "state_requirements": _serialize_value(self.state_requirements),
            "state_modifications": _serialize_value(self.state_modifications),
            "reusable_action": self.reusable_action,
            "action_category": self.action_category,
            "execution_history": _serialize_value(self.execution_history),
            "success_rate": self.success_rate,
            "average_execution_time": self.average_execution_time,
            "last_executed": self.last_executed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Node":
        """Reconstruye un nodo desde datos serializados, sin restaurar callbacks."""
        if not isinstance(data, dict):
            raise TypeError("Node.from_dict espera un diccionario.")

        normalized = dict(data)
        node_type = normalized.get("type", NodeType.ACTION)
        if node_type is None:
            node_type = NodeType.ACTION
        elif isinstance(node_type, str):
            node_type = NodeType(node_type.strip().lower())
        normalized["type"] = node_type

        # Los callbacks y funciones pertenecen al runtime, no al formato persistido.
        for field_name in (
            "execute_callback",
            "success_criteria",
            "preconditions_functions",
            "effects_functions",
        ):
            normalized.pop(field_name, None)

        # Versiones anteriores pueden guardar estos marcadores textuales.
        for field_name in ("preconditions_functions", "effects_functions"):
            if normalized.get(field_name) == "FUNCIONES_NO_SERIALIZABLES":
                normalized.pop(field_name, None)

        list_fields = (
            "preconditions",
            "effects",
            "dependencies",
            "in_edges",
            "out_edges",
            "children",
            "execution_history",
        )
        dict_fields = (
            "parameters",
            "metadata",
            "edge_costs",
            "state_requirements",
            "state_modifications",
        )
        for field_name in list_fields:
            if normalized.get(field_name) is None:
                normalized[field_name] = []
        for field_name in dict_fields:
            if normalized.get(field_name) is None:
                normalized[field_name] = {}

        return cls(**normalized)

    def add_edge(self, target_node_id: str, cost: float = 1.0) -> None:
        """Añade o actualiza una transición saliente y su coste finito no negativo."""
        if target_node_id is None or not str(target_node_id).strip():
            return
        target_id = str(target_node_id)
        normalized_cost = max(0.0, _safe_float(cost, 1.0))
        if target_id not in self.out_edges:
            self.out_edges.append(target_id)
        self.edge_costs[target_id] = normalized_cost

    def add_in_edge(self, source_node_id: str, cost: float = 1.0) -> None:
        """Registra una transición entrante; el coste canónico reside en el emisor."""
        if source_node_id is not None and str(source_node_id).strip():
            source_id = str(source_node_id)
            if source_id not in self.in_edges:
                self.in_edges.append(source_id)

    def get_edge_cost(self, target_node_id: str) -> Optional[float]:
        """Obtiene el coste de una transición."""
        return self.edge_costs.get(target_node_id)

    def get_valid_transitions(self, current_state: Dict[str, Any], all_nodes: Dict[str, "Node"]) -> List[str]:
        """Devuelve transiciones de salida cuyo nodo destino puede ejecutarse."""
        valid_transitions: List[str] = []
        for target_id in self.out_edges:
            target_node = all_nodes.get(target_id)
            if target_node is not None and target_node.can_execute(current_state):
                valid_transitions.append(target_id)
        return valid_transitions

    def add_precondition_function(self, precond_func: Callable[[Dict[str, Any]], bool]) -> None:
        """Añade una precondición funcional."""
        if callable(precond_func):
            self.preconditions_functions.append(precond_func)

    def add_effect_function(self, effect_func: Callable[..., Dict[str, Any]]) -> None:
        """Añade un efecto funcional."""
        if callable(effect_func):
            self.effects_functions.append(effect_func)

    def set_state_requirement(self, key: str, value: Any) -> None:
        """Define un requisito de estado."""
        self.state_requirements[key] = value

    def set_state_modification(self, key: str, value: Any) -> None:
        """Define una modificación de estado esperada."""
        self.state_modifications[key] = value

    def mark_as_reusable_action(self, category: str) -> None:
        """Marca el nodo como acción reutilizable."""
        self.reusable_action = True
        self.action_category = category

    def get_execution_stats(self) -> Dict[str, Any]:
        """Devuelve estadísticas agregadas sin fallar ante entradas históricas malformadas."""
        records = [record for record in self.execution_history if isinstance(record, dict)]
        if not records:
            return {
                "total_executions": 0,
                "successful_executions": 0,
                "success_rate": 0.0,
                "average_execution_time": 0.0,
                "last_execution": self.last_executed,
                "most_recent_result": None,
            }

        total = len(records)
        successful = sum(1 for record in records if bool(record.get("success", False)))
        times = [
            max(0.0, _safe_float(record.get("execution_time")))
            for record in records
            if "execution_time" in record
        ]
        average = sum(times) / len(times) if times else 0.0

        return {
            "total_executions": total,
            "successful_executions": successful,
            "success_rate": successful / total,
            "average_execution_time": average,
            "last_execution": self.last_executed,
            "most_recent_result": records[-1],
        }


@dataclass
class Goal:
    """Objetivo de alto nivel alcanzable mediante planificación."""

    id: str
    type: str
    target: Union[str, Dict[str, Any]]
    description: str
    priority: int = 1
    deadline: Optional[float] = None
    constraints: List[str] = field(default_factory=list)
    nodes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if isinstance(self.type, Enum):
            self.type = str(self.type.value)
        elif self.type is not None:
            self.type = str(self.type).strip()
        if self.metadata is None or not isinstance(self.metadata, dict):
            self.metadata = {}
        if not isinstance(self.constraints, list):
            self.constraints = list(self.constraints) if isinstance(self.constraints, (tuple, set)) else ([] if self.constraints is None else [str(self.constraints)])
        if not isinstance(self.nodes, list):
            self.nodes = list(self.nodes) if isinstance(self.nodes, (tuple, set)) else ([] if self.nodes is None else [str(self.nodes)])
        self.priority = int(_safe_float(self.priority, 1.0))
        if self.deadline is not None:
            deadline = _safe_float(self.deadline, float("nan"))
            self.deadline = deadline if math.isfinite(deadline) else None
        self.created_at = _safe_float(self.created_at, time.time())
        self.updated_at = _safe_float(self.updated_at, self.created_at)

    def _target_value(self, key: str = "url", default: Any = "") -> Any:
        if isinstance(self.target, dict):
            return self.target.get(key, default)
        return self.target

    def is_achieved(self, current_state: Dict[str, Any]) -> bool:
        """Comprueba si el estado actual satisface el objetivo conocido."""
        state = current_state if isinstance(current_state, dict) else {}
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        goal_type = self.type.value if isinstance(self.type, Enum) else str(self.type)

        if goal_type in {"navigate", "navigate_stream", "navigate_to_entity"}:
            expected_url = self._target_value("url", "")
            if not expected_url:
                expected_url = metadata.get("url", "") or metadata.get("target_url", "")
            if not expected_url and isinstance(self.target, str):
                expected_url = self.target
            if not expected_url:
                entity_data = metadata.get("entity_data", {})
                expected_url = entity_data.get("url") if isinstance(entity_data, dict) else None
            return bool(expected_url and state.get("current_url", "") == expected_url)

        if goal_type == "open_application":
            app_name = self._target_value("app_name", self._target_value("name", ""))
            if not app_name:
                return False
            return bool(state.get(f"{str(app_name).strip().lower()}_open", False))

        if goal_type == "close_application":
            app_name = self._target_value("app_name", self._target_value("name", ""))
            if not app_name:
                return False
            return not bool(state.get(f"{str(app_name).strip().lower()}_open", False))

        if goal_type == "search":
            return bool(state.get("search_performed", False))

        criteria_func = metadata.get("achievement_criteria")
        if callable(criteria_func):
            try:
                return bool(criteria_func(state))
            except Exception:
                logger.debug("Falló el criterio de logro del objetivo %s.", self.id, exc_info=True)
                return False

        target_state = metadata.get("target_state")
        if isinstance(target_state, dict):
            return all(state.get(key) == value for key, value in target_state.items())

        return False

    def get_required_capabilities(self) -> List[str]:
        """Obtiene capacidades necesarias para el objetivo preservando el orden."""
        capabilities: List[str] = []

        default_capabilities = {
            "navigate": ["open_application", "navigate", "focus_element", "type_text", "press_key"],
            "open_application": ["open_application", "activate_window"],
            "close_application": ["close_application", "activate_window"],
            "search": ["open_application", "navigate", "focus_element", "type_text", "press_key"],
            "navigate_stream": ["open_application", "navigate", "focus_element", "type_text", "press_key"],
            "navigate_to_entity": ["open_application", "navigate"],
        }
        goal_type = self.type.value if isinstance(self.type, Enum) else str(self.type)
        capabilities.extend(default_capabilities.get(goal_type, []))
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        required = metadata.get("required_capabilities", [])
        if isinstance(required, str):
            required = [required]
        elif not isinstance(required, (list, tuple, set)):
            required = []
        capabilities.extend(str(item) for item in required if item is not None and str(item).strip())

        return list(dict.fromkeys(capabilities))

    def estimate_cost(self, current_state: Dict[str, Any]) -> float:
        """Estima el coste restante del objetivo."""
        metadata = self.metadata or {}
        base_cost = max(0.0, _safe_float(metadata.get("base_cost", 10.0), 10.0))
        state = current_state if isinstance(current_state, dict) else {}

        if self.is_achieved(state):
            return 0.0

        if self.type == "open_application":
            app_name = self._target_value("app_name", self._target_value("name", ""))
            if state.get(f"{str(app_name).lower()}_open", False):
                return min(2.0, base_cost)

        if self.type == "close_application":
            app_name = self._target_value("app_name", self._target_value("name", ""))
            if not state.get(f"{str(app_name).lower()}_open", False):
                return 0.0

        complexity_factor = max(0.0, _safe_float(metadata.get("complexity", 1.0), 1.0))
        return base_cost * complexity_factor

    def is_expired(self) -> bool:
        """Indica si se ha superado el deadline válido del objetivo."""
        return self.deadline is not None and time.time() > _safe_float(self.deadline, float("inf"))

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el objetivo a un diccionario serializable."""
        return {
            "id": self.id,
            "type": self.type,
            "target": _serialize_value(self.target),
            "description": self.description,
            "priority": self.priority,
            "deadline": self.deadline,
            "constraints": list(self.constraints),
            "nodes": list(self.nodes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": _serialize_value(self.metadata) if self.metadata else {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        """Reconstruye un objetivo desde un diccionario serializado."""
        if not isinstance(data, dict):
            raise TypeError("Goal.from_dict espera un diccionario.")
        normalized = dict(data)
        normalized.setdefault("metadata", {})
        normalized.setdefault("constraints", [])
        normalized.setdefault("nodes", [])
        return cls(**normalized)


@dataclass
class Task:
    """Tarea jerárquica descomponible en otras tareas o nodos."""

    id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    nodes: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status.strip().lower())
        elif not isinstance(self.status, TaskStatus):
            self.status = TaskStatus.PENDING

        for field_name in ("nodes", "children", "dependencies"):
            value = getattr(self, field_name)
            if value is None:
                setattr(self, field_name, [])
            elif isinstance(value, list):
                continue
            elif isinstance(value, (tuple, set, frozenset)):
                setattr(self, field_name, list(value))
            else:
                setattr(self, field_name, [str(value)])

        self.created_at = _safe_float(self.created_at, time.time())
        if self.started_at is not None:
            self.started_at = _safe_float(self.started_at, 0.0) or None
        if self.completed_at is not None:
            self.completed_at = _safe_float(self.completed_at, 0.0) or None

    def _dependency_satisfied(
        self,
        dependency_id: str,
        all_nodes: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> bool:
        """Comprueba una dependencia usando la semántica disponible en el modelo."""
        if not isinstance(all_nodes, dict):
            return False
        dependency = all_nodes.get(dependency_id)
        if dependency is None:
            return False

        if isinstance(dependency, Task):
            return dependency.status == TaskStatus.COMPLETED
        if isinstance(dependency, Node):
            return dependency.can_execute(current_state)
        return False

    def can_execute(self, current_state: Dict[str, Any], all_nodes: Dict[str, Any]) -> bool:
        """Verifica dependencias y disponibilidad de hijos, evitando ciclos jerárquicos."""
        state = current_state if isinstance(current_state, dict) else {}
        nodes = all_nodes if isinstance(all_nodes, dict) else {}

        def _can_execute(task: "Task", active_path: Set[str]) -> bool:
            if task.id in active_path:
                logger.warning("Ciclo detectado en la jerarquía de tareas: %s.", task.id)
                return False

            if any(
                not task._dependency_satisfied(dependency_id, nodes, state)
                for dependency_id in task.dependencies
            ):
                return False

            if not task.children:
                return True

            next_path = set(active_path)
            next_path.add(task.id)
            for child_id in task.children:
                child = nodes.get(child_id)
                if isinstance(child, Node) and child.can_execute(state):
                    return True
                if isinstance(child, Task) and _can_execute(child, next_path):
                    return True
            return False

        return _can_execute(self, set())

    def decompose_task(self, all_nodes: Dict[str, Any]) -> List[str]:
        """Descompone recursivamente la tarea en hojas sin quedar atrapada en ciclos."""
        nodes = all_nodes if isinstance(all_nodes, dict) else {}

        def _decompose(task: "Task", active_path: Set[str]) -> List[str]:
            if task.id in active_path:
                logger.warning("Ciclo detectado al descomponer la tarea %s; se omite la rama.", task.id)
                return []
            if not task.children:
                return [task.id]

            next_path = set(active_path)
            next_path.add(task.id)
            decomposition: List[str] = []
            for child_id in task.children:
                child = nodes.get(child_id)
                if isinstance(child, Task):
                    decomposition.extend(_decompose(child, next_path))
                elif isinstance(child, Node):
                    decomposition.append(child_id)
            return decomposition

        return _decompose(self, set())

    def get_execution_plan(self, current_state: Dict[str, Any], all_nodes: Dict[str, Any]) -> List[str]:
        """Obtiene candidatos ejecutables en el orden declarado y sin recursión cíclica."""
        if self.status == TaskStatus.COMPLETED:
            return []

        state = current_state if isinstance(current_state, dict) else {}
        nodes = all_nodes if isinstance(all_nodes, dict) else {}

        def _build_plan(task: "Task", active_path: Set[str]) -> List[str]:
            if task.id in active_path or task.status == TaskStatus.COMPLETED:
                if task.id in active_path:
                    logger.warning("Ciclo detectado al crear el plan de la tarea %s; se omite la rama.", task.id)
                return []

            next_path = set(active_path)
            next_path.add(task.id)
            plan: List[str] = []
            for child_id in task.children:
                child = nodes.get(child_id)
                if isinstance(child, Task):
                    if child.can_execute(state, nodes):
                        plan.extend(_build_plan(child, next_path))
                elif isinstance(child, Node) and child.can_execute(state):
                    plan.append(child_id)
            return plan

        return _build_plan(self, set())

    def estimate_task_cost(self, current_state: Dict[str, Any], all_nodes: Dict[str, Any]) -> float:
        """Estima el coste de los hijos ejecutables sin contar ramas cíclicas."""
        if self.status == TaskStatus.COMPLETED:
            return 0.0

        state = current_state if isinstance(current_state, dict) else {}
        nodes = all_nodes if isinstance(all_nodes, dict) else {}

        def _estimate(task: "Task", active_path: Set[str]) -> float:
            if task.id in active_path or task.status == TaskStatus.COMPLETED:
                return 0.0

            next_path = set(active_path)
            next_path.add(task.id)
            total_cost = 0.0
            for child_id in task.children:
                child = nodes.get(child_id)
                if isinstance(child, Task):
                    total_cost += _estimate(child, next_path)
                elif isinstance(child, Node) and child.can_execute(state):
                    total_cost += max(0.0, _safe_float(child.cost, 0.0))
            return total_cost

        return _estimate(self, set())

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la tarea a un diccionario serializable."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "nodes": list(self.nodes),
            "parent": self.parent,
            "children": list(self.children),
            "dependencies": list(self.dependencies),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Reconstruye una tarea desde un diccionario serializado."""
        if not isinstance(data, dict):
            raise TypeError("Task.from_dict espera un diccionario.")
        normalized = dict(data)
        status = normalized.get("status", TaskStatus.PENDING)
        if isinstance(status, str):
            normalized["status"] = TaskStatus(status.strip().lower())
        for field_name in ("nodes", "children", "dependencies"):
            if normalized.get(field_name) is None:
                normalized[field_name] = []
        return cls(**normalized)


def create_action_node(
    id: str,
    name: str,
    application: str,
    ui_element: Optional[str] = None,
    cost: float = 1.0,
    **kwargs,
) -> Node:
    """Crea un nodo de acción reutilizable."""
    kwargs.setdefault("reusable_action", True)
    kwargs.setdefault("action_category", "basic_action")
    return Node(
        id=id,
        type=NodeType.ACTION,
        name=name,
        application=application,
        ui_element=ui_element,
        cost=cost,
        **kwargs,
    )


def create_application_node(id: str, name: str, app_name: str, **kwargs) -> Node:
    """Crea un nodo que representa una aplicación."""
    return Node(id=id, type=NodeType.APPLICATION, name=name, application=app_name, **kwargs)


def create_state_node(id: str, name: str, state_key: str, state_value: Any, **kwargs) -> Node:
    """Crea un nodo que representa un requisito de estado."""
    requirements = dict(kwargs.pop("state_requirements", {}) or {})
    requirements[state_key] = state_value
    return Node(id=id, type=NodeType.STATE, name=name, state_requirements=requirements, **kwargs)


def create_condition_node(
    id: str,
    name: str,
    condition_func: Callable[[Dict[str, Any]], bool],
    **kwargs,
) -> Node:
    """Crea un nodo de condición mediante callback."""
    functions = list(kwargs.pop("preconditions_functions", []) or [])
    functions.append(condition_func)
    return Node(id=id, type=NodeType.CONDITION, name=name, preconditions_functions=functions, **kwargs)


@dataclass
class WorldState:
    """
    Estado del mundo canónico para planificación.

    Es un contenedor deliberadamente ligero para el estado utilizado por el
    grafo y el planner; no sustituye estructuras más ricas de memoria.
    """

    state: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Asegura que el estado interno siempre sea un diccionario independiente."""
        self.state = _copy_state(self.state)

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor del estado."""
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Establece un valor evitando retener referencias mutables externas."""
        self.state[str(key)] = _copy_state({"value": value}).get("value")

    def update(self, other: Dict[str, Any]) -> None:
        """Actualiza el estado con otro estado o diccionario."""
        if isinstance(other, WorldState):
            self.state.update(_copy_state(other.state))
        elif isinstance(other, dict):
            self.state.update(_copy_state(other))

    def copy(self) -> "WorldState":
        """Devuelve una copia independiente del estado."""
        return WorldState(state=_copy_state(self.state))

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el estado a una representación serializable."""
        return {"state": _serialize_value(self.state)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        """Reconstruye el estado desde un diccionario serializado."""
        if not isinstance(data, dict):
            return cls()
        state = data.get("state", data)
        return cls(state=state if isinstance(state, dict) else {})


__all__ = [
    "NodeType",
    "TaskStatus",
    "Node",
    "Goal",
    "Task",
    "WorldState",
    "create_action_node",
    "create_application_node",
    "create_state_node",
    "create_condition_node",
]
