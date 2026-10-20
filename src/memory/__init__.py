# src/memory/__init__.py
"""
Módulo de memoria mejorado para soportar planificación jerárquica.

Este módulo proporciona:
- Separación de memoria conversacional y conocimiento permanente
- Gestión de entidades de dominio
- Estado del mundo explícito
- Soporte para planificación jerárquica (FASE 5)
"""

from .storage import (
    MemoryType,
    Entity,
    ConversationalMemory,
    MemoryManager,
    JSONStorage,
    get_memory_manager,
    save_entity,
    get_entity,
    get_entities_by_type,
    add_conversational_memory,
    get_world_state,
    update_world_state,
    # Funciones específicas para SUBFASE 5.1
    resolve_entity_to_url,
    get_entity_attributes,
    create_goal_from_entity,
    verify_entity_integrity
)

# Sistema de resolución de entidades (SUBFASE 5.2)
from .entity_resolver import (
    EntityResolver,
    EntityResolutionResult,
    ResolutionContext,
    entity_resolver
)

# Mantener compatibilidad con el sistema existente
try:
    from .conversation import ConversationMemory as Memory
except ImportError:
    Memory = None

try:
    from .storage import JSONStorage as Storage
except ImportError:
    Storage = None

__all__ = [
    # Nuevas clases mejoradas
    'MemoryType',
    'Entity', 
    'ConversationalMemory',
    'MemoryManager',
    'JSONStorage',
    'get_memory_manager',
    'save_entity',
    'get_entity', 
    'get_entities_by_type',
    'add_conversational_memory',
    'get_world_state',
    'update_world_state',
    # Funciones específicas para SUBFASE 5.1
    'resolve_entity_to_url',
    'get_entity_attributes',
    'create_goal_from_entity',
    'verify_entity_integrity',
    # Sistema de resolución de entidades (SUBFASE 5.2)
    'EntityResolver',
    'EntityResolutionResult',
    'ResolutionContext',
    'entity_resolver',
    # Compatibilidad con sistema existente
    'Memory',
    'Storage'
]