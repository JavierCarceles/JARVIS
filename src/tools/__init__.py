"""
Paquete de herramientas de Jarvis.

Expone las clases y funciones principales del sistema de ejecucion y registro
de acciones para facilitar sus imports desde otros modulos.
"""

from src.tools.executor import UnifiedExecutor, get_executor, process_and_execute
from src.tools.registry import ActionInfo, ActionRegistry, ActionType, get_action, get_action_registry, get_available_actions, register_action

__all__ = [
    "ActionInfo",
    "ActionRegistry",
    "ActionType",
    "UnifiedExecutor",
    "get_action",
    "get_action_registry",
    "get_available_actions",
    "get_executor",
    "process_and_execute",
    "register_action",
]
