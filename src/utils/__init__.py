"""
Utils Package v2.7.0 - Sistema de optimización y automejora
Sistema completo de optimización con inteligencia artificial y aprendizaje automático
"""

from .advanced_logger import AdvancedLogger
from .performance_optimizer import PerformanceOptimizer, OptimizationStrategy, OptimizationLevel, OptimizationMetrics, OptimizationAction
from .self_improvement_system import SelfImprovementSystem, LearningMode, ImprovementType, LearningSession, ImprovementRule, KnowledgeGraph
from .adaptive_learning_engine import AdaptiveLearningEngine, LearningTask, NeuralArchitecture, LearningTaskConfig, ModelPerformance
from .optimization_orchestrator import OptimizationOrchestrator, OrchestrationMode, OptimizationPriority, OptimizationJob, OrchestrationMetrics
from .pattern_analyzer import PatternAnalyzer
from .log_analytics import LogAnalytics
from .log_predictor import LogPredictor
from .log_dashboard import LogDashboard
from .performance_monitor import PerformanceMonitor
from .log_integration import LogIntegrator

__version__ = "2.7.0"
__author__ = "JARVIS AI System"
__description__ = "Sistema avanzado de optimización y automejora con inteligencia artificial"

# Componentes principales del sistema de optimización v2.7.0
__all__ = [
    # Core Optimization Components
    'PerformanceOptimizer',
    'SelfImprovementSystem', 
    'AdaptiveLearningEngine',
    'OptimizationOrchestrator',
    
    # Supporting Components
    'AdvancedLogger',
    'PatternAnalyzer',
    'LogAnalytics',
    'LogPredictor',
    'LogDashboard',
    'PerformanceMonitor',
    'LogIntegrator',
    
    # Enums and Data Classes
    'OptimizationStrategy',
    'OptimizationLevel',
    'OptimizationMetrics',
    'OptimizationAction',
    'LearningMode',
    'ImprovementType',
    'LearningSession',
    'ImprovementRule',
    'KnowledgeGraph',
    'LearningTask',
    'NeuralArchitecture',
    'LearningTaskConfig',
    'ModelPerformance',
    'OrchestrationMode',
    'OptimizationPriority',
    'OptimizationJob',
    'OrchestrationMetrics'
]

# Sistema de optimización completo v2.7.0
class OptimizationSystem:
    """
    Sistema completo de optimización y automejora
    Integración de todos los componentes para un sistema de optimización inteligente
    """
    
    def __init__(self, config_path: str = None):
        """
        Inicializar el sistema de optimización completo
        
        Args:
            config_path: Ruta al archivo de configuración
        """
        # Inicializar componentes principales
        self.logger = AdvancedLogger("OptimizationSystem")
        self.performance_optimizer = PerformanceOptimizer(config_path)
        self.self_improvement_system = SelfImprovementSystem(config_path)
        self.adaptive_learning_engine = AdaptiveLearningEngine(config_path)
        self.optimization_orchestrator = OptimizationOrchestrator(config_path)
        
        # Componentes de soporte
        self.pattern_analyzer = PatternAnalyzer()
        self.analytics = LogAnalytics()
        self.log_predictor = LogPredictor()
        self.log_dashboard = LogDashboard()
        self.performance_monitor = PerformanceMonitor()
        self.log_integration = LogIntegrator()
        
        self.logger.log("Sistema de optimización completo v2.7.0 inicializado", level="INFO")
    
    def get_system_status(self) -> dict:
        """
        Obtener estado completo del sistema de optimización
        
        Returns:
            dict: Estado completo del sistema
        """
        try:
            return {
                'system_version': __version__,
                'timestamp': str(self.performance_optimizer.current_metrics.timestamp),
                'performance_optimizer': self.performance_optimizer.get_optimization_status(),
                'self_improvement_system': self.self_improvement_system.get_learning_status(),
                'adaptive_learning_engine': self.adaptive_learning_engine.get_learning_engine_status(),
                'optimization_orchestrator': self.optimization_orchestrator.get_orchestration_status(),
                'pattern_analyzer': self.pattern_analyzer.get_pattern_analysis(),
                'analytics_summary': self.analytics.get_analytics_summary(),
                'overall_efficiency': self.performance_optimizer.current_metrics.efficiency_score,
                'optimization_gain': self.performance_optimizer.current_metrics.optimization_gain,
                'system_health': self._calculate_system_health()
            }
        except Exception as e:
            self.logger.log(f"Error obteniendo estado del sistema: {e}", level="ERROR")
            return {}
    
    def _calculate_system_health(self) -> float:
        """Calcular salud general del sistema"""
        try:
            # Basado en métricas clave
            efficiency = self.performance_optimizer.current_metrics.efficiency_score
            success_rate = self.optimization_orchestrator._calculate_success_rate()
            resource_utilization = self.optimization_orchestrator._calculate_resource_utilization()
            
            # Calcular salud (0-100)
            health = (efficiency * 0.4 + success_rate * 0.4 + (1 - resource_utilization) * 0.2) * 100
            return round(health, 2)
        except Exception as e:
            self.logger.log(f"Error calculando salud del sistema: {e}", level="ERROR")
            return 0.0
    
    def optimize_system(self, strategy: OptimizationStrategy, level: OptimizationLevel = OptimizationLevel.MODERATE) -> dict:
        """
        Optimizar el sistema manualmente
        
        Args:
            strategy: Estrategia de optimización
            level: Nivel de optimización
            
        Returns:
            dict: Resultado de la optimización
        """
        try:
            # Coordinar optimización a través del orquestador
            job = self.optimization_orchestrator.optimization_orchestrator._create_optimization_job(
                name=f"Manual Optimization: {strategy.value}",
                strategy=strategy,
                level=level
            )
            
            self.optimization_orchestrator.add_custom_optimization_job(job)
            
            return {
                'success': True,
                'job_id': job.job_id,
                'message': f"Optimización manual iniciada: {strategy.value}",
                'estimated_duration': job.estimated_duration
            }
            
        except Exception as e:
            self.logger.log(f"Error optimizando sistema manualmente: {e}", level="ERROR")
            return {'success': False, 'error': str(e)}
    
    def start_auto_optimization(self):
        """Iniciar optimización automática"""
        try:
            self.performance_optimizer.start_optimization()
            self.self_improvement_system.start_learning()
            self.adaptive_learning_engine.start_learning_engine()
            self.optimization_orchestrator.start_orchestration()
            
            self.logger.log("Optimización automática iniciada", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error iniciando optimización automática: {e}", level="ERROR")
    
    def stop_auto_optimization(self):
        """Detener optimización automática"""
        try:
            self.performance_optimizer.stop_optimization()
            self.self_improvement_system.stop_learning()
            self.adaptive_learning_engine.stop_learning_engine()
            self.optimization_orchestrator.stop_orchestration()
            
            self.logger.log("Optimización automática detenida", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error deteniendo optimización automática: {e}", level="ERROR")
    
    def export_system_report(self, filepath: str):
        """
        Exportar reporte completo del sistema
        
        Args:
            filepath: Ruta del archivo de reporte
        """
        try:
            report = {
                'system_info': {
                    'version': __version__,
                    'timestamp': str(datetime.now()),
                    'components': {
                        'performance_optimizer': 'Advanced performance optimization with ML',
                        'self_improvement_system': 'Continuous learning and improvement',
                        'adaptive_learning_engine': 'Deep learning and hyperparameter optimization',
                        'optimization_orchestrator': 'Coordination of all optimization strategies'
                    }
                },
                'system_status': self.get_system_status(),
                'performance_optimizer_report': self.performance_optimizer.get_optimization_history(),
                'self_improvement_report': self.self_improvement_system.get_learning_history(),
                'adaptive_learning_report': self.adaptive_learning_engine.performance_history,
                'orchestration_report': self.optimization_orchestrator.optimization_history,
                'pattern_analysis': self.pattern_analyzer.get_pattern_analysis(),
                'analytics_summary': self.analytics.get_analytics_summary(),
                'predictions': self.log_predictor.get_predictions(),
                'recommendations': self.optimization_orchestrator.get_optimization_recommendations()
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log(f"Reporte completo del sistema exportado a {filepath}", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error exportando reporte completo: {e}", level="ERROR")
    
    def get_optimization_recommendations(self) -> list:
        """
        Obtener recomendaciones de optimización del sistema
        
        Returns:
            list: Lista de recomendaciones
        """
        try:
            recommendations = []
            
            # Recomendaciones del orquestador
            orchestrator_recs = self.optimization_orchestrator.get_optimization_recommendations()
            recommendations.extend(orchestrator_recs)
            
            # Recomendaciones del sistema de automejora
            improvement_recs = self.self_improvement_system.get_optimization_recommendations()
            recommendations.extend(improvement_recs)
            
            # Recomendaciones del optimizador de rendimiento
            performance_recs = self.performance_optimizer.get_optimization_recommendations()
            recommendations.extend(performance_recs)
            
            # Eliminar duplicados y ordenar
            unique_recs = []
            seen = set()
            
            for rec in recommendations:
                rec_key = (rec.get('type'), rec.get('priority'))
                if rec_key not in seen:
                    seen.add(rec_key)
                    unique_recs.append(rec)
            
            return sorted(unique_recs, key=lambda x: x.get('priority', 'medium'), reverse=True)
            
        except Exception as e:
            self.logger.log(f"Error obteniendo recomendaciones: {e}", level="ERROR")
            return []
    
    def emergency_optimization(self):
        """Optimización de emergencia para situaciones críticas"""
        try:
            self.logger.log("Iniciando optimización de emergencia", level="WARNING")
            
            # Detener todas las optimizaciones regulares
            self.stop_auto_optimization()
            
            # Ejecutar optimizaciones críticas
            critical_strategies = [
                OptimizationStrategy.CPU_OPTIMIZATION,
                OptimizationStrategy.MEMORY_OPTIMIZATION,
                OptimizationStrategy.PROCESS_OPTIMIZATION
            ]
            
            for strategy in critical_strategies:
                try:
                    self.performance_optimizer.optimize_system(strategy, OptimizationLevel.CRITICAL)
                    time.sleep(10)  # Esperar entre optimizaciones
                except Exception as e:
                    self.logger.log(f"Error en optimización crítica {strategy.value}: {e}", level="ERROR")
            
            # Reiniciar sistema normal
            self.start_auto_optimization()
            
            self.logger.log("Optimización de emergencia completada", level="INFO")
            
        except Exception as e:
            self.logger.log(f"Error en optimización de emergencia: {e}", level="ERROR")
    
    def __del__(self):
        """Destructor"""
        try:
            self.stop_auto_optimization()
            self.logger.log("Sistema de optimización finalizado", level="INFO")
        except Exception as e:
            self.logger.log(f"Error en destructor: {e}", level="ERROR")

# Instancia global del sistema de optimización
optimization_system = OptimizationSystem()

# Funciones de conveniencia
def get_system_status() -> dict:
    """Obtener estado del sistema de optimización"""
    return optimization_system.get_system_status()

def optimize_system(strategy: OptimizationStrategy, level: OptimizationLevel = OptimizationLevel.MODERATE) -> dict:
    """Optimizar el sistema"""
    return optimization_system.optimize_system(strategy, level)

def start_auto_optimization():
    """Iniciar optimización automática"""
    optimization_system.start_auto_optimization()

def stop_auto_optimization():
    """Detener optimización automática"""
    optimization_system.stop_auto_optimization()

def get_optimization_recommendations() -> list:
    """Obtener recomendaciones de optimización"""
    return optimization_system.get_optimization_recommendations()

def emergency_optimization():
    """Optimización de emergencia"""
    optimization_system.emergency_optimization()

# Importaciones necesarias
import json
import datetime
import time