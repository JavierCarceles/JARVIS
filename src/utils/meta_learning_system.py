"""
Meta Learning System v2.8.0
Sistema de metaprendizaje que aprende sobre el comportamiento de aprendizaje ya existente
"""

import asyncio
import json
import logging

from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy
from .self_improvement_system import SelfImprovementSystem, LearningMode
from .adaptive_learning_engine import AdaptiveLearningEngine, LearningTask
from .pattern_analyzer import PatternAnalyzer
from .log_analytics import LogAnalytics
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib
import threading
import queue
import os
from pathlib import Path

import logging


class MetaLearningLevel(Enum):
    """Niveles de metaprendizaje"""
    STRATEGY_SELECTION = "strategy_selection"
    PARAMETER_ADAPTATION = "parameter_adaptation"
    CONTEXTUAL_OPTIMIZATION = "contextual_optimization"
    KNOWLEDGE_ABSTRACTION = "knowledge_abstraction"
    LEARNING_RATE_ADJUSTMENT = "learning_rate_adjustment"


class MetaLearningResult(Enum):
    """Resultados del metaprendizaje"""
    IMPROVEMENT_DETECTED = "improvement_detected"
    DEGRADATION_DETECTED = "degradation_detected"
    NO_CHANGE = "no_change"
    INSUFFICIENT_DATA = "insufficient_data"
    CONFLICTING_SIGNALS = "conflicting_signals"


@dataclass
class LearningExperience:
    """Representa una experiencia de aprendizaje"""
    experience_id: str
    timestamp: datetime
    learning_system: str  # "adaptive_learning", "self_improvement", "performance_optimizer"
    task_type: str
    context: Dict[str, Any]
    strategy_used: str
    parameters: Dict[str, Any]
    outcome: Dict[str, Any]
    success_metrics: Dict[str, float]
    confidence_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningEvaluation:
    """Resultado de evaluar una estrategia de aprendizaje con evidencia disponible"""
    learning_system: str
    task_type: str
    strategy: str
    sample_count: int
    required_samples: int
    success_rate: float
    confidence: float
    consistency: float
    sufficient_evidence: bool
    stable_pattern: bool
    result: MetaLearningResult
    indicators: List[str] = field(default_factory=list)
    sample_ids: List[str] = field(default_factory=list)


class MetaRuleStatus(Enum):
    """Resultado de evaluar/aplicar una meta-regla sobre una regla de aprendizaje"""
    APPLIED = "applied"
    SKIPPED_CONDITION_NOT_MET = "skipped_condition_not_met"
    SKIPPED_INSUFFICIENT_SAMPLES = "skipped_insufficient_samples"
    SKIPPED_UNSUPPORTED_ACTION = "skipped_unsupported_action"
    REJECTED_RULE_NOT_FOUND = "rejected_rule_not_found"
    REJECTED_INVALID = "rejected_invalid"
    REVERTED = "reverted"


@dataclass
class MetaRule:
    """
    Meta-regla: una regla que actúa sobre otra regla de aprendizaje existente.

    Solo representa operaciones que el modelo real soporta
    (ImprovementRule.enabled, priority, success_rate, execution_count, last_execution).
    """
    meta_rule_id: str
    name: str
    target_rule_id: str
    condition_metric: str      # success_rate | execution_count | improvement_score | priority
    operator: str              # "<" | "<=" | ">" | ">=" | "=="
    threshold: float
    action: str                # disable | enable | set_priority | reset_stats
    action_value: Optional[float] = None
    min_execution_count: int = 0
    enabled: bool = True

    SUPPORTED_METRICS = ("success_rate", "execution_count", "improvement_score", "priority")
    SUPPORTED_OPERATORS = ("<", "<=", ">", ">=", "==")
    SUPPORTED_ACTIONS = ("disable", "enable", "set_priority", "reset_stats")

    def is_valid(self) -> bool:
        return (self.condition_metric in self.SUPPORTED_METRICS
                and self.operator in self.SUPPORTED_OPERATORS
                and self.action in self.SUPPORTED_ACTIONS)


@dataclass
class MetaRuleApplication:
    """Registro de una aplicación de meta-regla, con estado previo para poder revertir"""
    meta_rule_id: str
    target_rule_id: str
    action: str
    status: MetaRuleStatus
    previous_state: Dict[str, Any] = field(default_factory=dict)
    new_state: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    reverted: bool = False


@dataclass
class MetaLearningInsight:
    """Representa un insight de metaprendizaje"""
    insight_id: str
    timestamp: datetime
    level: MetaLearningLevel
    description: str
    confidence: float
    evidence: List[LearningExperience]
    recommendation: str
    impact_score: float
    validation_required: bool = False
    applied: bool = False
    # Sistema y tarea de origen. El código los usaba antes de que existieran
    # (18 referencias), por lo que se incorporan como parte real del insight.
    learning_system: str = ""
    task_type: str = ""


class MetaLearningSystem:
    """
    Sistema de metaprendizaje que analiza el comportamiento de los sistemas de aprendizaje existentes
    y genera insights para mejorar su funcionamiento.
    """
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "data/meta_learning_config.json"
        
        # Inicialización de componentes
        self.logger = logging.getLogger("MetaLearningSystem")
        self.logger.setLevel(logging.INFO)
        
        # Crear handler si no existe
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.adaptive_engine = AdaptiveLearningEngine()
        self.self_improvement = SelfImprovementSystem()
        self.performance_optimizer = PerformanceOptimizer()
        self.pattern_analyzer = PatternAnalyzer()
        self.log_analytics = LogAnalytics()
        
        self.config = self._load_config()
        
        # Almacenamiento de experiencias e insights
        self.experiences: List[LearningExperience] = []
        self.insights: List[MetaLearningInsight] = []
        self.meta_rules: Dict[str, Any] = {}
        self.meta_rule_definitions: List[MetaRule] = []
        self.meta_rule_history: List[MetaRuleApplication] = []

        # 2.8.3.6 — Integración. Instancias reales compartidas con las que se
        # conecta este sistema. Ninguna se crea aquí: conectar una sustituye a
        # la instancia propia por la compartida, nunca por una nueva.
        self.contextual_adaptation_engine = None
        self.integrated_components: Dict[str, Any] = {}
        
        # Estado del sistema
        self.is_running = False
        self.learning_queue = queue.Queue()
        self.processing_thread = None
        
        # Métricas de metaprendizaje
        self.total_experiences = 0
        self.successful_insights = 0
        self.improvement_detection_rate = 0.0

        # 2.8.3.7 — SEGURIDAD. Contadores y registro de decisiones de seguridad.
        # auto_changes_applied se reinicia en cada ciclo de aplicación automática:
        # los límites son por ciclo, no acumulados para siempre.
        self.auto_changes_applied = 0
        self.security_decisions: List[Dict[str, Any]] = []
        
        self.logger.info("MetaLearningSystem inicializado")
    
    def _load_config(self) -> Dict[str, Any]:
        """Cargar configuración del sistema"""
        default_config = {
            "enabled": True,
            "max_experiences": 10000,
            "min_experiences_for_analysis": 50,
            "confidence_threshold": 0.7,
            "analysis_interval": 3600,  # 1 hora
            "insight_validation": True,
            "auto_apply_insights": False,
            "persistence_enabled": True,
            "export_path": "data/meta_learning_exports/",
            "persistence_path": "data/meta_learning_state.json",
            "learning_rate_adjustment": {
                "enabled": True,
                "min_rate": 0.01,
                "max_rate": 1.0,
                "adjustment_factor": 0.1
            },
            "strategy_selection": {
                "enabled": True,
                "max_strategies": 5,
                "selection_window": 100
            },
            "knowledge_abstraction": {
                "enabled": True,
                "abstraction_level": 2,
                "pattern_min_support": 0.1
            },
            # 2.8.3.7 — SEGURIDAD: límites de los cambios automáticos.
            "security": {
                "max_auto_changes_per_cycle": 3,
                "protected_actions": ["reset_stats"],
                "require_validation_for_shared_engines": True,
                "max_security_decisions": 500
            }
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)
                    # El bloque de seguridad se fusiona campo a campo: un update
                    # plano perdería los límites no repetidos en el archivo.
                    if isinstance(config.get("security"), dict):
                        default_config["security"].update(config["security"])
                self.logger.info(f"Configuración cargada desde {self.config_path}")
            else:
                self.logger.info("Usando configuración por defecto")
        except Exception as e:
            self.logger.warning(f"Error al cargar configuración: {e}")
        
        return default_config
    
    def _save_config(self):
        """Guardar configuración actual"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, default=str)
            self.logger.info(f"Configuración guardada en {self.config_path}")
        except Exception as e:
            self.logger.error(f"Error al guardar configuración: {e}")
    
    def capture_learning_experience(self, 
                                   learning_system: str,
                                   task_type: str,
                                   context: Dict[str, Any],
                                   strategy: str,
                                   parameters: Dict[str, Any],
                                   outcome: Dict[str, Any],
                                   success_metrics: Dict[str, float],
                                   confidence_score: float) -> str:
        """
        Captura una experiencia de aprendizaje para análisis metaprendizaje
        
        Args:
            learning_system: Sistema de aprendizaje que generó la experiencia
            task_type: Tipo de tarea realizada
            context: Contexto de la ejecución
            strategy: Estrategia utilizada
            parameters: Parámetros de la estrategia
            outcome: Resultado de la ejecución
            success_metrics: Métricas de éxito
            confidence_score: Puntuación de confianza (0-1)
        
        Returns:
            ID de la experiencia capturada

        Raises:
            ValueError: Si algún parámetro está fuera de su rango válido
        """
        if not isinstance(confidence_score, (int, float)) or isinstance(confidence_score, bool):
            raise ValueError(f"confidence_score debe ser numérico: {confidence_score!r}")
        if not 0.0 <= confidence_score <= 1.0:
            raise ValueError(f"confidence_score debe estar entre 0.0 y 1.0: {confidence_score}")

        # Validar que la experiencia tiene utilidad antes de registrar
        if not self._validate_experience_utility(learning_system, task_type, context, outcome):
            self.logger.warning(f"Experiencia descartada por falta de utilidad: {task_type}")
            return None
        
        experience_id = f"exp_{int(time.time())}_{hash(str(context)) % 10000}"
        
        experience = LearningExperience(
            experience_id=experience_id,
            timestamp=datetime.now(),
            learning_system=learning_system,
            task_type=task_type,
            context=context,
            strategy_used=strategy,
            parameters=parameters,
            outcome=outcome,
            success_metrics=success_metrics,
            confidence_score=confidence_score
        )
        
        # Añadir a la lista de experiencias
        self.experiences.append(experience)
        self.total_experiences += 1
        
        # Mantener límite de experiencias
        if len(self.experiences) > self.config["max_experiences"]:
            self.experiences = self.experiences[-self.config["max_experiences"]:]
        
        # Añadir a cola para procesamiento asíncrono
        self.learning_queue.put(experience)
        
        self.logger.info(f"Experiencia capturada: {experience_id}")
        return experience_id
    
    def capture_structured_experience(self,
                                    learning_system: str,
                                    task_type: str,
                                    context_features: Dict[str, Any],
                                    action_taken: Dict[str, Any],
                                    strategy_applied: str,
                                    strategy_parameters: Dict[str, Any],
                                    execution_result: Dict[str, Any],
                                    performance_metrics: Dict[str, float],
                                    contextual_factors: Dict[str, Any] = None) -> str:
        """
        Captura una experiencia de aprendizaje estructurada con asociación explícita
        de contexto, acción/estrategia y resultado.
        
        Args:
            learning_system: Sistema de aprendizaje que generó la experiencia
            task_type: Tipo de tarea realizada
            context_features: Características del contexto (sistema, entorno, recursos)
            action_taken: Acción realizada (operación, parámetros, decisiones)
            strategy_applied: Estrategia utilizada
            strategy_parameters: Parámetros de la estrategia
            execution_result: Resultado de la ejecución
            performance_metrics: Métricas de rendimiento
            contextual_factors: Factores contextuales adicionales
        
        Returns:
            ID de la experiencia capturada
        """
        # Construir contexto completo
        full_context = {
            "features": context_features,
            "factors": contextual_factors or {},
            "timestamp": datetime.now().isoformat(),
            "system_state": self._get_current_system_state()
        }
        
        # Construir resultado estructurado
        structured_outcome = {
            "action_result": execution_result,
            "performance": performance_metrics,
            "success_indicators": self._extract_success_indicators(performance_metrics),
            "failure_indicators": self._extract_failure_indicators(execution_result)
        }
        
        # Validar utilidad de la experiencia estructurada
        if not self._validate_experience_utility(learning_system, task_type, full_context, structured_outcome):
            self.logger.warning(f"Experiencia estructurada descartada: {task_type}")
            return None
        
        # Capturar experiencia con estructura enriquecida
        experience_id = f"structured_exp_{int(time.time())}_{hash(str(full_context)) % 10000}"
        
        experience = LearningExperience(
            experience_id=experience_id,
            timestamp=datetime.now(),
            learning_system=learning_system,
            task_type=task_type,
            context=full_context,
            strategy_used=strategy_applied,
            parameters=strategy_parameters,
            outcome=structured_outcome,
            success_metrics=performance_metrics,
            confidence_score=self._calculate_experience_confidence(performance_metrics)
        )
        
        # Añadir metadata sobre la estructura
        experience.metadata = {
            "structured_capture": True,
            "action_details": action_taken,
            "context_completeness": self._assess_context_completeness(full_context),
            "result_quality": self._assess_result_quality(execution_result)
        }
        
        # Añadir a la lista de experiencias
        self.experiences.append(experience)
        self.total_experiences += 1
        
        # Mantener límite de experiencias
        if len(self.experiences) > self.config["max_experiences"]:
            self.experiences = self.experiences[-self.config["max_experiences"]:]
        
        # Añadir a cola para procesamiento asíncrono
        self.learning_queue.put(experience)
        
        self.logger.info(f"Experiencia estructurada capturada: {experience_id}")
        return experience_id
    
    def capture_experience_with_context(self,
                                      learning_system: str,
                                      task_type: str,
                                      environment_context: Dict[str, Any],
                                      user_context: Dict[str, Any],
                                      system_context: Dict[str, Any],
                                      action_executed: Dict[str, Any],
                                      strategy_info: Dict[str, Any],
                                      outcome_data: Dict[str, Any],
                                      learning_value: float) -> str:
        """
        Captura una experiencia con asociación detallada de contexto completo
        
        Args:
            learning_system: Sistema de aprendizaje
            task_type: Tipo de tarea
            environment_context: Contexto del entorno (hardware, software, red)
            user_context: Contexto del usuario (preferencias, historial, estado)
            system_context: Contexto del sistema (recursos, estado interno)
            action_executed: Acción ejecutada (detalles completos)
            strategy_info: Información de la estrategia aplicada
            outcome_data: Datos del resultado
            learning_value: Valor de aprendizaje estimado (0-1)
        
        Returns:
            ID de la experiencia capturada
        """
        # Construir contexto completo multi-nivel
        complete_context = {
            "environment": environment_context,
            "user": user_context,
            "system": system_context,
            "combined_context": {
                "timestamp": datetime.now().isoformat(),
                "session_id": self._get_session_id(),
                "task_complexity": self._assess_task_complexity(task_type),
                "resource_availability": self._assess_resource_availability(system_context)
            }
        }
        
        # Construir información de acción/estrategia
        action_strategy_info = {
            "action": action_executed,
            "strategy": strategy_info,
            "decision_points": self._extract_decision_points(action_executed),
            "resource_usage": self._extract_resource_usage(action_executed)
        }
        
        # Validar utilidad basada en valor de aprendizaje
        if learning_value < 0.3:  # Umbral mínimo de valor de aprendizaje
            self.logger.warning(f"Experiencia con bajo valor de aprendizaje: {learning_value}")
            return None
        
        # Capturar experiencia con contexto completo
        experience_id = f"contextual_exp_{int(time.time())}_{hash(str(complete_context)) % 10000}"
        
        experience = LearningExperience(
            experience_id=experience_id,
            timestamp=datetime.now(),
            learning_system=learning_system,
            task_type=task_type,
            context=complete_context,
            strategy_used=strategy_info.get("name", "unknown"),
            parameters=strategy_info.get("parameters", {}),
            outcome=outcome_data,
            success_metrics={"learning_value": learning_value},
            confidence_score=learning_value
        )
        
        # Añadir metadata detallada
        experience.metadata = {
            "contextual_capture": True,
            "environmental_factors": environment_context,
            "user_factors": user_context,
            "system_factors": system_context,
            "action_strategy": action_strategy_info,
            "learning_assessment": {
                "value": learning_value,
                "potential": self._assess_learning_potential(task_type, outcome_data),
                "reusability": self._assess_reusability(complete_context, outcome_data)
            }
        }
        
        # Añadir a la lista de experiencias
        self.experiences.append(experience)
        self.total_experiences += 1
        
        # Mantener límite de experiencias
        if len(self.experiences) > self.config["max_experiences"]:
            self.experiences = self.experiences[-self.config["max_experiences"]:]
        
        # Añadir a cola para procesamiento asíncrono
        self.learning_queue.put(experience)
        
        self.logger.info(f"Experiencia contextual capturada: {experience_id} (valor: {learning_value:.2f})")
        return experience_id
    
    def _get_current_system_state(self) -> Dict[str, Any]:
        """Obtiene el estado actual del sistema"""
        return {
            "memory_usage": getattr(self, 'memory_usage', 'unknown'),
            "active_processes": getattr(self, 'active_processes', []),
            "performance_metrics": getattr(self, 'performance_metrics', {}),
            "learning_systems_status": {
                "adaptive_engine": hasattr(self, 'adaptive_engine') and self.adaptive_engine.is_running if hasattr(self, 'adaptive_engine') else False,
                "self_improvement": hasattr(self, 'self_improvement') and self.self_improvement.is_running if hasattr(self, 'self_improvement') else False,
                "performance_optimizer": hasattr(self, 'performance_optimizer') and self.performance_optimizer.is_running if hasattr(self, 'performance_optimizer') else False
            }
        }
    
    def _extract_success_indicators(self, performance_metrics: Dict[str, float]) -> List[str]:
        """Extrae indicadores de éxito de las métricas de rendimiento"""
        success_indicators = []
        for metric, value in performance_metrics.items():
            if isinstance(value, (int, float)) and value > 0.7:  # Umbral de éxito
                success_indicators.append(f"{metric}_success")
        return success_indicators
    
    def _extract_failure_indicators(self, execution_result: Dict[str, Any]) -> List[str]:
        """Extrae indicadores de fallo del resultado de ejecución"""
        failure_indicators = []
        if execution_result.get("error") or execution_result.get("failed"):
            failure_indicators.append("execution_failure")
        if execution_result.get("timeout"):
            failure_indicators.append("timeout")
        if execution_result.get("invalid_input"):
            failure_indicators.append("invalid_input")
        return failure_indicators
    
    def _calculate_experience_confidence(self, performance_metrics: Dict[str, float]) -> float:
        """Calcula la confianza de la experiencia basada en métricas de rendimiento"""
        if not performance_metrics:
            return 0.5
        
        # Calcular confianza promedio de las métricas
        metric_values = [v for v in performance_metrics.values() if isinstance(v, (int, float))]
        if not metric_values:
            return 0.5
        
        confidence = sum(metric_values) / len(metric_values)
        return min(max(confidence, 0.0), 1.0)
    
    def _assess_context_completeness(self, context: Dict[str, Any]) -> float:
        """Evalúa la completitud del contexto"""
        required_fields = ['features', 'factors', 'timestamp', 'system_state']
        present_fields = sum(1 for field in required_fields if field in context)
        return present_fields / len(required_fields)
    
    def _assess_result_quality(self, execution_result: Dict[str, Any]) -> float:
        """Evalúa la calidad del resultado de ejecución"""
        if not execution_result:
            return 0.0
        
        quality_indicators = 0
        if "result" in execution_result:
            quality_indicators += 1
        if "metrics" in execution_result:
            quality_indicators += 1
        if "timestamp" in execution_result:
            quality_indicators += 1
        
        return min(quality_indicators / 3.0, 1.0)
    
    def _get_session_id(self) -> str:
        """Obtiene o genera un ID de sesión"""
        if not hasattr(self, '_current_session_id'):
            self._current_session_id = f"session_{int(time.time())}"
        return self._current_session_id
    
    def _assess_task_complexity(self, task_type: str) -> float:
        """Evalúa la complejidad de la tarea"""
        complex_tasks = ["optimization", "learning", "adaptation", "planning"]
        return 0.8 if task_type.lower() in complex_tasks else 0.5
    
    def _assess_resource_availability(self, system_context: Dict[str, Any]) -> float:
        """Evalúa la disponibilidad de recursos"""
        if "resources" in system_context:
            resources = system_context["resources"]
            if isinstance(resources, dict):
                available = 0
                total = 0
                for key, value in resources.items():
                    total += 1
                    if isinstance(value, bool):
                        if value:
                            available += 1
                    elif isinstance(value, dict):
                        if value.get("available", False):
                            available += 1
                    elif value:  # Cualquier valor truthy se considera disponible
                        available += 1
                
                return available / total if total > 0 else 0.5
        return 0.5
    
    def _extract_decision_points(self, action_executed: Dict[str, Any]) -> List[str]:
        """Extrae puntos de decisión de la acción ejecutada"""
        decision_points = []
        if "strategy_selection" in action_executed:
            decision_points.append("strategy_selection")
        if "parameter_tuning" in action_executed:
            decision_points.append("parameter_tuning")
        if "resource_allocation" in action_executed:
            decision_points.append("resource_allocation")
        return decision_points
    
    def _extract_resource_usage(self, action_executed: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae uso de recursos de la acción ejecutada"""
        return action_executed.get("resource_usage", {})
    
    def _assess_learning_potential(self, task_type: str, outcome_data: Dict[str, Any]) -> float:
        """Evalúa el potencial de aprendizaje de la experiencia"""
        potential = 0.5
        
        # Aumentar potencial para tareas complejas
        if task_type.lower() in ["optimization", "learning", "adaptation"]:
            potential += 0.3
        
        # Aumentar potencial si hay resultados interesantes
        if outcome_data.get("unexpected_result"):
            potential += 0.2
        
        return min(potential, 1.0)
    
    def _assess_reusability(self, context: Dict[str, Any], outcome: Dict[str, Any]) -> float:
        """Evalúa la reutilidad de la experiencia"""
        reusability = 0.5
        
        # Aumentar reutilidad si el contexto es generalizable
        if "environment" in context and len(context["environment"]) > 2:
            reusability += 0.2
        
        # Aumentar reutilidad si el resultado es consistente
        if outcome.get("consistent_result"):
            reusability += 0.3
        
        return min(reusability, 1.0)
    
    def _validate_experience_utility(self, 
                                   learning_system: str,
                                   task_type: str,
                                   context: Dict[str, Any],
                                   outcome: Dict[str, Any]) -> bool:
        """
        Valida si una experiencia tiene utilidad para el metaprendizaje
        
        Args:
            learning_system: Sistema de aprendizaje
            task_type: Tipo de tarea
            context: Contexto de la ejecución
            outcome: Resultado de la ejecución
        
        Returns:
            True si la experiencia tiene utilidad, False en caso contrario
        """
        # Evitar registrar experiencias duplicadas idénticas.
        # La primera aparición de una firma es válida (puede ser la propia experiencia
        # ya registrada que se está revalidando); solo las repeticiones se rechazan.
        signature = (learning_system, task_type, json.dumps(context, sort_keys=True, default=str),
                     json.dumps(outcome, sort_keys=True, default=str))
        previous_signatures = set()
        for exp in self.experiences:
            if (exp.learning_system == learning_system and
                    exp.task_type == task_type and
                    exp.context == context and
                    exp.outcome == outcome):
                if signature in previous_signatures:
                    self.logger.debug(f"Experiencia duplicada detectada: {exp.experience_id}")
                    return False
                previous_signatures.add(signature)
        
        # Verificar que el contexto contiene información relevante
        if not context or len(context) == 0:
            self.logger.debug("Contexto vacío detectado")
            return False
        
        # Verificar que el outcome contiene información útil
        if not outcome or len(outcome) == 0:
            self.logger.debug("Outcome vacío detectado")
            return False
        
        # Excluir experiencias de sistemas no soportados
        supported_systems = ["adaptive_learning", "self_improvement", "performance_optimizer"]
        if learning_system not in supported_systems:
            self.logger.debug(f"Sistema de aprendizaje no soportado: {learning_system}")
            return False
        
        # Excluir tareas triviales o de prueba que no aportan aprendizaje
        trivial_tasks = ["test", "mock", "demo", "debug"]
        if task_type.lower() in trivial_tasks:
            self.logger.debug(f"Tarea trivial detectada: {task_type}")
            return False
        
        # Verificar que el contexto tiene al menos un campo relevante
        relevant_context_fields = ['timestamp', 'system', 'environment', 'features', 'factors', 'user', 'system_state']
        context_has_relevant_data = any(field in context for field in relevant_context_fields)
        
        # Si no tiene campos contextuales específicos, verificar que tenga datos
        # estructurados o valores numéricos medibles
        if not context_has_relevant_data:
            has_structured = any(isinstance(v, (dict, list)) for v in context.values())
            has_numeric = any(isinstance(v, (int, float)) and not isinstance(v, bool)
                              for v in context.values())
            if not (has_structured or has_numeric):
                self.logger.debug("Contexto sin datos estructurados ni valores medibles detectado")
                return False
        
        return True
    
    def get_learning_success_indicators(self) -> Dict[str, Any]:
        """
        Identifica los indicadores de éxito realmente disponibles en las experiencias
        capturadas, sin inventar métricas nuevas.
        """
        return {
            "primary_metrics": ["success_rate", "learning_value"],
            "fallback_metrics": ["confidence_score"],
            "qualitative_indicators": ["outcome.success_indicators", "outcome.failure_indicators"],
            "quality_indicators": ["metadata.result_quality"],
            "min_experiences_for_analysis": self.config["min_experiences_for_analysis"],
            "confidence_threshold": self.config["confidence_threshold"],
        }
    
    def _experience_success_score(self, experience: LearningExperience) -> Optional[float]:
        """Extrae el valor de éxito de una experiencia usando los indicadores existentes"""
        metrics = experience.success_metrics or {}
        for key in ("success_rate", "learning_value"):
            value = metrics.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(min(max(value, 0.0), 1.0))
        
        values = [v for v in metrics.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if values:
            return float(min(max(sum(values) / len(values), 0.0), 1.0))
        
        if isinstance(experience.confidence_score, (int, float)) and not isinstance(experience.confidence_score, bool):
            return float(min(max(float(experience.confidence_score), 0.0), 1.0))
        
        return None
    
    @staticmethod
    def _calculate_consistency(scores: List[float]) -> float:
        """Consistencia de los resultados: 1.0 = resultados idénticos, 0.0 = máxima dispersión"""
        if not scores:
            return 0.0
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        # normaliza la desviación por la media (o 1.0 si la media es 0)
        normalized = (variance ** 0.5) / (mean if mean > 0 else 1.0)
        return float(max(0.0, min(1.0, 1.0 - normalized)))
    
    def evaluate_learning_strategy(self,
                                   learning_system: str,
                                   task_type: str,
                                   strategy: Optional[str] = None,
                                   experiences: Optional[List[LearningExperience]] = None) -> LearningEvaluation:
        """
        Evalúa una estrategia de aprendizaje usando únicamente evidencia disponible.
        
        Separa resultado puntual de patrón estable y evita adaptar por muestras insuficientes.
        
        Args:
            learning_system: Sistema de aprendizaje a evaluar
            task_type: Tipo de tarea a evaluar
            strategy: Estrategia concreta; si es None se evalúan todas y se agrega
            experiences: Experiencias a considerar; por defecto las capturadas por el sistema
        
        Returns:
            LearningEvaluation con métricas, evidencia y veredicto
        """
        source = experiences if experiences is not None else self.experiences
        
        selected = [
            exp for exp in source
            if exp.learning_system == learning_system
            and exp.task_type == task_type
            and (strategy is None or exp.strategy_used == strategy)
        ]
        
        required = int(self.config["min_experiences_for_analysis"])
        scores: List[float] = []
        indicators: List[str] = []
        sample_ids: List[str] = []
        confidences: List[float] = []
        
        for exp in selected:
            score = self._experience_success_score(exp)
            if score is None:
                continue
            scores.append(score)
            sample_ids.append(exp.experience_id)
            if isinstance(exp.confidence_score, (int, float)) and not isinstance(exp.confidence_score, bool):
                confidences.append(float(exp.confidence_score))
            for name in (exp.outcome or {}).get("success_indicators", []) or []:
                if name not in indicators:
                    indicators.append(name)
            for name in (exp.outcome or {}).get("failure_indicators", []) or []:
                failure_name = f"failure:{name}"
                if failure_name not in indicators:
                    indicators.append(failure_name)
        
        sample_count = len(scores)
        sufficient = sample_count >= required
        
        success_rate = (sum(scores) / sample_count) if sample_count else 0.0
        confidence = (sum(confidences) / len(confidences)) if confidences else 0.0
        consistency = self._calculate_consistency(scores)
        
        # Un patrón solo es estable si hay muestras suficientes y baja dispersión
        stable_pattern = bool(sufficient and consistency >= self.config["confidence_threshold"])
        
        if not sufficient:
            result = MetaLearningResult.INSUFFICIENT_DATA
        elif stable_pattern and success_rate >= self.config["confidence_threshold"]:
            result = MetaLearningResult.IMPROVEMENT_DETECTED
        elif stable_pattern:
            result = MetaLearningResult.DEGRADATION_DETECTED
        else:
            # Evidencia suficiente pero resultados inconsistentes: no permite afirmar patrón
            result = MetaLearningResult.CONFLICTING_SIGNALS
        
        return LearningEvaluation(
            learning_system=learning_system,
            task_type=task_type,
            strategy=strategy or "aggregate",
            sample_count=sample_count,
            required_samples=required,
            success_rate=success_rate,
            confidence=confidence,
            consistency=consistency,
            sufficient_evidence=sufficient,
            stable_pattern=stable_pattern,
            result=result,
            indicators=indicators,
            sample_ids=sample_ids
        )
    
    def get_learning_evaluations(self,
                                 learning_system: Optional[str] = None,
                                 task_type: Optional[str] = None) -> List[LearningEvaluation]:
        """Evalúa todas las combinaciones sistema/tarea/estrategia presentes en las experiencias"""
        combos = set()
        for exp in self.experiences:
            if learning_system and exp.learning_system != learning_system:
                continue
            if task_type and exp.task_type != task_type:
                continue
            combos.add((exp.learning_system, exp.task_type, exp.strategy_used))
        
        return [
            self.evaluate_learning_strategy(system_name, task, strategy)
            for system_name, task, strategy in sorted(combos)
        ]
    
    def analyze_learning_patterns(self) -> List[MetaLearningInsight]:
        """
        Analiza patrones en las experiencias de aprendizaje para generar insights
        
        Returns:
            Lista de insights generados
        """
        if len(self.experiences) < self.config["min_experiences_for_analysis"]:
            self.logger.warning(f"Insuficientes experiencias para análisis: {len(self.experiences)}")
            return []
        
        insights = []
        
        # Análisis por nivel de metaprendizaje
        insights.extend(self._analyze_strategy_selection())
        insights.extend(self._analyze_parameter_adaptation())
        insights.extend(self._analyze_contextual_optimization())
        insights.extend(self._analyze_learning_rate_adjustment())
        
        # Filtrar insights por confianza
        filtered_insights = [
            insight for insight in insights 
            if insight.confidence >= self.config["confidence_threshold"]
        ]
        
        # Añadir insights al sistema
        for insight in filtered_insights:
            insight.insight_id = f"insight_{int(time.time())}_{hash(insight.description) % 10000}"
            insight.timestamp = datetime.now()
            self.insights.append(insight)
        
        self.logger.info(f"Generados {len(filtered_insights)} insights de metaprendizaje")
        return filtered_insights
    
    def _analyze_strategy_selection(self) -> List[MetaLearningInsight]:
        """Análisis de selección de estrategias"""
        insights = []
        
        # Agrupar experiencias por sistema y estrategia
        system_strategies = {}
        for exp in self.experiences:
            key = f"{exp.learning_system}_{exp.task_type}"
            if key not in system_strategies:
                system_strategies[key] = []
            system_strategies[key].append(exp)
        
        # Evaluar rendimiento de estrategias
        for key, experiences in system_strategies.items():
            if len(experiences) < 5:  # Mínimo para análisis
                continue
            
            # Calcular rendimiento promedio por estrategia
            strategy_performance = {}
            for exp in experiences:
                strategy = exp.strategy_used
                if strategy not in strategy_performance:
                    strategy_performance[strategy] = []
                strategy_performance[strategy].append(exp.success_metrics.get('success_rate', 0))
            
            # Identificar mejor estrategia
            best_strategy = None
            best_avg = 0
            for strategy, rates in strategy_performance.items():
                avg_rate = sum(rates) / len(rates)
                if avg_rate > best_avg:
                    best_avg = avg_rate
                    best_strategy = strategy
            
            # Generar insight si hay diferencia significativa
            if best_strategy and best_avg > 0.7:
                insight = MetaLearningInsight(
                    insight_id="",
                    timestamp=datetime.now(),
                    level=MetaLearningLevel.STRATEGY_SELECTION,
                    description=f"La estrategia '{best_strategy}' muestra mejor rendimiento ({best_avg:.2f}) para {key}",
                    confidence=min(best_avg, 1.0),
                    evidence=experiences,
                    recommendation=f"Priorizar uso de '{best_strategy}' para tareas similares",
                    impact_score=best_avg * 0.8,
                    learning_system=experiences[0].learning_system,
                    task_type=experiences[0].task_type
                )
                insights.append(insight)
        
        return insights
    
    def _analyze_parameter_adaptation(self) -> List[MetaLearningInsight]:
        """Análisis de adaptación de parámetros"""
        insights = []
        
        # Analizar parámetros que afectan el rendimiento
        param_impact = {}
        for exp in self.experiences:
            for param, value in exp.parameters.items():
                param_key = f"{param}_{exp.task_type}"
                if param_key not in param_impact:
                    param_impact[param_key] = []
                
                # Calcular impacto en el éxito
                success_rate = exp.success_metrics.get('success_rate', 0)
                param_impact[param_key].append({
                    'value': value,
                    'success': success_rate,
                    'experience': exp
                })
        
        # Identificar parámetros óptimos
        for param_key, data in param_impact.items():
            if len(data) < 3:  # Mínimo para análisis
                continue
            
            # Encontrar valor óptimo
            success_by_value = {}
            for item in data:
                value = item['value']
                if value not in success_by_value:
                    success_by_value[value] = []
                success_by_value[value].append(item['success'])
            
            # Calcular éxito promedio por valor
            avg_success = {}
            for value, successes in success_by_value.items():
                avg_success[value] = sum(successes) / len(successes)
            
            # Encontrar mejor valor
            best_value = max(avg_success.keys(), key=lambda x: avg_success[x])
            best_success = avg_success[best_value]
            
            # Generar insight
            if best_success > 0.7:
                insight = MetaLearningInsight(
                    insight_id="",
                    timestamp=datetime.now(),
                    level=MetaLearningLevel.PARAMETER_ADAPTATION,
                    description=f"El valor '{best_value}' para parámetro '{param_key.split('_')[0]}' óptimo ({best_success:.2f})",
                    confidence=best_success,
                    evidence=[item['experience'] for item in data],
                    recommendation=f"Ajustar parámetro '{param_key.split('_')[0]}' a '{best_value}'",
                    impact_score=best_success * 0.6,
                    learning_system=data[0]['experience'].learning_system,
                    task_type=data[0]['experience'].task_type
                )
                insights.append(insight)
        
        return insights
    
    def _analyze_contextual_optimization(self) -> List[MetaLearningInsight]:
        """Análisis de optimización contextual"""
        insights = []
        
        # Analizar contexto vs rendimiento
        context_patterns = {}
        for exp in self.experiences:
            # Crear patrón de contexto
            context_key = self._create_context_pattern(exp.context)
            if context_key not in context_patterns:
                context_patterns[context_key] = []
            context_patterns[context_key].append(exp)
        
        # Evaluar rendimiento por contexto
        for context_key, experiences in context_patterns.items():
            if len(experiences) < 3:
                continue
            
            avg_success = sum(exp.success_metrics.get('success_rate', 0) for exp in experiences) / len(experiences)
            
            if avg_success > 0.8:  # Alto rendimiento en contexto específico
                insight = MetaLearningInsight(
                    insight_id="",
                    timestamp=datetime.now(),
                    level=MetaLearningLevel.CONTEXTUAL_OPTIMIZATION,
                    description=f"Alto rendimiento ({avg_success:.2f}) en contexto: {context_key}",
                    confidence=avg_success,
                    evidence=experiences,
                    recommendation=f"Optimizar estrategias para contexto similar a '{context_key}'",
                    impact_score=avg_success * 0.7,
                    learning_system=experiences[0].learning_system,
                    task_type=experiences[0].task_type
                )
                insights.append(insight)
        
        return insights
    
    def _analyze_learning_rate_adjustment(self) -> List[MetaLearningInsight]:
        """Análisis de ajuste de tasa de aprendizaje"""
        insights = []
        
        # Analizar tendencias de rendimiento
        if len(self.experiences) < 10:
            return insights
        
        # Ordenar experiencias por tiempo
        sorted_experiences = sorted(self.experiences, key=lambda x: x.timestamp)
        
        # Calcular tendencias
        window_size = min(10, len(sorted_experiences) // 2)
        recent_success = []
        older_success = []
        
        for i, exp in enumerate(sorted_experiences):
            success_rate = exp.success_metrics.get('success_rate', 0)
            if i >= len(sorted_experiences) - window_size:
                recent_success.append(success_rate)
            else:
                older_success.append(success_rate)
        
        if recent_success and older_success:
            recent_avg = sum(recent_success) / len(recent_success)
            older_avg = sum(older_success) / len(older_success)
            
            # Detectar mejora o degradación
            if recent_avg > older_avg + 0.1:  # Mejora significativa
                insight = MetaLearningInsight(
                    insight_id="",
                    timestamp=datetime.now(),
                    level=MetaLearningLevel.LEARNING_RATE_ADJUSTMENT,
                    description=f"Mejora de rendimiento detectada: {older_avg:.2f} -> {recent_avg:.2f}",
                    confidence=min(recent_avg, 1.0),
                    evidence=sorted_experiences[-window_size:],
                    recommendation="Mantener configuración actual - tendencia positiva",
                    impact_score=(recent_avg - older_avg) * 0.9,
                    learning_system=sorted_experiences[-1].learning_system,
                    task_type=sorted_experiences[-1].task_type
                )
                insights.append(insight)
            elif recent_avg < older_avg - 0.1:  # Degradación significativa
                insight = MetaLearningInsight(
                    insight_id="",
                    timestamp=datetime.now(),
                    level=MetaLearningLevel.LEARNING_RATE_ADJUSTMENT,
                    description=f"Degradación de rendimiento detectada: {older_avg:.2f} -> {recent_avg:.2f}",
                    confidence=1.0 - recent_avg,
                    evidence=sorted_experiences[-window_size:],
                    recommendation="Revisar parámetros de aprendizaje - tendencia negativa",
                    impact_score=(older_avg - recent_avg) * 0.8,
                    learning_system=sorted_experiences[-1].learning_system,
                    task_type=sorted_experiences[-1].task_type
                )
                insights.append(insight)
        
        return insights
    
    def _create_context_pattern(self, context: Dict[str, Any]) -> str:
        """Crea un patrón de contexto para análisis"""
        # Extraer características relevantes del contexto
        relevant_keys = ['task_type', 'system_state', 'resource_usage', 'time_pattern']
        pattern_parts = []
        
        for key in relevant_keys:
            if key not in context:
                continue
            raw_value = context[key]
            # resource_usage debe tratarse como dict: convertir antes a str
            # hacía que esta rama nunca se ejecutara.
            if key == 'resource_usage' and isinstance(raw_value, dict):
                cpu = raw_value.get('cpu_usage', 0)
                memory = raw_value.get('memory_usage', 0)
                pattern_parts.append(f"{key}_cpu{cpu}_mem{memory}")
            else:
                pattern_parts.append(f"{key}_{raw_value}")
        
        return "_".join(pattern_parts)
    
    def apply_meta_learning_insights(self, insights: List[MetaLearningInsight]) -> Dict[str, Any]:
        """
        Aplica insights de metaprendizaje a los sistemas de aprendizaje
        
        Args:
            insights: Lista de insights a aplicar
        
        Returns:
            Resultado de la aplicación
        """
        results = {
            'applied_insights': 0,
            'failed_insights': 0,
            'systems_updated': [],
            'errors': []
        }
        
        for insight in insights:
            try:
                # Un insight construido a mano puede no declarar el sistema de origen;
                # en ese caso se toma de su evidencia real, no se inventa.
                if not insight.learning_system and insight.evidence:
                    insight.learning_system = insight.evidence[0].learning_system
                if not insight.task_type and insight.evidence:
                    insight.task_type = insight.evidence[0].task_type

                if insight.level == MetaLearningLevel.STRATEGY_SELECTION:
                    result = self._apply_strategy_selection_insight(insight)
                elif insight.level == MetaLearningLevel.PARAMETER_ADAPTATION:
                    result = self._apply_parameter_adaptation_insight(insight)
                elif insight.level == MetaLearningLevel.CONTEXTUAL_OPTIMIZATION:
                    result = self._apply_contextual_optimization_insight(insight)
                elif insight.level == MetaLearningLevel.LEARNING_RATE_ADJUSTMENT:
                    result = self._apply_learning_rate_adjustment_insight(insight)
                else:
                    result = {'success': False, 'reason': 'Unsupported level'}
                
                if result.get('success', False):
                    results['applied_insights'] += 1
                    insight.applied = True
                    if insight.learning_system not in results['systems_updated']:
                        results['systems_updated'].append(insight.learning_system)
                else:
                    results['failed_insights'] += 1
                    results['errors'].append({
                        'insight_id': insight.insight_id,
                        'error': result.get('reason', 'Unknown error')
                    })
                
            except Exception as e:
                results['failed_insights'] += 1
                results['errors'].append({
                    'insight_id': insight.insight_id,
                    'error': str(e)
                })
                self.logger.error(f"Error al aplicar insight {insight.insight_id}: {e}")
        
        self.logger.info(f"Aplicados {results['applied_insights']}/{len(insights)} insights")
        return results

    # ------------------------------------------------------------------
    # 2.8.3.7 — SEGURIDAD
    # El metaprendizaje solo cambia motores reales de aprendizaje. Estos
    # metodos limitan los cambios automáticos, bloquean los que tocarían
    # estructuras críticas sin validación y registran cada decisión.
    # La aplicación explícita (apply_meta_learning_insights / apply_meta_rule)
    # no cambia de comportamiento: la seguridad limita lo automático.
    # ------------------------------------------------------------------

    #: Componente de integración al que pertenece el sistema de un insight.
    INSIGHT_SYSTEM_TO_COMPONENT = {
        'adaptive': 'adaptive_learning',
        'self_improvement': 'self_improvement',
        'contextual_adaptation': 'contextual_adaptation',
    }

    def get_security_limits(self) -> Dict[str, Any]:
        """Límites de seguridad normalizados desde la configuración real"""
        security = self.config.get("security", {})
        if not isinstance(security, dict):
            security = {}
        max_changes = security.get("max_auto_changes_per_cycle", 3)
        if not isinstance(max_changes, int) or isinstance(max_changes, bool) or max_changes < 0:
            max_changes = 3
        protected = security.get("protected_actions", ["reset_stats"])
        if not isinstance(protected, list):
            protected = ["reset_stats"]
        max_decisions = security.get("max_security_decisions", 500)
        if not isinstance(max_decisions, int) or isinstance(max_decisions, bool) or max_decisions <= 0:
            max_decisions = 500
        return {
            'auto_apply_enabled': bool(self.config.get("auto_apply_insights", False)),
            'max_auto_changes_per_cycle': max_changes,
            'protected_actions': [action for action in protected if isinstance(action, str)],
            'require_validation_for_shared_engines': bool(
                security.get("require_validation_for_shared_engines", True)),
            'max_security_decisions': max_decisions,
            'auto_changes_applied': self.auto_changes_applied,
            'auto_changes_remaining': max(0, max_changes - self.auto_changes_applied),
        }

    def reset_auto_change_cycle(self) -> None:
        """Reinicia el contador de cambios automáticos del ciclo actual"""
        self.auto_changes_applied = 0

    def get_shared_components(self) -> List[str]:
        """Componentes cuyo motor es una instancia compartida (2.8.3.6)"""
        shared = []
        for name, attribute in self.INTEGRATION_ATTRIBUTES.items():
            engine = getattr(self, attribute, None)
            if engine is not None and self.integrated_components.get(name) is engine:
                shared.append(name)
        return sorted(shared)

    def _component_for_insight(self, insight: MetaLearningInsight) -> Optional[str]:
        """Componente afectado por un insight según su sistema de origen real"""
        system = insight.learning_system or ""
        if not system and insight.evidence:
            system = insight.evidence[0].learning_system
        for token, component in self.INSIGHT_SYSTEM_TO_COMPONENT.items():
            if token in system:
                return component
        return None

    def _record_security_decision(self, subject_type: str, subject_id: str,
                                  allowed: bool, reason: str,
                                  detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Registra una decisión de seguridad (2.8.3.7.3)"""
        decision = {
            'timestamp': datetime.now().isoformat(),
            'subject_type': subject_type,
            'subject_id': subject_id,
            'allowed': bool(allowed),
            'reason': reason,
            'detail': detail or {}
        }
        self.security_decisions.append(decision)
        max_decisions = self.get_security_limits()['max_security_decisions']
        if len(self.security_decisions) > max_decisions:
            del self.security_decisions[:-max_decisions]
        (self.logger.info if allowed else self.logger.warning)(
            f"Seguridad {subject_type} {subject_id}: "
            f"{'permitido' if allowed else 'bloqueado'} - {reason}")
        return decision

    def get_security_decisions(self) -> List[Dict[str, Any]]:
        """Decisiones de seguridad registradas"""
        return list(self.security_decisions)

    def get_security_status(self) -> Dict[str, Any]:
        """Estado de seguridad: límites, pendientes y decisiones por resultado"""
        blocked = [d for d in self.security_decisions if not d['allowed']]
        reasons: Dict[str, int] = {}
        for decision in blocked:
            reasons[decision['reason']] = reasons.get(decision['reason'], 0) + 1
        return {
            'limits': self.get_security_limits(),
            'shared_components': self.get_shared_components(),
            'total_decisions': len(self.security_decisions),
            'allowed_decisions': len(self.security_decisions) - len(blocked),
            'blocked_decisions': len(blocked),
            'blocked_reasons': reasons
        }

    def check_insight_security(self, insight: MetaLearningInsight) -> Tuple[bool, str]:
        """
        Decide si un insight puede aplicarse automáticamente.
        Retorna (permitido, motivo).
        """
        limits = self.get_security_limits()
        if not limits['auto_apply_enabled']:
            return False, "auto_apply_insights deshabilitado"

        component = self._component_for_insight(insight)
        if limits['require_validation_for_shared_engines'] \
                and component in self.get_shared_components() \
                and insight.validation_required:
            return False, f"requiere validación previa en motor compartido: {component}"

        if limits['auto_changes_remaining'] <= 0:
            return False, "límite de cambios automáticos por ciclo alcanzado"

        return True, "cambio automático permitido"

    def check_meta_rule_security(self, meta_rule: MetaRule) -> Tuple[bool, str]:
        """Decide si una meta-regla puede aplicarse automáticamente"""
        limits = self.get_security_limits()
        if not limits['auto_apply_enabled']:
            return False, "auto_apply_insights deshabilitado"

        if meta_rule.action in limits['protected_actions']:
            return False, f"acción protegida sin validación: {meta_rule.action}"

        if limits['require_validation_for_shared_engines'] \
                and 'self_improvement' in self.get_shared_components() \
                and not meta_rule.is_valid():
            return False, "meta-regla inválida sobre motor compartido"

        if limits['auto_changes_remaining'] <= 0:
            return False, "límite de cambios automáticos por ciclo alcanzado"

        return True, "cambio automático permitido"

    def auto_apply_insights(self, insights: List[MetaLearningInsight]) -> Dict[str, Any]:
        """
        Aplica insights de forma automática y limitada (2.8.3.7.1).

        Cada insight se aplica individualmente para que un bloqueo no impida
        evaluar los siguientes. Los límites son por ciclo.
        """
        results = {
            'applied_insights': 0,
            'blocked_insights': 0,
            'failed_insights': 0,
            'decisions': [],
            'errors': []
        }

        for insight in insights:
            allowed, reason = self.check_insight_security(insight)
            results['decisions'].append(self._record_security_decision(
                'insight', insight.insight_id, allowed, reason,
                {'level': insight.level.value,
                 'confidence': insight.confidence,
                 'component': self._component_for_insight(insight)}))

            if not allowed:
                results['blocked_insights'] += 1
                continue

            applied = self.apply_meta_learning_insights([insight])
            if applied['applied_insights']:
                self.auto_changes_applied += 1
                results['applied_insights'] += 1
            else:
                results['failed_insights'] += 1
                results['errors'].extend(applied['errors'])

        self.logger.info(
            f"Aplicación automática: {results['applied_insights']} aplicados, "
            f"{results['blocked_insights']} bloqueados")
        return results

    def auto_apply_meta_rules(self) -> Dict[str, Any]:
        """Aplica las meta-reglas registradas de forma automática y limitada"""
        results = {
            'applied_meta_rules': 0,
            'blocked_meta_rules': 0,
            'decisions': [],
            'applications': []
        }

        for meta_rule in self.get_meta_rules():
            allowed, reason = self.check_meta_rule_security(meta_rule)
            results['decisions'].append(self._record_security_decision(
                'meta_rule', meta_rule.meta_rule_id, allowed, reason,
                {'target_rule_id': meta_rule.target_rule_id,
                 'action': meta_rule.action}))

            if not allowed:
                results['blocked_meta_rules'] += 1
                continue

            application = self.apply_meta_rule(meta_rule)
            results['applications'].append(application)
            if application.status == MetaRuleStatus.APPLIED:
                self.auto_changes_applied += 1
                results['applied_meta_rules'] += 1
            else:
                results['blocked_meta_rules'] += 1

        return results
    
    @staticmethod
    def _target_store(engine: Any, attribute: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve el almacén real de estrategias/parámetros de un motor de aprendizaje.

        ni AdaptiveLearningEngine ni SelfImprovementSystem declaran estos mapas,
        por lo que se crean la primera vez que se usan. Si el motor no existe,
        se devuelve None y la aplicación falla de forma explicita.
        """
        if engine is None:
            return None
        store = getattr(engine, attribute, None)
        if store is None:
            store = {}
            setattr(engine, attribute, store)
        if not isinstance(store, dict):
            return None
        return store

    def _apply_strategy_selection_insight(self, insight: MetaLearningInsight) -> Dict[str, Any]:
        """Aplica insight de selección de estrategia"""
        try:
            # Extraer mejor estrategia de las evidencias
            best_strategy = None
            best_success = 0
            
            for exp in insight.evidence:
                success_rate = exp.success_metrics.get('success_rate', 0)
                if success_rate > best_success:
                    best_success = success_rate
                    best_strategy = exp.strategy_used
            
            if best_strategy:
                # Aplicar al sistema correspondiente
                target = None
                if 'adaptive' in insight.learning_system:
                    target = self._target_store(self.adaptive_engine, 'preferred_strategies')
                elif 'self_improvement' in insight.learning_system:
                    target = self._target_store(self.self_improvement, 'preferred_strategies')

                if target is not None:
                    target[insight.task_type] = best_strategy
                    return {'success': True, 'strategy_applied': best_strategy}

                return {'success': False, 'reason': 'No target system identified'}
            
            return {'success': False, 'reason': 'No strategy identified'}
        
        except Exception as e:
            return {'success': False, 'reason': str(e)}
    
    def _apply_parameter_adaptation_insight(self, insight: MetaLearningInsight) -> Dict[str, Any]:
        """Aplica insight de adaptación de parámetros"""
        try:
            # Extraer el nombre del parámetro de la evidencia.
            # Formato real: "El valor '0.1' para parámetro 'learning_rate' óptimo (0.85)"
            # El valor es la cita 1; el nombre del parámetro es la cita 3.
            quoted = insight.description.split("'")
            if len(quoted) < 4:
                return {'success': False, 'reason': 'Insight sin formato de parámetro reconocible'}
            param_name = quoted[3]
            optimal_value = None
            
            for exp in insight.evidence:
                if param_name in exp.parameters:
                    # Usar el valor que mejor funcionó
                    success_rate = exp.success_metrics.get('success_rate', 0)
                    if optimal_value is None or success_rate > optimal_value.get('success', 0):
                        optimal_value = {
                            'value': exp.parameters[param_name],
                            'success': success_rate
                        }
            
            if optimal_value:
                # Aplicar parámetro al sistema real
                target = None
                if 'adaptive' in insight.learning_system:
                    target = self._target_store(self.adaptive_engine, 'learning_params')
                elif 'self_improvement' in insight.learning_system:
                    target = self._target_store(self.self_improvement, 'learning_params')

                if target is not None:
                    target[param_name] = optimal_value['value']
                    return {'success': True, 'parameter': param_name, 'value': optimal_value['value']}

                return {'success': False, 'reason': 'No target system identified'}
            
            return {'success': False, 'reason': 'No parameter identified'}
        
        except Exception as e:
            return {'success': False, 'reason': str(e)}
    
    def _apply_contextual_optimization_insight(self, insight: MetaLearningInsight) -> Dict[str, Any]:
        """Aplica insight de optimización contextual"""
        try:
            # Extraer patrón de contexto
            context_pattern = insight.description.split("context: ")[1].split(")")[0]
            
            # Almacenar para uso futuro
            if 'contextual_patterns' not in self.meta_rules:
                self.meta_rules['contextual_patterns'] = {}
            
            self.meta_rules['contextual_patterns'][context_pattern] = {
                'recommended_strategy': insight.recommendation,
                'confidence': insight.confidence,
                'impact_score': insight.impact_score
            }
            
            return {'success': True, 'pattern': context_pattern}
        
        except Exception as e:
            return {'success': False, 'reason': str(e)}
    
    def _apply_learning_rate_adjustment_insight(self, insight: MetaLearningInsight) -> Dict[str, Any]:
        """Aplica insight de ajuste de tasa de aprendizaje"""
        try:
            # Determinar dirección del ajuste
            if "mejora" in insight.description.lower():
                # Aumentar tasa de aprendizaje
                adjustment_factor = 1.1
                action = "increased"
            else:
                # Disminuir tasa de aprendizaje
                adjustment_factor = 0.9
                action = "decreased"
            
            # Aplicar ajuste al motor real identificado por el insight
            target = None
            if 'adaptive' in insight.learning_system:
                target = self._target_store(self.adaptive_engine, 'learning_params')
            elif 'self_improvement' in insight.learning_system:
                target = self._target_store(self.self_improvement, 'learning_params')

            if target is not None:
                current_rate = target.get('learning_rate', 0.1)
                new_rate = max(0.01, min(1.0, current_rate * adjustment_factor))
                target['learning_rate'] = new_rate
                return {'success': True, 'action': action, 'new_rate': new_rate}
            
            return {'success': False, 'reason': 'No system identified'}
        
        except Exception as e:
            return {'success': False, 'reason': str(e)}
    
    def get_meta_learning_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas del sistema de metaprendizaje"""
        # El estado real es la lista de experiencias: el contador total_experiences
        # solo se incrementa en los métodos de captura y queda desincronizado cuando
        # las experiencias se añaden directamente (análisis, carga, integración).
        total_experiences = len(self.experiences)
        total_insights = len(self.insights)
        applied_insights = len([i for i in self.insights if i.applied])
        return {
            'total_experiences': total_experiences,
            'active_insights': len([i for i in self.insights if not i.applied]),
            'applied_insights': applied_insights,
            # Proporción de insights realmente aplicados sobre los generados.
            'success_rate': applied_insights / total_insights if total_insights else 0.0,
            'confidence_distribution': self._calculate_confidence_distribution(),
            'system_coverage': self._get_system_coverage(),
            'learning_progress': self._calculate_learning_progress()
        }
    
    def _calculate_confidence_distribution(self) -> Dict[str, float]:
        """Calcula distribución de confianza de los insights"""
        if not self.insights:
            return {'low': 0, 'medium': 0, 'high': 0}
        
        low = sum(1 for i in self.insights if i.confidence < 0.5)
        medium = sum(1 for i in self.insights if 0.5 <= i.confidence < 0.8)
        high = sum(1 for i in self.insights if i.confidence >= 0.8)
        
        total = len(self.insights)
        return {
            'low': low / total,
            'medium': medium / total,
            'high': high / total
        }
    
    def _get_system_coverage(self) -> Dict[str, int]:
        """Obtiene cobertura por sistema de aprendizaje"""
        coverage = {}
        for exp in self.experiences:
            system = exp.learning_system
            coverage[system] = coverage.get(system, 0) + 1
        return coverage
    
    def _calculate_learning_progress(self) -> Dict[str, float]:
        """Calcula progreso de aprendizaje por sistema"""
        progress = {}
        
        for system in self._get_system_coverage().keys():
            system_experiences = [exp for exp in self.experiences if exp.learning_system == system]
            
            if system_experiences:
                # Calcular mejora reciente
                recent = system_experiences[-10:]  # Últimas 10 experiencias
                older = system_experiences[:-10] if len(system_experiences) > 10 else []
                
                recent_avg = sum(exp.success_metrics.get('success_rate', 0) for exp in recent) / len(recent)
                older_avg = sum(exp.success_metrics.get('success_rate', 0) for exp in older) / len(older) if older else 0
                
                progress[system] = recent_avg - older_avg
        
        return progress
    
    def save_meta_learning_data(self) -> bool:
        """Guarda datos de metaprendizaje"""
        try:
            os.makedirs(os.path.dirname(self.config["export_path"]), exist_ok=True)
            
            # Guardar experiencias
            experiences_data = []
            for exp in self.experiences:
                exp_dict = {
                    'experience_id': exp.experience_id,
                    'timestamp': exp.timestamp.isoformat(),
                    'learning_system': exp.learning_system,
                    'task_type': exp.task_type,
                    'context': exp.context,
                    'strategy_used': exp.strategy_used,
                    'parameters': exp.parameters,
                    'outcome': exp.outcome,
                    'success_metrics': exp.success_metrics,
                    'confidence_score': exp.confidence_score,
                    'metadata': exp.metadata
                }
                experiences_data.append(exp_dict)
            
            # Guardar insights
            insights_data = []
            for insight in self.insights:
                insight_dict = {
                    'insight_id': insight.insight_id,
                    'timestamp': insight.timestamp.isoformat(),
                    'level': insight.level.value,
                    'description': insight.description,
                    'confidence': insight.confidence,
                    'evidence_count': len(insight.evidence),
                    'recommendation': insight.recommendation,
                    'impact_score': insight.impact_score,
                    'validation_required': insight.validation_required,
                    'applied': insight.applied
                }
                insights_data.append(insight_dict)
            
            # Guardar datos
            export_file = os.path.join(self.config["export_path"], f"meta_learning_data_{int(time.time())}.json")
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'experiences': experiences_data,
                    'insights': insights_data,
                    'metrics': self.get_meta_learning_metrics(),
                    'config': self.config
                }, f, indent=2)
            
            self.logger.info(f"Datos de metaprendizaje guardados en {export_file}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error al guardar datos de metaprendizaje: {e}")
            return False
    
    def load_meta_learning_data(self, file_path: str) -> bool:
        """Carga datos de metaprendizaje desde archivo"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Cargar experiencias
            self.experiences = []
            for exp_data in data.get('experiences', []):
                experience = LearningExperience(
                    experience_id=exp_data['experience_id'],
                    timestamp=datetime.fromisoformat(exp_data['timestamp']),
                    learning_system=exp_data['learning_system'],
                    task_type=exp_data['task_type'],
                    context=exp_data['context'],
                    strategy_used=exp_data['strategy_used'],
                    parameters=exp_data['parameters'],
                    outcome=exp_data['outcome'],
                    success_metrics=exp_data['success_metrics'],
                    confidence_score=exp_data['confidence_score'],
                    metadata=exp_data.get('metadata', {})
                )
                self.experiences.append(experience)
            
            # Cargar insights
            self.insights = []
            for insight_data in data.get('insights', []):
                insight = MetaLearningInsight(
                    insight_id=insight_data['insight_id'],
                    timestamp=datetime.fromisoformat(insight_data['timestamp']),
                    level=MetaLearningLevel(insight_data['level']),
                    description=insight_data['description'],
                    confidence=insight_data['confidence'],
                    evidence=[],  # No se cargan evidencias por simplicidad
                    recommendation=insight_data['recommendation'],
                    impact_score=insight_data['impact_score'],
                    validation_required=insight_data['validation_required'],
                    applied=insight_data['applied']
                )
                self.insights.append(insight)
            
            self.total_experiences = len(self.experiences)
            self.logger.info(f"Datos de metaprendizaje cargados desde {file_path}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error al cargar datos de metaprendizaje: {e}")
            return False
    
    def start_meta_learning_process(self):
        """Inicia el proceso asíncrono de metaprendizaje"""
        if self.is_running:
            self.logger.warning("MetaLearningSystem ya está en ejecución")
            return
        
        self.is_running = True
        self.processing_thread = threading.Thread(target=self._meta_learning_loop)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        self.logger.info("Proceso de metaprendizaje iniciado")
    
    def stop_meta_learning_process(self):
        """Detiene el proceso asíncrono de metaprendizaje"""
        self.is_running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        
        self.logger.info("Proceso de metaprendizaje detenido")
    
    def _meta_learning_loop(self):
        """Bucle principal de procesamiento de metaprendizaje"""
        while self.is_running:
            try:
                # Procesar experiencias en la cola
                while not self.learning_queue.empty():
                    experience = self.learning_queue.get_nowait()
                    
                    # Procesar experiencia
                    self._process_single_experience(experience)
                    
                    # Guardar periodicamente
                    if self.config["persistence_enabled"] and self.total_experiences % 100 == 0:
                        self.save_meta_learning_data()
                
                # Análisis periódico
                if self.total_experiences % self.config["analysis_interval"] == 0:
                    insights = self.analyze_learning_patterns()
                    if insights and self.config["auto_apply_insights"]:
                        # 2.8.3.7: la aplicación automática respeta los límites
                        # por ciclo y registra cada decisión de seguridad.
                        self.reset_auto_change_cycle()
                        self.auto_apply_insights(insights)
                        self.auto_apply_meta_rules()
                
                # Esperar antes de siguiente ciclo
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error en bucle de metaprendizaje: {e}")
                time.sleep(5)
    
    def _process_single_experience(self, experience: LearningExperience):
        """Procesa una experiencia individual"""
        try:
            # Actualizar métricas
            self.total_experiences += 1
            
            # Registrar en sistema de logging
            self.logger.info(f"Procesando experiencia {experience.experience_id}: "
                           f"{experience.learning_system} - {experience.task_type} - "
                           f"Éxito: {experience.success_metrics.get('success_rate', 0):.2f}")
            
            # Aquí se podrían añadir análisis más detallados
            # Por ejemplo, detección de patrones inusuales, anomalías, etc.
            
        except Exception as e:
            self.logger.error(f"Error al procesar experiencia {experience.experience_id}: {e}")
    
    def validate_meta_learning_insights(self, insight_ids: List[str]) -> Dict[str, bool]:
        """Valida insights específicos"""
        results = {}
        
        for insight_id in insight_ids:
            insight = next((i for i in self.insights if i.insight_id == insight_id), None)
            if insight:
                # Simulación de validación
                # En un sistema real, esto implicaría pruebas adicionales o verificación externa
                validation_result = insight.confidence > 0.8  # Simplificación
                insight.validation_required = False
                insight.applied = validation_result
                results[insight_id] = validation_result
            else:
                results[insight_id] = False
        
        return results
    
    def get_recommendations(self, system_type: str = None, task_type: str = None) -> List[str]:
        """
        Obtiene recomendaciones basadas en insights de metaprendizaje
        
        Args:
            system_type: Filtrar por tipo de sistema (opcional)
            task_type: Filtrar por tipo de tarea (opcional)
        
        Returns:
            Lista de recomendaciones
        """
        recommendations = []
        
        for insight in self.insights:
            if insight.applied and insight.confidence >= self.config["confidence_threshold"]:
                # Sin sistema declarado se toma de la evidencia antes de filtrar
                if not insight.learning_system and insight.evidence:
                    insight.learning_system = insight.evidence[0].learning_system
                if not insight.task_type and insight.evidence:
                    insight.task_type = insight.evidence[0].task_type
                if system_type and system_type not in insight.learning_system:
                    continue
                if task_type and task_type != insight.task_type:
                    continue
                
                recommendations.append({
                    'insight_id': insight.insight_id,
                    'description': insight.description,
                    'recommendation': insight.recommendation,
                    'confidence': insight.confidence,
                    'impact_score': insight.impact_score,
                    'timestamp': insight.timestamp.isoformat()
                })
        
        # Ordenar por impacto y confianza
        recommendations.sort(key=lambda x: (x['impact_score'], x['confidence']), reverse=True)
        
        return recommendations

    # ------------------------------------------------------------------
    # 2.8.3.4 — META-REGLAS
    # Actúa sobre ImprovementRule de SelfImprovementSystem, que ya expone
    # enabled, priority, success_rate, execution_count e improvement_score.
    # No se inventan atributos que el modelo real no soporte.
    # ------------------------------------------------------------------

    def get_learning_rules(self) -> List[Any]:
        """Devuelve las ImprovementRule reales del SelfImprovementSystem"""
        system = self.self_improvement
        if system is None:
            return []
        return list(getattr(system, 'improvement_rules', []) or [])

    def get_meta_rules(self) -> List[MetaRule]:
        """Devuelve las meta-reglas registradas"""
        return list(self.meta_rule_definitions)

    def add_meta_rule(self, meta_rule: MetaRule) -> MetaRuleStatus:
        """Registra una meta-regla si su contrato es válido y no está duplicada"""
        if not isinstance(meta_rule, MetaRule) or not meta_rule.is_valid():
            self.logger.warning("Meta-regla rechazada: contrato no soportado")
            return MetaRuleStatus.REJECTED_INVALID
        if any(r.meta_rule_id == meta_rule.meta_rule_id for r in self.meta_rule_definitions):
            self.logger.warning(f"Meta-regla duplicada ignorada: {meta_rule.meta_rule_id}")
            return MetaRuleStatus.REJECTED_INVALID
        self.meta_rule_definitions.append(meta_rule)
        self.logger.info(f"Meta-regla registrada: {meta_rule.meta_rule_id}")
        return MetaRuleStatus.APPLIED

    @staticmethod
    def _compare_metric(value: Any, operator: str, threshold: float) -> bool:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if operator == "<":
            return value < threshold
        if operator == "<=":
            return value <= threshold
        if operator == ">":
            return value > threshold
        if operator == ">=":
            return value >= threshold
        if operator == "==":
            return value == threshold
        return False

    def _evaluate_meta_rule_condition(self, meta_rule: MetaRule, rule: Any) -> bool:
        """Evalúa la condición de la meta-regla sobre el estado real de la regla"""
        if meta_rule.min_execution_count > 0:
            executions = getattr(rule, 'execution_count', 0) or 0
            if executions < meta_rule.min_execution_count:
                return False
        current = getattr(rule, meta_rule.condition_metric, None)
        return self._compare_metric(current, meta_rule.operator, meta_rule.threshold)

    @staticmethod
    def _capture_rule_state(rule: Any) -> Dict[str, Any]:
        return {
            "enabled": getattr(rule, "enabled", None),
            "priority": getattr(rule, "priority", None),
            "success_rate": getattr(rule, "success_rate", None),
            "execution_count": getattr(rule, "execution_count", None),
            "improvement_score": getattr(rule, "improvement_score", None),
            "last_execution": getattr(rule, "last_execution", None),
        }

    def apply_meta_rule(self, meta_rule: MetaRule) -> MetaRuleApplication:
        """
        Aplica una meta-regla sobre la ImprovementRule objetivo.
        Guarda el estado previo para permitir reversión posterior.
        """
        if not isinstance(meta_rule, MetaRule) or not meta_rule.is_valid():
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.REJECTED_INVALID, {}, {}, "Contrato de meta-regla no soportado")

        target = next((r for r in self.get_learning_rules()
                       if getattr(r, 'rule_id', None) == meta_rule.target_rule_id), None)
        if target is None:
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.REJECTED_RULE_NOT_FOUND, {}, {},
                f"Regla objetivo no encontrada: {meta_rule.target_rule_id}")

        previous_state = self._capture_rule_state(target)

        if not meta_rule.enabled:
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.SKIPPED_CONDITION_NOT_MET, previous_state, {},
                "Meta-regla deshabilitada")

        if meta_rule.min_execution_count > 0 and \
                (getattr(target, 'execution_count', 0) or 0) < meta_rule.min_execution_count:
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.SKIPPED_INSUFFICIENT_SAMPLES, previous_state, {},
                "Muestra insuficiente de ejecuciones para evaluar la meta-regla")

        if not self._evaluate_meta_rule_condition(meta_rule, target):
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.SKIPPED_CONDITION_NOT_MET, previous_state, {},
                "Condición de la meta-regla no satisfecha")

        # Aplicación de una única operación soportada por el modelo real
        if meta_rule.action == "disable":
            target.enabled = False
        elif meta_rule.action == "enable":
            target.enabled = True
        elif meta_rule.action == "set_priority":
            if not isinstance(meta_rule.action_value, int) or isinstance(meta_rule.action_value, bool):
                return self._record_meta_rule(
                    meta_rule, MetaRuleStatus.SKIPPED_UNSUPPORTED_ACTION, previous_state, {},
                    "set_priority requiere action_value entero")
            target.priority = meta_rule.action_value
        elif meta_rule.action == "reset_stats":
            target.success_rate = 0.0
            target.execution_count = 0
            target.improvement_score = 0.0
            target.last_execution = None
        else:
            return self._record_meta_rule(
                meta_rule, MetaRuleStatus.SKIPPED_UNSUPPORTED_ACTION, previous_state, {},
                f"Acción no soportada: {meta_rule.action}")

        return self._record_meta_rule(
            meta_rule, MetaRuleStatus.APPLIED, previous_state, self._capture_rule_state(target),
            "Meta-regla aplicada")

    def verify_meta_rule_application(self, application: MetaRuleApplication) -> bool:
        """Verifica que el estado real de la regla coincide con el estado aplicado"""
        if application.status != MetaRuleStatus.APPLIED or application.reverted:
            return False
        target = next((r for r in self.get_learning_rules()
                       if getattr(r, 'rule_id', None) == application.target_rule_id), None)
        if target is None:
            return False
        for key, expected in application.new_state.items():
            if getattr(target, key, None) != expected:
                return False
        return True

    def revert_meta_rule_application(self, application: MetaRuleApplication) -> bool:
        """
        Revierte una aplicación de meta-regla restaurando el estado previo completo.
        Solo es posible si el estado previo fue registrado.
        """
        if application.reverted or not application.previous_state:
            return False
        target = next((r for r in self.get_learning_rules()
                       if getattr(r, 'rule_id', None) == application.target_rule_id), None)
        if target is None:
            return False
        for key, value in application.previous_state.items():
            if hasattr(target, key):
                setattr(target, key, value)
        application.reverted = True
        self.logger.info(f"Meta-regla revertida: {application.meta_rule_id}")
        return True

    def get_meta_rule_history(self) -> List[MetaRuleApplication]:
        return list(self.meta_rule_history)

    def _record_meta_rule(self, meta_rule: MetaRule, status: MetaRuleStatus,
                          previous_state: Dict[str, Any], new_state: Dict[str, Any],
                          message: str) -> MetaRuleApplication:
        if not isinstance(meta_rule, MetaRule):
            meta_rule = MetaRule("unknown", "unknown", "unknown", "success_rate", "==", 0.0, "disable")
        application = MetaRuleApplication(
            meta_rule_id=meta_rule.meta_rule_id,
            target_rule_id=meta_rule.target_rule_id,
            action=meta_rule.action,
            status=status,
            previous_state=previous_state,
            new_state=new_state,
            message=message
        )
        self.meta_rule_history.append(application)
        return application

    # ------------------------------------------------------------------
    # 2.8.3.5 — PERSISTENCIA
    # Reutiliza la persistencia ya existente (save/load_meta_learning_data)
    # y la extiende con el estado propio del metaprendizaje: meta-reglas,
    # historial de aplicaciones y experiencias recuperables.
    # ------------------------------------------------------------------

    STATE_VERSION = 1

    @staticmethod
    def _experience_to_dict(experience: LearningExperience) -> Dict[str, Any]:
        return {
            'experience_id': experience.experience_id,
            'timestamp': experience.timestamp.isoformat(),
            'learning_system': experience.learning_system,
            'task_type': experience.task_type,
            'context': experience.context,
            'strategy_used': experience.strategy_used,
            'parameters': experience.parameters,
            'outcome': experience.outcome,
            'success_metrics': experience.success_metrics,
            'confidence_score': experience.confidence_score,
            'metadata': experience.metadata
        }

    @staticmethod
    def _experience_from_dict(data: Any) -> Optional[LearningExperience]:
        if not isinstance(data, dict):
            return None
        try:
            return LearningExperience(
                experience_id=data['experience_id'],
                timestamp=datetime.fromisoformat(data['timestamp']),
                learning_system=data['learning_system'],
                task_type=data['task_type'],
                context=data.get('context', {}),
                strategy_used=data.get('strategy_used', ''),
                parameters=data.get('parameters', {}),
                outcome=data.get('outcome', {}),
                success_metrics=data.get('success_metrics', {}),
                confidence_score=data.get('confidence_score', 0.0),
                metadata=data.get('metadata', {})
            )
        except Exception as e:
            logging.getLogger("MetaLearningSystem").warning(
                f"Experiencia corrupta ignorada: {e}")
            return None

    @staticmethod
    def _meta_rule_to_dict(meta_rule: MetaRule) -> Dict[str, Any]:
        return {
            'meta_rule_id': meta_rule.meta_rule_id,
            'name': meta_rule.name,
            'target_rule_id': meta_rule.target_rule_id,
            'condition_metric': meta_rule.condition_metric,
            'operator': meta_rule.operator,
            'threshold': meta_rule.threshold,
            'action': meta_rule.action,
            'action_value': meta_rule.action_value,
            'min_execution_count': meta_rule.min_execution_count,
            'enabled': meta_rule.enabled
        }

    @staticmethod
    def _meta_rule_from_dict(data: Any) -> Optional[MetaRule]:
        if not isinstance(data, dict):
            return None
        try:
            meta_rule = MetaRule(
                meta_rule_id=data['meta_rule_id'],
                name=data.get('name', ''),
                target_rule_id=data['target_rule_id'],
                condition_metric=data['condition_metric'],
                operator=data['operator'],
                threshold=data['threshold'],
                action=data['action'],
                action_value=data.get('action_value'),
                min_execution_count=int(data.get('min_execution_count', 0)),
                enabled=bool(data.get('enabled', True))
            )
        except Exception as e:
            logging.getLogger("MetaLearningSystem").warning(
                f"Meta-regla corrupta ignorada: {e}")
            return None
        return meta_rule if meta_rule.is_valid() else None

    @staticmethod
    def _meta_rule_application_to_dict(application: MetaRuleApplication) -> Dict[str, Any]:
        return {
            'meta_rule_id': application.meta_rule_id,
            'target_rule_id': application.target_rule_id,
            'action': application.action,
            'status': application.status.value,
            'previous_state': application.previous_state,
            'new_state': application.new_state,
            'message': application.message,
            'timestamp': application.timestamp.isoformat(),
            'reverted': application.reverted
        }

    @staticmethod
    def _restore_rule_state_dates(state: Any) -> Dict[str, Any]:
        """
        Devuelve el estado de una regla con last_execution novamente como datetime.
        Sin esto la reversión tras recuperar escribiría una cadena en la regla real.
        """
        if not isinstance(state, dict):
            return {}
        restored = dict(state)
        raw_execution = restored.get("last_execution")
        if isinstance(raw_execution, str) and raw_execution:
            try:
                restored["last_execution"] = datetime.fromisoformat(raw_execution)
            except ValueError:
                restored["last_execution"] = None
        return restored

    @staticmethod
    def _meta_rule_application_from_dict(data: Any) -> Optional[MetaRuleApplication]:
        if not isinstance(data, dict):
            return None
        try:
            return MetaRuleApplication(
                meta_rule_id=data['meta_rule_id'],
                target_rule_id=data['target_rule_id'],
                action=data['action'],
                status=MetaRuleStatus(data['status']),
                previous_state=MetaLearningSystem._restore_rule_state_dates(
                    data.get('previous_state', {})),
                new_state=MetaLearningSystem._restore_rule_state_dates(
                    data.get('new_state', {})),
                message=data.get('message', ''),
                timestamp=datetime.fromisoformat(data['timestamp']),
                reverted=bool(data.get('reverted', False))
            )
        except Exception as e:
            logging.getLogger("MetaLearningSystem").warning(
                f"Aplicación de meta-regla corrupta ignorada: {e}")
            return None

    def get_meta_learning_state(self) -> Dict[str, Any]:
        """Estado serializable del metaprendizaje (experiencias, meta-reglas e historial)"""
        return {
            'version': self.STATE_VERSION,
            'experiences': [self._experience_to_dict(exp) for exp in self.experiences],
            'meta_rules': [self._meta_rule_to_dict(rule) for rule in self.meta_rule_definitions],
            'meta_rule_history': [self._meta_rule_application_to_dict(app)
                                  for app in self.meta_rule_history],
            'metrics': self.get_meta_learning_metrics()
        }

    def save_meta_learning_state(self, file_path: str = None) -> bool:
        """
        Guarda el estado de metaprendizaje en un archivo estable.
        No sustituye a save_meta_learning_data (export histórico con timestamp),
        solo añade un punto de recuperación determinista.
        """
        target_path = file_path or self.config.get("persistence_path", "data/meta_learning_state.json")
        try:
            directory = os.path.dirname(target_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_meta_learning_state(), f, indent=2, default=str)
            self.logger.info(f"Estado de metaprendizaje guardado en {target_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error al guardar estado de metaprendizaje: {e}")
            return False

    def load_meta_learning_state(self, file_path: str) -> bool:
        """
        Recupera el estado de metaprendizaje.

        No destructivo: fusiona con el estado actual evitando duplicados por
        identificador. Los registros corruptos se ignoran sin abortar la carga.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"No existe estado de metaprendizaje: {file_path}")
            return False
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.logger.error(f"Estado de metaprendizaje corrupto en {file_path}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error al leer estado de metaprendizaje: {e}")
            return False

        if not isinstance(data, dict):
            self.logger.error("Estado de metaprendizaje inválido: se esperaba un objeto JSON")
            return False

        existing_experiences = {exp.experience_id for exp in self.experiences}
        for exp_data in data.get('experiences', []) or []:
            experience = self._experience_from_dict(exp_data)
            if experience is None:
                continue
            if experience.experience_id in existing_experiences:
                continue
            existing_experiences.add(experience.experience_id)
            self.experiences.append(experience)

        existing_rules = {rule.meta_rule_id for rule in self.meta_rule_definitions}
        for rule_data in data.get('meta_rules', []) or []:
            meta_rule = self._meta_rule_from_dict(rule_data)
            if meta_rule is None:
                continue
            if meta_rule.meta_rule_id in existing_rules:
                continue
            existing_rules.add(meta_rule.meta_rule_id)
            self.meta_rule_definitions.append(meta_rule)

        existing_history = {
            (app.meta_rule_id, app.target_rule_id, app.action,
             app.status.value, app.timestamp.isoformat())
            for app in self.meta_rule_history
        }
        for app_data in data.get('meta_rule_history', []) or []:
            application = self._meta_rule_application_from_dict(app_data)
            if application is None:
                continue
            key = (application.meta_rule_id, application.target_rule_id, application.action,
                   application.status.value, application.timestamp.isoformat())
            if key in existing_history:
                continue
            existing_history.add(key)
            self.meta_rule_history.append(application)

        self.total_experiences = len(self.experiences)
        self.logger.info(f"Estado de metaprendizaje cargado desde {file_path}")
        return True

    # ------------------------------------------------------------------
    # 2.8.3.6 — INTEGRACIÓN
    # El metaprendizaje observa motores de aprendizaje que ya existen.
    # Conectar una instancia real la comparte: no se crea un segundo motor
    # ni se duplica lógica de aprendizaje.
    # ------------------------------------------------------------------

    #: Atributo real donde se guarda cada componente conectado.
    INTEGRATION_ATTRIBUTES: Dict[str, str] = {
        'adaptive_learning': 'adaptive_engine',
        'self_improvement': 'self_improvement',
        'contextual_adaptation': 'contextual_adaptation_engine'
    }

    #: Capacidades reales que un componente debe exponer para ser integrado.
    INTEGRATION_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
        'adaptive_learning': ('get_learning_engine_status',),
        'self_improvement': ('get_learning_status',),
        'contextual_adaptation': ('integrate_with_meta_learning_system',)
    }

    def connect_component(self, component: str, engine: Any) -> Dict[str, Any]:
        """
        Conecta una instancia real de un motor de aprendizaje existente.

        No crea motores: valida la API real del componente y, si es válida,
        comparte esa misma instancia.
        """
        result = {
            'success': False,
            'component': component,
            'attribute': None,
            'already_connected': False,
            'shared': False,
            'missing_capabilities': [],
            'reason': None
        }

        if component not in self.INTEGRATION_REQUIREMENTS:
            result['reason'] = f"Componente no soportado: {component}"
            return result

        if engine is None:
            result['reason'] = "Instancia no proporcionada"
            return result

        missing = [name for name in self.INTEGRATION_REQUIREMENTS[component]
                   if not hasattr(engine, name)]
        if missing:
            result['missing_capabilities'] = missing
            result['reason'] = f"API real no disponible: {', '.join(missing)}"
            self.logger.warning(
                f"Integración de {component} rechazada: {result['reason']}")
            return result

        attribute = self.INTEGRATION_ATTRIBUTES[component]
        already_connected = getattr(self, attribute, None) is engine
        setattr(self, attribute, engine)
        self.integrated_components[component] = engine
        result.update({
            'success': True,
            'attribute': attribute,
            'already_connected': already_connected,
            'shared': True
        })
        self.logger.info(
            f"{component} conectado ({type(engine).__name__})"
            + (" ya estaba conectado" if already_connected else ""))
        return result

    def connect_adaptive_learning_engine(self, engine: Any) -> Dict[str, Any]:
        """Integra con AdaptiveLearningEngine (2.8.3.6.1)"""
        return self.connect_component('adaptive_learning', engine)

    def connect_self_improvement_system(self, system: Any) -> Dict[str, Any]:
        """Integra con SelfImprovementSystem (2.8.3.6.2)"""
        return self.connect_component('self_improvement', system)

    def connect_contextual_adaptation_engine(self, engine: Any) -> Dict[str, Any]:
        """
        Integra con ContextualAdaptationEngine (2.8.3.6.3).

        La conexión es bidireccional, como con ArchitecturalEvolutionManager:
        el motor de adaptación queda informado de este sistema.
        """
        result = self.connect_component('contextual_adaptation', engine)
        if result['success'] and hasattr(engine, 'set_meta_learning_system'):
            engine.set_meta_learning_system(self)
        return result

    def get_integration_status(self) -> Dict[str, Any]:
        """
        Estado de integración y comprobación de motores duplicados (2.8.3.6.4).
        """
        observed = dict(self.INTEGRATION_ATTRIBUTES)
        observed['performance_optimizer'] = 'performance_optimizer'

        components: Dict[str, Dict[str, Any]] = {}
        for name, attribute in observed.items():
            engine = getattr(self, attribute, None)
            components[name] = {
                'attribute': attribute,
                'connected': engine is not None,
                'shared': engine is not None and self.integrated_components.get(name) is engine,
                'type': type(engine).__name__ if engine is not None else None,
                'object_id': id(engine) if engine is not None else None
            }

        identities = [info['object_id'] for info in components.values() if info['connected']]
        duplicates = sorted(
            name for name, info in components.items()
            if info['connected'] and identities.count(info['object_id']) > 1
        )

        return {
            'components': components,
            'connected_components': sorted(name for name, info in components.items()
                                           if info['connected']),
            'shared_components': sorted(name for name, info in components.items()
                                        if info['shared']),
            'duplicate_components': duplicates,
            'no_duplicate_engines': not duplicates,
            'meta_learning_metrics': self.get_meta_learning_metrics()
        }