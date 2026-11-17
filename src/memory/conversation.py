"""
Memoria de conversaciones y sistema de planificacion jerarquica.
Transforma el sistema de texto->comando->funcion a intencion->objetivo->plan->ejecucion.

Cumple con:
- FASE 1: Modelo de nodos
- FASE 2: Nodos jerarquicos  
- FASE 5: Memoria de dominio
- FASE 15: Comandos de alto nivel
- FASE 16: Compatibilidad
"""

import json
import os
import re
import tempfile
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from src.memory.storage import MemoryManager, Entity as StorageEntity, JSONStorage as Storage, MemoryType
from src.core.config import (
    get_memory_config,
    get_predictive_config,
    get_project_root,
)
from src.core.log import get_logger


# Clases basicas para evitar importaciones circulares
class NodeType(Enum):
    """Tipos de nodos en el sistema de planificacion."""
    INTENTION = "intention"
    GOAL = "goal"
    TASK = "task"
    ACTION = "action"
    CONDITION = "condition"
    STATE = "state"
    RESOURCE = "resource"
    APPLICATION = "application"
    UI_ELEMENT = "ui_element"
    RESULT = "result"
    PLAN = "plan"


class TaskStatus(Enum):
    """Estado de ejecucion de tareas."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class Node:
    """Modelo basico de nodo para memoria."""
    id: str
    type: NodeType
    name: str
    description: str = ""
    preconditions: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    cost: float = 1.0
    dependencies: list = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    application: str = None
    ui_element: str = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Goal:
    """Modelo basico de objetivo para memoria."""
    id: str
    type: str
    target: any
    description: str
    priority: int = 1
    constraints: list = field(default_factory=list)
    created_at: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class Task:
    """Modelo basico de tarea para memoria."""
    id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    nodes: list = field(default_factory=list)
    parent: str = None

logger = get_logger(__name__)





@dataclass
class Task:
    """Tarea jerarquica (FASE 2)."""
    id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    nodes: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def can_execute(self, current_state: Dict[str, Any], all_nodes: Dict[str, Node]) -> bool:
        """Verifica si la tarea puede ejecutarse."""
        # Verificar dependencias
        for dep_id in self.dependencies:
            if dep_id not in all_nodes:
                return False
            dep_node = all_nodes[dep_id]
            if not dep_node.can_execute(current_state):
                return False
        return True


class DomainMemory:
    """Memoria de conocimiento del dominio (FASE 5)."""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.applications: Dict[str, Dict[str, Any]] = {}
        self.capabilities: Dict[str, List[str]] = {}
        self.preferences: Dict[str, Any] = {}  # Preferencias del usuario
        self.user_interactions: List[Dict[str, Any]] = []  # Historial de interacciones
        self.knowledge_updates: List[Dict[str, Any]] = []  # Actualizaciones de conocimiento
        self.load_domain_knowledge()
        self.load_user_preferences()
    
    def load_domain_knowledge(self) -> None:
        """Carga conocimiento del dominio desde archivos."""
        logger.info("[DOMAIN] Cargando conocimiento del dominio...")
        
        # Cargar entidades
        try:
            entities_path = get_project_root() / "data" / "knowledge" / "entities.json"
            if entities_path.exists():
                with open(entities_path, "r", encoding="utf-8") as f:
                    entities_data = json.load(f)
                    # Handle both list and dictionary formats
                    if isinstance(entities_data, list):
                        for entity_data in entities_data:
                            entity_id = entity_data.get("id")
                            if entity_id:
                                # Use StorageEntity from storage.py
                                entity = StorageEntity.from_dict(entity_data)
                                self.entities[entity_id] = entity
                    elif isinstance(entities_data, dict):
                        for entity_id, entity_data in entities_data.items():
                            # Use StorageEntity from storage.py
                            entity = StorageEntity.from_dict(entity_data)
                            self.entities[entity_id] = entity
                logger.info(f"[DOMAIN] Cargadas {len(self.entities)} entidades")
        except Exception as e:
            logger.error(f"[DOMAIN] Error cargando entidades: {e}")
        
        # Cargar aplicaciones
        try:
            apps_path = get_project_root() / "data" / "knowledge" / "applications.json"
            if apps_path.exists():
                with open(apps_path, "r", encoding="utf-8") as f:
                    self.applications = json.load(f)
                logger.info(f"[DOMAIN] Cargadas {len(self.applications)} aplicaciones")
        except Exception as e:
            logger.error(f"[DOMAIN] Error cargando aplicaciones: {e}")
        
        # Cargar capacidades
        try:
            caps_path = get_project_root() / "data" / "knowledge" / "capabilities.json"
            if caps_path.exists():
                with open(caps_path, "r", encoding="utf-8") as f:
                    self.capabilities = json.load(f)
                logger.info(f"[DOMAIN] Cargadas {len(self.capabilities)} categorias de capacidades")
        except Exception as e:
            logger.error(f"[DOMAIN] Error cargando capacidades: {e}")
    
    def load_user_preferences(self) -> None:
        """Carga preferencias del usuario desde archivo persistente."""
        try:
            prefs_path = get_project_root() / "data" / "user_preferences.json"
            if prefs_path.exists():
                with open(prefs_path, "r", encoding="utf-8") as f:
                    self.preferences = json.load(f)
                logger.info(f"[DOMAIN] Cargadas preferencias del usuario")
        except Exception as e:
            logger.error(f"[DOMAIN] Error cargando preferencias: {e}")
            self.preferences = {}
    
    def save_user_preferences(self) -> bool:
        """Guarda preferencias del usuario de forma persistente."""
        try:
            prefs_path = get_project_root() / "data" / "user_preferences.json"
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2, ensure_ascii=False)
            logger.info("Preferencias guardadas exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error guardando preferencias: {e}")
            return False
    
    def get_entity(self, entity_name: str) -> Optional[Entity]:
        """Obtiene una entidad por nombre o alias."""
        for entity in self.entities.values():
            if entity.matches_name(entity_name):
                logger.info(f"Entidad encontrada: {entity.name} ({entity.id})")
                return entity
        logger.debug(f"Entidad no encontrada: {entity_name}")
        return None
    
    def get_application_capabilities(self, app_name: str) -> List[str]:
        """Obtiene capacidades de una aplicacion."""
        return self.capabilities.get(app_name, [])
    
    def get_capability_definition(self, category: str, capability: str) -> Optional[Dict[str, Any]]:
        """Obtiene definicion detallada de una capacidad."""
        category_caps = self.capabilities.get(category, {})
        return category_caps.get(capability)
    
    def record_user_interaction(self, user_input: str, entity_used: Optional[str], 
                               action_taken: str, success: bool) -> None:
        """Registra interaccion del usuario para aprendizaje y preferencias."""
        interaction = {
            "timestamp": time.time(),
            "user_input": user_input,
            "entity_used": entity_used,
            "action_taken": action_taken,
            "success": success,
            "user_preferences": self.preferences.copy()
        }
        self.user_interactions.append(interaction)
        
        # Actualizar preferencias basadas en interacciones exitosas
        if success and entity_used:
            self._update_preferences_from_interaction(interaction)
        
        logger.debug(f"Interaccion registrada: {action_taken} (exitosa: {success})")
    
    def _update_preferences_from_interaction(self, interaction: Dict[str, Any]) -> None:
        """Actualiza preferencias basadas en interacciones exitosas."""
        entity_id = interaction.get("entity_used")
        action = interaction.get("action_taken")
        
        if entity_id and entity_id in self.entities:
            entity = self.entities[entity_id]
            
            # Actualizar preferencias de aplicaciones
            if entity.type == "application":
                app_name = entity.name.lower()
                if "preferred_app" not in self.preferences:
                    self.preferences["preferred_app"] = {}
                
                if app_name not in self.preferences["preferred_app"]:
                    self.preferences["preferred_app"][app_name] = {
                        "usage_count": 0,
                        "last_used": interaction["timestamp"]
                    }
                
                self.preferences["preferred_app"][app_name]["usage_count"] += 1
                self.preferences["preferred_app"][app_name]["last_used"] = interaction["timestamp"]
            
            # Actualizar preferencias de entidades
            if "preferred_entities" not in self.preferences:
                self.preferences["preferred_entities"] = []
            
            if entity_id not in self.preferences["preferred_entities"]:
                self.preferences["preferred_entities"].append(entity_id)
        
        # Guardar preferencias actualizadas
        self.save_user_preferences()
    
    def get_user_preferences(self) -> Dict[str, Any]:
        """Obtiene preferencias del usuario."""
        return self.preferences.copy()
    
    def get_preferred_entities(self, entity_type: Optional[str] = None) -> List[Entity]:
        """Obtiene entidades preferidas por el usuario."""
        preferred_ids = self.preferences.get("preferred_entities", [])
        preferred_entities = []
        
        for entity_id in preferred_ids:
            if entity_id in self.entities:
                entity = self.entities[entity_id]
                if entity_type is None or entity.type == entity_type:
                    preferred_entities.append(entity)
        
        # Ordenar por uso reciente
        preferred_entities.sort(
            key=lambda e: self.preferences.get("preferred_app", {}).get(e.name.lower(), {}).get("last_used", 0),
            reverse=True
        )
        
        return preferred_entities
    
    def get_preferred_application(self, action_type: str) -> Optional[str]:
        """Obtiene aplicacion preferida para un tipo de accion."""
        preferred_apps = self.preferences.get("preferred_app", {})
        
        # Obtener aplicaciones que soportan esta accion
        suitable_apps = []
        for app_name, app_info in preferred_apps.items():
            if app_name in self.applications:
                app_caps = self.capabilities.get(app_name, [])
                if action_type in app_caps:
                    suitable_apps.append((app_name, app_info))
        
        # Ordenar por uso y devolver la mas usada
        suitable_apps.sort(key=lambda x: x[1]["usage_count"], reverse=True)
        
        if suitable_apps:
            return suitable_apps[0][0]
        
        return None
    
    def add_knowledge_update(self, update_type: str, content: Dict[str, Any]) -> None:
        """Anade actualizacion de conocimiento para persistencia futura."""
        update = {
            "timestamp": time.time(),
            "type": update_type,
            "content": content,
            "verified": False
        }
        self.knowledge_updates.append(update)
        logger.info(f"[DOMAIN] Actualizacion de conocimiento registrada: {update_type}")
    
    def get_suggested_entities(self, partial_name: str, limit: int = 5) -> List[Entity]:
        """Obtiene sugerencias de entidades basadas en nombre parcial y preferencias."""
        matches = []
        normalized_partial = self._normalize_text(partial_name)
        
        # Buscar coincidencias
        for entity in self.entities.values():
            if normalized_partial in entity.name.lower() or any(
                normalized_partial in alias.lower() for alias in entity.aliases
            ):
                matches.append(entity)
        
        # Ordenar por preferencias del usuario
        preferred_ids = set(self.preferences.get("preferred_entities", []))
        matches.sort(
            key=lambda e: 1 if e.id in preferred_ids else 2,
            reverse=True
        )
        
        return matches[:limit]
    
    def reason_about_entities(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Realiza razonamiento basico sobre entidades basado en contexto y preferencias."""
        reasoning = {
            "context": context,
            "relevant_entities": [],
            "preferred_actions": [],
            "suggested_entities": [],
            "confidence": 0.0
        }
        
        # Obtener entidades relevantes del contexto
        if "intent" in context:
            intent = context["intent"]
            entity_name = intent.get("entity", "")
            
            if entity_name:
                entity = self.get_entity(entity_name)
                if entity:
                    reasoning["relevant_entities"].append(entity)
                    
                    # Sugerir acciones basadas en preferencias
                    if entity.type == "application":
                        preferred_app = self.get_preferred_application(intent.get("type", ""))
                        if preferred_app:
                            reasoning["preferred_actions"].append(preferred_app)
                    
                    # Obtener sugerencias
                    suggestions = self.get_suggested_entities(entity_name)
                    reasoning["suggested_entities"] = suggestions
                    
                    # Calcular confianza basada en preferencias y historial
                    usage_count = self.preferences.get("preferred_app", {}).get(entity.name.lower(), {}).get("usage_count", 0)
                    reasoning["confidence"] = min(0.9, 0.3 + (usage_count * 0.1))
        
        return reasoning
    
    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para busqueda."""
        if not isinstance(text, str):
            return ""
        
        text = text.strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = re.sub(r"[^a-z0-9]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class ConversationMemory:
    """
    Sistema de memoria transformado para planificacion jerarquica.
    
    Implementa:
    - FASE 1: Modelo de nodos
    - FASE 2: Nodos jerarquicos
    - FASE 5: Memoria de dominio
    - FASE 15: Comandos de alto nivel
    - FASE 16: Compatibilidad
    """

    STATIC_COMMAND_ALIASES_FILE = "config/command_aliases.json"
    FALLBACK_LEARNED_ALIASES_FILE = "data/jarvis_learned_aliases.json"

    def __init__(self):
        config = get_memory_config()

        # Memoria conversacional
        self.chat_storage = Storage(config.chat_memory_file)
        
        # Memoria predictiva
        self.predictive_config = get_predictive_config()
        self.predictive_storage = Storage(self.predictive_config.prediction_memory_file)
        
        # Nueva memoria de dominio (FASE 5)
        self.domain_memory = DomainMemory()
        
        # Sistema de planificacion
        self.goals: List[Goal] = []
        self.nodes: Dict[str, Node] = {}
        self.tasks: Dict[str, Task] = {}
        self.current_state: Dict[str, Any] = {}
        
        # Carga de aliases (compatibilidad FASE 16)
        self.command_aliases: Dict[str, str] = {}
        self.learned_aliases: Dict[str, str] = {}
        self._load_aliases()

        logger.info("Sistema de memoria inicializado para planificacion jerarquica")

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para busqueda."""
        if not isinstance(text, str):
            return ""

        text = text.strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = re.sub(r"[^a-z0-9]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _remove_wake_word(self, text: str) -> str:
        """Elimina 'jarvis' inicial."""
        normalized = self._normalize_text(text)
        if normalized == "jarvis":
            return ""
        return re.sub(r"^jarvis\s+", "", normalized).strip()

    # Cache por proceso de los aliases estaticos: el fichero tiene decenas de
    # miles de entradas y no cambia en ejecucion.
    _static_alias_cache: Optional[Dict[str, Any]] = None
    _static_alias_lock = threading.Lock()

    @staticmethod
    def _read_alias_file(path: Path) -> Dict[str, str]:
        """Lee un fichero JSON de aliases ``{frase: comando}``.

        Devuelve un diccionario vacio si el fichero no existe, no es JSON
        valido o no tiene forma de diccionario. Ignora entradas cuyo valor no
        sea texto.
        """
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            logger.error(f"[MEMORY] No se pudo leer {path}: {exc}")
            return {}
        if not isinstance(data, dict):
            logger.warning(f"[MEMORY] {path} no contiene un diccionario de aliases")
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, str) and v.strip()}

    def _build_alias_index(self, aliases: Dict[str, str]) -> Dict[str, str]:
        """Indexa los aliases por texto normalizado (sin la palabra 'jarvis')."""
        index: Dict[str, str] = {}
        for alias, command in aliases.items():
            for key in (self._normalize_text(alias), self._remove_wake_word(alias)):
                if key and key not in index:
                    index[key] = command
        return index

    def _static_aliases_path(self) -> Path:
        path = Path(self.STATIC_COMMAND_ALIASES_FILE)
        return path if path.is_absolute() else get_project_root() / path

    def _learned_aliases_path(self) -> Path:
        # Ruta relativa al directorio de trabajo, igual que el resto de la
        # memoria conversacional (en los tests queda dentro del sandbox).
        return Path(self.FALLBACK_LEARNED_ALIASES_FILE)

    def _load_aliases(self) -> None:
        """Carga los aliases estaticos (config) y los aprendidos (data)."""
        cls = type(self)
        with cls._static_alias_lock:
            if cls._static_alias_cache is None:
                static = self._read_alias_file(self._static_aliases_path())
                cls._static_alias_cache = {"aliases": static, "index": self._build_alias_index(static)}
        self.command_aliases = cls._static_alias_cache["aliases"]
        self._static_alias_index = cls._static_alias_cache["index"]

        self.learned_aliases = self._read_alias_file(self._learned_aliases_path())
        self._learned_alias_index = self._build_alias_index(self.learned_aliases)

        logger.info(f"[MEMORY] Aliases cargados: {len(self.command_aliases)} estaticos, {len(self.learned_aliases)} aprendidos")

    # ========================================================================
    # NUEVO SISTEMA: INTENCION -> OBJETIVO -> PLANIFICACION
    # ========================================================================

    def parse_user_input(self, user_input: str) -> Optional[Goal]:
        """
        Transforma entrada de usuario en objetivo (FASE 15).
        
        Ejemplo:
        "abre stream de nissaxter" -> Goal(navigate, {url: "https://twitch.tv/nissaxter"})
        """
        
        # 1. Normalizar entrada
        normalized = self._normalize_text(user_input)
        
        # 2. Extraer intencion
        intention = self._extract_intention(normalized)
        if not intention:
            logger.warning(f"[PARSER] No se pudo extraer intencion de: {user_input}")
            return None
        
        logger.debug(f"[PARSER] Intencion extraida: {intention}")
        
        # 3. Realizar razonamiento sobre el dominio (FASE 5 mejorada)
        context = {
            "intent": intention,
            "user_input": user_input,
            "current_state": self.current_state,
            "user_preferences": self.domain_memory.get_user_preferences()
        }
        
        reasoning = self.domain_memory.reason_about_entities(context)
        logger.debug(f"[PARSER] Razonamiento del dominio: {reasoning}")
        
        # 4. Mejorar intencion con razonamiento
        if reasoning["relevant_entities"]:
            intention["entity_data"] = reasoning["relevant_entities"][0]
            intention["confidence"] = reasoning["confidence"]
            intention["suggested_entities"] = reasoning["suggested_entities"]
        
        # 5. Buscar entidad en memoria de dominio con sugerencias
        entity_name = intention.get("entity", "")
        if entity_name:
            entity = self.domain_memory.get_entity(entity_name)
            if not entity and reasoning["suggested_entities"]:
                # Si no se encontro exacto, usar sugerencias
                entity = reasoning["suggested_entities"][0]
                intention["entity_data"] = entity
                intention["used_suggestion"] = True
                logger.debug(f"[PARSER] Usando sugerencia: {entity.name}")
        
        # 6. Crear objetivo (FASE 7)
        goal = self._create_goal_from_intention(intention)
        if goal:
            self.goals.append(goal)
            logger.info(f"[PARSER] Objetivo creado: {goal.id} - {goal.description}")
            
            # Registrar interaccion para aprendizaje
            self.domain_memory.record_user_interaction(
                user_input=user_input,
                entity_used=intention.get("entity"),
                action_taken=goal.type,
                success=True  # Asumir exito por ahora, se verificara despues
            )
        
        return goal

    def _extract_intention(self, normalized_text: str) -> Optional[Dict[str, Any]]:
        """Extrae intencion del texto normalizado."""
        logger.debug(f"[INTENTION] Extrayendo intencion de: {normalized_text}")
        
        # Patrones de intenciones mejorados
        patterns = {
            "abrir_aplicacion": {
                "regex": r"(abrir|abre|abreme|iniciar|inicia|launch)\s+(.+)",
                "type": "open_application",
                "confidence": 0.9
            },
            "navegar": {
                "regex": r"(navegar a|ir a|abre|abrir|visitar|go to)\s+(.+)",
                "type": "navigate",
                "confidence": 0.8
            },
            "stream": {
                "regex": r"(stream|directo|en vivo|live)\s+(.+)",
                "type": "navigate_stream",
                "confidence": 0.9
            },
            "cerrar": {
                "regex": r"(cerrar|cierra|cierrame|terminar|close)\s+(.+)",
                "type": "close_application",
                "confidence": 0.8
            },
            "buscar": {
                "regex": r"(buscar|search|find)\s+(.+)",
                "type": "search",
                "confidence": 0.7
            }
        }
        
        best_match = None
        best_confidence = 0
        
        for intent_type, pattern in patterns.items():
            match = re.search(pattern["regex"], normalized_text)
            if match:
                confidence = pattern["confidence"]
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        "type": pattern["type"],
                        "entity": match.group(2).strip(),
                        "confidence": confidence,
                        "raw_text": normalized_text
                    }
        
        if best_match:
            logger.info("Intencion reconocida")
        
        return best_match

    def _create_goal_from_intention(self, intention: Dict[str, Any]) -> Optional[Goal]:
        """Crea objetivo a partir de intencion."""
        intent_type = intention["type"]
        entity_name = intention["entity"]
        
        logger.info("Entidad procesada exitosamente")
        
        # Caso especial: stream de entidad conocida (FASE 5)
        if intent_type == "navigate_stream" and intention.get("entity_data"):
            entity = intention["entity_data"]
            url = entity.get_url()
            if url:
                return Goal(
                    id=f"navigate_stream_{entity.id}",
                    type="navigate_stream",
                    target={"url": url, "source": entity.name, "entity_id": entity.id},
                    description=f"Navegar a stream de {entity.name}",
                    priority=1,
                    constraints=["requires_browser", "requires_internet"]
                )
        
        # Aplicacion conocida
        elif intent_type == "open_application" and entity_name in self.domain_memory.applications:
            return Goal(
                id=f"open_{entity_name}",
                type="open_application",
                target=entity_name,
                description=f"Abrir {entity_name}",
                priority=1,
                constraints=["requires_application_installation"]
            )
        
        # Navegacion generica
        elif intent_type in ["navigate", "search"]:
            # Verificar si es una URL o una busqueda
            if re.match(r'https?://', entity_name):
                return Goal(
                    id=f"navigate_{entity_name}",
                    type="navigate",
                    target=entity_name,
                    description=f"Navegar a {entity_name}",
                    priority=1,
                    constraints=["requires_browser", "requires_internet"]
                )
            else:
                return Goal(
                    id=f"search_{entity_name}",
                    type="search",
                    target=entity_name,
                    description=f"Buscar {entity_name}",
                    priority=1,
                    constraints=["requires_browser", "requires_internet"]
                )
        
        # Cerrar aplicacion
        elif intent_type == "close_application" and entity_name in self.domain_memory.applications:
            return Goal(
                id=f"close_{entity_name}",
                type="close_application",
                target=entity_name,
                description=f"Cerrar {entity_name}",
                priority=1,
                constraints=["requires_application_open"]
            )
        
        logger.warning(f"[GOAL_CREATOR] No se pudo crear objetivo para: {intention}")
        return None

    def create_plan_from_goal(self, goal: Goal) -> Optional[List[str]]:
        """
        Crea un plan a partir de un objetivo (FASE 6, 7).
        
        Devuelve lista de nodos IDs que conforman el plan.
        """
        logger.info(f"[PLANNER] Creando plan para objetivo: {goal.id}")
        
        # Ejemplos de planes basicos
        if goal.type == "navigate_stream" and isinstance(goal.target, dict):
            # Plan: abrir navegador -> navegar a URL
            return [
                "chrome.open",
                "chrome.activate", 
                "chrome.address_bar_focus",
                "chrome.type_url",
                "chrome.press_enter"
            ]
        
        elif goal.type == "open_application":
            # Plan: abrir aplicacion
            return [f"{goal.target}.open"]
        
        elif goal.type == "navigate":
            # Plan: navegar a URL
            return [
                "chrome.open",
                "chrome.activate",
                "chrome.address_bar_focus", 
                "chrome.type_url",
                "chrome.press_enter"
            ]
        
        logger.warning(f"[PLANNER] No se pudo crear plan para objetivo: {goal.id}")
        return None

    # ========================================================================
    # GESTION DE ESTADO DEL MUNDO (FASE 3)
    # ========================================================================

    def update_world_state(self, state_update: Dict[str, Any]) -> None:
        """Actualiza el estado del mundo."""
        logger.debug(f"[STATE] Actualizando estado: {state_update}")
        self.current_state.update(state_update)
        
        # Verificar objetivos alcanzados
        self._check_achieved_goals()
    
    def add_user_message(self, user_text: str) -> None:
        """Anade mensaje de usuario a la memoria conversacional (compatibilidad)."""
        # Guardar en memoria conversacional
        self.save_conversation(
            user_text=user_text,
            assistant_text="",
            goal=None,
            plan=None,
            execution_result=None
        )

    def get_current_state(self) -> Dict[str, Any]:
        """Obtiene estado actual del mundo."""
        return self.current_state.copy()

    def _check_achieved_goals(self) -> None:
        """Verifica si algun objetivo ha sido alcanzado."""
        for goal in self.goals[:]:  # Copia para poder modificar
            if goal.is_achieved(self.current_state):
                logger.info(f"[GOAL] Objetivo alcanzado: {goal.id}")
                # Aqui se podria notificar al sistema o ejecutar acciones
            elif goal.is_expired():
                logger.warning(f"[GOAL] Objetivo expirado: {goal.id}")
                self.goals.remove(goal)

    # ========================================================================
    # GESTION DE NODOS Y TAREAS (FASE 1, 2)
    # ========================================================================

    def create_node(self, node_config: Dict[str, Any]) -> Node:
        """Crea un nodo en el sistema de planificacion."""
        node = Node(
            id=node_config["id"],
            type=NodeType(node_config["type"]),
            name=node_config["name"],
            description=node_config.get("description", ""),
            preconditions=node_config.get("preconditions", []),
            effects=node_config.get("effects", []),
            cost=node_config.get("cost", 1.0),
            dependencies=node_config.get("dependencies", []),
            parameters=node_config.get("parameters", {}),
            application=node_config.get("application"),
            ui_element=node_config.get("ui_element"),
            metadata=node_config.get("metadata", {})
        )
        self.nodes[node.id] = node
        logger.debug(f"[NODE] Creado nodo: {node.id}")
        return node

    def create_task(self, task_config: Dict[str, Any]) -> Task:
        """Crea una tarea jerarquica."""
        task = Task(
            id=task_config["id"],
            name=task_config["name"],
            description=task_config.get("description", ""),
            dependencies=task_config.get("dependencies", [])
        )
        self.tasks[task.id] = task
        logger.debug(f"[TASK] Creada tarea: {task.id}")
        return task

    def get_applicable_nodes(self, current_state: Dict[str, Any]) -> List[Node]:
        """Obtiene nodos aplicables en el estado actual."""
        applicable = [node for node in self.nodes.values() if node.can_execute(current_state)]
        logger.info(f"Encontrados {len(applicable)} nodos aplicables")
        return applicable


# ========================================================================
# MANTENIMIENTO DE COMPATIBILIDAD (FASE 16)
# ========================================================================

    def get_alias(self, transcribed_text: str) -> Optional[str]:
        """Devuelve el comando asociado a una frase conocida, o ``None``.

        Busca primero en los aliases aprendidos (los ha confirmado el uso real)
        y despues en los estaticos. Compara el texto normalizado, con y sin la
        palabra de activacion 'jarvis'. Siempre devuelve un nombre de comando
        ejecutable, nunca un identificador de objetivo.
        """
        if not isinstance(transcribed_text, str) or not transcribed_text.strip():
            return None
        keys = [self._normalize_text(transcribed_text), self._remove_wake_word(transcribed_text)]
        for index in (getattr(self, "_learned_alias_index", {}), getattr(self, "_static_alias_index", {})):
            for key in keys:
                if key and key in index:
                    return index[key]
        return None

    def save_alias(self, transcribed_text: str, command: str) -> bool:
        """Aprende que una frase corresponde a un comando y lo guarda en disco.

        No guarda nada si la frase o el comando estan vacios, si el comando no
        es un nombre de accion simple o si la frase ya apunta a ese comando.
        La escritura es atomica (fichero temporal + reemplazo).
        """
        if not isinstance(transcribed_text, str) or not isinstance(command, str):
            return False
        phrase = self._remove_wake_word(transcribed_text)
        command = command.strip()
        if not phrase or not re.fullmatch(r"[A-Za-z0-9_]+", command):
            return False
        if self.get_alias(phrase) == command:
            return True

        self.learned_aliases[phrase] = command
        self._learned_alias_index[phrase] = command

        path = self._learned_aliases_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.learned_aliases, handle, ensure_ascii=False, indent=2, sort_keys=True)
                os.replace(tmp_name, path)
            except BaseException:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                raise
        except OSError as exc:
            logger.error(f"[MEMORY] No se pudo guardar el alias aprendido: {exc}")
            return False
        logger.info(f"[MEMORY] Alias aprendido: '{phrase}' -> {command}")
        return True

    def record_command_usage(self, user_input: str, command_executed: str, success: bool = True) -> None:
        """
        Registra uso de comando para analisis predictivo (compatibilidad).
        """
        if not self.predictive_config.enabled:
            return

        timestamp = time.time()
        
        # Registrar en formato antiguo (compatibilidad)
        if not hasattr(self, "command_usage_stats"):
            self.command_usage_stats = defaultdict(int)
        
        self.command_usage_stats[command_executed] += 1
        
        # Registrar en nuevo formato
        if not hasattr(self, "execution_events"):
            self.execution_events = []
        
        execution_event = {
            "timestamp": timestamp,
            "user_input": user_input,
            "command": command_executed,
            "success": success,
            "state": self.current_state.copy(),
            "goals": [goal.id for goal in self.goals]
        }
        
        self.execution_events.append(execution_event)
        
        logger.debug(f"[COMPAT] Comando registrado: {command_executed} (exitoso: {success})")

    # ========================================================================
    # PERSISTENCIA Y CARGA
    # ========================================================================

    def _chat_history_path(self) -> Path:
        return self.chat_storage.get_file_path(MemoryType.CONVERSATIONAL)

    @staticmethod
    def _deduplicate_history(history: List[Any]) -> List[Dict[str, Any]]:
        """Quita entradas repetidas (mismo rol, texto y marca de tiempo)."""
        seen = set()
        result: List[Dict[str, Any]] = []
        for entry in history:
            if not isinstance(entry, dict):
                continue
            key = (entry.get("role"), entry.get("content"), entry.get("timestamp"))
            if key in seen:
                continue
            seen.add(key)
            result.append(entry)
        return result

    def _read_chat_history(self) -> List[Dict[str, Any]]:
        path = self._chat_history_path()
        if not path.is_file():
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            logger.error(f"[MEMORY] Historial ilegible en {path}: {exc}")
            return []
        return self._deduplicate_history(data) if isinstance(data, list) else []

    def _write_chat_history(self, history: List[Dict[str, Any]]) -> bool:
        """Reemplaza el fichero de historial completo de forma atomica."""
        path = self._chat_history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(history, handle, ensure_ascii=False, indent=2, default=str)
                os.replace(tmp_name, path)
            except BaseException:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                raise
            return True
        except OSError as exc:
            logger.error(f"[MEMORY] No se pudo guardar el historial: {exc}")
            return False

    def save_conversation(
        self,
        user_text: str,
        assistant_text: str,
        goal: Optional[Goal] = None,
        plan: Optional[List[str]] = None,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Anade un turno (usuario + asistente) al historial y lo guarda.

        El fichero se reescribe entero con los ultimos
        ``max_history_length * 2`` mensajes, sin duplicar entradas anteriores.
        """
        if not user_text or not assistant_text:
            logger.warning("Intento de guardar conversacion con texto vacio")
            return False

        try:
            history = self._read_chat_history()
            now = time.time()
            history.append({
                "role": "user",
                "content": user_text,
                "timestamp": now,
                "intention_parsed": goal is not None,
                "goal_id": goal.id if goal else None,
                "goal_type": goal.type if goal else None,
                "goal_target": goal.target if goal else None,
                "plan_generated": plan is not None,
                "plan_steps": plan,
                "system_state": self.current_state.copy(),
                "active_goals": [g.id for g in self.goals]
            })
            history.append({
                "role": "assistant",
                "content": assistant_text,
                "timestamp": now,
                "execution_result": execution_result,
                "system_state": self.current_state.copy()
            })

            max_length = get_memory_config().max_history_length * 2
            if max_length > 0 and len(history) > max_length:
                history = history[-max_length:]

            return self._write_chat_history(history)

        except Exception as e:
            logger.error(f"[MEMORY] Error guardando conversacion: {e}")
            return False

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Devuelve el historial guardado, sin entradas duplicadas."""
        return self._read_chat_history()

    def clear_history(self) -> bool:
        """Borra el historial de conversaciones."""
        return self._write_chat_history([])

    def clear_predictive_data(self) -> bool:
        """Borra datos predictivos."""
        try:
            if hasattr(self, "command_usage_stats"):
                self.command_usage_stats.clear()
            if hasattr(self, "execution_events"):
                self.execution_events.clear()
            return self.predictive_storage.save({})
        except Exception as e:
            logger.debug("ConversationMemory.clear_predictive_data: %s", e)
            return False

    def get_learning_insights(self) -> Dict[str, Any]:
        """Obtiene insights de aprendizaje del nuevo sistema."""
        insights = {
            # Sistema nuevo
            "domain_entities_loaded": len(self.domain_memory.entities),
            "applications_loaded": len(self.domain_memory.applications),
            "capabilities_loaded": len(self.domain_memory.capabilities),
            "nodes_created": len(self.nodes),
            "tasks_created": len(self.tasks),
            "goals_generated": len(self.goals),
            "current_state_keys": len(self.current_state),
            
            # Estadisticas de planificacion
            "total_goals_created": len(self.goals),
            "completed_goals": sum(1 for goal in self.goals if goal.is_achieved(self.current_state)),
            "expired_goals": sum(1 for goal in self.goals if goal.is_expired()),
            
            # Compatibilidad
            "static_aliases_loaded": len(self.command_aliases),
            "learned_aliases_loaded": len(self.learned_aliases),
            
            # FASE 5 - Domain Memory mejorada
            "user_preferences_loaded": len(self.domain_memory.preferences),
            "user_interactions_recorded": len(self.domain_memory.user_interactions),
            "knowledge_updates_pending": len(self.domain_memory.knowledge_updates),
            "preferred_entities_count": len(self.domain_memory.preferences.get("preferred_entities", [])),
            "preferred_apps_count": len(self.domain_memory.preferences.get("preferred_app", {})),
            
            # Razonamiento del dominio
            "reasoning_sessions": 0,  # Se incrementa al usar reason_about_entities
            "suggestions_provided": 0,  # Se incrementa al usar get_suggested_entities
        }
        
        # Compatibilidad con insights antiguos
        if hasattr(self, "command_usage_stats"):
            insights.update({
                "total_commands_executed": sum(self.command_usage_stats.values()),
                "unique_commands_learned": len(self.command_usage_stats),
                "most_used_commands": sorted(
                    self.command_usage_stats.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            })
        
        return insights
    
    def save_domain_knowledge_persistence(self) -> bool:
        """
        Guarda el estado completo del conocimiento de dominio para persistencia.
        Implementa la separacion entre memoria conversacional y conocimiento permanente.
        """
        try:
            # Crear estructura de persistencia
            persistence_data = {
                "version": "1.0",
                "timestamp": time.time(),
                "entities": {
                    entity_id: {
                        "id": entity.id,
                        "name": entity.name,
                        "type": entity.type,
                        "attributes": entity.attributes,
                        "aliases": entity.aliases,
                        "created_at": entity.created_at,
                        "last_accessed": time.time()  # Nuevo: seguimiento de acceso
                    }
                    for entity_id, entity in self.domain_memory.entities.items()
                },
                "applications": self.domain_memory.applications,
                "capabilities": self.domain_memory.capabilities,
                "user_preferences": self.domain_memory.preferences,
                "user_interactions_summary": {
                    "total_interactions": len(self.domain_memory.user_interactions),
                    "successful_interactions": sum(
                        1 for interaction in self.domain_memory.user_interactions 
                        if interaction["success"]
                    ),
                    "most_used_entities": self._get_most_used_entities(),
                    "most_used_actions": self._get_most_used_actions()
                },
                "knowledge_updates": [
                    {
                        "timestamp": update["timestamp"],
                        "type": update["type"],
                        "verified": update["verified"]
                    }
                    for update in self.domain_memory.knowledge_updates
                ]
            }
            
            # Guardar archivo de persistencia
            persistence_path = get_project_root() / "data" / "domain_knowledge_persistence.json"
            with open(persistence_path, "w", encoding="utf-8") as f:
                json.dump(persistence_data, f, indent=2, ensure_ascii=False)
            
            logger.info("[DOMAIN] Conocimiento de dominio persistido exitosamente")
            return True
            
        except Exception as e:
            logger.debug("ConversationMemory.save_domain_knowledge_persistence: %s", e)
            return False
    
    def _get_most_used_entities(self) -> List[Dict[str, Any]]:
        """Obtiene las entidades mas usadas basadas en interacciones."""
        entity_usage = Counter()
        
        for interaction in self.domain_memory.user_interactions:
            if interaction.get("entity_used"):
                entity_usage[interaction["entity_used"]] += 1
        
        return [
            {"entity_id": entity_id, "usage_count": count}
            for entity_id, count in entity_usage.most_common(5)
        ]
    
    def _get_most_used_actions(self) -> List[Dict[str, Any]]:
        """Obtiene las acciones mas usadas basadas en interacciones."""
        action_usage = Counter()
        
        for interaction in self.domain_memory.user_interactions:
            action_usage[interaction["action_taken"]] += 1
        
        return [
            {"action": action, "usage_count": count}
            for action, count in action_usage.most_common(5)
        ]
    
    def load_domain_knowledge_persistence(self) -> bool:
        """
        Carga conocimiento de dominio persistido.
        """
        try:
            persistence_path = get_project_root() / "data" / "domain_knowledge_persistence.json"
            if not persistence_path.exists():
                logger.info("[DOMAIN] No existe archivo de persistencia, usando datos base")
                return True
            
            with open(persistence_path, "r", encoding="utf-8") as f:
                persistence_data = json.load(f)
            
            # Cargar entidades con informacion de acceso
            if "entities" in persistence_data:
                for entity_id, entity_data in persistence_data["entities"].items():
                    if entity_id in self.domain_memory.entities:
                        # Actualizar timestamp de ultima vez accesada
                        self.domain_memory.entities[entity_id].created_at = entity_data.get("last_accessed", time.time())
            
            # Cargar preferencias actualizadas
            if "user_preferences" in persistence_data:
                self.domain_memory.preferences.update(persistence_data["user_preferences"])
            
            logger.info("[DOMAIN] Conocimiento de dominio persistido cargado exitosamente")
            return True
            
        except Exception as e:
            logger.debug("ConversationMemory.load_domain_knowledge_persistence: %s", e)
            return False