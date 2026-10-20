"""Grafo de estados y búsqueda de rutas para la planificación de JARVIS.

El módulo mantiene separadas la planificación y la ejecución de acciones reales.
Las aristas describen transiciones declarativas; buscar una ruta no ejecuta los
callbacks de los nodos. Las modificaciones de estado producidas por las aristas
se simulan sobre copias para que la búsqueda no altere el estado del llamador.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import math
import pickle
import time
from collections import deque
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from itertools import count
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.hands.planner.node import Node, Goal, NodeType
from src.hands.planner.heuristic import Heuristic, HeuristicType
from src.hands.planner.preconditions_effects import (
    PreconditionsEffectsManager,
    Condition,
    Effect,
)
from src.hands.planner.preconditions_effects_types import ConditionType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SearchStrategy(Enum):
    """Estrategias de búsqueda soportadas por el grafo."""

    A_STAR = "a_star"
    DIJKSTRA = "dijkstra"
    BFS = "bfs"
    DFS = "dfs"
    GREEDY = "greedy"
    # Alias histórico conservado para compatibilidad.
    Dijkstra = DIJKSTRA


@dataclass
class GraphNode:
    """Estado auxiliar de búsqueda asociado a un nodo canónico."""

    node: Node
    g_cost: float = float("inf")
    h_cost: float = 0.0
    f_cost: float = float("inf")
    parent: Optional[str] = None
    visited: bool = False
    state: Optional[Dict[str, Any]] = None

    def __lt__(self, other: "GraphNode") -> bool:
        if not isinstance(other, GraphNode):
            return NotImplemented
        if self.f_cost != other.f_cost:
            return self.f_cost < other.f_cost
        return str(getattr(self.node, "id", "")) < str(
            getattr(other.node, "id", "")
        )


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convierte a float finito y usa *default* ante datos no válidos."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _copy_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Crea una copia defensiva y tolera objetos no copiables."""
    if not isinstance(state, dict):
        return {}
    try:
        import copy

        result = copy.deepcopy(state)
        return result if isinstance(result, dict) else dict(state)
    except Exception:
        return dict(state)


def _type_value(value: Any) -> Any:
    """Devuelve el valor estable de un Enum sin modificar otros objetos."""
    return value.value if isinstance(value, Enum) else value


@dataclass
class GraphEdge:
    """Transición entre dos nodos, con condiciones y efectos declarativos."""

    source_id: str
    target_id: str
    cost: float
    transition_type: str = "normal"
    conditions: List[Any] = field(default_factory=list)
    preconditions: List[Condition] = field(default_factory=list)
    effects: List[Effect] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id)
        self.target_id = str(self.target_id)
        self.cost = _safe_float(self.cost, float("inf"))
        self.transition_type = str(self.transition_type or "normal")
        self.conditions = list(self.conditions or [])
        self.preconditions = list(self.preconditions or [])
        self.effects = list(self.effects or [])

    @staticmethod
    def _values_equal(actual: Any, expected: Any) -> bool:
        """Compara valores de estado sin confundir True con 1."""
        if isinstance(actual, bool) or isinstance(expected, bool):
            if isinstance(actual, bool) and isinstance(expected, bool):
                return actual is expected
            return str(actual).strip().lower() == str(expected).strip().lower()
        if actual == expected:
            return True
        if isinstance(actual, (int, float)) and isinstance(expected, str):
            try:
                return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-9)
            except (TypeError, ValueError, OverflowError):
                return False
        if isinstance(expected, (int, float)) and isinstance(actual, str):
            try:
                return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-9)
            except (TypeError, ValueError, OverflowError):
                return False
        return str(actual).strip().casefold() == str(expected).strip().casefold()

    @staticmethod
    def _evaluate_raw_condition(condition: Any, state: Dict[str, Any]) -> bool:
        """Evalúa una condición compatible sin depender de una API única."""
        if isinstance(condition, str):
            raw = condition.strip()
            if not raw:
                return False
            if ":" in raw:
                key, expected = raw.split(":", 1)
                return GraphEdge._values_equal(state.get(key.strip()), expected.strip())
            if raw.endswith("_not_met"):
                key = raw[: -len("_not_met")]
                return not bool(state.get(key, False))
            return bool(state.get(raw, False))

        if isinstance(condition, dict):
            kind = str(condition.get("type", "state_true")).strip().lower()
            key = condition.get("key", condition.get("state"))
            expected = condition.get("value", condition.get("expected_value"))
            if not isinstance(key, str) or not key:
                return False
            if kind in {"state_equals", "equals", "state_equal"}:
                return GraphEdge._values_equal(state.get(key), expected)
            if kind in {"state_exists", "exists"}:
                return key in state and state.get(key) is not None
            if kind in {"state_not_exists", "not_exists"}:
                return key not in state or state.get(key) is None
            if kind in {"state_true", "true"}:
                return bool(state.get(key, False))
            if kind in {"state_false", "false"}:
                return not bool(state.get(key, False))
            if kind in {"state_greater_than", "greater_than", "gt"}:
                return _safe_float(state.get(key), float("-inf")) > _safe_float(expected, float("inf"))
            if kind in {"state_less_than", "less_than", "lt"}:
                return _safe_float(state.get(key), float("inf")) < _safe_float(expected, float("-inf"))
            if kind in {"composite_and", "and"}:
                params = condition.get("parameters", {}) or {}
                return all(
                    GraphEdge._evaluate_raw_condition(item, state)
                    for item in params.get("conditions", condition.get("conditions", []))
                )
            if kind in {"composite_or", "or"}:
                params = condition.get("parameters", {}) or {}
                return any(
                    GraphEdge._evaluate_raw_condition(item, state)
                    for item in params.get("conditions", condition.get("conditions", []))
                )
            return False

        evaluate = getattr(condition, "evaluate", None)
        if callable(evaluate):
            try:
                return bool(evaluate(state))
            except Exception:
                return False
        if callable(condition):
            try:
                return bool(condition(state))
            except Exception:
                return False
        return False

    def can_traverse(self, current_state: Dict[str, Any]) -> bool:
        """Indica si se pueden satisfacer todas las condiciones de la arista."""
        state = _copy_state(current_state)
        if not math.isfinite(self.cost) or self.cost < 0:
            return False
        for condition in self.conditions:
            if not self._evaluate_raw_condition(condition, state):
                return False
        for precondition in self.preconditions:
            if not self._evaluate_raw_condition(precondition, state):
                return False
        return True

    def apply_effects(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica efectos a una copia del estado, registrando los fallos reales."""
        state = _copy_state(current_state)
        for effect in self.effects:
            try:
                apply_method = getattr(effect, "apply", None)
                if callable(apply_method):
                    try:
                        updated = apply_method(state)
                    except TypeError:
                        # Algunas APIs antiguas aceptan un segundo contexto opcional.
                        updated = apply_method(state, {})
                    if isinstance(updated, dict):
                        state = updated
                    continue

                if isinstance(effect, dict):
                    key = effect.get("key", effect.get("state"))
                    value = effect.get("value")
                    effect_type = str(_type_value(effect.get("type", "state_set"))).lower()
                    if not key and effect_type != "composite":
                        logger.warning(
                            "[GRAPH] Efecto sin clave en %s -> %s",
                            self.source_id,
                            self.target_id,
                        )
                        continue
                    if effect_type in {"state_set", "set"}:
                        state[str(key)] = value
                    elif effect_type in {"state_increment", "increment"}:
                        state[str(key)] = _safe_float(state.get(str(key)), 0.0) + _safe_float(value, 1.0)
                    elif effect_type in {"state_decrement", "decrement"}:
                        state[str(key)] = _safe_float(state.get(str(key)), 0.0) - _safe_float(value, 1.0)
                    elif effect_type in {"state_remove", "remove"}:
                        items = list(state.get(str(key), [])) if isinstance(state.get(str(key), []), list) else []
                        if value in items:
                            items.remove(value)
                        state[str(key)] = items
                    elif effect_type in {"state_append", "append"}:
                        items = list(state.get(str(key), [])) if isinstance(state.get(str(key), []), list) else []
                        items.append(value)
                        state[str(key)] = items
                    elif effect_type == "composite":
                        params = effect.get("parameters", {}) or {}
                        for nested in params.get("effects", []):
                            state = GraphEdge(
                                self.source_id,
                                self.target_id,
                                self.cost,
                                effects=[nested],
                            ).apply_effects(state)
                    else:
                        logger.debug("[GRAPH] Tipo de efecto no soportado: %s", effect_type)
                    continue

                logger.debug(
                    "[GRAPH] Efecto no aplicable (%s -> %s): %r",
                    self.source_id,
                    self.target_id,
                    effect,
                )
            except Exception as exc:
                logger.warning(
                    "[GRAPH] No se pudo aplicar efecto en %s -> %s: %s",
                    self.source_id,
                    self.target_id,
                    exc,
                )
        return state

    def get_total_cost(self, current_state: Optional[Dict[str, Any]] = None) -> float:
        """Calcula coste de transición y sobrecoste declarativo determinista."""
        del current_state
        if not math.isfinite(self.cost) or self.cost < 0:
            return float("inf")
        return self.cost + len(self.effects) * 0.1 + len(self.preconditions) * 0.05


@dataclass
class RouteResult:
    """Resultado estructurado de una búsqueda de ruta."""

    success: bool
    start_node_id: Optional[str]
    goal_node_id: Optional[str]
    path: List[str] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    total_cost: float = float("inf")
    alternative_paths: List[List[str]] = field(default_factory=list)
    strategy: str = SearchStrategy.A_STAR.value
    iterations: int = 0
    elapsed_time: float = 0.0
    initial_state: Dict[str, Any] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self) -> None:
        self.path = list(self.path or [])
        self.edges = list(self.edges or [])
        self.alternative_paths = [list(path) for path in (self.alternative_paths or [])]
        self.initial_state = _copy_state(self.initial_state)
        self.final_state = _copy_state(self.final_state)
        self.iterations = max(0, int(_safe_float(self.iterations, 0)))
        self.elapsed_time = max(0.0, _safe_float(self.elapsed_time, 0.0))
        self.total_cost = _safe_float(self.total_cost, float("inf"))

    @property
    def length(self) -> int:
        return len(self.path)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "start_node_id": self.start_node_id,
            "goal_node_id": self.goal_node_id,
            "path": list(self.path),
            "edges": [
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "cost": edge.cost,
                    "transition_type": edge.transition_type,
                }
                for edge in self.edges
            ],
            "total_cost": self.total_cost,
            "alternative_paths": [list(path) for path in self.alternative_paths],
            "strategy": self.strategy,
            "iterations": self.iterations,
            "elapsed_time": self.elapsed_time,
            "initial_state": _json_safe(self.initial_state),
            "final_state": _json_safe(self.final_state),
            "error": self.error,
        }


def _json_safe(value: Any, _active: Optional[Set[int]] = None) -> Any:
    """Convierte valores habituales a JSON sin romper ante ciclos u objetos raros."""
    active = _active if _active is not None else set()
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value, active)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)

    identity = id(value)
    if identity in active:
        return "<circular-reference>"

    if isinstance(value, dict):
        active.add(identity)
        try:
            return {str(key): _json_safe(item, active) for key, item in value.items()}
        finally:
            active.discard(identity)
    if isinstance(value, (list, tuple, set, frozenset)):
        active.add(identity)
        try:
            return [_json_safe(item, active) for item in value]
        finally:
            active.discard(identity)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _json_safe(to_dict(), active)
        except Exception:
            pass
    if is_dataclass(value) and not isinstance(value, type):
        active.add(identity)
        try:
            return {
                item.name: _json_safe(getattr(value, item.name), active)
                for item in fields(value)
            }
        except Exception:
            pass
        finally:
            active.discard(identity)
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError, OverflowError):
        return repr(value)


class StateGraph:
    """Grafo de estados con búsqueda de rutas condicionada por el estado."""

    def __init__(self, heuristic: Optional[Heuristic] = None) -> None:
        self.nodes: Dict[str, Node] = {}
        self.graph_nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.heuristic = heuristic or Heuristic(HeuristicType.GOAL_DISTANCE)
        self.graph_cache: Dict[str, Any] = {}
        self.preconditions_effects_manager = PreconditionsEffectsManager()
        self.last_search_iterations = 0
        self.last_search_elapsed = 0.0
        self._graph_revision = 0
        logger.info("[GRAPH] Grafo de estados inicializado")

    @property
    def graph_revision(self) -> int:
        """Versión monotónica del grafo, usada para invalidar cachés."""
        return self._graph_revision

    def _invalidate_search_cache(self) -> None:
        self._graph_revision += 1
        self.graph_cache.clear()
        search_cache = getattr(self, "search_cache", None)
        if isinstance(search_cache, dict):
            search_cache.clear()
        clear_heuristic_cache = getattr(self.heuristic, "clear_cache", None)
        if callable(clear_heuristic_cache):
            try:
                clear_heuristic_cache()
            except Exception:
                logger.debug("No se pudo limpiar la caché de heurística", exc_info=True)

    def add_node(self, node: Node) -> None:
        if node is None:
            raise ValueError("node no puede ser None")
        node_id = getattr(node, "id", None)
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("El nodo debe tener un id válido")
        node_id = node_id.strip()
        if node_id in self.nodes and self.nodes[node_id] is node:
            return
        self.nodes[node_id] = node
        self.graph_nodes[node_id] = GraphNode(node=node)
        # Si se sustituye un nodo conservando su ID, reconstruir las relaciones
        # auxiliares desde las aristas canónicas para no dejarlo desconectado.
        for edge in self.edges:
            try:
                if edge.source_id == node_id:
                    node.add_edge(edge.target_id, edge.cost)
                if edge.target_id == node_id:
                    node.add_in_edge(edge.source_id)
            except Exception:
                logger.debug("No se pudo reconstruir la relación del nodo %s", node_id, exc_info=True)
        self._invalidate_search_cache()

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        cost: float = 1.0,
        conditions: Optional[List[Any]] = None,
        transition_type: str = "normal",
        preconditions: Optional[List[Condition]] = None,
        effects: Optional[List[Effect]] = None,
    ) -> bool:
        if source_id not in self.nodes or target_id not in self.nodes:
            return False
        numeric_cost = _safe_float(cost, float("inf"))
        if not math.isfinite(numeric_cost) or numeric_cost < 0:
            return False
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            cost=numeric_cost,
            transition_type=transition_type or "normal",
            conditions=list(conditions or []),
            preconditions=list(preconditions or []),
            effects=list(effects or []),
        )
        # Conserva las aristas paralelas si difieren en tipo/condiciones, pero evita
        # duplicar accidentalmente la misma transición declarativa.
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(self.edges)
                if existing.source_id == source_id
                and existing.target_id == target_id
                and existing.transition_type == edge.transition_type
                and self._conditions_equivalent(existing.conditions, edge.conditions)
                and self._conditions_equivalent(existing.preconditions, edge.preconditions)
                and self._conditions_equivalent(existing.effects, edge.effects)
            ),
            None,
        )
        if duplicate_index is not None:
            existing = self.edges[duplicate_index]
            if (
                existing.cost == edge.cost
                and existing.conditions == edge.conditions
                and existing.preconditions == edge.preconditions
                and existing.effects == edge.effects
            ):
                return True
            self.edges[duplicate_index] = edge
        else:
            self.edges.append(edge)
        try:
            self.nodes[source_id].add_edge(target_id, numeric_cost)
        except Exception:
            # La arista canónica sigue siendo la fuente de verdad del grafo.
            logger.debug("No se pudo sincronizar out_edges de %s", source_id, exc_info=True)
        try:
            self.nodes[target_id].add_in_edge(source_id)
        except Exception:
            logger.debug("No se pudo sincronizar in_edges de %s", target_id, exc_info=True)
        self._invalidate_search_cache()
        return True

    @staticmethod
    def _conditions_equivalent(left: List[Any], right: List[Any]) -> bool:
        try:
            return _json_safe(left) == _json_safe(right)
        except Exception:
            return left is right

    def get_edges_from(self, node_id: str) -> List[GraphEdge]:
        return [edge for edge in self.edges if edge.source_id == node_id]

    def get_edge(self, source_id: str, target_id: str) -> Optional[GraphEdge]:
        for edge in self.edges:
            if edge.source_id == source_id and edge.target_id == target_id:
                return edge
        return None

    def find_route(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Optional[Dict[str, Any]] = None,
        strategy: SearchStrategy | str = SearchStrategy.A_STAR,
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> RouteResult:
        started = time.perf_counter()
        state = _copy_state(current_state)
        try:
            selected = self._normalize_strategy(strategy)
        except ValueError as exc:
            return self._route_error(start_node_id, goal_node_id, str(strategy), state, str(exc), started)
        if start_node_id not in self.nodes:
            return self._route_error(start_node_id, goal_node_id, selected.value, state, f"Nodo inicial no encontrado: {start_node_id}", started)
        if goal_node_id not in self.nodes:
            return self._route_error(start_node_id, goal_node_id, selected.value, state, f"Nodo objetivo no encontrado: {goal_node_id}", started)
        limit = self._normalize_max_iterations(max_iterations)
        alternatives_limit = self._normalize_alternative_count(alternative_count)
        dispatch = {
            SearchStrategy.A_STAR: self.find_path_astar,
            SearchStrategy.DIJKSTRA: self.find_path_dijkstra,
            SearchStrategy.BFS: self.find_path_bfs,
            SearchStrategy.DFS: self.find_path_dfs,
            SearchStrategy.GREEDY: self.find_path_greedy,
        }
        try:
            path, cost, alternatives = dispatch[selected](
                start_node_id, goal_node_id, state, limit, find_alternatives, alternatives_limit
            )
        except Exception as exc:
            logger.exception("[GRAPH] Error durante búsqueda %s -> %s", start_node_id, goal_node_id)
            return self._route_error(start_node_id, goal_node_id, selected.value, state, str(exc), started)
        success = bool(path)
        final_state = self.apply_path_effects(path, state) if success else _copy_state(state)
        return RouteResult(
            success=success,
            start_node_id=start_node_id,
            goal_node_id=goal_node_id,
            path=path,
            edges=self.get_edges_for_path(path, state),
            total_cost=cost,
            alternative_paths=alternatives,
            strategy=selected.value,
            iterations=self.last_search_iterations,
            elapsed_time=time.perf_counter() - started,
            initial_state=state,
            final_state=final_state,
            error=None if success else "No se encontró una ruta dentro de los límites indicados",
        )

    @staticmethod
    def _route_error(
        start_node_id: Optional[str],
        goal_node_id: Optional[str],
        strategy: str,
        state: Dict[str, Any],
        message: str,
        started: float,
    ) -> RouteResult:
        return RouteResult(
            success=False,
            start_node_id=start_node_id,
            goal_node_id=goal_node_id,
            strategy=strategy,
            initial_state=state,
            final_state=state,
            error=message,
            elapsed_time=time.perf_counter() - started,
        )

    @staticmethod
    def _normalize_max_iterations(value: Any) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError, OverflowError):
            return 1000

    @staticmethod
    def _normalize_alternative_count(value: Any) -> int:
        try:
            return min(20, max(0, int(value)))
        except (TypeError, ValueError, OverflowError):
            return 3

    def build_route(self, *args: Any, **kwargs: Any) -> RouteResult:
        """Alias compatible con las integraciones que usan `build_route`."""
        return self.find_route(*args, **kwargs)

    def find_path_astar(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        started = time.perf_counter()
        limit = self._normalize_max_iterations(max_iterations)
        path, cost = self._find_path_astar_internal(
            start_node_id, goal_node_id, _copy_state(current_state), limit, None
        )
        primary_iterations = self.last_search_iterations
        alternatives: List[List[str]] = []
        if find_alternatives and path and alternative_count > 0:
            target_count = self._normalize_alternative_count(alternative_count)
            for index in range(max(0, len(path) - 1)):
                blocked = {(path[index], path[index + 1])}
                alternative, _ = self._find_path_astar_internal(
                    start_node_id,
                    goal_node_id,
                    _copy_state(current_state),
                    limit,
                    blocked,
                )
                if alternative and alternative != path and alternative not in alternatives:
                    alternatives.append(alternative)
                if len(alternatives) >= target_count:
                    break
        self.last_search_iterations = primary_iterations
        self.last_search_elapsed = time.perf_counter() - started
        return path, cost, alternatives

    def _find_path_astar_internal(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int,
        blocked_edges: Optional[Set[Tuple[str, str]]],
    ) -> Tuple[List[str], float]:
        self.last_search_iterations = 0
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            return [], float("inf")
        initial = _copy_state(current_state)
        goal = self._create_goal_from_node(goal_node_id)
        start_key = (start_node_id, self._state_signature(initial))
        sequence = count()
        heap: List[Tuple[float, float, int, str, Dict[str, Any]]] = []
        heapq.heappush(heap, (self._estimate_heuristic(start_node_id, initial, goal), 0.0, next(sequence), start_node_id, initial))
        best_g: Dict[Tuple[str, str], float] = {start_key: 0.0}
        parent: Dict[Tuple[str, str], Optional[Tuple[Tuple[str, str], str]]] = {start_key: None}
        closed: Set[Tuple[str, str]] = set()
        iterations = 0
        while heap and iterations < max_iterations:
            _, g_cost, _, current_id, state = heapq.heappop(heap)
            iterations += 1
            current_key = (current_id, self._state_signature(state))
            if g_cost > best_g.get(current_key, float("inf")) + 1e-12 or current_key in closed:
                continue
            closed.add(current_key)
            if current_id == goal_node_id:
                self.last_search_iterations = iterations
                return self._reconstruct_state_path(current_key, parent), g_cost
            for edge in self.get_edges_from(current_id):
                if blocked_edges and (edge.source_id, edge.target_id) in blocked_edges:
                    continue
                if not edge.can_traverse(state):
                    continue
                edge_cost = edge.get_total_cost(state)
                if not math.isfinite(edge_cost):
                    continue
                next_state = edge.apply_effects(state)
                next_key = (edge.target_id, self._state_signature(next_state))
                new_g = g_cost + edge_cost
                if new_g + 1e-12 >= best_g.get(next_key, float("inf")):
                    continue
                best_g[next_key] = new_g
                parent[next_key] = (current_key, current_id)
                heuristic_cost = self._estimate_heuristic(edge.target_id, next_state, goal)
                heapq.heappush(heap, (new_g + heuristic_cost, new_g, next(sequence), edge.target_id, next_state))
        self.last_search_iterations = iterations
        return [], float("inf")

    @staticmethod
    def _reconstruct_state_path(
        current_key: Tuple[str, str],
        parent: Dict[Tuple[str, str], Optional[Tuple[Tuple[str, str], str]]],
    ) -> List[str]:
        path: List[str] = []
        cursor: Optional[Tuple[str, str]] = current_key
        while cursor is not None:
            path.append(cursor[0])
            parent_data = parent.get(cursor)
            cursor = parent_data[0] if parent_data is not None else None
        path.reverse()
        return path

    def find_path_dijkstra(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        del find_alternatives, alternative_count
        started = time.perf_counter()
        self.last_search_iterations = 0
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        initial = _copy_state(current_state)
        start_key = (start_node_id, self._state_signature(initial))
        distances: Dict[Tuple[str, str], float] = {start_key: 0.0}
        parents: Dict[Tuple[str, str], Optional[Tuple[Tuple[str, str], str]]] = {start_key: None}
        sequence = count()
        queue: List[Tuple[float, int, str, Dict[str, Any]]] = [(0.0, next(sequence), start_node_id, initial)]
        visited: Set[Tuple[str, str]] = set()
        iterations = 0
        limit = self._normalize_max_iterations(max_iterations)
        while queue and iterations < limit:
            distance, _, current_id, state = heapq.heappop(queue)
            iterations += 1
            key = (current_id, self._state_signature(state))
            if key in visited or distance > distances.get(key, float("inf")) + 1e-12:
                continue
            visited.add(key)
            if current_id == goal_node_id:
                self.last_search_iterations = iterations
                self.last_search_elapsed = time.perf_counter() - started
                return self._reconstruct_state_path(key, parents), distance, []
            for edge in self.get_edges_from(current_id):
                if not edge.can_traverse(state):
                    continue
                edge_cost = edge.get_total_cost(state)
                if not math.isfinite(edge_cost):
                    continue
                next_state = edge.apply_effects(state)
                next_key = (edge.target_id, self._state_signature(next_state))
                next_distance = distance + edge_cost
                if next_distance + 1e-12 >= distances.get(next_key, float("inf")):
                    continue
                distances[next_key] = next_distance
                parents[next_key] = (key, current_id)
                heapq.heappush(queue, (next_distance, next(sequence), edge.target_id, next_state))
        self.last_search_iterations = iterations
        self.last_search_elapsed = time.perf_counter() - started
        return [], float("inf"), []

    def find_path_bfs(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        del find_alternatives, alternative_count
        started = time.perf_counter()
        self.last_search_iterations = 0
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        initial = _copy_state(current_state)
        queue = deque([(start_node_id, initial, [start_node_id], 0.0)])
        visited = {(start_node_id, self._state_signature(initial))}
        iterations = 0
        limit = self._normalize_max_iterations(max_iterations)
        while queue and iterations < limit:
            current_id, state, path, cost = queue.popleft()
            iterations += 1
            if current_id == goal_node_id:
                self.last_search_iterations = iterations
                self.last_search_elapsed = time.perf_counter() - started
                return path, cost, []
            for edge in self.get_edges_from(current_id):
                if not edge.can_traverse(state):
                    continue
                edge_cost = edge.get_total_cost(state)
                if not math.isfinite(edge_cost):
                    continue
                next_state = edge.apply_effects(state)
                key = (edge.target_id, self._state_signature(next_state))
                if key in visited:
                    continue
                visited.add(key)
                queue.append((edge.target_id, next_state, path + [edge.target_id], cost + edge_cost))
        self.last_search_iterations = iterations
        self.last_search_elapsed = time.perf_counter() - started
        return [], float("inf"), []

    def find_path_dfs(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        del find_alternatives, alternative_count
        started = time.perf_counter()
        self.last_search_iterations = 0
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        initial = _copy_state(current_state)
        stack = [(start_node_id, initial, [start_node_id], 0.0)]
        visited = {(start_node_id, self._state_signature(initial))}
        iterations = 0
        limit = self._normalize_max_iterations(max_iterations)
        while stack and iterations < limit:
            current_id, state, path, cost = stack.pop()
            iterations += 1
            if current_id == goal_node_id:
                self.last_search_iterations = iterations
                self.last_search_elapsed = time.perf_counter() - started
                return path, cost, []
            for edge in reversed(self.get_edges_from(current_id)):
                if not edge.can_traverse(state):
                    continue
                edge_cost = edge.get_total_cost(state)
                if not math.isfinite(edge_cost):
                    continue
                next_state = edge.apply_effects(state)
                key = (edge.target_id, self._state_signature(next_state))
                if key in visited:
                    continue
                visited.add(key)
                stack.append((edge.target_id, next_state, path + [edge.target_id], cost + edge_cost))
        self.last_search_iterations = iterations
        self.last_search_elapsed = time.perf_counter() - started
        return [], float("inf"), []

    def find_path_greedy(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        del find_alternatives, alternative_count
        started = time.perf_counter()
        self.last_search_iterations = 0
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        goal = self._create_goal_from_node(goal_node_id)
        initial = _copy_state(current_state)
        sequence = count()
        heap: List[Tuple[float, float, int, str, Dict[str, Any], List[str]]] = []
        heapq.heappush(heap, (self._estimate_heuristic(start_node_id, initial, goal), 0.0, next(sequence), start_node_id, initial, [start_node_id]))
        best_cost = {(start_node_id, self._state_signature(initial)): 0.0}
        iterations = 0
        limit = self._normalize_max_iterations(max_iterations)
        while heap and iterations < limit:
            _, actual_cost, _, current_id, state, path = heapq.heappop(heap)
            iterations += 1
            key = (current_id, self._state_signature(state))
            if actual_cost > best_cost.get(key, float("inf")) + 1e-12:
                continue
            if current_id == goal_node_id:
                self.last_search_iterations = iterations
                self.last_search_elapsed = time.perf_counter() - started
                return path, actual_cost, []
            for edge in self.get_edges_from(current_id):
                if not edge.can_traverse(state):
                    continue
                edge_cost = edge.get_total_cost(state)
                if not math.isfinite(edge_cost):
                    continue
                next_state = edge.apply_effects(state)
                next_key = (edge.target_id, self._state_signature(next_state))
                next_cost = actual_cost + edge_cost
                if next_cost + 1e-12 >= best_cost.get(next_key, float("inf")):
                    continue
                best_cost[next_key] = next_cost
                heuristic_cost = self._estimate_heuristic(edge.target_id, next_state, goal)
                heapq.heappush(heap, (heuristic_cost, next_cost, next(sequence), edge.target_id, next_state, path + [edge.target_id]))
        self.last_search_iterations = iterations
        self.last_search_elapsed = time.perf_counter() - started
        return [], float("inf"), []

    def get_edges_for_path(
        self,
        path: List[str],
        current_state: Optional[Dict[str, Any]] = None,
    ) -> List[GraphEdge]:
        """Obtiene una arista por salto; con paralelas elige la primera válida."""
        if len(path) < 2:
            return []
        result: List[GraphEdge] = []
        state: Dict[str, Any] = _copy_state(current_state)
        for source_id, target_id in zip(path, path[1:]):
            candidates = [
                edge for edge in self.edges
                if edge.source_id == source_id and edge.target_id == target_id
            ]
            if not candidates:
                continue
            edge = next((candidate for candidate in candidates if candidate.can_traverse(state)), candidates[0])
            result.append(edge)
            state = edge.apply_effects(state)
        return result

    def apply_path_effects(self, path: List[str], current_state: Dict[str, Any]) -> Dict[str, Any]:
        state = _copy_state(current_state)
        for source_id, target_id in zip(path, path[1:]):
            candidates = [
                edge for edge in self.edges
                if edge.source_id == source_id and edge.target_id == target_id
            ]
            edge = next((candidate for candidate in candidates if candidate.can_traverse(state)), None)
            if edge is None:
                logger.warning("[GRAPH] No se puede reproducir el salto %s -> %s; se detiene la simulación", source_id, target_id)
                break
            state = edge.apply_effects(state)
        return state

    def get_node_path_cost(self, path: List[str]) -> float:
        if len(path) < 2:
            return 0.0
        return sum(edge.get_total_cost({}) for edge in self.get_edges_for_path(path))

    def get_neighbors(self, node_id: str, current_state: Dict[str, Any]) -> List[Tuple[str, float]]:
        return [
            (edge.target_id, edge.get_total_cost(current_state))
            for edge in self.get_edges_from(node_id)
            if edge.can_traverse(current_state) and math.isfinite(edge.get_total_cost(current_state))
        ]

    def add_edge_with_preconditions(
        self,
        source_id: str,
        target_id: str,
        cost: float = 1.0,
        transition_type: str = "normal",
        **kwargs: Any,
    ) -> bool:
        return self.add_edge(
            source_id,
            target_id,
            cost,
            list(kwargs.get("conditions", []) or []),
            transition_type,
            list(kwargs.get("preconditions", []) or []),
            list(kwargs.get("effects", []) or []),
        )

    def create_conditional_edge(
        self,
        source_id: str,
        target_id: str,
        cost: float = 1.0,
        condition_type: Optional[ConditionType] = None,
        **condition_params: Any,
    ) -> bool:
        if condition_type is None:
            return False
        try:
            condition = Condition(type=condition_type, **condition_params)
        except Exception:
            logger.exception("[GRAPH] Error creando condición para %s -> %s", source_id, target_id)
            return False
        return self.add_edge(source_id, target_id, cost, [], "conditional", [condition], [])

    def create_effect_edge(
        self,
        source_id: str,
        target_id: str,
        cost: float = 1.0,
        effect_type: Optional[str] = None,
        **effect_params: Any,
    ) -> bool:
        if not effect_type:
            return False
        try:
            effect = Effect(type=effect_type, **effect_params)
        except Exception:
            logger.exception("[GRAPH] Error creando efecto para %s -> %s", source_id, target_id)
            return False
        return self.add_edge(source_id, target_id, cost, [], "normal", [], [effect])

    def validate_graph(self) -> List[str]:
        errors: List[str] = []
        for edge in self.edges:
            if edge.source_id not in self.nodes:
                errors.append(f"Origen de arista no existe: {edge.source_id}")
            if edge.target_id not in self.nodes:
                errors.append(f"Destino de arista no existe: {edge.target_id}")
            if not math.isfinite(edge.cost) or edge.cost < 0:
                errors.append(f"Coste inválido: {edge.source_id} -> {edge.target_id} ({edge.cost})")
        expected_out: Dict[str, Set[str]] = {node_id: set() for node_id in self.nodes}
        expected_in: Dict[str, Set[str]] = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            if edge.source_id in expected_out and edge.target_id in expected_in:
                expected_out[edge.source_id].add(edge.target_id)
                expected_in[edge.target_id].add(edge.source_id)
        for node_id, node in self.nodes.items():
            for out_id in getattr(node, "out_edges", []) or []:
                if out_id not in self.nodes:
                    errors.append(f"Nodo out_edge no existe: {node_id} -> {out_id}")
            for in_id in getattr(node, "in_edges", []) or []:
                if in_id not in self.nodes:
                    errors.append(f"Nodo in_edge no existe: {in_id} -> {node_id}")
            actual_out = set(getattr(node, "out_edges", []) or [])
            actual_in = set(getattr(node, "in_edges", []) or [])
            if actual_out != expected_out.get(node_id, set()):
                errors.append(f"out_edges no sincronizado para nodo: {node_id}")
            if actual_in != expected_in.get(node_id, set()):
                errors.append(f"in_edges no sincronizado para nodo: {node_id}")
        return errors

    def validate_graph_advanced(self) -> Tuple[List[str], Dict[str, Any]]:
        errors = self.validate_graph()
        connected = {item for edge in self.edges for item in (edge.source_id, edge.target_id)}
        disconnected = set(self.nodes) - connected
        issues: List[str] = []
        nodes_with_issues: Set[str] = set()
        edges_with_issues: Set[Tuple[str, str]] = set()
        for node_id, node in self.nodes.items():
            out_count = len(getattr(node, "out_edges", []) or [])
            in_count = len(getattr(node, "in_edges", []) or [])
            if out_count > 10:
                issues.append(f"Nodo {node_id} tiene {out_count} vecinos")
                nodes_with_issues.add(node_id)
            if in_count > 10:
                issues.append(f"Nodo {node_id} tiene {in_count} predecesores")
                nodes_with_issues.add(node_id)
        for edge in self.edges:
            if len(edge.preconditions) > 5:
                issues.append(f"Arista {edge.source_id} -> {edge.target_id} tiene {len(edge.preconditions)} precondiciones")
                edges_with_issues.add((edge.source_id, edge.target_id))
            if len(edge.effects) > 5:
                issues.append(f"Arista {edge.source_id} -> {edge.target_id} tiene {len(edge.effects)} efectos")
                edges_with_issues.add((edge.source_id, edge.target_id))
        if disconnected:
            errors.append(f"Nodos desconectados: {sorted(disconnected)}")
        circular = sum(1 for node_id in self.nodes if self._has_circular_path(node_id))
        return errors, {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_with_issues": len(nodes_with_issues),
            "edges_with_issues": len(edges_with_issues),
            "circular_paths": circular,
            "disconnected_nodes": len(disconnected),
            "performance_issues": issues,
        }

    def _has_circular_path(self, start_node_id: str, max_depth: int = 100) -> bool:
        if start_node_id not in self.nodes:
            return False
        limit = max(0, int(max_depth))
        active: Set[str] = set()
        visited: Set[str] = set()

        def visit(node_id: str, depth: int) -> bool:
            if depth > limit:
                return False
            visited.add(node_id)
            active.add(node_id)
            for edge in self.get_edges_from(node_id):
                if edge.target_id in active:
                    return True
                if edge.target_id not in visited and visit(edge.target_id, depth + 1):
                    return True
            active.remove(node_id)
            return False

        return visit(start_node_id, 0)

    def get_graph_stats(self) -> Dict[str, Any]:
        heuristic_type = getattr(self.heuristic, "heuristic_type", None)
        heuristic_type = _type_value(heuristic_type) if heuristic_type is not None else None
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "heuristic_type": heuristic_type,
            "heuristic_weight": getattr(self.heuristic, "weight", None),
            "cache_size": len(self.graph_cache),
            "average_branching": len(self.edges) / len(self.nodes) if self.nodes else 0.0,
            "graph_revision": self._graph_revision,
        }

    def clear_search_cache(self) -> None:
        for graph_node in self.graph_nodes.values():
            graph_node.g_cost = float("inf")
            graph_node.h_cost = 0.0
            graph_node.f_cost = float("inf")
            graph_node.parent = None
            graph_node.visited = False
            graph_node.state = None
        self.graph_cache.clear()
        search_cache = getattr(self, "search_cache", None)
        if isinstance(search_cache, dict):
            search_cache.clear()
        clear_heuristic_cache = getattr(self.heuristic, "clear_cache", None)
        if callable(clear_heuristic_cache):
            try:
                clear_heuristic_cache()
            except Exception:
                logger.debug("No se pudo limpiar la caché de heurística", exc_info=True)

    def export_to_json(self) -> Dict[str, Any]:
        return {
            "nodes": [self._serialize_node(node) for node in self.nodes.values()],
            "edges": [self._serialize_edge(edge) for edge in self.edges],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "heuristic_type": _type_value(getattr(self.heuristic, "heuristic_type", None)),
                "heuristic_weight": getattr(self.heuristic, "weight", None),
                "graph_revision": self._graph_revision,
            },
        }

    def import_from_json(self, data: Dict[str, Any]) -> None:
        """Importa de manera transaccional: un documento inválido no borra el grafo actual."""
        if not isinstance(data, dict):
            raise ValueError("El contenido del grafo debe ser un dict")
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        if isinstance(raw_nodes, dict):
            raw_nodes = list(raw_nodes.values())
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("'nodes' y 'edges' deben ser listas o 'nodes' un diccionario")

        staged = StateGraph(heuristic=self.heuristic)
        for node_data in raw_nodes:
            if not isinstance(node_data, dict):
                raise ValueError("El documento contiene un nodo que no es un objeto")
            staged.add_node(self._deserialize_node(node_data))
        for edge_data in raw_edges:
            if not isinstance(edge_data, dict):
                raise ValueError("El documento contiene una arista que no es un objeto")
            source_id = edge_data.get("source_id")
            target_id = edge_data.get("target_id")
            if source_id not in staged.nodes or target_id not in staged.nodes:
                raise ValueError(f"Arista con origen/destino desconocido: {source_id} -> {target_id}")
            raw_preconditions = edge_data.get("preconditions", []) or []
            raw_effects = edge_data.get("effects", []) or []
            preconditions = [self._deserialize_condition(raw) for raw in raw_preconditions]
            effects = [self._deserialize_effect(raw) for raw in raw_effects]
            if any(item is None for item in preconditions):
                raise ValueError(f"Precondición no recuperable en arista: {source_id} -> {target_id}")
            if any(item is None for item in effects):
                raise ValueError(f"Efecto no recuperable en arista: {source_id} -> {target_id}")
            if not staged.add_edge(
                source_id,
                target_id,
                edge_data.get("cost", 1.0),
                edge_data.get("conditions", []),
                edge_data.get("transition_type", "normal"),
                preconditions,
                effects,
            ):
                raise ValueError(f"No se pudo importar arista: {source_id} -> {target_id}")

        metadata = data.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            raise ValueError("Los metadatos del grafo deben ser un objeto")
        heuristic_type = metadata.get("heuristic_type")
        if heuristic_type:
            try:
                staged.heuristic = Heuristic(
                    HeuristicType(heuristic_type),
                    _safe_float(metadata.get("heuristic_weight", 1.0), 1.0),
                )
            except Exception:
                logger.warning("Tipo de heurística inválido en el documento; se conserva la heurística actual")
                staged.heuristic = self.heuristic

        # Publicar el nuevo grafo solo después de validar todos sus componentes.
        self.nodes = staged.nodes
        self.graph_nodes = staged.graph_nodes
        self.edges = staged.edges
        self.heuristic = staged.heuristic
        self.preconditions_effects_manager = staged.preconditions_effects_manager
        self.graph_cache.clear()
        self._invalidate_search_cache()

    def export_graph(self, file_path: str, format: str = "json") -> bool:
        try:
            fmt = str(format).strip().lower()
            if fmt == "json":
                with open(file_path, "w", encoding="utf-8") as stream:
                    json.dump(self.export_to_json(), stream, indent=2, ensure_ascii=False, allow_nan=False)
            elif fmt == "pickle":
                with open(file_path, "wb") as stream:
                    pickle.dump(self, stream, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                return False
            return True
        except Exception:
            logger.exception("[GRAPH] Error exportando grafo a %s", file_path)
            return False

    def import_graph(self, file_path: str, format: str = "json") -> bool:
        try:
            fmt = str(format).strip().lower()
            if fmt == "json":
                with open(file_path, "r", encoding="utf-8") as stream:
                    data = json.load(stream)
                self.import_from_json(data)
            elif fmt == "pickle":
                # Solo importar pickle de fuentes locales de confianza: pickle puede
                # ejecutar código durante la deserialización.
                with open(file_path, "rb") as stream:
                    imported = pickle.load(stream)
                if not isinstance(imported, StateGraph):
                    raise TypeError("El pickle no contiene un StateGraph válido")
                self.nodes = imported.nodes
                self.graph_nodes = imported.graph_nodes
                self.edges = imported.edges
                self.heuristic = imported.heuristic
                self.graph_cache = dict(getattr(imported, "graph_cache", {}) or {})
                self.preconditions_effects_manager = imported.preconditions_effects_manager
                self._invalidate_search_cache()
            else:
                return False
            return True
        except Exception:
            logger.exception("[GRAPH] Error importando grafo desde %s", file_path)
            return False

    @staticmethod
    def _serialize_node(node: Node) -> Dict[str, Any]:
        to_dict = getattr(node, "to_dict", None)
        if callable(to_dict):
            try:
                serialized = to_dict()
                if isinstance(serialized, dict):
                    # Callbacks no forman parte del contrato serializable.
                    for key in ("execute_callback", "success_criteria"):
                        serialized.pop(key, None)
                    return _json_safe(serialized)
            except Exception:
                logger.debug("Node.to_dict no disponible; usando serialización compatible", exc_info=True)
        return {
            "id": getattr(node, "id", ""),
            "type": _type_value(getattr(node, "type", NodeType.ACTION)),
            "name": getattr(node, "name", ""),
            "description": getattr(node, "description", ""),
            "parameters": _json_safe(getattr(node, "parameters", {})),
            "preconditions": _json_safe(getattr(node, "preconditions", [])),
            "effects": _json_safe(getattr(node, "effects", [])),
            "dependencies": _json_safe(getattr(node, "dependencies", [])),
            "cost": _safe_float(getattr(node, "cost", 1.0), 1.0),
            "application": getattr(node, "application", None),
            "ui_element": getattr(node, "ui_element", None),
            "metadata": _json_safe(getattr(node, "metadata", {})),
            "parent": getattr(node, "parent", None),
            "children": _json_safe(getattr(node, "children", [])),
        }

    @staticmethod
    def _serialize_edge(edge: GraphEdge) -> Dict[str, Any]:
        return {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "cost": edge.cost,
            "transition_type": edge.transition_type,
            "conditions": _json_safe(edge.conditions),
            "preconditions": [StateGraph._serialize_condition(item) for item in edge.preconditions],
            "effects": [StateGraph._serialize_effect(item) for item in edge.effects],
        }

    @staticmethod
    def _serialize_condition(condition: Any) -> Dict[str, Any]:
        if isinstance(condition, dict):
            return _json_safe(condition)
        kind = getattr(condition, "type", "")
        return {
            "type": _type_value(kind),
            "key": getattr(condition, "key", None),
            "expected_value": _json_safe(getattr(condition, "expected_value", None)),
            "description": getattr(condition, "description", ""),
            "parameters": _json_safe(getattr(condition, "parameters", {}) or {}),
        }

    @staticmethod
    def _serialize_effect(effect: Any) -> Dict[str, Any]:
        if isinstance(effect, dict):
            return _json_safe(effect)
        return {
            "type": _json_safe(getattr(effect, "type", "")),
            "key": getattr(effect, "key", None),
            "value": _json_safe(getattr(effect, "value", None)),
            "description": getattr(effect, "description", ""),
            "parameters": _json_safe(getattr(effect, "parameters", {}) or {}),
        }

    @staticmethod
    def _deserialize_node(node_data: Dict[str, Any]) -> Node:
        if not isinstance(node_data.get("id"), str) or not node_data.get("id", "").strip():
            raise ValueError("Nodo serializado sin id válido")
        from_dict = getattr(Node, "from_dict", None)
        if callable(from_dict):
            try:
                return from_dict(dict(node_data))
            except Exception:
                logger.debug("Node.from_dict rechazó el nodo; usando conversión compatible", exc_info=True)
        try:
            node_type = NodeType(node_data.get("type", NodeType.ACTION.value))
        except Exception:
            node_type = NodeType.ACTION
        kwargs = {
            "id": node_data["id"],
            "type": node_type,
            "name": node_data.get("name", node_data["id"]),
            "description": node_data.get("description", ""),
            "parameters": dict(node_data.get("parameters", {}) or {}),
            "preconditions": list(node_data.get("preconditions", []) or []),
            "effects": list(node_data.get("effects", []) or []),
            "dependencies": list(node_data.get("dependencies", []) or []),
            "cost": _safe_float(node_data.get("cost", 1.0), 1.0),
            "application": node_data.get("application"),
            "ui_element": node_data.get("ui_element"),
            "metadata": dict(node_data.get("metadata", {}) or {}),
            "parent": node_data.get("parent"),
            "children": list(node_data.get("children", []) or []),
        }
        try:
            return Node(**kwargs)
        except TypeError:
            kwargs.pop("parent", None)
            kwargs.pop("children", None)
            return Node(**kwargs)

    @staticmethod
    def _deserialize_condition(data: Any) -> Optional[Condition]:
        if not isinstance(data, dict):
            return None
        try:
            raw_type = data.get("type")
            try:
                condition_type = ConditionType(raw_type)
            except Exception:
                condition_type = raw_type
            kwargs = {
                "type": condition_type,
                "key": data.get("key"),
                "expected_value": data.get("expected_value", data.get("value")),
                "description": data.get("description", ""),
            }
            if isinstance(data.get("parameters"), dict):
                kwargs["parameters"] = data["parameters"]
            try:
                return Condition(**kwargs)
            except TypeError:
                kwargs.pop("parameters", None)
                return Condition(**kwargs)
        except Exception:
            logger.exception("[GRAPH] Error al deserializar condición")
            return None

    @staticmethod
    def _deserialize_effect(data: Any) -> Optional[Effect]:
        if not isinstance(data, dict):
            return None
        try:
            kwargs = {
                "type": data.get("type", ""),
                "key": data.get("key"),
                "value": data.get("value"),
                "description": data.get("description", ""),
            }
            if isinstance(data.get("parameters"), dict):
                kwargs["parameters"] = data["parameters"]
            try:
                return Effect(**kwargs)
            except TypeError:
                kwargs.pop("parameters", None)
                return Effect(**kwargs)
        except Exception:
            logger.exception("[GRAPH] Error al deserializar efecto")
            return None

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Alias histórico para la conversión JSON segura."""
        return _json_safe(value)

    @staticmethod
    def _normalize_strategy(strategy: SearchStrategy | str) -> SearchStrategy:
        if isinstance(strategy, SearchStrategy):
            return strategy
        if isinstance(strategy, str):
            raw = strategy.strip().lower()
            aliases = {
                "astar": SearchStrategy.A_STAR,
                "a*": SearchStrategy.A_STAR,
                "a_star": SearchStrategy.A_STAR,
                "a-star": SearchStrategy.A_STAR,
                "dijkstra": SearchStrategy.DIJKSTRA,
                "bfs": SearchStrategy.BFS,
                "dfs": SearchStrategy.DFS,
                "greedy": SearchStrategy.GREEDY,
            }
            if raw in aliases:
                return aliases[raw]
        raise ValueError(f"Estrategia de búsqueda no soportada: {strategy}")

    def _create_goal_from_node(self, node_id: str) -> Goal:
        node = self.nodes.get(node_id)
        target: Any = node_id
        description = f"Alcanzar nodo {node_id}"
        if node is not None:
            metadata = getattr(node, "metadata", {}) or {}
            if isinstance(metadata, dict):
                target = metadata.get("target", node_id)
                description = getattr(node, "description", "") or description
        return Goal(id=f"goal_{node_id}", type="reach_node", target=target, description=description)

    def _estimate_heuristic(self, node_id: str, current_state: Dict[str, Any], goal: Goal) -> float:
        try:
            value = _safe_float(self.heuristic.estimate_cost(node_id, current_state, goal, self.nodes), 0.0)
            return max(0.0, value)
        except Exception:
            logger.debug("Heurística no disponible para %s", node_id, exc_info=True)
            return 0.0

    @staticmethod
    def _state_signature(state: Dict[str, Any]) -> str:
        try:
            canonical = json.dumps(
                _json_safe(state or {}), sort_keys=True, ensure_ascii=False,
                allow_nan=False, separators=(",", ":"),
            )
        except Exception:
            try:
                canonical = repr(sorted((str(key), repr(value)) for key, value in (state or {}).items()))
            except Exception:
                canonical = repr(state)
        return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


class GraphBuilder:
    """Constructores de grafos básicos de navegación y estado de aplicación."""

    @staticmethod
    def build_navigation_graph(nodes: Dict[str, Node]) -> StateGraph:
        graph = StateGraph()
        for node in nodes.values():
            graph.add_node(node)
        edges = [
            ("chrome.closed", "chrome.open", 10.0, ["chrome_closed"], "normal"),
            ("chrome.open", "chrome.activate", 2.0, ["chrome_open"], "normal"),
            ("chrome.activate", "focus_address_bar", 1.0, ["chrome_active"], "normal"),
            ("focus_address_bar", "type_url", 1.0, ["address_bar_focused"], "normal"),
            ("type_url", "press_enter", 1.0, ["url_typed"], "normal"),
            ("press_enter", "destination.loaded", 1.0, ["destination_loaded"], "normal"),
            ("chrome.activate", "click_address_bar", 1.5, ["chrome_active"], "alternative"),
            ("click_address_bar", "type_url", 1.0, ["address_bar_clicked"], "alternative"),
            ("chrome.activate", "hotkey_ctrl_l", 0.5, ["chrome_active"], "alternative"),
            ("hotkey_ctrl_l", "focus_address_bar", 0.0, [], "alternative"),
            ("chrome.activate", "search_google", 3.0, ["chrome_active"], "alternative"),
            ("search_google", "destination.loaded", 1.0, ["search_performed"], "normal"),
        ]
        for source, target, cost, conditions, transition in edges:
            if source in nodes and target in nodes:
                graph.add_edge(source, target, cost, conditions, transition)
        edge = graph.get_edge("chrome.closed", "chrome.open")
        if edge is not None:
            edge.preconditions.append(Condition(type=ConditionType.STATE_TRUE, key="chrome_closed"))
            edge.effects.append(Effect(type="state_set", key="chrome_open", value=True))
            graph._invalidate_search_cache()
        return graph

    @staticmethod
    def build_application_graph(nodes: Dict[str, Node]) -> StateGraph:
        graph = StateGraph()
        for node in nodes.values():
            graph.add_node(node)
        edges = [
            ("application.closed", "application.open", 5.0, ["app_closed"], "normal"),
            ("application.open", "application.active", 1.0, ["app_open"], "normal"),
            ("application.active", "application.inactive", 0.5, ["app_active"], "alternative"),
            ("application.inactive", "application.active", 1.0, ["app_inactive"], "normal"),
            ("application.active", "element.focused", 1.0, ["app_active"], "normal"),
            ("element.focused", "text.typed", 1.0, ["element_focused"], "normal"),
            ("text.typed", "action.executed", 0.5, ["text_typed"], "normal"),
        ]
        for source, target, cost, conditions, transition in edges:
            if source in nodes and target in nodes:
                graph.add_edge(source, target, cost, conditions, transition)
        edge = graph.get_edge("application.closed", "application.open")
        if edge is not None:
            edge.preconditions.append(Condition(type=ConditionType.STATE_TRUE, key="app_closed"))
            edge.effects.append(Effect(type="state_set", key="app_open", value=True))
            graph._invalidate_search_cache()
        return graph


class CacheEntry:
    """Entrada de caché con contexto, resultado y contador de accesos."""

    def __init__(
        self,
        path: List[str],
        cost: float,
        state: Dict[str, Any],
        timestamp: float,
        final_state: Optional[Dict[str, Any]] = None,
        strategy: Optional[str] = None,
        alternative_paths: Optional[List[List[str]]] = None,
        graph_revision: Optional[int] = None,
    ) -> None:
        self.path = list(path)
        self.cost = _safe_float(cost, float("inf"))
        self.state = _copy_state(state)
        self.timestamp = _safe_float(timestamp, time.time())
        self.final_state = _copy_state(final_state)
        self.strategy = strategy
        self.alternative_paths = [list(item) for item in (alternative_paths or [])]
        self.graph_revision = graph_revision
        self.access_count = 0
        self.last_access = self.timestamp

    def is_expired(self, max_age_seconds: float = 300) -> bool:
        return time.time() - self.timestamp > max(0.0, _safe_float(max_age_seconds, 300.0))

    def increment_access(self) -> None:
        self.access_count += 1
        self.last_access = time.time()


class PerformanceMetrics:
    """Métricas acumuladas de búsqueda y caché."""

    def __init__(self) -> None:
        self.search_count = 0
        self.total_search_time = 0.0
        self.successful_searches = 0
        self.average_path_length = 0.0
        self.average_cost = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        self.max_iterations = 0
        self.min_iterations = float("inf")

    def record_search(self, success: bool, path_length: int, cost: float, search_time: float, iterations: int) -> None:
        self.search_count += 1
        self.total_search_time += max(0.0, _safe_float(search_time, 0.0))
        normalized_iterations = max(0, int(_safe_float(iterations, 0)))
        self.max_iterations = max(self.max_iterations, normalized_iterations)
        self.min_iterations = min(self.min_iterations, normalized_iterations)
        if success:
            self.successful_searches += 1
            n = self.successful_searches
            self.average_path_length = ((self.average_path_length * (n - 1)) + max(0, path_length)) / n
            normalized_cost = _safe_float(cost, 0.0)
            self.average_cost = ((self.average_cost * (n - 1)) + normalized_cost) / n

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        self.cache_misses += 1

    def get_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    def get_average_search_time(self) -> float:
        return self.total_search_time / self.search_count if self.search_count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search_count": self.search_count,
            "successful_searches": self.successful_searches,
            "success_rate": self.successful_searches / self.search_count if self.search_count else 0.0,
            "average_search_time": self.get_average_search_time(),
            "average_path_length": self.average_path_length,
            "average_cost": self.average_cost,
            "cache_hit_rate": self.get_hit_rate(),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "max_iterations": self.max_iterations,
            "min_iterations": self.min_iterations if self.min_iterations != float("inf") else 0,
        }


class AdvancedStateGraph(StateGraph):
    """StateGraph con caché acotada y métricas de rendimiento."""

    def __init__(self, heuristic: Optional[Heuristic] = None, cache_size: int = 100, max_cache_age: float = 300) -> None:
        super().__init__(heuristic)
        self.search_cache: Dict[str, List[CacheEntry]] = {}
        self.cache_size = max(1, int(_safe_float(cache_size, 100)))
        self.max_cache_age = max(0.0, _safe_float(max_cache_age, 300.0))
        self.performance_metrics = PerformanceMetrics()
        self.search_strategy = SearchStrategy.A_STAR

    def find_path_with_strategy(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: Optional[SearchStrategy | str] = None,
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> Tuple[List[str], float, List[List[str]]]:
        started = time.perf_counter()
        try:
            selected = self._normalize_strategy(strategy if strategy is not None else self.search_strategy)
        except ValueError:
            self.last_search_iterations = 0
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        state = _copy_state(current_state)
        limit = self._normalize_max_iterations(max_iterations)
        alternatives_limit = self._normalize_alternative_count(alternative_count)
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            self.last_search_iterations = 0
            self.last_search_elapsed = time.perf_counter() - started
            return [], float("inf"), []
        key = self._build_cache_key(
            start_node_id, goal_node_id, state, selected, find_alternatives,
            alternatives_limit, limit,
        )
        cached = self._get_from_cache(key, state)
        if cached is not None and cached.graph_revision == self.graph_revision:
            self.performance_metrics.record_cache_hit()
            self.last_search_iterations = 0
            self.last_search_elapsed = time.perf_counter() - started
            return list(cached.path), cached.cost, [list(path) for path in cached.alternative_paths]
        self.performance_metrics.record_cache_miss()
        path, cost, alternatives = self._execute_strategy(
            start_node_id, goal_node_id, state, selected, limit,
            find_alternatives, alternatives_limit,
        )
        elapsed = time.perf_counter() - started
        self.performance_metrics.record_search(bool(path), len(path), cost, elapsed, self.last_search_iterations)
        if path:
            self._add_to_cache(
                key,
                CacheEntry(
                    path=path,
                    cost=cost,
                    state=state,
                    timestamp=time.time(),
                    final_state=self.apply_path_effects(path, state),
                    strategy=selected.value,
                    alternative_paths=alternatives,
                    graph_revision=self.graph_revision,
                ),
            )
        return path, cost, alternatives

    def _execute_strategy(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: SearchStrategy,
        max_iterations: int,
        find_alternatives: bool,
        alternative_count: int,
    ) -> Tuple[List[str], float, List[List[str]]]:
        return {
            SearchStrategy.A_STAR: self.find_path_astar,
            SearchStrategy.DIJKSTRA: self.find_path_dijkstra,
            SearchStrategy.BFS: self.find_path_bfs,
            SearchStrategy.DFS: self.find_path_dfs,
            SearchStrategy.GREEDY: self.find_path_greedy,
        }[strategy](
            start_node_id, goal_node_id, current_state, max_iterations,
            find_alternatives, alternative_count,
        )

    def find_route(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Optional[Dict[str, Any]] = None,
        strategy: Optional[SearchStrategy | str] = None,
        max_iterations: int = 1000,
        find_alternatives: bool = False,
        alternative_count: int = 3,
    ) -> RouteResult:
        started = time.perf_counter()
        state = _copy_state(current_state)
        try:
            selected = self._normalize_strategy(strategy if strategy is not None else self.search_strategy)
        except ValueError as exc:
            return self._route_error(start_node_id, goal_node_id, str(strategy), state, str(exc), started)
        path, cost, alternatives = self.find_path_with_strategy(
            start_node_id, goal_node_id, state, selected, max_iterations,
            find_alternatives, alternative_count,
        )
        success = bool(path)
        return RouteResult(
            success=success,
            start_node_id=start_node_id,
            goal_node_id=goal_node_id,
            path=path,
            edges=self.get_edges_for_path(path, state),
            total_cost=cost,
            alternative_paths=alternatives,
            strategy=selected.value,
            iterations=self.last_search_iterations,
            elapsed_time=time.perf_counter() - started,
            initial_state=state,
            final_state=self.apply_path_effects(path, state) if success else state,
            error=None if success else "No se encontró una ruta dentro de los límites indicados",
        )

    def build_route(self, *args: Any, **kwargs: Any) -> RouteResult:
        return self.find_route(*args, **kwargs)

    def _build_cache_key(
        self,
        start_node_id: str,
        goal_node_id: str,
        current_state: Dict[str, Any],
        strategy: SearchStrategy,
        find_alternatives: bool,
        alternative_count: int,
        max_iterations: int = 1000,
    ) -> str:
        payload = {
            "start": start_node_id,
            "goal": goal_node_id,
            "state": _json_safe(current_state),
            "strategy": strategy.value,
            "alternatives": bool(find_alternatives),
            "alternative_count": int(alternative_count),
            "max_iterations": int(max_iterations),
            "graph_revision": self.graph_revision,
            "heuristic_type": _type_value(getattr(self.heuristic, "heuristic_type", None)),
            "heuristic_weight": getattr(self.heuristic, "weight", None),
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8", errors="replace")).hexdigest()

    def _get_from_cache(self, cache_key: str, current_state: Dict[str, Any]) -> Optional[CacheEntry]:
        del current_state
        entries = self.search_cache.get(cache_key)
        if not entries:
            return None
        valid = [
            entry for entry in entries
            if not entry.is_expired(self.max_cache_age)
            and (entry.graph_revision is None or entry.graph_revision == self.graph_revision)
        ]
        if not valid:
            self.search_cache.pop(cache_key, None)
            return None
        best = max(valid, key=lambda entry: (entry.last_access, entry.access_count, entry.timestamp))
        best.increment_access()
        self.search_cache[cache_key] = [best]
        return best

    def _add_to_cache(self, cache_key: str, entry: CacheEntry) -> None:
        self.search_cache[cache_key] = [entry]
        # Acota el total de claves, no solo las entradas dentro de cada clave.
        while len(self.search_cache) > self.cache_size:
            oldest_key = min(
                self.search_cache,
                key=lambda key: max((item.last_access for item in self.search_cache[key]), default=0.0),
            )
            self.search_cache.pop(oldest_key, None)

    def _cleanup_cache(self) -> None:
        for key in list(self.search_cache):
            valid = [
                entry for entry in self.search_cache[key]
                if not entry.is_expired(self.max_cache_age)
                and (entry.graph_revision is None or entry.graph_revision == self.graph_revision)
            ]
            if valid:
                self.search_cache[key] = valid
            else:
                del self.search_cache[key]

    def get_advanced_stats(self) -> Dict[str, Any]:
        return {
            **self.get_graph_stats(),
            "search_cache_keys": len(self.search_cache),
            "cache_hit_rate": self.performance_metrics.get_hit_rate(),
            "performance_metrics": self.performance_metrics.to_dict(),
            "search_strategies": list(dict.fromkeys(strategy.value for strategy in SearchStrategy)),
            "current_strategy": self.search_strategy.value,
            "cache_config": {"max_size": self.cache_size, "max_age_seconds": self.max_cache_age},
        }

    def optimize_graph_for_performance(self) -> List[str]:
        """Limpia caché y ajusta su límite sin cambiar semántica de búsqueda."""
        changes: List[str] = []
        before = len(self.search_cache)
        self._cleanup_cache()
        after = len(self.search_cache)
        if before != after:
            changes.append(f"Caché limpiada: {before} -> {after} claves")
        new_size = 200 if len(self.nodes) > 100 else 150 if len(self.nodes) > 50 else 100
        if self.cache_size != new_size:
            self.cache_size = new_size
            changes.append(f"Tamaño de caché: {new_size}")
        while len(self.search_cache) > self.cache_size:
            oldest_key = min(
                self.search_cache,
                key=lambda key: max((entry.last_access for entry in self.search_cache[key]), default=0.0),
            )
            del self.search_cache[oldest_key]
        return changes


__all__ = [
    "SearchStrategy",
    "RouteResult",
    "GraphNode",
    "GraphEdge",
    "StateGraph",
    "GraphBuilder",
    "CacheEntry",
    "PerformanceMetrics",
    "AdvancedStateGraph",
]
