"""
Paquete de herramientas de Jarvis.

Expone las clases y funciones principales del sistema de ejecución y registro
de acciones para facilitar sus imports desde otros módulos.
"""

from .executor import UnifiedExecutor, get_executor, process_and_execute
from .registry import (
    ActionInfo,
    ActionRegistry,
    ActionType,
    get_action,
    get_action_registry,
    get_available_actions,
    register_action,
)

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
