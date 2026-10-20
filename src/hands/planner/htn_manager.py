"""Gestor de descomposición jerárquica de tareas (HTN) de JARVIS.

El módulo transforma objetivos en jerarquías de tareas, comprueba dependencias y
coordina la integración opcional con StateGraph, Planner y TaskExecutor. La
planificación no ejecuta acciones físicas por sí sola; la ejecución de tareas
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

try:  # Compatibilidad con ejecución como paquete y desde la raíz del proyecto.
    from src.hands.planner.node import Goal, Node, NodeType, Task, TaskStatus
    from src.hands.planner.graph import StateGraph
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.utils.logger import get_logger
except ImportError:  # pragma: no cover - depende de cómo se lance JARVIS.
    from src.hands.planner.node import Goal, Node, NodeType, Task, TaskStatus
    from src.hands.planner.graph import StateGraph
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.utils.logger import get_logger

logger = get_logger(__name__)


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
    """Gestor central de reglas HTN y jerarquías de tareas."""

    def __init__(self, planner: Optional[Any] = None) -> None:
        self.planner = planner
        self.available_tasks: Dict[str, Task] = {}
        self.decomposition_rules: List[HTNDecompositionRule] = []
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

        # False significa que la carga se intentó y falló; evita ciclos de imports.
        self._task_executor: Any = None
        self._lock = threading.RLock()
        logger.info("[HTN] Gestor de descomposición jerárquica inicializado")

    # ------------------------------------------------------------------
    # CONFIGURACIÓN
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
        logger.info("[HTN] %s reglas de descomposición inicializadas", len(rules))

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
        """Compatibilidad pública: descompone y procesa la jerarquía resultante."""
        if not self._valid_goal(goal):
            return self._failed_result("unknown", "Objetivo inválido")
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
            logger.exception("[HTN] Error en descomposición con grafo")
            if htn_tasks:
                return self._execute_task_hierarchy(htn_tasks, dict(current_state))
            return self._failed_result(goal.id, str(exc), state=current_state)
        finally:
            if self.status == HTNStatus.DECOMPOSING:
                self.status = previous_status if previous_status != HTNStatus.DECOMPOSING else HTNStatus.IDLE

    def _decompose_with_graph_advanced(
        self, goal: Goal, htn_tasks: List[Task], current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        """Usa las dependencias para ordenar tareas y delega ejecución a TaskExecutor.

        La integración gráfica no sustituye la jerarquía HTN por una ruta no
        relacionada ni considera que una simple respuesta del Planner sea ejecución.
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
                logger.warning("[HTN] Dependencias cíclicas o sin resolver en nodos HTN")
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

        Un resultado de planificación se etiqueta como ``planned_only``. El
        TaskExecutor es el único responsable de ejecutar acciones físicas.
        """
        if self.planner is None:
            return self._execute_plan_directly(execution_plan, current_state, goal)
        try:
            planning_result = self._call_planner(goal, current_state)
            if planning_result is None:
                return self._failed_result(goal.id, "El Planner no devolvió resultado", current_state)
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
                goal.id, f"Planificación fallida: {warning or status or 'estado desconocido'}", current_state
            )
        except Exception as exc:
            logger.exception("[HTN] Falló la integración con Planner")
            return self._failed_result(goal.id, str(exc), current_state)

    def _call_planner(self, goal: Goal, current_state: Dict[str, Any]) -> Any:
        plan_method = getattr(self.planner, "plan", None)
        if not callable(plan_method):
            raise AttributeError("El objeto Planner no dispone de plan()")
        # La firma canónica es plan(goal, current_state). No se reintenta con
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
        """Fallback de planificación que no ejecuta ni simula acciones."""
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
    # BIBLIOTECA Y DESCOMPOSICIÓN
    # ------------------------------------------------------------------

    def load_task_library(self) -> None:
        tasks = [
            Task("prepare_navigator", "Preparar navegador", "Prepara el navegador"),
            Task("navigate_to_target", "Navegar al destino", "Navega a la URL objetivo"),
            Task("navigate_to_search_engine", "Navegar al motor de búsqueda", "Navega al motor de búsqueda"),
            Task("perform_search", "Realizar búsqueda", "Realiza una búsqueda"),
            Task("check_availability", "Verificar disponibilidad", "Verifica disponibilidad"),
            Task("open_application", "Abrir aplicación", "Abre la aplicación"),
            Task("activate_window", "Activar ventana", "Activa la ventana"),
            Task("resolve_entity", "Resolver entidad", "Resuelve la entidad"),
        ]
        self.available_tasks = {task.id: task for task in tasks}
        logger.info("[HTN] Biblioteca de tareas cargada: %s tareas", len(tasks))

    def decompose_goal(self, goal: Goal, current_state: Dict[str, Any]) -> List[Task]:
        if not self._valid_goal(goal):
            logger.warning("[HTN] No se puede descomponer un objetivo inválido")
            return []
        prior_status = self.status
        self.status = HTNStatus.DECOMPOSING
        started = time.perf_counter()
        try:
            if not self.decomposition_rules:
                self.initialize_decomposition_rules()
            if not self.available_tasks:
                self.load_task_library()
            rule = self._find_decomposition_rule(goal, self._normalize_state(current_state))
            if rule is None:
                return []
            if not self._check_preconditions(rule, self._normalize_state(current_state)):
                logger.info("[HTN] Precondiciones no satisfechas para regla %s", rule.name)
                return []
            if rule.strategy == TaskDecompositionStrategy.SEQUENTIAL:
                tasks = self._decompose_sequential(goal, rule)
            elif rule.strategy == TaskDecompositionStrategy.PARALLEL:
                tasks = self._decompose_parallel(goal, rule)
            elif rule.strategy == TaskDecompositionStrategy.CONDITIONAL:
                tasks = self._decompose_conditional(goal, rule, self._normalize_state(current_state))
            else:
                tasks = self._decompose_iterative(goal, rule)
            tasks = self._establish_hierarchy(tasks, goal)
            dependency_error = self._validate_task_dependencies(tasks)
            if dependency_error:
                logger.warning("[HTN] Descomposición inválida: %s", dependency_error)
                return []
            return tasks
        except Exception:
            logger.exception("[HTN] Error al descomponer objetivo %s", getattr(goal, "id", None))
            return []
        finally:
            self.status = prior_status if prior_status != HTNStatus.DECOMPOSING else HTNStatus.IDLE
            logger.debug("[HTN] Descomposición en %.4fs", time.perf_counter() - started)

    def execute_goal_hierarchy(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> TaskExecutionResult:
        if not self._valid_goal(goal):
            return self._failed_result("unknown", "Objetivo inválido", current_state)

        state = self._normalize_state(current_state)
        with self._lock:
            self.status = HTNStatus.EXECUTING
            self.start_time = time.perf_counter()
            self.active_tasks.clear()
            self.completed_tasks.clear()
            self.failed_tasks.clear()
        started = self.start_time
        try:
            tasks = self.decompose_goal(goal, state)
            if not tasks:
                result = self._failed_result(goal.id, "No se pudo descomponer el objetivo", state)
                self.status = HTNStatus.FAILED
                self._record_execution(goal, [], result, time.perf_counter() - started)
                return result

            result = self._execute_task_hierarchy(tasks, dict(state))
            elapsed = time.perf_counter() - started
            self.total_execution_time += elapsed
            self.status = HTNStatus.COMPLETED if result.status == TaskStatus.COMPLETED else HTNStatus.FAILED
            self._record_execution(goal, tasks, result, elapsed)
            return result
        except Exception as exc:
            self.status = HTNStatus.FAILED
            logger.exception("[HTN] Falló la jerarquía del objetivo %s", goal.id)
            result = self._failed_result(goal.id, str(exc), state)
            self._record_execution(goal, [], result, time.perf_counter() - started)
            return result
        finally:
            if self.status not in (HTNStatus.COMPLETED, HTNStatus.FAILED):
                self.status = HTNStatus.IDLE

    def _find_decomposition_rule(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> Optional[HTNDecompositionRule]:
        goal_type = self._goal_type(goal)
        matches = [rule for rule in self.decomposition_rules if rule.target_type == goal_type]
        matches.extend(rule for rule in self.decomposition_rules if rule.target_type == "generic")
        for rule in sorted(matches, key=lambda item: item.priority):
            if self._check_preconditions(rule, current_state):
                return rule
        return None

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
        state = self._normalize_state(current_state)
        special = {
            "browser_available": self._browser_available(state),
            "entity_available": self._entity_available(state),
            "application_known": bool(state.get("applications_known", False)) or self._application_catalog_available(),
            "search_engine_known": bool(state.get("search_engine_known", True)),
            "multiple_tasks_defined": bool(state.get("multiple_tasks_defined", False)),
        }
        for precondition in rule.preconditions:
            if precondition in special:
                if not special[precondition]:
                    return False
            elif not self._evaluate_precondition(precondition, state):
                return False
        return True

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
            description=str(getattr(template, "description", f"Tarea dinámica para {pattern_id}")),
            status=TaskStatus.PENDING,
            parent=parent,
            dependencies=list(getattr(template, "dependencies", []) or []),
        )
        metadata = self._as_dict(getattr(template, "metadata", {}))
        metadata.update({"task_type": pattern_id, "goal_id": safe_goal_id})
        # Task del modelo canónico no declara metadata/parameters, se anexan de
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
            # Las tareas secuenciales son hermanas bajo el objetivo raíz; el
            # orden se expresa mediante dependencies, no como relación padre-hijo.
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
        return [
            self._task_from_pattern(goal, pattern_id, goal.id)
            for pattern_id in rule.decomposition_pattern
            if current_state.get(f"enable_{pattern_id}", True)
        ]

    def _decompose_iterative(self, goal: Goal, rule: HTNDecompositionRule) -> List[Task]:
        # La iteración está representada como contenedor jerárquico; no se ejecuta
        # como una acción física. El motor no inventa número de iteraciones.
        root = Task(
            id=f"{goal.id}_main_loop",
            name="Bucle principal",
            description="Contenedor de la descomposición iterativa",
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
            description=f"Tarea raíz para {self._goal_type(goal)}",
            parent=None,
        )
        by_id = {task.id: task for task in tasks if getattr(task, "id", None)}
        if len(by_id) != len(tasks):
            raise ValueError("La descomposición contiene IDs de tarea vacíos o duplicados")
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
    # DEPENDENCIAS Y EJECUCIÓN
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
                # No se descartan tareas; el validador posterior reportará ciclo
                # o dependencia inválida antes de que pueda ejecutarse ninguna.
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
                return f"Dependencia cíclica o fuera de orden para {task.id}: {sorted(unresolved)}"
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
            return self._failed_result("unknown", "No se encontró tarea raíz", current_state)

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

        for task in ordered:
            if task.id in container_ids:
                self.completed_tasks.add(task.id)
                try:
                    task.status = TaskStatus.COMPLETED
                except Exception:
                    pass
                continue

            result = self._execute_single_task(task, state)
            results.append(self._result_to_dict(result))
            if result.status != TaskStatus.COMPLETED:
                self.failed_tasks.add(task.id)
                try:
                    task.status = TaskStatus.FAILED
                except Exception:
                    pass
                return TaskExecutionResult(
                    task_id=root.id,
                    status=TaskStatus.FAILED,
                    result=result.result,
                    execution_time=time.perf_counter() - (self.start_time or time.perf_counter()),
                    subtask_results=results,
                    error_message=f"Tarea fallida: {task.name}: {result.error_message or 'error desconocido'}",
                    new_state=state,
                )

            self.completed_tasks.add(task.id)
            try:
                task.status = TaskStatus.COMPLETED
            except Exception:
                pass
            state = dict(result.new_state or state)
            completed = list(state.get("completed_tasks", []) or [])
            if task.id not in completed:
                completed.append(task.id)
            state["completed_tasks"] = completed

        return TaskExecutionResult(
            task_id=root.id,
            status=TaskStatus.COMPLETED,
            result={"message": "Jerarquía procesada", "new_state": state},
            execution_time=time.perf_counter() - (self.start_time or time.perf_counter()),
            subtask_results=results,
            new_state=state,
        )

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
                    error_message="TaskExecutor no disponible; no se simula éxito",
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
            # Un boolean true no demuestra que la ejecución terminara correctamente.
            status = TaskStatus.FAILED
            error = error or "TaskExecutor devolvió un booleano sin estado verificable"
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
            "[HTN] _simulate_task_execution está obsoleto; no se declarará éxito ficticio para %s",
            getattr(task, "id", "unknown"),
        )
        return False

    # ------------------------------------------------------------------
    # ESTADÍSTICAS E HISTORIAL
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
    "get_htn_manager",
]
