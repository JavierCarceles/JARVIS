# src/memory/storage.py
"""
Sistema de almacenamiento mejorado para soportar planificación jerárquica.

Implementa:
- FASE 3: Estado del mundo con tipos específicos
- FASE 5: Memoria de dominio avanzada con entidades y relaciones
- FASE 6-7: Soporte para planes y ejecuciones
- FASE 18: Estadísticas de aprendizaje para optimización
- Manejo avanzado de caché para rendimiento
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict, Optional, Union, Tuple
from enum import Enum
from dataclasses import dataclass, asdict, field
from abc import ABC, abstractmethod
from collections import defaultdict
import threading

from src.utils.logger import get_logger
from src.utils.config import get_project_root

logger = get_logger(__name__)

class MemoryType(Enum):
    """Tipos de memoria en el sistema mejorado."""

    CONVERSATIONAL = "conversational"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    ENTITIES = "entities"
    APPLICATIONS = "applications"
    STATE = "state"
    PLANS = "plans"
    EXECUTIONS = "executions"
    LEARNING_STATS = "learning_stats"
    RELATIONSHIPS = "relationships"
    PREFERENCES = "preferences"


@dataclass
class Entity:
    """Entidad mejorada para memoria de dominio (FASE 5)."""

    id: str
    type: str
    name: str
    properties: Dict[str, Any]
    created_at: str
    updated_at: str
    metadata: Optional[Dict[str, Any]] = None
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        data = asdict(self)
        data["created_at"] = self.created_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        """Crea desde diccionario."""
        data = data.copy()
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
        if "updated_at" not in data:
            data["updated_at"] = datetime.now().isoformat()
        if "aliases" not in data:
            data["aliases"] = []
        if "confidence" not in data:
            data["confidence"] = 1.0
        if "tags" not in data:
            data["tags"] = []
        return cls(**data)

    def matches_query(self, query: str) -> bool:
        """Verifica si la entidad coincide con una búsqueda."""
        query_lower = query.lower()
        return (
            query_lower in self.name.lower()
            or any(query_lower in alias.lower() for alias in self.aliases)
            or any(query_lower in tag.lower() for tag in self.tags)
            or any(query_lower in str(v).lower() for v in self.properties.values())
        )


@dataclass
class ConversationalMemory:
    """Memoria conversacional mejorada."""

    id: str
    message: str
    response: str
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    intent: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    confidence: float = 1.0
    execution_time: float = 0.0
    success: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationalMemory":
        """Crea desde diccionario."""
        data = data.copy()
        if "entities" not in data:
            data["entities"] = []
        return cls(**data)


@dataclass
class WorldState:
    """Estado del mundo mejorado (FASE 3)."""

    timestamp: float
    applications: Dict[str, Dict[str, Any]]
    ui_elements: Dict[str, Dict[str, Any]]
    system_info: Dict[str, Any]
    constraints: List[str]
    last_actions: List[str]
    active_goals: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        """Crea desde diccionario."""
        return cls(**data)

    def get_application_state(self, app_name: str) -> Dict[str, Any]:
        """Obtiene el estado de una aplicación específica."""
        return self.applications.get(app_name, {})

    def get_ui_element_state(self, element_name: str) -> Dict[str, Any]:
        """Obtiene el estado de un elemento UI específico."""
        return self.ui_elements.get(element_name, {})


@dataclass
class Plan:
    """Plan de ejecución (FASE 6-7)."""

    id: str
    goal: str
    nodes: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    status: str = "pending"
    execution_time: float = 0.0
    success: Optional[bool] = None
    cost: float = 0.0
    heuristic_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        data = asdict(self)
        data["created_at"] = self.created_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        """Crea desde diccionario."""
        data = data.copy()
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
        if "updated_at" not in data:
            data["updated_at"] = datetime.now().isoformat()
        if "nodes" not in data:
            data["nodes"] = []
        return cls(**data)


@dataclass
class ExecutionRecord:
    """Registro de ejecución para aprendizaje (FASE 18)."""

    id: str
    plan_id: str
    action_name: str
    parameters: Dict[str, Any]
    start_time: str
    end_time: str
    success: bool
    execution_time: float
    error: Optional[str] = None
    retries: int = 0
    alternatives_tried: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        """Crea desde diccionario."""
        data = data.copy()
        if "alternatives_tried" not in data:
            data["alternatives_tried"] = []
        if "context" not in data:
            data["context"] = {}
        return cls(**data)


@dataclass
class LearningStat:
    """Estadística de aprendizaje (FASE 18)."""

    action_name: str
    total_executions: int = 0
    successful_executions: int = 0
    average_execution_time: float = 0.0
    success_rate: float = 0.0
    last_updated: str = ""

    def update(self, success: bool, execution_time: float) -> None:
        """Actualiza estadísticas con nueva ejecución."""
        self.total_executions += 1

        if success:
            self.successful_executions += 1

        if self.total_executions == 1:
            self.average_execution_time = execution_time
        else:
            self.average_execution_time = (
                self.average_execution_time * (self.total_executions - 1)
                + execution_time
            ) / self.total_executions

        self.success_rate = (
            self.successful_executions / self.total_executions
            if self.total_executions > 0
            else 0.0
        )

        self.last_updated = datetime.now().isoformat()


@dataclass
class UserPreference:
    """Preferencia de usuario (SUBFASE 5.4)."""

    user_id: str
    preference_type: str
    preference_key: str
    preference_value: Any
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    context: Optional[Dict[str, Any]] = None
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        data = asdict(self)
        data["created_at"] = self.created_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreference":
        """Crea desde diccionario."""
        data = data.copy()
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
        if "updated_at" not in data:
            data["updated_at"] = datetime.now().isoformat()
        if "context" not in data:
            data["context"] = {}
        if "usage_count" not in data:
            data["usage_count"] = 0
        return cls(**data)


@dataclass
class EntityAttribute:
    """Atributo extendido de entidad (SUBFASE 5.4)."""

    entity_id: str
    attribute_name: str
    attribute_value: Any
    attribute_type: str = "string"
    source: str = "system"
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        data = asdict(self)
        data["created_at"] = self.created_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityAttribute":
        """Crea desde diccionario."""
        data = data.copy()
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
        if "updated_at" not in data:
            data["updated_at"] = datetime.now().isoformat()
        if "metadata" not in data:
            data["metadata"] = {}
        return cls(**data)


class MemoryStorage(ABC):
    """Interfaz abstracta para almacenamiento de memoria."""

    @abstractmethod
    def save(self, data: Any, memory_type: MemoryType) -> bool:
        """Guarda datos."""
        pass

    @abstractmethod
    def load(self, memory_type: MemoryType) -> Any:
        """Carga datos."""
        pass

    @abstractmethod
    def exists(self, memory_type: MemoryType) -> bool:
        """Verifica si existe."""
        pass


class JSONStorage(MemoryStorage):
    """Almacenamiento en archivos JSON con manejo avanzado."""

    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path)

        if self.base_path.is_file():
            self.base_path = self.base_path.parent

        self.base_path.mkdir(parents=True, exist_ok=True)

        self.file_mapping = {
            MemoryType.CONVERSATIONAL: "conversational_memory.json",
            MemoryType.DOMAIN_KNOWLEDGE: "domain_knowledge.json",
            MemoryType.ENTITIES: "entities.json",
            MemoryType.APPLICATIONS: "applications.json",
            MemoryType.STATE: "world_state.json",
            MemoryType.PLANS: "plans.json",
            MemoryType.EXECUTIONS: "executions.json",
            MemoryType.LEARNING_STATS: "learning_stats.json",
            MemoryType.RELATIONSHIPS: "relationships.json",
            MemoryType.PREFERENCES: "user_preferences.json",
        }

    def get_file_path(self, memory_type: MemoryType) -> Path:
        """Obtiene la ruta del archivo para un tipo de memoria."""
        return self.base_path / self.file_mapping[memory_type]

    def save(self, data: Any, memory_type: MemoryType) -> bool:
        """Guarda datos en archivo JSON con manejo inteligente."""
        try:
            file_path = self.get_file_path(memory_type)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            existing_data = self._load_existing_data(file_path)
            processed_data = self._process_data_for_save(
                data,
                existing_data,
                memory_type,
            )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    processed_data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )

            return True

        except Exception as e:
            logger._print_log(
                "error",
                f"Error guardando {memory_type.value} en {file_path}: {e}",
                "storage.py", "save", 396,
            )
            return False

    def _load_existing_data(self, file_path: Path) -> Any:
        """Carga datos existentes del archivo."""
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def _process_data_for_save(
        self,
        new_data: Any,
        existing_data: Any,
        memory_type: MemoryType,
    ) -> Any:
        """Procesa datos según el tipo de memoria."""
        if memory_type == MemoryType.CONVERSATIONAL:
            if not isinstance(existing_data, list):
                existing_data = []

            if isinstance(new_data, ConversationalMemory):
                existing_data.append(new_data.to_dict())

            elif isinstance(new_data, list):
                existing_data.extend(
                    [
                        item.to_dict()
                        if isinstance(item, ConversationalMemory)
                        else item
                        for item in new_data
                    ]
                )

            return existing_data

        elif memory_type == MemoryType.ENTITIES:
            if not isinstance(existing_data, list):
                existing_data = []

            if isinstance(new_data, Entity):
                existing = next(
                    (
                        e
                        for e in existing_data
                        if isinstance(e, dict) and e.get("id") == new_data.id
                    ),
                    None,
                )

                if existing:
                    existing_data.remove(existing)

                existing_data.append(new_data.to_dict())

            elif isinstance(new_data, list):
                for item in new_data:
                    if isinstance(item, Entity):
                        existing = next(
                            (
                                e
                                for e in existing_data
                                if isinstance(e, dict) and e.get("id") == item.id
                            ),
                            None,
                        )

                        if existing:
                            existing_data.remove(existing)

                        existing_data.append(item.to_dict())

            return existing_data

        elif memory_type == MemoryType.EXECUTIONS:
            if not isinstance(existing_data, list):
                existing_data = []

            if isinstance(new_data, ExecutionRecord):
                existing_data.append(new_data.to_dict())

            elif isinstance(new_data, list):
                existing_data.extend(
                    [
                        item.to_dict() if isinstance(item, ExecutionRecord) else item
                        for item in new_data
                    ]
                )

            return existing_data

        elif memory_type == MemoryType.LEARNING_STATS:
            if not isinstance(existing_data, dict):
                existing_data = {}

            if isinstance(new_data, LearningStat):
                existing_data[new_data.action_name] = new_data.__dict__

            elif isinstance(new_data, dict):
                existing_data.update(new_data)

            return existing_data

        elif memory_type == MemoryType.PREFERENCES:
            if not isinstance(existing_data, dict):
                existing_data = {}

            if isinstance(new_data, UserPreference):
                key = (
                    f"{new_data.user_id}_"
                    f"{new_data.preference_type}_"
                    f"{new_data.preference_key}"
                )
                existing_data[key] = new_data.to_dict()

            elif isinstance(new_data, dict):
                existing_data.update(new_data)

            return existing_data

        elif memory_type == MemoryType.RELATIONSHIPS:
            if not isinstance(existing_data, dict):
                existing_data = {}

            if isinstance(new_data, EntityAttribute):
                key = f"attr_{new_data.entity_id}_{new_data.attribute_name}"
                existing_data[key] = new_data.to_dict()

            elif isinstance(new_data, dict):
                existing_data.update(new_data)

            return existing_data

        else:
            return new_data if new_data is not None else existing_data

    def load(self, memory_type: MemoryType) -> Any:
        """Carga datos desde archivo JSON."""
        try:
            file_path = self.get_file_path(memory_type)

            if not file_path.exists():
                logger._print_log(
                    "info",
                    f"Archivo no existe, usando valor por defecto para "
                    f"{memory_type.value}",
                    "storage.py", "load", 542,
                )
                return self._get_default_value(memory_type)

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return data

        except json.JSONDecodeError as e:
            logger._print_log(
                "warning",
                f"JSON invalido en {file_path} para {memory_type.value}: "
                f"{e}. Usando valor por defecto.",
                "storage.py", "load", 552,
            )
            return self._get_default_value(memory_type)

        except Exception as e:
            logger._print_log(
                "error",
                f"Error inesperado cargando {memory_type.value} desde "
                f"{file_path}: {e}",
                "storage.py", "load", 556,
            )
            return self._get_default_value(memory_type)

    def _get_default_value(self, memory_type: MemoryType) -> Any:
        """Obtiene valor por defecto para un tipo de memoria."""
        defaults = {
            MemoryType.CONVERSATIONAL: [],
            MemoryType.DOMAIN_KNOWLEDGE: {},
            MemoryType.ENTITIES: [],
            MemoryType.APPLICATIONS: {},
            MemoryType.STATE: {},
            MemoryType.PLANS: [],
            MemoryType.EXECUTIONS: [],
            MemoryType.LEARNING_STATS: {},
            MemoryType.RELATIONSHIPS: {},
            MemoryType.PREFERENCES: {},
        }
        return defaults.get(memory_type, [])

    def exists(self, memory_type: MemoryType) -> bool:
        """Verifica si el archivo existe."""
        return self.get_file_path(memory_type).exists()


class MemoryManager:
    """Gestor de memoria mejorado con caché y soporte completo para arquitectura."""

    def __init__(self, storage_path: Optional[Union[str, Path]] = None):
        if storage_path is None:
            storage_path = get_project_root() / "data" / "memory"

        self.storage = JSONStorage(storage_path)
        self.cache = {}
        self.cache_lock = threading.Lock()
        self._cache_ttl = 300

        self._warm_cache()

    def _warm_cache(self) -> None:
        """Inicializa el caché con datos frecuentes."""
        try:
            entities_data = self.storage.load(MemoryType.ENTITIES)
            self._update_cache(
                "entities",
                entities_data if entities_data is not None else [],
                MemoryType.ENTITIES,
            )

            world_state_data = self.storage.load(MemoryType.STATE)
            self._update_cache(
                "world_state",
                world_state_data if world_state_data is not None else {},
                MemoryType.STATE,
            )

            domain_data = self.storage.load(MemoryType.DOMAIN_KNOWLEDGE)
            self._update_cache(
                "domain_knowledge",
                domain_data if domain_data is not None else {},
                MemoryType.DOMAIN_KNOWLEDGE,
            )

        except Exception as e:
            logger._print_log(
                "error",
                f"Error inicializando caché: {e}",
                "storage.py", "_warm_cache", 636,
            )

    def _get_from_cache(
        self,
        key: str,
        memory_type: MemoryType,
    ) -> Any:
        """Obtiene datos del caché si están frescos."""
        with self.cache_lock:
            if key in self.cache:
                cache_entry = self.cache[key]

                if time.time() - cache_entry["timestamp"] < self._cache_ttl:
                    return cache_entry["data"]

                del self.cache[key]

        return None

    def _update_cache(
        self,
        key: str,
        data: Any,
        memory_type: MemoryType,
    ) -> None:
        """Actualiza el caché con nuevos datos."""
        with self.cache_lock:
            self.cache[key] = {
                "data": data,
                "timestamp": time.time(),
                "memory_type": memory_type,
            }

    def save_entity(self, entity: Entity) -> bool:
        """Guarda una entidad en la memoria de dominio."""
        try:
            entities = self.storage.load(MemoryType.ENTITIES)

            if not isinstance(entities, list):
                entities = []

            existing_index = None

            for i, existing in enumerate(entities):
                if isinstance(existing, dict) and existing.get("id") == entity.id:
                    existing_index = i
                    break

            if existing_index is not None:
                entities[existing_index] = entity.to_dict()
            else:
                entities.append(entity.to_dict())

            entity.updated_at = datetime.now().isoformat()

            result = self.storage.save(
                entities,
                MemoryType.ENTITIES,
            )

            self._update_cache(
                "entities",
                entities,
                MemoryType.ENTITIES,
            )

            return result

        except Exception as e:
            logger._print_log(
                "error",
                f"Error guardando entidad id={entity.id} en disco: {e}",
                "storage.py", "save_entity", 709,
            )
            return False

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Obtiene una entidad por su ID."""
        cached_data = self._get_from_cache(
            "entities",
            MemoryType.ENTITIES,
        )

        if cached_data:
            entities_data = cached_data
        else:
            entities_data = self.storage.load(MemoryType.ENTITIES)
            self._update_cache(
                "entities",
                entities_data,
                MemoryType.ENTITIES,
            )

        if not isinstance(entities_data, list):
            return None

        for entity_data in entities_data:
            if isinstance(entity_data, dict) and entity_data.get("id") == entity_id:
                try:
                    return Entity.from_dict(entity_data)
                except Exception as exc:
                    logger._print_log(
                        "warning",
                        f"Entidad invalida no puede reconstruirse (id={entity_id}): {exc}",
                        "storage.py", "get_entity", 741,
                    )
                    return None

        return None

    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Obtiene todas las entidades de un tipo específico."""
        try:
            cached_data = self._get_from_cache(
                "entities",
                MemoryType.ENTITIES,
            )

            if cached_data:
                entities_data = cached_data
            else:
                entities_data = self.storage.load(MemoryType.ENTITIES)
                self._update_cache(
                    "entities",
                    entities_data,
                    MemoryType.ENTITIES,
                )

            if not isinstance(entities_data, list):
                logger._print_log(
                    "warning",
                    f"Datos de entidades no son una lista (tipo={type(entities_data).__name__}), "
                    f"usando [] para filtro tipo='{entity_type}'",
                    "storage.py", "get_entities_by_type", 771,
                )
                entities_data = []

            entities = []

            for entity_data in entities_data:
                if (
                    isinstance(entity_data, dict)
                    and entity_data.get("type") == entity_type
                ):
                    try:
                        entities.append(Entity.from_dict(entity_data))
                    except Exception as exc:
                        logger._print_log(
                            "warning",
                            f"Entidad invalida omitida (id={entity_data.get('id', '?')}) "
                            f"al cargar tipo '{entity_type}': {exc}",
                            "storage.py", "get_entities_by_type", 784,
                        )

            return entities

        except Exception as e:
            logger._print_log(
                "error",
                f"Error en get_entities_by_type(type='{entity_type}'): {e}",
                "storage.py", "get_entities_by_type", 799,
            )
            return []

    def find_entities(
        self,
        query: str = "",
        entity_type: Optional[str] = None,
    ) -> List[Entity]:
        """Busca entidades por texto en nombre, aliases, tags y propiedades."""
        cached_data = self._get_from_cache(
            "entities",
            MemoryType.ENTITIES,
        )

        if cached_data:
            entities_data = cached_data
        else:
            entities_data = self.storage.load(MemoryType.ENTITIES)
            self._update_cache(
                "entities",
                entities_data,
                MemoryType.ENTITIES,
            )

        if not isinstance(entities_data, list):
            return []

        matching_entities = []
        query_lower = (query or "").strip().lower()

        for entity_data in entities_data:
            if isinstance(entity_data, dict):
                try:
                    entity = Entity.from_dict(entity_data)
                except Exception as exc:
                    logger._print_log(
                        "warning",
                        f"Entidad invalida omitida en find_entities "
                        f"(id={entity_data.get('id', '?')}): {exc}",
                        "storage.py", "find_entities", 836,
                    )
                    continue

                if entity_type and entity.type != entity_type:
                    continue

                if not query_lower:
                    matching_entities.append(entity)
                    continue

                if entity.matches_query(query_lower):
                    matching_entities.append(entity)

        return matching_entities

    def find_entities_by_property(
        self,
        property_name: str,
        property_value: Any,
    ) -> List[Entity]:
        """Busca entidades por propiedad específica."""
        cached_data = self._get_from_cache(
            "entities",
            MemoryType.ENTITIES,
        )

        if cached_data:
            entities_data = cached_data
        else:
            entities_data = self.storage.load(MemoryType.ENTITIES)
            self._update_cache(
                "entities",
                entities_data,
                MemoryType.ENTITIES,
            )

        if not isinstance(entities_data, list):
            return []

        entities = []

        for entity_data in entities_data:
            if (
                isinstance(entity_data, dict)
                and property_name in entity_data.get("properties", {})
                and entity_data["properties"][property_name] == property_value
            ):
                try:
                    entities.append(Entity.from_dict(entity_data))
                except Exception as exc:
                    logger._print_log(
                        "warning",
                        f"Entidad invalida omitida en find_entities_by_property "
                        f"(id={entity_data.get('id', '?')}): {exc}",
                        "storage.py", "find_entities_by_property", 891,
                    )

        return entities

    def add_conversational_memory(
        self,
        message: str,
        response: str,
        context: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        entities: Optional[List[str]] = None,
        success: Optional[bool] = None,
        execution_time: float = 0.0,
        confidence: float = 1.0,
    ) -> bool:
        """Añade un registro mejorado a la memoria conversacional."""
        try:
            memory_id = f"conv_{datetime.now().timestamp()}"

            memory = ConversationalMemory(
                id=memory_id,
                message=message,
                response=response,
                timestamp=datetime.now().isoformat(),
                context=context,
                intent=intent,
                entities=entities or [],
                success=success,
                execution_time=execution_time,
                confidence=confidence,
            )

            return self.storage.save(
                memory,
                MemoryType.CONVERSATIONAL,
            )

        except Exception as e:
            logger._print_log("error", f"Error en add_conversational_memory: {e}", "storage.py", "add_conversational_memory", 935)
            return False

    def get_conversational_memory(
        self,
        limit: int = 50,
        intent: Optional[str] = None,
    ) -> List[ConversationalMemory]:
        """Obtiene la memoria conversacional con filtros."""
        try:
            memories_data = self.storage.load(MemoryType.CONVERSATIONAL)

            if not isinstance(memories_data, list):
                return []

            memories = []

            for memory_data in memories_data[-limit:]:
                if isinstance(memory_data, dict):
                    memory = ConversationalMemory.from_dict(memory_data)

                    if intent and memory.intent != intent:
                        continue

                    memories.append(memory)

            return memories

        except Exception as e:
            logger._print_log("error", f"Error en get_conversational_memory: {e}", "storage.py", "get_conversational_memory", 964)
            return []

    def save_world_state(
        self,
        state: Union[WorldState, Dict[str, Any]],
    ) -> bool:
        """Guarda el estado actual del mundo."""
        try:
            if isinstance(state, dict):
                world_state = WorldState.from_dict(state)
            else:
                world_state = state

            result = self.storage.save(
                world_state.to_dict(),
                MemoryType.STATE,
            )

            self._update_cache(
                "world_state",
                world_state.to_dict(),
                MemoryType.STATE,
            )

            return result

        except Exception as e:
            logger._print_log("error", f"Error en save_world_state: {e}", "storage.py", "save_world_state", 992)
            return False

    def get_world_state(self) -> WorldState:
        """Obtiene el estado actual del mundo."""
        cached_data = self._get_from_cache(
            "world_state",
            MemoryType.STATE,
        )

        if cached_data:
            return WorldState.from_dict(cached_data)

        try:
            state_data = self.storage.load(MemoryType.STATE)
            world_state = WorldState.from_dict(state_data)

            self._update_cache(
                "world_state",
                state_data,
                MemoryType.STATE,
            )

            return world_state

        except Exception as e:
            logger._print_log("error", f"Error en get_world_state: {e}", "storage.py", "get_world_state", 1018)

            return WorldState(
                timestamp=time.time(),
                applications={},
                ui_elements={},
                system_info={},
                constraints=[],
                last_actions=[],
                active_goals=[],
            )

    def update_world_state(self, key: str, value: Any) -> bool:
        """Actualiza una propiedad del estado del mundo."""
        try:
            state = self.get_world_state()

            if key.startswith("app_"):
                app_name = key[4:]

                if app_name not in state.applications:
                    state.applications[app_name] = {}

                state.applications[app_name].update(value)

            elif key.startswith("ui_"):
                element_name = key[3:]

                if element_name not in state.ui_elements:
                    state.ui_elements[element_name] = {}

                state.ui_elements[element_name].update(value)

            elif key in ["constraints", "last_actions", "active_goals"]:
                if not isinstance(value, list):
                    value = [value]

                setattr(state, key, value)

            else:
                state.system_info[key] = value

            state.timestamp = time.time()
            return self.save_world_state(state)

        except Exception as e:
            logger._print_log("error", f"Error en update_world_state: {e}", "storage.py", "update_world_state", 1064)
            return False

    def save_plan(self, plan: Plan) -> bool:
        """Guarda un plan."""
        try:
            plans = self.storage.load(MemoryType.PLANS)

            if not isinstance(plans, list):
                plans = []

            existing_index = None

            for i, existing in enumerate(plans):
                if isinstance(existing, dict) and existing.get("id") == plan.id:
                    existing_index = i
                    break

            if existing_index is not None:
                plans[existing_index] = plan.to_dict()
            else:
                plans.append(plan.to_dict())

            return self.storage.save(
                plans,
                MemoryType.PLANS,
            )

        except Exception as e:
            logger._print_log("error", f"Error en save_plan: {e}", "storage.py", "save_plan", 1093)
            return False

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """Obtiene un plan por su ID."""
        try:
            plans_data = self.storage.load(MemoryType.PLANS)

            if not isinstance(plans_data, list):
                return None

            for plan_data in plans_data:
                if isinstance(plan_data, dict) and plan_data.get("id") == plan_id:
                    return Plan.from_dict(plan_data)

            return None

        except Exception as e:
            logger._print_log("error", f"Error en get_plan: {e}", "storage.py", "get_plan", 1111)
            return None

    def save_execution_record(
        self,
        record: ExecutionRecord,
    ) -> bool:
        """Guarda un registro de ejecución."""
        try:
            executions = self.storage.load(MemoryType.EXECUTIONS)

            if not isinstance(executions, list):
                executions = []

            executions.append(record.to_dict())

            return self.storage.save(
                executions,
                MemoryType.EXECUTIONS,
            )

        except Exception as e:
            logger._print_log("error", f"Error en save_execution_record: {e}", "storage.py", "save_execution_record", 1133)
            return False

    def update_learning_stats(
        self,
        action_name: str,
        success: bool,
        execution_time: float,
    ) -> bool:
        """Actualiza estadísticas de aprendizaje para una acción."""
        try:
            stats_data = self.storage.load(MemoryType.LEARNING_STATS)

            if not isinstance(stats_data, dict):
                stats_data = {}

            if action_name not in stats_data:
                stats_data[action_name] = {
                    "action_name": action_name,
                    "total_executions": 0,
                    "successful_executions": 0,
                    "average_execution_time": 0.0,
                    "success_rate": 0.0,
                    "last_updated": datetime.now().isoformat(),
                }

            stat = LearningStat(**stats_data[action_name])
            stat.update(success, execution_time)
            stats_data[action_name] = stat.__dict__

            return self.storage.save(
                stats_data,
                MemoryType.LEARNING_STATS,
            )

        except Exception as e:
            logger._print_log("error", f"Error en update_learning_stats: {e}", "storage.py", "update_learning_stats", 1169)
            return False

    def get_learning_stats(
        self,
        action_name: Optional[str] = None,
    ) -> Union[LearningStat, Dict[str, LearningStat]]:
        """Obtiene estadísticas de aprendizaje."""
        try:
            stats_data = self.storage.load(MemoryType.LEARNING_STATS)

            if not isinstance(stats_data, dict):
                return {}

            if action_name:
                if action_name in stats_data:
                    return LearningStat(**stats_data[action_name])

                return None

            return {name: LearningStat(**data) for name, data in stats_data.items()}

        except Exception as e:
            logger._print_log("error", f"Error en get_learning_stats: {e}", "storage.py", "get_learning_stats", 1192)
            return {}

    def clear_memory(
        self,
        memory_type: Optional[MemoryType] = None,
    ) -> bool:
        """Limpia la memoria especificada o toda la memoria."""
        try:
            if memory_type:
                default_value = self.storage._get_default_value(memory_type)

                result = self.storage.save(
                    default_value,
                    memory_type,
                )

                with self.cache_lock:
                    keys_to_remove = [
                        k
                        for k, v in self.cache.items()
                        if v["memory_type"] == memory_type
                    ]

                    for key in keys_to_remove:
                        del self.cache[key]

                return result

            for mem_type in MemoryType:
                self.storage.save(
                    self.storage._get_default_value(mem_type),
                    mem_type,
                )

            with self.cache_lock:
                self.cache.clear()

            return True

        except Exception as e:
            logger._print_log("error", f"Error en clear_memory: {e}", "storage.py", "clear_memory", 1233)
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas detalladas de la memoria."""
        try:
            stats = {}

            for memory_type in MemoryType:
                try:
                    data = self.storage.load(memory_type)

                    if data is None:
                        stats[memory_type.value] = 0
                    elif isinstance(data, list):
                        stats[memory_type.value] = len(data)
                    elif isinstance(data, dict):
                        stats[memory_type.value] = len(data)
                    else:
                        stats[memory_type.value] = 1 if data else 0

                except Exception as e:
                    logger._print_log("error", f"Error en get_memory_stats: {e}", "storage.py", "get_memory_stats", 1255)
                    stats[memory_type.value] = 0

            with self.cache_lock:
                stats["cache_entries"] = len(self.cache)
                stats["cache_memory_usage"] = sum(
                    len(str(entry["data"])) for entry in self.cache.values()
                )

            return stats

        except Exception as e:
            logger._print_log("error", f"Error en get_memory_stats: {e}", "storage.py", "get_memory_stats", 1267)
            return {}

    def save_user_preference(
        self,
        preference: UserPreference,
    ) -> bool:
        """Guarda una preferencia de usuario."""
        try:
            preferences_data = self.storage.load(MemoryType.PREFERENCES)

            if not isinstance(preferences_data, dict):
                preferences_data = {}

            preference_key = (
                f"{preference.user_id}_"
                f"{preference.preference_type}_"
                f"{preference.preference_key}"
            )

            if preference_key in preferences_data:
                existing_pref = UserPreference.from_dict(
                    preferences_data[preference_key]
                )
                preference.usage_count = existing_pref.usage_count + 1

            preference.updated_at = datetime.now().isoformat()
            preferences_data[preference_key] = preference.to_dict()

            result = self.storage.save(
                preferences_data,
                MemoryType.PREFERENCES,
            )

            self._update_cache(
                "preferences",
                preferences_data,
                MemoryType.PREFERENCES,
            )

            return result

        except Exception as e:
            logger._print_log("error", f"Error en save_user_preference: {e}", "storage.py", "save_user_preference", 1310)
            return False

    def get_user_preference(
        self,
        user_id: str,
        preference_type: str,
        preference_key: str,
    ) -> Optional[UserPreference]:
        """Obtiene una preferencia específica del usuario."""
        try:
            cached_data = self._get_from_cache(
                "preferences",
                MemoryType.PREFERENCES,
            )

            if cached_data:
                preferences_data = cached_data
            else:
                preferences_data = self.storage.load(MemoryType.PREFERENCES)
                self._update_cache(
                    "preferences",
                    preferences_data,
                    MemoryType.PREFERENCES,
                )

            if not isinstance(preferences_data, dict):
                return None

            preference_key_full = f"{user_id}_{preference_type}_{preference_key}"

            if preference_key_full in preferences_data:
                return UserPreference.from_dict(preferences_data[preference_key_full])

            return None

        except Exception as e:
            logger._print_log("error", f"Error en get_user_preference: {e}", "storage.py", "get_user_preference", 1347)
            return None

    def get_user_preferences(
        self,
        user_id: str,
        preference_type: Optional[str] = None,
    ) -> List[UserPreference]:
        """Obtiene todas las preferencias de un usuario."""
        try:
            cached_data = self._get_from_cache(
                "preferences",
                MemoryType.PREFERENCES,
            )

            if cached_data:
                preferences_data = cached_data
            else:
                preferences_data = self.storage.load(MemoryType.PREFERENCES)
                self._update_cache(
                    "preferences",
                    preferences_data,
                    MemoryType.PREFERENCES,
                )

            if not isinstance(preferences_data, dict):
                return []

            preferences = []

            for key, pref_data in preferences_data.items():
                if key.startswith(f"{user_id}_"):
                    preference = UserPreference.from_dict(pref_data)

                    if (
                        preference_type
                        and preference.preference_type != preference_type
                    ):
                        continue

                    preferences.append(preference)

            preferences.sort(
                key=lambda p: (p.usage_count, p.updated_at),
                reverse=True,
            )

            return preferences

        except Exception as e:
            logger._print_log("error", f"Error en get_user_preferences: {e}", "storage.py", "get_user_preferences", 1397)
            return []

    def update_user_preference(
        self,
        user_id: str,
        preference_type: str,
        preference_key: str,
        value: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Actualiza o crea una preferencia de usuario."""
        try:
            existing_pref = self.get_user_preference(
                user_id,
                preference_type,
                preference_key,
            )

            if existing_pref:
                existing_pref.preference_value = value
                existing_pref.context = context
                existing_pref.updated_at = datetime.now().isoformat()
                existing_pref.usage_count += 1

                return self.save_user_preference(existing_pref)

            preference = UserPreference(
                user_id=user_id,
                preference_type=preference_type,
                preference_key=preference_key,
                preference_value=value,
                context=context,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                usage_count=1,
            )

            return self.save_user_preference(preference)

        except Exception as e:
            logger._print_log("error", f"Error en update_user_preference: {e}", "storage.py", "update_user_preference", 1438)
            return False

    def learn_user_preference(
        self,
        user_id: str,
        entity_id: str,
        interaction_type: str,
        success: bool = True,
    ) -> bool:
        """Aprende preferencias de usuario basadas en interacciones."""
        try:
            existing_preferences = self.get_user_preferences(
                user_id,
                f"entity_{interaction_type}",
            )

            preference_key = f"entity_{interaction_type}_{entity_id}"

            existing_pref = None

            for pref in existing_preferences:
                if pref.preference_key == preference_key:
                    existing_pref = pref
                    break

            if existing_pref:
                if success:
                    existing_pref.confidence = min(
                        1.0,
                        existing_pref.confidence + 0.05,
                    )
                    existing_pref.usage_count += 1
                else:
                    existing_pref.confidence = max(
                        0.1,
                        existing_pref.confidence - 0.1,
                    )

                existing_pref.updated_at = datetime.now().isoformat()

            else:
                existing_pref = UserPreference(
                    user_id=user_id,
                    preference_type=f"entity_{interaction_type}",
                    preference_key=preference_key,
                    preference_value=entity_id,
                    confidence=0.8 if success else 0.3,
                    context={
                        "interaction_type": interaction_type,
                        "success": success,
                    },
                    usage_count=1 if success else 0,
                )

            return self.save_user_preference(existing_pref)

        except Exception as e:
            logger._print_log("error", f"Error en learn_user_preference: {e}", "storage.py", "learn_user_preference", 1496)
            return False

    def save_entity_attribute(
        self,
        attribute: EntityAttribute,
    ) -> bool:
        """Guarda un atributo extendido de entidad."""
        try:
            attributes_data = self.storage.load(MemoryType.RELATIONSHIPS)

            if not isinstance(attributes_data, dict):
                attributes_data = {}

            attribute_key = f"attr_{attribute.entity_id}_{attribute.attribute_name}"

            attribute.updated_at = datetime.now().isoformat()
            attributes_data[attribute_key] = attribute.to_dict()

            result = self.storage.save(
                attributes_data,
                MemoryType.RELATIONSHIPS,
            )

            self._update_cache(
                "entity_attributes",
                attributes_data,
                MemoryType.RELATIONSHIPS,
            )

            return result

        except Exception as e:
            logger._print_log("error", f"Error en save_entity_attribute: {e}", "storage.py", "save_entity_attribute", 1529)
            return False

    def get_entity_attribute(
        self,
        entity_id: str,
        attribute_name: str,
    ) -> Optional[EntityAttribute]:
        """Obtiene un atributo específico de una entidad."""
        try:
            cached_data = self._get_from_cache(
                "entity_attributes",
                MemoryType.RELATIONSHIPS,
            )

            if cached_data:
                attributes_data = cached_data
            else:
                attributes_data = self.storage.load(MemoryType.RELATIONSHIPS)
                self._update_cache(
                    "entity_attributes",
                    attributes_data,
                    MemoryType.RELATIONSHIPS,
                )

            if not isinstance(attributes_data, dict):
                return None

            attribute_key = f"attr_{entity_id}_{attribute_name}"

            if attribute_key in attributes_data:
                return EntityAttribute.from_dict(attributes_data[attribute_key])

            return None

        except Exception as e:
            logger._print_log("error", f"Error en get_entity_attribute: {e}", "storage.py", "get_entity_attribute", 1565)
            return None

    def get_entity_attributes(
        self,
        entity_id: str,
    ) -> List[EntityAttribute]:
        """Obtiene todos los atributos extendidos de una entidad."""
        try:
            cached_data = self._get_from_cache(
                "entity_attributes",
                MemoryType.RELATIONSHIPS,
            )

            if cached_data:
                attributes_data = cached_data
            else:
                attributes_data = self.storage.load(MemoryType.RELATIONSHIPS)
                self._update_cache(
                    "entity_attributes",
                    attributes_data,
                    MemoryType.RELATIONSHIPS,
                )

            if not isinstance(attributes_data, dict):
                return []

            attributes = []

            for key, attr_data in attributes_data.items():
                if key.startswith(f"attr_{entity_id}_"):
                    attribute = EntityAttribute.from_dict(attr_data)
                    attributes.append(attribute)

            attributes.sort(
                key=lambda a: a.updated_at,
                reverse=True,
            )

            return attributes

        except Exception as e:
            logger._print_log("error", f"Error en get_entity_attributes: {e}", "storage.py", "get_entity_attributes", 1607)
            return []

    def update_entity_attribute(
        self,
        entity_id: str,
        attribute_name: str,
        value: Any,
        attribute_type: str = "string",
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Actualiza o crea un atributo extendido de entidad."""
        try:
            attribute = EntityAttribute(
                entity_id=entity_id,
                attribute_name=attribute_name,
                attribute_value=value,
                attribute_type=attribute_type,
                source=source,
                metadata=metadata,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

            return self.save_entity_attribute(attribute)

        except Exception as e:
            logger._print_log("error", f"Error en update_entity_attribute: {e}", "storage.py", "update_entity_attribute", 1635)
            return False

    def get_entities_by_attribute(
        self,
        attribute_name: str,
        attribute_value: Any,
    ) -> List[Entity]:
        """Busca entidades por atributo y valor."""
        try:
            entities_data = self.storage.load(MemoryType.ENTITIES)

            if not isinstance(entities_data, list):
                return []

            matching_entities = []

            attributes_data = self.storage.load(MemoryType.RELATIONSHIPS)

            if not isinstance(attributes_data, dict):
                return []

            for key, attr_data in attributes_data.items():
                if key.startswith("attr_"):
                    if (
                        isinstance(attr_data, dict)
                        and attr_data.get("attribute_name") == attribute_name
                        and attr_data.get("attribute_value") == attribute_value
                    ):
                        entity_id = attr_data.get("entity_id")

                        for entity_data in entities_data:
                            if (
                                isinstance(entity_data, dict)
                                and entity_data.get("id") == entity_id
                            ):
                                matching_entities.append(Entity.from_dict(entity_data))
                                break

            return matching_entities

        except Exception as e:
            logger._print_log("error", f"Error en get_entities_by_attribute: {e}", "storage.py", "get_entities_by_attribute", 1677)
            return []

    def export_memory(
        self,
        export_path: Union[str, Path],
    ) -> bool:
        """Exporta toda la memoria a un archivo JSON."""
        try:
            export_data = {}

            for memory_type in MemoryType:
                export_data[memory_type.value] = self.storage.load(memory_type)

            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(
                    export_data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            logger._print_log("info", f"Operacion completada en export_memory", "storage.py", "export_memory", 1699)
            return True

        except Exception as e:
            logger._print_log("error", f"Error en export_memory: {e}", "storage.py", "export_memory", 1703)
            return False


_memory_manager = None


def get_memory_manager() -> MemoryManager:
    """Obtiene la instancia global del gestor de memoria."""
    global _memory_manager

    if _memory_manager is None:
        _memory_manager = MemoryManager()

    return _memory_manager


def save_entity(entity: Entity) -> bool:
    """Guarda una entidad."""
    return get_memory_manager().save_entity(entity)


def get_entity(entity_id: str) -> Optional[Entity]:
    """Obtiene una entidad."""
    return get_memory_manager().get_entity(entity_id)


def get_entities_by_type(entity_type: str) -> List[Entity]:
    """Obtiene entidades."""
    return get_memory_manager().get_entities_by_type(entity_type)


def find_entities(
    query: str = "",
    entity_type: Optional[str] = None,
) -> List[Entity]:
    """Busca entidades."""
    return get_memory_manager().find_entities(
        query,
        entity_type,
    )


def add_conversational_memory(
    message: str,
    response: str,
    **kwargs,
) -> bool:
    """Añade memoria conversacional."""
    return get_memory_manager().add_conversational_memory(
        message,
        response,
        **kwargs,
    )


def get_world_state() -> WorldState:
    """Obtiene el estado del mundo."""
    return get_memory_manager().get_world_state()


def update_world_state(key: str, value: Any) -> bool:
    """Actualiza el estado del mundo."""
    return get_memory_manager().update_world_state(
        key,
        value,
    )


def save_plan(plan: Plan) -> bool:
    """Guarda un plan."""
    return get_memory_manager().save_plan(plan)


def get_plan(plan_id: str) -> Optional[Plan]:
    """Obtiene un plan."""
    return get_memory_manager().get_plan(plan_id)


def update_learning_stats(
    action_name: str,
    success: bool,
    execution_time: float,
) -> bool:
    """Actualiza estadísticas de aprendizaje."""
    return get_memory_manager().update_learning_stats(
        action_name,
        success,
        execution_time,
    )


def resolve_entity_to_url(entity: Entity) -> Optional[str]:
    """Resuelve una entidad a una URL."""
    try:
        if "url" in entity.properties:
            return entity.properties["url"]

        if entity.type == "application" and "url" in entity.properties:
            return entity.properties["url"]

        if entity.type == "streamer":
            platform = entity.properties.get("platform", "twitch")
            streamer_name = entity.name.lower().replace(" ", "")

            if platform == "twitch":
                return f"https://www.twitch.tv/{streamer_name}"

            elif platform == "youtube":
                return f"https://www.youtube.com/@{streamer_name}"

            elif platform == "tiktok":
                return f"https://www.tiktok.com/@{streamer_name}"

        if entity.type == "platform":
            platform_urls = {
                "twitch": "https://www.twitch.tv",
                "youtube": "https://www.youtube.com",
                "tiktok": "https://www.tiktok.com",
                "twitter": "https://twitter.com",
                "instagram": "https://instagram.com",
            }

            return platform_urls.get(entity.name.lower())

        return None

    except Exception as e:
        logger._print_log("error", f"Error en resolve_entity_to_url: {e}", "storage.py", "resolve_entity_to_url", 1831)
        return None


def get_entity_attributes(entity: Entity) -> Dict[str, Any]:
    """Obtiene atributos extendidos de una entidad."""
    try:
        attributes = {
            "basic": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.type,
                "confidence": entity.confidence,
                "aliases": entity.aliases,
                "tags": entity.tags,
            },
            "properties": entity.properties,
            "metadata": entity.metadata or {},
            "timestamps": {
                "created_at": entity.created_at,
                "updated_at": entity.updated_at,
            },
        }

        if entity.type == "streamer":
            attributes["calculated"] = {
                "platform_url": resolve_entity_to_url(entity),
                "category": entity.properties.get(
                    "category",
                    "unknown",
                ),
                "is_live": entity.properties.get(
                    "is_live",
                    False,
                ),
            }

        elif entity.type == "application":
            attributes["calculated"] = {
                "executable": entity.properties.get("executable"),
                "can_navigate": "url" in entity.properties,
                "has_ui_elements": len(entity.properties.get("ui_elements", {})) > 0,
            }

        elif entity.type == "platform":
            attributes["calculated"] = {
                "base_url": resolve_entity_to_url(entity),
                "supported_categories": entity.properties.get(
                    "categories",
                    [],
                ),
            }

        return attributes

    except Exception as e:
        logger._print_log("error", f"Error en get_entity_attributes: {e}", "storage.py", "get_entity_attributes", 1887)
        return {}


def create_goal_from_entity(
    entity: Entity,
    user_input: str,
) -> Optional[Dict[str, Any]]:
    """Integración entidad -> Goal."""
    try:
        goal_type = None
        goal_description = ""

        if entity.type == "streamer":
            goal_type = "streamer_goal"
            goal_description = f"Navegar al streamer {entity.name}"

            if any(
                word in user_input.lower()
                for word in ["abrir", "ver", "watch", "ver stream"]
            ):
                return {
                    "type": goal_type,
                    "description": goal_description,
                    "target_entity": entity.id,
                    "target_url": resolve_entity_to_url(entity),
                    "required_capabilities": [
                        "navigate",
                        "new_tab",
                    ],
                    "priority": "high",
                }

        elif entity.type == "application":
            goal_type = "application_goal"
            goal_description = f"Abrir aplicación {entity.name}"

            if "abrir" in user_input.lower() or "open" in user_input.lower():
                return {
                    "type": goal_type,
                    "description": goal_description,
                    "target_entity": entity.id,
                    "target_executable": entity.properties.get("executable"),
                    "required_capabilities": ["open_application"],
                    "priority": "medium",
                }

        elif entity.type == "platform":
            goal_type = "platform_goal"
            goal_description = f"Navegar a plataforma {entity.name}"

            if any(word in user_input.lower() for word in ["abrir", "ir", "go"]):
                return {
                    "type": goal_type,
                    "description": goal_description,
                    "target_entity": entity.id,
                    "target_url": resolve_entity_to_url(entity),
                    "required_capabilities": [
                        "navigate",
                        "new_tab",
                    ],
                    "priority": "medium",
                }

        return None

    except Exception as e:
        logger._print_log("error", f"Error en create_goal_from_entity: {e}", "storage.py", "create_goal_from_entity", 1954)
        return None


def verify_entity_integrity(
    entity: Entity,
) -> Dict[str, Any]:
    """Verifica la integridad de una entidad."""
    try:
        verification_result = {
            "entity_id": entity.id,
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "score": 100,
        }

        if not entity.id:
            verification_result["issues"].append("ID de entidad vacío")
            verification_result["is_valid"] = False
            verification_result["score"] -= 50

        if not entity.name:
            verification_result["issues"].append("Nombre de entidad vacío")
            verification_result["is_valid"] = False
            verification_result["score"] -= 30

        if not entity.type:
            verification_result["issues"].append("Tipo de entidad no especificado")
            verification_result["is_valid"] = False
            verification_result["score"] -= 20

        if entity.aliases:
            duplicate_aliases = []
            seen_aliases = set()

            for alias in entity.aliases:
                if alias.lower() in seen_aliases:
                    duplicate_aliases.append(alias)

                seen_aliases.add(alias.lower())

            if duplicate_aliases:
                verification_result["warnings"].append(
                    f"Aliases duplicados: {duplicate_aliases}"
                )
                verification_result["score"] -= 10

        if (
            entity.type in ["streamer", "application", "platform"]
            and "url" in entity.properties
        ):
            url = entity.properties["url"]

            if not url.startswith(("http://", "https://")):
                verification_result["warnings"].append(f"URL no parece válida: {url}")
                verification_result["score"] -= 15

        type_consistency_checks = {
            "streamer": ["url", "platform"],
            "application": ["executable"],
            "platform": ["url"],
        }

        if entity.type in type_consistency_checks:
            required_props = type_consistency_checks[entity.type]
            missing_props = []

            for prop in required_props:
                if prop not in entity.properties:
                    missing_props.append(prop)

            if missing_props:
                verification_result["warnings"].append(
                    f"Propiedades esperadas faltantes para "
                    f"tipo {entity.type}: {missing_props}"
                )
                verification_result["score"] -= 5

        return verification_result

    except Exception as e:
        logger._print_log("error", f"Error en verify_entity_integrity: {e}", "storage.py", "verify_entity_integrity", 2036)

        return {
            "entity_id": entity.id,
            "is_valid": False,
            "issues": [f"Error de verificación: {str(e)}"],
            "warnings": [],
            "score": 0,
        }
