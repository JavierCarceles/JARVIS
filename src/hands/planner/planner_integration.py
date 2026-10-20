"""

Responsabilidades:
- Inicializar y preparar el grafo.
- Construir transiciones de planificación a partir de precondiciones/efectos.
- Resolver nodos inicial/final sin depender de IDs inventados.
- Obtener una ruta del StateGraph/AdvancedStateGraph.
- Devolver un resultado estructurado sin ejecutar acciones reales.

La conversión final de una ruta a un Plan ejecutable pertenece a subfases
posteriores.
"""

from __future__ import annotations

import inspect
import math
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.hands.planner.graph import (
    AdvancedStateGraph,
    PerformanceMetrics,
    SearchStrategy,
    StateGraph,
)
from src.hands.planner.heuristic import Heuristic, HeuristicType
from src.hands.planner.node import Goal, Node, NodeType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IntegrationMode(Enum):
    GRAPH_ONLY = "graph_only"
    HTN_PLUS_GRAPH = "htn_plus_graph"
    FULL_INTEGRATION = "full_integration"


@dataclass
class GraphPlanningResult:
    status: str
    plan: List[Dict[str, Any]] = field(default_factory=list)
    path: List[str] = field(default_factory=list)
    total_cost: float = 0.0
    execution_time: float = 0.0
    nodes_used: int = 0
    edges_used: int = 0
    alternative_paths: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GraphPlannerIntegration:
    """Puente entre Goal/estado actual y StateGraph."""

    def __init__(
        self,
        use_astar: bool = True,
        integration_mode: IntegrationMode | str = IntegrationMode.FULL_INTEGRATION,
    ) -> None:
        """Inicializa el puente de planificación sin ejecutar acciones."""
        self.use_astar = bool(use_astar)
        if isinstance(integration_mode, IntegrationMode):
            self.integration_mode = integration_mode
        else:
            try:
                self.integration_mode = IntegrationMode(str(integration_mode).strip().lower())
            except ValueError as exc:
                raise ValueError(f"Modo de integración no soportado: {integration_mode}") from exc

        # El grafo no aporta por sí solo una distancia admisible al objetivo.
        # h=0 mantiene A* correcto para costes ponderados, incluidos costes 0.
        self.heuristic = Heuristic(HeuristicType.ZERO)
        self.state_graph: Optional[StateGraph] = None
        self.performance_metrics = PerformanceMetrics()
        self.total_plans_created = 0
        self.successful_plans = 0
        self.failed_plans = 0
        self.average_plan_length = 0.0
        self._contextual_edges: List[Any] = []

        logger.info(
            "[GRAPH-INTEGRATION] Integración inicializada: %s",
            self.integration_mode.value,
        )

    # ==================================================================
    # INICIALIZACIÓN
    # ==================================================================

    def initialize_graph(
        self,
        nodes: Iterable[Node],
        edges_config: Optional[List[Dict[str, Any]]] = None,
    ) -> StateGraph:
        """Construye un grafo nuevo y rechaza identificadores ambiguos."""
        try:
            materialized_nodes = [node for node in nodes if node is not None]
        except TypeError as exc:
            raise TypeError("nodes debe ser una colección iterable de Node") from exc

        seen_ids: Set[str] = set()
        for node in materialized_nodes:
            node_id = getattr(node, "id", None)
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValueError("Todos los nodos deben tener un id de texto no vacío")
            if node_id in seen_ids:
                raise ValueError(f"ID de nodo duplicado: {node_id}")
            seen_ids.add(node_id)

        # Preparar el grafo localmente evita perder el grafo vigente si la entrada
        # no puede convertirse en un grafo válido.
        graph = AdvancedStateGraph(self.heuristic)
        for node in materialized_nodes:
            graph.add_node(node)

        self.state_graph = graph
        self._contextual_edges.clear()

        if edges_config:
            self._configure_advanced_edges(edges_config)

        self._create_compatibility_edges()
        self._prepare_planning_edges()
        self._calculate_graph_metrics()
        self._invalidate_graph_caches()

        logger.info(
            "[GRAPH-INTEGRATION] Grafo inicializado: %s nodos, %s aristas",
            len(self.state_graph.nodes),
            len(self.state_graph.edges),
        )
        return self.state_graph

    def _configure_advanced_edges(self, edges_config: List[Dict[str, Any]]) -> None:
        if not self.state_graph:
            return

        for config in self._as_sequence(edges_config):
            if not isinstance(config, dict):
                logger.warning(
                    "[GRAPH-INTEGRATION] Configuración de arista inválida: %r",
                    config,
                )
                continue

            source_id = config.get("source", config.get("source_id"))
            target_id = config.get("target", config.get("target_id"))
            if not isinstance(source_id, str) or not isinstance(target_id, str):
                logger.warning(
                    "[GRAPH-INTEGRATION] Arista ignorada por falta de source/target: %r",
                    config,
                )
                continue
            if source_id not in self.state_graph.nodes or target_id not in self.state_graph.nodes:
                logger.warning(
                    "[GRAPH-INTEGRATION] Arista %s -> %s ignorada: nodo inexistente",
                    source_id,
                    target_id,
                )
                continue

            try:
                cost = self._safe_float(config.get("cost", 1.0), float("nan"))
            except (TypeError, ValueError, OverflowError):
                cost = float("nan")
            if not math.isfinite(cost) or cost < 0:
                logger.warning(
                    "[GRAPH-INTEGRATION] Coste inválido en arista %s -> %s: %r",
                    source_id,
                    target_id,
                    config.get("cost", 1.0),
                )
                continue

            added = self.state_graph.add_edge(
                source_id=source_id,
                target_id=target_id,
                cost=cost,
                conditions=self._as_sequence(config.get("conditions")),
                transition_type=str(config.get("transition_type", "conditional") or "conditional"),
                preconditions=self._as_sequence(config.get("preconditions")),
                effects=self._as_sequence(config.get("effects")),
            )
            if not added:
                logger.debug(
                    "[GRAPH-INTEGRATION] No se añadió la arista %s -> %s",
                    source_id,
                    target_id,
                )

    def _create_compatibility_edges(self) -> None:
        if not self.state_graph:
            return

        self._create_sequence_edges(
            [
                ("chrome.closed", "chrome.open", 5.0),
                ("chrome.open", "chrome.activate", 2.0),
                ("chrome.activate", "focus_address_bar", 1.0),
                ("focus_address_bar", "type_url", 1.0),
                ("type_url", "press_enter", 1.0),
                ("chrome.activate", "hotkey_ctrl_l", 1.0),
                ("hotkey_ctrl_l", "type_url", 1.0),
                ("chrome.activate", "focus_search_bar", 1.0),
                ("focus_search_bar", "type_search_query", 1.0),
                ("type_search_query", "press_enter", 1.0),
            ]
        )
        self._create_sequence_edges(
            [
                ("app.closed", "app.open", 5.0),
                ("app.open", "app.activate", 2.0),
                ("app.activate", "app.maximize", 1.0),
                ("browser.closed", "browser.open", 5.0),
                ("browser.open", "browser.activate", 2.0),
                ("browser.activate", "browser.focus", 1.0),
                ("app_inactive", "app_active", 1.0),
                ("app_active", "app_minimized", 1.0),
                ("app_minimized", "app_active", 1.0),
                ("system_idle", "system_busy", 1.0),
                ("system_busy", "system_idle", 1.0),
            ]
        )

    def _create_sequence_edges(self, sequences: Sequence[Tuple[str, str, float]]) -> None:
        if not self.state_graph:
            return
        for source_id, target_id, raw_cost in sequences:
            if source_id not in self.state_graph.nodes or target_id not in self.state_graph.nodes:
                continue
            cost = self._safe_float(raw_cost, float("nan"))
            if not math.isfinite(cost) or cost < 0:
                logger.warning(
                    "[GRAPH-INTEGRATION] Coste inválido en transición de compatibilidad %s -> %s",
                    source_id,
                    target_id,
                )
                continue
            self._add_edge_if_missing(
                source_id,
                target_id,
                cost=cost,
                transition_type="normal",
            )

    # ==================================================================
    # TRANSICIONES DERIVADAS
    # ==================================================================

    def _prepare_planning_edges(self) -> None:
        """Deriva aristas solo de dependencias o efectos que aportan evidencia."""
        if not self.state_graph:
            return

        state_nodes = [
            node for node in self.state_graph.nodes.values()
            if getattr(node, "type", None) == NodeType.STATE
        ]
        action_nodes = [
            node for node in self.state_graph.nodes.values()
            if getattr(node, "type", None) == NodeType.ACTION
        ]

        # No conectar todos los estados con todas las acciones: una conexión
        # derivada necesita una dependencia explícita o hechos que habiliten
        # las precondiciones de la acción.
        for state_node in state_nodes:
            state_facts: Dict[str, Any] = {}
            for attribute in ("state_requirements", "state_modifications"):
                facts = getattr(state_node, attribute, None)
                if isinstance(facts, dict):
                    state_facts.update(facts)
            metadata = getattr(state_node, "metadata", None)
            if isinstance(metadata, dict):
                for field_name in ("state_facts", "expected_state"):
                    facts = metadata.get(field_name)
                    if isinstance(facts, dict):
                        state_facts.update(facts)
            fact_effects = [{"type": "state_set", "key": key, "value": value} for key, value in state_facts.items()]

            for action_node in action_nodes:
                dependencies = set(self._as_sequence(getattr(action_node, "dependencies", [])))
                explicitly_depends = state_node.id in dependencies
                facts_enable = bool(fact_effects) and self._effects_support_preconditions(
                    fact_effects,
                    getattr(action_node, "preconditions", []),
                )
                if explicitly_depends or facts_enable:
                    self._add_planning_edge(state_node, action_node)

        for source_node in action_nodes:
            for target_node in action_nodes:
                if source_node.id == target_node.id:
                    continue
                dependencies = set(self._as_sequence(getattr(target_node, "dependencies", [])))
                explicitly_depends = source_node.id in dependencies
                source_effects = list(self._as_sequence(getattr(source_node, "effects", [])))
                state_modifications = getattr(source_node, "state_modifications", None)
                if isinstance(state_modifications, dict):
                    source_effects.extend(
                        {"type": "state_set", "key": key, "value": value}
                        for key, value in state_modifications.items()
                    )
                effects_enable = self._effects_support_preconditions(
                    source_effects,
                    getattr(target_node, "preconditions", []),
                )
                if explicitly_depends or effects_enable:
                    self._add_planning_edge(source_node, target_node)

        self._invalidate_graph_caches()

    def _connect_if_plannable(
        self,
        source_node: Node,
        target_node: Node,
        current_state: Optional[Dict[str, Any]],
    ) -> None:
        if current_state is not None and not self._preconditions_satisfied(
            target_node.preconditions, current_state
        ):
            return
        self._add_planning_edge(source_node, target_node)

    def _add_planning_edge(self, source_node: Node, target_node: Node) -> None:
        if source_node.id == target_node.id:
            return
        cost = self._safe_float(getattr(target_node, "cost", 1.0), 1.0)
        if not math.isfinite(cost) or cost < 0:
            cost = 1.0

        self._add_edge_if_missing(
            source_node.id,
            target_node.id,
            cost=cost,
            transition_type="planning",
            preconditions=self._as_sequence(getattr(target_node, "preconditions", [])),
            effects=self._as_sequence(getattr(target_node, "effects", [])),
        )

    def _add_edge_if_missing(
        self,
        source_id: str,
        target_id: str,
        cost: float,
        transition_type: str,
        preconditions: Optional[List[Any]] = None,
        effects: Optional[List[Any]] = None,
    ) -> bool:
        if not self.state_graph:
            return False
        if source_id not in self.state_graph.nodes or target_id not in self.state_graph.nodes:
            return False
        if source_id == target_id:
            return False
        if any(
            edge.source_id == source_id and edge.target_id == target_id
            for edge in self.state_graph.edges
        ):
            return False
        numeric_cost = self._safe_float(cost, float("nan"))
        if not math.isfinite(numeric_cost) or numeric_cost < 0:
            return False
        added = self.state_graph.add_edge(
            source_id,
            target_id,
            cost=numeric_cost,
            conditions=[],
            transition_type=transition_type,
            preconditions=self._as_sequence(preconditions),
            effects=self._as_sequence(effects),
        )
        if added:
            self._invalidate_graph_caches()
        return bool(added)

    # ==================================================================
    # PLANIFICACIÓN
    # ==================================================================

    def create_plan_with_graph(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Optional[Dict[str, Node]] = None,
        max_planning_time: float = 30.0,
        start_node_id: Optional[str] = None,
        goal_node_id: Optional[str] = None,
    ) -> GraphPlanningResult:
        """Planifica una ruta y devuelve metadatos; nunca ejecuta acciones."""
        started = time.monotonic()
        self.total_plans_created += 1
        warnings = self._validate_planning_input(goal, current_state, available_nodes)
        if warnings:
            self.failed_plans += 1
            self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
            return GraphPlanningResult(
                status="failed",
                warnings=warnings,
                execution_time=time.monotonic() - started,
            )
        if not self.state_graph:
            self.failed_plans += 1
            self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
            return GraphPlanningResult(
                status="failed",
                warnings=["El grafo no está inicializado"],
                execution_time=time.monotonic() - started,
            )

        try:
            graph_nodes = self.state_graph.nodes
            local_nodes = dict(graph_nodes)
            if isinstance(available_nodes, dict):
                # Se admiten instancias complementarias solo para enriquecer los
                # metadatos; una ruta nunca puede contener IDs ajenos al grafo.
                local_nodes.update({
                    key: value
                    for key, value in available_nodes.items()
                    if isinstance(key, str)
                    and key in graph_nodes
                    and getattr(value, "id", None) == key
                    and getattr(value, "type", None) is not None
                })

            resolved_start = start_node_id or self._get_start_node_for_goal(goal, current_state)
            resolved_goal = goal_node_id or self._get_goal_node_for_goal(goal)
            if not resolved_start or not resolved_goal:
                self.failed_plans += 1
                self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
                return GraphPlanningResult(
                    status="failed",
                    warnings=["No se pudieron determinar los nodos de inicio y destino sin asumir una correspondencia"],
                    execution_time=time.monotonic() - started,
                    metadata={"start_node_id": resolved_start, "goal_node_id": resolved_goal},
                )
            if resolved_start not in graph_nodes or resolved_goal not in graph_nodes:
                self.failed_plans += 1
                self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
                return GraphPlanningResult(
                    status="failed",
                    warnings=["El nodo inicial o final no pertenece al grafo inicializado"],
                    execution_time=time.monotonic() - started,
                    metadata={"start_node_id": resolved_start, "goal_node_id": resolved_goal},
                )

            # Los enlaces contextuales dependen del estado de esta solicitud;
            # se eliminan al terminar para que no contaminen peticiones futuras.
            self._remove_contextual_planning_edges()
            self._prepare_contextual_planning_edges(resolved_start, resolved_goal, current_state, goal=goal)
            strategy = self._determine_search_strategy(goal, current_state)
            route_data = self._execute_search(
                resolved_start,
                resolved_goal,
                current_state,
                strategy,
                max_planning_time,
            )

            route_status = str(route_data.get("status", "failed")).strip().lower()
            path = self._normalize_path(route_data.get("path", []))
            if route_status not in {"success", "completed"} or not path:
                self.failed_plans += 1
                self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
                failure_warnings = self._as_sequence(route_data.get("warnings"))
                if not failure_warnings:
                    failure_warnings = ["No se encontró una ruta válida"]
                return GraphPlanningResult(
                    status="failed",
                    warnings=[str(item) for item in failure_warnings],
                    execution_time=time.monotonic() - started,
                    metadata={
                        **(route_data.get("metadata", {}) if isinstance(route_data.get("metadata"), dict) else {}),
                        "algorithm": route_data.get("algorithm", strategy.value),
                        "start_node_id": resolved_start,
                        "goal_node_id": resolved_goal,
                    },
                )

            path_errors = self._validate_route_path(path, resolved_start, resolved_goal, current_state)
            if path_errors:
                self.failed_plans += 1
                self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
                return GraphPlanningResult(
                    status="failed",
                    warnings=path_errors,
                    path=path,
                    execution_time=time.monotonic() - started,
                    metadata={"algorithm": route_data.get("algorithm", strategy.value), "start_node_id": resolved_start, "goal_node_id": resolved_goal},
                )

            edges_used = self._normalize_edge_ids(route_data.get("edges_used", route_data.get("edges", [])), path)
            calculated_cost = self._calculate_path_cost(path, current_state)
            reported_cost = self._safe_float(route_data.get("total_cost"), float("nan"))
            total_cost = reported_cost if math.isfinite(reported_cost) and reported_cost >= 0 else calculated_cost
            if not math.isfinite(total_cost) or total_cost < 0:
                self.failed_plans += 1
                self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
                return GraphPlanningResult(
                    status="failed",
                    warnings=["El resultado de búsqueda contiene un coste total inválido"],
                    path=path,
                    execution_time=time.monotonic() - started,
                )

            plan_entries = self._convert_path_to_plan_metadata(path, local_nodes)
            elapsed = time.monotonic() - started
            self.successful_plans += 1
            self._update_performance_metrics(plan_entries, elapsed, total_cost)
            self._record_integration_search(True, len(path), total_cost, elapsed)

            return GraphPlanningResult(
                status="success",
                plan=plan_entries,
                path=path,
                total_cost=total_cost,
                execution_time=elapsed,
                nodes_used=len(path),
                edges_used=len(edges_used),
                alternative_paths=[self._normalize_path(item) for item in self._as_sequence(route_data.get("alternative_paths")) if self._normalize_path(item)],
                warnings=[str(item) for item in self._as_sequence(route_data.get("warnings"))],
                metadata={
                    **(route_data.get("metadata", {}) if isinstance(route_data.get("metadata"), dict) else {}),
                    "algorithm": route_data.get("algorithm", strategy.value),
                    "start_node_id": resolved_start,
                    "goal_node_id": resolved_goal,
                    "executable_plan": False,
                },
            )
        except Exception as exc:
            logger.exception("[GRAPH-INTEGRATION] Error durante la planificación")
            self.failed_plans += 1
            self._record_integration_search(False, 0, 0.0, time.monotonic() - started)
            return GraphPlanningResult(
                status="error",
                warnings=[f"Error en planificación: {exc}"],
                execution_time=time.monotonic() - started,
            )
        finally:
            self._remove_contextual_planning_edges()
    def _validate_planning_input(
        self,
        goal: Goal,
        current_state: Dict[str, Any],
        available_nodes: Optional[Dict[str, Node]],
    ) -> List[str]:
        warnings: List[str] = []
        if goal is None or not getattr(goal, "id", None):
            warnings.append("Objetivo inválido: falta un id")
        elif not getattr(goal, "type", None):
            warnings.append("Objetivo inválido: falta el tipo")
        if not isinstance(current_state, dict):
            warnings.append("El estado actual debe ser un diccionario")
        if available_nodes is not None and not isinstance(available_nodes, dict):
            warnings.append("available_nodes debe ser un diccionario")
        if available_nodes is not None and isinstance(available_nodes, dict):
            invalid_keys = [key for key in available_nodes if not isinstance(key, str) or not key]
            if invalid_keys:
                warnings.append("available_nodes contiene claves que no son IDs de nodo válidos")
        return warnings

    def _determine_search_strategy(self, goal: Goal, current_state: Dict[str, Any]) -> SearchStrategy:
        # La selección por complejidad no debe cambiar a BFS en grafos ponderados:
        # BFS minimiza número de aristas, no coste total. Sin A* se usa Dijkstra.
        if self.use_astar:
            return SearchStrategy.A_STAR
        return SearchStrategy.DIJKSTRA

    def _calculate_goal_complexity(self, goal: Goal, current_state: Dict[str, Any]) -> int:
        goal_type = str(getattr(goal, "type", "")).lower()
        complexity = {
            "navigate_stream": 4,
            "navigate": 2,
            "search": 3,
            "open_application": 1,
            "close_application": 1,
        }.get(goal_type, 2)
        if current_state.get("browser_available") is False:
            complexity += 2
        if current_state.get("entities_available") is False:
            complexity += 1
        return min(complexity, 10)

    def _execute_search(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: SearchStrategy,
        max_planning_time: float,
    ) -> Dict[str, Any]:
        """Invoca la API de búsqueda compatible y normaliza el resultado."""
        if not self.state_graph:
            return {"status": "failed", "warnings": ["Grafo no inicializado"]}

        method = self._select_search_method()
        if method is None:
            return {"status": "failed", "warnings": ["El grafo no expone una API de búsqueda compatible"]}

        budget_seconds = self._safe_float(max_planning_time, 30.0)
        if not math.isfinite(budget_seconds) or budget_seconds <= 0:
            return {"status": "failed", "warnings": ["max_planning_time debe ser un número finito mayor que cero"]}
        # La API del grafo expone max_iterations, no timeout. Se usa un presupuesto
        # acotado derivado del parámetro sin afirmar que interrumpe por tiempo real.
        iterations = max(1, min(1_000_000, int(budget_seconds * 100)))
        kwargs = self._build_search_kwargs(method, start_node_id, goal_node_id, current_state, strategy, iterations)
        try:
            raw_result = method(**kwargs)
        except TypeError:
            logger.debug("[GRAPH-INTEGRATION] La API rechazó kwargs; se probará invocación posicional", exc_info=True)
            try:
                raw_result = self._call_search_positionally(
                    method, start_node_id, goal_node_id, current_state, strategy, iterations
                )
            except Exception as exc:
                return {"status": "failed", "warnings": [f"API de búsqueda incompatible: {exc}"]}
        except Exception as exc:
            return {"status": "failed", "warnings": [f"Error en búsqueda: {exc}"]}

        return self._normalize_route_result(raw_result, strategy)

    def _select_search_method(self) -> Optional[Any]:
        if not self.state_graph:
            return None
        for name in ("find_route", "build_route", "find_path_with_strategy"):
            method = getattr(self.state_graph, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _build_search_kwargs(
        method: Any,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: SearchStrategy,
        max_iterations: int,
    ) -> Dict[str, Any]:
        values = {
            "start_node_id": start_node_id,
            "goal_node_id": goal_node_id,
            "start_id": start_node_id,
            "goal_id": goal_node_id,
            "current_state": dict(current_state),
            "strategy": strategy,
            "max_iterations": max_iterations,
        }
        try:
            signature = inspect.signature(method)
            parameters = signature.parameters
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
                return {
                    "start_node_id": start_node_id,
                    "goal_node_id": goal_node_id,
                    "current_state": dict(current_state),
                    "strategy": strategy,
                    "max_iterations": max_iterations,
                }
            return {key: value for key, value in values.items() if key in parameters}
        except (TypeError, ValueError):
            return {
                "start_node_id": start_node_id,
                "goal_node_id": goal_node_id,
                "current_state": dict(current_state),
                "strategy": strategy,
                "max_iterations": max_iterations,
            }

    @staticmethod
    def _call_search_positionally(
        method: Any,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: SearchStrategy,
        max_iterations: int,
    ) -> Any:
        attempts = (
            ((start_node_id, goal_node_id, dict(current_state), strategy, max_iterations), {}),
            ((start_node_id, goal_node_id, dict(current_state), strategy), {}),
            ((start_node_id, goal_node_id, dict(current_state)), {}),
            ((start_node_id, goal_node_id), {}),
        )
        last_error: Optional[Exception] = None
        for args, kwargs in attempts:
            try:
                return method(*args, **kwargs)
            except TypeError as exc:
                last_error = exc
                continue
        raise TypeError(f"API de búsqueda incompatible: {last_error}")

    def _normalize_route_result(self, raw_result: Any, strategy: SearchStrategy) -> Dict[str, Any]:
        """Adapta RouteResult, dict, tupla y lista sin convertir errores en éxitos."""
        if raw_result is None:
            return {"status": "failed", "warnings": ["La búsqueda no devolvió resultado"], "algorithm": strategy.value}

        if isinstance(raw_result, dict):
            data = dict(raw_result)
            path = self._normalize_path(data.get("path", data.get("route", [])))
            data["path"] = path
            explicit_success = data.get("success")
            status = str(data.get("status", "")).strip().lower()
            explicit_failure = explicit_success is not None and str(explicit_success).strip().lower() in {"false", "0", "no", "failed", "failure"}
            if explicit_failure or status in {"failed", "failure", "error", "aborted"}:
                data["status"] = "failed"
            elif path and status in {"", "success", "completed"}:
                data["status"] = "success"
            else:
                data["status"] = "failed"
            data.setdefault("algorithm", strategy.value)
            if not data.get("edges_used"):
                data["edges_used"] = self._normalize_edge_ids(data.get("edges", []), path)
            if not isinstance(data.get("warnings"), (list, tuple)):
                data["warnings"] = [str(data["warnings"])] if data.get("warnings") else []
            if not isinstance(data.get("metadata"), dict):
                data["metadata"] = {}
            return data

        if hasattr(raw_result, "path"):
            path = self._normalize_path(getattr(raw_result, "path", []))
            explicit_success = getattr(raw_result, "success", None)
            explicit_failure = explicit_success is not None and str(explicit_success).strip().lower() in {"false", "0", "no", "failed", "failure"}
            status = str(getattr(raw_result, "status", "") or "").strip().lower()
            if explicit_failure or status in {"failed", "failure", "error", "aborted"}:
                status = "failed"
            elif path and status in {"", "success", "completed"} and not explicit_failure:
                status = "success"
            else:
                status = "failed"
            edges = getattr(raw_result, "edges", []) or []
            edge_ids = getattr(raw_result, "edges_used", None)
            if not edge_ids:
                edge_ids = self._normalize_edge_ids(edges, path)
            warnings = self._as_sequence(getattr(raw_result, "warnings", []))
            error = getattr(raw_result, "error", None)
            if error and not warnings:
                warnings = [str(error)]
            return {
                "status": status,
                "success": status == "success",
                "path": path,
                "total_cost": getattr(raw_result, "total_cost", None),
                "edges_used": list(edge_ids),
                "alternative_paths": [self._normalize_path(item) for item in self._as_sequence(getattr(raw_result, "alternative_paths", []))],
                "warnings": [str(item) for item in warnings],
                "metadata": dict(getattr(raw_result, "metadata", {}) or {}) if isinstance(getattr(raw_result, "metadata", {}), dict) else {},
                "algorithm": strategy.value,
            }

        if isinstance(raw_result, tuple):
            path = self._normalize_path(raw_result[0] if raw_result else [])
            data: Dict[str, Any] = {"status": "success" if path else "failed", "path": path, "algorithm": strategy.value}
            if len(raw_result) > 1:
                data["total_cost"] = raw_result[1]
            if len(raw_result) > 2:
                alternatives = self._as_sequence(raw_result[2])
                data["alternative_paths"] = [self._normalize_path(item) for item in alternatives]
            data["edges_used"] = self._get_edges_used_in_path(path)
            return data

        if isinstance(raw_result, list):
            path = self._normalize_path(raw_result)
            return {"status": "success" if path else "failed", "path": path, "edges_used": self._get_edges_used_in_path(path), "algorithm": strategy.value}

        return {"status": "failed", "warnings": [f"Formato de resultado no soportado: {type(raw_result).__name__}"], "algorithm": strategy.value}

    @staticmethod
    def _normalize_edge_ids(edges: Any, path: List[str]) -> List[str]:
        result: List[str] = []
        edge_items = edges if isinstance(edges, (list, tuple, set)) else ([edges] if edges else [])
        for edge in edge_items:
            if isinstance(edge, str):
                result.append(edge)
            else:
                source = getattr(edge, "source_id", None)
                target = getattr(edge, "target_id", None)
                if source is not None and target is not None:
                    result.append(f"{source}->{target}")
                elif isinstance(edge, dict):
                    source = edge.get("source_id", edge.get("source"))
                    target = edge.get("target_id", edge.get("target"))
                    if source is not None and target is not None:
                        result.append(f"{source}->{target}")
        return result or [f"{src}->{dst}" for src, dst in zip(path, path[1:])]

    # ==================================================================
    # RESOLUCIÓN DE NODOS
    # ==================================================================

    def _prepare_contextual_planning_edges(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        goal: Optional[Goal] = None,
    ) -> None:
        """Añade enlaces temporales para esta búsqueda según el estado observado."""
        if not self.state_graph:
            return
        start_node = self.state_graph.nodes.get(start_node_id)
        goal_node = self.state_graph.nodes.get(goal_node_id)
        if start_node is None or goal_node is None:
            return

        if start_node.type in {NodeType.STATE, NodeType.ACTION, NodeType.APPLICATION}:
            for action in self.state_graph.nodes.values():
                if action.type != NodeType.ACTION or action.id == start_node.id:
                    continue
                if self._preconditions_satisfied(getattr(action, "preconditions", []), current_state):
                    self._add_contextual_edge_if_missing(
                        start_node.id,
                        action.id,
                        cost=self._safe_float(getattr(action, "cost", 1.0), 1.0),
                        transition_type="contextual_start",
                        preconditions=self._as_sequence(getattr(action, "preconditions", [])),
                        effects=self._as_sequence(getattr(action, "effects", [])),
                    )

        # Solo se introduce el cierre si existe evidencia de que la acción puede
        # cumplir el objetivo concreto, no solo porque ambos sean del mismo tipo.
        if goal_node.type == NodeType.GOAL:
            for action in self.state_graph.nodes.values():
                if action.type != NodeType.ACTION or action.id == goal_node.id:
                    continue
                if self._node_can_satisfy_goal(action, goal_node, current_state, goal=goal):
                    self._add_contextual_edge_if_missing(
                        action.id,
                        goal_node.id,
                        cost=0.0,
                        transition_type="contextual_goal",
                        preconditions=self._as_sequence(getattr(goal_node, "preconditions", [])),
                        effects=self._as_sequence(getattr(goal_node, "effects", [])),
                    )

        self._invalidate_graph_caches()

    def _get_start_node_for_goal(self, goal: Goal, current_state: Dict[str, Any]) -> Optional[str]:
        if not self.state_graph:
            return None

        goal_metadata = getattr(goal, "metadata", {}) or {}
        if not isinstance(goal_metadata, dict):
            goal_metadata = {}
        explicit_candidates = [
            current_state.get("start_node_id"),
            current_state.get("current_node_id"),
            current_state.get("state_node_id"),
            goal_metadata.get("start_node_id"),
        ]
        for explicit in explicit_candidates:
            if isinstance(explicit, str) and explicit.strip():
                # Un ID expreso pero inexistente es una discrepancia real; no se
                # sustituye silenciosamente por un nodo escogido por heurística.
                return explicit if explicit in self.state_graph.nodes else None

        state_candidates = [
            (self._score_state_node(node, current_state), node_id)
            for node_id, node in self.state_graph.nodes.items()
            if getattr(node, "type", None) == NodeType.STATE
        ]
        if state_candidates:
            state_candidates.sort(key=lambda item: (-item[0], item[1]))
            best_score, best_id = state_candidates[0]
            tied = len(state_candidates) > 1 and state_candidates[1][0] == best_score
            if best_score > 0 and not tied:
                return best_id
            # Una única state-node sin datos discriminantes es una opción
            # inequívoca; un nodo que contradice el estado observado no lo es.
            if len(state_candidates) == 1 and best_score >= 0:
                return best_id

        explicitly_marked = []
        for node in self.state_graph.nodes.values():
            metadata = getattr(node, "metadata", {}) or {}
            if isinstance(metadata, dict) and (
                metadata.get("is_start") is True
                or metadata.get("role") in {"start", "initial_state"}
            ):
                explicitly_marked.append(node.id)
        if len(explicitly_marked) == 1:
            return explicitly_marked[0]

        action_candidates = [
            node for node in self.state_graph.nodes.values()
            if getattr(node, "type", None) == NodeType.ACTION
            and self._preconditions_satisfied(getattr(node, "preconditions", []), current_state)
        ]
        if len(action_candidates) == 1:
            return action_candidates[0].id
        if len(self.state_graph.nodes) == 1:
            return next(iter(self.state_graph.nodes))
        return None

    def _score_state_node(self, node: Node, current_state: Dict[str, Any]) -> int:
        score = 0
        requirements: Dict[str, Any] = {}
        raw_requirements = getattr(node, "state_requirements", None)
        if isinstance(raw_requirements, dict):
            requirements.update(raw_requirements)
        metadata = getattr(node, "metadata", {}) or {}
        if isinstance(metadata, dict):
            for key in ("state_requirements", "expected_state", "state_facts"):
                value = metadata.get(key)
                if isinstance(value, dict):
                    requirements.update(value)
            for key, value in metadata.items():
                if key not in {"state_requirements", "expected_state", "state_facts", "description", "name", "role", "is_start"} and key in current_state:
                    if current_state.get(key) == value:
                        score += 2
                    else:
                        score -= 1

        if requirements:
            matches = sum(1 for key, value in requirements.items() if current_state.get(key) == value)
            mismatches = sum(1 for key, value in requirements.items() if key in current_state and current_state.get(key) != value)
            score += matches * 4 - mismatches * 3

        node_id_key = current_state.get("current_node_id", current_state.get("state_node_id"))
        if node_id_key == node.id:
            score += 100
        return score

    def _get_goal_node_for_goal(self, goal: Goal) -> Optional[str]:
        if not self.state_graph:
            return None
        metadata = getattr(goal, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        explicit_goal_id = getattr(goal, "graph_goal_node_id", None) or metadata.get("graph_goal_node_id") or metadata.get("goal_node_id")
        if isinstance(explicit_goal_id, str) and explicit_goal_id.strip():
            # Un objetivo ligado explícitamente a un nodo ausente no debe
            # redirigirse a otro nodo por coincidencia textual.
            return explicit_goal_id if explicit_goal_id in self.state_graph.nodes else None

        goal_id = getattr(goal, "id", None)
        goal_type = str(getattr(goal, "type", "") or "").strip().lower()
        target = getattr(goal, "target", None)
        target_terms = self._goal_target_terms(target)

        # Primero, correspondencia estructurada por ID, tipo y target en nodos GOAL.
        goal_candidates: List[Tuple[int, str]] = []
        for node_id, node in self.state_graph.nodes.items():
            if getattr(node, "type", None) != NodeType.GOAL:
                continue
            node_metadata = getattr(node, "metadata", {}) or {}
            if not isinstance(node_metadata, dict):
                continue
            if node_metadata.get("goal_id") == goal_id:
                return node_id
            score = 0
            if goal_type and str(node_metadata.get("goal_type", "")).strip().lower() == goal_type:
                score += 5
            candidate_target = node_metadata.get("target", node_metadata.get("goal_target"))
            if candidate_target is not None and target_terms:
                candidate_terms = self._goal_target_terms(candidate_target)
                overlap = len(target_terms.intersection(candidate_terms))
                if overlap:
                    score += 5 * overlap
            if score:
                goal_candidates.append((score, node_id))
        if goal_candidates:
            goal_candidates.sort(key=lambda item: (-item[0], item[1]))
            if len(goal_candidates) == 1 or goal_candidates[0][0] > goal_candidates[1][0]:
                return goal_candidates[0][1]
            return None

        # Si el objetivo no tiene un nodo GOAL explícito, puede mapearse a una
        # acción solo con coincidencia semántica suficiente y no ambigua.
        action_candidates: List[Tuple[int, str]] = []
        for node_id, node in self.state_graph.nodes.items():
            if getattr(node, "type", None) != NodeType.ACTION:
                continue
            node_metadata = getattr(node, "metadata", {}) or {}
            if not isinstance(node_metadata, dict):
                node_metadata = {}
            score = 0
            if node_metadata.get("goal_id") == goal_id:
                score += 100
            if goal_type and str(node_metadata.get("goal_type", "")).strip().lower() == goal_type:
                score += 20
            candidate_target = node_metadata.get("goal_target", node_metadata.get("target"))
            if candidate_target is not None and target_terms:
                overlap = len(target_terms.intersection(self._goal_target_terms(candidate_target)))
                if overlap:
                    score += 15 * overlap
            haystack = self._normalize_text(" ".join((node_id, str(getattr(node, "name", "")), str(getattr(node, "description", "")))))
            normalized_goal_type = self._normalize_text(goal_type)
            if normalized_goal_type and normalized_goal_type in haystack:
                score += 5
            for term in target_terms:
                if len(term) >= 3 and term in haystack:
                    score += 3
            if score:
                action_candidates.append((score, node_id))
        if action_candidates:
            action_candidates.sort(key=lambda item: (-item[0], item[1]))
            if len(action_candidates) == 1 or action_candidates[0][0] > action_candidates[1][0]:
                return action_candidates[0][1]

        # Un único nodo GOAL sigue siendo una selección no ambigua; varios nodos
        # genéricos no se resuelven por orden de inserción.
        all_goal_ids = [node_id for node_id, node in self.state_graph.nodes.items() if getattr(node, "type", None) == NodeType.GOAL]
        return all_goal_ids[0] if len(all_goal_ids) == 1 else None

    def _node_can_satisfy_goal(
        self,
        action_node: Node,
        goal_node: Node,
        current_state: Dict[str, Any],
        goal: Optional[Goal] = None,
    ) -> bool:
        """Comprueba compatibilidad con evidencia, priorizando el target exacto."""
        node_metadata = getattr(goal_node, "metadata", {}) or {}
        if not isinstance(node_metadata, dict):
            node_metadata = {}
        action_metadata = getattr(action_node, "metadata", {}) or {}
        if not isinstance(action_metadata, dict):
            action_metadata = {}
        goal_id = str(getattr(goal, "id", None) or node_metadata.get("goal_id", "") or "").strip()
        goal_type = str(getattr(goal, "type", None) or node_metadata.get("goal_type", "") or "").strip().lower()
        target = getattr(goal, "target", None) if goal is not None else None
        if target is None:
            target = node_metadata.get("target", node_metadata.get("goal_target"))

        action_goal_id = str(action_metadata.get("goal_id", "") or "").strip()
        if goal_id and action_goal_id == goal_id:
            return True

        action_goal_type = str(action_metadata.get("goal_type", "") or "").strip().lower()
        action_target = action_metadata.get("goal_target", action_metadata.get("target"))
        if goal_type and action_goal_type == goal_type and (target is None or action_target == target):
            return True

        effects = self._as_sequence(getattr(action_node, "effects", []))
        target_value = target
        if isinstance(target, dict):
            if goal_type in {"navigate", "navigate_stream", "streaming"}:
                target_value = target.get("url", target.get("target_url", target.get("target")))
            elif goal_type in {"open_application", "close_application"}:
                target_value = target.get("app_name", target.get("application", target.get("name", target.get("target"))))
            elif goal_type == "search":
                target_value = target.get("query", target.get("search_query", target.get("target")))

        if target_value not in (None, ""):
            if goal_type in {"navigate", "navigate_stream", "streaming"}:
                return self._effects_support_preconditions(
                    effects,
                    [{"type": "state_equals", "key": "current_url", "value": target_value}],
                )

            if goal_type == "open_application":
                target_name = str(target_value).strip().casefold()
                for item in effects:
                    effect_type, effect_key, effect_value, params = self._effect_fields(item)
                    effect_app = str(params.get("app_name", params.get("application", ""))).strip().casefold()
                    key = str(effect_key or "").strip().casefold()
                    if effect_type == "application_open" and (
                        effect_app == target_name or key == f"{target_name}_open"
                    ):
                        return True
                    if key == f"{target_name}_open" and effect_value is True:
                        return True
                return False

            if goal_type == "close_application":
                target_name = str(target_value).strip().casefold()
                for item in effects:
                    effect_type, effect_key, _effect_value, params = self._effect_fields(item)
                    effect_app = str(params.get("app_name", params.get("application", ""))).strip().casefold()
                    key = str(effect_key or "").strip().casefold()
                    if effect_type == "application_close" and (effect_app == target_name or key == f"{target_name}_open"):
                        return True
                return False

            if goal_type == "search":
                if action_metadata.get("query") == target_value or action_metadata.get("search_query") == target_value:
                    return True
                return False

            # Para otros objetivos, una metadata explícita puede establecer la
            # relación; si no existe, no se infiere por coincidencia textual.
            return False

        if goal_type:
            return self._goal_type_matches_effects(goal_type, effects)
        return self._goal_satisfied_by_effects(current_state, effects)

    @staticmethod
    def _goal_type_matches_effects(goal_type: str, effects: Any) -> bool:
        normalized_goal = str(goal_type or "").strip().lower()
        expected_by_goal = {
            "navigate": {("current_url", None), ("url_changed", True), ("page_loaded", True)},
            "navigate_stream": {("current_url", None), ("stream_loaded", True), ("page_loaded", True)},
            "open_application": {("application_open", True)},
            "close_application": {("application_close", True)},
            "search": {("search_performed", True), ("search_results", None)},
            "login": {("logged_in", True), ("authenticated", True), ("authorized", True)},
        }
        expected = expected_by_goal.get(normalized_goal, set())
        if not expected:
            return False

        for effect in GraphPlannerIntegration._as_sequence(effects):
            if isinstance(effect, dict):
                effect_type = str(effect.get("type", "state_set")).strip().lower()
                key = str(effect.get("key", effect.get("state", ""))).strip().lower()
                value = effect.get("value", True)
                params = effect.get("parameters", {}) or {}
            else:
                effect_type = str(getattr(getattr(effect, "type", ""), "value", getattr(effect, "type", ""))).strip().lower()
                key = str(getattr(effect, "key", "") or "").strip().lower()
                value = getattr(effect, "value", True)
                params = getattr(effect, "parameters", {}) or {}
            if not isinstance(params, dict):
                params = {}

            if normalized_goal in {"open_application", "close_application"}:
                expected_type = "application_open" if normalized_goal == "open_application" else "application_close"
                if effect_type == expected_type:
                    return True
                app_name = str(params.get("app_name", "")).strip().lower()
                if app_name and key in {f"{app_name}_open", f"{app_name}_active"}:
                    if normalized_goal == "open_application" and value is True:
                        return True
                    if normalized_goal == "close_application" and value is False:
                        return True
            else:
                for expected_key, expected_value in expected:
                    if expected_value is None and key == expected_key:
                        return True
                    if key == expected_key and value == expected_value:
                        return True
                    if effect_type == expected_key:
                        return True
        return False

    # ==================================================================
    # COSTES / METADATOS
    # ==================================================================

    def _calculate_path_cost(self, path: List[str], current_state: Optional[Dict[str, Any]] = None) -> float:
        if not self.state_graph or len(path) < 2:
            return 0.0
        state = self._copy_state(current_state)
        total = 0.0
        for source_id, target_id in zip(path, path[1:]):
            edge = self._find_edge(source_id, target_id, state)
            if edge is None:
                return float("inf")
            try:
                edge_cost = self._safe_float(edge.get_total_cost(state), float("inf"))
            except Exception:
                edge_cost = self._safe_float(getattr(edge, "cost", float("inf")), float("inf"))
            if not math.isfinite(edge_cost) or edge_cost < 0:
                return float("inf")
            total += edge_cost
            if not math.isfinite(total):
                return float("inf")
            try:
                new_state = edge.apply_effects(state)
                if isinstance(new_state, dict):
                    state = new_state
            except Exception:
                logger.debug("[GRAPH-INTEGRATION] No se pudieron aplicar efectos al recalcular la ruta", exc_info=True)
        return total

    def _find_edge(self, source_id: str, target_id: str, state: Dict[str, Any]) -> Any:
        if not self.state_graph:
            return None
        candidates = [
            edge for edge in self.state_graph.edges
            if edge.source_id == source_id and edge.target_id == target_id
        ]
        for edge in candidates:
            try:
                if edge.can_traverse(state):
                    return edge
            except Exception:
                continue
        return None

    @staticmethod
    def _get_edges_used_in_path(path: List[str]) -> List[str]:
        return [f"{source_id}->{target_id}" for source_id, target_id in zip(path, path[1:])]

    def _convert_path_to_plan_metadata(
        self,
        path: List[str],
        available_nodes: Dict[str, Node],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for node_id in path:
            node = available_nodes.get(node_id)
            if node is None or node.type != NodeType.ACTION:
                continue
            try:
                cost = float(getattr(node, "cost", 1.0) or 1.0)
            except (TypeError, ValueError):
                cost = 1.0
            entries.append(
                {
                    "id": node.id,
                    "name": getattr(node, "name", node.id),
                    "description": getattr(node, "description", ""),
                    "type": node.type.value if hasattr(node.type, "value") else str(node.type),
                    "cost": cost,
                    "application": getattr(node, "application", None),
                    "parameters": dict(getattr(node, "parameters", {}) or {}),
                    "preconditions": list(getattr(node, "preconditions", []) or []),
                    "effects": list(getattr(node, "effects", []) or []),
                    "metadata": {
                        "node_type": "graph_action",
                        "node_id": node_id,
                        "executable": False,
                    },
                }
            )
        return entries

    def _update_performance_metrics(self, plan_entries: List[Dict[str, Any]], execution_time: float, total_cost: float) -> None:
        if self.successful_plans > 0:
            self.average_plan_length = (
                (self.average_plan_length * (self.successful_plans - 1)) + len(plan_entries)
            ) / self.successful_plans
        if not self.state_graph:
            return
        metrics = getattr(self.state_graph, "performance_metrics", None)
        record_search = getattr(metrics, "record_search", None) if metrics else None
        if callable(record_search):
            try:
                record_search(
                    success=True,
                    path_length=len(plan_entries),
                    cost=total_cost,
                    search_time=execution_time,
                    iterations=max(1, len(plan_entries)),
                )
            except Exception:
                logger.debug("[GRAPH-INTEGRATION] No se pudieron registrar métricas del grafo", exc_info=True)

    # ==================================================================
    # PRECONDICIONES / EFECTOS
    # ==================================================================

    def _preconditions_satisfied(self, preconditions: Any, state: Dict[str, Any]) -> bool:
        if not preconditions:
            return True
        if not isinstance(state, dict):
            return False
        if isinstance(preconditions, dict) and not any(key in preconditions for key in ("type", "key", "state", "conditions", "function")):
            return all(state.get(key) == value for key, value in preconditions.items())
        return all(self._evaluate_condition_like(condition, state) for condition in self._as_sequence(preconditions))

    @staticmethod
    def _effects_support_preconditions(effects: Any, preconditions: Any) -> bool:
        """Indica si todos los requisitos podrían quedar garantizados por los efectos."""
        if not preconditions:
            # Un requisito vacío no ofrece evidencia para crear una arista entre
            # dos acciones que de otro modo no tienen relación declarada.
            return False
        if isinstance(preconditions, dict) and not any(key in preconditions for key in ("type", "key", "state", "conditions", "function")):
            conditions: List[Any] = [{"type": "state_equals", "key": key, "value": value} for key, value in preconditions.items()]
        else:
            conditions = GraphPlannerIntegration._as_sequence(preconditions)
        effect_items = GraphPlannerIntegration._as_sequence(effects)
        if not effect_items:
            return False
        return all(GraphPlannerIntegration._condition_supported_by_effects(condition, effect_items) for condition in conditions)

    @staticmethod
    def _condition_supported_by_effects(condition: Any, effects: List[Any]) -> bool:
        """Comprueba compatibilidad declarativa; no adivina el efecto de callbacks."""
        kind = ""
        key = None
        expected = None
        children = None
        operator = "and"
        params: Dict[str, Any] = {}

        if isinstance(condition, str):
            text = condition.strip()
            if not text:
                return False
            if ":" in text:
                key, raw_expected = text.split(":", 1)
                return GraphPlannerIntegration._key_value_supported(key.strip(), raw_expected.strip(), effects, stringify=True)
            if text.endswith("_not_met"):
                return GraphPlannerIntegration._key_value_supported(text[:-8], False, effects)
            return GraphPlannerIntegration._key_value_supported(text, True, effects)

        if isinstance(condition, dict):
            if "conditions" in condition:
                children = condition.get("conditions", [])
                operator = str(condition.get("operator", condition.get("op", "and"))).strip().lower()
                if operator not in {"and", "or"}:
                    return False
                results = [GraphPlannerIntegration._condition_supported_by_effects(item, effects) for item in GraphPlannerIntegration._as_sequence(children)]
                return (all(results) if operator == "and" else any(results)) and bool(results)
            if callable(condition.get("function")):
                return False
            kind = str(condition.get("type", "state_equals" if ("key" in condition or "state" in condition) else "")).strip().lower()
            key = condition.get("key", condition.get("state"))
            expected = condition.get("value", condition.get("expected_value", condition.get("expected")))
            params = condition.get("parameters", {}) or {}
            if not kind:
                return all(GraphPlannerIntegration._key_value_supported(k, v, effects) for k, v in condition.items())
        else:
            kind_value = getattr(condition, "type", None)
            kind = str(getattr(kind_value, "value", kind_value) or "").strip().lower()
            key = getattr(condition, "key", None)
            expected = getattr(condition, "expected_value", None)
            params = getattr(condition, "parameters", {}) or {}
            if kind in {"composite_and", "composite_or"}:
                children = params.get("conditions", []) if isinstance(params, dict) else []
                results = [GraphPlannerIntegration._condition_supported_by_effects(item, effects) for item in GraphPlannerIntegration._as_sequence(children)]
                return (all(results) if kind == "composite_and" else any(results)) and bool(results)
            if callable(getattr(condition, "function", None)) or kind == "custom_function":
                return False

        if not isinstance(params, dict):
            params = {}
        normalized_key = str(key or "").strip()
        if kind in {"application_open", "application_active"}:
            app_name = params.get("app_name") or params.get("application") or normalized_key
            flag = "open" if kind == "application_open" else "active"
            expected_value = True if expected is None else expected
            return GraphPlannerIntegration._key_value_supported(f"{str(app_name).strip().lower()}_{flag}", expected_value, effects)
        if kind in {"ui_element_available", "ui_element_calibrated"}:
            app_name = params.get("app_name") or params.get("application") or ""
            element = params.get("element_name") or normalized_key
            suffix = "available" if kind == "ui_element_available" else "calibrated"
            expected_value = True if expected is None else expected
            return GraphPlannerIntegration._key_value_supported(f"{str(app_name).strip().lower()}_{str(element).strip().lower()}_{suffix}", expected_value, effects)
        if kind in {"state_true", "true"}:
            return GraphPlannerIntegration._key_value_supported(normalized_key, True, effects)
        if kind in {"state_false", "false"}:
            return GraphPlannerIntegration._key_value_supported(normalized_key, False, effects)
        if kind in {"state_equals", "equals", "state_equal", "state_exists", "exists"}:
            if kind in {"state_exists", "exists"}:
                return GraphPlannerIntegration._has_effect_key(normalized_key, effects)
            return GraphPlannerIntegration._key_value_supported(normalized_key, expected, effects)
        if kind in {"state_greater_than", "greater_than", "gt", "state_less_than", "less_than", "lt"}:
            return GraphPlannerIntegration._condition_numeric_supported(normalized_key, kind, expected, effects)
        return False

    @staticmethod
    def _has_effect_key(key: str, effects: List[Any]) -> bool:
        target = str(key).strip().lower()
        if not target:
            return False
        for effect in GraphPlannerIntegration._as_sequence(effects):
            effect_type, effect_key, effect_value, params = GraphPlannerIntegration._effect_fields(effect)
            if effect_key is None:
                continue
            normalized_key = str(effect_key).strip().lower()
            candidates = {normalized_key}
            app_name = str(params.get("app_name", params.get("application", ""))).strip().lower()
            if effect_type in {"application_open", "application_close", "application_activate"}:
                app_name = app_name or normalized_key.removesuffix("_open").removesuffix("_active")
                if app_name:
                    candidates.update({f"{app_name}_open", f"{app_name}_active"})
            if effect_type == "ui_element_calibrate":
                app_name = app_name or ""
                element = str(params.get("element_name", normalized_key)).strip().lower()
                if app_name:
                    candidates.update({f"{app_name}_{element}_calibrated", f"{app_name}_{element}_available"})
            if target in candidates:
                return True
        return False

    @staticmethod
    def _key_value_supported(key: Any, expected: Any, effects: List[Any], stringify: bool = False) -> bool:
        target = str(key).strip().lower()
        if not target:
            return False
        for effect in GraphPlannerIntegration._as_sequence(effects):
            effect_type, effect_key, effect_value, params = GraphPlannerIntegration._effect_fields(effect)
            if effect_key is None:
                continue
            normalized_key = str(effect_key).strip().lower()
            facts: Dict[str, Any] = {normalized_key: effect_value}
            app_name = str(params.get("app_name", params.get("application", ""))).strip().lower()
            if effect_type == "application_open":
                app_name = app_name or normalized_key.removesuffix("_open")
                facts.update({f"{app_name}_open": True, f"{app_name}_active": True})
            elif effect_type == "application_close":
                app_name = app_name or normalized_key.removesuffix("_open")
                facts.update({f"{app_name}_open": False, f"{app_name}_active": False})
            elif effect_type == "application_activate":
                app_name = app_name or normalized_key.removesuffix("_active")
                facts[f"{app_name}_active"] = True
            elif effect_type == "ui_element_calibrate":
                element = str(params.get("element_name", normalized_key)).strip().lower()
                if app_name:
                    facts[f"{app_name}_{element}_calibrated"] = True
                    facts[f"{app_name}_{element}_available"] = True

            if target not in facts:
                continue
            actual = facts[target]
            if stringify:
                if str(actual).strip().casefold() == str(expected).strip().casefold():
                    return True
            elif actual == expected:
                return True
        # Legacy compact representation: "key:value".
        for effect in GraphPlannerIntegration._as_sequence(effects):
            if isinstance(effect, str) and ":" in effect:
                effect_key, effect_value = effect.split(":", 1)
                if effect_key.strip().lower() == target:
                    if (str(effect_value).strip().casefold() == str(expected).strip().casefold()) if stringify else effect_value.strip() == str(expected):
                        return True
        return False

    @staticmethod
    def _goal_satisfied_by_effects(current_state: Dict[str, Any], effects: Any) -> bool:
        if not isinstance(current_state, dict):
            return False
        for effect in GraphPlannerIntegration._as_sequence(effects):
            effect_type, key, value, params = GraphPlannerIntegration._effect_fields(effect)
            if key is None:
                continue
            facts: Dict[str, Any] = {str(key): value}
            app_name = str(params.get("app_name", params.get("application", ""))).strip().lower()
            normalized_key = str(key).strip().lower()
            if effect_type == "application_open":
                app_name = app_name or normalized_key.removesuffix("_open")
                facts.update({f"{app_name}_open": True, f"{app_name}_active": True})
            elif effect_type == "application_close":
                app_name = app_name or normalized_key.removesuffix("_open")
                facts.update({f"{app_name}_open": False, f"{app_name}_active": False})
            for state_key, desired in facts.items():
                if state_key in current_state and current_state.get(state_key) == desired:
                    return True
        return False

    # ==================================================================
    # ESTADÍSTICAS / PERSISTENCIA
    # ==================================================================

    def _calculate_graph_metrics(self) -> None:
        if not self.state_graph:
            return
        num_nodes = len(self.state_graph.nodes)
        num_edges = len(self.state_graph.edges)
        denominator = num_nodes * (num_nodes - 1)
        self.state_graph.graph_metrics = {
            "nodes": num_nodes,
            "edges": num_edges,
            "density": min(1.0, num_edges / denominator) if denominator > 0 else 0.0,
            "average_degree": num_edges / num_nodes if num_nodes else 0.0,
        }

    def get_integration_statistics(self) -> Dict[str, Any]:
        total = self.total_plans_created
        return {
            "total_plans_created": total,
            "successful_plans": self.successful_plans,
            "failed_plans": self.failed_plans,
            "success_rate": self.successful_plans / total if total else 0.0,
            "average_plan_length": self.average_plan_length,
            "use_astar": self.use_astar,
            "integration_mode": self.integration_mode.value,
            "graph_initialized": self.state_graph is not None,
            "performance_metrics": self.performance_metrics.to_dict(),
        }

    def export_graph_state(self, filepath: str) -> bool:
        if not self.state_graph:
            logger.warning("[GRAPH-INTEGRATION] No hay grafo para exportar")
            return False

        normalized_path = str(filepath)
        lower = normalized_path.lower()
        methods = []
        if lower.endswith(".json"):
            methods = [("export_graph", {"file_path": normalized_path, "format": "json"})]
        elif lower.endswith((".pkl", ".pickle")):
            methods = [("export_graph", {"file_path": normalized_path, "format": "pickle"})]
        else:
            methods = [
                ("export_graph", {"file_path": normalized_path, "format": "json"}),
                ("export_to_json", {}),
            ]

        for method_name, kwargs in methods:
            method = getattr(self.state_graph, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(**kwargs)
                if method_name == "export_to_json" and isinstance(result, dict):
                    import json
                    with open(normalized_path, "w", encoding="utf-8") as file:
                        json.dump(result, file, ensure_ascii=False, indent=2, default=str)
                    result = True
                if result is not False:
                    logger.info("[GRAPH-INTEGRATION] Grafo exportado: %s", normalized_path)
                    return True
            except Exception as exc:
                logger.debug("[GRAPH-INTEGRATION] Fallo exportando con %s", method_name, exc_info=True)
        return False

    def import_graph_state(self, filepath: str) -> bool:
        if not self.state_graph:
            self.state_graph = AdvancedStateGraph(self.heuristic)
        try:
            lower = str(filepath).lower()
            if lower.endswith((".pkl", ".pickle")):
                method = getattr(self.state_graph, "import_graph", None)
                if callable(method):
                    imported = bool(method(filepath, format="pickle"))
                    if imported:
                        self._contextual_edges.clear()
                        self._calculate_graph_metrics()
                        self._invalidate_graph_caches()
                    return imported
            method = getattr(self.state_graph, "import_graph", None)
            if callable(method):
                result = method(filepath, format="json")
                if result:
                    self._contextual_edges.clear()
                    self._calculate_graph_metrics()
                    self._invalidate_graph_caches()
                return bool(result)

            method = getattr(self.state_graph, "import_from_json", None)
            if callable(method):
                import json
                with open(filepath, "r", encoding="utf-8") as file:
                    data = json.load(file)
                method(data)
                self._contextual_edges.clear()
                self._calculate_graph_metrics()
                self._invalidate_graph_caches()
                return True
        except Exception as exc:
            logger.exception("[GRAPH-INTEGRATION] Error durante la planificación")
        return False

    def validate_graph_consistency(self) -> Dict[str, Any]:
        if not self.state_graph:
            return {"valid": False, "errors": ["Grafo no inicializado"]}

        advanced = getattr(self.state_graph, "validate_graph_advanced", None)
        if callable(advanced):
            try:
                result = advanced()
                if isinstance(result, tuple) and len(result) >= 2:
                    errors, stats = result[0], result[1]
                    errors = list(errors or [])
                    return {"valid": not errors, "errors": errors, "stats": dict(stats or {})}
            except Exception as exc:
                logger.debug("[GRAPH-INTEGRATION] Fallo en validación avanzada", exc_info=True)

        validator = getattr(self.state_graph, "validate_graph", None)
        if callable(validator):
            try:
                result = validator()
                if isinstance(result, list):
                    return {"valid": not result, "errors": list(result)}
                if isinstance(result, tuple):
                    errors = list(result[0] or []) if result else []
                    return {"valid": not errors, "errors": errors}
                if isinstance(result, dict):
                    return result
                return {"valid": bool(result), "errors": [] if result else ["Validación fallida"]}
            except Exception as exc:
                return {"valid": False, "errors": [f"Error en validación: {exc}"]}

        return {"valid": True, "errors": [], "warnings": ["El grafo no expone un validador explícito"]}

    @staticmethod
    def _as_sequence(value: Any) -> List[Any]:
        """Normaliza colecciones sin separar strings ni diccionarios en sus partes."""
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, (tuple, set)):
            return list(value)
        return [value]

    @staticmethod
    def _normalize_path(value: Any) -> List[str]:
        """Normaliza una ruta y descarta entradas vacías/no textuales."""
        if isinstance(value, str):
            raw_items = [value]
        elif isinstance(value, (list, tuple)):
            raw_items = list(value)
        else:
            return []
        if any(not isinstance(item, str) or not item for item in raw_items):
            return []
        return list(raw_items)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").casefold().replace("_", " ").replace(".", " ").replace("-", " ").split())

    @staticmethod
    def _goal_target_terms(target: Any) -> Set[str]:
        """Extrae términos de target manteniendo las claves/valores existentes."""
        if isinstance(target, dict):
            values: List[Any] = []
            for key in ("app_name", "application", "name", "url", "target_url", "entity", "query", "search_query", "streamer", "platform", "target"):
                if target.get(key) not in (None, ""):
                    values.append(target[key])
            if not values:
                values.extend(target.values())
        elif isinstance(target, (list, tuple, set)):
            values = list(target)
        elif target in (None, ""):
            values = []
        else:
            values = [target]
        terms: Set[str] = set()
        for value in values:
            normalized = GraphPlannerIntegration._normalize_text(value)
            if normalized:
                terms.add(normalized)
                for token in normalized.split():
                    if len(token) >= 3:
                        terms.add(token)
        return terms

    @staticmethod
    def _effect_fields(effect: Any) -> Tuple[str, Any, Any, Dict[str, Any]]:
        if isinstance(effect, dict):
            effect_type = str(getattr(effect.get("type", "state_set"), "value", effect.get("type", "state_set"))).strip().lower()
            key = effect.get("key", effect.get("state"))
            value = effect.get("value", True)
            params = effect.get("parameters", {}) or {}
        elif isinstance(effect, str):
            effect_type, key, value, params = "state_set", effect, True, {}
            if ":" in effect:
                key, raw_value = effect.split(":", 1)
                key, value = key.strip(), raw_value.strip()
        else:
            raw_type = getattr(effect, "type", "state_set")
            effect_type = str(getattr(raw_type, "value", raw_type)).strip().lower()
            key = getattr(effect, "key", None)
            value = getattr(effect, "value", True)
            params = getattr(effect, "parameters", {}) or {}
        if not isinstance(params, dict):
            params = {}
        return effect_type, key, value, params

    @staticmethod
    def _condition_numeric_supported(key: str, kind: str, expected: Any, effects: List[Any]) -> bool:
        for effect in GraphPlannerIntegration._as_sequence(effects):
            effect_type, effect_key, value, _ = GraphPlannerIntegration._effect_fields(effect)
            if str(effect_key or "").strip().lower() != str(key or "").strip().lower():
                continue
            try:
                actual = float(value)
                boundary = float(expected)
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(actual) or not math.isfinite(boundary):
                return False
            if kind in {"state_greater_than", "greater_than", "gt"} and actual > boundary:
                return True
            if kind in {"state_less_than", "less_than", "lt"} and actual < boundary:
                return True
        return False

    @staticmethod
    def _evaluate_condition_like(condition: Any, state: Dict[str, Any]) -> bool:
        """Evalúa condiciones declarativas compatibles, fallando de forma segura."""
        snapshot = GraphPlannerIntegration._copy_state(state)
        try:
            if isinstance(condition, str):
                text = condition.strip()
                if not text:
                    return False
                if ":" in text:
                    key, expected = text.split(":", 1)
                    return str(snapshot.get(key.strip())) == expected.strip()
                if text.endswith("_not_met"):
                    return not bool(snapshot.get(text[:-8], False))
                return bool(snapshot.get(text, False))

            if callable(condition):
                return bool(condition(snapshot))
            evaluator = getattr(condition, "evaluate", None)
            if callable(evaluator):
                return bool(evaluator(snapshot))
            checker = getattr(condition, "check", None)
            if callable(checker):
                return bool(checker(snapshot))

            if isinstance(condition, dict):
                if "conditions" in condition:
                    operator = str(condition.get("operator", condition.get("op", "and"))).strip().lower()
                    children = condition.get("conditions", [])
                    if operator not in {"and", "or"}:
                        return False
                    results = [GraphPlannerIntegration._evaluate_condition_like(item, snapshot) for item in GraphPlannerIntegration._as_sequence(children)]
                    return all(results) if operator == "and" else any(results)
                function = condition.get("function")
                if callable(function):
                    return bool(function(snapshot))
                structured = any(key in condition for key in ("type", "key", "state"))
                if not structured:
                    return all(snapshot.get(key) == value for key, value in condition.items())
                kind = str(getattr(condition.get("type", "state_equals"), "value", condition.get("type", "state_equals"))).strip().lower()
                key = condition.get("key", condition.get("state"))
                expected = condition.get("value", condition.get("expected_value", condition.get("expected")))
                params = condition.get("parameters", {}) or {}
            else:
                return False

            if not isinstance(params, dict):
                params = {}
            if kind in {"state_equals", "equals", "state_equal"}:
                return snapshot.get(key) == expected
            if kind in {"state_exists", "exists"}:
                return key in snapshot and snapshot.get(key) is not None
            if kind in {"state_true", "true"}:
                return bool(snapshot.get(key, False))
            if kind in {"state_false", "false"}:
                return not bool(snapshot.get(key, False))
            if kind in {"state_greater_than", "greater_than", "gt", "state_less_than", "less_than", "lt"}:
                try:
                    left, right = float(snapshot.get(key, 0)), float(expected)
                except (TypeError, ValueError, OverflowError):
                    return False
                if not math.isfinite(left) or not math.isfinite(right):
                    return False
                return left > right if kind in {"state_greater_than", "greater_than", "gt"} else left < right
            if kind in {"application_open", "application_active"}:
                app_name = str(params.get("app_name", params.get("application", key or ""))).strip().lower()
                flag = "open" if kind == "application_open" else "active"
                app_state = None
                for container_name in ("applications", "application_states"):
                    container = snapshot.get(container_name)
                    if isinstance(container, dict):
                        for app_key, candidate in container.items():
                            if GraphPlannerIntegration._normalize_text(app_key) == GraphPlannerIntegration._normalize_text(app_name) and isinstance(candidate, dict):
                                app_state = candidate
                                break
                    if app_state is not None:
                        break
                if isinstance(app_state, dict) and flag in app_state:
                    return bool(app_state[flag])
                for candidate_key in (f"{app_name}_{flag}", f"app_{app_name}_{flag}", f"{app_name}.{flag}"):
                    if candidate_key in snapshot:
                        return bool(snapshot[candidate_key])
                return False
            if kind in {"ui_element_available", "ui_element_calibrated"}:
                app_name = GraphPlannerIntegration._normalize_text(params.get("app_name", params.get("application", ""))).replace(" ", "_")
                element_name = GraphPlannerIntegration._normalize_text(params.get("element_name", key or "")).replace(" ", "_")
                flag = "available" if kind == "ui_element_available" else "calibrated"
                return bool(snapshot.get(f"{app_name}_{element_name}_{flag}", snapshot.get(f"ui_{app_name}_{element_name}_{flag}", False)))
            if kind in {"composite_and", "composite_or"}:
                children = params.get("conditions", [])
                results = [GraphPlannerIntegration._evaluate_condition_like(item, snapshot) for item in GraphPlannerIntegration._as_sequence(children)]
                return all(results) if kind == "composite_and" else any(results)
            if kind == "custom_function":
                function = condition.get("function") if isinstance(condition, dict) else None
                return bool(function(snapshot)) if callable(function) else False
            return False
        except Exception:
            return False

    @staticmethod
    def _copy_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {}
        try:
            copied = deepcopy(state)
            return copied if isinstance(copied, dict) else dict(state)
        except Exception:
            return dict(state)

    def _add_contextual_edge_if_missing(
        self,
        source_id: str,
        target_id: str,
        cost: float,
        transition_type: str,
        preconditions: Optional[List[Any]] = None,
        effects: Optional[List[Any]] = None,
    ) -> bool:
        if not self.state_graph:
            return False
        if any(edge.source_id == source_id and edge.target_id == target_id for edge in self.state_graph.edges):
            return False
        added = self.state_graph.add_edge(
            source_id,
            target_id,
            cost=cost,
            conditions=[],
            transition_type=transition_type,
            preconditions=self._as_sequence(preconditions),
            effects=self._as_sequence(effects),
        )
        if added:
            for edge in reversed(self.state_graph.edges):
                if edge.source_id == source_id and edge.target_id == target_id and edge.transition_type == transition_type:
                    self._contextual_edges.append(edge)
                    break
            self._invalidate_graph_caches()
        return bool(added)

    def _remove_contextual_planning_edges(self) -> None:
        if not self.state_graph or not self._contextual_edges:
            self._contextual_edges.clear()
            return
        contextual_ids = {id(edge) for edge in self._contextual_edges}
        self.state_graph.edges = [edge for edge in self.state_graph.edges if id(edge) not in contextual_ids]
        self._contextual_edges.clear()
        # Reconstruir listas auxiliares de Node para que no queden enlaces obsoletos.
        for node_id, node in self.state_graph.nodes.items():
            outgoing = [edge for edge in self.state_graph.edges if edge.source_id == node_id]
            incoming = [edge for edge in self.state_graph.edges if edge.target_id == node_id]
            try:
                node.out_edges = list(dict.fromkeys(edge.target_id for edge in outgoing))
                node.in_edges = list(dict.fromkeys(edge.source_id for edge in incoming))
                node.edge_costs = {edge.target_id: edge.cost for edge in outgoing}
            except Exception:
                logger.debug("No se pudieron reconstruir los enlaces auxiliares de %s", node_id, exc_info=True)
        self._calculate_graph_metrics()
        revision_invalidator = getattr(self.state_graph, "_invalidate_search_cache", None)
        if callable(revision_invalidator):
            try:
                revision_invalidator()
            except Exception:
                logger.debug("No se pudo actualizar la revisión del grafo", exc_info=True)
        self._invalidate_graph_caches()

    def _invalidate_graph_caches(self) -> None:
        graph = self.state_graph
        if graph is None:
            return
        clear = getattr(graph, "clear_search_cache", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                logger.debug("No se pudo invalidar la caché de búsqueda", exc_info=True)
        heuristic = getattr(graph, "heuristic", None)
        clear_heuristic = getattr(heuristic, "clear_cache", None)
        if callable(clear_heuristic):
            try:
                clear_heuristic()
            except Exception:
                logger.debug("No se pudo invalidar la caché de heurística", exc_info=True)

    def _validate_route_path(
        self,
        path: List[str],
        start_node_id: str,
        goal_node_id: str,
        initial_state: Dict[str, Any],
    ) -> List[str]:
        if not path:
            return ["La búsqueda devolvió una ruta vacía"]
        if path[0] != start_node_id or path[-1] != goal_node_id:
            return ["La ruta no coincide con los nodos inicial y final solicitados"]
        if not self.state_graph:
            return ["Grafo no inicializado"]
        for node_id in path:
            if node_id not in self.state_graph.nodes:
                return [f"La ruta contiene un nodo inexistente: {node_id}"]
        state = self._copy_state(initial_state)
        for source_id, target_id in zip(path, path[1:]):
            edge = self._find_edge(source_id, target_id, state)
            if edge is None:
                return [f"La ruta contiene una transición no válida en el estado actual: {source_id} -> {target_id}"]
            try:
                updated = edge.apply_effects(state)
                if isinstance(updated, dict):
                    state = updated
            except Exception:
                logger.debug("No se pudieron simular los efectos al validar %s -> %s", source_id, target_id, exc_info=True)
        return []

    def _record_integration_search(self, success: bool, path_length: int, cost: float, elapsed: float) -> None:
        recorder = getattr(self.performance_metrics, "record_search", None)
        if not callable(recorder):
            return
        try:
            recorder(
                success=bool(success),
                path_length=max(0, int(path_length)),
                cost=self._safe_float(cost, 0.0),
                search_time=max(0.0, self._safe_float(elapsed, 0.0)),
                iterations=0,
            )
        except Exception:
            logger.debug("No se pudieron registrar métricas de integración", exc_info=True)

    # ==================================================================
    # RUTAS COMPATIBLES / PÚBLICAS
    # ==================================================================

    def build_route(self, *args: Any, **kwargs: Any) -> Any:
        if not self.state_graph:
            return GraphPlanningResult(status="failed", warnings=["El grafo no está inicializado"])
        return self.state_graph.build_route(*args, **kwargs)

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            fallback = float(default)
            if not math.isfinite(fallback):
                fallback = 0.0
        except (TypeError, ValueError, OverflowError):
            fallback = 0.0
        try:
            result = float(value)
            return result if math.isfinite(result) else fallback
        except (TypeError, ValueError, OverflowError):
            return fallback
