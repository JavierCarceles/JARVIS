"""
Planificador principal de JARVIS.

Responsabilidades:
- Recibir Goal, estado actual y nodos disponibles.
- Construir/usar el StateGraph para obtener rutas.
- Mantener compatibilidad con HTN, conocimiento de aplicaciones,
  optimización, aprendizaje y CoordinateManager.
- Devolver un PlanningResult estructurado.

La planificación no ejecuta acciones físicas. La ejecución, cuando se solicita
explícitamente por compatibilidad, se delega a un executor externo.
"""

from __future__ import annotations

import copy
import inspect
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# El proyecto ha usado ambas convenciones de importación. Se acepta la ruta
# instalada y la ruta relativa al directorio src para evitar fallos de arranque.
try:
    from src.hands.planner.node import Goal, Node, NodeType
    from src.hands.planner.graph import (
        AdvancedStateGraph,
        GraphBuilder,
        SearchStrategy,
        StateGraph,
    )
    from src.hands.planner.heuristic import Heuristic, HeuristicType
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.hands.coordinate_manager import get_coordinate_manager
    from src.utils.logger import get_logger
except ImportError:  # pragma: no cover - depende del layout del proyecto
    from src.hands.planner.node import Goal, Node, NodeType
    from src.hands.planner.graph import (
        AdvancedStateGraph,
        GraphBuilder,
        SearchStrategy,
        StateGraph,
    )
    from src.hands.planner.heuristic import Heuristic, HeuristicType
    from src.hands.planner.application_integration import (
        get_application_knowledge_integrator,
    )
    from src.hands.coordinate_manager import get_coordinate_manager
    from src.utils.logger import get_logger

logger = get_logger(__name__)


class PlannerStatus(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLANNING = "replanning"


class PlanQuality(Enum):
    OPTIMAL = "optimal"
    SUBOPTIMAL = "suboptimal"
    MINIMAL = "minimal"
    UNCERTAIN = "uncertain"


@dataclass
class PlanningResult:
    """Resultado estructurado de una solicitud de planificación."""

    status: PlannerStatus
    plan: List[Dict[str, Any]] = field(default_factory=list)
    plan_id: Optional[str] = None
    goal: Optional[Goal] = None
    current_state: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    quality: PlanQuality = PlanQuality.UNCERTAIN
    alternatives: List[List[Dict[str, Any]]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlannerStatus):
            value = getattr(self.status, "value", self.status)
            try:
                self.status = PlannerStatus(str(value).lower())
            except ValueError:
                self.status = PlannerStatus.FAILED
        if not isinstance(self.quality, PlanQuality):
            value = getattr(self.quality, "value", self.quality)
            try:
                self.quality = PlanQuality(str(value).lower())
            except ValueError:
                self.quality = PlanQuality.UNCERTAIN
        if not isinstance(self.plan, list):
            self.plan = []
        if not isinstance(self.alternatives, list):
            self.alternatives = []
        if not isinstance(self.warnings, list):
            self.warnings = [str(self.warnings)] if self.warnings else []
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        if not isinstance(self.current_state, dict) and self.current_state is not None:
            self.current_state = {}
        self.execution_time = _finite_nonnegative(self.execution_time, 0.0)


class Planner:
    """Planificador central de JARVIS; no ejecuta físicamente sus planes."""

    def __init__(self, executor: Any = None) -> None:
        self.executor = executor
        self.available_nodes: Dict[str, Node] = {}
        self.planning_history: List[Dict[str, Any]] = []
        self.state_graph: Optional[StateGraph] = None
        self.heuristic: Optional[Heuristic] = None
        self.use_astar = False

        try:
            self.coordinate_manager = get_coordinate_manager()
        except Exception as exc:
            logger.warning("[PLANNER] CoordinateManager no disponible: %s", exc)
            self.coordinate_manager = None
        self.optimization_manager: Optional[Any] = None
        self.learning_system: Optional[Any] = None
        try:
            self.application_integrator = get_application_knowledge_integrator()
        except Exception as exc:
            logger.warning(
                "[PLANNER] Integrador de aplicaciones no disponible: %s", exc
            )
            self.application_integrator = None
        self.htn_manager: Optional[Any] = None
        logger.info("[PLANNER] Planificador inicializado")

    # ==================================================================
    # APRENDIZAJE
    # ==================================================================

    def get_learning_insights(self) -> Dict[str, Any]:
        if not self.learning_system:
            return {"error": "Sistema de aprendizaje no disponible"}
        try:
            value = self.learning_system.get_system_insights()
            return value if isinstance(value, dict) else {"insights": value}
        except Exception as exc:
            logger.warning("[PLANNER] Error obteniendo insights: %s", exc)
            return {"error": str(exc)}

    def get_action_learning_insights(self, action_name: str) -> Dict[str, Any]:
        if not self.learning_system:
            return {"error": "Sistema de aprendizaje no disponible"}
        try:
            value = self.learning_system.get_action_insights(action_name)
            return value if isinstance(value, dict) else {"insights": value}
        except Exception as exc:
            logger.warning(
                "[PLANNER] Error obteniendo insights de %s: %s", action_name, exc
            )
            return {"error": str(exc)}

    def get_cost_adjustments(self) -> Dict[str, float]:
        if not self.learning_system:
            return {}
        try:
            raw = self.learning_system.get_cost_adjustments() or {}
            if not isinstance(raw, dict):
                return {}
            return {str(key): _finite_float(value, 0.0) for key, value in raw.items()}
        except Exception as exc:
            logger.warning("[PLANNER] Error obteniendo ajustes de coste: %s", exc)
            return {}

    def export_learning_data(self, filepath: str) -> None:
        if not self.learning_system:
            logger.info("[PLANNER] Sistema de aprendizaje no disponible para exportar")
            return
        try:
            self.learning_system.export_learning_data(filepath)
        except Exception:
            logger.exception(
                "[PLANNER] No se pudieron exportar los datos de aprendizaje"
            )
            raise

    def import_learning_data(self, filepath: str) -> None:
        if not self.learning_system:
            logger.info("[PLANNER] Sistema de aprendizaje no disponible para importar")
            return
        try:
            self.learning_system.import_learning_data(filepath)
        except Exception:
            logger.exception(
                "[PLANNER] No se pudieron importar los datos de aprendizaje"
            )
            raise

    def clear_learning_data(self) -> None:
        if not self.learning_system:
            logger.info("[PLANNER] Sistema de aprendizaje no disponible para limpiar")
            return
        self.learning_system.clear_learning_data()

    def enable_learning(self, enabled: bool = True) -> None:
        if not self.learning_system:
            logger.info("[PLANNER] Sistema de aprendizaje no disponible")
            return
        self.learning_system.enable_learning(bool(enabled))

    # ==================================================================
    # HTN (solo descomposición/planificación, nunca ejecución física)
    # ==================================================================

    def initialize_htn_manager(self) -> None:
        if self.htn_manager is not None:
            return
        try:
            try:
                from src.hands.planner.htn_manager import HTNManager
            except ImportError:
                from src.hands.planner.htn_manager import HTNManager
            self.htn_manager = HTNManager(self)
            setter = getattr(self.htn_manager, "set_state_graph", None)
            if self.state_graph is not None and callable(setter):
                setter(self.state_graph)
            logger.info("[PLANNER] HTN Manager inicializado")
        except Exception as exc:
            logger.warning("[PLANNER] No se pudo inicializar HTN Manager: %s", exc)
            self.htn_manager = None

    def set_htn_manager(self, htn_manager: Any) -> None:
        self.htn_manager = htn_manager
        setter = getattr(htn_manager, "set_state_graph", None) if htn_manager else None
        if self.state_graph is not None and callable(setter):
            setter(self.state_graph)

    def plan_with_htn_integration(
        self,
        goal: Goal,
        current_state: Optional[Dict[str, Any]] = None,
        available_nodes: Optional[Dict[str, Node]] = None,
        max_planning_time: float = 30.0,
        use_graph_optimization: bool = True,
        htn_decomposition_threshold: int = 3,
    ) -> PlanningResult:
        started = time.perf_counter()
        state = (
            self._normalize_state(current_state)
            if current_state is not None
            else self._get_default_state()
        )
        nodes = (
            dict(available_nodes)
            if available_nodes is not None
            else self._get_available_nodes()
        )
        invalid = self._validate_goal_request(goal, max_planning_time)
        if invalid:
            return self._failure_result(invalid, goal, state, started)
        try:
            if use_graph_optimization and self.state_graph is not None:
                result = self._plan_with_graph_optimized(
                    goal, state, nodes, max_planning_time, htn_decomposition_threshold
                )
            elif self.htn_manager is not None:
                result = self._plan_with_htn_traditional(
                    goal, state, nodes, max_planning_time
                )
            else:
                result = self._create_plan(goal, state, nodes, max_planning_time)
            if result.status == PlannerStatus.COMPLETED:
                result = self._optimize_integrated_plan(result, state, goal)
            result.execution_time = time.perf_counter() - started
            result.plan_id = result.plan_id or self._new_plan_id()
            self._record_planning_history(goal, state, result, "htn_graph_integration")
            return result
        except Exception as exc:
            logger.exception("[PLANNER] Error en planificación HTN + grafo")
            return self._failure_result(
                f"Error en planificación integrada: {exc}", goal, state, started
            )

    def _plan_with_graph_optimized(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
        htn_threshold: int,
    ) -> PlanningResult:
        complexity = self._calculate_goal_complexity(goal, current_state)
        if complexity <= max(0, int(htn_threshold)):
            return self._create_plan_astar(
                goal, current_state, available_nodes, max_planning_time
            )
        return self._plan_complex_htn_graph(
            goal, current_state, available_nodes, max_planning_time
        )

    def _plan_with_htn_traditional(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
    ) -> PlanningResult:
        if self.htn_manager is None:
            return self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )
        # Solo se invocan APIs de descomposición o planificación. Los métodos cuyo
        # nombre indica ejecución se excluyen para mantener este módulo no ejecutor.
        for method_name in (
            "plan_goal",
            "decompose_and_plan",
            "decompose_goal",
            "build_plan",
            "plan",
        ):
            method = getattr(self.htn_manager, method_name, None)
            if not callable(method):
                continue
            try:
                raw = self._invoke_planner_method(
                    method, goal, current_state, available_nodes, max_planning_time
                )
                result = self._coerce_htn_result(raw, goal, current_state)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("[PLANNER] HTN %s falló: %s", method_name, exc)
        return self._create_plan(
            goal, current_state, available_nodes, max_planning_time
        )

    def _plan_complex_htn_graph(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
    ) -> PlanningResult:
        if self.htn_manager is not None:
            for method_name in (
                "decompose_and_plan",
                "decompose_goal",
                "plan_goal",
                "build_plan",
                "plan",
            ):
                method = getattr(self.htn_manager, method_name, None)
                if not callable(method):
                    continue
                try:
                    raw = self._invoke_planner_method(
                        method, goal, current_state, available_nodes, max_planning_time
                    )
                    result = self._coerce_htn_result(raw, goal, current_state)
                    if result is not None and result.status == PlannerStatus.COMPLETED:
                        result.metadata["htn_graph_optimized"] = (
                            self.state_graph is not None
                        )
                        return result
                except Exception as exc:
                    logger.warning(
                        "[PLANNER] Descomposición HTN %s falló: %s", method_name, exc
                    )
        if self.state_graph is not None:
            result = self._create_plan_astar(
                goal, current_state, available_nodes, max_planning_time
            )
            if result.status == PlannerStatus.COMPLETED:
                result.metadata["htn_fallback"] = True
            return result
        return self._create_plan(
            goal, current_state, available_nodes, max_planning_time
        )

    @staticmethod
    def _invoke_planner_method(
        method: Any,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
    ) -> Any:
        """Invoca una API HTN legacy sin repetirla si falla dentro de su cuerpo."""
        full_args = (goal, current_state, available_nodes, max_planning_time)
        try:
            signature = inspect.signature(method)
            parameters = list(signature.parameters.values())
            accepts_varargs = any(
                item.kind == inspect.Parameter.VAR_POSITIONAL for item in parameters
            )
            positional = [
                item
                for item in parameters
                if item.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            required_count = sum(
                1 for item in positional if item.default is inspect.Parameter.empty
            )
            maximum_count = len(full_args) if accepts_varargs else len(positional)
            count = min(len(full_args), maximum_count)
            if count < required_count:
                raise TypeError(
                    f"La API HTN requiere {required_count} argumentos posicionales; solo hay {len(full_args)} disponibles"
                )
            return method(*full_args[:count])
        except (ValueError, AttributeError):
            # Algunos callables C/extensión no exponen firma introspectable. Solo
            # en ese caso se usa una llamada conservadora y única.
            return method(goal, current_state)

    def _coerce_htn_result(
        self, raw: Any, goal: Goal, current_state: Dict[str, Any]
    ) -> Optional[PlanningResult]:
        if isinstance(raw, PlanningResult):
            raw.goal = raw.goal or goal
            raw.current_state = raw.current_state or dict(current_state)
            return raw
        if isinstance(raw, dict):
            status = str(
                getattr(
                    raw.get("status", "completed"),
                    "value",
                    raw.get("status", "completed"),
                )
            ).lower()
            if status not in {"completed", "success", "successful", "planned"}:
                return None
            raw_plan = raw.get("plan", raw.get("execution_plan", []))
            plan = self._normalize_dict_plan(raw_plan)
            return PlanningResult(
                status=PlannerStatus.COMPLETED
                if plan or self._is_goal_achieved(goal, current_state)
                else PlannerStatus.FAILED,
                plan=plan,
                goal=goal,
                current_state=dict(current_state),
                quality=self._evaluate_plan_quality(plan, current_state, goal),
                warnings=list(raw.get("warnings", []) or []),
                metadata={
                    "htn_used": True,
                    **(
                        raw.get("metadata", {})
                        if isinstance(raw.get("metadata"), dict)
                        else {}
                    ),
                },
            )
        if raw is not None:
            status = self._status_value(getattr(raw, "status", "completed"))
            if status and status not in {
                "completed",
                "success",
                "successful",
                "planned",
            }:
                return None
            tasks = getattr(raw, "plan", None)
            if tasks is None:
                tasks = getattr(raw, "execution_plan", None)
            if tasks is None:
                return None
            plan = self._convert_htn_result_to_plan(raw)
            return PlanningResult(
                status=PlannerStatus.COMPLETED
                if plan or self._is_goal_achieved(goal, current_state)
                else PlannerStatus.FAILED,
                plan=plan,
                goal=goal,
                current_state=dict(current_state),
                quality=self._evaluate_plan_quality(plan, current_state, goal),
                metadata={"htn_used": True},
            )
        return None

    def _normalize_dict_plan(self, raw_plan: Any) -> List[Dict[str, Any]]:
        """Normaliza listas de nodos/diccionarios a pasos declarativos de plan."""
        normalized: List[Dict[str, Any]] = []
        for index, raw in enumerate(_as_values(raw_plan)):
            if isinstance(raw, dict):
                item = copy.deepcopy(raw)
                node_id = str(item.get("id", item.get("action", f"plan_step_{index}")))
                item["id"] = node_id
                item.setdefault("action", node_id)
                item.setdefault("name", node_id)
                item.setdefault("type", "action")
                item["cost"] = _finite_nonnegative(item.get("cost", 1.0), 1.0)
                if not isinstance(item.get("parameters"), dict):
                    item["parameters"] = {}
                item["preconditions"] = _as_values(item.get("preconditions", []))
                item["effects"] = _as_values(item.get("effects", []))
                normalized.append(item)
            elif getattr(raw, "id", None) is not None:
                if self._node_type_value(raw) in {"action", "task"}:
                    normalized.append(self._convert_node_to_execution_node(raw))
                else:
                    node_id = str(getattr(raw, "id", f"plan_step_{index}"))
                    normalized.append(
                        {
                            "id": node_id,
                            "action": node_id,
                            "name": str(getattr(raw, "name", node_id)),
                            "description": str(getattr(raw, "description", "")),
                            "type": "htn_task",
                            "cost": _finite_nonnegative(getattr(raw, "cost", 1.0), 1.0),
                            "parameters": copy.deepcopy(
                                getattr(raw, "parameters", {}) or {}
                            ),
                            "preconditions": _as_values(
                                getattr(raw, "preconditions", [])
                            ),
                            "effects": _as_values(getattr(raw, "effects", [])),
                        }
                    )
            else:
                logger.warning(
                    "[PLANNER] Se omite paso HTN no interpretable en posición %s", index
                )
        return normalized

    def _convert_htn_result_to_plan(self, htn_result: Any) -> List[Dict[str, Any]]:
        tasks = getattr(htn_result, "execution_plan", None)
        if tasks is None:
            tasks = getattr(htn_result, "plan", [])
        plan: List[Dict[str, Any]] = []
        for index, task in enumerate(tasks or []):
            if isinstance(task, dict):
                item = dict(task)
                item.setdefault("id", str(item.get("action", f"htn_task_{index}")))
                item.setdefault("action", item["id"])
                item.setdefault("type", "htn_task")
                item.setdefault("cost", 1.0)
                item.setdefault("parameters", {})
                plan.append(item)
                continue
            cost = _finite_nonnegative(getattr(task, "cost", 1.0), 1.0)
            task_id = str(getattr(task, "id", f"htn_task_{index}"))
            plan.append(
                {
                    "id": task_id,
                    "name": str(getattr(task, "name", task_id)),
                    "action": str(getattr(task, "action", task_id) or task_id),
                    "description": str(getattr(task, "description", "")),
                    "type": "htn_task",
                    "cost": cost,
                    "parameters": dict(getattr(task, "parameters", {}) or {}),
                    "preconditions": list(getattr(task, "preconditions", []) or []),
                    "effects": list(getattr(task, "effects", []) or []),
                    "metadata": {"htn_result": True},
                }
            )
        return plan

    # ==================================================================
    # GRAPH <-> PLANNER
    # ==================================================================

    def set_state_graph(self, state_graph: StateGraph) -> None:
        if state_graph is None:
            raise ValueError("state_graph no puede ser None")
        nodes = getattr(state_graph, "nodes", None)
        if not isinstance(nodes, dict):
            raise TypeError("state_graph debe exponer un diccionario nodes")
        self.state_graph = state_graph
        self.use_astar = True
        setter = (
            getattr(self.htn_manager, "set_state_graph", None)
            if self.htn_manager
            else None
        )
        if callable(setter):
            try:
                setter(state_graph)
            except Exception:
                logger.exception(
                    "[PLANNER] No se pudo propagar el grafo al HTN manager"
                )
        logger.info("[PLANNER] Grafo de estados establecido (%s nodos)", len(nodes))

    def get_state_graph(self) -> Optional[StateGraph]:
        return self.state_graph

    def create_graph_from_nodes(self, nodes: Dict[str, Node]) -> StateGraph:
        if not isinstance(nodes, dict):
            raise TypeError("nodes debe ser un diccionario de ID a Node")
        graph = StateGraph(self.heuristic)
        normalized: Dict[str, Node] = {}
        for key, node in nodes.items():
            if node is None:
                continue
            node_id = getattr(node, "id", None)
            if not isinstance(node_id, str) or not node_id.strip():
                logger.warning("[PLANNER] Se ignora un nodo sin ID válido: %r", key)
                continue
            if key != node_id:
                logger.debug(
                    "[PLANNER] La clave %r se normaliza al ID %r", key, node_id
                )
            if node_id in normalized and normalized[node_id] is not node:
                logger.warning(
                    "[PLANNER] ID duplicado en grafo, se conserva el primero: %s",
                    node_id,
                )
                continue
            normalized[node_id] = node
            graph.add_node(node)
        self._build_graph_edges(graph, normalized)
        self.available_nodes.update(normalized)
        self.set_state_graph(graph)
        return graph

    def _build_graph_edges(self, graph: StateGraph, nodes: Dict[str, Node]) -> None:
        """Genera solo transiciones respaldadas por dependencias o semántica."""
        if graph is None:
            return
        for source_id, source_node in nodes.items():
            for target_id, target_node in nodes.items():
                if source_id == target_id or not self._should_create_edge(
                    source_node, target_node
                ):
                    continue
                cost = self._calculate_edge_cost_for_graph(source_node, target_node)
                conditions = self._get_edge_conditions(source_node, target_node)
                try:
                    graph.add_edge(
                        source_id,
                        target_id,
                        cost,
                        conditions,
                        "planning",
                        list(getattr(target_node, "preconditions", []) or []),
                        list(getattr(target_node, "effects", []) or []),
                    )
                except TypeError:
                    graph.add_edge(source_id, target_id, cost)
                except Exception:
                    logger.exception(
                        "[PLANNER] No se pudo crear arista %s -> %s",
                        source_id,
                        target_id,
                    )

    def _should_create_edge(self, source_node: Node, target_node: Node) -> bool:
        """No conecta nodos solo por compartir tipo o aplicación."""
        source_id = str(getattr(source_node, "id", ""))
        target_id = str(getattr(target_node, "id", ""))
        source_type = self._node_type_value(source_node)
        target_type = self._node_type_value(target_node)

        # Dependencias y jerarquía declaradas tienen prioridad semántica.
        target_dependencies = _as_values(getattr(target_node, "dependencies", []))
        if source_id in {
            str(getattr(item, "id", item)) for item in target_dependencies
        }:
            return True
        source_children = _as_values(getattr(source_node, "children", []))
        if target_id in {str(getattr(item, "id", item)) for item in source_children}:
            return True
        if str(getattr(target_node, "parent", "") or "") == source_id:
            return True
        if str(getattr(source_node, "parent", "") or "") == target_id:
            return False

        source_metadata = getattr(source_node, "metadata", {}) or {}
        target_metadata = getattr(target_node, "metadata", {}) or {}
        explicit_next = (
            _as_values(source_metadata.get("next_nodes", []))
            if isinstance(source_metadata, dict)
            else []
        )
        explicit_before = (
            _as_values(target_metadata.get("depends_on", []))
            if isinstance(target_metadata, dict)
            else []
        )
        if target_id in {str(getattr(item, "id", item)) for item in explicit_next}:
            return True
        if source_id in {str(getattr(item, "id", item)) for item in explicit_before}:
            return True

        source_facts = self._node_effect_facts(source_node)
        target_preconditions = _as_values(getattr(target_node, "preconditions", []))
        if self._facts_support_conditions(source_facts, target_preconditions):
            return True

        # Un estado puede habilitar una acción si sus hechos declarados satisfacen
        # sus precondiciones; no existe conexión automática state->action.
        if source_type == "state" and target_type == "action":
            return self._facts_support_conditions(
                self._node_state_facts(source_node), target_preconditions
            )
        return False

    def _calculate_edge_cost_for_graph(
        self, source_node: Node, target_node: Node
    ) -> float:
        target_cost = _finite_nonnegative(getattr(target_node, "cost", 1.0), 1.0)
        source_app = _normalize_text(getattr(source_node, "application", None))
        target_app = _normalize_text(getattr(target_node, "application", None))
        cost = target_cost
        if source_app and target_app:
            cost *= 0.8 if source_app == target_app else 1.2
        if self._node_type_value(source_node) == "goal":
            cost *= 1.5
        cost += 0.1 * len(_as_values(getattr(target_node, "preconditions", [])))
        return max(0.0, _finite_nonnegative(cost, 1.0))

    def _get_edge_conditions(self, source_node: Node, target_node: Node) -> List[Any]:
        del source_node
        return _as_values(getattr(target_node, "preconditions", []))

    def integrate_graph_with_htn(self, graph: StateGraph, htn_manager: Any) -> None:
        self.set_state_graph(graph)
        self.set_htn_manager(htn_manager)
        for method_name, args in (
            ("set_planner", (self,)),
            ("set_htn_manager", (htn_manager,)),
        ):
            method = getattr(graph, method_name, None)
            if callable(method):
                try:
                    method(*args)
                except Exception:
                    logger.exception(
                        "[PLANNER] Falló la integración del grafo mediante %s",
                        method_name,
                    )

    def validate_graph_integration(self) -> List[str]:
        if self.state_graph is None:
            return ["Grafo de estados no configurado"]
        errors: List[str] = []
        validate = getattr(self.state_graph, "validate_graph", None)
        if callable(validate):
            try:
                validation = validate()
                if isinstance(validation, dict):
                    errors.extend(
                        str(item) for item in (validation.get("errors", []) or [])
                    )
                elif isinstance(validation, list):
                    errors.extend(str(item) for item in validation)
            except Exception as exc:
                errors.append(f"Error validando grafo: {exc}")
        graph_nodes = getattr(self.state_graph, "nodes", {})
        for node_id in self.available_nodes:
            if node_id not in graph_nodes:
                errors.append(f"Nodo no encontrado en grafo: {node_id}")
        for method_name in ("add_node", "add_edge"):
            if not callable(getattr(self.state_graph, method_name, None)):
                errors.append(f"Método requerido no encontrado en grafo: {method_name}")
        if not hasattr(self.state_graph, "edges"):
            errors.append("Propiedad requerida no encontrada en grafo: edges")
        return errors

    def get_graph_integration_status(self) -> Dict[str, Any]:
        errors = self.validate_graph_integration()
        graph_stats = None
        if self.state_graph is not None:
            stats_method = getattr(self.state_graph, "get_graph_stats", None)
            if callable(stats_method):
                try:
                    graph_stats = stats_method()
                except Exception as exc:
                    errors.append(f"Error obteniendo estadísticas: {exc}")
        return {
            "graph_configured": self.state_graph is not None,
            "htn_manager_available": self.htn_manager is not None,
            "integration_valid": not errors,
            "graph_stats": graph_stats,
            "integration_errors": errors,
        }

    # ==================================================================
    # CONFIGURACIÓN DEL GRAFO / A*
    # ==================================================================

    def configure_astar_planning(
        self,
        heuristic_type: HeuristicType = HeuristicType.GOAL_DISTANCE,
        heuristic_weight: float = 1.0,
        graph_type: str = "navigation",
    ) -> None:
        if not self.available_nodes:
            self.available_nodes = self._get_available_nodes()
        try:
            weight = max(0.0, _finite_float(heuristic_weight, 1.0))
            self.heuristic = Heuristic(heuristic_type, weight)
        except Exception as exc:
            logger.warning(
                "[PLANNER] Heurística no válida; se usa coste uniforme: %s", exc
            )
            self.heuristic = Heuristic(HeuristicType.UNIFORM_COST)

        try:
            if graph_type == "navigation" and callable(
                getattr(GraphBuilder, "build_navigation_graph", None)
            ):
                graph = GraphBuilder.build_navigation_graph(self.available_nodes)
            elif graph_type == "application" and callable(
                getattr(GraphBuilder, "build_application_graph", None)
            ):
                graph = GraphBuilder.build_application_graph(self.available_nodes)
            else:
                graph = StateGraph(self.heuristic)
                for node in self.available_nodes.values():
                    graph.add_node(node)
                self._build_graph_edges(graph, self.available_nodes)
            self.set_state_graph(graph)
        except Exception as exc:
            logger.exception("[PLANNER] Falló la construcción del grafo %s", graph_type)
            raise RuntimeError(
                f"No se pudo configurar el grafo {graph_type}: {exc}"
            ) from exc
        self.use_astar = True

    def _create_graph_edges_from_nodes(self) -> None:
        if self.state_graph is None:
            return
        nodes = getattr(self.state_graph, "nodes", {})
        self._build_graph_edges(self.state_graph, nodes)

    def set_custom_graph(self, graph: StateGraph) -> None:
        self.set_state_graph(graph)

    # ==================================================================
    # PLANIFICACIÓN PRINCIPAL
    # ==================================================================

    def plan(
        self,
        goal: Goal,
        current_state: Optional[Dict[str, Any]] = None,
        available_nodes: Optional[Dict[str, Node]] = None,
        max_planning_time: float = 30.0,
        find_alternatives: bool = True,
        use_optimization: bool = False,
    ) -> PlanningResult:
        started = time.perf_counter()
        state = (
            self._normalize_state(current_state)
            if current_state is not None
            else self._get_default_state()
        )
        nodes = (
            dict(available_nodes)
            if available_nodes is not None
            else self._get_available_nodes()
        )
        invalid = self._validate_goal_request(goal, max_planning_time)
        if invalid:
            return self._failure_result(invalid, goal, state, started)
        try:
            self.available_nodes.update(nodes)
            result = self._plan_with_optional_optimization(
                goal, state, nodes, max_planning_time, use_optimization
            )
            if result.status == PlannerStatus.COMPLETED:
                ui_validation = self.validate_ui_resources_for_plan(result.plan, state)
                result.metadata["ui_validation"] = ui_validation
                if ui_validation["missing_resources"]:
                    resolved = self.resolve_ui_conflicts(result.plan, state)
                    if resolved != result.plan:
                        result.plan = resolved
                        result.metadata["ui_resolved"] = True
                result.metadata["ui_readiness"] = self.check_ui_readiness(
                    goal, state, nodes
                )
                if find_alternatives and self.state_graph is not None and result.plan:
                    result.alternatives = self._find_alternative_plans_astar(
                        goal, state, nodes, result.plan
                    )
            result.plan_id = result.plan_id or self._new_plan_id()
            result.goal = result.goal or goal
            result.current_state = dict(state)
            result.execution_time = time.perf_counter() - started
            self._record_planning_history(goal, state, result, "planner")
            return result
        except Exception as exc:
            logger.exception("[PLANNER] Error de planificación")
            return self._failure_result(
                f"Error de planificación: {exc}", goal, state, started
            )

    def _plan_with_optional_optimization(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
        use_optimization: bool,
    ) -> PlanningResult:
        if use_optimization:
            self._ensure_optimization_systems()
            if self.optimization_manager is not None:
                try:
                    optimized = self.optimization_manager.optimize_planning(
                        goal, current_state, available_nodes, max_planning_time
                    )
                    if isinstance(optimized, PlanningResult):
                        return optimized
                    if isinstance(optimized, dict) and "status" in optimized:
                        status = self._status_value(optimized.get("status"))
                        return PlanningResult(
                            status=PlannerStatus.COMPLETED
                            if status in {"completed", "success"}
                            else PlannerStatus.FAILED,
                            plan=self._normalize_dict_plan(optimized.get("plan", [])),
                            goal=goal,
                            current_state=dict(current_state),
                            warnings=list(optimized.get("warnings", []) or []),
                            metadata={"optimized": True},
                        )
                except Exception as exc:
                    logger.warning(
                        "[PLANNER] Optimización no disponible; continúa planificación base: %s",
                        exc,
                    )
        if self.state_graph is not None and self.use_astar:
            return self._create_plan_astar(
                goal, current_state, available_nodes, max_planning_time
            )
        return self._create_plan(
            goal, current_state, available_nodes, max_planning_time
        )

    def _create_plan_astar(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
    ) -> PlanningResult:
        if self._is_goal_achieved(goal, current_state):
            return PlanningResult(
                status=PlannerStatus.COMPLETED,
                plan=[],
                goal=goal,
                current_state=dict(current_state),
                quality=PlanQuality.OPTIMAL,
                metadata={"message": "Objetivo ya alcanzado", "algorithm": "none"},
            )
        if self.state_graph is None:
            return self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )

        start_id = self._get_start_node_for_goal(goal, current_state)
        goal_id = self._get_goal_node_for_goal(goal)
        if not start_id or not goal_id:
            fallback = self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )
            fallback.warnings.insert(
                0,
                f"No se pudieron resolver extremos de A*: start={start_id}, goal={goal_id}",
            )
            fallback.metadata.setdefault("algorithm_fallback", "deterministic")
            return fallback

        max_iterations = self._time_budget_to_iterations(max_planning_time)
        try:
            try:
                route = self.state_graph.find_route(
                    start_id,
                    goal_id,
                    current_state,
                    strategy=SearchStrategy.A_STAR,
                    max_iterations=max_iterations,
                    find_alternatives=False,
                )
                path, total_cost, alternatives, metadata = self._normalize_route_result(
                    route
                )
            except TypeError:
                raw = self.state_graph.find_path_astar(
                    start_id,
                    goal_id,
                    current_state,
                    max_iterations=max_iterations,
                    find_alternatives=False,
                )
                path, total_cost, alternatives, metadata = self._normalize_route_result(
                    raw
                )
        except Exception as exc:
            logger.exception("[PLANNER] Error en A*")
            fallback = self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )
            fallback.warnings.insert(0, f"Error en A*: {exc}")
            fallback.metadata.setdefault("algorithm_fallback", "deterministic")
            return fallback

        if not path:
            fallback = self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )
            fallback.warnings.insert(0, "No se encontró una ruta con A*")
            fallback.metadata.setdefault("algorithm_fallback", "deterministic")
            fallback.metadata.update({"start_node": start_id, "goal_node": goal_id})
            return fallback

        plan = self._convert_path_to_plan(path, available_nodes)
        if not plan and not self._is_goal_achieved(goal, current_state):
            fallback = self._create_plan(
                goal, current_state, available_nodes, max_planning_time
            )
            fallback.warnings.insert(0, "La ruta no contiene acciones planificables")
            fallback.metadata.setdefault("algorithm_fallback", "deterministic")
            return fallback
        return PlanningResult(
            status=PlannerStatus.COMPLETED,
            plan=plan,
            goal=goal,
            current_state=dict(current_state),
            quality=self._evaluate_plan_quality(plan, current_state, goal),
            alternatives=self._normalize_alternative_plans(
                alternatives, available_nodes
            ),
            metadata={
                **metadata,
                "algorithm": "A*",
                "path": path,
                "total_cost": total_cost,
                "start_node": start_id,
                "goal_node": goal_id,
            },
        )

    def _create_plan(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        max_planning_time: float,
    ) -> PlanningResult:
        del (
            max_planning_time
        )  # Esta estrategia es determinista y no consume un solver temporal.
        if self._is_goal_achieved(goal, current_state):
            return PlanningResult(
                status=PlannerStatus.COMPLETED,
                plan=[],
                goal=goal,
                current_state=dict(current_state),
                quality=PlanQuality.OPTIMAL,
                metadata={
                    "message": "Objetivo ya alcanzado",
                    "algorithm": "deterministic",
                },
            )
        required_capabilities = self._safe_required_capabilities(goal)
        plan = self._build_hierarchical_plan(
            goal, current_state, available_nodes, required_capabilities
        )
        if not plan:
            return PlanningResult(
                status=PlannerStatus.FAILED,
                goal=goal,
                current_state=dict(current_state),
                warnings=["No se pudo construir un plan válido"],
                metadata={
                    "algorithm": "deterministic",
                    "capabilities_requested": required_capabilities,
                },
            )
        return PlanningResult(
            status=PlannerStatus.COMPLETED,
            plan=plan,
            goal=goal,
            current_state=dict(current_state),
            quality=self._evaluate_plan_quality(plan, current_state, goal),
            metadata={
                "algorithm": "deterministic",
                "plan_length": len(plan),
                "total_cost": sum(
                    _finite_nonnegative(node.get("cost", 1.0), 1.0) for node in plan
                ),
                "capabilities_used": required_capabilities,
            },
        )

    # ==================================================================
    # NODOS / RUTAS
    # ==================================================================

    def _get_available_nodes(self) -> Dict[str, Node]:
        nodes = dict(self.available_nodes)
        if not nodes:
            nodes = self._create_compatibility_nodes()
            self.available_nodes.update(nodes)
        try:
            self.load_application_knowledge()
        except Exception as exc:
            logger.debug("[PLANNER] Conocimiento de aplicaciones no cargado: %s", exc)
        return dict(self.available_nodes)

    def _create_compatibility_nodes(self) -> Dict[str, Node]:
        """Nodos mínimos de compatibilidad; no representan ejecución ya realizada."""
        return {
            "chrome.closed": Node(
                id="chrome.closed",
                type=NodeType.STATE,
                name="Chrome cerrado",
                description="Estado inicial de Chrome",
                effects=["chrome_closed"],
                metadata={"application": "chrome", "state": "closed"},
            ),
            "chrome.open": Node(
                id="chrome.open",
                type=NodeType.ACTION,
                name="Abrir Chrome",
                preconditions=["application_available"],
                effects=["chrome_open"],
                cost=10.0,
                application="chrome",
                action_category="open_application",
                parameters={"application": "chrome"},
            ),
            "chrome.activate": Node(
                id="chrome.activate",
                type=NodeType.ACTION,
                name="Activar Chrome",
                preconditions=["chrome_open"],
                effects=["chrome_active"],
                cost=2.0,
                application="chrome",
                action_category="activate_window",
            ),
            "focus_address_bar": Node(
                id="focus_address_bar",
                type=NodeType.ACTION,
                name="Enfocar barra de dirección",
                preconditions=["chrome_active"],
                effects=["address_bar_focused"],
                cost=1.0,
                application="chrome",
                ui_element="address_bar",
                action_category="focus_element",
            ),
            "click_address_bar": Node(
                id="click_address_bar",
                type=NodeType.ACTION,
                name="Click en barra de dirección",
                preconditions=["chrome_active"],
                effects=["address_bar_focused"],
                cost=1.5,
                application="chrome",
                ui_element="address_bar",
                action_category="focus_element",
            ),
            "hotkey_ctrl_l": Node(
                id="hotkey_ctrl_l",
                type=NodeType.ACTION,
                name="Atajo Ctrl+L",
                preconditions=["chrome_active"],
                effects=["address_bar_focused"],
                cost=0.5,
                application="chrome",
                action_category="focus_element",
                metadata={"hotkey": ["ctrl", "l"]},
            ),
            "type_url": Node(
                id="type_url",
                type=NodeType.ACTION,
                name="Escribir URL",
                preconditions=["address_bar_focused"],
                effects=["url_typed"],
                cost=1.0,
                application="chrome",
                ui_element="address_bar",
                action_category="type_text",
            ),
            "press_enter": Node(
                id="press_enter",
                type=NodeType.ACTION,
                name="Presionar Enter",
                preconditions=["url_typed"],
                effects=["destination_loaded", "url_changed"],
                cost=1.0,
                application="chrome",
                action_category="press_key",
            ),
            "search_google": Node(
                id="search_google",
                type=NodeType.ACTION,
                name="Buscar en Google",
                preconditions=["chrome_active"],
                effects=["search_performed"],
                cost=3.0,
                application="chrome",
                action_category="search",
                metadata={"search_engine": "google"},
            ),
        }

    def _get_start_node_for_goal(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> Optional[str]:
        if self.state_graph is None:
            return None
        nodes = self.state_graph.nodes
        goal_type = str(getattr(goal, "type", "")).lower()
        target = self._goal_target_string(goal)
        app = (
            self._normalize_identifier(target)
            if goal_type in {"open_application", "close_application"}
            else "chrome"
        )

        # Priorizar estados explícitos del contexto en vez de elegir el primer nodo.
        state_candidates: List[Tuple[int, str]] = []
        for node_id, node in nodes.items():
            if self._node_type_value(node) != "state":
                continue
            score = 0
            metadata = getattr(node, "metadata", {}) or {}
            metadata_app = (
                self._normalize_identifier(metadata.get("application", ""))
                if isinstance(metadata, dict)
                else ""
            )
            state_value = (
                str(metadata.get("state", "")).lower()
                if isinstance(metadata, dict)
                else ""
            )
            if metadata_app and app and metadata_app == app:
                score += 1
            if self._state_node_matches_context(node, current_state):
                score += 20
            if metadata_app and state_value:
                positive_key = f"{metadata_app}_{state_value.replace(' ', '_')}"
                if positive_key in current_state:
                    expected = bool(current_state[positive_key])
                    if expected:
                        score += 12
                    else:
                        score -= 4
                opposite = {
                    "open": "closed",
                    "closed": "open",
                    "active": "inactive",
                    "inactive": "active",
                }.get(state_value)
                if (
                    opposite
                    and f"{metadata_app}_{opposite}" in current_state
                    and current_state[f"{metadata_app}_{opposite}"]
                ):
                    score -= 8
            fact_names = self._node_state_facts(node)
            for key, value in current_state.items():
                if value and str(key).lower() in fact_names:
                    score += 2
            if state_value and current_state.get(f"{metadata_app}_{state_value}"):
                score += 8
            if score > 1:
                state_candidates.append((score, node_id))
        if state_candidates:
            state_candidates.sort(key=lambda item: (-item[0], item[1]))
            return state_candidates[0][1]

        compatibility_candidates = []
        if goal_type in {"navigate", "navigate_stream", "search"}:
            if current_state.get("chrome_active"):
                compatibility_candidates.append("chrome.activate")
            if current_state.get("chrome_open"):
                compatibility_candidates.append("chrome.open")
            compatibility_candidates.append("chrome.closed")
        elif goal_type in {"open_application", "close_application"}:
            compatibility_candidates.extend(
                (f"{app}.closed", f"{app}.open", f"{app}.active")
            )
        for candidate in compatibility_candidates:
            if candidate in nodes and self._node_type_value(nodes[candidate]) in {
                "state",
                "action",
            }:
                return candidate
        return None

    def _get_goal_node_for_goal(self, goal: Goal) -> Optional[str]:
        if self.state_graph is None:
            return None
        nodes = self.state_graph.nodes
        goal_type = str(getattr(goal, "type", "")).lower()
        target = self._goal_target_string(goal).lower()
        candidates: List[Tuple[float, str]] = []
        for node_id, node in nodes.items():
            node_type = self._node_type_value(node)
            if node_type in {
                "goal",
                "intention",
                "plan",
                "resource",
                "application",
                "ui_element",
            }:
                # Un nodo Goal no se considera destino salvo que tenga una
                # transición entrante explícita y no haya mejor terminal de acción.
                if node_type == "goal" and self._has_incoming_edge(node_id):
                    pass
                else:
                    continue
            effects = getattr(node, "effects", []) or []
            if not self._goal_satisfied_by_effects(
                effects, goal
            ) and not self._node_can_satisfy_goal(node, goal):
                continue
            score = 0.0
            low_id = node_id.lower()
            low_name = str(getattr(node, "name", "")).lower()
            if goal_type and goal_type in low_id:
                score += 5
            if goal_type and goal_type in low_name:
                score += 3
            if target and target in low_id:
                score += 4
            if target and target in low_name:
                score += 2
            if self._goal_satisfied_by_effects(effects, goal):
                score += 8
            if node_type == "action":
                score += 3
            elif node_type == "task":
                score += 2
            elif node_type == "state":
                score += 1
            candidates.append((score, node_id))
        if candidates:
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]

        # Compatibilidad: solo se acepta un ID legacy si existe realmente.
        for candidate in {
            "navigate": ("press_enter", "destination.loaded"),
            "navigate_stream": ("press_enter", "destination.loaded"),
            "search": ("search_google",),
            "open_application": ("chrome.activate", "chrome.open"),
            "close_application": ("chrome.closed",),
        }.get(goal_type, ()):
            if candidate in nodes:
                return candidate
        return None

    def _convert_path_to_plan(
        self, path: Sequence[str], available_nodes: Dict[str, Node]
    ) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        for node_id in path:
            node = available_nodes.get(node_id)
            if node is None and self.state_graph is not None:
                node = self.state_graph.nodes.get(node_id)
            if node is None:
                logger.warning(
                    "[PLANNER] La ruta contiene un nodo ausente: %s", node_id
                )
                continue
            if self._node_type_value(node) not in {"action", "task"}:
                continue
            plan.append(self._convert_node_to_execution_node(node))
        return plan

    def _convert_node_to_execution_node(self, node: Node) -> Dict[str, Any]:
        node_id = str(getattr(node, "id", ""))
        parameters = getattr(node, "parameters", {}) or {}
        metadata = getattr(node, "metadata", {}) or {}
        execution_node: Dict[str, Any] = {
            "id": node_id,
            "name": str(getattr(node, "name", node_id)),
            "action": node_id,
            "description": str(getattr(node, "description", "")),
            "type": self._node_type_value(node),
            "parameters": copy.deepcopy(parameters)
            if isinstance(parameters, dict)
            else {},
            "preconditions": _as_values(getattr(node, "preconditions", [])),
            "effects": _as_values(getattr(node, "effects", [])),
            "cost": _finite_nonnegative(getattr(node, "cost", 1.0), 1.0),
            "application": getattr(node, "application", None),
            "ui_element": getattr(node, "ui_element", None),
            "alternatives": [],
        }
        if isinstance(metadata, dict) and metadata:
            execution_node["metadata"] = copy.deepcopy(metadata)
        if execution_node["ui_element"]:
            resource_id = f"{execution_node['application'] or 'unknown'}.{execution_node['ui_element']}"
            execution_node["ui_resource_id"] = resource_id
            manager = self.coordinate_manager
            if manager is not None:
                try:
                    strategy = getattr(
                        manager, "get_execution_strategy_for_action", None
                    )
                    if callable(strategy):
                        execution_node["ui_strategy"] = strategy(node_id, resource_id)
                    alternatives = getattr(manager, "get_resource_alternatives", None)
                    if callable(alternatives):
                        execution_node["ui_alternatives"] = alternatives(resource_id)
                except Exception as exc:
                    logger.debug(
                        "[PLANNER] No se pudo resolver estrategia UI %s: %s",
                        resource_id,
                        exc,
                    )
        return execution_node

    # ==================================================================
    # PLAN DETERMINISTA
    # ==================================================================

    def _build_hierarchical_plan(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        required_capabilities: List[str],
    ) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        simulated_state = copy.deepcopy(current_state)
        used_ids: set[str] = set()
        for capability in required_capabilities:
            candidates = self._find_nodes_for_capability(
                capability, available_nodes, simulated_state
            )
            best = self._select_best_node(candidates, simulated_state)
            if best is None:
                # Una capacidad puede ser redundante si el estado actual ya
                # demuestra su efecto; no se inventa una acción para suplirla.
                if self._capability_already_satisfied(capability, simulated_state):
                    continue
                continue
            if best.id in used_ids:
                continue
            item = self._convert_node_to_execution_node(best)
            plan.append(item)
            used_ids.add(best.id)
            simulated_state = self._apply_declared_effects(
                simulated_state, getattr(best, "effects", [])
            )

        if not plan:
            related = [
                node
                for node in available_nodes.values()
                if self._node_can_satisfy_goal(node, goal)
                and self._node_type_value(node) in {"action", "task"}
            ]
            best = self._select_best_node(related, current_state)
            if best is not None:
                plan.append(self._convert_node_to_execution_node(best))
        return self._optimize_plan(plan, current_state)

    def _find_nodes_for_capability(
        self,
        capability: str,
        available_nodes: Dict[str, Node],
        current_state: Dict[str, Any],
    ) -> List[Node]:
        result: List[Node] = []
        for node in available_nodes.values():
            if self._node_type_value(node) not in {"action", "task"}:
                continue
            try:
                checker = getattr(node, "can_execute", None)
                if callable(checker) and not checker(current_state):
                    continue
            except Exception:
                # Una API legacy de validación no debe convertir una excepción
                # en permiso para añadir la acción al plan.
                continue
            if self._node_provides_capability(node, capability):
                result.append(node)
        return result

    def _node_provides_capability(self, node: Node, capability: str) -> bool:
        requested = _slug(capability)
        if not requested:
            return False
        node_id = _slug(getattr(node, "id", ""))
        action_category = _slug(getattr(node, "action_category", ""))
        name = _slug(getattr(node, "name", ""))
        metadata = getattr(node, "metadata", {}) or {}
        raw_capabilities = (
            metadata.get("capabilities", []) if isinstance(metadata, dict) else []
        )
        declared = {_slug(item) for item in _as_values(raw_capabilities)}
        if isinstance(metadata, dict) and metadata.get("capability") is not None:
            declared.add(_slug(metadata["capability"]))
        aliases = {
            "activate_window": {"activate", "activate_window", "focus_window"},
            "open_application": {"open", "launch", "open_application"},
            "close_application": {"close", "close_application", "quit"},
            "focus_element": {"focus", "click", "focus_element"},
            "type_text": {"type", "write", "type_text"},
            "press_key": {"press", "key", "press_key"},
            "navigate": {"navigate", "browse", "open_url"},
        }
        accepted = aliases.get(requested, {requested})
        all_labels = {node_id, action_category, name, *declared}
        if accepted.intersection(all_labels):
            return True
        tokens = (
            set(node_id.split("_"))
            | set(action_category.split("_"))
            | set(name.split("_"))
        )
        if any(alias in tokens for alias in accepted):
            return True
        # La aplicación solo identifica al proveedor; no implica que toda acción
        # de esa aplicación implemente cualquier capacidad solicitada.
        return False

    def _select_best_node(
        self, nodes: List[Node], current_state: Dict[str, Any]
    ) -> Optional[Node]:
        if not nodes:
            return None
        scored: List[Tuple[float, str, Node]] = []
        for node in nodes:
            score = -_finite_nonnegative(getattr(node, "cost", 1.0), 1.0) * 0.1
            score += _finite_float(getattr(node, "success_rate", 0.0), 0.0) * 10.0
            score -= (
                _finite_nonnegative(getattr(node, "average_execution_time", 0.0), 0.0)
                * 0.5
            )
            app = getattr(node, "application", None)
            if app and current_state.get(
                f"{self._normalize_identifier(app)}_open", False
            ):
                score += 5.0
            ui_element = getattr(node, "ui_element", None)
            manager = self.coordinate_manager
            if ui_element and app and manager is not None:
                resource_id = f"{app}.{ui_element}"
                try:
                    if manager.has_resource(resource_id):
                        score += 8.0
                    else:
                        score -= 3.0
                    fallbacks = getattr(
                        manager, "get_fallback_strategies", lambda _rid: []
                    )(resource_id)
                    score += min(3, len(fallbacks or [])) * 0.5
                except Exception:
                    pass
            scored.append((score, str(getattr(node, "id", "")), node))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][2]

    def _optimize_plan(
        self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        del current_state
        # Solo se quitan pasos idénticos consecutivos. Repetir una acción en otra
        # posición puede ser deliberado y por tanto no es una redundancia segura.
        result: List[Dict[str, Any]] = []
        previous_signature = None
        for node in plan:
            if not isinstance(node, dict):
                continue
            signature = (
                node.get("id"),
                repr(node.get("parameters", {})),
                node.get("action"),
            )
            if signature == previous_signature:
                continue
            result.append(node)
            previous_signature = signature
        return result

    # ==================================================================
    # UI / COORDENADAS
    # ==================================================================

    def validate_ui_resources_for_plan(
        self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        del current_state
        result: Dict[str, Any] = {
            "total_nodes": len(plan),
            "ui_nodes": 0,
            "available_resources": 0,
            "missing_resources": 0,
            "alternative_strategies": 0,
            "needs_manual_calibration": [],
            "resource_status": {},
            "recommendations": [],
        }
        manager = self.coordinate_manager
        for node in plan:
            if not isinstance(node, dict) or not node.get("ui_element"):
                continue
            result["ui_nodes"] += 1
            app = node.get("application") or "unknown"
            resource_id = f"{app}.{node['ui_element']}"
            try:
                available = bool(manager and manager.has_resource(resource_id))
            except Exception:
                available = False
            if available:
                result["available_resources"] += 1
                result["resource_status"][resource_id] = "available"
                try:
                    result["alternative_strategies"] += len(
                        manager.get_fallback_strategies(resource_id) or []
                    )
                except Exception:
                    pass
                continue
            result["missing_resources"] += 1
            result["resource_status"][resource_id] = "missing"
            try:
                can_calibrate = bool(
                    manager and manager.can_calibrate_element(app, node["ui_element"])
                )
            except Exception:
                can_calibrate = False
            if can_calibrate:
                result["recommendations"].append(
                    f"Calibrar automáticamente: {resource_id}"
                )
            else:
                result["needs_manual_calibration"].append(resource_id)
                result["recommendations"].append(
                    f"Requiere calibración manual: {resource_id}"
                )
        return result

    def get_optimal_ui_strategy(
        self, action_id: str, resource_id: Optional[str] = None
    ) -> Dict[str, Any]:
        manager = self.coordinate_manager
        if manager is None:
            return {
                "action_id": action_id,
                "resource_id": resource_id,
                "resource_available": False,
                "priority": "low",
                "warning": "CoordinateManager no disponible",
            }
        try:
            strategy = manager.get_execution_strategy_for_action(action_id, resource_id)
            strategy = (
                dict(strategy) if isinstance(strategy, dict) else {"strategy": strategy}
            )
            if strategy.get("resource_available"):
                priority = "high"
            elif strategy.get("alternative_resources") or strategy.get(
                "alternative_methods"
            ):
                priority = "medium"
            else:
                priority = "low"
            strategy["priority"] = priority
            return strategy
        except Exception as exc:
            logger.warning("[PLANNER] Error obteniendo estrategia UI: %s", exc)
            return {
                "action_id": action_id,
                "resource_id": resource_id,
                "priority": "low",
                "error": str(exc),
            }

    def resolve_ui_conflicts(
        self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        del current_state
        resolved: List[Dict[str, Any]] = []
        manager = self.coordinate_manager
        for node in plan:
            if not isinstance(node, dict):
                continue
            ui_element = node.get("ui_element")
            app = node.get("application") or "unknown"
            if not ui_element or manager is None:
                resolved.append(node)
                if ui_element and manager is None:
                    unresolved = dict(node)
                    unresolved["ui_resolution_required"] = True
                    if resolved[-1] is node:
                        resolved[-1] = unresolved
                continue
            resource_id = f"{app}.{ui_element}"
            try:
                if manager.has_resource(resource_id):
                    resolved.append(node)
                    continue
                alternatives = manager.get_resource_alternatives(resource_id) or []
                if alternatives:
                    alt = dict(node)
                    alternative = alternatives[0]
                    alt["ui_element"] = getattr(alternative, "element_type", ui_element)
                    alt["ui_resource_id"] = getattr(alternative, "id", resource_id)
                    alt["strategy"] = "alternative_resource"
                    resolved.append(alt)
                    continue
                fallbacks = manager.get_fallback_strategies(resource_id) or []
                if fallbacks:
                    alt = dict(node)
                    alt["strategy"] = "alternative_method"
                    alt["fallback_method"] = fallbacks[0]
                    alt["cost"] = _finite_nonnegative(alt.get("cost", 1.0), 1.0) + 1.0
                    resolved.append(alt)
                    continue
            except Exception as exc:
                logger.debug("[PLANNER] Error resolviendo UI %s: %s", resource_id, exc)
            unresolved = dict(node)
            unresolved["ui_resolution_required"] = True
            resolved.append(unresolved)
        return resolved

    def check_ui_readiness(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Optional[Dict[str, Node]] = None,
    ) -> Dict[str, Any]:
        readiness: Dict[str, Any] = {
            "goal": getattr(goal, "id", None),
            "ui_ready": True,
            "missing_resources": [],
            "calibration_needed": [],
            "alternative_strategies": [],
            "recommendations": [],
        }
        manager = self.coordinate_manager
        nodes_map = (
            dict(available_nodes)
            if available_nodes is not None
            else dict(self.available_nodes)
        )
        for capability in self._safe_required_capabilities(goal):
            nodes = self._find_nodes_for_capability(
                capability, nodes_map, current_state
            )
            for node in nodes:
                app = getattr(node, "application", None)
                ui_element = getattr(node, "ui_element", None)
                if not app or not ui_element:
                    continue
                resource_id = f"{app}.{ui_element}"
                try:
                    if manager is not None and manager.has_resource(resource_id):
                        continue
                    readiness["ui_ready"] = False
                    if resource_id not in readiness["missing_resources"]:
                        readiness["missing_resources"].append(resource_id)
                    can_calibrate = bool(
                        manager and manager.can_calibrate_element(app, ui_element)
                    )
                    if can_calibrate:
                        readiness["calibration_needed"].append(resource_id)
                        readiness["recommendations"].append(
                            f"Auto-calibrar: {resource_id}"
                        )
                    else:
                        readiness["recommendations"].append(
                            f"Requiere calibración manual: {resource_id}"
                        )
                    if manager is not None:
                        readiness["alternative_strategies"].extend(
                            manager.get_fallback_strategies(resource_id) or []
                        )
                except Exception:
                    readiness["ui_ready"] = False
                    if resource_id not in readiness["missing_resources"]:
                        readiness["missing_resources"].append(resource_id)
        return readiness

    # ==================================================================
    # PLANES ALTERNATIVOS
    # ==================================================================

    def _find_alternative_plans_astar(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        original_plan: List[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        del goal
        alternatives: List[List[Dict[str, Any]]] = []
        for index, original_node in enumerate(original_plan):
            capability = str(original_node.get("action", original_node.get("id", "")))
            candidates = [
                node
                for node in available_nodes.values()
                if str(node.id) != str(original_node.get("id"))
                and self._node_type_value(node) in {"action", "task"}
                and self._same_capability_or_category(node, original_node)
            ]
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    _finite_nonnegative(getattr(item, "cost", 1.0), 1.0),
                    str(item.id),
                ),
            )[:2]:
                if not self._candidate_preconditions_compatible(
                    candidate, current_state, original_plan[:index]
                ):
                    continue
                alt_plan = (
                    list(original_plan[:index])
                    + [self._convert_node_to_execution_node(candidate)]
                    + list(original_plan[index + 1 :])
                )
                if alt_plan != original_plan and alt_plan not in alternatives:
                    alternatives.append(alt_plan)
                if len(alternatives) >= 3:
                    return alternatives
        return alternatives

    def _find_alternatives_for_node(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Dict[str, Node],
        original_plan: List[Dict[str, Any]],
        original_node: Dict[str, Any],
        position: int,
    ) -> List[List[Dict[str, Any]]]:
        del goal
        results: List[List[Dict[str, Any]]] = []
        for candidate in available_nodes.values():
            if str(candidate.id) == str(
                original_node.get("id")
            ) or self._node_type_value(candidate) not in {"action", "task"}:
                continue
            if not self._same_capability_or_category(candidate, original_node):
                continue
            if not self._candidate_preconditions_compatible(
                candidate, current_state, original_plan[:position]
            ):
                continue
            alt_plan = (
                list(original_plan[:position])
                + [self._convert_node_to_execution_node(candidate)]
                + list(original_plan[position + 1 :])
            )
            if alt_plan != original_plan:
                results.append(alt_plan)
        return results[:3]

    def _select_best_alternative(
        self,
        alternatives: List[List[Dict[str, Any]]],
        current_state: Dict[str, Any],
        goal: Goal,
        original_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        del goal
        if not alternatives:
            return []
        original = original_plan or current_state.get("original_plan", [])
        scored: List[Tuple[float, int, List[Dict[str, Any]]]] = []
        for plan in alternatives:
            cost = sum(_finite_nonnegative(node.get("cost", 1.0), 1.0) for node in plan)
            similarity = self._calculate_plan_similarity(plan, original)
            compatibility = self._calculate_state_compatibility(plan, current_state)
            score = -(cost * 0.1) + similarity * 10.0 + compatibility * 5.0
            scored.append((score, len(plan), plan))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][2]

    def _calculate_plan_similarity(
        self, alt_plan: List[Dict[str, Any]], original_plan: List[Dict[str, Any]]
    ) -> float:
        if not original_plan:
            return 1.0 if not alt_plan else 0.0
        compare_count = min(len(alt_plan), len(original_plan))
        matches = sum(
            1
            for index in range(compare_count)
            if alt_plan[index].get("action") == original_plan[index].get("action")
        )
        return matches / max(1, len(original_plan))

    def _calculate_state_compatibility(
        self, plan: List[Dict[str, Any]], current_state: Dict[str, Any]
    ) -> float:
        # Simula efectos declarativos en una copia para no puntuar cada paso contra
        # un estado congelado que aún no incluye los efectos de pasos anteriores.
        state = copy.deepcopy(current_state)
        checks = matches = 0
        for node in plan:
            for condition in node.get("preconditions", []) or []:
                checks += 1
                if self._evaluate_condition_with_state(condition, state):
                    matches += 1
            state = self._apply_declared_effects(state, node.get("effects", []))
        return matches / checks if checks else 1.0

    def _evaluate_condition_with_state(
        self, condition: Any, state: Dict[str, Any]
    ) -> bool:
        if isinstance(condition, dict):
            key = condition.get(
                "key", condition.get("state_key", condition.get("name"))
            )
            if not key:
                return False
            expected = condition.get("value", condition.get("equals", True))
            return state.get(str(key)) == expected
        if not isinstance(condition, str):
            return False
        condition = condition.strip()
        if not condition:
            return True
        if condition.startswith("not "):
            return not self._evaluate_condition_with_state(condition[4:].strip(), state)
        if condition in state:
            return bool(state[condition])
        app_states = state.get("application_states", {})
        if isinstance(app_states, dict):
            for prefix in ("chrome_", "app_"):
                if condition.startswith(prefix):
                    app_key, _, state_key = condition[len(prefix) :].partition("_")
                    candidate = app_states.get(app_key)
                    if isinstance(candidate, dict) and state_key:
                        return bool(candidate.get(state_key, False))
        if condition.startswith("ui_"):
            ui = state.get("ui_elements", {})
            return (
                isinstance(ui, dict) and condition[3:] in ui and bool(ui[condition[3:]])
            )
        # Desconocido no equivale a verdadero: una alternativa con precondiciones
        # que no se pueden comprobar no obtiene una puntuación artificial.
        return False

    # ==================================================================
    # REPLANIFICACIÓN
    # ==================================================================

    def replan(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        failed_plan: List[Dict[str, Any]],
        failed_node_index: int,
    ) -> PlanningResult:
        state = self._normalize_state(current_state)
        if failed_node_index < 0 or failed_node_index >= len(failed_plan):
            return PlanningResult(
                status=PlannerStatus.FAILED,
                goal=goal,
                current_state=state,
                warnings=["Índice de nodo fallido inválido"],
            )
        failed_node = failed_plan[failed_node_index]
        alternatives = self._find_alternatives_for_node(
            goal,
            state,
            self._get_available_nodes(),
            failed_plan,
            failed_node,
            failed_node_index,
        )
        if alternatives:
            best = self._select_best_alternative(
                alternatives, state, goal, original_plan=failed_plan
            )
            if best:
                return PlanningResult(
                    status=PlannerStatus.COMPLETED,
                    plan=best,
                    plan_id=self._new_plan_id(),
                    goal=goal,
                    current_state=state,
                    quality=PlanQuality.SUBOPTIMAL,
                    alternatives=alternatives,
                    metadata={
                        "replan_from": failed_node.get("id"),
                        "alternatives_count": len(alternatives),
                        "replan_reason": "node_failure",
                        "partial_replan": True,
                    },
                )
        logger.info(
            "[PLANNER] Sin alternativa local; se intenta una planificación completa"
        )
        return self.plan(
            goal,
            state,
            self._get_available_nodes(),
            max_planning_time=15.0,
            find_alternatives=True,
        )

    # ==================================================================
    # CALIDAD / COSTES
    # ==================================================================

    def _evaluate_plan_quality(
        self, plan: List[Dict[str, Any]], current_state: Dict[str, Any], goal: Goal
    ) -> PlanQuality:
        del current_state, goal
        if not plan:
            return PlanQuality.OPTIMAL
        total_cost = sum(
            _finite_nonnegative(node.get("cost", 1.0), 1.0) for node in plan
        )
        if len(plan) <= 3 and total_cost <= 5:
            return PlanQuality.OPTIMAL
        if len(plan) <= 5 and total_cost <= 10:
            return PlanQuality.SUBOPTIMAL
        return PlanQuality.MINIMAL

    def _optimize_integrated_plan(
        self, result: PlanningResult, current_state: Dict[str, Any], goal: Goal
    ) -> PlanningResult:
        del current_state, goal
        original_length = len(result.plan)
        result.plan = self._remove_redundancies(result.plan)
        result.plan = self._apply_learned_cost_adjustments(result.plan)
        result.metadata["optimized"] = True
        result.metadata["original_length"] = original_length
        result.metadata["optimized_length"] = len(result.plan)
        return result

    @staticmethod
    def _remove_redundancies(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        previous_key = None
        for node in plan:
            key = (node.get("id"), repr(node.get("parameters", {})), node.get("action"))
            if result and key == previous_key:
                continue
            result.append(node)
            previous_key = key
        return result

    def _apply_learned_cost_adjustments(
        self, plan: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        adjustments = self.get_cost_adjustments()
        if not adjustments:
            return [dict(node) for node in plan]
        updated: List[Dict[str, Any]] = []
        for node in plan:
            item = dict(node)
            action = str(item.get("action", item.get("id", "")))
            if action in adjustments:
                item["cost"] = max(
                    0.0,
                    _finite_nonnegative(item.get("cost", 1.0), 1.0)
                    + adjustments[action],
                )
            updated.append(item)
        return updated

    def _ensure_optimization_systems(self) -> None:
        if self.learning_system is None:
            try:
                try:
                    from src.hands.planner.learning_system import LearningSystem
                except ImportError:
                    from src.hands.planner.learning_system import LearningSystem
                self.learning_system = LearningSystem()
            except Exception as exc:
                logger.debug("[PLANNER] LearningSystem no disponible: %s", exc)
        if self.optimization_manager is None:
            try:
                try:
                    from src.hands.planner.optimization import OptimizationManager
                except ImportError:
                    from src.hands.planner.optimization import OptimizationManager
                self.optimization_manager = OptimizationManager(self)
            except Exception as exc:
                logger.debug("[PLANNER] OptimizationManager no disponible: %s", exc)

    # ==================================================================
    # APLICACIONES
    # ==================================================================

    def load_application_knowledge(self) -> None:
        integrator = self.application_integrator
        if integrator is None:
            return
        try:
            manager = getattr(integrator, "application_manager", None)
            applications = getattr(manager, "applications", {}) or {}
            if not isinstance(applications, dict):
                logger.warning(
                    "[PLANNER] El gestor de aplicaciones no expone un diccionario applications"
                )
                return
        except Exception as exc:
            logger.warning(
                "[PLANNER] No se pudo acceder al conocimiento de aplicaciones: %s", exc
            )
            return
        for app_name in applications:
            try:
                nodes = integrator.convert_application_to_nodes(str(app_name)) or []
                for node in nodes:
                    node_id = getattr(node, "id", None)
                    if isinstance(node_id, str) and node_id.strip():
                        self.available_nodes[node_id] = node
            except Exception as exc:
                logger.warning(
                    "[PLANNER] Error cargando aplicación %s: %s", app_name, exc
                )

    def get_applications_by_capability(self, capability_name: str) -> List[str]:
        integrator = self.application_integrator
        if integrator is None:
            return []
        try:
            try:
                from src.hands.applications_core import ApplicationCapability
            except ImportError:
                from src.hands.applications_core import ApplicationCapability
            capability = ApplicationCapability(capability_name)
            return list(integrator.get_applications_by_capability(capability) or [])
        except Exception as exc:
            logger.warning("[PLANNER] Capacidad no válida %s: %s", capability_name, exc)
            try:
                return list(
                    integrator.get_applications_by_capability(capability_name) or []
                )
            except Exception:
                return []

    def get_application_capabilities(self, app_name: str) -> Dict[str, Any]:
        if self.application_integrator is None:
            return {}
        try:
            capabilities = self.application_integrator.get_application_capabilities(
                app_name
            )
            return capabilities if isinstance(capabilities, dict) else {}
        except Exception as exc:
            logger.warning(
                "[PLANNER] Error obteniendo capacidades de %s: %s", app_name, exc
            )
            return {}

    def get_application_capabilities_as_list(self, app_name: str) -> List[str]:
        """Expone las capacidades de una aplicación en formato consumible por el
        planificador: una lista de identificadores canónicos de capacidad.

        Reutiliza el contrato canónico :meth:`get_application_capabilities` (no
        duplica lógica) y transforma ese dict —cuyas claves son nombres
        específicos de la aplicación— a una lista de los identificadores
        canónicos de capacidad (``descriptor["capability"]``) que el planificador
        consume en la fase de planificación. Normaliza con :func:`_slug` para
        coincidir con el vocabulario canónico usado en
        :meth:`_node_provides_capability`.

        Maneja el ausente —integrador no disponible, aplicación desconocida o
        aplicación conocida sin capacidades declaradas— devolviendo ``[]`` en
        lugar de lanzar ni devolver estructuras parciales.
        """
        capabilities = self.get_application_capabilities(app_name)
        if not isinstance(capabilities, dict) or not capabilities:
            return []
        identifiers: List[str] = []
        seen: set = set()
        for descriptor in capabilities.values():
            if not isinstance(descriptor, dict):
                continue
            identifier = _slug(descriptor.get("capability"))
            if identifier and identifier not in seen:
                identifiers.append(identifier)
                seen.add(identifier)
        return identifiers

    def find_application_for_goal(self, goal: Goal) -> Optional[str]:
        goal_type = str(getattr(goal, "type", "")).lower()
        type_mapping = {
            "navigate": ["browser"],
            "navigate_stream": ["browser", "streaming"],
            "search": ["browser", "media"],
            "play": ["media"],
            "open_application": ["desktop", "browser", "media"],
            "development": ["editor"],
            "streaming": ["streaming"],
        }
        try:
            manager = getattr(self.application_integrator, "application_manager", None)
            if manager is None:
                return None
            for app_type in type_mapping.get(goal_type, []):
                method = getattr(manager, "get_applications_by_type", None)
                apps = method(app_type) if callable(method) else []
                if apps:
                    name = getattr(apps[0], "name", None)
                    if name:
                        return str(name)
            apps = getattr(manager, "applications", {}) or {}
            if isinstance(apps, dict):
                requested = self._safe_required_capabilities(goal)
                for app_name, app in apps.items():
                    checker = getattr(app, "is_capable", None)
                    if not callable(checker):
                        continue
                    for capability in requested:
                        try:
                            if checker(capability):
                                return str(getattr(app, "name", app_name))
                        except Exception:
                            continue
        except Exception as exc:
            logger.debug("[PLANNER] Error buscando aplicación: %s", exc)
        return None

    def build_application_aware_plan(
        self, goal: Goal, current_state: Dict[str, Any]
    ) -> PlanningResult:
        self.load_application_knowledge()
        target_app = self.find_application_for_goal(goal)
        if not target_app:
            result = self._create_plan(
                goal,
                self._normalize_state(current_state),
                self._get_available_nodes(),
                30.0,
            )
            result.metadata["application_used"] = None
            result.metadata["application_capabilities"] = []
            return result
        normalized_app = _normalize_text(target_app)
        nodes = {
            node_id: node
            for node_id, node in self.available_nodes.items()
            if _normalize_text(getattr(node, "application", "")) == normalized_app
        }
        if not nodes:
            nodes = self._get_available_nodes()
        result = self._create_plan(
            goal, self._normalize_state(current_state), nodes, 30.0
        )
        result.metadata["application_used"] = target_app
        result.metadata["application_capabilities"] = (
            self.get_application_capabilities_as_list(target_app)
        )
        return result

    def is_application_available(self, app_name: str) -> bool:
        try:
            try:
                from src.hands.application_preflight import ApplicationPreflight
            except ImportError:
                from src.hands.application_preflight import ApplicationPreflight
            result = ApplicationPreflight().check(
                {"name": app_name, "executable": f"{app_name.lower()}.exe"}
            )
            return bool(isinstance(result, dict) and result.get("allowed", False))
        except Exception as exc:
            logger.warning("[PLANNER] Error verificando %s: %s", app_name, exc)
            return False

    def get_application_ui_requirements(
        self, app_name: str, capability: str
    ) -> List[str]:
        if self.application_integrator is None:
            return []
        try:
            try:
                from src.hands.applications_core import ApplicationCapability

                capability_obj: Any = ApplicationCapability(capability)
            except (ImportError, ValueError, TypeError):
                capability_obj = capability
            return list(
                self.application_integrator.get_ui_elements_for_capability(
                    app_name, capability_obj
                )
                or []
            )
        except Exception as exc:
            logger.warning("[PLANNER] Error obteniendo requisitos UI: %s", exc)
            return []

    # ==================================================================
    # ESTADÍSTICAS / DELEGACIÓN DE EJECUCIÓN COMPATIBLE
    # ==================================================================

    def get_planning_stats(self) -> Dict[str, Any]:
        if not self.planning_history:
            return {
                "total_plans": 0,
                "successful_plans": 0,
                "success_rate": 0.0,
                "average_planning_time": 0.0,
                "average_plan_length": 0.0,
                "last_planning": None,
            }
        history = list(self.planning_history)
        total = len(history)
        successful = sum(1 for item in history if item.get("success", False))
        return {
            "total_plans": total,
            "successful_plans": successful,
            "success_rate": successful / total,
            "average_planning_time": sum(
                _finite_nonnegative(item.get("execution_time", 0.0), 0.0)
                for item in history
            )
            / total,
            "average_plan_length": sum(
                int(item.get("plan_length", 0)) for item in history
            )
            / total,
            "last_planning": copy.deepcopy(history[-1]),
        }

    def execute_plan(
        self, plan: List[Dict[str, Any]], plan_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delegación explícita legacy. Nunca ejecuta acciones dentro del Planner."""
        if self.executor is None:
            return {
                "plan_id": plan_id,
                "execution_status": "not_executed",
                "execution_time": 0.0,
                "success": False,
                "error": "No hay executor configurado",
            }
        try:
            executor_method = getattr(self.executor, "execute_plan", None)
            if callable(executor_method):
                raw = executor_method(plan, plan_id=plan_id)
            elif callable(self.executor):
                raw = self.executor(plan)
            else:
                return {
                    "plan_id": plan_id,
                    "execution_status": "not_executed",
                    "execution_time": 0.0,
                    "success": False,
                    "error": "El executor no expone una API compatible",
                }
            if isinstance(raw, dict):
                success = bool(raw.get("success", False))
                elapsed = _finite_nonnegative(raw.get("execution_time", 0.0), 0.0)
                error = raw.get("error")
            else:
                success = bool(raw)
                elapsed = 0.0
                error = None if success else "El executor no confirmó el éxito"
            return {
                "plan_id": plan_id,
                "execution_status": "success" if success else "failed",
                "execution_time": elapsed,
                "success": success,
                "error": error,
            }
        except Exception as exc:
            logger.exception("[PLANNER] El executor externo falló")
            return {
                "plan_id": plan_id,
                "execution_status": "failed",
                "execution_time": 0.0,
                "success": False,
                "error": str(exc),
            }

    def record_execution_result(
        self,
        plan: List[Dict[str, Any]],
        execution_time: float,
        success: bool,
        context: Dict[str, Any],
    ) -> None:
        """Registra feedback tras una ejecución externa real; plan() no lo simula."""
        elapsed = _finite_nonnegative(execution_time, 0.0)
        if self.optimization_manager is not None and callable(
            getattr(self.optimization_manager, "record_execution_result", None)
        ):
            try:
                self.optimization_manager.record_execution_result(
                    plan, elapsed, bool(success), context
                )
            except Exception:
                logger.exception(
                    "[PLANNER] No se pudo registrar resultado en OptimizationManager"
                )
        if self.learning_system is not None:
            method = getattr(self.learning_system, "record_plan_execution", None)
            if callable(method):
                try:
                    plan_id = (
                        str(context.get("plan_id", ""))
                        if isinstance(context, dict)
                        else ""
                    )
                    method(
                        plan_id=plan_id or self._new_plan_id(),
                        goal_id=(
                            context.get("goal_id")
                            if isinstance(context, dict)
                            else None
                        ),
                        plan=[
                            str(node.get("id", node.get("action", ""))) for node in plan
                        ],
                        success=bool(success),
                        execution_time=elapsed,
                        total_estimated_cost=sum(
                            _finite_nonnegative(node.get("cost", 1.0), 1.0)
                            for node in plan
                        ),
                        context=dict(context or {}),
                    )
                except Exception:
                    logger.exception(
                        "[PLANNER] No se pudo registrar feedback de aprendizaje"
                    )

    def get_optimization_stats(self) -> Dict[str, Any]:
        if self.optimization_manager is None:
            return {"optimization_available": False}
        try:
            result = self.optimization_manager.get_optimization_stats()
            return (
                result
                if isinstance(result, dict)
                else {"optimization_available": True, "stats": result}
            )
        except Exception as exc:
            return {"optimization_available": False, "error": str(exc)}

    def clear_optimization_cache(self) -> None:
        method = (
            getattr(self.optimization_manager, "clear_cache", None)
            if self.optimization_manager
            else None
        )
        if callable(method):
            method()

    def enable_optimization(self, optimization_type: str, enabled: bool = True) -> None:
        if self.optimization_manager is None:
            self._ensure_optimization_systems()
        if self.optimization_manager is None:
            return
        try:
            try:
                from src.hands.planner.optimization import OptimizationType
            except ImportError:
                from src.hands.planner.optimization import OptimizationType
            selected = OptimizationType(optimization_type)
            self.optimization_manager.enable_optimization(selected, bool(enabled))
        except Exception as exc:
            logger.warning("[PLANNER] Error configurando optimización: %s", exc)

    def export_optimization_data(self, filepath: str) -> None:
        method = (
            getattr(self.optimization_manager, "export_optimization_data", None)
            if self.optimization_manager
            else None
        )
        if callable(method):
            method(filepath)

    def import_optimization_data(self, filepath: str) -> None:
        method = (
            getattr(self.optimization_manager, "import_optimization_data", None)
            if self.optimization_manager
            else None
        )
        if callable(method):
            method(filepath)

    def get_optimization_recommendations(self) -> List[str]:
        stats = self.get_optimization_stats()
        recommendations: List[str] = []
        if stats.get("cache_hit_rate", 0) < 0.1 and stats.get(
            "optimization_available", True
        ):
            recommendations.append("Revisar la reutilización de rutas en caché")
        return recommendations

    # ==================================================================
    # UTILIDADES INTERNAS
    # ==================================================================

    def _record_planning_history(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        result: PlanningResult,
        method: str,
    ) -> None:
        record = {
            "timestamp": time.time(),
            "goal_id": getattr(goal, "id", None),
            "goal_type": getattr(goal, "type", None),
            "plan_length": len(result.plan),
            "execution_time": result.execution_time,
            "quality": result.quality.value,
            "alternatives_found": len(result.alternatives),
            "current_state": copy.deepcopy(current_state),
            "success": result.status == PlannerStatus.COMPLETED,
            "status": result.status.value,
            "method": method,
            "plan_id": result.plan_id,
        }
        self.planning_history.append(record)
        # Importante: no se llama a record_plan_execution aquí. Que exista un plan
        # no demuestra que haya sido ejecutado ni que sus acciones hayan tenido éxito.

    def _get_default_state(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "application_states": {},
            "ui_elements": {},
            "available_actions": [],
            "last_actions": [],
            "constraints": [],
        }

    @staticmethod
    def _safe_required_capabilities(goal: Goal) -> List[str]:
        try:
            value = goal.get_required_capabilities()
        except Exception:
            value = getattr(goal, "required_capabilities", [])
        raw = _as_values(value)
        result: List[str] = []
        seen: set[str] = set()
        for item in raw:
            text = str(getattr(item, "value", item) or "").strip()
            if text and text.lower() not in seen:
                result.append(text)
                seen.add(text.lower())
        return result

    @staticmethod
    def _is_goal_expired(goal: Goal) -> bool:
        deadline = getattr(goal, "deadline", None)
        if deadline is not None:
            try:
                if float(deadline) < time.time():
                    return True
            except (TypeError, ValueError, OverflowError):
                pass
        method = getattr(goal, "is_expired", None)
        if callable(method):
            try:
                return bool(method())
            except Exception:
                return False
        return False

    @staticmethod
    def _is_goal_achieved(goal: Goal, current_state: Dict[str, Any]) -> bool:
        method = getattr(goal, "is_achieved", None)
        if callable(method):
            try:
                return bool(method(current_state))
            except Exception:
                logger.debug(
                    "[PLANNER] No se pudo evaluar logro del objetivo", exc_info=True
                )
        metadata = getattr(goal, "metadata", {}) or {}
        criteria = metadata.get("target_state") if isinstance(metadata, dict) else None
        if isinstance(criteria, dict):
            return all(
                current_state.get(key) == value for key, value in criteria.items()
            )
        return False

    @staticmethod
    def _node_type_value(node: Any) -> str:
        value = getattr(getattr(node, "type", None), "value", getattr(node, "type", ""))
        return str(value).strip().lower()

    @staticmethod
    def _status_value(status: Any) -> str:
        return (
            str(getattr(status, "value", status if status is not None else ""))
            .strip()
            .lower()
        )

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        return _normalize_text(value).replace(" ", "_").replace("-", "_")

    @staticmethod
    def _state_node_matches_context(node: Node, current_state: Dict[str, Any]) -> bool:
        requirements = getattr(node, "state_requirements", None)
        if isinstance(requirements, dict) and requirements:
            return all(
                current_state.get(key) == value for key, value in requirements.items()
            )
        metadata = getattr(node, "metadata", {}) or {}
        if isinstance(metadata, dict):
            requirements = metadata.get("state_requirements")
            if isinstance(requirements, dict) and requirements:
                return all(
                    current_state.get(key) == value
                    for key, value in requirements.items()
                )
        return False

    def _node_can_satisfy_goal(self, node: Node, goal: Goal) -> bool:
        goal_type = str(getattr(goal, "type", "")).lower()
        text = " ".join(
            (
                str(getattr(node, "id", "")),
                str(getattr(node, "name", "")),
                str(getattr(node, "description", "")),
                " ".join(map(str, _as_values(getattr(node, "effects", [])))),
            )
        ).lower()
        target = self._goal_target_string(goal).lower()
        keywords = {
            "navigate": (
                "navigate",
                "destination",
                "loaded",
                "url_changed",
                "navigated_to",
            ),
            "navigate_stream": (
                "navigate",
                "stream",
                "loaded",
                "destination",
                "navigated_to",
            ),
            "search": ("search", "result", "found"),
            "open_application": ("open", "active", "running", "launched"),
            "close_application": ("close", "closed", "stopped"),
        }.get(goal_type, (goal_type,) if goal_type else ())
        if target and target in text:
            return True
        return any(keyword in text for keyword in keywords if keyword)

    def _goal_satisfied_by_effects(self, effects: Any, goal: Goal) -> bool:
        goal_type = str(getattr(goal, "type", "")).lower()
        target = self._goal_target_string(goal).lower()
        values = [
            str(getattr(item, "value", item)).lower() for item in _as_values(effects)
        ]
        if goal_type in {"navigate", "navigate_stream", "navigate_to_entity"}:
            return any(
                any(
                    token in effect
                    for token in (
                        "url_changed",
                        "destination_loaded",
                        "navigated",
                        "loaded",
                    )
                )
                for effect in values
            )
        if goal_type == "search":
            return any(
                "search" in effect or "result" in effect or "found" in effect
                for effect in values
            )
        if goal_type == "open_application":
            return any(
                "open" in effect or "active" in effect or "running" in effect
                for effect in values
            )
        if goal_type == "close_application":
            return any("closed" in effect or "stopped" in effect for effect in values)
        return bool(target and any(target in effect for effect in values))

    @staticmethod
    def _effects_support_preconditions(effects: Any, preconditions: Any) -> bool:
        return Planner._facts_support_conditions(
            _as_values(effects), _as_values(preconditions)
        )

    @staticmethod
    def _facts_support_conditions(
        facts: Iterable[Any], conditions: Iterable[Any]
    ) -> bool:
        fact_values: set[str] = set()
        for fact in facts or []:
            if isinstance(fact, dict):
                key = fact.get("key", fact.get("state_key", fact.get("name")))
                if key is not None:
                    fact_values.add(str(key).lower())
                    fact_values.add(
                        f"{key}={fact.get('value', fact.get('equals', True))}".lower()
                    )
            else:
                value = str(getattr(fact, "value", fact)).strip().lower()
                if value:
                    fact_values.add(value)
        for condition in conditions or []:
            if isinstance(condition, dict):
                key = condition.get(
                    "key", condition.get("state_key", condition.get("name"))
                )
                if key is not None:
                    expected = condition.get("value", condition.get("equals", True))
                    if (
                        f"{key}={expected}".lower() in fact_values
                        or str(key).lower() in fact_values
                    ):
                        return True
            else:
                value = str(getattr(condition, "value", condition)).strip().lower()
                if value and value in fact_values:
                    return True
        return False

    @staticmethod
    def _normalize_route_result(
        raw_result: Any,
    ) -> Tuple[List[str], float, List[List[str]], Dict[str, Any]]:
        """Normaliza RouteResult, diccionarios, tuplas y listas legacy."""
        if raw_result is None:
            return [], 0.0, [], {"route_result_missing": True}
        if isinstance(raw_result, dict):
            status = str(
                getattr(
                    raw_result.get("status", ""), "value", raw_result.get("status", "")
                )
            ).lower()
            success = raw_result.get("success")
            path = raw_result.get("path", raw_result.get("route", [])) or []
            metadata = raw_result.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            if success is False or status in {"failed", "error", "not_found"}:
                return [], 0.0, [], {**metadata, "route_error": raw_result.get("error")}
            return (
                list(path),
                _finite_nonnegative(
                    raw_result.get("total_cost", raw_result.get("cost", 0.0)), 0.0
                ),
                _normalize_alternative_paths(
                    raw_result.get(
                        "alternative_paths", raw_result.get("alternatives", [])
                    )
                ),
                metadata,
            )
        if hasattr(raw_result, "path"):
            success = getattr(raw_result, "success", None)
            status = str(
                getattr(
                    getattr(raw_result, "status", None),
                    "value",
                    getattr(raw_result, "status", ""),
                )
            ).lower()
            metadata = getattr(raw_result, "metadata", {}) or {}
            if success is False or status in {"failed", "error", "not_found"}:
                return (
                    [],
                    0.0,
                    [],
                    {
                        **(metadata if isinstance(metadata, dict) else {}),
                        "route_error": getattr(raw_result, "error", None),
                    },
                )
            return (
                list(getattr(raw_result, "path", []) or []),
                _finite_nonnegative(getattr(raw_result, "total_cost", 0.0), 0.0),
                _normalize_alternative_paths(
                    getattr(raw_result, "alternative_paths", []) or []
                ),
                dict(metadata) if isinstance(metadata, dict) else {},
            )
        if isinstance(raw_result, tuple):
            path = (
                list(raw_result[0] or [])
                if len(raw_result) > 0 and isinstance(raw_result[0], (list, tuple))
                else []
            )
            cost = (
                _finite_nonnegative(raw_result[1], 0.0) if len(raw_result) > 1 else 0.0
            )
            alternatives = (
                _normalize_alternative_paths(raw_result[2])
                if len(raw_result) > 2
                else []
            )
            metadata = (
                raw_result[3]
                if len(raw_result) > 3 and isinstance(raw_result[3], dict)
                else {}
            )
            return path, cost, alternatives, metadata
        if isinstance(raw_result, list):
            return list(raw_result), 0.0, [], {}
        return [], 0.0, [], {"unsupported_route_result_type": type(raw_result).__name__}

    # ==================================================================
    # TRANSICIONES COMPATIBLES
    # ==================================================================

    def _create_sequential_navigation_edges(self) -> None:
        """Añade secuencia legacy únicamente cuando los nodos existen."""
        if self.state_graph is None:
            return
        sequences = [
            ("chrome.closed", "chrome.open"),
            ("chrome.open", "chrome.activate"),
            ("chrome.activate", "focus_address_bar"),
            ("chrome.activate", "hotkey_ctrl_l"),
            ("focus_address_bar", "type_url"),
            ("hotkey_ctrl_l", "type_url"),
            ("type_url", "press_enter"),
        ]
        edge_lookup = self._edge_pairs()
        for source, target in sequences:
            if (
                source not in self.state_graph.nodes
                or target not in self.state_graph.nodes
            ):
                continue
            # La secuencia histórica solo se usa cuando el grafo contiene alguno
            # de los nodos de compatibilidad, no como atajo genérico entre apps.
            if source.startswith("chrome.") or target in {
                "focus_address_bar",
                "hotkey_ctrl_l",
                "type_url",
                "press_enter",
            }:
                if (source, target) not in edge_lookup:
                    try:
                        self.state_graph.add_edge(
                            source, target, 1.0, [], "compatibility"
                        )
                        edge_lookup.add((source, target))
                    except Exception:
                        logger.debug(
                            "[PLANNER] No se pudo añadir transición legacy",
                            exc_info=True,
                        )

    # ==================================================================
    # HELPERS ADICIONALES DE INTEGRACIÓN
    # ==================================================================

    def _validate_goal_request(
        self, goal: Goal, max_planning_time: float
    ) -> Optional[str]:
        if goal is None or not str(getattr(goal, "id", "") or "").strip():
            return "Objetivo inválido: falta un ID"
        try:
            budget = float(max_planning_time)
            if not math.isfinite(budget) or budget <= 0:
                return "max_planning_time debe ser un número finito mayor que cero"
        except (TypeError, ValueError, OverflowError):
            return "max_planning_time no es válido"
        if self._is_goal_expired(goal):
            return "El objetivo ha expirado"
        return None

    def _failure_result(
        self, message: str, goal: Optional[Goal], state: Dict[str, Any], started: float
    ) -> PlanningResult:
        return PlanningResult(
            status=PlannerStatus.FAILED,
            goal=goal,
            current_state=dict(state),
            execution_time=time.perf_counter() - started,
            warnings=[message],
        )

    def _new_plan_id(self) -> str:
        return f"plan_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _normalize_state(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        try:
            return copy.deepcopy(value)
        except Exception:
            return dict(value)

    @staticmethod
    def _goal_target_string(goal: Any) -> str:
        target = getattr(goal, "target", "")
        if isinstance(target, dict):
            for key in (
                "app_name",
                "application",
                "name",
                "url",
                "query",
                "target",
                "stream",
            ):
                value = target.get(key)
                if value:
                    return str(value)
            return " ".join(
                str(value) for value in target.values() if value is not None
            )
        return str(target or "")

    def _node_effect_facts(self, node: Any) -> set[str]:
        facts = {
            str(getattr(effect, "value", effect)).strip().lower()
            for effect in _as_values(getattr(node, "effects", []))
        }
        facts.update(self._node_state_facts(node))
        return {fact for fact in facts if fact}

    def _node_state_facts(self, node: Any) -> set[str]:
        facts: set[str] = set()
        node_type = self._node_type_value(node)
        node_id = str(getattr(node, "id", "")).strip().lower()
        if node_type == "state" and node_id:
            facts.add(node_id)
            facts.add(node_id.replace(".", "_"))
        requirements = getattr(node, "state_requirements", {}) or {}
        modifications = getattr(node, "state_modifications", {}) or {}
        metadata = getattr(node, "metadata", {}) or {}
        for payload in (requirements, modifications):
            if isinstance(payload, dict):
                for key, value in payload.items():
                    facts.add(str(key).lower())
                    facts.add(f"{key}={value}".lower())
        if isinstance(metadata, dict):
            app = _normalize_text(
                metadata.get("application", getattr(node, "application", ""))
            )
            state = _normalize_text(metadata.get("state", ""))
            if app and state:
                facts.update(
                    {
                        f"{app}_{state}",
                        f"{app}.{state}",
                        f"{app}_{state.replace(' ', '_')}",
                    }
                )
                facts.add(state)
            for key, value in metadata.items():
                if key in {"application", "state", "source", "mapping_phase"}:
                    continue
                if isinstance(value, bool) and value:
                    facts.add(str(key).lower())
                    if app:
                        facts.add(f"{app}_{str(key).lower()}")
        return facts

    def _has_incoming_edge(self, node_id: str) -> bool:
        return any(target == node_id for _, target in self._edge_pairs())

    def _edge_pairs(self) -> set[Tuple[str, str]]:
        edges = (
            getattr(self.state_graph, "edges", [])
            if self.state_graph is not None
            else []
        )
        pairs: set[Tuple[str, str]] = set()
        if isinstance(edges, dict):
            pairs.update(
                tuple(key)
                for key in edges
                if isinstance(key, (tuple, list)) and len(key) == 2
            )
        else:
            try:
                for edge in edges:
                    source = getattr(edge, "source_id", None)
                    target = getattr(edge, "target_id", None)
                    if source is not None and target is not None:
                        pairs.add((str(source), str(target)))
            except TypeError:
                pass
        return pairs

    def _time_budget_to_iterations(self, max_planning_time: float) -> int:
        # StateGraph recibe max_iterations, no un deadline en segundos. Se usa una
        # equivalencia conservadora y se deja constancia para no prometer timeout real.
        budget = _finite_nonnegative(max_planning_time, 30.0)
        return max(1, min(200_000, int(budget * 100)))

    def _normalize_alternative_plans(
        self, alternatives: Any, nodes: Dict[str, Node]
    ) -> List[List[Dict[str, Any]]]:
        result = []
        for path in _normalize_alternative_paths(alternatives):
            plan = self._convert_path_to_plan(path, nodes)
            if plan and plan not in result:
                result.append(plan)
            if len(result) >= 3:
                break
        return result

    def _candidate_preconditions_compatible(
        self,
        node: Node,
        current_state: Dict[str, Any],
        preceding_plan: List[Dict[str, Any]],
    ) -> bool:
        state = copy.deepcopy(current_state)
        for step in preceding_plan:
            for effect in _as_values(step.get("effects", [])):
                state[str(getattr(effect, "value", effect))] = True
        preconditions = _as_values(getattr(node, "preconditions", []))
        # Si no existe una representación de estado suficiente, no descartamos
        # automáticamente la alternativa: el executor/precondition manager puede
        # validar las condiciones dinámicas reales antes de ejecutarla.
        known_state = bool(state)
        return (
            all(
                self._evaluate_condition_with_state(condition, state)
                for condition in preconditions
            )
            if known_state
            else True
        )

    def _same_capability_or_category(
        self, candidate: Node, original_node: Dict[str, Any]
    ) -> bool:
        metadata = original_node.get("metadata", {}) or {}
        capability = metadata.get("capability") if isinstance(metadata, dict) else None
        original_category = original_node.get("action_category") or (
            metadata.get("action_category") if isinstance(metadata, dict) else None
        )
        candidate_metadata = getattr(candidate, "metadata", {}) or {}
        candidate_capability = (
            candidate_metadata.get("capability")
            if isinstance(candidate_metadata, dict)
            else None
        )
        candidate_category = getattr(candidate, "action_category", None)
        if capability and candidate_capability:
            return _normalize_text(capability) == _normalize_text(candidate_capability)
        if original_category and candidate_category:
            return _normalize_text(original_category) == _normalize_text(
                candidate_category
            )
        original_app = _normalize_text(original_node.get("application", ""))
        candidate_app = _normalize_text(getattr(candidate, "application", ""))
        original_tokens = set(_normalize_text(original_node.get("name", "")).split())
        candidate_tokens = set(_normalize_text(getattr(candidate, "name", "")).split())
        return bool(
            original_app
            and original_app == candidate_app
            and original_tokens.intersection(candidate_tokens)
        )

    def _capability_already_satisfied(
        self, capability: str, state: Dict[str, Any]
    ) -> bool:
        key = _normalize_text(capability).replace(" ", "_")
        if not key:
            return False
        aliases = {key, f"{key}_done", f"{key}_completed", f"{key}_performed"}
        return any(state.get(alias) is True for alias in aliases)

    @staticmethod
    def _apply_declared_effects(
        state: Dict[str, Any], effects: Iterable[Any]
    ) -> Dict[str, Any]:
        result = copy.deepcopy(state)
        for effect in effects or []:
            if isinstance(effect, dict):
                key = effect.get("key", effect.get("state_key", effect.get("name")))
                if key is not None:
                    result[str(key)] = effect.get("value", effect.get("equals", True))
            else:
                key = str(getattr(effect, "value", effect)).strip()
                if key:
                    result[key] = True
        return result

    @staticmethod
    def _calculate_goal_complexity(goal: Goal, current_state: Dict[str, Any]) -> int:
        required = Planner._safe_required_capabilities(goal)
        missing = sum(
            1
            for capability in required
            if not current_state.get(
                f"{_normalize_text(capability).replace(' ', '_')}_done"
            )
        )
        constraints = _as_values(getattr(goal, "constraints", []))
        return max(1, missing + len(constraints))


def _normalize_text(value: Any) -> str:
    return " ".join(
        str(getattr(value, "value", value) or "")
        .strip()
        .lower()
        .replace("_", " ")
        .split()
    )


def _slug(value: Any) -> str:
    """Normaliza nombres de capacidades sin perder el separador de palabras."""
    return "_".join(_normalize_text(value).replace(".", " ").replace("-", " ").split())


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _finite_nonnegative(value: Any, default: float = 0.0) -> float:
    number = _finite_float(value, default)
    return number if number >= 0 else default


def _as_values(value: Any) -> List[Any]:
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


def _normalize_alternative_paths(value: Any) -> List[List[str]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: List[List[str]] = []
    for path in value:
        if isinstance(path, (list, tuple)) and all(
            isinstance(item, str) for item in path
        ):
            result.append(list(path))
    return result


__all__ = ["Planner", "PlanningResult", "PlannerStatus", "PlanQuality"]
