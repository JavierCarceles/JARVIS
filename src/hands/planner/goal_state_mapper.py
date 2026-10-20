"""

Responsabilidades:
- Convertir un Goal en nodos del StateGraph.
- Representar el World State en nodos del StateGraph.
- Mapear capacidades reutilizables a acciones del grafo.
- Crear relaciones explícitas entre objetivos, capacidades, acciones y estado.
- Mantener trazabilidad del mapeo mediante MappingResult e historial.

Este módulo prepara la entrada estructurada que utilizará la siguiente fase
(6.5.3) para construir rutas/planes. No ejecuta acciones ni convierte rutas
en planes ejecutables.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.hands.planner.graph import StateGraph
from src.hands.planner.node import Goal, Node, NodeType, WorldState as WorldStateData
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MappingType(Enum):
    """Tipos de mapeo soportados."""

    GOAL_TO_NODES = "goal_to_nodes"
    STATE_TO_NODES = "state_to_nodes"
    CAPABILITY_TO_NODES = "capability_to_nodes"
    HYBRID = "hybrid"


@dataclass
class MappingResult:
    """Resultado de una operación de mapeo."""

    mapping_type: MappingType
    created_nodes: List[str] = field(default_factory=list)
    created_edges: List[Tuple[str, str]] = field(default_factory=list)
    mapping_quality: float = 0.0
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0


class GoalStateMapper:
    """
    Mapea Goal y World State al StateGraph.

    El mapper mantiene una separación clara entre:
        - conocimiento del objetivo;
        - capacidades necesarias;
        - acciones concretas;
        - representación del estado actual.

    No ejecuta acciones y no genera todavía un ``Plan`` ejecutable.
    """

    def __init__(self, state_graph: StateGraph) -> None:
        if state_graph is None:
            raise ValueError("state_graph no puede ser None")

        self.state_graph = state_graph
        self.mapping_history: List[Dict[str, Any]] = []

        # Capacidades primitivas reutilizables. Los valores son plantillas para
        # crear Nodes; no son acciones ejecutadas por este módulo.
        self.base_capabilities: Dict[str, Dict[str, Any]] = {
            "open_application": {
                "type": NodeType.ACTION,
                "cost": 5.0,
                "preconditions": ["application_available"],
                "effects": ["application_open"],
                "category": "system",
            },
            "close_application": {
                "type": NodeType.ACTION,
                "cost": 3.0,
                "preconditions": ["application_open"],
                "effects": ["application_closed"],
                "category": "system",
            },
            "navigate": {
                "type": NodeType.ACTION,
                "cost": 2.0,
                "preconditions": ["browser_open", "browser_active"],
                "effects": ["url_changed"],
                "category": "browser",
            },
            "focus_element": {
                "type": NodeType.ACTION,
                "cost": 1.0,
                "preconditions": ["element_visible"],
                "effects": ["element_focused"],
                "category": "ui",
            },
            "type_text": {
                "type": NodeType.ACTION,
                "cost": 1.0,
                "preconditions": ["element_focused"],
                "effects": ["text_typed"],
                "category": "ui",
            },
            "press_key": {
                "type": NodeType.ACTION,
                "cost": 0.5,
                "preconditions": ["element_focused"],
                "effects": ["key_pressed"],
                "category": "ui",
            },
            "new_tab": {
                "type": NodeType.ACTION,
                "cost": 2.0,
                "preconditions": ["browser_open"],
                "effects": ["new_tab_created"],
                "category": "browser",
            },
            "close_tab": {
                "type": NodeType.ACTION,
                "cost": 1.0,
                "preconditions": ["tab_open"],
                "effects": ["tab_closed"],
                "category": "browser",
            },
            "activate_window": {
                "type": NodeType.ACTION,
                "cost": 1.0,
                "preconditions": ["application_open"],
                "effects": ["application_active"],
                "category": "system",
            },
            "search": {
                "type": NodeType.ACTION,
                "cost": 3.0,
                "preconditions": ["browser_open", "browser_active"],
                "effects": ["search_performed"],
                "category": "search",
            },
        }

    # ======================================================================
    # API PÚBLICA
    # ======================================================================

    def map_goal_to_graph(
        self,
        goal: Goal,
        world_state: WorldStateData,
    ) -> MappingResult:
        """Mapea un objetivo y su contexto al grafo sin ejecutar acciones."""
        started = time.perf_counter()
        result = MappingResult(mapping_type=MappingType.GOAL_TO_NODES)
        goal_id: Optional[str] = None
        try:
            goal_id = self._get_required_id(goal, "goal")
            logger.info("[MAPPER] Mapeando objetivo %s al grafo", goal_id)

            goal_node = self._create_goal_node(goal, world_state)
            self._add_node(goal_node, result)

            capabilities = self._get_required_capabilities(goal)
            capability_nodes = self._create_capability_nodes(capabilities, result=result)
            specific_nodes = self._create_goal_specific_nodes(goal, world_state, result=result)

            self._establish_goal_transitions(
                goal_node_id=goal_node.id,
                capability_nodes=capability_nodes,
                specific_nodes=specific_nodes,
                goal=goal,
                result=result,
            )
            result.mapping_quality = self._calculate_mapping_quality(goal, result.created_nodes)
        except Exception as exc:
            logger.exception("[MAPPER] Falló el mapeo del objetivo")
            result.warnings.append(f"Fallo en mapeo de objetivo: {exc}")

        result.execution_time = max(0.0, time.perf_counter() - started)
        self._record_history(operation="goal_mapping", goal_id=goal_id, result=result)
        logger.info(
            "[MAPPER] Goal %s mapeado: %s nodos, %s aristas, calidad=%.3f",
            goal_id or "desconocido",
            len(result.created_nodes),
            len(result.created_edges),
            result.mapping_quality,
        )
        return result

    def map_world_state_to_graph(
        self,
        world_state: WorldStateData,
    ) -> MappingResult:
        """Mapea el estado del mundo, tanto en formato canónico como legacy."""
        started = time.perf_counter()
        result = MappingResult(mapping_type=MappingType.STATE_TO_NODES)
        try:
            if world_state is None:
                result.warnings.append("World State ausente; se mapeará un estado vacío")

            app_nodes = self._create_application_state_nodes(world_state, result=result)
            resource_nodes = self._create_resource_nodes(world_state, result=result)
            calibrated_nodes = self._create_calibrated_element_nodes(world_state, result=result)
            generic_state_nodes = self._create_generic_state_nodes(world_state, result=result)

            self._establish_state_transitions(
                app_nodes=app_nodes,
                resource_nodes=resource_nodes,
                calibrated_nodes=calibrated_nodes,
                world_state=world_state,
                result=result,
            )
            result.mapping_quality = self._calculate_state_mapping_quality(
                world_state,
                self._unique_preserve_order(
                    result.created_nodes + generic_state_nodes
                ),
            )
        except Exception as exc:
            logger.exception("[MAPPER] Falló el mapeo del estado del mundo")
            result.warnings.append(f"Fallo en mapeo de estado: {exc}")

        result.execution_time = max(0.0, time.perf_counter() - started)
        self._record_history(operation="world_state_mapping", result=result)
        logger.info(
            "[MAPPER] World State mapeado: %s nodos, %s aristas, calidad=%.3f",
            len(result.created_nodes),
            len(result.created_edges),
            result.mapping_quality,
        )
        return result

    def map_capabilities_to_graph(
        self,
        capabilities: Sequence[str],
    ) -> MappingResult:
        """Mapea capacidades declaradas a nodos reutilizables conocidos."""
        started = time.perf_counter()
        result = MappingResult(mapping_type=MappingType.CAPABILITY_TO_NODES)
        raw_capabilities = self._safe_iterable(capabilities)
        normalized_capabilities = self._unique_preserve_order(
            str(capability).strip().lower()
            for capability in raw_capabilities
            if capability is not None and str(capability).strip()
        )

        try:
            self._create_capability_nodes(normalized_capabilities, result=result)
            supported_count = sum(
                1 for capability in normalized_capabilities
                if capability in self.base_capabilities
            )
            result.mapping_quality = (
                supported_count / len(normalized_capabilities)
                if normalized_capabilities else 0.0
            )
            unsupported = [
                capability for capability in normalized_capabilities
                if capability not in self.base_capabilities
            ]
            if unsupported:
                result.warnings.append(
                    "Capacidades sin plantilla base: " + ", ".join(unsupported)
                )
        except Exception as exc:
            logger.exception("[MAPPER] Falló el mapeo de capacidades")
            result.warnings.append(f"Fallo en mapeo de capacidades: {exc}")

        result.execution_time = max(0.0, time.perf_counter() - started)
        self._record_history(operation="capability_mapping", result=result)
        return result

    def map_goal_and_world_state_to_graph(
        self,
        goal: Goal,
        world_state: WorldStateData,
    ) -> MappingResult:
        """Realiza el mapeo híbrido y agrega sus resultados sin duplicados."""
        started = time.perf_counter()
        result = MappingResult(mapping_type=MappingType.HYBRID)
        goal_result = self.map_goal_to_graph(goal, world_state)
        state_result = self.map_world_state_to_graph(world_state)

        result.created_nodes = self._unique_preserve_order(
            goal_result.created_nodes + state_result.created_nodes
        )
        result.created_edges = self._unique_edges(
            goal_result.created_edges + state_result.created_edges
        )
        result.mapping_quality = max(
            0.0, min(1.0, (goal_result.mapping_quality + state_result.mapping_quality) / 2.0)
        )
        result.warnings = list(goal_result.warnings) + list(state_result.warnings)
        result.execution_time = max(0.0, time.perf_counter() - started)
        self._record_history(
            operation="hybrid_mapping",
            goal_id=self._safe_getattr(goal, "id"),
            result=result,
        )
        return result

    def get_mapping_history(self) -> List[Dict[str, Any]]:
        """Devuelve una copia del historial de mapeos."""
        return copy.deepcopy(self.mapping_history)

    def clear_mapping_history(self) -> None:
        """Limpia el historial de mapeos."""
        self.mapping_history.clear()

    # ======================================================================
    # CREACIÓN DE NODOS DE GOAL
    # ======================================================================

    def _create_goal_node(
        self,
        goal: Goal,
        world_state: Optional[WorldStateData] = None,
    ) -> Node:
        """Crea el nodo raíz de un objetivo con metadatos normalizados."""
        goal_id = self._get_required_id(goal, "goal")
        goal_type = self._normalize_goal_type(self._safe_getattr(goal, "type", "goal"))
        description = str(
            self._safe_getattr(goal, "description", "")
            or f"Realizar objetivo: {goal_type}"
        )
        target = copy.deepcopy(self._safe_getattr(goal, "target", None))
        priority = self._safe_getattr(goal, "priority", 1)
        deadline = self._safe_getattr(goal, "deadline", None)
        metadata = self._get_goal_metadata(goal)
        metadata.update({
            "goal_id": goal_id,
            "goal_type": goal_type,
            "priority": priority,
            "deadline": deadline,
            "target": target,
            "mapping_phase": "6.5.2",
        })
        if world_state is not None:
            metadata["world_state_mapped"] = True
        return Node(
            id=f"goal_{goal_id}",
            type=NodeType.GOAL,
            name=self._get_goal_name(goal, goal_type),
            description=description,
            cost=self._get_goal_base_cost(goal),
            metadata=metadata,
        )

    def _create_capability_nodes(
        self,
        capabilities: Sequence[str],
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea una única instancia de cada capacidad base reconocida."""
        created_nodes: List[str] = []
        for raw_capability in self._safe_iterable(capabilities):
            if raw_capability is None:
                continue
            capability = str(raw_capability).strip().lower()
            if not capability:
                continue
            template = self.base_capabilities.get(capability)
            if template is None:
                if result is not None:
                    warning = f"Capacidad no soportada por plantilla base: {capability}"
                    if warning not in result.warnings:
                        result.warnings.append(warning)
                continue
            node = self._build_capability_node(capability, template)
            self._add_node(node, result)
            if node.id not in created_nodes:
                created_nodes.append(node.id)
        return created_nodes

    def _build_capability_node(
        self,
        capability: str,
        template: Dict[str, Any],
    ) -> Node:
        """Construye una acción reutilizable a partir de una plantilla validada."""
        raw_cost = template.get("cost", 1.0)
        cost = self._safe_nonnegative_float(raw_cost, default=1.0)
        return Node(
            id=f"capability_{self._safe_id_component(capability)}",
            type=template.get("type", NodeType.ACTION),
            name=capability.replace("_", " ").title(),
            description=f"Capacidad del sistema: {capability}",
            cost=cost,
            preconditions=self._normalize_conditions(template.get("preconditions", [])),
            effects=self._normalize_conditions(template.get("effects", [])),
            action_category=str(template.get("category", "system")),
            reusable_action=True,
            metadata={"capability": capability, "mapping_phase": "6.5.2"},
        )

    def _create_goal_specific_nodes(
        self,
        goal: Goal,
        world_state: WorldStateData,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea acciones concretas según la intención y el tipo de objetivo."""
        goal_type = self._normalize_goal_type(self._safe_getattr(goal, "type", ""))

        # Para búsquedas de una plataforma conocida, la secuencia especializada
        # sustituye a la búsqueda genérica; así se evitan acciones duplicadas.
        if goal_type == "search":
            specialized = self._map_goal_specific_nodes(goal, world_state, result=result)
            if specialized:
                return self._unique_preserve_order(specialized)
            return self._create_search_nodes(goal, world_state, result=result)

        creators = {
            "navigate": self._create_navigation_nodes,
            "navigate_stream": self._create_navigation_nodes,
            "navigate_to_entity": self._create_navigation_nodes,
            "open_application": self._create_open_app_nodes,
            "close_application": self._create_close_app_nodes,
        }
        creator = creators.get(goal_type)
        if creator is not None:
            return self._unique_preserve_order(creator(goal, world_state, result=result))

        return self._unique_preserve_order(
            self._map_goal_specific_nodes(goal, world_state, result=result)
        )

    def _create_navigation_nodes(
        self,
        goal: Goal,
        world_state: Optional[WorldStateData] = None,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea la secuencia lógica de abrir el navegador y navegar a un destino."""
        del world_state
        nodes: List[str] = []
        goal_id = self._get_required_id(goal, "goal")
        target = self._get_goal_target_value(
            goal, ("url", "href", "target_url", "destination", "name"),
            fallback_keys=("url", "target_url", "entity_data"),
        )
        if isinstance(target, dict):
            target = target.get("url") or target.get("href") or target.get("name")
        target_text = str(target).strip() if target is not None else ""
        metadata = self._get_goal_metadata(goal)
        skip_browser_open = bool(metadata.get("skip_browser_open", False))

        if not skip_browser_open:
            browser_node = Node(
                id=f"open_browser_for_{goal_id}",
                type=NodeType.ACTION,
                name="Open Browser",
                description="Abrir navegador web para navegación",
                cost=5.0,
                preconditions=["application_available"],
                effects=["browser_open", "browser_active"],
                action_category="browser",
                metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
            )
            self._add_node(browser_node, result)
            nodes.append(browser_node.id)

        nav_node = Node(
            id=f"navigate_to_{goal_id}",
            type=NodeType.ACTION,
            name="Navigate to URL",
            description=f"Navegar a {target_text or 'el destino del objetivo'}",
            cost=2.0,
            preconditions=["browser_open", "browser_active"],
            effects=["url_changed", f"navigated_to_{goal_id}"],
            parameters={"url": target_text} if target_text else {},
            action_category="browser",
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(nav_node, result)
        nodes.append(nav_node.id)
        return nodes

    def _create_open_app_nodes(
        self,
        goal: Goal,
        world_state: Optional[WorldStateData] = None,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea los nodos de abrir y activar la aplicación objetivo."""
        del world_state
        target = self._normalize_target_name(
            self._get_goal_target_value(
                goal, ("app_name", "application", "program", "name"),
                fallback_keys=("app_name", "application", "name"),
            )
        )
        safe_target = self._safe_id_component(target)
        goal_id = self._get_required_id(goal, "goal")
        app_node = Node(
            id=f"open_{safe_target}", type=NodeType.ACTION,
            name=f"Open {target}", description=f"Abrir aplicación {target}",
            cost=5.0, preconditions=["application_available"],
            effects=[f"{safe_target}_open", "application_open"],
            action_category="system", parameters={"application": target},
            metadata={"goal_id": goal_id, "application": target, "mapping_phase": "6.5.2"},
        )
        self._add_node(app_node, result)
        activate_node = Node(
            id=f"activate_{safe_target}", type=NodeType.ACTION,
            name=f"Activate {target}", description=f"Activar ventana de {target}",
            cost=2.0, preconditions=[f"{safe_target}_open"],
            effects=[f"{safe_target}_active", "application_active"],
            action_category="system", parameters={"application": target},
            metadata={"goal_id": goal_id, "application": target, "mapping_phase": "6.5.2"},
        )
        self._add_node(activate_node, result)
        return [app_node.id, activate_node.id]

    def _create_close_app_nodes(
        self,
        goal: Goal,
        world_state: Optional[WorldStateData] = None,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea la acción para cerrar la aplicación indicada por el objetivo."""
        del world_state
        target = self._normalize_target_name(
            self._get_goal_target_value(
                goal, ("app_name", "application", "program", "name"),
                fallback_keys=("app_name", "application", "name"),
            )
        )
        safe_target = self._safe_id_component(target)
        goal_id = self._get_required_id(goal, "goal")
        close_node = Node(
            id=f"close_{safe_target}", type=NodeType.ACTION,
            name=f"Close {target}", description=f"Cerrar aplicación {target}",
            cost=3.0, preconditions=[f"{safe_target}_open"],
            effects=[f"{safe_target}_closed", "application_closed"],
            action_category="system", parameters={"application": target},
            metadata={"goal_id": goal_id, "application": target, "mapping_phase": "6.5.2"},
        )
        self._add_node(close_node, result)
        return [close_node.id]

    def _create_search_nodes(
        self,
        goal: Goal,
        world_state: Optional[WorldStateData] = None,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea la secuencia genérica de preparar navegador y realizar búsqueda."""
        del world_state
        goal_id = self._get_required_id(goal, "goal")
        query = self._get_goal_target_value(
            goal, ("query", "search_query", "search_term", "text", "name", "title"),
            fallback_keys=("query", "search_query", "search_term"),
        )
        if isinstance(query, (dict, list, tuple, set)):
            query = str(query)
        query_text = str(query).strip() if query is not None else ""
        nodes: List[str] = []
        metadata = self._get_goal_metadata(goal)
        if not bool(metadata.get("skip_browser_open", False)):
            browser_node = Node(
                id=f"open_browser_for_{goal_id}",
                type=NodeType.ACTION,
                name="Open Browser",
                description="Abrir navegador web para realizar la búsqueda",
                cost=5.0,
                preconditions=["application_available"],
                effects=["browser_open", "browser_active"],
                action_category="browser",
                metadata={"goal_id": goal_id, "mapping_phase": "6.5.2"},
            )
            self._add_node(browser_node, result)
            nodes.append(browser_node.id)

        search_node = Node(
            id=f"search_for_{goal_id}", type=NodeType.ACTION,
            name="Perform Search",
            description=f"Realizar búsqueda: {query_text}" if query_text else "Realizar búsqueda solicitada",
            cost=3.0, preconditions=["browser_open", "browser_active"],
            effects=["search_performed", f"search_results_{self._safe_id_component(goal_id)}"],
            parameters={"query": query_text} if query_text else {},
            action_category="search",
            metadata={"goal_id": goal_id, "mapping_phase": "6.5.2"},
        )
        self._add_node(search_node, result)
        nodes.append(search_node.id)
        return nodes

    def _map_goal_specific_nodes(
        self,
        goal: Goal,
        world_state: WorldStateData,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Añade una secuencia específica para búsquedas de plataformas conocidas."""
        del world_state
        target = self._safe_getattr(goal, "target", None)
        metadata = self._get_goal_metadata(goal)
        if isinstance(target, dict):
            searchable_parts = [str(value) for value in target.values() if value is not None]
        else:
            searchable_parts = [str(target)] if target is not None else []
        platform = metadata.get("platform")
        if platform is not None:
            searchable_parts.append(str(platform))
        searchable = " ".join(searchable_parts)
        target_lower = searchable.casefold()
        goal_type = self._normalize_goal_type(self._safe_getattr(goal, "type", ""))
        if goal_type != "search":
            return []
        if "youtube" in target_lower:
            return self._create_youtube_specific_nodes(goal, result=result)
        if "spotify" in target_lower:
            return self._create_spotify_specific_nodes(goal, result=result)
        return []

    def _create_youtube_specific_nodes(
        self,
        goal: Goal,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea abrir navegador, acceder a YouTube y buscar en ese servicio."""
        goal_id = self._get_required_id(goal, "goal")
        target = self._get_goal_target_value(
            goal, ("query", "search_query", "search_term", "text", "title", "name"),
            fallback_keys=("query", "search_query", "search_term"),
        )
        query = str(target).strip() if target is not None else ""
        nodes: List[str] = []
        browser_open = Node(
            id=f"open_browser_for_{goal_id}", type=NodeType.ACTION,
            name="Open Browser", description="Abrir navegador para buscar en YouTube",
            cost=5.0, preconditions=["application_available"],
            effects=["browser_open", "browser_active"], action_category="browser",
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(browser_open, result)
        nodes.append(browser_open.id)
        youtube_open = Node(
            id=f"open_youtube_for_{goal_id}", type=NodeType.ACTION,
            name="Open YouTube", description="Navegar al sitio de YouTube",
            cost=2.0, preconditions=["browser_open", "browser_active"],
            effects=["youtube_open", "youtube_active"], action_category="browser",
            parameters={"url": "https://www.youtube.com"},
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(youtube_open, result)
        nodes.append(youtube_open.id)
        youtube_search = Node(
            id=f"youtube_search_for_{goal_id}", type=NodeType.ACTION,
            name="YouTube Search", description=f"Buscar en YouTube: {query or 'consulta solicitada'}",
            cost=3.0, preconditions=["youtube_open", "youtube_active"],
            effects=["search_performed", f"youtube_results_{goal_id}"],
            parameters={"query": query} if query else {}, action_category="search",
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(youtube_search, result)
        nodes.append(youtube_search.id)
        return nodes

    def _create_browser_specific_nodes(
        self,
        goal: Goal,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Compatibilidad para crear una secuencia genérica de navegador."""
        # Mantiene el método para callers legacy, pero no interpreta el nombre
        # "Chrome" como una URL ni genera una navegación inventada.
        return self._create_navigation_nodes(goal, result=result)

    def _create_spotify_specific_nodes(
        self,
        goal: Goal,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea abrir Spotify y buscar el contenido solicitado."""
        goal_id = self._get_required_id(goal, "goal")
        target = self._get_goal_target_value(
            goal, ("query", "search_query", "search_term", "text", "title", "name"),
            fallback_keys=("query", "search_query", "search_term"),
        )
        query = str(target).strip() if target is not None else ""
        nodes: List[str] = []
        spotify_open = Node(
            id=f"open_spotify_for_{goal_id}", type=NodeType.ACTION,
            name="Open Spotify", description="Abrir la aplicación Spotify",
            cost=4.0, preconditions=["spotify_available"],
            effects=["spotify_open", "spotify_active"], action_category="system",
            parameters={"application": "Spotify"},
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(spotify_open, result)
        nodes.append(spotify_open.id)
        spotify_search = Node(
            id=f"spotify_search_for_{goal_id}", type=NodeType.ACTION,
            name="Spotify Search", description=f"Buscar en Spotify: {query or 'consulta solicitada'}",
            cost=2.0, preconditions=["spotify_open", "spotify_active"],
            effects=["search_performed", f"spotify_results_{goal_id}"],
            parameters={"query": query} if query else {}, action_category="search",
            metadata={"goal_id": self._safe_getattr(goal, "id"), "mapping_phase": "6.5.2"},
        )
        self._add_node(spotify_search, result)
        nodes.append(spotify_search.id)
        return nodes

    # ======================================================================
    # ESTADO DEL MUNDO
    # ======================================================================

    def _create_application_state_nodes(
        self,
        world_state: WorldStateData,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea nodos STATE por aplicación, aceptando objetos y diccionarios."""
        nodes: List[str] = []
        applications = self._as_dict(self._world_state_field(world_state, "applications", {}))
        for app_name, app_info in applications.items():
            state_value = self._get_state_value(app_info)
            safe_app = self._safe_id_component(app_name)
            node = Node(
                id=f"state_{safe_app}_{self._safe_id_component(state_value)}",
                type=NodeType.STATE,
                name=f"{app_name} State: {state_value}",
                description=f"Estado actual de {app_name}: {state_value}",
                cost=0.0,
                metadata={
                    "application": str(app_name),
                    "state": state_value,
                    "window_title": self._read_field(app_info, "window_title", ""),
                    "visible_elements": copy.deepcopy(self._read_field(app_info, "visible_elements", [])),
                    "monitor_id": self._first_present(
                        self._read_field(app_info, "monitor_id"),
                        self._read_field(app_info, "screen_id"),
                        self._read_field(app_info, "screen"),
                    ),
                    "mapping_phase": "6.5.2",
                },
            )
            self._add_node(node, result)
            nodes.append(node.id)
        return nodes

    def _create_resource_nodes(
        self,
        world_state: WorldStateData,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea nodos RESOURCE para monitores y recursos declarados."""
        nodes: List[str] = []
        active_monitor = self._world_state_field(world_state, "active_monitor", None)
        if active_monitor is not None:
            node = Node(
                id="state_active_monitor", type=NodeType.RESOURCE,
                name="Active Monitor", description=f"Monitor activo: {active_monitor}", cost=0.0,
                metadata={"monitor_id": active_monitor, "active": True, "mapping_phase": "6.5.2"},
            )
            self._add_node(node, result)
            nodes.append(node.id)

        for monitor_id in self._safe_iterable(
            self._world_state_field(world_state, "available_monitors", [])
        ):
            if monitor_id is None:
                continue
            safe_monitor = self._safe_id_component(monitor_id)
            node = Node(
                id=f"monitor_{safe_monitor}_available", type=NodeType.RESOURCE,
                name=f"Monitor {monitor_id} Available",
                description=f"Monitor {monitor_id} está disponible", cost=0.0,
                metadata={"monitor_id": monitor_id, "available": True, "mapping_phase": "6.5.2"},
            )
            self._add_node(node, result)
            nodes.append(node.id)

        resources = self._as_dict(self._world_state_field(world_state, "resources", {}))
        for resource_name, resource_value in resources.items():
            safe_name = self._safe_id_component(resource_name)
            node = Node(
                id=f"resource_{safe_name}", type=NodeType.RESOURCE,
                name=str(resource_name), description=f"Recurso disponible: {resource_name}", cost=0.0,
                metadata={
                    "resource": str(resource_name),
                    "value": self._safe_copy(resource_value),
                    "mapping_phase": "6.5.2",
                },
            )
            self._add_node(node, result)
            nodes.append(node.id)
        return self._unique_preserve_order(nodes)

    def _create_calibrated_element_nodes(
        self,
        world_state: WorldStateData,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Crea nodos UI_ELEMENT para elementos calibrados y su monitor."""
        nodes: List[str] = []
        calibrated_elements = self._as_dict(
            self._world_state_field(world_state, "calibrated_elements", {})
        )
        for element_name, element_data in calibrated_elements.items():
            data = self._as_dict(element_data)
            confidence = self._safe_unit_float(data.get("confidence", 0.0))
            safe_name = self._safe_id_component(element_name)
            monitor_id = self._first_present(
                data.get("monitor_id"), data.get("screen_id"), data.get("screen"),
                data.get("monitor"),
            )
            node = Node(
                id=f"calibrated_{safe_name}", type=NodeType.UI_ELEMENT,
                name=f"Calibrated: {element_name}",
                description=f"Elemento UI calibrado: {element_name}", cost=0.0,
                metadata={
                    "element_name": str(element_name),
                    "calibration_data": self._safe_copy(data),
                    "confidence": confidence,
                    "monitor_id": monitor_id,
                    "mapping_phase": "6.5.2",
                },
            )
            self._add_node(node, result)
            nodes.append(node.id)
        return nodes

    # ======================================================================
    # RELACIONES
    # ======================================================================

    def _establish_goal_transitions(
        self,
        goal_node_id: str,
        capability_nodes: Sequence[str],
        specific_nodes: Sequence[str],
        goal: Goal,
        *,
        result: Optional[MappingResult] = None,
    ) -> None:
        """Crea enlaces dirigidos de descomposición sin introducir ciclos."""
        goal_id = self._safe_getattr(goal, "id", "")
        valid_capabilities = [
            node_id for node_id in capability_nodes if self._get_graph_node(node_id) is not None
        ]
        valid_specific = [
            node_id for node_id in specific_nodes if self._get_graph_node(node_id) is not None
        ]

        for capability_node in valid_capabilities:
            self._add_edge(goal_node_id, capability_node, cost=1.0, result=result)

        for specific_node in valid_specific:
            relevant_capability = self._find_relevant_capability(specific_node, goal)
            if relevant_capability and relevant_capability in valid_capabilities:
                self._add_edge(relevant_capability, specific_node, cost=0.5, result=result)
            elif not valid_capabilities:
                self._add_edge(goal_node_id, specific_node, cost=1.0, result=result)
            else:
                # Una acción sin capacidad compatible sigue siendo accesible desde
                # el objetivo, en vez de quedarse aislada.
                self._add_edge(goal_node_id, specific_node, cost=1.0, result=result)

        # Los nodos específicos se crean en orden lógico; conservar la secuencia
        # permite al planificador descubrir el flujo de acciones del mismo objetivo.
        for previous_node, next_node in zip(valid_specific, valid_specific[1:]):
            self._add_edge(previous_node, next_node, cost=0.1, result=result)

        logger.debug("[MAPPER] Relaciones de goal creadas para %s", goal_id)

    def _find_relevant_capability(
        self,
        node_id: str,
        goal: Goal,
    ) -> Optional[str]:
        """Relaciona una acción concreta con la capacidad declarativa adecuada."""
        node = self._get_graph_node(node_id)
        node_name = str(node_id).casefold()
        goal_type = self._normalize_goal_type(self._safe_getattr(goal, "type", ""))
        category = str(self._safe_getattr(node, "action_category", "") or "").casefold()
        metadata = self._safe_getattr(node, "metadata", {})
        if isinstance(metadata, dict) and metadata.get("capability"):
            capability_id = f"capability_{self._safe_id_component(metadata['capability'])}"
            if self._get_graph_node(capability_id) is not None:
                return capability_id

        if "activate_" in node_name or "activate window" in str(self._safe_getattr(node, "name", "")).casefold():
            candidates = ["activate_window", "open_application"]
        elif "close_" in node_name and "close_tab" not in node_name:
            candidates = ["close_application"]
        elif "search" in node_name or category == "search":
            candidates = ["search", "navigate"]
        elif "open_browser" in node_name:
            candidates = ["open_application", "navigate"]
        elif "open_youtube" in node_name or "navigate" in node_name or "browser" in node_name:
            candidates = ["navigate", "open_application"]
        elif category in {"ui", "user_interface"}:
            candidates = ["focus_element", "type_text", "press_key"]
        elif "open_" in node_name or category in {"system", "application"}:
            candidates = ["open_application"]
        elif "focus" in node_name:
            candidates = ["focus_element"]
        elif "type" in node_name:
            candidates = ["type_text"]
        elif "press" in node_name:
            candidates = ["press_key"]
        elif "new_tab" in node_name:
            candidates = ["new_tab"]
        elif "close_tab" in node_name:
            candidates = ["close_tab"]
        else:
            candidates = []

        if goal_type in {"navigate", "navigate_stream", "navigate_to_entity"} and "search" in node_name:
            candidates = ["navigate", "search"]
        for capability in candidates:
            capability_id = f"capability_{capability}"
            if self._get_graph_node(capability_id) is not None:
                return capability_id
        return None

    def _establish_state_transitions(
        self,
        app_nodes: Sequence[str],
        resource_nodes: Sequence[str],
        calibrated_nodes: Sequence[str],
        world_state: Optional[WorldStateData] = None,
        *,
        result: Optional[MappingResult] = None,
    ) -> None:
        """Relaciona estado y recursos solo con identificadores semánticamente asociados."""
        del world_state
        resource_ids = set(resource_nodes)
        for calibrated_node_id in calibrated_nodes:
            node = self._get_graph_node(calibrated_node_id)
            screen_id = self._extract_screen_id(node) if node is not None else None
            if screen_id is None:
                continue
            resource_id = f"monitor_{self._safe_id_component(screen_id)}_available"
            if resource_id in resource_ids:
                self._add_edge(resource_id, calibrated_node_id, cost=0.2, result=result)

        for app_node_id in app_nodes:
            app_node = self._get_graph_node(app_node_id)
            screen_id = self._extract_screen_id(app_node) if app_node is not None else None
            if screen_id is None:
                continue
            resource_id = f"monitor_{self._safe_id_component(screen_id)}_available"
            if resource_id in resource_ids:
                self._add_edge(app_node_id, resource_id, cost=0.1, result=result)

    # ======================================================================
    # CALIDAD
    # ======================================================================

    def _calculate_mapping_quality(
        self,
        goal: Goal,
        created_nodes: Sequence[str],
    ) -> float:
        """Calcula cobertura del mapeo de Goal sin puntuar ejecución."""
        if not created_nodes:
            return 0.0

        required_capabilities = self._get_required_capabilities(goal)
        if not required_capabilities:
            capability_coverage = 1.0
        else:
            covered = sum(
                1
                for capability in required_capabilities
                if self._capability_exists(capability)
            )
            capability_coverage = covered / len(required_capabilities)

        goal_nodes = sum(1 for node_id in created_nodes if node_id.startswith("goal_"))
        action_nodes = sum(
            1 for node_id in created_nodes if self._is_action_node(node_id)
        )

        structure_coverage = min(
            1.0,
            (goal_nodes + action_nodes) / max(1.0, len(created_nodes)),
        )

        return max(
            0.0,
            min(1.0, capability_coverage * 0.7 + structure_coverage * 0.3),
        )

    def _calculate_state_mapping_quality(
        self,
        world_state: WorldStateData,
        created_nodes: Sequence[str],
    ) -> float:
        """Calcula cobertura de los elementos del estado realmente declarados."""
        applications = self._as_dict(self._world_state_field(world_state, "applications", {}))
        monitors = list(self._safe_iterable(self._world_state_field(world_state, "available_monitors", [])))
        calibrated = self._as_dict(self._world_state_field(world_state, "calibrated_elements", {}))
        resources = self._as_dict(self._world_state_field(world_state, "resources", {}))
        active_monitor = self._world_state_field(world_state, "active_monitor", None)
        reserved = {"applications", "active_monitor", "available_monitors", "resources", "calibrated_elements"}
        generic_entries = self._get_generic_state_entries(world_state)
        generic_count = sum(1 for key in generic_entries if key not in reserved)
        expected = len(applications) + len(monitors) + len(calibrated) + len(resources) + generic_count
        if active_monitor is not None:
            expected += 1
        if expected == 0:
            return 1.0

        mapped_ids = set(created_nodes)
        actual = sum(1 for node_id in mapped_ids if node_id.startswith("state_"))
        actual += sum(1 for node_id in mapped_ids if node_id.startswith("monitor_") or node_id.startswith("resource_"))
        actual += sum(1 for node_id in mapped_ids if node_id.startswith("calibrated_"))
        return max(0.0, min(1.0, actual / expected))

    # ======================================================================
    # HELPERS DE GRAFO
    # ======================================================================

    def _add_node(
        self,
        node: Node,
        result: Optional[MappingResult] = None,
    ) -> None:
        """Inserta un nodo solo si falta y registra el nodo usado por el mapeo."""
        node_id = self._safe_getattr(node, "id", None)
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("No se puede mapear un nodo sin id válido")
        existing = self._get_graph_node(node_id)
        if existing is None:
            self.state_graph.add_node(node)
        elif self._safe_getattr(existing, "type", None) != self._safe_getattr(node, "type", None):
            raise ValueError(
                f"Colisión de id '{node_id}': el nodo existente tiene tipo incompatible"
            )
        elif self._safe_getattr(node, "type", None) in {
            NodeType.STATE, NodeType.RESOURCE, NodeType.UI_ELEMENT
        }:
            # Son observaciones del mundo actual: refrescar sus metadatos evita
            # conservar valores antiguos al volver a mapear el estado.
            self.state_graph.add_node(node)
        if result is not None and node_id not in result.created_nodes:
            # Históricamente este campo se utiliza como conjunto de nodos del
            # mapeo, incluidos los que ya estaban en el grafo.
            result.created_nodes.append(node_id)

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        *,
        cost: float = 1.0,
        result: Optional[MappingResult] = None,
    ) -> None:
        """Añade una arista válida y reporta únicamente las transiciones nuevas."""
        if not source_id or not target_id or source_id == target_id:
            return
        if self._get_graph_node(source_id) is None or self._get_graph_node(target_id) is None:
            return
        numeric_cost = self._safe_nonnegative_float(cost, default=float("nan"))
        if not (numeric_cost >= 0.0 and numeric_cost < float("inf")):
            if result is not None:
                result.warnings.append(f"Coste de arista inválido: {source_id} -> {target_id}")
            return

        edge_key = (source_id, target_id)
        if edge_key in self._iter_graph_edges():
            return
        added = self.state_graph.add_edge(source_id, target_id, cost=numeric_cost)
        # Algunos grafos legacy no devuelven bool; comprobamos la fuente canónica
        # después de la llamada en vez de asumir que la transición se añadió.
        exists_after = edge_key in self._iter_graph_edges()
        if exists_after and added is not False and result is not None and edge_key not in result.created_edges:
            result.created_edges.append(edge_key)

    def _get_graph_node(self, node_id: str) -> Optional[Node]:
        try:
            node = self.state_graph.get_node(node_id)
            if isinstance(node, Node):
                return node
            return node
        except AttributeError:
            nodes = self._safe_getattr(self.state_graph, "nodes", {})
            return nodes.get(node_id)
        except Exception:
            return None

    def _iter_graph_edges(self) -> set[Tuple[str, str]]:
        """Devuelve pares fuente/destino desde las representaciones de grafo conocidas."""
        edges = self._safe_getattr(self.state_graph, "edges", {})
        collected: set[Tuple[str, str]] = set()
        if isinstance(edges, dict):
            for key, edge in edges.items():
                if isinstance(key, tuple) and len(key) >= 2:
                    collected.add((str(key[0]), str(key[1])))
                else:
                    source = self._safe_getattr(edge, "source_id", None)
                    target = self._safe_getattr(edge, "target_id", None)
                    if source is not None and target is not None:
                        collected.add((str(source), str(target)))
            return collected
        try:
            for edge in edges or []:
                if isinstance(edge, tuple) and len(edge) >= 2:
                    collected.add((str(edge[0]), str(edge[1])))
                    continue
                source = self._safe_getattr(edge, "source_id", None)
                target = self._safe_getattr(edge, "target_id", None)
                if source is not None and target is not None:
                    collected.add((str(source), str(target)))
        except TypeError:
            logger.debug("La representación de aristas del grafo no es iterable")
        return collected

    # ======================================================================
    # COMPATIBILIDAD / DATOS
    # ======================================================================

    def _update_graph_with_nodes(
        self,
        goal_node: Node,
        capability_nodes: Sequence[str],
        specific_nodes: Sequence[str],
    ) -> None:
        """Compatibilidad: asegura que los nodos indicados están en el grafo."""
        del capability_nodes, specific_nodes
        self._add_node(goal_node)

    def _update_graph_with_state_nodes(
        self,
        app_nodes: Sequence[str],
        resource_nodes: Sequence[str],
        calibrated_nodes: Sequence[str],
    ) -> None:
        """Compatibilidad: los nodos ya se agregan al crearse."""
        del app_nodes, resource_nodes, calibrated_nodes

    def _get_required_capabilities(self, goal: Goal) -> List[str]:
        """Obtiene capacidades declaradas y añade las necesarias por intención."""
        try:
            capabilities = goal.get_required_capabilities()
        except (AttributeError, TypeError):
            capabilities = self._safe_getattr(goal, "required_capabilities", [])
        normalized = [
            str(capability).strip().lower()
            for capability in self._safe_iterable(capabilities)
            if capability is not None and str(capability).strip()
        ]
        goal_type = self._normalize_goal_type(self._safe_getattr(goal, "type", ""))
        if goal_type == "search":
            normalized.append("search")
        return self._unique_preserve_order(normalized)

    def _capability_exists(self, capability: str) -> bool:
        capability_id = f"capability_{str(capability).strip().lower()}"
        return self._get_graph_node(capability_id) is not None

    def _get_goal_metadata(self, goal: Goal) -> Dict[str, Any]:
        metadata = self._safe_getattr(goal, "metadata", {})
        return dict(metadata) if isinstance(metadata, dict) else {}

    def _get_goal_base_cost(self, goal: Goal) -> float:
        """Devuelve un coste finito y no negativo para representar el objetivo."""
        metadata = self._get_goal_metadata(goal)
        return self._safe_nonnegative_float(metadata.get("base_cost", 10.0), default=10.0)

    def _get_goal_name(self, goal: Goal, goal_type: str) -> str:
        """Devuelve un nombre legible aun cuando Goal no incluya el campo name."""
        name = self._safe_getattr(goal, "name", None)
        if name:
            return str(name)
        description = self._safe_getattr(goal, "description", None)
        if description:
            return str(description)
        return f"Goal: {goal_type}"

    def _get_state_value(self, app_info: Any) -> str:
        """Normaliza el estado de aplicación cuando llega como enum, objeto o dict."""
        state = self._read_field(app_info, "state", "unknown")
        value = self._read_field(state, "value", state)
        if value is None or not str(value).strip():
            return "unknown"
        return self._safe_id_component(value)

    def _extract_screen_id(self, node: Any) -> Optional[Any]:
        """Busca identificadores de monitor en los metadatos del nodo."""
        metadata = self._safe_getattr(node, "metadata", {})
        if not isinstance(metadata, dict):
            return None
        for key in ("monitor_id", "monitor", "screen_id", "screen", "screen_number"):
            if metadata.get(key) is not None:
                return metadata[key]
        calibration = metadata.get("calibration_data")
        if isinstance(calibration, dict):
            for key in ("monitor_id", "monitor", "screen_id", "screen", "screen_number"):
                if calibration.get(key) is not None:
                    return calibration[key]
        return None

    def _is_action_node(self, node_id: str) -> bool:
        node = self._get_graph_node(node_id)
        if node is None:
            return False
        node_type = self._safe_getattr(node, "type", None)
        return node_type == NodeType.ACTION

    # ======================================================================
    # UTILIDADES
    # ======================================================================

    @staticmethod
    def _unique_preserve_order(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    def _unique_edges(values: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
        seen: set[Tuple[str, str]] = set()
        result: List[Tuple[str, str]] = []
        for source_id, target_id in values:
            edge = (source_id, target_id)
            if edge in seen:
                continue
            seen.add(edge)
            result.append(edge)
        return result

    def _record_history(
        self,
        *,
        operation: str,
        result: MappingResult,
        goal_id: Optional[str] = None,
    ) -> None:
        self.mapping_history.append(
            {
                "timestamp": time.time(),
                "operation": operation,
                "goal_id": goal_id,
                "mapping_type": result.mapping_type.value,
                "created_nodes": list(result.created_nodes),
                "created_edges": list(result.created_edges),
                "quality": result.mapping_quality,
                "warnings": list(result.warnings),
                "execution_time": result.execution_time,
            }
        )

    def _update_last_history_execution_time(self, result: MappingResult) -> None:
        """Actualiza un registro coincidente sin corromper operaciones anteriores."""
        for entry in reversed(self.mapping_history):
            if (
                entry.get("mapping_type") == result.mapping_type.value
                and entry.get("created_nodes") == list(result.created_nodes)
                and entry.get("created_edges") == list(result.created_edges)
            ):
                entry["execution_time"] = result.execution_time
                entry["quality"] = result.mapping_quality
                entry["warnings"] = list(result.warnings)
                return

    @staticmethod
    def _safe_getattr(obj: Any, attribute: str, default: Any = None) -> Any:
        """Lee atributos o claves de diccionario sin propagar errores externos."""
        try:
            if isinstance(obj, dict):
                return obj.get(attribute, default)
            return getattr(obj, attribute)
        except Exception:
            return default

    @staticmethod
    def _get_required_id(obj: Any, kind: str) -> str:
        """Valida y normaliza el identificador requerido para un objeto."""
        value = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", None)
        if value is None or not str(value).strip():
            raise ValueError(f"{kind} debe tener un id válido")
        return str(value).strip()

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _safe_iterable(value: Any) -> List[Any]:
        """Convierte valores iterables a lista sin dividir cadenas en caracteres."""
        if value is None:
            return []
        if isinstance(value, (str, bytes, bytearray)):
            return [value]
        if isinstance(value, dict):
            return list(value.values())
        try:
            return list(value)
        except (TypeError, ValueError):
            return [value]

    @staticmethod
    def _normalize_target_name(value: Any) -> str:
        """Extrae un nombre de aplicación razonable de cadenas o targets estructurados."""
        if isinstance(value, dict):
            for key in ("app_name", "application", "program", "name", "title"):
                candidate = value.get(key)
                if candidate is not None and str(candidate).strip():
                    return str(candidate).strip()
            return "application"
        text = str(value).strip() if value is not None else ""
        return text or "application"

    @staticmethod
    def _safe_id_component(value: Any) -> str:
        text = str(value).strip().lower()
        cleaned = "".join(
            char if char.isalnum() or char in {"_", "-"} else "_" for char in text
        )
        cleaned = cleaned.strip("_")
        return cleaned or "unknown"


    def _create_generic_state_nodes(
        self,
        world_state: Any,
        *,
        result: Optional[MappingResult] = None,
    ) -> List[str]:
        """Representa hechos libres del estado canónico que no son colecciones."""
        nodes: List[str] = []
        reserved = {"applications", "active_monitor", "available_monitors", "resources", "calibrated_elements"}
        for key, value in self._get_generic_state_entries(world_state).items():
            if key in reserved:
                continue
            safe_key = self._safe_id_component(key)
            node = Node(
                id=f"state_fact_{safe_key}",
                type=NodeType.STATE,
                name=f"World State: {key}",
                description=f"Hecho del estado del mundo: {key}",
                cost=0.0,
                metadata={
                    "state_key": str(key),
                    "value": self._safe_copy(value),
                    "mapping_phase": "6.5.2",
                },
            )
            self._add_node(node, result)
            nodes.append(node.id)
        return self._unique_preserve_order(nodes)

    def _get_generic_state_entries(self, world_state: Any) -> Dict[str, Any]:
        """Obtiene el diccionario de hechos del WorldState canónico, si existe."""
        if isinstance(world_state, dict):
            payload = world_state.get("state", world_state)
            return payload if isinstance(payload, dict) else {}
        payload = self._safe_getattr(world_state, "state", {})
        return payload if isinstance(payload, dict) else {}

    def _world_state_field(self, world_state: Any, key: str, default: Any = None) -> Any:
        """Lee primero modelos legacy con atributos y luego WorldState.state."""
        direct = self._safe_getattr(world_state, key, None)
        payload = self._get_generic_state_entries(world_state)
        if direct is not None:
            if isinstance(direct, (dict, list, tuple, set)) and not direct and key in payload:
                return payload[key]
            return direct
        return payload.get(key, default)

    def _get_goal_target_value(
        self,
        goal: Any,
        target_keys: Sequence[str],
        *,
        fallback_keys: Sequence[str] = (),
    ) -> Any:
        """Extrae datos de Goal.target (str/dict) y de metadata sin perder contexto."""
        target = self._safe_getattr(goal, "target", None)
        if isinstance(target, dict):
            for key in target_keys:
                value = target.get(key)
                if value is not None and (not isinstance(value, str) or value.strip()):
                    return value
        elif target is not None and not isinstance(target, (dict, list, tuple, set)):
            if not isinstance(target, str) or target.strip():
                return target
        metadata = self._get_goal_metadata(goal)
        for key in fallback_keys:
            value = metadata.get(key)
            if value is not None and (not isinstance(value, str) or value.strip()):
                return value
        if isinstance(target, dict):
            for value in target.values():
                if value is not None and (not isinstance(value, str) or value.strip()):
                    return value
        return None

    @staticmethod
    def _normalize_goal_type(value: Any) -> str:
        """Normaliza tipos de goal que puedan llegar como Enum o texto."""
        if isinstance(value, Enum):
            value = value.value
        return str(value or "").strip().lower().replace(" ", "_")

    @staticmethod
    def _read_field(value: Any, key: str, default: Any = None) -> Any:
        """Lee una clave en dict o atributo en objeto."""
        if isinstance(value, dict):
            return value.get(key, default)
        try:
            return getattr(value, key)
        except Exception:
            return default

    @staticmethod
    def _first_present(*values: Any) -> Any:
        """Retorna el primer valor no nulo/no vacío."""
        for value in values:
            if value is not None and (not isinstance(value, str) or value.strip()):
                return value
        return None

    @staticmethod
    def _safe_copy(value: Any) -> Any:
        """Copia datos de metadatos con fallback cuando un objeto no se puede copiar."""
        try:
            return copy.deepcopy(value)
        except Exception:
            try:
                return copy.copy(value)
            except Exception:
                return repr(value)

    @staticmethod
    def _safe_nonnegative_float(value: Any, default: float = 0.0) -> float:
        """Convierte a float finito no negativo."""
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if numeric != numeric or numeric in (float("inf"), float("-inf")) or numeric < 0:
            return default
        return numeric

    @classmethod
    def _safe_unit_float(cls, value: Any) -> float:
        """Normaliza una confianza al intervalo [0, 1]."""
        return max(0.0, min(1.0, cls._safe_nonnegative_float(value, default=0.0)))

    @staticmethod
    def _normalize_conditions(value: Any) -> List[Any]:
        """Normaliza condiciones preservando dicts y cadenas como elementos únicos."""
        if value is None:
            return []
        if isinstance(value, list):
            return copy.deepcopy(value)
        if isinstance(value, (tuple, set, frozenset)):
            return copy.deepcopy(list(value))
        return [copy.deepcopy(value)]

__all__ = [
    "GoalStateMapper",
    "MappingResult",
    "MappingType",
]
