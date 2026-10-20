"""
Optimization Orchestrator v2.7.0
Orquestador de optimización que coordina todos los sistemas de optimización
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
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib
import threading
import queue
import os
from pathlib import Path

from .advanced_logger import AdvancedLogger
from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy
from .self_improvement_system import SelfImprovementSystem, LearningMode
from .adaptive_learning_engine import AdaptiveLearningEngine, LearningTask
from .pattern_analyzer import PatternAnalyzer
from .log_analytics import LogAnalytics

class OrchestrationMode(Enum):
    """Modos de orquestación"""
    COORDINATED = "coordinated"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ADAPTIVE = "adaptive"
    OPTIMIZED = "optimized"

class OptimizationPriority(Enum):
    """Prioridades de optimización"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"

@dataclass
class OptimizationJob:
    """Trabajo de optimización"""
    job_id: str
    name: str
    description: str
    priority: OptimizationPriority
    strategies: List[OptimizationStrategy]
    dependencies: List[str] = field(default_factory=list)
    estimated_duration: float = 60.0
    resources_required: Dict[str, float] = field(default_factory=dict)
    status: str = "pending"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    success: bool = False
    error_message: Optional[str] = None

@dataclass
class OrchestrationMetrics:
    """Métricas de orquestación"""
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    running_jobs: int = 0
    pending_jobs: int = 0
    average_job_duration: float = 0.0
    system_efficiency: float = 0.0
    resource_utilization: float = 0.0
    optimization_success_rate: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

class OptimizationOrchestrator:
    """
    Orquestador de optimización que coordina todos los sistemas de optimización
    """
    
    def __init__(self, config_path: str = None):
        self.logger = AdvancedLogger("OptimizationOrchestrator")
        
        # Sistemas de optimización
        self.performance_optimizer = PerformanceOptimizer()
        self.self_improvement_system = SelfImprovementSystem()
        self.adaptive_learning_engine = AdaptiveLearningEngine()
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        
        # Configuración
        self.config = self._load_config(config_path)
        self.optimization_jobs = {}
        self.job_queue = queue.PriorityQueue()
        self.is_running = False
        self.orchestration_mode = OrchestrationMode.ADAPTIVE
        
        # Estado del sistema
        self.system_metrics = OrchestrationMetrics()
        self.optimization_history = []
        self.resource_monitor = {}
        
        # Inicialización
        self._initialize_resource_monitor()
        self._start_orchestration_loop()
        
        self.logger.log("OptimizationOrchestrator inicializado", level="INFO")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Cargar configuración del orquestador"""
        default_config = {
            'orchestration_enabled': True,
            'auto_orchestration': True,
            'orchestration_interval': 30,  # segundos
            'max_concurrent_jobs': 5,
            'orchestration_mode': 'adaptive',
            'resource_limits': {
                'cpu_max': 80.0,
                'memory_max': 85.0,
                'disk_max': 90.0,
                'network_max': 75.0
            },
            'priority_weights': {
                OptimizationPriority.CRITICAL: 10,
                OptimizationPriority.HIGH: 8,
                OptimizationPriority.MEDIUM: 5,
                OptimizationPriority.LOW: 3,
                OptimizationPriority.BACKGROUND: 1
            },
            'strategy_preferences': {
                OptimizationStrategy.CPU_OPTIMIZATION: 0.8,
                OptimizationStrategy.MEMORY_OPTIMIZATION: 0.8,
                OptimizationStrategy.DISK_OPTIMIZATION: 0.6,
                OptimizationStrategy.NETWORK_OPTIMIZATION: 0.7,
                OptimizationStrategy.PROCESS_OPTIMIZATION: 0.9,
                OptimizationStrategy.CACHE_OPTIMIZATION: 0.7,
                OptimizationStrategy.THREAD_POOL_OPTIMIZATION: 0.6,
                OptimizationStrategy.ALGORITHM_OPTIMIZATION: 0.8,
                OptimizationStrategy.RESOURCE_ALLOCATION: 0.7,
                OptimizationStrategy.LOAD_BALANCING: 0.5
            },
            'job_timeout': 300,  # 5 minutos
            'retry_attempts': 3,
            'failure_threshold': 0.3,
            'success_threshold': 0.8,
            'model_save_path': 'models/orchestration_models',
            'orchestration_history_file': 'data/orchestration_history.json'
        }
        
        try:
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
        except Exception as e:
            self.logger.log(f"Error cargando configuración: {e}", level="ERROR")
        
        return default_config
    
    def _initialize_resource_monitor(self):
        """Inicializar monitor de recursos"""
        try:
            self.resource_monitor = {
                'cpu': {'current': 0.0, 'max': self.config['resource_limits']['cpu_max']},
                'memory': {'current': 0.0, 'max': self.config['resource_limits']['memory_max']},
                'disk': {'current': 0.0, 'max': self.config['resource_limits']['disk_max']},
                'network': {'current': 0.0, 'max': self.config['resource_limits']['network_max']}
            }
            
            self.logger.log("Monitor de recursos inicializado", level="INFO")
        except Exception as e:
            self.logger.log(f"Error inicializando monitor de recursos: {e}", level="ERROR")
    
    def _start_orchestration_loop(self):
        """Iniciar bucle de orquestación"""
        self.is_running = True
        self.orchestration_thread = threading.Thread(target=self._orchestration_loop)
        self.orchestration_thread.daemon = True
        self.orchestration_thread.start()
        
        self.logger.log("Bucle de orquestación iniciado", level="INFO")
    
    def _orchestration_loop(self):
        """Bucle principal de orquestación"""
        while self.is_running:
            try:
                if self.config['orchestration_enabled'] and self.config['auto_orchestration']:
                    self._update_system_metrics()
                    self._analyze_optimization_needs()
                    self._coordinate_optimization_strategies()
                    self._process_optimization_jobs()
                    self._monitor_job_progress()
                    self._optimize_orchestration_mode()
                
                time.sleep(self.config['orchestration_interval'])
            except Exception as e:
                self.logger.log(f"Error en bucle de orquestación: {e}", level="ERROR")
                time.sleep(5)
    
    def _update_system_metrics(self):
        """Actualizar métricas del sistema"""
        try:
            # Obtener métricas del optimizador de rendimiento
            performance_metrics = self.performance_optimizer.get_optimization_status()
            
            # Actualizar monitor de recursos
            self.resource_monitor['cpu']['current'] = performance_metrics.get('current_metrics', {}).get('cpu_usage', 0.0)
            self.resource_monitor['memory']['current'] = performance_metrics.get('current_metrics', {}).get('memory_usage', 0.0)
            self.resource_monitor['disk']['current'] = performance_metrics.get('current_metrics', {}).get('disk_usage', 0.0)
            self.resource_monitor['network']['current'] = performance_metrics.get('current_metrics', {}).get('network_usage', 0.0)
            
            # Actualizar métricas de orquestación
            self.system_metrics = OrchestrationMetrics(
                total_jobs=len(self.optimization_jobs),
                completed_jobs=len([j for j in self.optimization_jobs.values() if j.status == "completed"]),
                failed_jobs=len([j for j in self.optimization_jobs.values() if j.status == "failed"]),
                running_jobs=len([j for j in self.optimization_jobs.values() if j.status == "running"]),
                pending_jobs=len([j for j in self.optimization_jobs.values() if j.status == "pending"]),
                system_efficiency=performance_metrics.get('efficiency_score', 0.0),
                resource_utilization=self._calculate_resource_utilization(),
                optimization_success_rate=self._calculate_success_rate(),
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.log(f"Error actualizando métricas del sistema: {e}", level="ERROR")
    
    def _calculate_resource_utilization(self) -> float:
        """Calcular utilización de recursos"""
        try:
            utilizations = []
            for resource, data in self.resource_monitor.items():
                utilization = data['current'] / data['max']
                utilizations.append(min(1.0, utilization))
            
            return np.mean(utilizations)
        except Exception as e:
            self.logger.log(f"Error calculando utilización de recursos: {e}", level="ERROR")
            return 0.0
    
    def _calculate_success_rate(self) -> float:
        """Calcular tasa de éxito de optimización"""
        try:
            completed_jobs = [j for j in self.optimization_jobs.values() if j.status == "completed"]
            if not completed_jobs:
                return 0.0
            
            successful_jobs = [j for j in completed_jobs if j.success]
            return len(successful_jobs) / len(completed_jobs)
        except Exception as e:
            self.logger.log(f"Error calculando tasa de éxito: {e}", level="ERROR")
            return 0.0
    
    def _analyze_optimization_needs(self):
        """Analizar necesidades de optimización"""
        try:
            needs = []
            
            # Analizar métricas del sistema
            cpu_usage = self.resource_monitor['cpu']['current']
            memory_usage = self.resource_monitor['memory']['current']
            disk_usage = self.resource_monitor['disk']['current']
            network_usage = self.resource_monitor['network']['current']
            
            # Detectar necesidades críticas
            if cpu_usage > 90:
                needs.append({
                    'priority': OptimizationPriority.CRITICAL,
                    'strategy': OptimizationStrategy.CPU_OPTIMIZATION,
                    'description': "Uso de CPU crítico, requiere optimización inmediata",
                    'urgency': 1.0
                })
            
            if memory_usage > 95:
                needs.append({
                    'priority': OptimizationPriority.CRITICAL,
                    'strategy': OptimizationStrategy.MEMORY_OPTIMIZATION,
                    'description': "Uso de memoria crítico, requiere optimización inmediata",
                    'urgency': 1.0
                })
            
            if disk_usage > 95:
                needs.append({
                    'priority': OptimizationPriority.CRITICAL,
                    'strategy': OptimizationStrategy.DISK_OPTIMIZATION,
                    'description': "Uso de disco crítico, requiere optimización inmediata",
                    'urgency': 1.0
                })
            
            # Detectar necesidades altas
            if cpu_usage > 80:
                needs.append({
                    'priority': OptimizationPriority.HIGH,
                    'strategy': OptimizationStrategy.CPU_OPTIMIZATION,
                    'description': "Uso de CPU alto, requiere optimización",
                    'urgency': 0.8
                })
            
            if memory_usage > 85:
                needs.append({
                    'priority': OptimizationPriority.HIGH,
                    'strategy': OptimizationStrategy.MEMORY_OPTIMIZATION,
                    'description': "Uso de memoria alto, requiere optimización",
                    'urgency': 0.8
                })
            
            # Detectar necesidades medias
            if network_usage > 70:
                needs.append({
                    'priority': OptimizationPriority.MEDIUM,
                    'strategy': OptimizationStrategy.NETWORK_OPTIMIZATION,
                    'description': "Uso de red alto, considera optimización",
                    'urgency': 0.6
                })
            
            # Analizar patrones del sistema
            pattern_analysis = self.pattern_analyzer.get_pattern_analysis()
            if pattern_analysis.get('anomaly_count', 0) > 5:
                needs.append({
                    'priority': OptimizationPriority.HIGH,
                    'strategy': OptimizationStrategy.PROCESS_OPTIMIZATION,
                    'description': "Alta cantidad de anomalías detectadas",
                    'urgency': 0.9
                })
            
            # Crear trabajos de optimización basados en necesidades
            for need in needs:
                job = OptimizationJob(
                    job_id=f"opt_{int(time.time())}_{need['strategy'].value}",
                    name=f"Optimization: {need['strategy'].value}",
                    description=need['description'],
                    priority=need['priority'],
                    strategies=[need['strategy']],
                    estimated_duration=60.0,
                    resources_required=self._estimate_resources(need['strategy']),
                    status="pending"
                )
                
                self._add_optimization_job(job)
            
        except Exception as e:
            self.logger.log(f"Error analizando necesidades de optimización: {e}", level="ERROR")
    
    def _estimate_resources(self, strategy: OptimizationStrategy) -> Dict[str, float]:
        """Estimar recursos requeridos para una estrategia"""
        try:
            resource_map = {
                OptimizationStrategy.CPU_OPTIMIZATION: {'cpu': 0.2, 'memory': 0.1},
                OptimizationStrategy.MEMORY_OPTIMIZATION: {'cpu': 0.1, 'memory': 0.2},
                OptimizationStrategy.DISK_OPTIMIZATION: {'cpu': 0.15, 'memory': 0.05, 'disk': 0.1},
                OptimizationStrategy.NETWORK_OPTIMIZATION: {'cpu': 0.1, 'memory': 0.05, 'network': 0.2},
                OptimizationStrategy.PROCESS_OPTIMIZATION: {'cpu': 0.3, 'memory': 0.15},
                OptimizationStrategy.CACHE_OPTIMIZATION: {'cpu': 0.1, 'memory': 0.1},
                OptimizationStrategy.THREAD_POOL_OPTIMIZATION: {'cpu': 0.05, 'memory': 0.05},
                OptimizationStrategy.ALGORITHM_OPTIMIZATION: {'cpu': 0.2, 'memory': 0.1},
                OptimizationStrategy.RESOURCE_ALLOCATION: {'cpu': 0.1, 'memory': 0.1},
                OptimizationStrategy.LOAD_BALANCING: {'cpu': 0.15, 'memory': 0.1, 'network': 0.1}
            }
            
            return resource_map.get(strategy, {'cpu': 0.1, 'memory': 0.1})
        except Exception as e:
            self.logger.log(f"Error estimando recursos: {e}", level="ERROR")
            return {'cpu': 0.1, 'memory': 0.1}
    
    def _add_optimization_job(self, job: OptimizationJob):
        """Añadir trabajo de optimización"""
        try:
            # Calcular prioridad numérica
            priority_weight = self.config['priority_weights'].get(job.priority, 5)
            job_id_int = int(job.job_id.split('_')[-1])
            priority = -priority_weight * 1000 - job_id_int  # Negativo para PriorityQueue
            
            self.job_queue.put((priority, job))
            self.optimization_jobs[job.job_id] = job
            
            self.logger.log(f"Trabajo de optimización añadido: {job.name}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error añadiendo trabajo de optimización: {e}", level="ERROR")
    
    def _coordinate_optimization_strategies(self):
        """Coordinar estrategias de optimización"""
        try:
            # Determinar modo de orquestación
            if self.orchestration_mode == OrchestrationMode.ADAPTIVE:
                self._adapt_orchestration_mode()
            
            # Agrupar trabajos por compatibilidad
            compatible_groups = self._group_compatible_jobs()
            
            # Ejecutar grupos según modo de orquestación
            for group in compatible_groups:
                if self.orchestration_mode == OrchestrationMode.SEQUENTIAL:
                    self._execute_sequential(group)
                elif self.orchestration_mode == OrchestrationMode.PARALLEL:
                    self._execute_parallel(group)
                elif self.orchestration_mode == OrchestrationMode.COORDINATED:
                    self._execute_coordinated(group)
                elif self.orchestration_mode == OrchestrationMode.OPTIMIZED:
                    self._execute_optimized(group)
            
        except Exception as e:
            self.logger.log(f"Error coordinando estrategias: {e}", level="ERROR")
    
    def _group_compatible_jobs(self) -> List[List[OptimizationJob]]:
        """Agrupar trabajos compatibles"""
        try:
            groups = []
            available_jobs = list(self.optimization_jobs.values())
            
            while available_jobs:
                # Encontrar trabajo con mayor prioridad
                current_job = max(available_jobs, key=lambda j: self.config['priority_weights'].get(j.priority, 0))
                
                # Crear nuevo grupo
                group = [current_job]
                available_jobs.remove(current_job)
                
                # Encontrar trabajos compatibles
                for job in available_jobs[:]:
                    if self._are_jobs_compatible(current_job, job):
                        group.append(job)
                        available_jobs.remove(job)
                
                groups.append(group)
            
            return groups
            
        except Exception as e:
            self.logger.log(f"Error agrupando trabajos: {e}", level="ERROR")
            return []
    
    def _are_jobs_compatible(self, job1: OptimizationJob, job2: OptimizationJob) -> bool:
        """Verificar si dos trabajos son compatibles"""
        try:
            # Verificar conflicto de recursos
            resources1 = job1.resources_required
            resources2 = job2.resources_required
            
            for resource in resources1:
                if resource in resources2:
                    if resources1[resource] + resources2[resource] > 0.8:  # 80% de límite
                        return False
            
            # Verificar dependencias
            if job2.job_id in job1.dependencies or job1.job_id in job2.dependencies:
                return False
            
            # Verificar estrategias compatibles
            if job1.strategies[0] == OptimizationStrategy.CPU_OPTIMIZATION and job2.strategies[0] == OptimizationStrategy.CPU_OPTIMIZATION:
                return False  # Mismo tipo de optimización
            
            return True
            
        except Exception as e:
            self.logger.log(f"Error verificando compatibilidad: {e}", level="ERROR")
            return False
    
    def _execute_sequential(self, jobs: List[OptimizationJob]):
        """Ejecutar trabajos secuencialmente"""
        try:
            for job in jobs:
                self._execute_single_job(job)
        except Exception as e:
            self.logger.log(f"Error ejecutando trabajos secuenciales: {e}", level="ERROR")
    
    def _execute_parallel(self, jobs: List[OptimizationJob]):
        """Ejecutar trabajos en paralelo"""
        try:
            threads = []
            for job in jobs:
                thread = threading.Thread(target=self._execute_single_job, args=(job,))
                thread.daemon = True
                thread.start()
                threads.append(thread)
            
            # Esperar a que todos los hilos terminen
            for thread in threads:
                thread.join(timeout=self.config['job_timeout'])
                
        except Exception as e:
            self.logger.log(f"Error ejecutando trabajos en paralelo: {e}", level="ERROR")
    
    def _execute_coordinated(self, jobs: List[OptimizationJob]):
        """Ejecutar trabajos coordinados"""
        try:
            # Ejecutar con sincronización de recursos
            resource_locks = threading.Lock()
            
            for job in jobs:
                thread = threading.Thread(
                    target=self._execute_coordinated_job,
                    args=(job, resource_locks)
                )
                thread.daemon = True
                thread.start()
                
        except Exception as e:
            self.logger.log(f"Error ejecutando trabajos coordinados: {e}", level="ERROR")
    
    def _execute_optimized(self, jobs: List[OptimizationJob]):
        """Ejecutar trabajos optimizados"""
        try:
            # Ordenar trabajos por eficiencia esperada
            sorted_jobs = sorted(
                jobs,
                key=lambda j: self._calculate_job_efficiency(j),
                reverse=True
            )
            
            # Ejecutar los más eficientes primero
            for job in sorted_jobs:
                self._execute_single_job(job)
                
        except Exception as e:
            self.logger.log(f"Error ejecutando trabajos optimizados: {e}", level="ERROR")
    
    def _process_optimization_jobs(self):
        """Procesar trabajos de optimización"""
        try:
            while not self.job_queue.empty() and len([j for j in self.optimization_jobs.values() if j.status == "running"]) < self.config['max_concurrent_jobs']:
                _, job = self.job_queue.get()
                self._execute_single_job(job)
        except Exception as e:
            self.logger.log(f"Error procesando trabajos de optimización: {e}", level="ERROR")
    
    def _execute_single_job(self, job: OptimizationJob):
        """Ejecutar un trabajo de optimización individual"""
        try:
            self.logger.log(f"Iniciando ejecución de trabajo: {job.name}", level="INFO")
            
            job.status = "running"
            job.start_time = datetime.now()
            
            # Guardar métricas iniciales
            initial_metrics = self.performance_optimizer.current_metrics.__dict__.copy()
            
            # Ejecutar estrategias
            results = []
            for strategy in job.strategies:
                try:
                    # Ejecutar optimización
                    result = self._execute_strategy(strategy, job)
                    results.append(result)
                    
                except Exception as strategy_error:
                    self.logger.log(f"Error ejecutando estrategia {strategy.value}: {strategy_error}", level="ERROR")
                    results.append({'success': False, 'error': str(strategy_error)})
            
            # Evaluar resultados
            success = all(r.get('success', False) for r in results)
            improvement = self._calculate_job_improvement(initial_metrics, self.performance_optimizer.current_metrics.__dict__)
            
            # Actualizar estado del trabajo
            job.success = success
            job.status = "completed" if success else "failed"
            job.end_time = datetime.now()
            job.result = {
                'strategies_executed': len(results),
                'success_rate': sum(1 for r in results if r.get('success', False)) / len(results),
                'improvement': improvement,
                'results': results
            }
            
            # Registrar en historial
            self.optimization_history.append({
                'job_id': job.job_id,
                'name': job.name,
                'priority': job.priority.value,
                'success': success,
                'improvement': improvement,
                'duration': (job.end_time - job.start_time).total_seconds(),
                'timestamp': job.end_time.isoformat()
            })
            
            # Generar alerta
            if success and improvement > 10:
                self.analytics.set_alert(
                    title="Optimización Exitosa",
                    message=f"Trabajo '{job.name}' completado con éxito. Mejora: {improvement:.2f}%",
                    severity="success",
                    category="orchestration"
                )
            elif not success:
                self.analytics.set_alert(
                    title="Optimización Fallida",
                    message=f"Trabajo '{job.name}' fallido",
                    severity="error",
                    category="orchestration"
                )
            
            self.logger.log(f"Trabajo completado: {job.name}, Éxito: {success}, Mejora: {improvement:.2f}%", level="INFO")
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            self.logger.log(f"Error ejecutando trabajo {job.job_id}: {e}", level="ERROR")
    
    def _execute_coordinated_job(self, job: OptimizationJob, resource_locks: threading.Lock):
        """Ejecutar trabajo coordinado con control de recursos"""
        try:
            with resource_locks:
                self._execute_single_job(job)
        except Exception as e:
            self.logger.log(f"Error ejecutando trabajo coordinado: {e}", level="ERROR")
    
    def _execute_strategy(self, strategy: OptimizationStrategy, job: OptimizationJob) -> Dict[str, Any]:
        """Ejecutar una estrategia de optimización"""
        try:
            # Mapear estrategia a acción
            action_map = {
                OptimizationStrategy.CPU_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.MEMORY_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.DISK_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.NETWORK_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.PROCESS_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.CACHE_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.THREAD_POOL_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.ALGORITHM_OPTIMIZATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.RESOURCE_ALLOCATION: lambda: self.performance_optimizer.optimize_system(strategy),
                OptimizationStrategy.LOAD_BALANCING: lambda: self.performance_optimizer.optimize_system(strategy)
            }
            
            # Ejecutar acción
            action = action_map.get(strategy)
            if action:
                result = action()
                return {'success': True, 'result': result}
            else:
                return {'success': False, 'error': 'Strategy not implemented'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _calculate_job_efficiency(self, job: OptimizationJob) -> float:
        """Calcular eficiencia esperada de un trabajo"""
        try:
            # Basado en prioridad y recursos requeridos
            priority_weight = self.config['priority_weights'].get(job.priority, 5)
            resource_weight = sum(job.resources_required.values())
            
            # Calcular eficiencia
            efficiency = priority_weight / (1 + resource_weight)
            
            return efficiency
        except Exception as e:
            self.logger.log(f"Error calculando eficiencia: {e}", level="ERROR")
            return 0.0
    
    def _calculate_job_improvement(self, initial_metrics: Dict[str, float], final_metrics: Dict[str, float]) -> float:
        """Calcular mejora de un trabajo"""
        try:
            # Calcular puntuación de eficiencia antes y después
            initial_efficiency = initial_metrics.get('efficiency_score', 0)
            final_efficiency = final_metrics.get('efficiency_score', 0)
            
            if initial_efficiency == 0:
                return 0.0
            
            improvement = ((final_efficiency - initial_efficiency) / initial_efficiency) * 100
            return round(improvement, 2)
        except Exception as e:
            self.logger.log(f"Error calculando mejora: {e}", level="ERROR")
            return 0.0
    
    def _monitor_job_progress(self):
        """Monitorear progreso de trabajos"""
        try:
            # Verificar trabajos en ejecución
            for job_id, job in self.optimization_jobs.items():
                if job.status == "running":
                    # Verificar timeout
                    if job.start_time and (datetime.now() - job.start_time).total_seconds() > self.config['job_timeout']:
                        job.status = "failed"
                        job.error_message = "Job timeout"
                        self.logger.log(f"Trabajo {job_id} timeout", level="WARNING")
            
            # Limpiar trabajos completados
            completed_jobs = [job_id for job_id, job in self.optimization_jobs.items() 
                           if job.status in ["completed", "failed"]]
            
            for job_id in completed_jobs:
                del self.optimization_jobs[job_id]
            
        except Exception as e:
            self.logger.log(f"Error monitoreando progreso: {e}", level="ERROR")
    
    def _adapt_orchestration_mode(self):
        """Adaptar modo de orquestación según condiciones del sistema"""
        try:
            # Analizar carga del sistema
            system_load = self._calculate_resource_utilization()
            
            # Analizar tasa de éxito
            success_rate = self._calculate_success_rate()
            
            # Determinar modo óptimo
            if system_load > 0.9:
                self.orchestration_mode = OrchestrationMode.SEQUENTIAL
            elif success_rate < 0.5:
                self.orchestration_mode = OrchestrationMode.COORDINATED
            elif system_load > 0.7:
                self.orchestration_mode = OrchestrationMode.OPTIMIZED
            else:
                self.orchestration_mode = OrchestrationMode.PARALLEL
            
            self.logger.log(f"Modo de orquestación adaptado: {self.orchestration_mode.value}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error adaptando modo de orquestación: {e}", level="ERROR")
    
    def _optimize_orchestration_mode(self):
        """Optimizar modo de orquestación"""
        try:
            # Analizar rendimiento actual
            current_mode_performance = self._calculate_mode_performance(self.orchestration_mode)
            
            # Probar otros modos
            other_modes = [mode for mode in OrchestrationMode if mode != self.orchestration_mode]
            
            for mode in other_modes:
                mode_performance = self._calculate_mode_performance(mode)
                if mode_performance > current_mode_performance:
                    self.orchestration_mode = mode
                    self.logger.log(f"Modo de orquestación optimizado: {mode.value}", level="INFO")
                    break
                    
        except Exception as e:
            self.logger.log(f"Error optimizando modo de orquestación: {e}", level="ERROR")
    
    def _calculate_mode_performance(self, mode: OrchestrationMode) -> float:
        """Calcular rendimiento de un modo de orquestación"""
        try:
            # Basado en métricas del sistema
            efficiency_score = self.system_metrics.system_efficiency
            success_rate = self.system_metrics.optimization_success_rate
            resource_utilization = self.system_metrics.resource_utilization
            
            # Calcular puntuación del modo
            mode_score = (efficiency_score * 0.4 + success_rate * 0.4 + (1 - resource_utilization) * 0.2)
            
            return mode_score
        except Exception as e:
            self.logger.log(f"Error calculando rendimiento del modo: {e}", level="ERROR")
            return 0.0
    
    def get_orchestration_status(self) -> Dict[str, Any]:
        """Obtener estado de orquestación"""
        try:
            return {
                'is_running': self.is_running,
                'orchestration_mode': self.orchestration_mode.value,
                'orchestration_enabled': self.config['orchestration_enabled'],
                'auto_orchestration': self.config['auto_orchestration'],
                'system_metrics': self.system_metrics.__dict__,
                'resource_monitor': self.resource_monitor,
                'active_jobs': len([j for j in self.optimization_jobs.values() if j.status == "running"]),
                'pending_jobs': len([j for j in self.optimization_jobs.values() if j.status == "pending"]),
                'completed_jobs': len([j for j in self.optimization_jobs.values() if j.status == "completed"]),
                'failed_jobs': len([j for j in self.optimization_jobs.values() if j.status == "failed"]),
                'queue_size': self.job_queue.qsize(),
                'average_job_duration': self._calculate_average_job_duration(),
                'optimization_history_size': len(self.optimization_history)
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo estado de orquestación: {e}", level="ERROR")
            return {}
    
    def _calculate_average_job_duration(self) -> float:
        """Calcular duración promedio de trabajos"""
        try:
            if not self.optimization_history:
                return 0.0
            
            durations = [h.get('duration', 0) for h in self.optimization_history]
            return np.mean(durations)
        except Exception as e:
            self.logger.log(f"Error calculando duración promedio: {e}", level="ERROR")
            return 0.0
    
    def add_custom_optimization_job(self, job: OptimizationJob):
        """Añadir trabajo de optimización personalizado"""
        try:
            self._add_optimization_job(job)
            self.logger.log(f"Trabajo personalizado añadido: {job.name}", level="INFO")
        except Exception as e:
            self.logger.log(f"Error añadiendo trabajo personalizado: {e}", level="ERROR")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Obtener estado de un trabajo específico"""
        try:
            job = self.optimization_jobs.get(job_id)
            if job:
                return {
                    'job_id': job.job_id,
                    'name': job.name,
                    'description': job.description,
                    'priority': job.priority.value,
                    'status': job.status,
                    'start_time': job.start_time.isoformat() if job.start_time else None,
                    'end_time': job.end_time.isoformat() if job.end_time else None,
                    'success': job.success,
                    'error_message': job.error_message,
                    'result': job.result
                }
            return None
        except Exception as e:
            self.logger.log(f"Error obteniendo estado del trabajo: {e}", level="ERROR")
            return None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancelar un trabajo"""
        try:
            job = self.optimization_jobs.get(job_id)
            if job and job.status == "pending":
                job.status = "cancelled"
                del self.optimization_jobs[job_id]
                self.logger.log(f"Trabajo cancelado: {job.name}", level="INFO")
                return True
            return False
        except Exception as e:
            self.logger.log(f"Error cancelando trabajo: {e}", level="ERROR")
            return False
    
    def export_orchestration_report(self, filepath: str):
        """Exportar reporte de orquestación"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'orchestration_status': self.get_orchestration_status(),
                'system_metrics': self.system_metrics.__dict__,
                'resource_monitor': self.resource_monitor,
                'optimization_history': self.optimization_history[-100:],
                'active_jobs': [
                    {
                        'job_id': job.job_id,
                        'name': job.name,
                        'priority': job.priority.value,
                        'status': job.status,
                        'start_time': job.start_time.isoformat() if job.start_time else None
                    }
                    for job in self.optimization_jobs.values()
                ],
                'orchestration_mode': self.orchestration_mode.value,
                'performance_summary': {
                    'total_jobs': len(self.optimization_history),
                    'successful_jobs': len([h for h in self.optimization_history if h.get('success', False)]),
                    'failed_jobs': len([h for h in self.optimization_history if not h.get('success', False)]),
                    'average_improvement': np.mean([h.get('improvement', 0) for h in self.optimization_history]) if self.optimization_history else 0,
                    'total_improvement': sum(h.get('improvement', 0) for h in self.optimization_history)
                }
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log(f"Reporte de orquestación exportado a {filepath}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error exportando reporte de orquestación: {e}", level="ERROR")
    
    def stop_orchestration(self):
        """Detener orquestación"""
        try:
            self.is_running = False
            self.config['orchestration_enabled'] = False
            self.logger.log("Orquestación detenida", level="INFO")
        except Exception as e:
            self.logger.log(f"Error deteniendo orquestación: {e}", level="ERROR")
    
    def start_orchestration(self):
        """Iniciar orquestación"""
        try:
            self.config['orchestration_enabled'] = True
            self.is_running = True
            self.logger.log("Orquestación iniciada", level="INFO")
        except Exception as e:
            self.logger.log(f"Error iniciando orquestación: {e}", level="ERROR")
    
    def __del__(self):
        """Destructor"""
        try:
            self.is_running = False
            if hasattr(self, 'orchestration_thread'):
                self.orchestration_thread.join(timeout=5)
        except Exception as e:
            self.logger.log(f"Error en destructor: {e}", level="ERROR")