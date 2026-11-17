"""Paquete de planificacion de JARVIS.

El modelo canonico ``node`` se importa de forma directa porque contiene los
contratos de datos ligeros. Los demas subsistemas se exponen mediante carga
perezosa para evitar ciclos de importacion con ``action_registry``, ejecucion,
memoria y optimizacion.

Las funciones ``get_*`` delegan en los singletons de cada modulo; el paquete no
mantiene copias de esos singletons.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from src.hands.planner.node import Goal, Node, NodeType, Task, TaskStatus, WorldState, create_action_node, create_application_node, create_condition_node, create_state_node


# nombre publico -> (modulo relativo, atributo exportado).
# No se importan estos modulos hasta que se solicita uno de sus nombres.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # Grafo de estados y busqueda.
    "SearchStrategy": (".graph", "SearchStrategy"),
    "RouteResult": (".graph", "RouteResult"),
    "GraphNode": (".graph", "GraphNode"),
    "GraphEdge": (".graph", "GraphEdge"),
    "StateGraph": (".graph", "StateGraph"),
    "GraphBuilder": (".graph", "GraphBuilder"),
    "CacheEntry": (".graph", "CacheEntry"),
    "PerformanceMetrics": (".graph", "PerformanceMetrics"),
    "AdvancedStateGraph": (".graph", "AdvancedStateGraph"),
    # Heuristicas.
    "HeuristicType": (".heuristic", "HeuristicType"),
    "Heuristic": (".heuristic", "Heuristic"),
    "HeuristicFactory": (".heuristic", "HeuristicFactory"),
    # Planificador principal.
    "Planner": (".planner", "Planner"),
    "PlanningResult": (".planner", "PlanningResult"),
    "PlannerStatus": (".planner", "PlannerStatus"),
    "PlanQuality": (".planner", "PlanQuality"),
    # Integracion de planificacion mediante grafo.
    "IntegrationMode": (".planner_integration", "IntegrationMode"),
    "GraphPlanningResult": (".planner_integration", "GraphPlanningResult"),
    "GraphPlannerIntegration": (".planner_integration", "GraphPlannerIntegration"),
    # Mapeo Goal / World State.
    "MappingType": (".goal_state_mapper", "MappingType"),
    "MappingResult": (".goal_state_mapper", "MappingResult"),
    "GoalStateMapper": (".goal_state_mapper", "GoalStateMapper"),
    # HTN.
    "HTNManager": (".htn_manager", "HTNManager"),
    "HTNStatus": (".htn_manager", "HTNStatus"),
    "TaskDecompositionStrategy": (".htn_manager", "TaskDecompositionStrategy"),
    "TaskExecutionResult": (".htn_manager", "TaskExecutionResult"),
    "HTNDecompositionRule": (".htn_manager", "HTNDecompositionRule"),
    # Conocimiento de aplicaciones.
    "ApplicationKnowledgeIntegrator": (
        ".application_integration",
        "ApplicationKnowledgeIntegrator",
    ),
    # Ejecutor de tareas.
    "TaskExecutor": (".task_executor", "TaskExecutor"),
    "TaskExecutorStatus": (".task_executor", "TaskExecutorStatus"),
    "TaskExecutionMode": (".task_executor", "TaskExecutionMode"),
    "TaskExecutionConfig": (".task_executor", "TaskExecutionConfig"),
    # Aprendizaje.
    "LearningEventType": (".learning_system", "LearningEventType"),
    "LearningEvent": (".learning_system", "LearningEvent"),
    "LearningStatistics": (".learning_system", "LearningStatistics"),
    "LearningSystem": (".learning_system", "LearningSystem"),
    # Optimizacion.
    "OptimizationType": (".optimization", "OptimizationType"),
    "RouteCacheEntry": (".optimization", "RouteCacheEntry"),
    "CostLearningData": (".optimization", "CostLearningData"),
    "ContextData": (".optimization", "ContextData"),
    "OptimizationManager": (".optimization", "OptimizationManager"),
    # Configuracion de optimizacion.
    "OptimizationMode": (".optimization_config", "OptimizationMode"),
    "RouteCacheConfig": (".optimization_config", "RouteCacheConfig"),
    "CostLearningConfig": (".optimization_config", "CostLearningConfig"),
    "RedundancyRemovalConfig": (".optimization_config", "RedundancyRemovalConfig"),
    "ContextAwareConfig": (".optimization_config", "ContextAwareConfig"),
    "AlternativeSelectionConfig": (".optimization_config", "AlternativeSelectionConfig"),
    "PerformanceMonitoringConfig": (".optimization_config", "PerformanceMonitoringConfig"),
    "OptimizationConfig": (".optimization_config", "OptimizationConfig"),
    # Precondiciones y efectos.
    "PreconditionsEffectsManager": (".preconditions_effects", "PreconditionsEffectsManager"),
    "create_application_open_condition": (
        ".preconditions_effects",
        "create_application_open_condition",
    ),
    "create_application_active_condition": (
        ".preconditions_effects",
        "create_application_active_condition",
    ),
    "create_ui_element_calibrated_condition": (
        ".preconditions_effects",
        "create_ui_element_calibrated_condition",
    ),
    "create_application_open_effect": (
        ".preconditions_effects",
        "create_application_open_effect",
    ),
    "create_ui_element_calibrate_effect": (
        ".preconditions_effects",
        "create_ui_element_calibrate_effect",
    ),
    "ConditionType": (".preconditions_effects_types", "ConditionType"),
    "Condition": (".preconditions_effects_types", "Condition"),
    "Effect": (".preconditions_effects_types", "Effect"),
    "State": (".preconditions_effects_types", "State"),
    "ConditionFunction": (".preconditions_effects_types", "ConditionFunction"),
    "EffectFunction": (".preconditions_effects_types", "EffectFunction"),
}


def get_htn_manager() -> Any:
    """Obtiene el singleton HTN sin importar el gestor al cargar el paquete."""
    from src.hands.planner.htn_manager import get_htn_manager as getter

    return getter()


def get_application_knowledge_integrator() -> Any:
    """Obtiene el singleton del integrador de aplicaciones."""
    from src.hands.planner.application_integration import get_application_knowledge_integrator as getter

    return getter()


def get_applications_by_capability(capability_name: str) -> list[str]:
    """Busca aplicaciones por capacidad mediante el modulo correspondiente."""
    from src.hands.planner.application_integration import get_applications_by_capability as getter

    return getter(capability_name)


def get_application_knowledge(app_name: str) -> dict[str, Any]:
    """Obtiene las capacidades declaradas de una aplicacion."""
    from src.hands.planner.application_integration import get_application_knowledge as getter

    return getter(app_name)


def get_task_executor() -> Any:
    """Obtiene el singleton TaskExecutor mediante importacion diferida."""
    from src.hands.planner.task_executor import get_task_executor as getter

    return getter()


def get_learning_system() -> Any:
    """Obtiene el singleton del sistema de aprendizaje cuando se necesita."""
    from src.hands.planner.learning_system import get_learning_system as getter

    return getter()


def get_preconditions_effects_manager() -> Any:
    """Obtiene el singleton del gestor de precondiciones y efectos."""
    from src.hands.planner.preconditions_effects import get_preconditions_effects_manager as getter

    return getter()


def __getattr__(name: str) -> Any:
    """Carga un componente bajo demanda y conserva el atributo en el paquete."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    module = import_module(module_name, package=__name__)
    try:
        value = getattr(module, attribute_name)
    except AttributeError as exc:
        raise AttributeError(
            f"El modulo {module.__name__!r} no exporta {attribute_name!r} "
            f"(solicitado como {name!r})"
        ) from exc

    # Cachea el atributo una vez resuelto; la resolucion en si sigue siendo lazy.
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Incluye los componentes de carga perezosa en dir(paquete)."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


# Exportaciones estables para ``from ... import *``. El resto de los componentes
# siguen disponibles por acceso explicito (p. ej. ``from .planner import Planner``
# o ``from . import Planner``), sin forzar la carga de todos los subsistemas con
# una importacion global del paquete.
__all__ = [
    # Modelo canonico ligero.
    "Node",
    "Goal",
    "Task",
    "WorldState",
    "NodeType",
    "TaskStatus",
    "create_action_node",
    "create_application_node",
    "create_state_node",
    "create_condition_node",
    # Compatibilidad publica del paquete y grafo.
    "StateGraph",
    "GraphNode",
    "GraphEdge",
    "GraphBuilder",
    "SearchStrategy",
    "PerformanceMetrics",
    "AdvancedStateGraph",
    # Singletons y ejecutores centrales.
    "HTNManager",
    "get_htn_manager",
    "TaskExecutor",
    "get_task_executor",
    "get_application_knowledge_integrator",
]
