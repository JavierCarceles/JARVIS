"""
Self Improvement System v2.7.0
Sistema de automejora con aprendizaje continuo y optimización adaptativa
"""

import asyncio
import json
import logging
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
import importlib
import inspect

from .advanced_logger import AdvancedLogger
from .performance_optimizer import PerformanceOptimizer, OptimizationAction, OptimizationStrategy
from .pattern_analyzer import PatternAnalyzer, PatternDetector
from .log_analytics import LogAnalyticsEngine, LogAnalytics
from .log_predictor import LogPredictor, PredictionType

class LearningMode(Enum):
    """Modos de aprendizaje del sistema"""
    PASSIVE_LEARNING = "passive_learning"
    ACTIVE_LEARNING = "active_learning"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    TRANSFER_LEARNING = "transfer_learning"
    FEDERATED_LEARNING = "federated_learning"

class ImprovementType(Enum):
    """Tipos de mejora"""
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    ERROR_REDUCTION = "error_reduction"
    EFFICIENCY_GAIN = "efficiency_gain"
    RESOURCE_OPTIMIZATION = "resource_optimization"
    USER_EXPERIENCE = "user_experience"
    FEATURE_ENHANCEMENT = "feature_enhancement"
    ALGORITHM_OPTIMIZATION = "algorithm_optimization"
    ARCHITECTURE_IMPROVEMENT = "architecture_improvement"

@dataclass
class LearningSession:
    """Sesión de aprendizaje"""
    session_id: str
    mode: LearningMode
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    data_points: int = 0
    improvements_made: int = 0
    success_rate: float = 0.0
    confidence_score: float = 0.0
    learning_rate: float = 0.01
    exploration_rate: float = 0.1
    performance_metrics: Dict[str, float] = field(default_factory=dict)

@dataclass
class ImprovementRule:
    """Regla de mejora"""
    rule_id: str
    name: str
    description: str
    condition: str
    action: str
    priority: int
    enabled: bool = True
    success_rate: float = 0.0
    execution_count: int = 0
    last_execution: Optional[datetime] = None
    improvement_score: float = 0.0

@dataclass
class KnowledgeGraph:
    """Grafo de conocimiento"""
    node_id: str
    node_type: str
    properties: Dict[str, Any]
    connections: List[str] = field(default_factory=list)
    confidence: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)

class SelfImprovementSystem:
    """
    Sistema de automejora con aprendizaje continuo y optimización adaptativa
    """
    
    def __init__(self, config_path: str = None):
        self.logger = AdvancedLogger("SelfImprovementSystem")
        self.performance_optimizer = PerformanceOptimizer()
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        self.log_predictor = LogPredictor()
        
        # Configuración
        self.config = self._load_config(config_path)
        self.learning_sessions = []
        self.improvement_rules = []
        self.knowledge_graph = {}
        self.learning_queue = queue.Queue()
        self.improvement_queue = queue.Queue()
        
        # Modelos de aprendizaje
        self.learning_models = {}
        self.scalers = {}
        # Buffer de muestras para reentrenamiento incremental.
        # Un clasificador no puede entrenarse con una sola muestra, por lo que
        # se acumulan muestras y solo se reentrena cuando hay suficientes
        # ejemplos y al menos 2 clases distintas.
        self.learning_samples: Dict[str, Dict[str, list]] = {}
        self.min_training_samples = 10
        self.feature_extractors = {}
        
        # Estado del sistema
        self.is_learning = False
        self.current_session = None
        self.performance_baseline = None
        self.improvement_history = []
        self.learning_history = []
        
        # Inicialización
        self._initialize_learning_models()
        self._initialize_improvement_rules()
        self._start_learning_loop()
        
        self.logger.log("SelfImprovementSystem inicializado", level="INFO")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Cargar configuración del sistema de automejora"""
        default_config = {
            'learning_enabled': True,
            'auto_learning': True,
            'learning_interval': 300,  # 5 minutos
            'max_concurrent_learning': 2,
            'learning_modes': {
                'passive_learning': {'enabled': True, 'priority': 1},
                'active_learning': {'enabled': True, 'priority': 2},
                'reinforcement_learning': {'enabled': True, 'priority': 3},
                'transfer_learning': {'enabled': True, 'priority': 4},
                'federated_learning': {'enabled': False, 'priority': 5}
            },
            'improvement_thresholds': {
                'performance_gain': 0.1,  # 10% de mejora
                'error_reduction': 0.2,   # 20% de reducción de errores
                'efficiency_gain': 0.15,  # 15% de ganancia de eficiencia
                'resource_optimization': 0.1  # 10% de optimización de recursos
            },
            'ml_model_path': 'models/learning_models',
            'knowledge_graph_path': 'data/knowledge_graph.json',
            'learning_history_file': 'data/learning_history.json',
            'rule_engine_path': 'data/improvement_rules.json',
            'exploration_rate': 0.1,
            'learning_rate': 0.01,
            'max_learning_sessions': 100,
            'confidence_threshold': 0.8
        }
        
        try:
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
        except Exception as e:
            self.logger.log(f"Error cargando configuración: {e}", level="ERROR")
        
        return default_config
    
    def _initialize_learning_models(self):
        """Inicializar modelos de aprendizaje"""
        try:
            # Crear directorio para modelos si no existe
            os.makedirs(self.config['ml_model_path'], exist_ok=True)
            
            # Inicializar modelos para diferentes tipos de aprendizaje
            self.learning_models['performance'] = RandomForestClassifier(n_estimators=100, random_state=42)
            self.learning_models['error'] = GradientBoostingClassifier(n_estimators=100, random_state=42)
            self.learning_models['efficiency'] = RandomForestClassifier(n_estimators=100, random_state=42)
            self.learning_models['resource'] = GradientBoostingClassifier(n_estimators=100, random_state=42)
            
            # Inicializar escaladores
            for model_name in self.learning_models.keys():
                self.scalers[model_name] = StandardScaler()
            
            # Cargar modelos pre-entrenados si existen
            self._load_trained_learning_models()
            
            self.logger.log("Modelos de aprendizaje inicializados", level="INFO")
        except Exception as e:
            self.logger.log(f"Error inicializando modelos de aprendizaje: {e}", level="ERROR")
    
    def _load_trained_learning_models(self):
        """Cargar modelos pre-entrenados"""
        try:
            for model_name, model in self.learning_models.items():
                model_path = os.path.join(self.config['ml_model_path'], f'{model_name}_model.pkl')
                scaler_path = os.path.join(self.config['ml_model_path'], f'{model_name}_scaler.pkl')
                
                if os.path.exists(model_path):
                    self.learning_models[model_name] = joblib.load(model_path)
                    self.logger.log(f"Modelo de aprendizaje {model_name} cargado desde {model_path}", level="INFO")
                
                if os.path.exists(scaler_path):
                    self.scalers[model_name] = joblib.load(scaler_path)
                    self.logger.log(f"Escalador de aprendizaje {model_name} cargado desde {scaler_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error cargando modelos pre-entrenados: {e}", level="WARNING")
    
    def _save_trained_learning_models(self):
        """Guardar modelos entrenados"""
        try:
            for model_name, model in self.learning_models.items():
                model_path = os.path.join(self.config['ml_model_path'], f'{model_name}_model.pkl')
                scaler_path = os.path.join(self.config['ml_model_path'], f'{model_name}_scaler.pkl')
                
                joblib.dump(model, model_path)
                joblib.dump(self.scalers[model_name], scaler_path)
                
                self.logger.log(f"Modelo de aprendizaje {model_name} guardado en {model_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error guardando modelos de aprendizaje: {e}", level="ERROR")
    
    def _initialize_improvement_rules(self):
        """Inicializar reglas de mejora"""
        try:
            # Reglas predeterminadas
            default_rules = [
                ImprovementRule(
                    rule_id="perf_high_cpu",
                    name="Optimización de CPU alta",
                    description="Detecta uso alto de CPU y aplica optimización",
                    condition="cpu_usage > 80",
                    action="performance_optimizer.optimize_system(OptimizationStrategy.CPU_OPTIMIZATION)",
                    priority=1,
                    enabled=True
                ),
                ImprovementRule(
                    rule_id="mem_high_usage",
                    name="Optimización de memoria alta",
                    description="Detecta uso alto de memoria y aplica optimización",
                    condition="memory_usage > 85",
                    action="performance_optimizer.optimize_system(OptimizationStrategy.MEMORY_OPTIMIZATION)",
                    priority=2,
                    enabled=True
                ),
                ImprovementRule(
                    rule_id="error_rate_high",
                    name="Reducción de tasa de errores",
                    description="Detecta tasa de errores alta y aplica corrección",
                    condition="error_rate > 0.05",
                    action="performance_optimizer.optimize_system(OptimizationStrategy.PROCESS_OPTIMIZATION)",
                    priority=3,
                    enabled=True
                ),
                ImprovementRule(
                    rule_id="response_time_high",
                    name="Optimización de tiempo de respuesta",
                    description="Detecta tiempo de respuesta elevado y aplica optimización",
                    condition="response_time > 1000",
                    action="performance_optimizer.optimize_system(OptimizationStrategy.ALGORITHM_OPTIMIZATION)",
                    priority=4,
                    enabled=True
                ),
                ImprovementRule(
                    rule_id="efficiency_low",
                    name="Mejora de eficiencia general",
                    description="Detecta baja eficiencia y aplica optimización general",
                    condition="efficiency_score < 70",
                    action="performance_optimizer.optimize_system(OptimizationStrategy.RESOURCE_ALLOCATION)",
                    priority=5,
                    enabled=True
                )
            ]
            
            self.improvement_rules.extend(default_rules)
            
            # Cargar reglas personalizadas si existen
            self._load_custom_rules()
            
            self.logger.log(f"Reglas de mejora inicializadas: {len(self.improvement_rules)} reglas", level="INFO")
        except Exception as e:
            self.logger.log(f"Error inicializando reglas de mejora: {e}", level="ERROR")
    
    def _load_custom_rules(self):
        """Cargar reglas personalizadas"""
        try:
            rules_path = self.config['rule_engine_path']
            if os.path.exists(rules_path):
                with open(rules_path, 'r') as f:
                    custom_rules = json.load(f)
                    
                    for rule_data in custom_rules:
                        rule = ImprovementRule(
                            rule_id=rule_data['rule_id'],
                            name=rule_data['name'],
                            description=rule_data['description'],
                            condition=rule_data['condition'],
                            action=rule_data['action'],
                            priority=rule_data['priority'],
                            enabled=rule_data.get('enabled', True),
                            success_rate=rule_data.get('success_rate', 0.0),
                            execution_count=rule_data.get('execution_count', 0),
                            last_execution=datetime.fromisoformat(rule_data['last_execution']) if rule_data.get('last_execution') else None,
                            improvement_score=rule_data.get('improvement_score', 0.0)
                        )
                        self.improvement_rules.append(rule)
                
                self.logger.log(f"Reglas personalizadas cargadas desde {rules_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error cargando reglas personalizadas: {e}", level="WARNING")
    
    def _save_custom_rules(self):
        """Guardar reglas personalizadas"""
        try:
            rules_path = self.config['rule_engine_path']
            custom_rules = []
            
            for rule in self.improvement_rules:
                custom_rules.append({
                    'rule_id': rule.rule_id,
                    'name': rule.name,
                    'description': rule.description,
                    'condition': rule.condition,
                    'action': rule.action,
                    'priority': rule.priority,
                    'enabled': rule.enabled,
                    'success_rate': rule.success_rate,
                    'execution_count': rule.execution_count,
                    'last_execution': rule.last_execution.isoformat() if rule.last_execution else None,
                    'improvement_score': rule.improvement_score
                })
            
            with open(rules_path, 'w') as f:
                json.dump(custom_rules, f, indent=2)
            
            self.logger.log(f"Reglas personalizadas guardadas en {rules_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error guardando reglas personalizadas: {e}", level="ERROR")
    
    def _start_learning_loop(self):
        """Iniciar bucle de aprendizaje"""
        self.is_learning = True
        self.learning_thread = threading.Thread(target=self._learning_loop)
        self.learning_thread.daemon = True
        self.learning_thread.start()
        
        self.logger.log("Bucle de aprendizaje iniciado", level="INFO")
    
    def _learning_loop(self):
        """Bucle principal de aprendizaje"""
        while self.is_learning:
            try:
                if self.config['learning_enabled'] and self.config['auto_learning']:
                    self._perform_passive_learning()
                    self._execute_improvement_rules()
                    self._analyze_learning_patterns()
                    self._update_knowledge_graph()
                
                time.sleep(self.config['learning_interval'])
            except Exception as e:
                self.logger.log(f"Error en bucle de aprendizaje: {e}", level="ERROR")
                time.sleep(5)
    
    def _perform_passive_learning(self):
        """Realizar aprendizaje pasivo"""
        try:
            # Iniciar sesión de aprendizaje pasivo
            session = self._start_learning_session(LearningMode.PASSIVE_LEARNING)
            
            # Recopilar datos del sistema
            system_data = self._collect_system_data()
            
            # Extraer características
            features = self._extract_learning_features(system_data)
            
            # Actualizar modelos de aprendizaje
            self._update_learning_models(features, system_data)
            
            # Evaluar mejoras potenciales
            improvements = self._identify_improvement_opportunities(system_data)
            
            # Agregar a cola de mejoras
            for improvement in improvements:
                self.improvement_queue.put(improvement)
            
            # Finalizar sesión
            self._end_learning_session(session)
            
        except Exception as e:
            self.logger.log(f"Error en aprendizaje pasivo: {e}", level="ERROR")
    
    def _collect_system_data(self) -> Dict[str, Any]:
        """Recopilar datos del sistema para aprendizaje"""
        try:
            # Obtener métricas del optimizador de rendimiento
            performance_data = self.performance_optimizer.get_optimization_status()
            
            # Obtener métricas del analizador de patrones
            pattern_data = self.pattern_analyzer.get_pattern_analysis()
            
            # Obtener métricas del analítico de logs
            analytics_data = self.analytics.get_analytics_summary()
            
            # Obtener predicciones del predictor de logs
            # OJO: get_predictions() devuelve una LISTA de Prediction, no un dict.
            prediction_data = self.log_predictor.get_predictions()
            
            # Combinar todos los datos (normalizados a dicts planos)
            system_data = {
                'timestamp': datetime.now().isoformat(),
                'performance': self._flatten_performance(performance_data),
                'patterns': self._flatten_patterns(pattern_data),
                'analytics': self._flatten_analytics(analytics_data),
                'predictions': self._summarize_predictions(prediction_data),
                'efficiency_score': performance_data.get('efficiency_score', 0),
                'optimization_gain': performance_data.get('optimization_gain', 0),
                'system_load': self._calculate_system_load()
            }
            
            return system_data
            
        except Exception as e:
            self.logger.log(f"Error recopilando datos del sistema: {e}", level="ERROR")
            return {}
    
    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        """Convertir cualquier valor a dict de forma segura."""
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {'items': value}
        return {}
    
    def _flatten_performance(self, status: Any) -> Dict[str, Any]:
        """Aplanar el estado del optimizador a métricas planas."""
        status = self._as_dict(status)
        metrics = self._as_dict(status.get('current_metrics', {}))
        
        flat = {
            'cpu_usage': metrics.get('cpu_usage', 0),
            'memory_usage': metrics.get('memory_usage', 0),
            'disk_usage': metrics.get('disk_usage', 0),
            'network_usage': metrics.get('network_usage', 0),
            'response_time': metrics.get('response_time', 0),
            'throughput': metrics.get('throughput', 0),
            'error_rate': metrics.get('error_rate', 0),
            'efficiency_score': status.get('efficiency_score', metrics.get('efficiency_score', 0)),
            'optimization_gain': status.get('optimization_gain', metrics.get('optimization_gain', 0)),
            'active_actions': status.get('active_actions', 0),
            'queued_actions': status.get('queued_actions', 0)
        }
        return flat
    
    def _flatten_patterns(self, analysis: Any) -> Dict[str, Any]:
        """Aplanar el análisis de patrones a métricas planas."""
        analysis = self._as_dict(analysis)
        stats = self._as_dict(analysis.get('statistics', {}))
        
        return {
            'anomaly_count': analysis.get('active_count', stats.get('active_patterns', 0)),
            'total_patterns': analysis.get('total_patterns', stats.get('total_patterns', 0)),
            'recent_patterns': analysis.get('recent_count', stats.get('recent_patterns', 0)),
            'trend_strength': stats.get('trend_strength', 0),
            'seasonality_score': stats.get('seasonality_score', 0),
            'correlation_strength': stats.get('correlation_strength', 0)
        }
    
    def _flatten_analytics(self, summary: Any) -> Dict[str, Any]:
        """Aplanar el resumen analítico a contadores planos."""
        summary = self._as_dict(summary)
        data = self._as_dict(summary.get('data', {}))
        
        total_logs = data.get('total_logs', 0)
        error_count = data.get('error_count', 0)
        warning_count = data.get('warning_count', 0)
        
        return {
            'total_logs': total_logs,
            'error_count': error_count,
            'warning_count': warning_count,
            'info_count': max(total_logs - error_count - warning_count, 0),
            'logs_per_second': data.get('logs_per_second', 0),
            'duration_seconds': data.get('duration_seconds', 0)
        }
    
    def _summarize_predictions(self, predictions: Any) -> Dict[str, float]:
        """Convertir una lista de Prediction en métricas agregadas."""
        summary = {
            'error_probability': 0.0,
            'performance_risk': 0.0,
            'resource_demand': 0.0,
            'prediction_count': 0
        }
        
        if not predictions:
            return summary
        
        if isinstance(predictions, dict):
            # Por si el proveedor devuelve dict en el futuro
            return {
                'error_probability': predictions.get('error_probability', 0.0),
                'performance_risk': predictions.get('performance_risk', 0.0),
                'resource_demand': predictions.get('resource_demand', 0.0),
                'prediction_count': len(predictions)
            }
        
        buckets: Dict[str, list] = {
            'error_probability': [],
            'performance_risk': [],
            'resource_demand': []
        }
        
        for prediction in predictions:
            p_type = getattr(prediction, 'type', None)
            p_value = getattr(prediction, 'predicted_value', None)
            if p_type is None or p_value is None:
                continue
            
            try:
                value = float(p_value)
            except (TypeError, ValueError):
                continue
            
            type_value = getattr(p_type, 'value', p_type)
            
            if type_value in (PredictionType.ERROR_RATE.value, PredictionType.FAILURE_PROBABILITY.value):
                buckets['error_probability'].append(value)
            elif type_value in (PredictionType.RESPONSE_TIME.value, PredictionType.SYSTEM_HEALTH.value):
                buckets['performance_risk'].append(value)
            elif type_value in (PredictionType.RESOURCE_USAGE.value, PredictionType.THROUGHPUT.value):
                buckets['resource_demand'].append(value)
        
        for key, values in buckets.items():
            if values:
                summary[key] = round(sum(values) / len(values), 4)
        
        summary['prediction_count'] = len(predictions)
        return summary
    
    def _calculate_system_load(self) -> float:
        """Calcular carga del sistema"""
        try:
            # Obtener métricas actuales
            metrics = self.performance_optimizer.current_metrics
            
            # Calcular carga normalizada (0-1)
            cpu_load = metrics.cpu_usage / 100
            memory_load = metrics.memory_usage / 100
            disk_load = metrics.disk_usage / 100
            network_load = metrics.network_usage / 100
            
            # Ponderar carga
            total_load = (
                cpu_load * 0.3 +
                memory_load * 0.3 +
                disk_load * 0.2 +
                network_load * 0.2
            )
            
            return round(total_load, 2)
        except Exception as e:
            self.logger.log(f"Error calculando carga del sistema: {e}", level="ERROR")
            return 0.0
    
    def _extract_learning_features(self, system_data: Dict[str, Any]) -> List[float]:
        """Extraer características para aprendizaje"""
        try:
            features = []
            
            system_data = self._as_dict(system_data)
            
            # Métricas de rendimiento
            performance_metrics = self._as_dict(system_data.get('performance', {}))
            features.extend([
                system_data.get('efficiency_score', 0),
                system_data.get('optimization_gain', 0),
                system_data.get('system_load', 0),
                performance_metrics.get('cpu_usage', 0) / 100,
                performance_metrics.get('memory_usage', 0) / 100,
                performance_metrics.get('response_time', 0) / 1000,
                performance_metrics.get('error_rate', 0)
            ])
            
            # Métricas de patrones
            pattern_metrics = self._as_dict(system_data.get('patterns', {}))
            features.extend([
                pattern_metrics.get('anomaly_count', 0),
                pattern_metrics.get('trend_strength', 0),
                pattern_metrics.get('seasonality_score', 0),
                pattern_metrics.get('correlation_strength', 0)
            ])
            
            # Métricas de analítico
            analytics_metrics = self._as_dict(system_data.get('analytics', {}))
            features.extend([
                analytics_metrics.get('total_logs', 0),
                analytics_metrics.get('error_count', 0),
                analytics_metrics.get('warning_count', 0),
                analytics_metrics.get('info_count', 0)
            ])
            
            # Métricas de predicción
            prediction_metrics = self._as_dict(system_data.get('predictions', {}))
            features.extend([
                prediction_metrics.get('error_probability', 0),
                prediction_metrics.get('performance_risk', 0),
                prediction_metrics.get('resource_demand', 0)
            ])
            
            # Características temporales
            current_time = datetime.now()
            features.extend([
                current_time.hour / 24,  # Hora normalizada
                current_time.weekday() / 7,  # Día de la semana normalizado
                np.sin(2 * np.pi * current_time.hour / 24),  # Componente sinusoidal
                np.cos(2 * np.pi * current_time.hour / 24)   # Componente coseno
            ])
            
            return features
        except Exception as e:
            self.logger.log(f"Error extrayendo características: {e}", level="ERROR")
            return []
    
    def _update_learning_models(self, features: List[float], system_data: Dict[str, Any]):
        """Actualizar modelos de aprendizaje"""
        try:
            if not features:
                return
            
            # Determinar etiquetas basadas en métricas
            labels = self._determine_learning_labels(system_data)
            
            retrained = False
            
            # Actualizar cada modelo
            for model_name, label in labels.items():
                if model_name not in self.learning_models:
                    continue
                
                try:
                    # Acumular la muestra en el buffer del modelo
                    buffer = self.learning_samples.setdefault(model_name, {'X': [], 'y': []})
                    buffer['X'].append(list(features))
                    buffer['y'].append(int(label))
                    
                    # Acotar el buffer para que no crezca sin límite
                    max_samples = max(self.min_training_samples * 10, 500)
                    if len(buffer['y']) > max_samples:
                        buffer['X'] = buffer['X'][-max_samples:]
                        buffer['y'] = buffer['y'][-max_samples:]
                    
                    # Un clasificador necesita varias muestras y >= 2 clases.
                    X_all = np.array(buffer['X'], dtype=float)
                    y_all = np.array(buffer['y'], dtype=int)
                    
                    if len(y_all) < self.min_training_samples:
                        continue
                    
                    if len(np.unique(y_all)) < 2:
                        # Todas las muestras son de la misma clase: aún no se puede entrenar.
                        continue
                    
                    # Escalar características con todas las muestras acumuladas
                    scaler = self.scalers[model_name]
                    try:
                        X_scaled = scaler.fit_transform(X_all)
                    except Exception:
                        # Si el escalado falla, entrenar sin escalar
                        X_scaled = X_all
                    
                    # Re-entrenar modelo
                    self.learning_models[model_name].fit(X_scaled, y_all)
                    retrained = True
                    
                except Exception as model_error:
                    self.logger.log(
                        f"Error actualizando modelo de aprendizaje {model_name}: {model_error}",
                        level="WARNING"
                    )
            
            # Guardar modelos actualizados (solo si hubo re-entrenamiento real)
            if retrained:
                self._save_trained_learning_models()
            
        except Exception as e:
            self.logger.log(f"Error actualizando modelos de aprendizaje: {e}", level="ERROR")
    
    def _determine_learning_labels(self, system_data: Dict[str, Any]) -> Dict[str, int]:
        """Determinar etiquetas para aprendizaje"""
        try:
            labels = {}
            
            # Etiqueta de rendimiento
            efficiency = system_data.get('efficiency_score', 0)
            labels['performance'] = 1 if efficiency > 80 else 0
            
            # Etiqueta de errores
            error_rate = self._as_dict(system_data.get('performance', {})).get('error_rate', 0)
            labels['error'] = 1 if error_rate > 0.05 else 0
            
            # Etiqueta de eficiencia
            optimization_gain = system_data.get('optimization_gain', 0)
            labels['efficiency'] = 1 if optimization_gain > 0.1 else 0
            
            # Etiqueta de recursos
            system_load = system_data.get('system_load', 0)
            labels['resource'] = 1 if system_load > 0.8 else 0
            
            return labels
        except Exception as e:
            self.logger.log(f"Error determinando etiquetas: {e}", level="ERROR")
            return {}
    
    def _identify_improvement_opportunities(self, system_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identificar oportunidades de mejora"""
        try:
            opportunities = []
            
            # Analizar métricas actuales
            efficiency = system_data.get('efficiency_score', 0)
            error_rate = self._as_dict(system_data.get('performance', {})).get('error_rate', 0)
            system_load = system_data.get('system_load', 0)
            
            # Verificar umbrales de mejora
            if efficiency < self.config['improvement_thresholds']['performance_gain'] * 100:
                opportunities.append({
                    'type': ImprovementType.PERFORMANCE_IMPROVEMENT,
                    'priority': 'high',
                    'description': 'Baja eficiencia detectada, aplicando optimización',
                    'action': 'performance_optimizer.optimize_system(OptimizationStrategy.RESOURCE_ALLOCATION)',
                    'confidence': 0.8,
                    'expected_improvement': 15.0
                })
            
            if error_rate > self.config['improvement_thresholds']['error_reduction']:
                opportunities.append({
                    'type': ImprovementType.ERROR_REDUCTION,
                    'priority': 'critical',
                    'description': 'Tasa de errores alta, aplicando corrección',
                    'action': 'performance_optimizer.optimize_system(OptimizationStrategy.PROCESS_OPTIMIZATION)',
                    'confidence': 0.9,
                    'expected_improvement': 25.0
                })
            
            if system_load > 0.8:
                opportunities.append({
                    'type': ImprovementType.RESOURCE_OPTIMIZATION,
                    'priority': 'medium',
                    'description': 'Carga del sistema alta, aplicando optimización de recursos',
                    'action': 'performance_optimizer.optimize_system(OptimizationStrategy.CPU_OPTIMIZATION)',
                    'confidence': 0.7,
                    'expected_improvement': 10.0
                })
            
            return opportunities
        except Exception as e:
            self.logger.log(f"Error identificando oportunidades: {e}", level="ERROR")
            return []
    
    def _execute_improvement_rules(self):
        """Ejecutar reglas de mejora"""
        try:
            for rule in self.improvement_rules:
                if not rule.enabled:
                    continue
                
                # Evaluar condición
                if self._evaluate_rule_condition(rule):
                    # Ejecutar acción
                    self._execute_rule_action(rule)
                    
                    # Actualizar estadísticas de la regla
                    rule.execution_count += 1
                    rule.last_execution = datetime.now()
                    
                    # Guardar reglas actualizadas
                    self._save_custom_rules()
                    
        except Exception as e:
            self.logger.log(f"Error ejecutando reglas de mejora: {e}", level="ERROR")
    
    def _evaluate_rule_condition(self, rule: ImprovementRule) -> bool:
        """Evaluar condición de una regla"""
        try:
            # Obtener contexto actual del sistema
            context = {
                'cpu_usage': self.performance_optimizer.current_metrics.cpu_usage,
                'memory_usage': self.performance_optimizer.current_metrics.memory_usage,
                'disk_usage': self.performance_optimizer.current_metrics.disk_usage,
                'response_time': self.performance_optimizer.current_metrics.response_time,
                'error_rate': self.performance_optimizer.current_metrics.error_rate,
                'efficiency_score': self.performance_optimizer.current_metrics.efficiency_score,
                'system_load': self._calculate_system_load()
            }
            
            # Evaluar condición (simplificado - en un sistema real esto sería más complejo)
            condition_eval = eval(rule.condition, {}, context)
            
            return condition_eval
            
        except Exception as e:
            self.logger.log(f"Error evaluando condición de regla {rule.rule_id}: {e}", level="WARNING")
            return False
    
    def _execute_rule_action(self, rule: ImprovementRule):
        """Ejecutar acción de una regla"""
        try:
            self.logger.log(f"Ejecutando regla: {rule.name}", level="INFO")
            
            # Ejecutar acción (simplificado - en un sistema real esto sería más seguro)
            try:
                # Evaluar acción en un entorno seguro
                action_result = eval(rule.action, {
                    'performance_optimizer': self.performance_optimizer,
                    'OptimizationStrategy': OptimizationStrategy
                }, {})
                
                # Registrar resultado
                rule.success_rate = (rule.success_rate * rule.execution_count + 1) / (rule.execution_count + 1)
                
                self.logger.log(f"Regla ejecutada con éxito: {rule.name}", level="INFO")
                
            except Exception as action_error:
                # Actualizar tasa de fallo
                rule.success_rate = (rule.success_rate * rule.execution_count) / (rule.execution_count + 1)
                
                self.logger.log(f"Error ejecutando regla {rule.name}: {action_error}", level="ERROR")
                
        except Exception as e:
            self.logger.log(f"Error ejecutando acción de regla {rule.rule_id}: {e}", level="ERROR")
    
    def _analyze_learning_patterns(self):
        """Analizar patrones de aprendizaje"""
        try:
            if len(self.learning_sessions) < 10:
                return
            
            # Analizar sesiones recientes
            recent_sessions = self.learning_sessions[-10:]
            
            # Calcular tendencias
            efficiency_trend = []
            success_rate_trend = []
            
            for session in recent_sessions:
                efficiency_trend.append(session.performance_metrics.get('efficiency_score', 0))
                success_rate_trend.append(session.success_rate)
            
            # Detectar patrones
            if len(efficiency_trend) > 1:
                efficiency_slope = np.polyfit(range(len(efficiency_trend)), efficiency_trend, 1)[0]
                success_slope = np.polyfit(range(len(success_rate_trend)), success_rate_trend, 1)[0]
                
                # Ajustar tasa de aprendizaje basado en tendencias
                if efficiency_slope > 0:
                    self.config['learning_rate'] = min(0.1, self.config['learning_rate'] * 1.1)
                else:
                    self.config['learning_rate'] = max(0.001, self.config['learning_rate'] * 0.9)
                
                if success_slope > 0:
                    self.config['exploration_rate'] = min(0.3, self.config['exploration_rate'] * 1.05)
                else:
                    self.config['exploration_rate'] = max(0.01, self.config['exploration_rate'] * 0.95)
            
            self.logger.log(f"Tendencias de aprendizaje: eficiencia {efficiency_slope:.4f}, éxito {success_slope:.4f}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error analizando patrones de aprendizaje: {e}", level="ERROR")
    
    def _update_knowledge_graph(self):
        """Actualizar grafo de conocimiento"""
        try:
            # Crear nuevo nodo de conocimiento
            node_id = f"node_{int(time.time())}"
            node_type = "system_state"
            
            # Propiedades del nodo
            properties = {
                'timestamp': datetime.now().isoformat(),
                'efficiency_score': self.performance_optimizer.current_metrics.efficiency_score,
                'optimization_gain': self.performance_optimizer.current_metrics.optimization_gain,
                'system_load': self._calculate_system_load(),
                'learning_rate': self.config['learning_rate'],
                'exploration_rate': self.config['exploration_rate']
            }
            
            # Crear nodo
            node = KnowledgeGraph(
                node_id=node_id,
                node_type=node_type,
                properties=properties,
                confidence=self._calculate_node_confidence(properties)
            )
            
            # Agregar al grafo
            self.knowledge_graph[node_id] = node
            
            # Conectar con nodos anteriores
            if len(self.knowledge_graph) > 1:
                previous_nodes = list(self.knowledge_graph.keys())[-2:]
                node.connections = previous_nodes
            
            # Limitar tamaño del grafo
            if len(self.knowledge_graph) > 1000:
                oldest_nodes = sorted(self.knowledge_graph.keys())[:100]
                for old_node in oldest_nodes:
                    del self.knowledge_graph[old_node]
            
            # Guardar grafo
            self._save_knowledge_graph()
            
        except Exception as e:
            self.logger.log(f"Error actualizando grafo de conocimiento: {e}", level="ERROR")
    
    def _calculate_node_confidence(self, properties: Dict[str, Any]) -> float:
        """Calcular confianza de un nodo"""
        try:
            # Basado en métricas de sistema
            efficiency = properties.get('efficiency_score', 0)
            system_load = properties.get('system_load', 0)
            
            # Calcular confianza (0-1)
            confidence = (efficiency / 100) * (1 - system_load)
            
            return round(confidence, 2)
        except Exception as e:
            self.logger.log(f"Error calculando confianza de nodo: {e}", level="ERROR")
            return 0.0
    
    def _save_knowledge_graph(self):
        """Guardar grafo de conocimiento"""
        try:
            graph_data = []
            for node_id, node in self.knowledge_graph.items():
                graph_data.append({
                    'node_id': node_id,
                    'node_type': node.node_type,
                    'properties': node.properties,
                    'connections': node.connections,
                    'confidence': node.confidence,
                    'last_updated': node.last_updated.isoformat()
                })
            
            with open(self.config['knowledge_graph_path'], 'w') as f:
                json.dump(graph_data, f, indent=2, default=str)
            
            self.logger.log(f"Grafo de conocimiento guardado en {self.config['knowledge_graph_path']}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error guardando grafo de conocimiento: {e}", level="ERROR")
    
    def _start_learning_session(self, mode: LearningMode) -> LearningSession:
        """Iniciar sesión de aprendizaje"""
        session = LearningSession(
            session_id=f"session_{int(time.time())}",
            mode=mode,
            start_time=datetime.now()
        )
        
        self.learning_sessions.append(session)
        self.current_session = session
        
        # Limitar número de sesiones
        if len(self.learning_sessions) > self.config['max_learning_sessions']:
            self.learning_sessions = self.learning_sessions[-self.config['max_learning_sessions']:]
        
        return session
    
    def _end_learning_session(self, session: LearningSession):
        """Finalizar sesión de aprendizaje"""
        try:
            session.end_time = datetime.now()
            session.duration = (session.end_time - session.start_time).total_seconds()
            
            # Calcular métricas de la sesión
            session.data_points = len(self.knowledge_graph)
            session.improvements_made = len(self.improvement_queue.queue)
            
            # Guardar historial
            self.learning_history.append({
                'session_id': session.session_id,
                'mode': session.mode.value,
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat(),
                'duration': session.duration,
                'data_points': session.data_points,
                'improvements_made': session.improvements_made,
                'success_rate': session.success_rate,
                'confidence_score': session.confidence_score,
                'learning_rate': session.learning_rate,
                'exploration_rate': session.exploration_rate
            })
            
            self.current_session = None
            
        except Exception as e:
            self.logger.log(f"Error finalizando sesión de aprendizaje: {e}", level="ERROR")
    
    def get_learning_status(self) -> Dict[str, Any]:
        """Obtener estado actual de aprendizaje"""
        try:
            return {
                'is_learning': self.is_learning,
                'current_session': self.current_session.__dict__ if self.current_session else None,
                'learning_enabled': self.config['learning_enabled'],
                'auto_learning': self.config['auto_learning'],
                'learning_rate': self.config['learning_rate'],
                'exploration_rate': self.config['exploration_rate'],
                'total_sessions': len(self.learning_sessions),
                'active_rules': len([r for r in self.improvement_rules if r.enabled]),
                'knowledge_nodes': len(self.knowledge_graph),
                'efficiency_score': self.performance_optimizer.current_metrics.efficiency_score,
                'optimization_gain': self.performance_optimizer.current_metrics.optimization_gain
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo estado de aprendizaje: {e}", level="ERROR")
            return {}
    
    def get_learning_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener historial de aprendizaje"""
        try:
            return self.learning_history[-limit:]
        except Exception as e:
            self.logger.log(f"Error obteniendo historial de aprendizaje: {e}", level="ERROR")
            return []
    
    def add_improvement_rule(self, rule: ImprovementRule):
        """Añadir regla de mejora personalizada"""
        try:
            self.improvement_rules.append(rule)
            self._save_custom_rules()
            self.logger.log(f"Regla de mejora añadida: {rule.name}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error añadiendo regla de mejora: {e}", level="ERROR")
    
    def remove_improvement_rule(self, rule_id: str):
        """Eliminar regla de mejora"""
        try:
            self.improvement_rules = [r for r in self.improvement_rules if r.rule_id != rule_id]
            self._save_custom_rules()
            self.logger.log(f"Regla de mejora eliminada: {rule_id}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error eliminando regla de mejora: {e}", level="ERROR")
    
    def enable_learning_mode(self, mode: LearningMode):
        """Habilitar modo de aprendizaje"""
        try:
            self.config['learning_modes'][mode.value]['enabled'] = True
            self.logger.log(f"Modo de aprendizaje habilitado: {mode.value}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error habilitando modo de aprendizaje: {e}", level="ERROR")
    
    def disable_learning_mode(self, mode: LearningMode):
        """Deshabilitar modo de aprendizaje"""
        try:
            self.config['learning_modes'][mode.value]['enabled'] = False
            self.logger.log(f"Modo de aprendizaje deshabilitado: {mode.value}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error deshabilitando modo de aprendizaje: {e}", level="ERROR")
    
    def perform_active_learning(self):
        """Realizar aprendizaje activo"""
        try:
            session = self._start_learning_session(LearningMode.ACTIVE_LEARNING)
            
            # Realizar experimentos controlados
            experiments = self._design_experiments()
            
            for experiment in experiments:
                result = self._run_experiment(experiment)
                self._process_experiment_result(result)
            
            self._end_learning_session(session)
            
            self.logger.log("Aprendizaje activo completado", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error en aprendizaje activo: {e}", level="ERROR")
    
    def _design_experiments(self) -> List[Dict[str, Any]]:
        """Diseñar experimentos para aprendizaje activo"""
        try:
            experiments = []
            
            # Experimento 1: Optimización de CPU
            experiments.append({
                'name': 'CPU Optimization Experiment',
                'action': 'performance_optimizer.optimize_system(OptimizationStrategy.CPU_OPTIMIZATION)',
                'parameters': {'level': OptimizationLevel.MODERATE},
                'expected_improvement': 15.0,
                'duration': 60.0
            })
            
            # Experimento 2: Optimización de memoria
            experiments.append({
                'name': 'Memory Optimization Experiment',
                'action': 'performance_optimizer.optimize_system(OptimizationStrategy.MEMORY_OPTIMIZATION)',
                'parameters': {'level': OptimizationLevel.MODERATE},
                'expected_improvement': 20.0,
                'duration': 45.0
            })
            
            # Experimento 3: Optimización de algoritmos
            experiments.append({
                'name': 'Algorithm Optimization Experiment',
                'action': 'performance_optimizer.optimize_system(OptimizationStrategy.ALGORITHM_OPTIMIZATION)',
                'parameters': {'level': OptimizationLevel.MODERATE},
                'expected_improvement': 25.0,
                'duration': 90.0
            })
            
            return experiments
        except Exception as e:
            self.logger.log(f"Error diseñando experimentos: {e}", level="ERROR")
            return []
    
    def _run_experiment(self, experiment: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar experimento"""
        try:
            self.logger.log(f"Ejecutando experimento: {experiment['name']}", level="INFO")
            
            # Guardar métricas iniciales
            initial_metrics = self.performance_optimizer.current_metrics.__dict__.copy()
            
            # Ejecutar acción del experimento
            result = eval(experiment['action'], {
                'performance_optimizer': self.performance_optimizer,
                'OptimizationStrategy': OptimizationStrategy,
                'OptimizationLevel': OptimizationLevel
            }, experiment['parameters'])
            
            # Esperar a que el experimento complete
            time.sleep(experiment['duration'])
            
            # Medir resultados
            final_metrics = self.performance_optimizer.current_metrics.__dict__.copy()
            improvement = self._calculate_improvement(initial_metrics, final_metrics)
            
            return {
                'experiment_name': experiment['name'],
                'initial_metrics': initial_metrics,
                'final_metrics': final_metrics,
                'improvement': improvement,
                'success': improvement > 0,
                'duration': experiment['duration']
            }
            
        except Exception as e:
            self.logger.log(f"Error ejecutando experimento {experiment['name']}: {e}", level="ERROR")
            return {
                'experiment_name': experiment['name'],
                'success': False,
                'error': str(e)
            }
    
    def _process_experiment_result(self, result: Dict[str, Any]):
        """Procesar resultado de experimento"""
        try:
            if result['success']:
                # Actualizar modelos de aprendizaje con éxito
                features = self._extract_learning_features(self._collect_system_data())
                if features:
                    self._update_learning_models(features, self._collect_system_data())
                
                # Registrar experimento exitoso
                self.analytics.set_alert(
                    title="Experimento Exitoso",
                    message=f"Experimento '{result['experiment_name']}' completado con éxito. Mejora: {result['improvement']:.2f}%",
                    severity="success",
                    category="experiment"
                )
            else:
                # Registrar experimento fallido
                self.analytics.set_alert(
                    title="Experimento Fallido",
                    message=f"Experimento '{result['experiment_name']}' fallido: {result.get('error', 'Unknown error')}",
                    severity="warning",
                    category="experiment"
                )
                
        except Exception as e:
            self.logger.log(f"Error procesando resultado de experimento: {e}", level="ERROR")
    
    def export_learning_report(self, filepath: str):
        """Exportar reporte de aprendizaje"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'learning_status': self.get_learning_status(),
                'learning_history': self.get_learning_history(),
                'improvement_rules': [
                    {
                        'rule_id': rule.rule_id,
                        'name': rule.name,
                        'description': rule.description,
                        'enabled': rule.enabled,
                        'success_rate': rule.success_rate,
                        'execution_count': rule.execution_count,
                        'last_execution': rule.last_execution.isoformat() if rule.last_execution else None
                    }
                    for rule in self.improvement_rules
                ],
                'knowledge_graph_summary': {
                    'total_nodes': len(self.knowledge_graph),
                    'average_confidence': np.mean([node.confidence for node in self.knowledge_graph.values()]) if self.knowledge_graph else 0,
                    'latest_node': list(self.knowledge_graph.keys())[-1] if self.knowledge_graph else None
                },
                'performance_metrics': {
                    'efficiency_score': self.performance_optimizer.current_metrics.efficiency_score,
                    'optimization_gain': self.performance_optimizer.current_metrics.optimization_gain,
                    'total_improvements': len([h for h in self.improvement_history if h.get('improvement', 0) > 0]),
                    'average_improvement': np.mean([h.get('improvement', 0) for h in self.improvement_history if h.get('improvement', 0) > 0]) if any(h.get('improvement', 0) > 0 for h in self.improvement_history) else 0
                }
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log(f"Reporte de aprendizaje exportado a {filepath}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error exportando reporte de aprendizaje: {e}", level="ERROR")
    
    def stop_learning(self):
        """Detener aprendizaje"""
        try:
            self.is_learning = False
            self.config['learning_enabled'] = False
            self.logger.log("Aprendizaje detenido", level="INFO")
        except Exception as e:
            self.logger.log(f"Error deteniendo aprendizaje: {e}", level="ERROR")
    
    def start_learning(self):
        """Iniciar aprendizaje"""
        try:
            self.config['learning_enabled'] = True
            self.is_learning = True
            self.logger.log("Aprendizaje iniciado", level="INFO")
        except Exception as e:
            self.logger.log(f"Error iniciando aprendizaje: {e}", level="ERROR")
    
    def __del__(self):
        """Destructor"""
        try:
            self.is_learning = False
            if hasattr(self, 'learning_thread'):
                self.learning_thread.join(timeout=5)
        except Exception as e:
            self.logger.log(f"Error en destructor: {e}", level="ERROR")