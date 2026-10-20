"""
Memoria de conversaciones y sistema de planificación jerárquica.
Transforma el sistema de texto→comando→función a intención→objetivo→plan→ejecución.

Cumple con:
- FASE 1: Modelo de nodos
- FASE 2: Nodos jerárquicos  
- FASE 5: Memoria de dominio
- FASE 15: Comandos de alto nivel
- FASE 16: Compatibilidad
"""

import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from .storage import MemoryManager, Entity as StorageEntity, JSONStorage as Storage, MemoryType
from src.utils.config import (
    get_memory_config,
    get_predictive_config,
    get_project_root,
)
from src.utils.logger import get_logger


# Clases básicas para evitar importaciones circulares
class NodeType(Enum):
    """Tipos de nodos en el sistema de planificación."""
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
    """Estado de ejecución de tareas."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class Node:
    """Modelo básico de nodo para memoria."""
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
    """Modelo básico de objetivo para memoria."""
    id: str
    type: str
    target: any
    description: str
    priority: int = 1
    constraints: list = field(default_factory=list)
    created_at: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class Task:
    """Modelo básico de tarea para memoria."""
    id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    nodes: list = field(default_factory=list)
    parent: str = None

logger = get_logger(__name__)





@dataclass
class Task:
    """Tarea jerárquica (FASE 2)."""
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
        logger._print_log("info", "[DOMAIN] Cargando conocimiento del dominio...", "conversation.py", "method", 145)
        
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
                logger._print_log("info", f"[DOMAIN] Cargadas {len(self.entities)} entidades", "conversation.py", "method", 166)
        except Exception as e:
            logger._print_log("error", f"[DOMAIN] Error cargando entidades: {e}", "conversation.py", "method", 168)
        
        # Cargar aplicaciones
        try:
            apps_path = get_project_root() / "data" / "knowledge" / "applications.json"
            if apps_path.exists():
                with open(apps_path, "r", encoding="utf-8") as f:
                    self.applications = json.load(f)
                logger._print_log("info", f"[DOMAIN] Cargadas {len(self.applications)} aplicaciones", "conversation.py", "method", 176)
        except Exception as e:
            logger._print_log("error", f"[DOMAIN] Error cargando aplicaciones: {e}", "conversation.py", "method", 178)
        
        # Cargar capacidades
        try:
            caps_path = get_project_root() / "data" / "knowledge" / "capabilities.json"
            if caps_path.exists():
                with open(caps_path, "r", encoding="utf-8") as f:
                    self.capabilities = json.load(f)
                logger._print_log("info", f"[DOMAIN] Cargadas {len(self.capabilities)} categorías de capacidades", "conversation.py", "method", 186)
        except Exception as e:
            logger._print_log("error", f"[DOMAIN] Error cargando capacidades: {e}", "conversation.py", "method", 188)
    
    def load_user_preferences(self) -> None:
        """Carga preferencias del usuario desde archivo persistente."""
        try:
            prefs_path = get_project_root() / "data" / "user_preferences.json"
            if prefs_path.exists():
                with open(prefs_path, "r", encoding="utf-8") as f:
                    self.preferences = json.load(f)
                logger._print_log("info", f"[DOMAIN] Cargadas preferencias del usuario", "conversation.py", "method", 197)
        except Exception as e:
            logger._print_log("error", f"[DOMAIN] Error cargando preferencias: {e}", "conversation.py", "method", 199)
            self.preferences = {}
    
    def save_user_preferences(self) -> bool:
        """Guarda preferencias del usuario de forma persistente."""
        try:
            prefs_path = get_project_root() / "data" / "user_preferences.json"
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2, ensure_ascii=False)
            logger._print_log("info", "Preferencias guardadas exitosamente", "conversation.py", "method", 208)
            return True
        except Exception as e:
            logger._print_log("error", f"Error guardando preferencias: {e}", "conversation.py", "method", 211)
            return False
    
    def get_entity(self, entity_name: str) -> Optional[Entity]:
        """Obtiene una entidad por nombre o alias."""
        for entity in self.entities.values():
            if entity.matches_name(entity_name):
                logger._print_log("info", f"Entidad encontrada: {entity.name} ({entity.id})", "conversation.py", "method", 218)
                return entity
        logger._print_log("debug", f"Entidad no encontrada: {entity_name}", "conversation.py", "method", 220)
        return None
    
    def get_application_capabilities(self, app_name: str) -> List[str]:
        """Obtiene capacidades de una aplicación."""
        return self.capabilities.get(app_name, [])
    
    def get_capability_definition(self, category: str, capability: str) -> Optional[Dict[str, Any]]:
        """Obtiene definición detallada de una capacidad."""
        category_caps = self.capabilities.get(category, {})
        return category_caps.get(capability)
    
    def record_user_interaction(self, user_input: str, entity_used: Optional[str], 
                               action_taken: str, success: bool) -> None:
        """Registra interacción del usuario para aprendizaje y preferencias."""
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
        
        logger._print_log("debug", f"Interacción registrada: {action_taken} (exitosa: {success})", "conversation.py", "method", 249)
    
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
        """Obtiene aplicación preferida para un tipo de acción."""
        preferred_apps = self.preferences.get("preferred_app", {})
        
        # Obtener aplicaciones que soportan esta acción
        suitable_apps = []
        for app_name, app_info in preferred_apps.items():
            if app_name in self.applications:
                app_caps = self.capabilities.get(app_name, [])
                if action_type in app_caps:
                    suitable_apps.append((app_name, app_info))
        
        # Ordenar por uso y devolver la más usada
        suitable_apps.sort(key=lambda x: x[1]["usage_count"], reverse=True)
        
        if suitable_apps:
            return suitable_apps[0][0]
        
        return None
    
    def add_knowledge_update(self, update_type: str, content: Dict[str, Any]) -> None:
        """Añade actualización de conocimiento para persistencia futura."""
        update = {
            "timestamp": time.time(),
            "type": update_type,
            "content": content,
            "verified": False
        }
        self.knowledge_updates.append(update)
        logger._print_log("info", f"[DOMAIN] Actualización de conocimiento registrada: {update_type}", "conversation.py", "method", 336)
    
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
        """Realiza razonamiento básico sobre entidades basado en contexto y preferencias."""
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
        """Normaliza texto para búsqueda."""
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
    Sistema de memoria transformado para planificación jerárquica.
    
    Implementa:
    - FASE 1: Modelo de nodos
    - FASE 2: Nodos jerárquicos
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
        
        # Sistema de planificación
        self.goals: List[Goal] = []
        self.nodes: Dict[str, Node] = {}
        self.tasks: Dict[str, Task] = {}
        self.current_state: Dict[str, Any] = {}
        
        # Carga de aliases (compatibilidad FASE 16)
        self.command_aliases: Dict[str, str] = {}
        self.learned_aliases: Dict[str, str] = {}
        self._load_aliases()

        logger._print_log("info", "Sistema de memoria inicializado para planificación jerárquica", "conversation.py", "method", 447)

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para búsqueda."""
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

    def _load_aliases(self) -> None:
        """Carga aliases (mantener compatibilidad FASE 16)."""
        logger._print_log("info", "[MEMORY] Cargando aliases para compatibilidad...", "conversation.py", "method", 470)
        
        # Cargar aliases estáticos
        try:
            static_storage = Storage(self.STATIC_COMMAND_ALIASES_FILE)
            aliases = static_storage.load(MemoryType.CONVERSATIONAL)
            
            if isinstance(aliases, dict):
                self.command_aliases = aliases
                logger._print_log("info", f"[MEMORY] Cargados {len(self.command_aliases, "conversation.py", "method", 479)} aliases estáticos")
            else:
                self.command_aliases = {}
        except Exception as e:
            logger._print_log("error", f"[MEMORY] Error cargando command_aliases.json: {e}", "conversation.py", "method", 483)
            self.command_aliases = {}

        # Cargar aliases aprendidos
        try:
            learned_storage = Storage(self.FALLBACK_LEARNED_ALIASES_FILE)
            learned = learned_storage.load(MemoryType.CONVERSATIONAL)
            
            if isinstance(learned, dict):
                self.learned_aliases = learned
                logger._print_log("info", f"[MEMORY] Cargados {len(self.learned_aliases, "conversation.py", "method", 493)} aliases aprendidos")
        except Exception as e:
            logger._print_log("error", f"[MEMORY] Error cargando aliases aprendidos: {e}", "conversation.py", "method", 495)
            self.learned_aliases = {}

    # ========================================================================
    # NUEVO SISTEMA: INTENCIÓN → OBJETIVO → PLANIFICACIÓN
    # ========================================================================

    def parse_user_input(self, user_input: str) -> Optional[Goal]:
        """
        Transforma entrada de usuario en objetivo (FASE 15).
        
        Ejemplo:
        "abre stream de nissaxter" → Goal(navigate, {url: "https://twitch.tv/nissaxter"})
        """
        logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
        
        # 1. Normalizar entrada
        normalized = self._normalize_text(user_input)
        
        # 2. Extraer intención
        intention = self._extract_intention(normalized)
        if not intention:
            logger._print_log("warning", f"[PARSER] No se pudo extraer intención de: {user_input}", "conversation.py", "method", 517)
            return None
        
        logger._print_log("debug", f"[PARSER] Intención extraída: {intention}", "conversation.py", "method", 520)
        
        # 3. Realizar razonamiento sobre el dominio (FASE 5 mejorada)
        context = {
            "intent": intention,
            "user_input": user_input,
            "current_state": self.current_state,
            "user_preferences": self.domain_memory.get_user_preferences()
        }
        
        reasoning = self.domain_memory.reason_about_entities(context)
        logger._print_log("debug", f"[PARSER] Razonamiento del dominio: {reasoning}", "conversation.py", "method", 531)
        
        # 4. Mejorar intención con razonamiento
        if reasoning["relevant_entities"]:
            intention["entity_data"] = reasoning["relevant_entities"][0]
            intention["confidence"] = reasoning["confidence"]
            intention["suggested_entities"] = reasoning["suggested_entities"]
        
        # 5. Buscar entidad en memoria de dominio con sugerencias
        entity_name = intention.get("entity", "")
        if entity_name:
            entity = self.domain_memory.get_entity(entity_name)
            if not entity and reasoning["suggested_entities"]:
                # Si no se encontró exacto, usar sugerencias
                entity = reasoning["suggested_entities"][0]
                intention["entity_data"] = entity
                intention["used_suggestion"] = True
                logger._print_log("debug", f"[PARSER] Usando sugerencia: {entity.name}", "conversation.py", "method", 548)
        
        # 6. Crear objetivo (FASE 7)
        goal = self._create_goal_from_intention(intention)
        if goal:
            self.goals.append(goal)
            logger._print_log("info", f"[PARSER] Objetivo creado: {goal.id} - {goal.description}", "conversation.py", "method", 554)
            
            # Registrar interacción para aprendizaje
            self.domain_memory.record_user_interaction(
                user_input=user_input,
                entity_used=intention.get("entity"),
                action_taken=goal.type,
                success=True  # Asumir éxito por ahora, se verificará después
            )
        
        return goal

    def _extract_intention(self, normalized_text: str) -> Optional[Dict[str, Any]]:
        """Extrae intención del texto normalizado."""
        logger._print_log("debug", f"[INTENTION] Extrayendo intención de: {normalized_text}", "conversation.py", "method", 568)
        
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
            logger._print_log("info", "Intención reconocida", "conversation.py", "extract_intention", 616)
        
        return best_match

    def _create_goal_from_intention(self, intention: Dict[str, Any]) -> Optional[Goal]:
        """Crea objetivo a partir de intención."""
        intent_type = intention["type"]
        entity_name = intention["entity"]
        
        logger._print_log("info", "Entidad procesada exitosamente", "conversation.py", "learn_intention", 625)
        
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
        
        # Aplicación conocida
        elif intent_type == "open_application" and entity_name in self.domain_memory.applications:
            return Goal(
                id=f"open_{entity_name}",
                type="open_application",
                target=entity_name,
                description=f"Abrir {entity_name}",
                priority=1,
                constraints=["requires_application_installation"]
            )
        
        # Navegación genérica
        elif intent_type in ["navigate", "search"]:
            # Verificar si es una URL o una búsqueda
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
        
        # Cerrar aplicación
        elif intent_type == "close_application" and entity_name in self.domain_memory.applications:
            return Goal(
                id=f"close_{entity_name}",
                type="close_application",
                target=entity_name,
                description=f"Cerrar {entity_name}",
                priority=1,
                constraints=["requires_application_open"]
            )
        
        logger._print_log("warning", f"[GOAL_CREATOR] No se pudo crear objetivo para: {intention}", "conversation.py", "method", 685)
        return None

    def create_plan_from_goal(self, goal: Goal) -> Optional[List[str]]:
        """
        Crea un plan a partir de un objetivo (FASE 6, 7).
        
        Devuelve lista de nodos IDs que conforman el plan.
        """
        logger._print_log("info", f"[PLANNER] Creando plan para objetivo: {goal.id}", "conversation.py", "method", 694)
        
        # Ejemplos de planes básicos
        if goal.type == "navigate_stream" and isinstance(goal.target, dict):
            # Plan: abrir navegador → navegar a URL
            return [
                "chrome.open",
                "chrome.activate", 
                "chrome.address_bar_focus",
                "chrome.type_url",
                "chrome.press_enter"
            ]
        
        elif goal.type == "open_application":
            # Plan: abrir aplicación
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
        
        logger._print_log("warning", f"[PLANNER] No se pudo crear plan para objetivo: {goal.id}", "conversation.py", "method", 721)
        return None

    # ========================================================================
    # GESTIÓN DE ESTADO DEL MUNDO (FASE 3)
    # ========================================================================

    def update_world_state(self, state_update: Dict[str, Any]) -> None:
        """Actualiza el estado del mundo."""
        logger._print_log("debug", f"[STATE] Actualizando estado: {state_update}", "conversation.py", "method", 730)
        self.current_state.update(state_update)
        
        # Verificar objetivos alcanzados
        self._check_achieved_goals()
    
    def add_user_message(self, user_text: str) -> None:
        """Añade mensaje de usuario a la memoria conversacional (compatibilidad)."""
        logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
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
        """Verifica si algún objetivo ha sido alcanzado."""
        for goal in self.goals[:]:  # Copia para poder modificar
            if goal.is_achieved(self.current_state):
                logger._print_log("info", f"[GOAL] Objetivo alcanzado: {goal.id}", "conversation.py", "method", 756)
                # Aquí se podría notificar al sistema o ejecutar acciones
            elif goal.is_expired():
                logger._print_log("warning", f"[GOAL] Objetivo expirado: {goal.id}", "conversation.py", "method", 759)
                self.goals.remove(goal)

    # ========================================================================
    # GESTIÓN DE NODOS Y TAREAS (FASE 1, 2)
    # ========================================================================

    def create_node(self, node_config: Dict[str, Any]) -> Node:
        """Crea un nodo en el sistema de planificación."""
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
        logger._print_log("debug", f"[NODE] Creado nodo: {node.id}", "conversation.py", "method", 783)
        return node

    def create_task(self, task_config: Dict[str, Any]) -> Task:
        """Crea una tarea jerárquica."""
        task = Task(
            id=task_config["id"],
            name=task_config["name"],
            description=task_config.get("description", ""),
            dependencies=task_config.get("dependencies", [])
        )
        self.tasks[task.id] = task
        logger._print_log("debug", f"[TASK] Creada tarea: {task.id}", "conversation.py", "method", 795)
        return task

    def get_applicable_nodes(self, current_state: Dict[str, Any]) -> List[Node]:
        """Obtiene nodos aplicables en el estado actual."""
        applicable = [node for node in self.nodes.values() if node.can_execute(current_state)]
        logger._print_log("info", f"Encontrados {len(applicable)} nodos aplicables", "conversation.py", "get_applicable_nodes", 801)
        return applicable


# ========================================================================
# MANTENIMIENTO DE COMPATIBILIDAD (FASE 16)
# ========================================================================

    def get_alias(self, transcribed_text: str) -> Optional[str]:
        """
        Método de compatibilidad para aliases antiguos.
        
        Transforma alias antiguo a objetivo nuevo cuando sea posible.
        """
        logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
        
        # Lógica antigua
        normalized = self._normalize_text(transcribed_text)
        
        # Buscar en aliases estáticos
        for alias, command in self.command_aliases.items():
            if self._normalize_text(alias) == normalized:
                logger._print_log("info", f"Alias encontrado: {alias} -> {command}", "conversation.py", "method", 823)
                
                # Intentar transformar a nuevo sistema
                goal = self.parse_user_input(transcribed_text)
                if goal:
                    logger._print_log("info", "Transformación a nuevo sistema exitosa", "conversation.py", "parse_command_aliases", 828)
                    return f"GOAL:{goal.id}"
                
                return command
        
        # Buscar en aliases aprendidos
        for alias, command in self.learned_aliases.items():
            if self._normalize_text(alias) == normalized:
                logger._print_log("info", "Alias aprendido procesado", "conversation.py", "parse_command_aliases", 836)
                
                # Intentar transformar a nuevo sistema
                goal = self.parse_user_input(transcribed_text)
                if goal:
                    logger._print_log("info", "Alias aprendido transformado a sistema nuevo", "conversation.py", "parse_command_aliases", 841)
                    return f"GOAL:{goal.id}"
                
                return command
        
        return None

    def record_command_usage(self, user_input: str, command_executed: str, success: bool = True) -> None:
        """
        Registra uso de comando para análisis predictivo (compatibilidad).
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
        
        logger._print_log("debug", f"[COMPAT] Comando registrado: {command_executed} (exitoso: {success})", "conversation.py", "method", 878)

    # ========================================================================
    # PERSISTENCIA Y CARGA
    # ========================================================================

    def save_conversation(
        self,
        user_text: str,
        assistant_text: str,
        goal: Optional[Goal] = None,
        plan: Optional[List[str]] = None,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Guarda conversación con información de planificación.
        """
        if not user_text or not assistant_text:
            logger.WARNING(f"Intento de guardar conversación con texto vacío  [file:conversation.py, method:save_conversation, line:896]")
            return False

        try:
            history = self.chat_storage.load(MemoryType.CONVERSATIONAL)
            if not isinstance(history, list):
                history = []

            config = get_memory_config()
            max_length = config.max_history_length * 2

            if len(history) >= max_length:
                history = history[-max_length:]

            # Nueva estructura con información de planificación
            conversation_entry = {
                "role": "user",
                "content": user_text,
                "timestamp": time.time(),
                "intention_parsed": goal is not None,
                "goal_id": goal.id if goal else None,
                "goal_type": goal.type if goal else None,
                "goal_target": goal.target if goal else None,
                "plan_generated": plan is not None,
                "plan_steps": plan,
                "system_state": self.current_state.copy(),
                "active_goals": [g.id for g in self.goals]
            }

            history.append(conversation_entry)

            history.append({
                "role": "assistant",
                "content": assistant_text,
                "timestamp": time.time(),
                "execution_result": execution_result,
                "system_state": self.current_state.copy()
            })

            return self.chat_storage.save(history, MemoryType.CONVERSATIONAL)

        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
            return False

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Obtiene historial con información de planificación."""
        try:
            history = self.chat_storage.load(MemoryType.CONVERSATIONAL)
            if not isinstance(history, list):
                return []
            return history
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
            return []

    def clear_history(self) -> bool:
        """Borra historial de conversaciones."""
        try:
            return self.chat_storage.save([])
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
            return False

    def clear_predictive_data(self) -> bool:
        """Borra datos predictivos."""
        try:
            if hasattr(self, "command_usage_stats"):
                self.command_usage_stats.clear()
            if hasattr(self, "execution_events"):
                self.execution_events.clear()
            return self.predictive_storage.save({})
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
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
            
            # Estadísticas de planificación
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
        Implementa la separación entre memoria conversacional y conocimiento permanente.
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
            
            logger._print_log("info", "[DOMAIN] Conocimiento de dominio persistido exitosamente", "conversation.py", "method", 1068)
            return True
            
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
            return False
    
    def _get_most_used_entities(self) -> List[Dict[str, Any]]:
        """Obtiene las entidades más usadas basadas en interacciones."""
        entity_usage = Counter()
        
        for interaction in self.domain_memory.user_interactions:
            if interaction.get("entity_used"):
                entity_usage[interaction["entity_used"]] += 1
        
        return [
            {"entity_id": entity_id, "usage_count": count}
            for entity_id, count in entity_usage.most_common(5)
        ]
    
    def _get_most_used_actions(self) -> List[Dict[str, Any]]:
        """Obtiene las acciones más usadas basadas en interacciones."""
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
                logger._print_log("info", "[DOMAIN] No existe archivo de persistencia, usando datos base", "conversation.py", "method", 1107)
                return True
            
            with open(persistence_path, "r", encoding="utf-8") as f:
                persistence_data = json.load(f)
            
            # Cargar entidades con información de acceso
            if "entities" in persistence_data:
                for entity_id, entity_data in persistence_data["entities"].items():
                    if entity_id in self.domain_memory.entities:
                        # Actualizar timestamp de última vez accesada
                        self.domain_memory.entities[entity_id].created_at = entity_data.get("last_accessed", time.time())
            
            # Cargar preferencias actualizadas
            if "user_preferences" in persistence_data:
                self.domain_memory.preferences.update(persistence_data["user_preferences"])
            
            logger._print_log("info", "[DOMAIN] Conocimiento de dominio persistido cargado exitosamente", "conversation.py", "method", 1124)
            return True
            
        except Exception as e:
            logger._print_log("info", "Procesando solicitud", "conversation.py", "method", 509)
            return False