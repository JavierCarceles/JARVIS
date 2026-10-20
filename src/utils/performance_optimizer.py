"""
Performance Optimizer v2.7.0
Optimización de rendimiento del sistema con machine learning y análisis predictivo
"""

import asyncio
import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import psutil
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import threading
import queue
import os
from pathlib import Path

from .advanced_logger import AdvancedLogger
from .performance_monitor import PerformanceMonitor
from .pattern_analyzer import PatternAnalyzer, PatternDetector
from .log_analytics import LogAnalyticsEngine, LogAnalytics

class OptimizationStrategy(Enum):
    """Estrategias de optimización disponibles"""
    CPU_OPTIMIZATION = "cpu_optimization"
    MEMORY_OPTIMIZATION = "memory_optimization"
    DISK_OPTIMIZATION = "disk_optimization"
    NETWORK_OPTIMIZATION = "network_optimization"
    PROCESS_OPTIMIZATION = "process_optimization"
    CACHE_OPTIMIZATION = "cache_optimization"
    THREAD_POOL_OPTIMIZATION = "thread_pool_optimization"
    ALGORITHM_OPTIMIZATION = "algorithm_optimization"
    RESOURCE_ALLOCATION = "resource_allocation"
    LOAD_BALANCING = "load_balancing"

class OptimizationLevel(Enum):
    """Niveles de optimización"""
    BASIC = "basic"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    CRITICAL = "critical"

@dataclass
class OptimizationMetrics:
    """Métricas de optimización"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_usage: float = 0.0
    response_time: float = 0.0
    throughput: float = 0.0
    error_rate: float = 0.0
    efficiency_score: float = 0.0
    optimization_gain: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
@dataclass
class OptimizationAction:
    """Acción de optimización"""
    action_id: str
    strategy: OptimizationStrategy
    level: OptimizationLevel
    description: str
    expected_improvement: float
    confidence: float
    priority: int
    estimated_time: float
    resources_needed: Dict[str, float]
    execution_command: str
    rollback_command: str
    status: str = "pending"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    actual_improvement: Optional[float] = None
    success: bool = False

class PerformanceOptimizer:
    """
    Optimizador de rendimiento con machine learning y optimización predictiva
    """
    
    def __init__(self, config_path: str = None):
        self.logger = AdvancedLogger("PerformanceOptimizer")
        self.monitor = PerformanceMonitor()
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        
        # Configuración
        self.config = self._load_config(config_path)
        self.optimization_history = []
        self.current_actions = {}
        self.optimization_queue = queue.Queue()
        self.is_running = False
        
        # Modelos ML para optimización
        self.models = {}
        self.scalers = {}
        self.feature_names = []
        
        # Métricas actuales
        self.current_metrics = OptimizationMetrics()
        self.baseline_metrics = None
        
        # Configuración de optimización
        self.optimization_thresholds = {
            'cpu_high': 80.0,
            'memory_high': 85.0,
            'disk_high': 90.0,
            'response_time_high': 1000.0,
            'error_rate_high': 0.05
        }
        
        # Inicialización
        self._initialize_models()
        self._start_optimization_loop()
        
        self.logger.log("PerformanceOptimizer inicializado", level="INFO")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Cargar configuración del optimizador"""
        default_config = {
            'optimization_enabled': True,
            'auto_optimization': True,
            'optimization_interval': 60,  # segundos
            'max_concurrent_actions': 3,
            'optimization_strategies': {
                'cpu_optimization': {'enabled': True, 'priority': 1},
                'memory_optimization': {'enabled': True, 'priority': 2},
                'disk_optimization': {'enabled': True, 'priority': 3},
                'network_optimization': {'enabled': True, 'priority': 4},
                'process_optimization': {'enabled': True, 'priority': 5},
                'cache_optimization': {'enabled': True, 'priority': 6},
                'thread_pool_optimization': {'enabled': True, 'priority': 7},
                'algorithm_optimization': {'enabled': True, 'priority': 8},
                'resource_allocation': {'enabled': True, 'priority': 9},
                'load_balancing': {'enabled': True, 'priority': 10}
            },
            'ml_model_path': 'models/optimization_models',
            'history_file': 'data/optimization_history.json',
            'optimization_rules': []
        }
        
        try:
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
        except Exception as e:
            self.logger.log(f"Error cargando configuración: {e}", level="ERROR")
        
        return default_config
    
    def _initialize_models(self):
        """Inicializar modelos de machine learning para optimización"""
        try:
            # Crear directorio para modelos si no existe
            os.makedirs(self.config['ml_model_path'], exist_ok=True)
            
            # Inicializar modelos para diferentes tipos de optimización
            self.models['cpu'] = RandomForestRegressor(n_estimators=100, random_state=42)
            self.models['memory'] = GradientBoostingRegressor(n_estimators=100, random_state=42)
            self.models['disk'] = RandomForestRegressor(n_estimators=100, random_state=42)
            self.models['network'] = GradientBoostingRegressor(n_estimators=100, random_state=42)
            self.models['performance'] = RandomForestRegressor(n_estimators=100, random_state=42)
            
            # Inicializar escaladores
            for metric in self.models.keys():
                self.scalers[metric] = StandardScaler()
            
            # Cargar modelos pre-entrenados si existen
            self._load_trained_models()
            
            self.logger.log("Modelos ML inicializados", level="INFO")
        except Exception as e:
            self.logger.log(f"Error inicializando modelos: {e}", level="ERROR")
    
    def _load_trained_models(self):
        """Cargar modelos pre-entrenados"""
        try:
            for metric, model in self.models.items():
                model_path = os.path.join(self.config['ml_model_path'], f'{metric}_model.pkl')
                scaler_path = os.path.join(self.config['ml_model_path'], f'{metric}_scaler.pkl')
                
                if os.path.exists(model_path):
                    self.models[metric] = joblib.load(model_path)
                    self.logger.log(f"Modelo {metric} cargado desde {model_path}", level="INFO")
                
                if os.path.exists(scaler_path):
                    self.scalers[metric] = joblib.load(scaler_path)
                    self.logger.log(f"Escalador {metric} cargado desde {scaler_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error cargando modelos pre-entrenados: {e}", level="WARNING")
    
    def _save_trained_models(self):
        """Guardar modelos entrenados"""
        try:
            for metric, model in self.models.items():
                model_path = os.path.join(self.config['ml_model_path'], f'{metric}_model.pkl')
                scaler_path = os.path.join(self.config['ml_model_path'], f'{metric}_scaler.pkl')
                
                joblib.dump(model, model_path)
                joblib.dump(self.scalers[metric], scaler_path)
                
                self.logger.log(f"Modelo {metric} guardado en {model_path}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error guardando modelos: {e}", level="ERROR")
    
    def _start_optimization_loop(self):
        """Iniciar bucle de optimización asíncrono"""
        self.is_running = True
        self.optimization_thread = threading.Thread(target=self._optimization_loop)
        self.optimization_thread.daemon = True
        self.optimization_thread.start()
        
        self.logger.log("Bucle de optimización iniciado", level="INFO")
    
    def _optimization_loop(self):
        """Bucle principal de optimización"""
        while self.is_running:
            try:
                if self.config['optimization_enabled'] and self.config['auto_optimization']:
                    self._analyze_system_performance()
                    self._identify_optimization_opportunities()
                    self._execute_optimization_actions()
                
                time.sleep(self.config['optimization_interval'])
            except Exception as e:
                self.logger.log(f"Error en bucle de optimización: {e}", level="ERROR")
                time.sleep(5)
    
    def _analyze_system_performance(self):
        """Analizar rendimiento del sistema"""
        try:
            # Obtener métricas actuales
            metrics = self.monitor.get_performance_summary()
            
            # Transformar métricas al formato esperado
            metrics_dict = {}
            if isinstance(metrics, dict):
                metrics_dict = metrics
            else:
                # Si get_performance_summary devuelve un objeto, extraer valores
                metrics_dict = {
                    'cpu_usage': getattr(metrics, 'cpu_usage', 0.0),
                    'memory_usage': getattr(metrics, 'memory_usage', 0.0),
                    'disk_usage': getattr(metrics, 'disk_usage', 0.0),
                    'network_usage': getattr(metrics, 'network_usage', 0.0),
                    'response_time': getattr(metrics, 'response_time', 0.0),
                    'throughput': getattr(metrics, 'throughput', 0.0),
                    'error_rate': getattr(metrics, 'error_rate', 0.0),
                }
            
            # Actualizar métricas actuales
            self.current_metrics = OptimizationMetrics(
                cpu_usage=metrics_dict.get('cpu_usage', 0.0),
                memory_usage=metrics_dict.get('memory_usage', 0.0),
                disk_usage=metrics_dict.get('disk_usage', 0.0),
                network_usage=metrics_dict.get('network_usage', 0.0),
                response_time=metrics_dict.get('response_time', 0.0),
                throughput=metrics_dict.get('throughput', 0.0),
                error_rate=metrics_dict.get('error_rate', 0.0),
                efficiency_score=self._calculate_efficiency_score(metrics_dict),
                timestamp=datetime.now()
            )
            
            # Establecer baseline si no existe
            if self.baseline_metrics is None:
                self.baseline_metrics = self.current_metrics
            
            # Guardar en historial
            self.optimization_history.append({
                'timestamp': self.current_metrics.timestamp,
                'metrics': self.current_metrics.__dict__,
                'analysis': self._analyze_performance_trends()
            })
            
            # Limitar tamaño del historial
            if len(self.optimization_history) > 1000:
                self.optimization_history = self.optimization_history[-1000:]
            
        except Exception as e:
            self.logger.log(f"Error analizando rendimiento: {e}", level="ERROR")
    
    def _calculate_efficiency_score(self, metrics: Dict[str, float]) -> float:
        """Calcular puntuación de eficiencia del sistema"""
        try:
            # Normalizar métricas (0-100, donde 100 es óptimo)
            cpu_score = max(0, 100 - metrics.get('cpu_usage', 0))
            memory_score = max(0, 100 - metrics.get('memory_usage', 0))
            disk_score = max(0, 100 - metrics.get('disk_usage', 0))
            network_score = max(0, 100 - metrics.get('network_usage', 0))
            response_score = max(0, 100 - min(100, metrics.get('response_time', 0) / 10))
            throughput_score = min(100, metrics.get('throughput', 0) * 10)
            error_score = max(0, 100 - metrics.get('error_rate', 0) * 1000)
            
            # Ponderar métricas
            weights = {
                'cpu': 0.2,
                'memory': 0.2,
                'disk': 0.15,
                'network': 0.15,
                'response': 0.15,
                'throughput': 0.1,
                'error': 0.05
            }
            
            efficiency_score = (
                cpu_score * weights['cpu'] +
                memory_score * weights['memory'] +
                disk_score * weights['disk'] +
                network_score * weights['network'] +
                response_score * weights['response'] +
                throughput_score * weights['throughput'] +
                error_score * weights['error']
            )
            
            return round(efficiency_score, 2)
        except Exception as e:
            self.logger.log(f"Error calculando eficiencia: {e}", level="ERROR")
            return 0.0
    
    def _analyze_performance_trends(self) -> Dict[str, Any]:
        """Analizar tendencias de rendimiento"""
        try:
            if len(self.optimization_history) < 10:
                return {'trend': 'insufficient_data', 'confidence': 0.0}
            
            # Extraer métricas recientes
            recent_metrics = [h['metrics'] for h in self.optimization_history[-10:]]
            
            # Calcular tendencias
            trends = {}
            for metric in ['cpu_usage', 'memory_usage', 'disk_usage', 'response_time', 'error_rate']:
                values = [m.get(metric, 0) for m in recent_metrics]
                if len(values) > 1:
                    trend = np.polyfit(range(len(values)), values, 1)[0]
                    trends[metric] = {
                        'trend': 'increasing' if trend > 0 else 'decreasing' if trend < 0 else 'stable',
                        'slope': trend,
                        'confidence': min(1.0, abs(trend) * 10)
                    }
            
            return trends
        except Exception as e:
            self.logger.log(f"Error analizando tendencias: {e}", level="ERROR")
            return {'trend': 'error', 'confidence': 0.0}
    
    def _identify_optimization_opportunities(self):
        """Identificar oportunidades de optimización"""
        try:
            opportunities = []
            
            # Verificar umbrales de optimización
            if self.current_metrics.cpu_usage > self.optimization_thresholds['cpu_high']:
                opportunities.append(self._create_cpu_optimization_action())
            
            if self.current_metrics.memory_usage > self.optimization_thresholds['memory_high']:
                opportunities.append(self._create_memory_optimization_action())
            
            if self.current_metrics.disk_usage > self.optimization_thresholds['disk_high']:
                opportunities.append(self._create_disk_optimization_action())
            
            if self.current_metrics.response_time > self.optimization_thresholds['response_time_high']:
                opportunities.append(self._create_response_time_optimization_action())
            
            if self.current_metrics.error_rate > self.optimization_thresholds['error_rate_high']:
                opportunities.append(self._create_error_rate_optimization_action())
            
            # Análisis predictivo con ML
            ml_opportunities = self._predict_optimization_opportunities()
            opportunities.extend(ml_opportunities)
            
            # Ordenar por prioridad y agregar a cola
            opportunities.sort(key=lambda x: x.priority, reverse=True)
            
            for opportunity in opportunities:
                if len(self.current_actions) < self.config['max_concurrent_actions']:
                    self.optimization_queue.put(opportunity)
                else:
                    self.logger.log(f"Límite de acciones concurrentes alcanzado, oportunidad en cola: {opportunity.description}", level="INFO")
            
            return opportunities
            
        except Exception as e:
            self.logger.log(f"Error identificando oportunidades: {e}", level="ERROR")
            return []
    
    def _predict_optimization_opportunities(self) -> List[OptimizationAction]:
        """Predecir oportunidades de optimización usando ML"""
        try:
            opportunities = []
            
            # Preparar características para predicción
            features = self._prepare_features_for_prediction()
            
            if features is None:
                return opportunities
            
            # Predecir para cada tipo de optimización
            for metric, model in self.models.items():
                try:
                    if model is not None:
                        # Escalar características
                        features_scaled = self.scalers[metric].transform([features])
                        
                        # Predecir
                        prediction = model.predict(features_scaled)[0]
                        confidence = abs(prediction) / (abs(prediction) + 1)  # Normalizar confianza
                        
                        if confidence > 0.7:  # Umbral de confianza
                            opportunity = self._create_ml_optimization_action(metric, prediction, confidence)
                            if opportunity:
                                opportunities.append(opportunity)
                except Exception as e:
                    self.logger.log(f"Error prediciendo {metric}: {e}", level="WARNING")
            
            return opportunities
        except Exception as e:
            self.logger.log(f"Error prediciendo oportunidades: {e}", level="ERROR")
            return []
    
    def _prepare_features_for_prediction(self) -> Optional[List[float]]:
        """Preparar características para predicción ML"""
        try:
            if len(self.optimization_history) < 5:
                return None
            
            # Extraer características históricas
            recent_history = self.optimization_history[-5:]
            
            features = []
            
            # Métricas actuales
            features.extend([
                self.current_metrics.cpu_usage,
                self.current_metrics.memory_usage,
                self.current_metrics.disk_usage,
                self.current_metrics.network_usage,
                self.current_metrics.response_time,
                self.current_metrics.throughput,
                self.current_metrics.error_rate,
                self.current_metrics.efficiency_score
            ])
            
            # Tendencias recientes
            for metric in ['cpu_usage', 'memory_usage', 'disk_usage', 'response_time', 'error_rate']:
                values = [h['metrics'].get(metric, 0) for h in recent_history]
                if len(values) > 1:
                    trend = np.polyfit(range(len(values)), values, 1)[0]
                    features.append(trend)
                else:
                    features.append(0)
            
            # Características temporales
            current_hour = datetime.now().hour
            current_day = datetime.now().weekday()
            features.extend([current_hour, current_day])
            
            return features
        except Exception as e:
            self.logger.log(f"Error preparando características: {e}", level="ERROR")
            return None
    
    def _create_cpu_optimization_action(self) -> OptimizationAction:
        """Crear acción de optimización de CPU"""
        return OptimizationAction(
            action_id=f"cpu_opt_{int(time.time())}",
            strategy=OptimizationStrategy.CPU_OPTIMIZATION,
            level=OptimizationLevel.MODERATE,
            description="Optimización de uso de CPU",
            expected_improvement=15.0,
            confidence=0.8,
            priority=1,
            estimated_time=30.0,
            resources_needed={'cpu': 0.1, 'memory': 0.05},
            execution_command="python scripts/optimize_cpu.py",
            rollback_command="python scripts/restore_cpu.py"
        )
    
    def _create_memory_optimization_action(self) -> OptimizationAction:
        """Crear acción de optimización de memoria"""
        return OptimizationAction(
            action_id=f"memory_opt_{int(time.time())}",
            strategy=OptimizationStrategy.MEMORY_OPTIMIZATION,
            level=OptimizationLevel.MODERATE,
            description="Optimización de uso de memoria",
            expected_improvement=20.0,
            confidence=0.9,
            priority=2,
            estimated_time=45.0,
            resources_needed={'cpu': 0.05, 'memory': 0.1},
            execution_command="python scripts/optimize_memory.py",
            rollback_command="python scripts/restore_memory.py"
        )
    
    def _create_disk_optimization_action(self) -> OptimizationAction:
        """Crear acción de optimización de disco"""
        return OptimizationAction(
            action_id=f"disk_opt_{int(time.time())}",
            strategy=OptimizationStrategy.DISK_OPTIMIZATION,
            level=OptimizationLevel.MODERATE,
            description="Optimización de uso de disco",
            expected_improvement=10.0,
            confidence=0.7,
            priority=3,
            estimated_time=60.0,
            resources_needed={'cpu': 0.1, 'disk': 0.2},
            execution_command="python scripts/optimize_disk.py",
            rollback_command="python scripts/restore_disk.py"
        )
    
    def _create_response_time_optimization_action(self) -> OptimizationAction:
        """Crear acción de optimización de tiempo de respuesta"""
        return OptimizationAction(
            action_id=f"response_opt_{int(time.time())}",
            strategy=OptimizationStrategy.ALGORITHM_OPTIMIZATION,
            level=OptimizationLevel.MODERATE,
            description="Optimización de tiempo de respuesta",
            expected_improvement=25.0,
            confidence=0.8,
            priority=4,
            estimated_time=90.0,
            resources_needed={'cpu': 0.2, 'memory': 0.1},
            execution_command="python scripts/optimize_algorithms.py",
            rollback_command="python scripts/restore_algorithms.py"
        )
    
    def _create_error_rate_optimization_action(self) -> OptimizationAction:
        """Crear acción de optimización de tasa de errores"""
        return OptimizationAction(
            action_id=f"error_opt_{int(time.time())}",
            strategy=OptimizationStrategy.PROCESS_OPTIMIZATION,
            level=OptimizationLevel.CRITICAL,
            description="Reducción de tasa de errores",
            expected_improvement=50.0,
            confidence=0.9,
            priority=5,
            estimated_time=120.0,
            resources_needed={'cpu': 0.15, 'memory': 0.1},
            execution_command="python scripts/optimize_processes.py",
            rollback_command="python scripts/restore_processes.py"
        )
    
    def _create_ml_optimization_action(self, metric: str, prediction: float, confidence: float) -> Optional[OptimizationAction]:
        """Crear acción de optimización basada en ML"""
        try:
            # Mapear métrica a estrategia
            strategy_map = {
                'cpu': OptimizationStrategy.CPU_OPTIMIZATION,
                'memory': OptimizationStrategy.MEMORY_OPTIMIZATION,
                'disk': OptimizationStrategy.DISK_OPTIMIZATION,
                'network': OptimizationStrategy.NETWORK_OPTIMIZATION,
                'performance': OptimizationStrategy.RESOURCE_ALLOCATION
            }
            
            strategy = strategy_map.get(metric, OptimizationStrategy.RESOURCE_ALLOCATION)
            
            # Determinar nivel de optimización basado en predicción
            if abs(prediction) > 0.5:
                level = OptimizationLevel.AGGRESSIVE
            elif abs(prediction) > 0.3:
                level = OptimizationLevel.MODERATE
            else:
                level = OptimizationLevel.BASIC
            
            return OptimizationAction(
                action_id=f"ml_opt_{metric}_{int(time.time())}",
                strategy=strategy,
                level=level,
                description=f"Optimización ML para {metric} (predicción: {prediction:.2f})",
                expected_improvement=abs(prediction) * 30,
                confidence=confidence,
                priority=6,
                estimated_time=60.0,
                resources_needed={'cpu': 0.1, 'memory': 0.05},
                execution_command=f"python scripts/optimize_{metric}.py",
                rollback_command=f"python scripts/restore_{metric}.py"
            )
        except Exception as e:
            self.logger.log(f"Error creando acción ML: {e}", level="ERROR")
            return None
    
    def _execute_optimization_actions(self):
        """Ejecutar acciones de optimización"""
        try:
            while not self.optimization_queue.empty() and len(self.current_actions) < self.config['max_concurrent_actions']:
                action = self.optimization_queue.get()
                
                # Ejecutar acción en hilo separado
                action_thread = threading.Thread(target=self._execute_single_action, args=(action,))
                action_thread.daemon = True
                action_thread.start()
                
                self.current_actions[action.action_id] = {
                    'action': action,
                    'thread': action_thread,
                    'start_time': datetime.now()
                }
            
            # Verificar estado de acciones en curso
            completed_actions = []
            for action_id, action_info in self.current_actions.items():
                if not action_info['thread'].is_alive():
                    completed_actions.append(action_id)
            
            # Limpiar acciones completadas
            for action_id in completed_actions:
                action_info = self.current_actions.pop(action_id)
                action = action_info['action']
                action.end_time = datetime.now()
                
                # Calcular mejora real
                if action.success:
                    improvement = self._calculate_actual_improvement(action)
                    action.actual_improvement = improvement
                    
                    # Actualizar modelos ML
                    self._update_ml_models(action, improvement)
                
                # Guardar en historial
                self.optimization_history.append({
                    'timestamp': datetime.now(),
                    'action': action.__dict__,
                    'improvement': action.actual_improvement
                })
            
        except Exception as e:
            self.logger.log(f"Error ejecutando acciones: {e}", level="ERROR")
    
    def _execute_single_action(self, action: OptimizationAction):
        """Ejecutar una acción de optimización individual"""
        try:
            self.logger.log(f"Iniciando ejecución de acción: {action.description}", level="INFO")
            
            action.status = "running"
            action.start_time = datetime.now()
            
            # Guardar métricas antes de ejecutar
            pre_metrics = self.current_metrics.__dict__.copy()
            
            # Ejecutar comando de optimización
            result = self._execute_optimization_command(action.execution_command)
            
            if result['success']:
                action.success = True
                action.status = "completed"
                
                # Esperar a que los cambios surtan efecto
                time.sleep(action.estimated_time)
                
                # Medir mejora real
                post_metrics = self.current_metrics.__dict__.copy()
                improvement = self._calculate_improvement(pre_metrics, post_metrics)
                
                action.actual_improvement = improvement
                
                self.logger.log(f"Acción completada con éxito. Mejora: {improvement:.2f}%", level="INFO")
                
                # Generar alerta si la mejora es significativa
                if improvement > 10.0:
                    self.analytics.set_alert(
                        title="Optimización Exitosa",
                        message=f"Mejora del {improvement:.2f}% en {action.strategy.value}",
                        severity="success",
                        category="optimization"
                    )
            else:
                action.success = False
                action.status = "failed"
                
                # Intentar rollback
                self._execute_optimization_command(action.rollback_command)
                
                self.logger.log(f"Acción fallida: {result['error']}", level="ERROR")
                
                # Generar alerta de error
                self.analytics.set_alert(
                    title="Optimización Fallida",
                    message=f"Error en {action.strategy.value}: {result['error']}",
                    severity="error",
                    category="optimization"
                )
                
        except Exception as e:
            action.success = False
            action.status = "error"
            self.logger.log(f"Error ejecutando acción {action.action_id}: {e}", level="ERROR")
            
            # Intentar rollback
            try:
                self._execute_optimization_command(action.rollback_command)
            except Exception as rollback_error:
                self.logger.log(f"Error en rollback: {rollback_error}", level="ERROR")
    
    def _execute_optimization_command(self, command: str) -> Dict[str, Any]:
        """Ejecutar comando de optimización"""
        try:
            # Ejecutar comando (esto debería ser implementado específicamente para cada sistema)
            # Por ahora, simulamos la ejecución
            result = {
                'success': True,
                'output': f"Ejecutando: {command}",
                'error': None
            }
            
            # En un sistema real, esto ejecutaría el comando real
            # result = subprocess.run(command, shell=True, capture_output=True, text=True)
            # result = {
            #     'success': result.returncode == 0,
            #     'output': result.stdout,
            #     'error': result.stderr if result.returncode != 0 else None
            # }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'output': None,
                'error': str(e)
            }
    
    def _calculate_improvement(self, pre_metrics: Dict[str, float], post_metrics: Dict[str, float]) -> float:
        """Calcular mejora porcentual"""
        try:
            # Calcular puntuación de eficiencia antes y después
            pre_efficiency = pre_metrics.get('efficiency_score', 0)
            post_efficiency = post_metrics.get('efficiency_score', 0)
            
            if pre_efficiency == 0:
                return 0.0
            
            improvement = ((post_efficiency - pre_efficiency) / pre_efficiency) * 100
            return round(improvement, 2)
        except Exception as e:
            self.logger.log(f"Error calculando mejora: {e}", level="ERROR")
            return 0.0
    
    def _calculate_actual_improvement(self, action: OptimizationAction) -> float:
        """Calcular mejora real de una acción"""
        try:
            if action.start_time is None:
                return 0.0
            
            # Encontrar métricas justo antes de la acción
            action_start_index = None
            for i, history_entry in enumerate(self.optimization_history):
                if history_entry['timestamp'] >= action.start_time:
                    action_start_index = i
                    break
            
            if action_start_index is None or action_start_index == 0:
                return 0.0
            
            # Calcular mejora basada en métricas
            pre_metrics = self.optimization_history[action_start_index - 1]['metrics']
            post_metrics = self.optimization_history[-1]['metrics']
            
            return self._calculate_improvement(pre_metrics, post_metrics)
        except Exception as e:
            self.logger.log(f"Error calculando mejora real: {e}", level="ERROR")
            return 0.0
    
    def _update_ml_models(self, action: OptimizationAction, improvement: float):
        """Actualizar modelos ML con resultados de optimización"""
        try:
            # Preparar características y etiqueta
            features = self._prepare_features_for_prediction()
            if features is None:
                return
            
            # Determinar etiqueta basada en mejora
            label = 1 if improvement > 5.0 else 0  # Mejora significativa o no
            
            # Actualizar modelo correspondiente a la estrategia
            strategy_model_map = {
                OptimizationStrategy.CPU_OPTIMIZATION: 'cpu',
                OptimizationStrategy.MEMORY_OPTIMIZATION: 'memory',
                OptimizationStrategy.DISK_OPTIMIZATION: 'disk',
                OptimizationStrategy.NETWORK_OPTIMIZATION: 'network',
                OptimizationStrategy.RESOURCE_ALLOCATION: 'performance'
            }
            
            model_key = strategy_model_map.get(action.strategy, 'performance')
            
            if model_key in self.models:
                # Escalar características
                features_scaled = self.scalers[model_key].transform([features])
                
                # Re-entrenar modelo
                X = np.vstack([features_scaled])
                y = np.array([label])
                
                self.models[model_key].fit(X, y)
                
                # Guardar modelos actualizados
                self._save_trained_models()
                
                self.logger.log(f"Modelo {model_key} actualizado con resultado de optimización", level="INFO")
                
        except Exception as e:
            self.logger.log(f"Error actualizando modelos ML: {e}", level="ERROR")
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """Obtener estado actual de optimización"""
        try:
            return {
                'is_running': self.is_running,
                'current_metrics': self.current_metrics.__dict__,
                'baseline_metrics': self.baseline_metrics.__dict__ if self.baseline_metrics else None,
                'active_actions': len(self.current_actions),
                'queued_actions': self.optimization_queue.qsize(),
                'optimization_enabled': self.config['optimization_enabled'],
                'auto_optimization': self.config['auto_optimization'],
                'efficiency_score': self.current_metrics.efficiency_score,
                'optimization_gain': self.current_metrics.optimization_gain,
                'last_analysis': self.optimization_history[-1]['timestamp'] if self.optimization_history else None
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo estado: {e}", level="ERROR")
            return {}
    
    def get_optimization_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Obtener historial de optimización"""
        try:
            return self.optimization_history[-limit:]
        except Exception as e:
            self.logger.log(f"Error obteniendo historial: {e}", level="ERROR")
            return []
    
    def get_current_actions(self) -> List[Dict[str, Any]]:
        """Obtener acciones en curso"""
        try:
            actions = []
            for action_id, action_info in self.current_actions.items():
                action = action_info['action']
                actions.append({
                    'action_id': action.action_id,
                    'strategy': action.strategy.value,
                    'level': action.level.value,
                    'description': action.description,
                    'status': action.status,
                    'start_time': action.start_time,
                    'expected_improvement': action.expected_improvement,
                    'actual_improvement': action.actual_improvement,
                    'success': action.success
                })
            return actions
        except Exception as e:
            self.logger.log(f"Error obteniendo acciones en curso: {e}", level="ERROR")
            return []
    
    def add_custom_optimization_action(self, action: OptimizationAction):
        """Añadir acción de optimización personalizada"""
        try:
            self.optimization_queue.put(action)
            self.logger.log(f"Acción personalizada añadida: {action.description}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error añadiendo acción personalizada: {e}", level="ERROR")
    
    def stop_optimization(self):
        """Detener optimización"""
        try:
            self.is_running = False
            self.config['optimization_enabled'] = False
            self.logger.log("Optimización detenida", level="INFO")
        except Exception as e:
            self.logger.log(f"Error deteniendo optimización: {e}", level="ERROR")
    
    def start_optimization(self):
        """Iniciar optimización"""
        try:
            self.config['optimization_enabled'] = True
            self.is_running = True
            self.logger.log("Optimización iniciada", level="INFO")
        except Exception as e:
            self.logger.log(f"Error iniciando optimización: {e}", level="ERROR")
    
    def optimize_system(self, strategy: OptimizationStrategy, level: OptimizationLevel = OptimizationLevel.MODERATE) -> OptimizationAction:
        """Optimizar sistema manualmente"""
        try:
            action = OptimizationAction(
                action_id=f"manual_opt_{int(time.time())}",
                strategy=strategy,
                level=level,
                description=f"Optimización manual: {strategy.value}",
                expected_improvement=15.0,
                confidence=0.8,
                priority=10,
                estimated_time=60.0,
                resources_needed={'cpu': 0.1, 'memory': 0.05},
                execution_command=f"python scripts/optimize_{strategy.value}.py",
                rollback_command=f"python scripts/restore_{strategy.value}.py"
            )
            
            self.add_custom_optimization_action(action)
            return action
            
        except Exception as e:
            self.logger.log(f"Error optimizando sistema: {e}", level="ERROR")
            return None
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Obtener recomendaciones de optimización"""
        try:
            recommendations = []
            
            # Analizar métricas actuales
            if self.current_metrics.cpu_usage > 80:
                recommendations.append({
                    'type': 'cpu',
                    'priority': 'high',
                    'description': 'Uso de CPU alto, considerando optimización',
                    'action': 'Optimize CPU usage',
                    'expected_improvement': 15.0,
                    'confidence': 0.8
                })
            
            if self.current_metrics.memory_usage > 85:
                recommendations.append({
                    'type': 'memory',
                    'priority': 'high',
                    'description': 'Uso de memoria alto, considerando optimización',
                    'action': 'Optimize memory usage',
                    'expected_improvement': 20.0,
                    'confidence': 0.9
                })
            
            if self.current_metrics.response_time > 1000:
                recommendations.append({
                    'type': 'performance',
                    'priority': 'medium',
                    'description': 'Tiempo de respuesta elevado, considerando optimización de algoritmos',
                    'action': 'Optimize algorithms',
                    'expected_improvement': 25.0,
                    'confidence': 0.8
                })
            
            if self.current_metrics.error_rate > 0.05:
                recommendations.append({
                    'type': 'error',
                    'priority': 'critical',
                    'description': 'Tasa de errores alta, requeriendo optimización crítica',
                    'action': 'Optimize processes',
                    'expected_improvement': 50.0,
                    'confidence': 0.9
                })
            
            return recommendations
        except Exception as e:
            self.logger.log(f"Error obteniendo recomendaciones: {e}", level="ERROR")
            return []
    
    def export_optimization_report(self, filepath: str):
        """Exportar reporte de optimización"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'current_metrics': self.current_metrics.__dict__,
                'baseline_metrics': self.baseline_metrics.__dict__ if self.baseline_metrics else None,
                'optimization_history': self.optimization_history[-100:],  # Últimos 100 registros
                'current_actions': self.get_current_actions(),
                'recommendations': self.get_optimization_recommendations(),
                'efficiency_score': self.current_metrics.efficiency_score,
                'total_improvements': sum(1 for h in self.optimization_history if 'improvement' in h and h['improvement'] > 0),
                'average_improvement': np.mean([h['improvement'] for h in self.optimization_history if 'improvement' in h and h['improvement'] > 0]) if any('improvement' in h and h['improvement'] > 0 for h in self.optimization_history) else 0
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log(f"Reporte de optimización exportado a {filepath}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error exportando reporte: {e}", level="ERROR")

    def optimize_resources(self, optimization_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimizar recursos basado en solicitud contextual.

        2.8.4.7.2 — Conectar PerformanceOptimizer cuando proceda.

        Args:
            optimization_request: Solicitud de optimización con contexto y recursos

        Returns:
            Resultado de optimización
        """
        try:
            self.logger.log(f"Iniciando optimización de recursos: {optimization_request}", level="INFO")

            # Extraer contexto de la solicitud
            context = optimization_request.get("context", {})
            current_resources = optimization_request.get("current_resources", {})
            
            # Analizar presión actual de recursos
            resource_pressure = {}
            for resource_type, resource_info in current_resources.items():
                if resource_info.get("maximum") and resource_info.get("available_amount") is not None:
                    pressure = (resource_info["maximum"] - resource_info["available_amount"]) / resource_info["maximum"]
                    resource_pressure[resource_type] = pressure

            # Generar recomendaciones de optimización
            recommendations = []
            
            # Análisis de presión de recursos
            high_pressure_resources = [r for r, p in resource_pressure.items() if p > 0.8]
            medium_pressure_resources = [r for r, p in resource_pressure.items() if p > 0.6 and p <= 0.8]
            
            if high_pressure_resources:
                recommendations.append({
                    "type": "critical_resource_pressure",
                    "resources": high_pressure_resources,
                    "priority": "critical",
                    "description": f"Recursos críticamente presionados: {', '.join(high_pressure_resources)}",
                    "action": "redistribute_resources",
                    "expected_improvement": 30.0,
                    "confidence": 0.9
                })
            
            if medium_pressure_resources:
                recommendations.append({
                    "type": "moderate_resource_pressure", 
                    "resources": medium_pressure_resources,
                    "priority": "medium",
                    "description": f"Recursos moderadamente presionados: {', '.join(medium_pressure_resources)}",
                    "action": "monitor_and_adjust",
                    "expected_improvement": 15.0,
                    "confidence": 0.7
                })

            # Análisis de contexto para optimización específica
            if context.get("workload") == "high":
                recommendations.append({
                    "type": "high_workload_optimization",
                    "priority": "high",
                    "description": "Optimización para carga de trabajo alta",
                    "action": "increase_thread_pool",
                    "expected_improvement": 20.0,
                    "confidence": 0.8
                })

            if context.get("error_rate") and context["error_rate"] > 0.05:
                recommendations.append({
                    "type": "error_rate_optimization",
                    "priority": "critical", 
                    "description": f"Optimización por alta tasa de errores: {context['error_rate']:.2%}",
                    "action": "optimize_error_handling",
                    "expected_improvement": 40.0,
                    "confidence": 0.85
                })

            # Calcular mejora potencial
            total_improvement = sum(r.get("expected_improvement", 0) for r in recommendations)
            
            # Construir resultado
            result = {
                "success": len(recommendations) > 0,
                "improvement": total_improvement,
                "recommendations": recommendations,
                "resource_pressure": resource_pressure,
                "context_analysis": context,
                "timestamp": datetime.now().isoformat(),
                "optimization_strategy": "resource_allocation_optimization"
            }

            self.logger.log(f"Optimización completada: {len(recommendations)} recomendaciones, {total_improvement:.1f}% mejora potencial", level="INFO")

            return result

        except Exception as e:
            self.logger.log(f"Error en optimización de recursos: {e}", level="ERROR")
            return {
                "success": False,
                "improvement": 0.0,
                "recommendations": [],
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def __del__(self):
        """Destructor"""
        try:
            self.is_running = False
            if hasattr(self, 'optimization_thread'):
                self.optimization_thread.join(timeout=5)
        except Exception as e:
            self.logger.log(f"Error en destructor: {e}", level="ERROR")