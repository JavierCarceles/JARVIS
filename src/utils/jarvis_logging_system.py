"""
Sistema de logging avanzado y análisis de patrones para JARVIS.
Integración completa con capacidades predictivas y dashboard interactivo.
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import defaultdict, deque

import numpy as np

from .advanced_logger import AdvancedLogger, LogLevel, LogCategory, LogEntry
from .log_predictor import LogPredictor, PredictionType

# Dashboard import opcional
try:
    from .log_dashboard import LogDashboard
    DASH_AVAILABLE = True
except ImportError:
    LogDashboard = None
    DASH_AVAILABLE = False


class JarvisLoggingSystem:
    """Sistema unificado de logging avanzado para JARVIS."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()
        self.db_path = Path(self.config.get('db_path', 'logs/jarvis_logs.db'))
        self.log_dir = Path(self.config.get('log_dir', 'logs'))
        self.model_dir = Path(self.config.get('model_dir', 'models/predictive_logs'))
        
        # Crear directorios
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        # Inicializar componentes
        self.predictor = self._create_predictor()
        self.logger = self._create_logger()
        self.alert_manager = None
        self.dashboard = self._create_dashboard()
        
        # Estado del sistema
        self.is_running = False
        self.training_thread = None
        self.prediction_interval = 300  # 5 minutos
        
        # Eventos y callbacks
        self.event_callbacks = defaultdict(list)
        
    def _default_config(self) -> Dict[str, Any]:
        """Configuración por defecto del sistema de logging."""
        return {
            'db_path': 'logs/jarvis_logs.db',
            'log_dir': 'logs',
            'model_dir': 'models/predictive_logs',
            'log_level': 'INFO',
            'enable_predictions': True,
            'enable_dashboard': True,
            'dashboard_port': 8050,
            'dashboard_host': '127.0.0.1',
            'prediction_interval': 300,  # segundos
            'training_interval': 86400,  # 24 horas
            'alert_cooldown': 1800,  # 30 minutos
            'max_log_retention': 30,  # días
            'enable_auto_training': True,
            'prediction_thresholds': {
                'error_probability': 0.7,
                'anomaly_severity': 'medium',
                'performance_degradation': 0.2
            }
        }
    
    def _create_logger(self) -> AdvancedLogger:
        """Crear logger avanzado."""
        logger = AdvancedLogger(
            name="Jarvis",
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            log_dir=str(self.log_dir),
            db_path=str(self.db_path)
        )
        # Conectar el predictor con el logger
        logger.predictor = self.predictor
        return logger
    
    def _create_predictor(self) -> LogPredictor:
        """Crear sistema predictivo."""
        return LogPredictor(
            db_path=str(self.db_path)
        )
    
    def _create_alert_manager(self) -> None:
        """Crear gestor de alertas."""
        # AlertManager no implementado, usar el predictor directamente
        pass
    
    def _create_dashboard(self) -> Optional[LogDashboard]:
        """Crear dashboard interactivo."""
        if not self.config.get('enable_dashboard', True) or not DASH_AVAILABLE:
            return None
        
        return LogDashboard(
            db_path=str(self.db_path),
            port=self.config.get('dashboard_port', 8050),
            host=self.config.get('dashboard_host', '127.0.0.1')
        )
    
    def start(self) -> None:
        """Iniciar el sistema de logging avanzado."""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Iniciar logger
        self.logger.info("Starting advanced logging system", category=LogCategory.SYSTEM)
        
        # Entrenar modelos predictivos
        if self.config.get('enable_predictions', True):
            self.logger.info("Training predictive models", category=LogCategory.SYSTEM)
            # El entrenamiento se realiza automáticamente al agregar datos
            self.logger.info("Training completed: automatic training on data ingestion", category=LogCategory.SYSTEM)
        
        # Iniciar hilo de predicciones automáticas
        if self.config.get('enable_predictions', True):
            self.training_thread = threading.Thread(target=self._prediction_worker, daemon=True)
            self.training_thread.start()
        
        # Iniciar dashboard
        if self.dashboard:
            dashboard_thread = threading.Thread(target=self._dashboard_worker, daemon=True)
            dashboard_thread.start()
        
        # Limpiar logs antiguos
        self._cleanup_old_logs()
        
        self.logger.info("Advanced logging system started successfully", category=LogCategory.SYSTEM)
    
    def stop(self) -> None:
        """Detener el sistema de logging avanzado."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Detener logger
        self.logger.info("Stopping advanced logging system", category=LogCategory.SYSTEM)
        self.logger.shutdown()
        
        # Esperar a que los hilos terminen
        if self.training_thread and self.training_thread.is_alive():
            self.training_thread.join(timeout=5)
        
        self.logger.info("Advanced logging system stopped", category=LogCategory.SYSTEM)
    
    def _prediction_worker(self) -> None:
        """Worker para predicciones automáticas."""
        while self.is_running:
            try:
                # Realizar predicciones periódicas
                self._perform_periodic_predictions()
                
                # Reentrenar modelos si es necesario
                if self.config.get('enable_auto_training', True):
                    self._check_and_retrain()
                
                # Esperar intervalo
                time.sleep(self.config.get('prediction_interval', 300))
                
            except Exception as e:
                self.logger.error(f"Error in prediction worker: {e}", category=LogCategory.SYSTEM)
                time.sleep(60)  # Esperar antes de reintentar
    
    def _dashboard_worker(self) -> None:
        """Worker para dashboard."""
        if not self.dashboard:
            return
        
        try:
            self.dashboard.start()
        except Exception as e:
            self.logger.error(f"Dashboard error: {e}", category=LogCategory.SYSTEM)
    
    def _perform_periodic_predictions(self) -> None:
        """Realizar predicciones periódicas."""
        try:
            # Extraer características de logs recientes
            recent_logs = self._extract_recent_features()
            
            if recent_logs is not None:
                # Asegurarse de que recent_logs es una lista/array válido
                if isinstance(recent_logs, list) and len(recent_logs) > 0:
                    # Generar predicciones
                    predictions = self.predictor.generate_predictions(recent_logs)
                elif isinstance(recent_logs, np.ndarray) and recent_logs.size > 0:
                    # Generar predicciones desde numpy array
                    predictions = self.predictor.generate_predictions([recent_logs])
                    
                    # Agregar resultado al historial
                    if predictions:
                        self.predictor.add_prediction_result(predictions)
                    
                    # Verificar alertas solo si el predictor existe
                    if hasattr(self, 'alert_manager') and self.alert_manager:
                        alerts = self.alert_manager.check_predictions(predictions)
                    else:
                        alerts = []
                    
                    # Procesar alertas
                    for alert in alerts:
                        self._process_alert(alert)
                    
                    # Disparar eventos
                    self._trigger_event('predictions_completed', predictions)
                    
                    self.logger.debug("Periodic predictions completed", category=LogCategory.SYSTEM)
                else:
                    self.logger.debug("No valid recent logs for predictions", category=LogCategory.SYSTEM)
            else:
                self.logger.debug("No recent logs available for predictions", category=LogCategory.SYSTEM)
                
        except Exception as e:
            self.logger.error(f"Error in periodic predictions: {e}", category=LogCategory.SYSTEM)
    
    def _extract_recent_features(self) -> np.ndarray:
        """Extraer características de logs recientes."""
        # Obtener logs de la última hora
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT timestamp, level, category, module
                    FROM logs 
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                ''', (cutoff_time.isoformat(),))
                
                rows = cursor.fetchall()
                
                if not rows:
                    return None
                
                # Procesar características
                features = []
                for row in rows:
                    timestamp = datetime.fromisoformat(row[0])
                    level = row[1]
                    category = row[2]
                    module = row[3]
                    
                    feature_vector = [
                        timestamp.hour,
                        timestamp.weekday(),
                        timestamp.minute,
                        1 if level in ['ERROR', 'CRITICAL'] else 0,
                        1 if level == 'WARNING' else 0,
                        1 if level == 'INFO' else 0,
                        hash(category) % 100,  # Categoría como hash
                        hash(module) % 100,    # Módulo como hash
                    ]
                    features.append(feature_vector)
                
                # Usar promedio de características
                if features:
                    return np.array([np.mean(features, axis=0)])
                else:
                    # Si no hay características, devolver array vacío o None
                    return None
                
        except Exception as e:
            self.logger.error(f"Error extracting features: {e}", category=LogCategory.SYSTEM)
            return None
    
    def _check_and_retrain(self) -> None:
        """Verificar si es necesario reentrenar modelos."""
        last_training = self.predictor.last_training
        
        if not last_training:
            return
        
        # Verificar si ha pasado suficiente tiempo desde el último entrenamiento
        time_since_training = datetime.now() - last_training
        training_interval = timedelta(seconds=self.config.get('training_interval', 86400))
        
        if time_since_training > training_interval:
            self.logger.info("Retraining predictive models", category=LogCategory.SYSTEM)
            training_results = self.predictor.train_models()
            self.logger.info(f"Retraining completed: {training_results}", category=LogCategory.SYSTEM)
    
    def _cleanup_old_logs(self) -> None:
        """Limpiar logs antiguos."""
        try:
            retention_days = self.config.get('max_log_retention', 30)
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM logs 
                    WHERE timestamp < ?
                ''', (cutoff_time.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} old log entries", category=LogCategory.SYSTEM)
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old logs: {e}", category=LogCategory.SYSTEM)
    
    def _process_alert(self, alert: Dict[str, Any]) -> None:
        """Procesar alerta generada."""
        # Loggear alerta
        self.logger.warning(f"Alert generated: {alert['message']}", category=LogCategory.SYSTEM)
        
        # Disparar evento de alerta
        self._trigger_event('alert_generated', alert)
        
        # Guardar alerta en base de datos (si no existe)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alerts (timestamp, type, severity, message, data)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    alert['type'],
                    alert['severity'],
                    alert['message'],
                    json.dumps(alert)
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error saving alert: {e}", category=LogCategory.SYSTEM)
    
    def _trigger_event(self, event_type: str, data: Any) -> None:
        """Disparar evento a callbacks registrados."""
        callbacks = self.event_callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Error in event callback: {e}", category=LogCategory.SYSTEM)
    
    def register_event_callback(self, event_type: str, callback) -> None:
        """Registrar callback para evento específico."""
        self.event_callbacks[event_type].append(callback)
    
    def log(self, message: str, level: LogLevel = LogLevel.INFO, 
            category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
        """Método principal de logging."""
        self.logger.log(level, category, message, **kwargs)
    
    def log_error(self, message: str, **kwargs) -> None:
        """Loggear error."""
        self.log(message, LogLevel.ERROR, LogCategory.ERROR, **kwargs)
    
    def log_warning(self, message: str, **kwargs) -> None:
        """Loggear warning."""
        self.log(message, LogLevel.WARNING, LogCategory.SYSTEM, **kwargs)
    
    def log_info(self, message: str, **kwargs) -> None:
        """Loggear info."""
        self.log(message, LogLevel.INFO, LogCategory.SYSTEM, **kwargs)
    
    def log_debug(self, message: str, **kwargs) -> None:
        """Loggear debug."""
        self.log(message, LogLevel.DEBUG, LogCategory.DEBUG, **kwargs)
    
    def log_performance(self, message: str, **kwargs) -> None:
        """Loggear métrica de rendimiento."""
        self.log(message, LogLevel.PERFORMANCE, LogCategory.PERFORMANCE, **kwargs)
    
    def log_with_trace(self, message: str, trace_id: str = None, **kwargs) -> None:
        """Loggear con trace ID."""
        self.logger.log_with_trace(message, trace_id=trace_id, **kwargs)
    
    def log_with_span(self, message: str, span_id: str = None, 
                     parent_span_id: str = None, **kwargs) -> None:
        """Loggear con span ID."""
        self.logger.log_with_span(message, span_id=span_id, 
                                parent_span_id=parent_span_id, **kwargs)
    
    def get_logs(self, start_time: datetime = None, end_time: datetime = None,
                 level: LogLevel = None, category: LogCategory = None,
                 module: str = None, limit: int = 100) -> List[LogEntry]:
        """Obtener logs desde la base de datos."""
        return self.logger.query_logs(start_time, end_time, level, category, module, limit)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas del sistema de logging."""
        return {
            'logger_stats': self.logger.get_statistics(),
            'predictor_stats': self.predictor.get_prediction_insights(),
            'alert_stats': self.alert_manager.get_alert_statistics(),
            'system_status': 'running' if self.is_running else 'stopped'
        }
    
    def get_predictions(self) -> Dict[str, Any]:
        """Obtener predicciones actuales."""
        return self.predictor.generate_predictions(self._extract_recent_features())
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """Obtener alertas activas."""
        return self.alert_manager.get_active_alerts()
    
    def acknowledge_alert(self, alert_id: str) -> None:
        """Reconocer alerta."""
        self.alert_manager.acknowledge_alert(alert_id)
    
    def resolve_alert(self, alert_id: str) -> None:
        """Resolver alerta."""
        self.alert_manager.resolve_alert(alert_id)
    
    def export_logs(self, start_time: datetime = None, end_time: datetime = None,
                   format: str = 'json') -> str:
        """Exportar logs."""
        return self.logger.export_logs(start_time, end_time, format)
    
    def export_predictions(self, format: str = 'json') -> str:
        """Exportar datos de predicción."""
        return self.predictor.export_prediction_data(format)
    
    def get_dashboard_url(self) -> Optional[str]:
        """Obtener URL del dashboard."""
        return self.dashboard.get_dashboard_url() if self.dashboard else None
    
    def train_models(self) -> Dict[str, Any]:
        """Entrenar modelos predictivos manualmente."""
        return self.predictor.train_models()
    
    def analyze_trends(self, days: int = 7) -> Dict[str, Any]:
        """Analizar tendencias."""
        return self.predictor.analyze_trends(days)
    
    def get_patterns(self, acknowledged: bool = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener patrones detectados."""
        return self.logger.get_patterns(acknowledged, limit)


# Instancia global del sistema de logging
jarvis_logging_system = JarvisLoggingSystem()


# Funciones de conveniencia para compatibilidad
def get_jarvis_logger() -> JarvisLoggingSystem:
    """Obtener instancia del sistema de logging de JARVIS."""
    return jarvis_logging_system


def log_jarvis(message: str, level: LogLevel = LogLevel.INFO, 
               category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
    """Loggear mensaje en el sistema de logging de JARVIS."""
    jarvis_logging_system.log(message, level, category, **kwargs)


def log_jarvis_error(message: str, **kwargs) -> None:
    """Loggear error en el sistema de logging de JARVIS."""
    jarvis_logging_system.log_error(message, **kwargs)


def log_jarvis_warning(message: str, **kwargs) -> None:
    """Loggear warning en el sistema de logging de JARVIS."""
    jarvis_logging_system.log_warning(message, **kwargs)


def log_jarvis_info(message: str, **kwargs) -> None:
    """Loggear info en el sistema de logging de JARVIS."""
    jarvis_logging_system.log_info(message, **kwargs)


def log_jarvis_performance(message: str, **kwargs) -> None:
    """Loggear métrica de rendimiento en el sistema de logging de JARVIS."""
    jarvis_logging_system.log_performance(message, **kwargs)