"""
Memoria predictiva mejorada para sistema de planificación jerárquica.
Integra predicciones con el nuevo sistema de intenciones y objetivos.

Cumple con:
- FASE 5: Memoria de dominio (mejorada)
- FASE 15: Comandos de alto nivel
- FASE 16: Compatibilidad
- FASE 17: Optimización
- FASE 18: Aprendizaje
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import statistics

from src.utils.config import get_project_root
from src.utils.logger import get_logger
from src.memory.conversation import Goal, Node, Task, NodeType, TaskStatus

logger = get_logger(__name__)


@dataclass
class PredictionResult:
    """Resultado de predicción para planificación."""
    predicted_goal: Optional[Goal] = None
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)
    alternative_goals: List[Goal] = field(default_factory=list)
    execution_probability: float = 0.0
    estimated_cost: float = 0.0
    historical_success_rate: float = 0.0


@dataclass
class ExecutionMetrics:
    """Métricas de ejecución para aprendizaje (FASE 18)."""
    goal_id: str
    success: bool
    execution_time: float
    actual_cost: float
    timestamp: float
    context: Dict[str, Any]
    error_message: Optional[str] = None
    replanifications: int = 0


class EnhancedPredictionMemory:
    """
    Memoria predictiva mejorada que integra:
    - Predicciones de objetivos basadas en entrada de usuario
    - Aprendizaje de rutas exitosas
    - Optimización de costes
    - Compatibilidad con sistema legacy
    """

    MAX_EVENTS = 10000
    MAX_GOAL_HISTORY = 5000
    MAX_METRICS = 10000

    def __init__(self, filepath: str = "data/prediction_memory.json") -> None:
        self.filepath = get_project_root() / filepath

        # Estructura de datos mejorada
        self.data: Dict[str, Any] = {
            # Datos legacy (compatibilidad FASE 16)
            "command_usage_stats": {},
            "time_patterns": {},
            "context_patterns": {},
            "system_state_patterns": {},
            "events": [],
            
            # Nuevos datos para planificación jerárquica
            "goal_history": [],
            "execution_metrics": [],
            "goal_success_patterns": {},
            "cost_estimations": {},
            "path_cache": {},
            "entity_usage": {},
            "goal_templates": {},
            
            "last_updated": 0.0,
        }

        self._load()
        logger.info(
            "[ENHANCED-PREDICTION] Memoria predictiva mejorada inicializada: %s",
            self.filepath,
        )

    # ========================================================================
    # CARGA Y MIGRACIÓN
    # ========================================================================

    def _load(self) -> None:
        """Carga datos con migración a nuevo formato."""
        if not self.filepath.exists():
            self._initialize_goal_templates()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                loaded = json.load(file)

            if not isinstance(loaded, dict):
                return

            # Migrar datos existentes
            self.data = self._migrate_enhanced_data(loaded)
            self._initialize_goal_templates()

            logger.info(
                "[ENHANCED-PREDICTION] Memoria cargada: %s goals, %s comandos legacy",
                len(self.data.get("goal_history", [])),
                len(self.data.get("command_usage_stats", {})),
            )

        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[ENHANCED-PREDICTION] No se pudo cargar %s: %s",
                self.filepath,
                exc,
            )
            self._initialize_goal_templates()

    def _initialize_goal_templates(self) -> None:
        """Inicializa plantillas de objetivos para predicción rápida."""
        self.data["goal_templates"] = {
            "open_application": {
                "type": "open_application",
                "confidence_base": 0.8,
                "cost_base": 5.0,
                "success_rate_historical": 0.9
            },
            "navigate": {
                "type": "navigate", 
                "confidence_base": 0.7,
                "cost_base": 3.0,
                "success_rate_historical": 0.85
            },
            "navigate_stream": {
                "type": "navigate_stream",
                "confidence_base": 0.9,
                "cost_base": 4.0,
                "success_rate_historical": 0.8
            },
            "search": {
                "type": "search",
                "confidence_base": 0.6,
                "cost_base": 2.0,
                "success_rate_historical": 0.75
            }
        }

    def _migrate_enhanced_data(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        """Migra datos al nuevo formato mejorado."""
        migrated: Dict[str, Any] = {
            # Mantener datos legacy
            "command_usage_stats": loaded.get("command_usage_stats", {}),
            "time_patterns": loaded.get("time_patterns", {}),
            "context_patterns": loaded.get("context_patterns", {}),
            "system_state_patterns": loaded.get("system_state_patterns", {}),
            "events": loaded.get("events", []),
            
            # Nueva estructura
            "goal_history": [],
            "execution_metrics": [],
            "goal_success_patterns": {},
            "cost_estimations": {},
            "path_cache": {},
            "entity_usage": {},
            "goal_templates": self.data.get("goal_templates", {}),
            
            "last_updated": loaded.get("last_updated", 0.0),
        }

        # Migrar eventos a goals cuando sea posible
        if "events" in loaded:
            for event in loaded["events"]:
                if self._can_migrate_to_goal(event):
                    goal = self._migrate_event_to_goal(event)
                    if goal:
                        migrated["goal_history"].append(goal)

        return migrated

    def _can_migrate_to_goal(self, event: Dict[str, Any]) -> bool:
        """Verifica si un evento puede migrarse a goal."""
        command = event.get("command", "")
        return bool(command and not command.startswith("CMD:"))

    def _migrate_event_to_goal(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Migra evento a formato goal."""
        try:
            command = event.get("command", "")
            success = event.get("success", True)
            
            # Inferir tipo de goal basado en comando
            goal_type = self._infer_goal_type_from_command(command)
            
            return {
                "goal_id": f"legacy_{event.get('timestamp', time.time())}",
                "type": goal_type,
                "target": command,
                "description": f"Legacy: {command}",
                "created_at": event.get("timestamp", time.time()),
                "executed_at": event.get("timestamp", time.time()),
                "success": success,
                "context": event.get("system_state", {}),
                "source": "legacy_migration"
            }
        except Exception:
            return None

    def _infer_goal_type_from_command(self, command: str) -> str:
        """Infiere tipo de goal desde comando legacy."""
        command_lower = command.lower()
        
        if any(word in command_lower for word in ["abrir", "abre", "iniciar"]):
            return "open_application"
        elif any(word in command_lower for word in ["navegar", "ir a", "visitar"]):
            return "navigate"
        elif any(word in command_lower for word in ["stream", "directo", "live"]):
            return "navigate_stream"
        elif any(word in command_lower for word in ["buscar", "search"]):
            return "search"
        else:
            return "unknown"

    # ========================================================================
    # PREDICCIÓN DE OBJETIVOS (FASE 15)
    # ========================================================================

    def predict_goal_from_input(self, user_input: str, current_state: Dict[str, Any]) -> PredictionResult:
        """
        Predice objetivo basado en entrada de usuario (FASE 15).
        
        Args:
            user_input: Texto del usuario
            current_state: Estado actual del sistema
            
        Returns:
            PredictionResult con predicción y métricas
        """
        logger._print_log("info", f"[PREDICTION] Prediciendo goal para: {user_input}", "prediction.py", "method", 253)
        
        start_time = time.time()
        
        # 1. Análisis básico de entrada
        normalized_input = self._normalize_input(user_input)
        
        # 2. Predicción basada en patrones históricos
        historical_patterns = self._analyze_historical_patterns(normalized_input)
        
        # 3. Predicción basada en estado actual
        state_influence = self._analyze_state_influence(current_state, normalized_input)
        
        # 4. Predicción basada en entidades
        entity_prediction = self._predict_entity_usage(normalized_input)
        
        # 5. Combinar predicciones
        goal = self._combine_predictions(
            normalized_input, 
            historical_patterns, 
            state_influence,
            entity_prediction
        )
        
        # 6. Calcular métricas de confianza
        confidence = self._calculate_prediction_confidence(
            goal, historical_patterns, state_influence, entity_prediction
        )
        
        # 7. Buscar alternativas
        alternatives = self._find_alternative_goals(normalized_input, current_state)
        
        # 8. Estimar coste y probabilidad
        estimated_cost = self._estimate_goal_cost(goal, current_state)
        execution_probability = self._estimate_execution_probability(goal, current_state)
        
        # 9. Calcular tasa de éxito histórica
        success_rate = self._get_historical_success_rate(goal.type)
        
        end_time = time.time()
        
        result = PredictionResult(
            predicted_goal=goal,
            confidence=confidence,
            reasoning=self._generate_prediction_reasoning(
                goal, historical_patterns, state_influence
            ),
            alternative_goals=alternatives,
            execution_probability=execution_probability,
            estimated_cost=estimated_cost,
            historical_success_rate=success_rate
        )
        
        logger._print_log("info", f"[PREDICTION] Predicción completada en {end_time - start_time:.3f}s", "prediction.py", "method", 306)
        logger._print_log("debug", f"[PREDICTION] Resultado: {result}", "prediction.py", "method", 307)
        
        return result

    def _normalize_input(self, text: str) -> str:
        """Normaliza texto para análisis."""
        if not isinstance(text, str):
            return ""
        
        import unicodedata
        import re
        
        text = text.strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = re.sub(r"[^a-z0-9\s]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _analyze_historical_patterns(self, normalized_input: str) -> Dict[str, Any]:
        """Analiza patrones históricos para predicción."""
        patterns = {
            "command_matches": [],
            "time_patterns": {},
            "success_patterns": {},
            "common_sequences": []
        }
        
        # Buscar coincidencias con comandos históricos
        for command, count in self.data.get("command_usage_stats", {}).items():
            if normalized_input in command or command in normalized_input:
                patterns["command_matches"].append({
                    "command": command,
                    "count": count,
                    "success_rate": self._get_command_success_rate(command)
                })
        
        # Patrones temporales
        current_hour = datetime.now().hour
        for command, hour_data in self.data.get("time_patterns", {}).items():
            if str(current_hour) in hour_data:
                patterns["time_patterns"][command] = hour_data[str(current_hour)]
        
        return patterns

    def _analyze_state_influence(self, current_state: Dict[str, Any], normalized_input: str) -> Dict[str, Any]:
        """Analiza cómo el estado actual influye en la predicción."""
        influence = {
            "state_factors": [],
            "confidence_boost": 0.0,
            "contextual_clues": []
        }
        
        # Analizar aplicaciones abiertas
        open_apps = current_state.get("open_windows", [])
        for app in open_apps:
            if any(keyword in app.lower() for keyword in ["chrome", "edge", "firefox"]):
                if any(word in normalized_input for word in ["navegar", "ir", "stream"]):
                    influence["state_factors"].append("browser_available")
                    influence["confidence_boost"] += 0.1
        
        # Analizar aplicación activa
        active_window = current_state.get("active_window", "")
        if active_window:
            influence["contextual_clues"].append(f"active: {active_window}")
        
        # Analizar estado del sistema
        if current_state.get("browser_open", False):
            influence["state_factors"].append("browser_context")
        
        return influence

    def _predict_entity_usage(self, normalized_input: str) -> Dict[str, Any]:
        """Predice uso de entidades basado en entrada."""
        entity_prediction = {
            "likely_entities": [],
            "entity_confidence": {},
            "url_predictions": {}
        }
        
        # Buscar entidades en memoria
        for entity_id, entity_data in self.data.get("entity_usage", {}).items():
            entity_name = entity_data.get("name", "").lower()
            if entity_name in normalized_input or normalized_input in entity_name:
                entity_prediction["likely_entities"].append(entity_id)
                entity_prediction["entity_confidence"][entity_id] = entity_data.get("usage_count", 1) / 100.0
                
                # Predecir URL si es conocida
                url = entity_data.get("url")
                if url:
                    entity_prediction["url_predictions"][entity_id] = url
        
        return entity_prediction

    def _combine_predictions(self, normalized_input: str, historical: Dict, 
                           state: Dict, entity: Dict) -> Optional[Goal]:
        """Combina diferentes predicciones para crear goal."""
        
        # Determinar tipo de goal más probable
        goal_type = self._determine_goal_type(normalized_input, historical, state, entity)
        
        if not goal_type:
            return None
        
        # Crear goal base
        goal_id = f"goal_{int(time.time())}"
        goal = Goal(
            id=goal_id,
            type=goal_type,
            target=self._extract_goal_target(normalized_input, entity),
            description=f"Predicted goal: {goal_type}",
            priority=1,
            created_at=time.time()
        )
        
        # Ajustar parámetros basados en contexto
        if goal_type == "navigate_stream" and entity.get("url_predictions"):
            goal.target = list(entity["url_predictions"].values())[0]
        
        return goal

    def _determine_goal_type(self, normalized_input: str, historical: Dict, 
                           state: Dict, entity: Dict) -> Optional[str]:
        """Determina el tipo de goal más probable."""
        
        # Patrones de intenciones
        intention_patterns = {
            "open_application": ["abrir", "abre", "iniciar", "launch"],
            "navigate": ["navegar", "ir a", "visitar", "go to"],
            "navigate_stream": ["stream", "directo", "en vivo", "live"],
            "search": ["buscar", "search", "find"]
        }
        
        scores = {}
        
        for goal_type, keywords in intention_patterns.items():
            score = 0.0
            
            # Puntuación por coincidencia de palabras clave
            for keyword in keywords:
                if keyword in normalized_input:
                    score += 0.3
            
            # Puntuación por patrones históricos
            for match in historical.get("command_matches", []):
                if goal_type in match["command"]:
                    score += match["count"] * 0.01
            
            # Puntuación por contexto de estado
            if "browser_available" in state.get("state_factors", []):
                if goal_type in ["navigate", "navigate_stream"]:
                    score += 0.2
            
            scores[goal_type] = score
        
        # Devolver tipo con mayor puntuación
        if scores:
            return max(scores, key=scores.get)
        
        return None

    def _extract_goal_target(self, normalized_input: str, entity: Dict) -> Union[str, Dict[str, Any]]:
        """Extrae target del goal basado en entrada y entidades."""
        
        # Si hay entidades predichas, usarlas
        if entity.get("likely_entities"):
            entity_id = entity["likely_entities"][0]
            entity_data = self.data["entity_usage"].get(entity_id, {})
            return entity_data.get("name", normalized_input)
        
        # Extraer entidad del texto
        words = normalized_input.split()
        if len(words) > 1:
            target = " ".join(words[1:])  # Suponer que el primer word es verbo
            return target
        
        return normalized_input

    def _calculate_prediction_confidence(self, goal: Optional[Goal], historical: Dict, 
                                      state: Dict, entity: Dict) -> float:
        """Calcula confianza en la predicción."""
        
        if not goal:
            return 0.0
        
        confidence = 0.5  # Base
        
        # Ajustar por patrones históricos
        historical_match = len(historical.get("command_matches", []))
        confidence += min(historical_match * 0.1, 0.3)
        
        # Ajustar por contexto de estado
        if state.get("confidence_boost", 0) > 0:
            confidence += min(state["confidence_boost"], 0.2)
        
        # Ajustar por entidades predichas
        entity_count = len(entity.get("likely_entities", []))
        confidence += min(entity_count * 0.1, 0.2)
        
        return min(confidence, 1.0)

    def _find_alternative_goals(self, normalized_input: str, current_state: Dict[str, Any]) -> List[Goal]:
        """Busca goals alternativos basados en entrada."""
        alternatives = []
        
        # Generar alternativas basadas en sinónimos
        synonym_goals = self._generate_synonym_goals(normalized_input)
        alternatives.extend(synonym_goals)
        
        # Generar alternativas basadas en estado
        state_goals = self._generate_state_based_goals(normalized_input, current_state)
        alternatives.extend(state_goals)
        
        return alternatives[:3]  # Limitar a 3 alternativas

    def _generate_synonym_goals(self, normalized_input: str) -> List[Goal]:
        """Genera goals alternativos usando sinónimos."""
        synonyms = {
            "abrir": ["iniciar", "launch", "ejecutar"],
            "navegar": ["ir", "visitar", "abrir"],
            "stream": ["directo", "en vivo", "live"],
            "buscar": ["search", "find", "localizar"]
        }
        
        alternatives = []
        words = normalized_input.split()
        
        if len(words) >= 2:
            verb = words[0]
            target = " ".join(words[1:])
            
            for synonym in synonyms.get(verb, []):
                goal_id = f"alt_{int(time.time())}_{len(alternatives)}"
                alternatives.append(Goal(
                    id=goal_id,
                    type=self._determine_goal_type(synonym + " " + target, {}, {}, {}),
                    target=target,
                    description=f"Alternative using synonym: {synonym}",
                    created_at=time.time()
                ))
        
        return alternatives

    def _generate_state_based_goals(self, normalized_input: str, current_state: Dict[str, Any]) -> List[Goal]:
        """Genera goals alternativos basados en estado actual."""
        alternatives = []
        
        # Si hay navegador abierto pero no se menciona, sugerir navegación
        if current_state.get("browser_open", False) and "navegar" not in normalized_input:
            goal_id = f"state_alt_{int(time.time())}"
            alternatives.append(Goal(
                id=goal_id,
                type="navigate",
                target="default_page",
                description="Suggested navigation due to browser availability",
                created_at=time.time()
            ))
        
        return alternatives

    def _estimate_goal_cost(self, goal: Optional[Goal], current_state: Dict[str, Any]) -> float:
        """Estima coste de ejecución del goal."""
        if not goal:
            return float('inf')
        
        # Coste base por tipo
        base_costs = {
            "open_application": 5.0,
            "navigate": 3.0,
            "navigate_stream": 4.0,
            "search": 2.0
        }
        
        cost = base_costs.get(goal.type, 1.0)
        
        # Ajustar por estado actual
        if current_state.get("browser_open", False) and goal.type in ["navigate", "navigate_stream"]:
            cost *= 0.7  # Descuento si navegador ya está abierto
        
        # Ajustar por costes históricos
        historical_cost = self.data.get("cost_estimations", {}).get(goal.type, {})
        if historical_cost:
            avg_cost = statistics.mean(historical_cost.values())
            cost = (cost + avg_cost) / 2  # Promedio con histórico
        
        return cost

    def _estimate_execution_probability(self, goal: Optional[Goal], current_state: Dict[str, Any]) -> float:
        """Estima probabilidad de éxito del goal."""
        if not goal:
            return 0.0
        
        # Probabilidad base por tipo
        base_probabilities = {
            "open_application": 0.9,
            "navigate": 0.8,
            "navigate_stream": 0.7,
            "search": 0.85
        }
        
        probability = base_probabilities.get(goal.type, 0.5)
        
        # Ajustar por estado actual
        if goal.type == "open_application":
            if current_state.get("open_window_count", 0) > 10:
                probability *= 0.9  # Menor probabilidad con muchas ventanas abiertas
        
        return probability

    def _get_historical_success_rate(self, goal_type: str) -> float:
        """Obtiene tasa de éxito histórica para tipo de goal."""
        history = self.data.get("goal_success_patterns", {}).get(goal_type, [])
        if not history:
            return 0.8  # Default
        
        successful = sum(1 for item in history if item.get("success", False))
        return successful / len(history)

    def _get_command_success_rate(self, command: str) -> float:
        """Obtiene tasa de éxito para comando legacy."""
        events = self.data.get("events", [])
        command_events = [e for e in events if e.get("command") == command]
        if not command_events:
            return 0.8
        
        successful = sum(1 for e in command_events if e.get("success", False))
        return successful / len(command_events)

    def _generate_prediction_reasoning(self, goal: Optional[Goal], historical: Dict, 
                                     state: Dict) -> List[str]:
        """Genera explicación de la predicción."""
        reasoning = []
        
        if goal:
            reasoning.append(f"Predicted goal type: {goal.type}")
            reasoning.append(f"Target: {goal.target}")
        
        if historical.get("command_matches"):
            reasoning.append(f"Found {len(historical['command_matches'])} historical matches")
        
        if state.get("state_factors"):
            reasoning.append(f"State factors: {state['state_factors']}")
        
        return reasoning

    # ========================================================================
    # REGISTRO DE EJECUCIÓN (FASE 18)
    # ========================================================================

    def record_goal_execution(self, goal: Goal, success: bool, execution_time: float,
                            actual_cost: float, context: Dict[str, Any],
                            error_message: Optional[str] = None, replanifications: int = 0) -> None:
        """
        Registra ejecución de goal para aprendizaje (FASE 18).
        
        Args:
            goal: Goal ejecutado
            success: Si tuvo éxito
            execution_time: Tiempo de ejecución
            actual_cost: Coste real
            context: Contexto de ejecución
            error_message: Error si falló
            replanifications: Número de replanificaciones
        """
        logger._print_log("info", f"[RECORDING] Registrando ejecución de goal: {goal.id} - {'éxito' if success else 'fallo'}", "prediction.py", "method", 671)
        
        # Registrar en historial
        execution_record = {
            "goal_id": goal.id,
            "type": goal.type,
            "target": goal.target,
            "success": success,
            "execution_time": execution_time,
            "actual_cost": actual_cost,
            "timestamp": time.time(),
            "context": context,
            "error_message": error_message,
            "replanifications": replanifications,
            "estimated_cost": goal.priority * 3.0,  # Coste estimado base
            "cost_variance": abs(actual_cost - goal.priority * 3.0)
        }
        
        self.data["goal_history"].append(execution_record)
        
        # Limitar tamaño del historial
        if len(self.data["goal_history"]) > self.MAX_GOAL_HISTORY:
            self.data["goal_history"] = self.data["goal_history"][-self.MAX_GOAL_HISTORY:]
        
        # Actualizar métricas de ejecución
        metrics = ExecutionMetrics(
            goal_id=goal.id,
            success=success,
            execution_time=execution_time,
            actual_cost=actual_cost,
            timestamp=time.time(),
            context=context,
            error_message=error_message,
            replanifications=replanifications
        )
        
        self.data["execution_metrics"].append(metrics.__dict__)
        
        # Limitar métricas
        if len(self.data["execution_metrics"]) > self.MAX_METRICS:
            self.data["execution_metrics"] = self.data["execution_metrics"][-self.MAX_METRICS:]
        
        # Actualizar patrones de éxito
        self._update_success_patterns(goal, success)
        
        # Actualizar estimaciones de coste
        self._update_cost_estimations(goal, actual_cost)
        
        # Actualizar caché de rutas
        self._update_path_cache(goal, success, execution_time, actual_cost)
        
        # Actualizar uso de entidades
        self._update_entity_usage(goal, context)
        
        self._save()
        
        logger._print_log("info", f"[RECORDING] Ejecución registrada para goal {goal.id}", "prediction.py", "method", 727)

    def _update_success_patterns(self, goal: Goal, success: bool) -> None:
        """Actualiza patrones de éxito por tipo de goal."""
        if goal.type not in self.data["goal_success_patterns"]:
            self.data["goal_success_patterns"][goal.type] = []
        
        self.data["goal_success_patterns"][goal.type].append({
            "goal_id": goal.id,
            "success": success,
            "timestamp": time.time()
        })
        
        # Limitar historial por tipo
        max_per_type = 100
        if len(self.data["goal_success_patterns"][goal.type]) > max_per_type:
            self.data["goal_success_patterns"][goal.type] = \
                self.data["goal_success_patterns"][goal.type][-max_per_type:]

    def _update_cost_estimations(self, goal: Goal, actual_cost: float) -> None:
        """Actualiza estimaciones de coste."""
        if goal.type not in self.data["cost_estimations"]:
            self.data["cost_estimations"][goal.type] = []
        
        self.data["cost_estimations"][goal.type].append(actual_cost)
        
        # Limitar historial
        max_estimations = 50
        if len(self.data["cost_estimations"][goal.type]) > max_estimations:
            self.data["cost_estimations"][goal.type] = \
                self.data["cost_estimations"][goal.type][-max_estimations:]

    def _update_path_cache(self, goal: Goal, success: bool, execution_time: float, actual_cost: float) -> None:
        """Actualiza caché de rutas exitosas."""
        cache_key = f"{goal.type}_{goal.target}"
        
        if cache_key not in self.data["path_cache"]:
            self.data["path_cache"][cache_key] = {
                "executions": [],
                "success_count": 0,
                "total_time": 0.0,
                "total_cost": 0.0,
                "avg_time": 0.0,
                "avg_cost": 0.0,
                "success_rate": 0.0
            }
        
        cache_entry = self.data["path_cache"][cache_key]
        cache_entry["executions"].append({
            "timestamp": time.time(),
            "success": success,
            "execution_time": execution_time,
            "cost": actual_cost
        })
        
        if success:
            cache_entry["success_count"] += 1
        
        cache_entry["total_time"] += execution_time
        cache_entry["total_cost"] += actual_cost
        
        # Limitar entradas en caché
        max_cache_entries = 20
        if len(cache_entry["executions"]) > max_cache_entries:
            cache_entry["executions"] = cache_entry["executions"][-max_cache_entries:]
        
        # Recalcular promedios
        total_executions = len(cache_entry["executions"])
        cache_entry["avg_time"] = cache_entry["total_time"] / total_executions if total_executions > 0 else 0
        cache_entry["avg_cost"] = cache_entry["total_cost"] / total_executions if total_executions > 0 else 0
        cache_entry["success_rate"] = cache_entry["success_count"] / total_executions if total_executions > 0 else 0

    def _update_entity_usage(self, goal: Goal, context: Dict[str, Any]) -> None:
        """Actualiza estadísticas de uso de entidades."""
        # Extraer entidades del contexto si están disponibles
        entities = context.get("entities", [])
        
        for entity_name in entities:
            entity_key = f"entity_{entity_name}"
            
            if entity_key not in self.data["entity_usage"]:
                self.data["entity_usage"][entity_key] = {
                    "name": entity_name,
                    "usage_count": 0,
                    "associated_goals": [],
                    "success_rate": 0.0
                }
            
            entity_data = self.data["entity_usage"][entity_key]
            entity_data["usage_count"] += 1
            entity_data["associated_goals"].append(goal.id)
            
            # Actualizar tasa de éxito
            recent_goals = entity_data["associated_goals"][-10:]  # Últimos 10 usos
            successful_goals = sum(1 for gid in recent_goals 
                                 if any(g.get("goal_id") == gid and g.get("success") 
                                       for g in self.data["goal_history"]))
            entity_data["success_rate"] = successful_goals / len(recent_goals) if recent_goals else 0.0

    # ========================================================================
    # CONSULTA DE DATOS
    # ========================================================================

    def get_goal_prediction_history(self, goal_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene historial de predicciones de goals."""
        if goal_type:
            return [g for g in self.data.get("goal_history", []) if g.get("type") == goal_type]
        return self.data.get("goal_history", [])

    def get_cached_path(self, goal_type: str, target: str) -> Optional[Dict[str, Any]]:
        """Obtiene ruta cacheada para goal específico."""
        cache_key = f"{goal_type}_{target}"
        return self.data.get("path_cache", {}).get(cache_key)

    def get_cost_estimation(self, goal_type: str) -> float:
        """Obtiene estimación de coste para tipo de goal."""
        estimations = self.data.get("cost_estimations", {}).get(goal_type, [])
        if estimations:
            return statistics.mean(estimations)
        return 1.0

    def get_success_rate(self, goal_type: str) -> float:
        """Obtiene tasa de éxito para tipo de goal."""
        patterns = self.data.get("goal_success_patterns", {}).get(goal_type, [])
        if not patterns:
            return 0.8
        
        successful = sum(1 for p in patterns if p.get("success", False))
        return successful / len(patterns)

    # ========================================================================
    # COMPATIBILIDAD LEGACY (FASE 16)
    # ========================================================================

    def record_command(self, command: str, success: bool = True, source: str = "voice") -> Dict[str, Any]:
        """
        Método legacy para registrar comandos (FASE 16).
        Ahora integra con nuevo sistema pero mantiene compatibilidad.
        """
        logger._print_log("info", f"[LEGACY] Registrando comando legacy: {command}", "prediction.py", "method", 866)
        
        # Registrar como evento legacy
        event = self._create_legacy_event(command, success, source)
        
        # Intentar migrar a goal si es posible
        if self._can_migrate_to_goal(event):
            goal = self._migrate_event_to_goal(event)
            if goal:
                # Registrar como goal para aprendizaje
                self.record_goal_execution(
                    goal=goal,  # Necesario convertir a objeto Goal real
                    success=success,
                    execution_time=0.0,  # Desconocido en legacy
                    actual_cost=1.0,  # Coste base
                    context=event.get("system_state", {}),
                    error_message=None if success else "Legacy command execution"
                )
        
        # Mantener registro legacy
        legacy_events = self.data.setdefault("events", [])
        legacy_events.append(event)
        
        if len(legacy_events) > self.MAX_EVENTS:
            del legacy_events[: len(legacy_events) - self.MAX_EVENTS]
        
        self._save()
        
        return event

    def _create_legacy_event(self, command: str, success: bool, source: str) -> Dict[str, Any]:
        """Crea evento en formato legacy."""
        now = datetime.now()
        timestamp = time.time()
        
        # Obtener estado del sistema
        open_windows = self._get_open_windows()
        active_window = self._get_active_window()
        system_state = self._get_system_state(open_windows, active_window)
        
        return {
            "timestamp": timestamp,
            "datetime": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "weekday": now.weekday(),
            "hour": now.hour,
            "minute": now.minute,
            "command": command,
            "success": bool(success),
            "source": source,
            "system_state": system_state,
            "legacy": True  # Marcar como legacy
        }

    # ========================================================================
    # UTILIDADES DE SISTEMA
    # ========================================================================

    def _get_open_windows(self) -> List[str]:
        """Obtiene ventanas abiertas (legacy)."""
        try:
            import pygetwindow as gw
            
            result = []
            seen = set()
            
            for window in gw.getAllWindows():
                try:
                    visible = getattr(window, "visible", False)
                    if not visible:
                        continue
                    
                    title = str(getattr(window, "title", "") or "").strip()
                    if not title:
                        continue
                    
                    normalized = title.casefold()
                    if normalized in seen:
                        continue
                    
                    seen.add(normalized)
                    result.append(title)
                    
                except Exception:
                    continue
            
            result.sort(key=str.casefold)
            return result
            
        except Exception as exc:
            logger._print_log("debug", f"[PREDICTION] No se pudieron obtener ventanas: {exc}", "prediction.py", "method", 956)
            return []

    def _get_active_window(self) -> Optional[str]:
        """Obtiene ventana activa (legacy)."""
        try:
            import pygetwindow as gw
            
            window = gw.getActiveWindow()
            if window is None:
                return None
            
            title = str(getattr(window, "title", "") or "").strip()
            return title or None
            
        except Exception as exc:
            logger._print_log("debug", f"[PREDICTION] No se pudo obtener ventana activa: {exc}", "prediction.py", "method", 972)
            return None

    def _get_system_state(self, open_windows: List[str], active_window: Optional[str]) -> Dict[str, Any]:
        """Obtiene estado del sistema (legacy)."""
        import psutil
        
        cpu_percent = None
        memory_percent = None
        
        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.0))
        except Exception:
            pass
        
        try:
            memory_percent = float(psutil.virtual_memory().percent)
        except Exception:
            pass
        
        normalized_windows = [window.casefold() for window in open_windows]
        browser_open = any(
            browser in window
            for window in normalized_windows
            for browser in ("chrome", "google chrome", "edge", "microsoft edge", "firefox")
        )
        
        return {
            "open_window_count": len(open_windows),
            "open_windows": open_windows,
            "active_window": active_window,
            "browser_open": browser_open,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "idle_seconds": self._get_idle_seconds()
        }

    def _get_idle_seconds(self) -> Optional[float]:
        """Obtiene segundos de inactividad (legacy)."""
        try:
            import ctypes
            
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            
            last_input = LASTINPUTINFO()
            last_input.cbSize = ctypes.sizeof(LASTINPUTINFO)
            
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input)):
                return None
            
            tick_count = ctypes.windll.kernel32.GetTickCount()
            idle_ms = int(tick_count) - int(last_input.dwTime)
            
            return max(0.0, idle_ms / 1000.0)
            
        except Exception:
            return None

    def _save(self) -> None:
        """Guarda datos en archivo."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.data["last_updated"] = time.time()
            
            temp_path = self.filepath.with_suffix(".json.tmp")
            
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(self.data, file, indent=2, ensure_ascii=False)
            
            temp_path.replace(self.filepath)
            
        except OSError as exc:
            logger._print_log("info", "Procesando solicitud", "prediction.py", "method", 1045)


# ============================================================================
# SINGLETON
# ============================================================================

_enhanced_prediction_memory: Optional[EnhancedPredictionMemory] = None


def get_enhanced_prediction_memory() -> EnhancedPredictionMemory:
    """Obtiene instancia singleton de memoria predictiva mejorada."""
    global _enhanced_prediction_memory
    
    if _enhanced_prediction_memory is None:
        _enhanced_prediction_memory = EnhancedPredictionMemory()
    
    return _enhanced_prediction_memory


# ============================================================================
# COMPATIBILIDAD
# ============================================================================

# Mantener interfaz legacy para compatibilidad
class PredictionMemory(EnhancedPredictionMemory):
    """Clase legacy para compatibilidad (FASE 16)."""
    
    def __init__(self, filepath: str = "data/prediction_memory.json"):
        super().__init__(filepath)
        logger._print_log("info", "[LEGACY] Usando PredictionMemory legacy (wrapper sobre EnhancedPredictionMemory)", "prediction.py", "method", 1075)


# Mantener función singleton legacy
def get_prediction_memory() -> PredictionMemory:
    """Función singleton legacy para compatibilidad."""
    return PredictionMemory()