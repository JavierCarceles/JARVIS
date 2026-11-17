"""Gestor de descomposicion jerarquica de tareas (HTN) de JARVIS.

El modulo transforma objetivos en jerarquias de tareas, comprueba dependencias y
coordina la integracion opcional con StateGraph, Planner y TaskExecutor. La
planificacion no ejecuta acciones fisicas por si sola; la ejecucion de tareas
primitivas se delega exclusivamente a TaskExecutor.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

try:  # Compatibilidad con ejecucion como paquete y desde la raiz del proyecto.
    from src.hands.planner.node import Goal, Node, NodeType, Task, TaskStatus
    from src.hands.planner.graph import StateGraph
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.core.log import get_logger
except ImportError:  # pragma: no cover - depende de como se lance JARVIS.
    from src.hands.planner.node import Goal, Node, NodeType, Task, TaskStatus
    from src.hands.planner.graph import StateGraph
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.core.log import get_logger

logger = get_logger(__name__)


# Tarea HTN -> (accion registrada en ActionRegistry, parametro que recibe el
# objetivo del Goal). Solo tareas con accion real; las demas (navegar, activar
# ventana, resolver entidad...) se completan en FASES 4 y 14.
HTN_TASK_ACTIONS = {
    "open_application": ("open_application", "app_name"),
}


# Limite de niveles de descomposicion recursiva de Tasks compuestas (4.3.4.3).
MAX_DECOMPOSITION_DEPTH = 6


class HTNDecompositionError(Exception):
    """Descomposicion imposible con el motivo estructurado en ``details``."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = dict(details or {})
        self.details.setdefault("message", message)


class HTNStatus(Enum):
    IDLE = "idle"
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTARTING = "restarting"


class TaskDecompositionStrategy(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    ITERATIVE = "iterative"


@dataclass
class TaskExecutionResult:
    task_id: str
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    subtask_results: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    new_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HTNDecompositionRule:
    name: str
    target_type: str
    strategy: TaskDecompositionStrategy
    decomposition_pattern: List[str]
    preconditions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


class HTNManager:
    """Gestor central de reglas HTN y jerarquias de tareas."""

    def __init__(self, planner: Optional[Any] = None) -> None:
        self.planner = planner
        self.available_tasks: Dict[str, Task] = {}
        self.decomposition_rules: List[HTNDecompositionRule] = []
        # Reglas de Tasks compuestas (4.3.4.1): ``target_type`` es el
        # ``task_type`` de la Task, no el tipo de Goal. Se mantienen separadas
        # de las reglas de Goal para que una tarea con el mismo nombre que un
        # tipo de Goal (``open_application``) no se descomponga en si misma.
        self.task_decomposition_rules: List[HTNDecompositionRule] = []
        # Motivo de la ultima descomposicion fallida (4.3.2.3) y decisiones de
        # ramas condicionales de la ultima descomposicion (4.4.2.4).
        self.last_decomposition_failure: Optional[Dict[str, Any]] = None
        self.last_branch_decisions: List[Dict[str, Any]] = []
        self.execution_history: List[Dict[str, Any]] = []
        self.current_execution: Optional[Dict[str, Any]] = None

        self.status = HTNStatus.IDLE
        self.active_tasks: Set[str] = set()
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()

        self.start_time: Optional[float] = None
        self.total_execution_time = 0.0
        self.state_graph: Optional[StateGraph] = None
        self.use_graph_decomposition = True
        self.graph_decomposition_threshold = 3
        self.application_integrator: Optional[Any] = None

        try:
            self.application_integrator = get_application_knowledge_integrator()
        except Exception:
            logger.warning(
                "[HTN] Integrador de aplicaciones no disponible", exc_info=True
            )

        # False significa que la carga se intento y fallo; evita ciclos de imports.
        self._task_executor: Any = None
        self._lock = threading.RLock()
        logger.info("[HTN] Gestor de descomposicion jerarquica inicializado")

    # ------------------------------------------------------------------
    # CONFIGURACION
    # ------------------------------------------------------------------

    def initialize_decomposition_rules(self) -> None:
        rules = [
            HTNDecompositionRule(
                name="navigation_decomposition",
                target_type="navigate",
                strategy=TaskDecompositionStrategy.SEQUENTIAL,
                decomposition_pattern=["prepare_navigator", "navigate_to_target"],
                preconditions=["browser_available"],
                priority=1,
            ),
            HTNDecompositionRule(
                name="stream_opening_decomposition",
                target_type="navigate_stream",
                strategy=TaskDecompositionStrategy.SEQUENTIAL,
                decomposition_pattern=[
                    "resolve_entity",
                    "prepare_navigator",
                    "navigate_to_target",
                ],
                preconditions=["entity_available", "browser_available"],
                priority=2,
            ),
            HTNDecompositionRule(
                name="application_opening_decomposition",
                target_type="open_application",
                strategy=TaskDecompositionStrategy.SEQUENTIAL,
                decomposition_pattern=[
                    "check_availability",
                    "open_application",
                    "activate_window",
                ],
                preconditions=["application_known"],
                priority=1,
            ),
            HTNDecompositionRule(
                name="search_decomposition",
                target_type="search",
                strategy=TaskDecompositionStrategy.SEQUENTIAL,
                decomposition_pattern=[
                    "prepare_navigator",
                    "navigate_to_search_engine",
                    "perform_search",
                ],
                preconditions=["browser_available", "search_engine_known"],
                priority=1,
            ),
            HTNDecompositionRule(
                name="parallel_execution_decomposition",
                target_type="parallel_tasks",
                strategy=TaskDecompositionStrategy.PARALLEL,
                decomposition_pattern=["task_1", "task_2", "task_3"],
                preconditions=["multiple_tasks_defined"],
                priority=3,
            ),
        ]
        self.decomposition_rules = sorted(rules, key=lambda rule: rule.priority)
        logger.info("[HTN] %s reglas de descomposicion inicializadas", len(rules))

    def set_planner(self, planner: Optional[Any]) -> None:
        self.planner = planner
        logger.info("[HTN] Planner %s", "establecido" if planner is not None else "eliminado")

    def set_state_graph(self, state_graph: Optional[StateGraph]) -> None:
        self.state_graph = state_graph
        logger.info("[HTN] StateGraph %s", "establecido" if state_graph is not None else "eliminado")

    def enable_graph_decomposition(self, enabled: bool = True, threshold: int = 3) -> None:
        self.use_graph_decomposition = bool(enabled)
        try:
            self.graph_decomposition_threshold = max(1, int(threshold))
        except (TypeError, ValueError, OverflowError):
            self.graph_decomposition_threshold = 3

    # ------------------------------------------------------------------
    # ENTRADAS DE ALTO NIVEL
    # ------------------------------------------------------------------

    def decompose_and_execute(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        """Compatibilidad publica: descompone y procesa la jerarquia resultante."""
        if not self._valid_goal(goal):
            return self._failed_result("unknown", "Objetivo inv\u00e1lido")
        state = self._normalize_state(current_state)
        if not self.use_graph_decomposition or self.state_graph is None:
            return self.execute_goal_hierarchy(goal, state)
        return self._decompose_and_execute_with_graph(goal, state)

    def _decompose_and_execute_with_graph(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        previous_status = self.status
        htn_tasks: List[Task] = []
        try:
            htn_tasks = self.decompose_goal(goal, current_state)
            if not htn_tasks:
                return self._execute_with_graph_only(goal, current_state)

            ordered = self._order_tasks_by_dependencies(htn_tasks)
            dependency_error = self._validate_task_dependencies(ordered)
            if dependency_error:
                return self._failed_result(goal.id, dependency_error, state=current_state)

            if len(ordered) <= self.graph_decomposition_threshold:
                return self._execute_task_hierarchy(ordered, dict(current_state))
            return self._decompose_with_graph_advanced(goal, ordered, current_state)
        except Exception as exc:
            logger.exception("[HTN] Error en descomposicion con grafo")
            if htn_tasks:
                return self._execute_task_hierarchy(htn_tasks, dict(current_state))
            return self._failed_result(goal.id, str(exc), state=current_state)
        finally:
            if self.status == HTNStatus.DECOMPOSING:
                self.status = previous_status if previous_status != HTNStatus.DECOMPOSING else HTNStatus.IDLE

    def _decompose_with_graph_advanced(
        self, goal: Goal, htn_tasks: List[Task], current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        """Usa las dependencias para ordenar tareas y delega ejecucion a TaskExecutor.

        La integracion grafica no sustituye la jerarquia HTN por una ruta no
        relacionada ni considera que una simple respuesta del Planner sea ejecucion.
        """
        ordered_tasks = self._order_tasks_by_dependencies(htn_tasks)
        error = self._validate_task_dependencies(ordered_tasks)
        if error:
            return self._failed_result(goal.id, error, state=current_state)
        execution_plan = self._convert_tasks_to_execution_plan(ordered_tasks, goal)
        result = self._execute_task_hierarchy(ordered_tasks, dict(current_state or {}))
        if isinstance(result.result, dict):
            result.result.setdefault("htn_execution_plan", execution_plan)
            result.result.setdefault("graph_integration", self.state_graph is not None)
        return result

    def _convert_htn_tasks_to_graph_nodes(
        self, htn_tasks: List[Task], goal: Goal
    ) -> List[Node]:
        """Convierte tareas HTN en nodos y mantiene las dependencias internas."""
        valid_ids = {str(getattr(task, "id", "")) for task in htn_tasks}
        id_map = {task_id: f"htn_{task_id}" for task_id in valid_ids if task_id}
        graph_nodes: List[Node] = []
        for task in htn_tasks:
            task_id = str(getattr(task, "id", ""))
            if not task_id:
                continue
            dependencies = [
                id_map[dependency]
                for dependency in (getattr(task, "dependencies", []) or [])
                if dependency in id_map
            ]
            graph_nodes.append(
                Node(
                    id=id_map[task_id],
                    type=NodeType.ACTION,
                    name=str(getattr(task, "name", task_id)),
                    description=str(getattr(task, "description", "")),
                    cost=self._estimate_task_cost(task),
                    dependencies=dependencies,
                    metadata={
                        "task_id": task_id,
                        "goal_id": getattr(goal, "id", None),
                        "task_type": "htn_decomposed",
                    },
                )
            )
        return graph_nodes

    def _optimize_task_sequence_with_graph(
        self, graph_tasks: List[Node], current_state: Dict[str, Any], goal: Goal
    ) -> List[str]:
        del current_state, goal
        pending = list(graph_tasks)
        known_ids = {str(node.id) for node in pending}
        resolved: Set[str] = set()
        ordered: List[str] = []

        # Las dependencias externas no pueden satisfacerse con la lista recibida.
        while pending:
            ready = [
                task for task in pending
                if set(task.dependencies or []).issubset(resolved)
                and not (set(task.dependencies or []) - known_ids - resolved)
            ]
            if not ready:
                logger.warning("[HTN] Dependencias ciclicas o sin resolver en nodos HTN")
                break
            for task in ready:
                ordered.append(task.id)
                resolved.add(task.id)
                pending.remove(task)
        return ordered

    def _convert_graph_sequence_to_execution_plan(
        self, graph_sequence: List[str], goal: Goal
    ) -> List[Dict[str, Any]]:
        if self.state_graph is None:
            return []
        plan: List[Dict[str, Any]] = []
        for node_id in graph_sequence:
            try:
                node = self.state_graph.get_node(node_id)
            except Exception:
                node = None
            if node is None or getattr(node, "type", None) not in (NodeType.ACTION, NodeType.TASK):
                continue
            plan.append(self._node_to_execution_dict(node, goal))
        return plan

    def _node_to_execution_dict(self, node: Node, goal: Goal) -> Dict[str, Any]:
        node_type = getattr(node, "type", NodeType.ACTION)
        return {
            "id": str(getattr(node, "id", "")),
            "name": str(getattr(node, "name", "")),
            "description": str(getattr(node, "description", "")),
            "type": getattr(node_type, "value", str(node_type)),
            "cost": self._safe_cost(getattr(node, "cost", 1.0)),
            "application": getattr(node, "application", None),
            "ui_element": getattr(node, "ui_element", None),
            "parameters": self._as_dict(getattr(node, "parameters", {})),
            "preconditions": self._as_list(getattr(node, "preconditions", [])),
            "effects": self._as_list(getattr(node, "effects", [])),
            "metadata": {
                **self._as_dict(getattr(node, "metadata", {})),
                "goal_id": getattr(goal, "id", None),
            },
        }

    def _convert_tasks_to_execution_plan(
        self, tasks: List[Task], goal: Goal
    ) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        for task in tasks:
            metadata = self._as_dict(getattr(task, "metadata", {}))
            metadata.update({"task_id": task.id, "goal_id": goal.id})
            plan.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "type": NodeType.TASK.value,
                    "cost": self._estimate_task_cost(task),
                    "parameters": self._as_dict(getattr(task, "parameters", {})),
                    "application": getattr(task, "application", None),
                    "dependencies": list(getattr(task, "dependencies", []) or []),
                    "preconditions": self._as_list(getattr(task, "preconditions", [])),
                    "effects": self._as_list(getattr(task, "effects", [])),
                    "metadata": metadata,
                }
            )
        return plan

    def _execute_optimized_plan(
        self,
        execution_plan: List[Dict[str, Any]],
        current_state: Dict[str, Any],
        goal: Goal,
    ) -> TaskExecutionResult:
        """Consulta al Planner cuando no hay tareas concretas que ejecutar.

        Un resultado de planificacion se etiqueta como ``planned_only``. El
        TaskExecutor es el unico responsable de ejecutar acciones fisicas.
        """
        if self.planner is None:
            return self._execute_plan_directly(execution_plan, current_state, goal)
        try:
            planning_result = self._call_planner(goal, current_state)
            if planning_result is None:
                return self._failed_result(goal.id, "El Planner no devolvi\u00f3 resultado", current_state)
            if isinstance(planning_result, list):
                return TaskExecutionResult(
                    task_id=goal.id,
                    status=TaskStatus.COMPLETED,
                    result={"plan": planning_result, "planned_only": True},
                    new_state=dict(current_state),
                )

            status = self._status_value(getattr(planning_result, "status", None))
            if status in {"completed", "success", "successful"}:
                plan = getattr(planning_result, "plan", execution_plan)
                return TaskExecutionResult(
                    task_id=goal.id,
                    status=TaskStatus.COMPLETED,
                    result={
                        "plan": copy.deepcopy(plan) if isinstance(plan, list) else execution_plan,
                        "execution_time": self._safe_cost(getattr(planning_result, "execution_time", 0.0)),
                        "planned_only": True,
                    },
                    execution_time=self._safe_cost(getattr(planning_result, "execution_time", 0.0)),
                    new_state=dict(current_state),
                )
            warning = getattr(planning_result, "warnings", None)
            return self._failed_result(
                goal.id, f"Planificaci\u00f3n fallida: {warning or status or 'estado desconocido'}", current_state
            )
        except Exception as exc:
            logger.exception("[HTN] Fallo la integracion con Planner")
            return self._failed_result(goal.id, str(exc), current_state)

    def _call_planner(self, goal: Goal, current_state: Dict[str, Any]) -> Any:
        plan_method = getattr(self.planner, "plan", None)
        if not callable(plan_method):
            raise AttributeError("El objeto Planner no dispone de plan()")
        # La firma canonica es plan(goal, current_state). No se reintenta con
        # otra firma al capturar TypeError interno, para no ocultar bugs del Planner.
        return plan_method(goal, current_state)

    def _execute_with_graph_only(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        if self.planner is not None:
            return self._execute_optimized_plan([], current_state, goal)
        return self._failed_result(goal.id, "No hay Planner ni tareas HTN ejecutables", current_state)

    def _estimate_task_cost(self, task: Task) -> float:
        metadata = self._as_dict(getattr(task, "metadata", {}))
        explicit = getattr(task, "cost", None)
        if explicit is None:
            explicit = metadata.get("cost", metadata.get("estimated_cost"))
        if explicit is not None:
            try:
                numeric = float(explicit)
                if math.isfinite(numeric) and numeric >= 0:
                    return numeric
            except (TypeError, ValueError, OverflowError):
                pass
        name = str(getattr(task, "name", "")).lower()
        base = 1.0
        if "prepare" in name:
            base = 2.0
        elif "navigate" in name:
            base = 3.0
        elif "search" in name:
            base = 2.5
        elif "check" in name or "validate" in name:
            base = 1.5
        description_length = len(str(getattr(task, "description", "")))
        return base + description_length * 0.01

    def _execute_plan_directly(
        self,
        execution_plan: List[Dict[str, Any]],
        current_state: Dict[str, Any],
        goal: Goal,
    ) -> TaskExecutionResult:
        """Fallback de planificacion que no ejecuta ni simula acciones."""
        state = dict(current_state or {})
        planned = [
            {"id": item.get("id"), "status": "planned", "cost": item.get("cost", 0.0)}
            for item in execution_plan
        ]
        return TaskExecutionResult(
            task_id=goal.id,
            status=TaskStatus.COMPLETED,
            result={"plan": copy.deepcopy(execution_plan), "final_state": state, "planned_only": True},
            subtask_results=planned,
            new_state=state,
        )

    # ------------------------------------------------------------------
    # BIBLIOTECA Y DESCOMPOSICION
    # ------------------------------------------------------------------

    def load_task_library(self) -> None:
        tasks = [
            Task("prepare_navigator", "Preparar navegador", "Prepara el navegador"),
            Task("navigate_to_target", "Navegar al destino", "Navega a la URL objetivo"),
            Task("navigate_to_search_engine", "Navegar al motor de b\u00fasqueda", "Navega al motor de b\u00fasqueda"),
            Task("perform_search", "Realizar b\u00fasqueda", "Realiza una b\u00fasqueda"),
            Task("check_availability", "Verificar disponibilidad", "Verifica disponibilidad"),
            Task("open_application", "Abrir aplicaci\u00f3n", "Abre la aplicaci\u00f3n"),
            Task("activate_window", "Activar ventana", "Activa la ventana"),
            Task("resolve_entity", "Resolver entidad", "Resuelve la entidad"),
        ]
        self.available_tasks = {task.id: task for task in tasks}
        logger.info("[HTN] Biblioteca de tareas cargada: %s tareas", len(tasks))

    def add_task_decomposition_rule(self, rule: HTNDecompositionRule) -> None:
        """Registra un metodo para una Task compuesta (``rule.target_type`` = task_type)."""
        self.task_decomposition_rules.append(rule)
        self.task_decomposition_rules.sort(key=lambda item: item.priority)

    def decompose_goal(self, goal: Goal, current_state: Dict[str, Any]) -> List[Task]:
        """
        Descompone el Goal hasta Tasks hoja.

        Devuelve la lista de Tasks (raiz incluida) o ``[]``; en ese caso el
        motivo queda en ``self.last_decomposition_failure`` (4.3.2.3) con
        ``reason`` = ``invalid_goal`` | ``no_rule_for_type`` |
        ``preconditions_unmet`` | ``no_branch_applicable`` |
        ``compound_task_without_method`` | ``decomposition_cycle`` |
        ``max_depth_exceeded`` | ``invalid_dependencies`` | ``error``.
        """
        self.last_decomposition_failure = None
        self.last_branch_decisions = []
        if not self._valid_goal(goal):
            logger.warning("[HTN] No se puede descomponer un objetivo invalido")
            self.last_decomposition_failure = {
                "reason": "invalid_goal",
                "message": "Objetivo inv\u00e1lido o sin id",
            }
            return []
        prior_status = self.status
        self.status = HTNStatus.DECOMPOSING
        started = time.perf_counter()
        state = self._normalize_state(current_state)
        try:
            if not self.decomposition_rules:
                self.initialize_decomposition_rules()
            if not self.available_tasks:
                self.load_task_library()
            selection = self.explain_method_selection(goal, state)
            rule = selection.get("rule")
            if rule is None:
                details = {k: v for k, v in selection.items() if k != "rule"}
                self.last_decomposition_failure = details
                logger.info("[HTN] Sin metodo para %s: %s", goal.id, details.get("message"))
                return []
            tasks = self._instantiate_rule(goal, rule, state)
            tasks = self._expand_compound_tasks(goal, tasks, state)
            tasks = self._establish_hierarchy(tasks, goal)
            dependency_error = self._validate_task_dependencies(tasks)
            if dependency_error:
                logger.warning("[HTN] Descomposicion invalida: %s", dependency_error)
                self.last_decomposition_failure = {
                    "reason": "invalid_dependencies",
                    "rule": rule.name,
                    "message": dependency_error,
                }
                return []
            return tasks
        except HTNDecompositionError as exc:
            logger.warning("[HTN] Descomposicion de %s detenida: %s", goal.id, exc)
            self.last_decomposition_failure = dict(exc.details)
            return []
        except Exception as exc:
            logger.exception("[HTN] Error al descomponer objetivo %s", getattr(goal, "id", None))
            self.last_decomposition_failure = {"reason": "error", "message": str(exc)}
            return []
        finally:
            self.status = prior_status if prior_status != HTNStatus.DECOMPOSING else HTNStatus.IDLE
            logger.debug("[HTN] Descomposicion en %.4fs", time.perf_counter() - started)

    def explain_method_selection(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Seleccion de metodo HTN (4.3.2.1-4.3.2.2).

        Un metodo (regla) es aplicable si ``rule.target_type`` coincide con el
        tipo del Goal (o es ``generic``) y TODAS sus precondiciones se cumplen
        en el estado real recibido. Entre los aplicables gana el de menor
        ``priority``. Devuelve ``{"rule": regla}`` o ``{"rule": None, "reason":
        ..., "goal_type": ..., "rules_evaluated": [{"rule", "unmet_preconditions"}],
        "message": ...}``.
        """
        if not self.decomposition_rules:
            self.initialize_decomposition_rules()
        return self._select_rule(
            self.decomposition_rules, self._goal_type(goal), current_state, allow_generic=True
        )

    def _select_rule(
        self,
        rules: List[HTNDecompositionRule],
        type_name: str,
        current_state: Dict[str, Any],
        allow_generic: bool = False,
    ) -> Dict[str, Any]:
        state = self._normalize_state(current_state)
        matches = [rule for rule in rules if rule.target_type == type_name]
        if allow_generic:
            matches.extend(rule for rule in rules if rule.target_type == "generic")
        if not matches:
            return {
                "rule": None,
                "reason": "no_rule_for_type",
                "goal_type": type_name,
                "rules_evaluated": [],
                "message": f"No hay regla HTN para el tipo '{type_name}'",
            }
        evaluated: List[Dict[str, Any]] = []
        for rule in sorted(matches, key=lambda item: item.priority):
            unmet = self._unmet_preconditions(rule, state)
            if not unmet:
                return {"rule": rule, "goal_type": type_name, "rules_evaluated": evaluated}
            evaluated.append({"rule": rule.name, "unmet_preconditions": unmet})
        detail = "; ".join(
            "%s: %s" % (item["rule"], ", ".join(item["unmet_preconditions"])) for item in evaluated
        )
        return {
            "rule": None,
            "reason": "preconditions_unmet",
            "goal_type": type_name,
            "rules_evaluated": evaluated,
            "message": f"Precondiciones no cumplidas para '{type_name}' ({detail})",
        }

    def _instantiate_rule(
        self, goal: Goal, rule: HTNDecompositionRule, state: Dict[str, Any]
    ) -> List[Task]:
        if rule.strategy == TaskDecompositionStrategy.SEQUENTIAL:
            return self._decompose_sequential(goal, rule)
        if rule.strategy == TaskDecompositionStrategy.PARALLEL:
            return self._decompose_parallel(goal, rule)
        if rule.strategy == TaskDecompositionStrategy.CONDITIONAL:
            return self._decompose_conditional(goal, rule, state)
        return self._decompose_iterative(goal, rule)

    # ------------------------------------------------------------------
    # DESCOMPOSICION RECURSIVA (4.3.4)
    # ------------------------------------------------------------------

    def _is_compound_task_type(self, task_type: Optional[str]) -> bool:
        """4.3.4.1: una Task es compuesta si existe al menos un metodo para su tipo."""
        if not task_type:
            return False
        return any(rule.target_type == task_type for rule in self.task_decomposition_rules)

    def _expand_compound_tasks(
        self, goal: Goal, tasks: List[Task], state: Dict[str, Any]
    ) -> List[Task]:
        """
        Expande cada Task compuesta un nivel cada vez (4.3.4.2) hasta que solo
        queden hojas (4.3.4.3). Un ``task_type`` que reaparece en su propia
        cadena de ancestros es un ciclo y la profundidad esta limitada por
        ``MAX_DECOMPOSITION_DEPTH`` (4.3.4.4). Las dependencias sobre una Task
        compuesta se trasladan a sus hojas: los contenedores no se ejecutan.
        """
        if not self.task_decomposition_rules:
            return tasks
        output: List[Task] = []

        def _expand(task: Task, depth: int, path: Tuple[str, ...]) -> None:
            output.append(task)
            metadata = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
            task_type = metadata.get("task_type")
            if task.status == TaskStatus.SKIPPED or not self._is_compound_task_type(task_type):
                return
            if task_type in path:
                raise HTNDecompositionError(
                    "Ciclo de descomposicion: %s" % " -> ".join(path + (task_type,)),
                    {"reason": "decomposition_cycle", "task_id": task.id,
                     "cycle": list(path + (task_type,))},
                )
            if depth >= MAX_DECOMPOSITION_DEPTH:
                raise HTNDecompositionError(
                    "Profundidad maxima de descomposicion (%s) superada en %s"
                    % (MAX_DECOMPOSITION_DEPTH, task.id),
                    {"reason": "max_depth_exceeded", "task_id": task.id,
                     "max_depth": MAX_DECOMPOSITION_DEPTH, "path": list(path + (task_type,))},
                )
            selection = self._select_rule(self.task_decomposition_rules, task_type, state)
            rule = selection.get("rule")
            if rule is None:
                details = {k: v for k, v in selection.items() if k != "rule"}
                details["reason"] = "compound_task_without_method"
                details["task_id"] = task.id
                raise HTNDecompositionError(
                    "Task compuesta %s sin metodo aplicable: %s"
                    % (task.id, selection.get("message")),
                    details,
                )
            children = self._instantiate_rule(goal, rule, state)
            children = self._reparent_subtasks(goal, task, children)
            # Una Task compuesta es un contenedor: nunca se despacha a una accion.
            metadata.pop("action", None)
            metadata.pop("action_unmapped", None)
            metadata["compound"] = True
            metadata["decomposition_rule"] = rule.name
            task.metadata = metadata
            task.children = [child.id for child in children if child.parent == task.id]
            for child in children:
                _expand(child, depth + 1, path + (task_type,))

        for task in tasks:
            _expand(task, 0, ())

        # Las dependencias sobre un contenedor pasan a sus hojas no omitidas.
        by_id = {task.id: task for task in output}

        def _leaves(task_id: str, seen: Set[str]) -> List[str]:
            task = by_id.get(task_id)
            if task is None or task_id in seen:
                return []
            seen.add(task_id)
            if not task.children:
                return [] if task.status == TaskStatus.SKIPPED else [task_id]
            leaves: List[str] = []
            for child_id in task.children:
                leaves.extend(_leaves(child_id, seen))
            return leaves

        def _ancestor_ids(task: Task) -> Set[str]:
            found: Set[str] = set()
            parent_id = task.parent
            while parent_id in by_id and parent_id not in found:
                found.add(parent_id)
                parent_id = by_id[parent_id].parent
            return found

        for task in output:
            rewritten: List[str] = []
            ancestors = _ancestor_ids(task)
            for dep in task.dependencies or []:
                dep_task = by_id.get(dep)
                # La dependencia sobre un ancestro (p. ej. el bucle iterativo)
                # se conserva: es un contenedor y no bloquea la ejecucion.
                if dep in ancestors or dep_task is None or not dep_task.children:
                    targets = [dep]
                else:
                    targets = _leaves(dep, set())
                for item in targets:
                    if item not in rewritten and item != task.id:
                        rewritten.append(item)
            task.dependencies = rewritten
        return output

    @staticmethod
    def _reparent_subtasks(goal: Goal, parent: Task, subtasks: List[Task]) -> List[Task]:
        """
        Renombra las Tasks creadas por un metodo de Task compuesta para que sus
        IDs sean unicos bajo ``parent`` y cuelguen de el. Las que no dependen de
        otra del mismo metodo heredan las dependencias del padre.
        """
        prefix = f"{goal.id}_"
        mapping: Dict[str, str] = {}
        for task in subtasks:
            local = task.id[len(prefix):] if task.id.startswith(prefix) else task.id
            mapping[task.id] = f"{parent.id}__{local}"
        for task in subtasks:
            task.id = mapping[task.id]
            if task.parent in mapping:
                task.parent = mapping[task.parent]
            else:
                task.parent = parent.id
            internal = [mapping[dep] for dep in (task.dependencies or []) if dep in mapping]
            external = [dep for dep in (task.dependencies or []) if dep not in mapping]
            if not internal and task.parent == parent.id:
                external = list(dict.fromkeys(external + list(parent.dependencies or [])))
            task.dependencies = internal + external
        by_new_id = {task.id: task for task in subtasks}
        for task in subtasks:
            container = by_new_id.get(task.parent)
            if container is not None and task.id not in container.children:
                container.children.append(task.id)
        return subtasks

    def execute_goal_hierarchy(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        tasks: Optional[List[Task]] = None,
    ) -> TaskExecutionResult:
        """
        Ejecuta la jerarquia del Goal. ``tasks`` permite ejecutar una
        descomposicion ya hecha (la de ``decompose_goal``) para no descomponer
        dos veces ni ejecutar Tasks distintas de las devueltas al llamador.
        """
        if not self._valid_goal(goal):
            return self._failed_result("unknown", "Objetivo inv\u00e1lido", current_state)

        state = self._normalize_state(current_state)
        with self._lock:
            self.status = HTNStatus.EXECUTING
            self.start_time = time.perf_counter()
            self.active_tasks.clear()
            self.completed_tasks.clear()
            self.failed_tasks.clear()
        started = self.start_time
        try:
            if not tasks:
                tasks = self.decompose_goal(goal, state)
            if not tasks:
                failure = dict(self.last_decomposition_failure or {})
                message = "No se pudo descomponer el objetivo"
                if failure.get("message"):
                    message = f"{message}: {failure['message']}"
                result = self._failed_result(goal.id, message, state)
                result.result = {"decomposition_failure": failure}
                if callable(getattr(goal, "record_result", None)):
                    goal.record_result(False, error=message)
                self.status = HTNStatus.FAILED
                self._record_execution(goal, [], result, time.perf_counter() - started)
                return result

            if callable(getattr(goal, "mark_executing", None)):
                goal.mark_executing()
            branch_decisions = list(self.last_branch_decisions)
            result = self._execute_task_hierarchy(tasks, dict(state))
            if branch_decisions:
                if not isinstance(result.result, dict):
                    result.result = {}
                result.result.setdefault("branch_decisions", branch_decisions)
            elapsed = time.perf_counter() - started
            self.total_execution_time += elapsed
            self.status = HTNStatus.COMPLETED if result.status == TaskStatus.COMPLETED else HTNStatus.FAILED
            # Propagar el resultado al Goal (4.2.3.3 / 4.3.5).
            if callable(getattr(goal, "record_result", None)):
                payload = result.result if isinstance(result.result, dict) else {}
                goal.record_result(
                    result.status == TaskStatus.COMPLETED,
                    failed_task_id=payload.get("failed_task_id"),
                    error=result.error_message,
                    aborted=bool(payload.get("aborted")),
                )
            self._record_execution(goal, tasks, result, elapsed)
            return result
        except Exception as exc:
            self.status = HTNStatus.FAILED
            logger.exception("[HTN] Fallo la jerarquia del objetivo %s", goal.id)
            result = self._failed_result(goal.id, str(exc), state)
            self._record_execution(goal, [], result, time.perf_counter() - started)
            return result
        finally:
            if self.status not in (HTNStatus.COMPLETED, HTNStatus.FAILED):
                self.status = HTNStatus.IDLE

    def _find_decomposition_rule(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> Optional[HTNDecompositionRule]:
        return self.explain_method_selection(goal, current_state).get("rule")

    def _application_catalog_available(self) -> bool:
        try:
            manager = getattr(self.application_integrator, "application_manager", None)
            applications = getattr(manager, "applications", None)
            return bool(applications)
        except Exception:
            return False

    def _check_preconditions(
        self, rule: HTNDecompositionRule, current_state: Dict[str, Any]
    ) -> bool:
        return not self._unmet_preconditions(rule, current_state)

    def _condition_holds(self, condition: str, state: Dict[str, Any]) -> bool:
        """Evalua una precondicion contra el estado real (4.3.2.2 / 4.4.2.1)."""
        special = {
            "browser_available": lambda: self._browser_available(state),
            "entity_available": lambda: self._entity_available(state),
            "application_known": lambda: bool(state.get("applications_known", False))
            or self._application_catalog_available(),
            "search_engine_known": lambda: bool(state.get("search_engine_known", True)),
            "multiple_tasks_defined": lambda: bool(state.get("multiple_tasks_defined", False)),
        }
        text = str(condition or "").strip()
        negated = text.startswith("not ")
        if negated:
            text = text[4:].strip()
        if text in special:
            value = bool(special[text]())
        elif "==" in text:
            key, expected = (part.strip() for part in text.split("==", 1))
            value = str(state.get(key)) == expected if key in state else False
        else:
            value = self._evaluate_precondition(text, state)
        return not value if negated else value

    def _unmet_preconditions(
        self, rule: HTNDecompositionRule, current_state: Dict[str, Any]
    ) -> List[str]:
        state = self._normalize_state(current_state)
        return [
            str(precondition)
            for precondition in rule.preconditions
            if not self._condition_holds(precondition, state)
        ]

    @staticmethod
    def _browser_available(state: Dict[str, Any]) -> bool:
        explicit = state.get("browser_available")
        if explicit is not None:
            return bool(explicit)
        keys = (
            "chrome_available", "edge_available", "firefox_available",
            "chrome_open", "edge_open", "firefox_open", "browser_ready",
        )
        if any(bool(state.get(key, False)) for key in keys):
            return True
        applications = state.get("applications")
        if isinstance(applications, dict):
            for name, info in applications.items():
                normalized = str(name).lower()
                if any(browser in normalized for browser in ("chrome", "edge", "firefox")):
                    if not isinstance(info, dict) or info.get("available", info.get("open", True)):
                        return True
        return False

    @staticmethod
    def _entity_available(state: Dict[str, Any]) -> bool:
        explicit = state.get("entities_available")
        if explicit is not None:
            return bool(explicit)
        for key in ("entities", "domain_entities", "resolved_entities"):
            value = state.get(key)
            if isinstance(value, (list, tuple, set, dict)) and value:
                return True
        return bool(state.get("entity_resolved", False))

    def _task_from_pattern(self, goal: Goal, pattern_id: str, parent: Optional[str]) -> Task:
        template = self.available_tasks.get(pattern_id)
        safe_goal_id = str(goal.id)
        task = Task(
            id=f"{safe_goal_id}_{pattern_id}",
            name=str(getattr(template, "name", f"Tarea: {pattern_id}")),
            description=str(getattr(template, "description", f"Tarea din\u00e1mica para {pattern_id}")),
            status=TaskStatus.PENDING,
            parent=parent,
            dependencies=list(getattr(template, "dependencies", []) or []),
        )
        metadata = self._as_dict(getattr(template, "metadata", {}))
        metadata.update({"task_type": pattern_id, "goal_id": safe_goal_id})
        # Las restricciones del Goal acompanan a cada tarea (4.3.3.4).
        goal_constraints = [
            str(item) for item in (getattr(goal, "constraints", None) or []) if str(item).strip()
        ]
        if goal_constraints:
            metadata["constraints"] = list(dict.fromkeys(
                list(metadata.get("constraints", []) or []) + goal_constraints
            ))
        # Enlace con una accion REAL del ActionRegistry: TaskExecutor resuelve la
        # accion por metadata["action"]. Solo se enlazan tareas con accion
        # registrada; el resto queda marcado y falla de forma explicita.
        if not metadata.get("action"):
            mapping = HTN_TASK_ACTIONS.get(pattern_id)
            target = getattr(goal, "target", None)
            if mapping and isinstance(target, str) and target.strip():
                action_name, parameter_name = mapping
                metadata["action"] = action_name
                parameters = self._as_dict(metadata.get("parameters", {}))
                parameters.setdefault(parameter_name, target.strip())
                metadata["parameters"] = parameters
            elif mapping is None:
                metadata["action_unmapped"] = (
                    "sin accion registrada para la tarea HTN %s" % pattern_id
                )
        # Task del modelo canonico no declara metadata/parameters, se anexan de
        # forma compatible para conservar datos auxiliares de las integraciones.
        try:
            task.metadata = metadata
        except Exception:
            pass
        return task

    def _decompose_sequential(self, goal: Goal, rule: HTNDecompositionRule) -> List[Task]:
        tasks: List[Task] = []
        previous: Optional[str] = None
        for pattern_id in rule.decomposition_pattern:
            # Las tareas secuenciales son hermanas bajo el objetivo raiz; el
            # orden se expresa mediante dependencies, no como relacion padre-hijo.
            task = self._task_from_pattern(goal, pattern_id, goal.id)
            if previous is not None and previous not in task.dependencies:
                task.dependencies.append(previous)
            tasks.append(task)
            previous = task.id
        return tasks

    def _decompose_parallel(self, goal: Goal, rule: HTNDecompositionRule) -> List[Task]:
        return [self._task_from_pattern(goal, pattern_id, goal.id) for pattern_id in rule.decomposition_pattern]

    def _decompose_conditional(
        self, goal: Goal, rule: HTNDecompositionRule, current_state: Dict[str, Any]
    ) -> List[Task]:
        """
        Ramas condicionales (4.4.2).

        Con ``rule.metadata["branches"]`` = ``[{"name", "condition", "pattern"}]``
        se evalua cada condicion en orden contra el estado real (4.4.2.1) y se
        elige SOLO la primera que se cumple (4.4.2.2); una rama sin
        ``condition`` es la rama por defecto. Las Tasks de las ramas no elegidas
        se crean en estado ``SKIPPED`` para que nunca se ejecuten (4.4.2.3) y la
        decision queda en ``self.last_branch_decisions`` y en la metadata de
        cada Task (4.4.2.4). Sin ``branches`` se conserva el comportamiento
        anterior (``enable_<tarea>`` en el estado).
        """
        branches = rule.metadata.get("branches") if isinstance(rule.metadata, dict) else None
        if not branches:
            return [
                self._task_from_pattern(goal, pattern_id, goal.id)
                for pattern_id in rule.decomposition_pattern
                if current_state.get(f"enable_{pattern_id}", True)
            ]
        evaluations: List[Dict[str, Any]] = []
        chosen: Optional[int] = None
        for index, branch in enumerate(branches):
            branch = branch if isinstance(branch, dict) else {}
            condition = branch.get("condition")
            holds = True if condition in (None, "") else self._condition_holds(str(condition), current_state)
            evaluations.append({
                "branch": str(branch.get("name") or f"branch_{index}"),
                "condition": condition,
                "holds": holds,
            })
            if holds and chosen is None:
                chosen = index
        decision = {
            "rule": rule.name,
            "goal_id": goal.id,
            "chosen_branch": evaluations[chosen]["branch"] if chosen is not None else None,
            "evaluations": evaluations,
        }
        self.last_branch_decisions.append(decision)
        logger.info(
            "[HTN] Decision condicional %s: rama=%s evaluaciones=%s",
            rule.name, decision["chosen_branch"], evaluations,
        )
        if chosen is None:
            raise HTNDecompositionError(
                "Ninguna rama de %s es aplicable" % rule.name,
                {"reason": "no_branch_applicable", "rule": rule.name, "branch_decision": decision},
            )
        tasks: List[Task] = []
        for index, branch in enumerate(branches):
            branch = branch if isinstance(branch, dict) else {}
            branch_name = evaluations[index]["branch"]
            previous: Optional[str] = None
            for pattern_id in self._as_list(branch.get("pattern")):
                task = self._task_from_pattern(goal, str(pattern_id), goal.id)
                task.id = f"{task.id}_{branch_name}"
                task.metadata["branch"] = branch_name
                task.metadata["branch_decision"] = decision
                if index == chosen:
                    if previous is not None:
                        task.dependencies.append(previous)
                    previous = task.id
                else:
                    task.mark_skipped(f"rama no elegida: {branch_name}")
                tasks.append(task)
        return tasks

    def _decompose_iterative(self, goal: Goal, rule: HTNDecompositionRule) -> List[Task]:
        # La iteracion esta representada como contenedor jerarquico; no se ejecuta
        # como una accion fisica. El motor no inventa numero de iteraciones.
        root = Task(
            id=f"{goal.id}_main_loop",
            name="Bucle principal",
            description="Contenedor de la descomposici\u00f3n iterativa",
            parent=goal.id,
        )
        tasks = [root]
        previous = root.id
        for pattern_id in rule.decomposition_pattern:
            task = self._task_from_pattern(goal, pattern_id, root.id)
            task.id = f"{task.id}_loop"
            task.dependencies.append(previous)
            tasks.append(task)
            previous = task.id
        return tasks

    def _establish_hierarchy(self, tasks: List[Task], goal: Goal) -> List[Task]:
        root = Task(
            id=str(goal.id),
            name=f"Objetivo: {getattr(goal, 'description', self._goal_type(goal))}",
            description=f"Tarea ra\u00edz para {self._goal_type(goal)}",
            parent=None,
        )
        by_id = {task.id: task for task in tasks if getattr(task, "id", None)}
        if len(by_id) != len(tasks):
            raise ValueError("La descomposicion contiene IDs de tarea vacios o duplicados")
        root.children = []
        for task in tasks:
            if task.parent in by_id and task.parent != task.id:
                parent = by_id[task.parent]
                if task.id not in parent.children:
                    parent.children.append(task.id)
            else:
                task.parent = root.id
                if task.id not in root.children:
                    root.children.append(task.id)
        try:
            root.metadata = {"goal_id": goal.id, "logical_container": True}
        except Exception:
            pass
        return [root] + tasks

    # ------------------------------------------------------------------
    # DEPENDENCIAS Y EJECUCION
    # ------------------------------------------------------------------

    def _order_tasks_by_dependencies(self, tasks: List[Task]) -> List[Task]:
        task_ids = {str(task.id) for task in tasks}
        pending = list(tasks)
        done: Set[str] = set()
        ordered: List[Task] = []
        while pending:
            ready = [
                task for task in pending
                if {str(dep) for dep in (task.dependencies or []) if str(dep) in task_ids}.issubset(done)
            ]
            if not ready:
                # No se descartan tareas; el validador posterior reportara ciclo
                # o dependencia invalida antes de que pueda ejecutarse ninguna.
                ordered.extend(pending)
                break
            for task in ready:
                ordered.append(task)
                done.add(str(task.id))
                pending.remove(task)
        return ordered

    def _validate_task_dependencies(self, tasks: List[Task]) -> Optional[str]:
        ids = {str(task.id) for task in tasks}
        done: Set[str] = set()
        for task in tasks:
            dependencies = {str(dep) for dep in (getattr(task, "dependencies", []) or [])}
            unknown = dependencies - ids
            if unknown:
                return f"La tarea {task.id} depende de tareas desconocidas: {sorted(unknown)}"
            unresolved = dependencies - done
            if unresolved:
                return f"Dependencia c\u00edclica o fuera de orden para {task.id}: {sorted(unresolved)}"
            done.add(str(task.id))
        return None

    def _get_task_executor(self) -> Optional[Any]:
        """Carga TaskExecutor de manera perezosa para evitar importaciones circulares."""
        if self._task_executor is None:
            try:
                from src.hands.planner.task_executor import get_task_executor
                self._task_executor = get_task_executor()
            except Exception:
                logger.warning("[HTN] TaskExecutor no disponible", exc_info=True)
                self._task_executor = False
        return self._task_executor if self._task_executor is not False else None

    def _execute_task_hierarchy(
        self, tasks: List[Task], current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        root = next((task for task in tasks if getattr(task, "parent", None) is None), None)
        if root is None:
            return self._failed_result("unknown", "No se encontr\u00f3 tarea ra\u00edz", current_state)

        all_tasks = [task for task in tasks if task.id != root.id]
        ordered = self._order_tasks_by_dependencies(all_tasks)
        dependency_error = self._validate_task_dependencies(ordered)
        if dependency_error:
            return self._failed_result(root.id, dependency_error, current_state)

        results: List[Dict[str, Any]] = []
        state = dict(current_state or {})
        container_ids = {
            str(task.parent)
            for task in all_tasks
            if getattr(task, "parent", None) in {item.id for item in all_tasks}
        }
        # Las tareas con hijos son contenedores HTN, no acciones ejecutables.
        container_ids.update(
            str(task.id) for task in all_tasks if getattr(task, "children", [])
        )

        by_id = {task.id: task for task in all_tasks}

        def _ancestors(task: Task) -> List[Task]:
            chain: List[Task] = []
            seen: Set[str] = set()
            parent_id = getattr(task, "parent", None)
            while parent_id in by_id and parent_id not in seen:
                seen.add(parent_id)
                chain.append(by_id[parent_id])
                parent_id = getattr(by_id[parent_id], "parent", None)
            return chain

        # Los contenedores no se marcan como completados al encontrarlos: solo
        # cuando todas sus hijas terminan (4.3.5 / 4.2.3.3). Antes se marcaban
        # COMPLETED antes de ejecutar las hojas y un fallo posterior no los
        # corregia.
        for task in ordered:
            if task.id in container_ids:
                continue
            # Rama condicional no elegida: no se ejecuta (4.4.2.3).
            if getattr(task, "status", None) == TaskStatus.SKIPPED:
                continue

            # Una dependencia no completada bloquea la tarea (4.4.3).
            unmet = [
                str(dep) for dep in (task.dependencies or [])
                if str(dep) in by_id and str(dep) not in container_ids
                and str(dep) not in self.completed_tasks
                and getattr(by_id[str(dep)], "status", None) != TaskStatus.SKIPPED
            ]
            if unmet:
                self._mark_task(task, TaskStatus.FAILED, f"dependencias no satisfechas: {unmet}")
                self.failed_tasks.add(task.id)
                for ancestor in _ancestors(task):
                    self._mark_task(ancestor, TaskStatus.FAILED, f"hija fallida: {task.id}")
                return TaskExecutionResult(
                    task_id=root.id,
                    status=TaskStatus.FAILED,
                    result={"failed_task_id": task.id, "unmet_dependencies": unmet},
                    execution_time=time.perf_counter() - (self.start_time or time.perf_counter()),
                    subtask_results=results,
                    error_message=f"Dependencia no satisfecha para {task.id}: {unmet}",
                    new_state=state,
                )

            self._mark_task(task, TaskStatus.EXECUTING)
            result = self._execute_single_task(task, state)
            results.append(self._result_to_dict(result))
            if result.status != TaskStatus.COMPLETED:
                aborted = result.status == TaskStatus.ABORTED
                self.failed_tasks.add(task.id)
                # Una cancelacion (4.7.3) deja la hoja ABORTED, no FAILED.
                self._mark_task(task, TaskStatus.ABORTED if aborted else TaskStatus.FAILED, result.error_message)
                # El fallo de una hoja marca como fallidos a sus contenedores
                # y nunca deja el Goal como completado (4.3.5.2).
                for ancestor in _ancestors(task):
                    self._mark_task(ancestor, TaskStatus.FAILED, f"hija fallida: {task.id}")
                failure_payload = dict(result.result) if isinstance(result.result, dict) else {}
                failure_payload.setdefault("failed_task_id", task.id)
                if aborted:
                    failure_payload["aborted"] = True
                failure_payload.setdefault(
                    "failed_task_path", [a.id for a in reversed(_ancestors(task))] + [task.id]
                )
                return TaskExecutionResult(
                    task_id=root.id,
                    status=TaskStatus.FAILED,
                    result=failure_payload,
                    execution_time=time.perf_counter() - (self.start_time or time.perf_counter()),
                    subtask_results=results,
                    error_message=f"Tarea fallida: {task.name}: {result.error_message or 'error desconocido'}",
                    new_state=state,
                )

            self.completed_tasks.add(task.id)
            self._mark_task(task, TaskStatus.COMPLETED)
            state = dict(result.new_state or state)
            completed = list(state.get("completed_tasks", []) or [])
            if task.id not in completed:
                completed.append(task.id)
            state["completed_tasks"] = completed

        # Todas las hojas terminaron: los contenedores se completan ahora.
        # Un contenedor cuyas hojas fueron todas omitidas queda SKIPPED.
        def _all_skipped(task: Task, seen: Set[str]) -> bool:
            if task.id in seen:
                return False
            seen.add(task.id)
            child_tasks = [by_id[c] for c in (task.children or []) if c in by_id]
            if not child_tasks:
                return getattr(task, "status", None) == TaskStatus.SKIPPED
            return all(_all_skipped(child, seen) for child in child_tasks)

        for task in all_tasks:
            if task.id in container_ids:
                if task.children and _all_skipped(task, set()):
                    self._mark_task(task, TaskStatus.SKIPPED)
                    continue
                self._mark_task(task, TaskStatus.COMPLETED)
                self.completed_tasks.add(task.id)

        return TaskExecutionResult(
            task_id=root.id,
            status=TaskStatus.COMPLETED,
            result={"message": "Jerarqu\u00eda procesada", "new_state": state},
            execution_time=time.perf_counter() - (self.start_time or time.perf_counter()),
            subtask_results=results,
            new_state=state,
        )

    @staticmethod
    def _mark_task(task: Task, status: TaskStatus, error: Optional[str] = None) -> None:
        """
        Cambia el estado de una Task respetando sus transiciones validas.

        Un contenedor pasa por EXECUTING antes de su estado final; si la Task no
        tiene ``transition_to`` (objetos externos) se asigna directamente.
        """
        transition = getattr(task, "transition_to", None)
        if not callable(transition):
            try:
                task.status = status
            except Exception:
                pass
            return
        current = getattr(task, "status", None)
        if current == status:
            return
        if (
            status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            and current == TaskStatus.PENDING
        ):
            transition(TaskStatus.EXECUTING)
        transition(status, error)

    def _execute_single_task(
        self, task: Task, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        started = time.perf_counter()
        self.active_tasks.add(task.id)
        try:
            executor = self._get_task_executor()
            if executor is None:
                return TaskExecutionResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    execution_time=time.perf_counter() - started,
                    error_message="TaskExecutor no disponible; no se simula \u00e9xito",
                    new_state=dict(current_state or {}),
                )
            execute = getattr(executor, "execute_task", None)
            if not callable(execute):
                return TaskExecutionResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error_message="TaskExecutor no dispone de execute_task()",
                    execution_time=time.perf_counter() - started,
                    new_state=dict(current_state or {}),
                )
            raw = execute(task, dict(current_state or {}))
            return self._normalize_task_result(raw, task, current_state, started)
        except Exception as exc:
            logger.exception("[HTN] Error al procesar tarea %s", task.id)
            return TaskExecutionResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error_message=str(exc),
                execution_time=time.perf_counter() - started,
                new_state=dict(current_state or {}),
            )
        finally:
            self.active_tasks.discard(task.id)

    @staticmethod
    def _result_to_dict(result: TaskExecutionResult) -> Dict[str, Any]:
        """Serializa el resultado de una subtarea sin exponer referencias mutables."""
        try:
            payload = copy.deepcopy(result.result)
        except Exception:
            payload = dict(result.result) if isinstance(result.result, dict) else result.result
        return {
            "task_id": result.task_id,
            "status": getattr(result.status, "value", str(result.status)),
            "result": payload,
            "execution_time": result.execution_time,
            "subtask_results": copy.deepcopy(result.subtask_results),
            "error_message": result.error_message,
            "new_state": dict(result.new_state or {}),
        }

    def _normalize_task_result(
        self, raw: Any, task: Task, current_state: Dict[str, Any], started: float
    ) -> TaskExecutionResult:
        if isinstance(raw, TaskExecutionResult):
            status = self._normalize_task_status(raw.status)
            return TaskExecutionResult(
                task_id=str(raw.task_id or task.id),
                status=status,
                result=self._as_dict(raw.result) if raw.result is not None else None,
                execution_time=self._safe_cost(raw.execution_time),
                subtask_results=self._as_list(raw.subtask_results),
                error_message=raw.error_message,
                new_state=self._normalize_state(raw.new_state) if raw.new_state else dict(current_state or {}),
            )

        status = self._normalize_task_status(getattr(raw, "status", None))
        if isinstance(raw, dict):
            status = self._normalize_task_status(raw.get("status", status))
            payload = raw.get("result", raw)
            new_state = raw.get("new_state", current_state)
            task_id = raw.get("task_id", task.id)
            duration = raw.get("execution_time", time.perf_counter() - started)
            error = raw.get("error_message", raw.get("error"))
        else:
            payload = getattr(raw, "result", None)
            new_state = getattr(raw, "new_state", current_state)
            task_id = getattr(raw, "task_id", task.id)
            duration = getattr(raw, "execution_time", time.perf_counter() - started)
            error = getattr(raw, "error_message", None)

        if status == TaskStatus.PENDING and isinstance(raw, bool) and raw:
            # Un boolean true no demuestra que la ejecucion terminara correctamente.
            status = TaskStatus.FAILED
            error = error or "TaskExecutor devolvi\u00f3 un booleano sin estado verificable"
        return TaskExecutionResult(
            task_id=str(task_id or task.id),
            status=status,
            result=payload if isinstance(payload, dict) else ({"result": payload} if payload is not None else None),
            execution_time=self._safe_cost(duration),
            error_message=str(error) if error else (None if status == TaskStatus.COMPLETED else "Resultado de tarea sin estado completado"),
            new_state=self._normalize_state(new_state),
        )

    @staticmethod
    def _normalize_task_status(status: Any) -> TaskStatus:
        if isinstance(status, TaskStatus):
            return status
        value = str(getattr(status, "value", status or "")).strip().lower()
        try:
            return TaskStatus(value)
        except ValueError:
            return TaskStatus.FAILED

    def _simulate_task_execution(self, task: Task, current_state: Dict[str, Any]) -> bool:
        del current_state
        logger.warning(
            "[HTN] _simulate_task_execution esta obsoleto; no se declarara exito ficticio para %s",
            getattr(task, "id", "unknown"),
        )
        return False

    # ------------------------------------------------------------------
    # ESTADISTICAS E HISTORIAL
    # ------------------------------------------------------------------

    def _record_execution(
        self,
        goal: Goal,
        tasks: List[Task],
        result: TaskExecutionResult,
        elapsed: float,
    ) -> None:
        self.execution_history.append(
            {
                "goal_id": getattr(goal, "id", None),
                "goal_type": self._goal_type(goal),
                "tasks_total": max(0, len(tasks) - 1),
                "execution_time": max(0.0, float(elapsed)),
                "status": result.status.value,
                "timestamp": time.time(),
                "completed_tasks": len(self.completed_tasks),
                "failed_tasks": len(self.failed_tasks),
                "planned_only": bool((result.result or {}).get("planned_only", False)) if isinstance(result.result, dict) else False,
                "error": result.error_message,
            }
        )

    def get_execution_statistics(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "total_executions": len(self.execution_history),
            "total_execution_time": self.total_execution_time,
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "available_tasks": len(self.available_tasks),
            "decomposition_rules": len(self.decomposition_rules),
        }

    def get_task_execution_history(self) -> List[Dict[str, Any]]:
        try:
            return copy.deepcopy(self.execution_history)
        except Exception:
            return [dict(record) for record in self.execution_history]

    # ------------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------------

    @staticmethod
    def _valid_goal(goal: Any) -> bool:
        return goal is not None and bool(str(getattr(goal, "id", "") or "").strip())

    @staticmethod
    def _goal_type(goal: Any) -> str:
        value = getattr(goal, "type", "")
        return str(getattr(value, "value", value) or "").strip().lower()

    @staticmethod
    def _normalize_state(state: Any) -> Dict[str, Any]:
        return dict(state) if isinstance(state, dict) else {}

    @staticmethod
    def _status_value(status: Any) -> str:
        return str(getattr(status, "value", status or "")).strip().lower()

    @staticmethod
    def _safe_cost(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
            return result if math.isfinite(result) and result >= 0 else default
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        if isinstance(value, (str, bytes)):
            return [value]
        try:
            return list(value)
        except TypeError:
            return [value]

    @staticmethod
    def _evaluate_precondition(precondition: str, state: Dict[str, Any]) -> bool:
        if precondition in state:
            return bool(state[precondition])
        # El formato de requisitos es declarativo: si no existe la clave, no se
        # considera satisfecha por defecto.
        return False

    @staticmethod
    def _failed_result(
        task_id: str, message: str, state: Optional[Dict[str, Any]] = None
    ) -> TaskExecutionResult:
        return TaskExecutionResult(
            task_id=str(task_id or "unknown"),
            status=TaskStatus.FAILED,
            error_message=str(message),
            new_state=dict(state) if isinstance(state, dict) else {},
        )


def get_htn_manager() -> HTNManager:
    """Obtiene la instancia global de HTNManager de forma segura."""
    global _htn_manager
    with _htn_manager_lock:
        if _htn_manager is None:
            manager = HTNManager()
            manager.initialize_decomposition_rules()
            manager.load_task_library()
            _htn_manager = manager
        return _htn_manager


_htn_manager: Optional[HTNManager] = None
_htn_manager_lock = threading.Lock()


__all__ = [
    "HTNManager",
    "HTNStatus",
    "TaskDecompositionStrategy",
    "TaskExecutionResult",
    "HTNDecompositionRule",
    "HTNDecompositionError",
    "MAX_DECOMPOSITION_DEPTH",
    "get_htn_manager",
]
