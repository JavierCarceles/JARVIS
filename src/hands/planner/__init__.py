"""Módulo de planificación de JARVIS.

El paquete evita inicializar componentes pesados durante la importación para
prevenir ciclos entre ``action_registry`` y los módulos del planner.
Los componentes principales se resuelven de forma perezosa cuando se solicitan.

Las funciones ``get_*`` delegan en los singletons definidos por cada módulo.
Así se evita mantener una segunda caché a nivel de paquete que pueda divergir
de la instancia real del componente.
"""

from __future__ import annotations

from .node import Goal, Node, NodeType, Task, TaskStatus


def get_htn_manager():
    """Obtiene la instancia global del HTN Manager mediante importación perezosa."""
    from .htn_manager import get_htn_manager as _get_htn_manager

    return _get_htn_manager()


def get_application_knowledge_integrator():
    """Obtiene la instancia global del integrador de conocimiento de aplicaciones."""
    from .application_integration import (
        get_application_knowledge_integrator as _get_integrator,
    )

    return _get_integrator()


def get_task_executor():
    """Obtiene la instancia global del TaskExecutor mediante importación perezosa."""
    from .task_executor import get_task_executor as _get_task_executor

    return _get_task_executor()


def __getattr__(name: str):
    """Carga componentes pesados del planner solo cuando se solicitan."""
    if name in {"StateGraph", "GraphNode", "GraphEdge", "GraphBuilder"}:
        from .graph import GraphBuilder, GraphEdge, GraphNode, StateGraph

        return {
            "StateGraph": StateGraph,
            "GraphNode": GraphNode,
            "GraphEdge": GraphEdge,
            "GraphBuilder": GraphBuilder,
        }[name]

    if name == "HTNManager":
        from .htn_manager import HTNManager

        return HTNManager

    if name == "TaskExecutor":
        from .task_executor import TaskExecutor

        return TaskExecutor

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Expone también los nombres disponibles mediante carga perezosa."""
    return sorted(
        set(globals())
        | {
            "StateGraph",
            "GraphNode",
            "GraphEdge",
            "GraphBuilder",
            "HTNManager",
            "TaskExecutor",
        }
    )


__all__ = [
    "Node",
    "Goal",
    "Task",
    "NodeType",
    "TaskStatus",
    "StateGraph",
    "GraphNode",
    "GraphEdge",
    "GraphBuilder",
    "HTNManager",
    "get_htn_manager",
    "TaskExecutor",
    "get_task_executor",
    "get_application_knowledge_integrator",
]
