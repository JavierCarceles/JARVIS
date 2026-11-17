# src/memory/__init__.py
"""
Modulo de memoria mejorado para soportar planificacion jerarquica.

Este modulo proporciona:
- Separacion de memoria conversacional y conocimiento permanente
- Gestion de entidades de dominio
- Estado del mundo explicito
- Soporte para planificacion jerarquica (FASE 5)
"""

from src.memory.storage import MemoryType, Entity, ConversationalMemory, MemoryManager, JSONStorage, get_memory_manager, save_entity, get_entity, get_entities_by_type, add_conversational_memory, get_world_state, update_world_state, resolve_entity_to_url, get_entity_attributes, create_goal_from_entity, verify_entity_integrity

# Sistema de resolucion de entidades (SUBFASE 5.2)
from src.memory.entity_resolver import EntityResolver, EntityResolutionResult, ResolutionContext, entity_resolver

# Mantener compatibilidad con el sistema existente
try:
    from src.memory.conversation import ConversationMemory as Memory
except ImportError:
    Memory = None

try:
    from src.memory.storage import JSONStorage as Storage
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
    # Funciones especificas para SUBFASE 5.1
    'resolve_entity_to_url',
    'get_entity_attributes',
    'create_goal_from_entity',
    'verify_entity_integrity',
    # Sistema de resolucion de entidades (SUBFASE 5.2)
    'EntityResolver',
    'EntityResolutionResult',
    'ResolutionContext',
    'entity_resolver',
    # Compatibilidad con sistema existente
    'Memory',
    'Storage'
]