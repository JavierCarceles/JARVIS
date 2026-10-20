"""
Sistema avanzado de logging y análisis de patrones para Jarvis.
Integración con sistema de logging existente y capacidades predictivas.
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import queue
from contextlib import contextmanager
import asyncio
from functools import wraps


class LogLevel(Enum):
    """Niveles de log extendidos."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    SUCCESS = logging.INFO + 5  # Nivel personalizado
    PERFORMANCE = logging.INFO + 10  # Nivel personalizado para métricas


class LogCategory(Enum):
    """Categorías de logs para análisis."""
    SYSTEM = "system"
    APPLICATION = "application"
    NETWORK = "network"
    PERFORMANCE = "performance"
    SECURITY = "security"
    BUSINESS = "business"
    DEBUG = "debug"
    ERROR = "error"


class PatternType(Enum):
    """Tipos de patrones detectables."""
    ERROR_SPIKE = "error_spike"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    ANOMALY = "anomaly"
    TREND = "trend"
    CYCLE = "cycle"
    CORRELATION = "correlation"


@dataclass
class LogEntry:
    """Estructura de entrada de log enriquecida."""
    timestamp: datetime
    level: LogLevel
    category: LogCategory
    message: str
    module: str
    function: str
    line: int
    thread_id: str
    process_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    tags: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    exception: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para almacenamiento."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogEntry':
        """Crear desde diccionario."""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class LogAnalyzer:
    """Analizador de logs avanzado con machine learning y detección de patrones complejos."""
    
    def __init__(self, window_size: int = 1000, pattern_threshold: float = 0.8, 
                 ml_enabled: bool = True, anomaly_detection: bool = True):
        self.window_size = window_size
        self.pattern_threshold = pattern_threshold
        self.ml_enabled = ml_enabled
        self.anomaly_detection = anomaly_detection
        self.log_buffer = deque(maxlen=window_size)
        self.error_counts = defaultdict(int)
        self.performance_metrics = defaultdict(list)
        self.patterns = {}
        self.ml_model = None
        self.anomaly_detector = None
        self.lock = threading.Lock()
        self._initialize_ml_models()
        
    def _initialize_ml_models(self) -> None:
        """Inicializar modelos de machine learning para análisis avanzado."""
        if self.ml_enabled:
            try:
                # Simple anomaly detection using statistical methods
                self.anomaly_detector = StatisticalAnomalyDetector()
                self.ml_model = PatternRecognizer()
            except ImportError:
                # Fallback to simple pattern detection
                self.ml_enabled = False
                
    def analyze_log_entry(self, entry: LogEntry) -> List[Dict[str, Any]]:
        """Analizar una entrada de log y detectar patrones con ML."""
        patterns_detected = []
        
        with self.lock:
            self.log_buffer.append(entry)
            
            # Contar errores
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                self.error_counts[entry.category] += 1
                
            # Recopilar métricas de rendimiento
            if entry.category == LogCategory.PERFORMANCE:
                self._collect_performance_metrics(entry)
                
            # Detectar patrones con ML
            if self.ml_enabled:
                patterns_detected = self._detect_patterns_with_ml()
            else:
                patterns_detected = self._detect_patterns()
                
            # Detección de anomalías
            if self.anomaly_detection:
                anomaly_patterns = self._detect_advanced_anomalies()
                patterns_detected.extend(anomaly_patterns)
            
        return patterns_detected
    
    def _collect_performance_metrics(self, entry: LogEntry) -> None:
        """Recopilar métricas de rendimiento."""
        # Extraer tiempo de respuesta del mensaje
        time_match = re.search(r'time=(\d+(?:\.\d+)?)', entry.message)
        if time_match:
            response_time = float(time_match.group(1))
            self.performance_metrics[f"{entry.module}_response_time"].append(response_time)
            
        # Extrafer tasa de éxito
        success_match = re.search(r'success_rate=(\d+(?:\.\d+)?)', entry.message)
        if success_match:
            success_rate = float(success_match.group(1))
            self.performance_metrics[f"{entry.module}_success_rate"].append(success_rate)
    
    def _detect_patterns(self) -> List[Dict[str, Any]]:
        """Detectar patrones básicos en los logs."""
        patterns = []
        
        # Detección de picos de errores
        error_spike = self._detect_error_spike()
        if error_spike:
            patterns.append(error_spike)
            
        # Detección de degradación de rendimiento
        performance_degradation = self._detect_performance_degradation()
        if performance_degradation:
            patterns.append(performance_degradation)
            
        # Detección de anomalías
        anomaly = self._detect_anomaly()
        if anomaly:
            patterns.append(anomaly)
            
        return patterns
    
    def _detect_patterns_with_ml(self) -> List[Dict[str, Any]]:
        """Detectar patrones con machine learning y análisis avanzado."""
        patterns = []
        
        # Detección de picos de errores con ML
        error_spike = self._detect_error_spike_ml()
        if error_spike:
            patterns.append(error_spike)
            
        # Detección de degradación de rendimiento con ML
        performance_degradation = self._detect_performance_degradation_ml()
        if performance_degradation:
            patterns.append(performance_degradation)
            
        # Detección de anomalías con ML
        anomaly = self._detect_anomaly_ml()
        if anomaly:
            patterns.append(anomaly)
            
        # Detección de patrones secuenciales
        sequential_patterns = self._detect_sequential_patterns()
        patterns.extend(sequential_patterns)
        
        # Detección de correlaciones
        correlation_patterns = self._detect_correlations()
        patterns.extend(correlation_patterns)
        
        return patterns
    
    def _detect_error_spike(self) -> Optional[Dict[str, Any]]:
        """Detectar picos de errores."""
        if len(self.log_buffer) < 100:
            return None
            
        recent_errors = sum(1 for entry in list(self.log_buffer)[-100:] 
                           if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL])
        
        if recent_errors > 20:  # Umbral de 20% de errores
            return {
                'type': PatternType.ERROR_SPIKE.value,
                'severity': 'high',
                'description': f'Detección de pico de errores: {recent_errors} errores en últimas 100 entradas',
                'timestamp': datetime.now().isoformat(),
                'error_count': recent_errors,
                'window_size': 100
            }
        return None
    
    def _detect_performance_degradation(self) -> Optional[Dict[str, Any]]:
        """Detectar degradación de rendimiento."""
        if not self.performance_metrics:
            return None
            
        degradation_found = []
        for metric_name, values in self.performance_metrics.items():
            if len(values) >= 10:
                recent_avg = sum(values[-10:]) / 10
                older_avg = sum(values[-20:-10]) / 10 if len(values) >= 20 else recent_avg
                
                if recent_avg > older_avg * 1.5:  # 50% de aumento
                    degradation_found.append({
                        'metric': metric_name,
                        'recent_avg': recent_avg,
                        'older_avg': older_avg,
                        'degradation_percent': ((recent_avg - older_avg) / older_avg) * 100
                    })
        
        if degradation_found:
            return {
                'type': PatternType.PERFORMANCE_DEGRADATION.value,
                'severity': 'medium',
                'description': f'Detección de degradación de rendimiento en {len(degradation_found)} métricas',
                'timestamp': datetime.now().isoformat(),
                'degradations': degradation_found
            }
        return None
    
    def _detect_anomaly(self) -> Optional[Dict[str, Any]]:
        """Detectar anomalías básicas en los logs."""
        if len(self.log_buffer) < 50:
            return None
            
        # Contar frecuencia de diferentes categorías
        category_counts = defaultdict(int)
        for entry in list(self.log_buffer)[-50:]:
            category_counts[entry.category] += 1
            
        # Detectar categorías inusualmente frecuentes
        total = sum(category_counts.values())
        anomalies = []
        
        for category, count in category_counts.items():
            frequency = count / total
            if frequency > 0.6:  # Una categoría domina más del 60%
                anomalies.append({
                    'category': category,
                    'frequency': frequency,
                    'count': count
                })
        
        if anomalies:
            return {
                'type': PatternType.ANOMALY.value,
                'severity': 'medium',
                'description': f'Detección de anomalías: {len(anomalies)} categorías dominantes',
                'timestamp': datetime.now().isoformat(),
                'anomalies': anomalies
            }
        return None
    
    def _detect_error_spike_ml(self) -> Optional[Dict[str, Any]]:
        """Detectar picos de errores con ML."""
        if len(self.log_buffer) < 100:
            return None
            
        # Usar detector de anomalías estadístico
        recent_errors = []
        for entry in list(self.log_buffer)[-100:]:
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                recent_errors.append(1)
            else:
                recent_errors.append(0)
        
        # Calcular tasa de error
        error_rate = sum(recent_errors) / len(recent_errors)
        
        # Detección de picos usando ML
        if self.anomaly_detector:
            anomaly_result = self.anomaly_detector.add_data_point('error_rate', error_rate)
            if anomaly_result:
                return {
                    'type': PatternType.ERROR_SPIKE.value,
                    'severity': 'high',
                    'description': f'Pico de detectado por ML: {error_rate:.2%} tasa de error',
                    'timestamp': datetime.now().isoformat(),
                    'error_rate': error_rate,
                    'ml_detection': True,
                    'anomaly_details': anomaly_result
                }
        
        # Fallback a detección básica
        if error_rate > 0.2:  # 20% de errores
            return {
                'type': PatternType.ERROR_SPIKE.value,
                'severity': 'high',
                'description': f'Detección de pico de errores: {error_rate:.2%} tasa de error',
                'timestamp': datetime.now().isoformat(),
                'error_rate': error_rate,
                'ml_detection': False
            }
        return None
    
    def _detect_performance_degradation_ml(self) -> Optional[Dict[str, Any]]:
        """Detectar degradación de rendimiento con ML."""
        if not self.performance_metrics:
            return None
            
        degradation_found = []
        for metric_name, values in self.performance_metrics.items():
            if len(values) >= 10:
                # Usar detector de anomalías para cada métrica
                if self.anomaly_detector:
                    for value in values[-10:]:
                        anomaly_result = self.anomaly_detector.add_data_point(metric_name, value)
                        if anomaly_result:
                            degradation_found.append({
                                'metric': metric_name,
                                'value': value,
                                'anomaly_details': anomaly_result
                            })
        
        if degradation_found:
            return {
                'type': PatternType.PERFORMANCE_DEGRADATION.value,
                'severity': 'medium',
                'description': f'Detección de degradación de rendimiento por ML en {len(degradation_found)} métricas',
                'timestamp': datetime.now().isoformat(),
                'degradations': degradation_found,
                'ml_detection': True
            }
        return None
    
    def _detect_anomaly_ml(self) -> Optional[Dict[str, Any]]:
        """Detectar anomalías con ML."""
        if len(self.log_buffer) < 50 or not self.anomaly_detector:
            return None
            
        # Analizar patrones secuenciales con ML
        anomalies = []
        for entry in list(self.log_buffer)[-50:]:
            pattern_result = self.ml_model.add_log_sequence(
                entry.category.value, 
                entry.level, 
                entry.module
            )
            if pattern_result:
                anomalies.append(pattern_result)
        
        if anomalies:
            return {
                'type': PatternType.ANOMALY.value,
                'severity': 'medium',
                'description': f'Detección de anomalías secuenciales por ML: {len(anomalies)} patrones',
                'timestamp': datetime.now().isoformat(),
                'anomalies': anomalies,
                'ml_detection': True
            }
        return None
    
    def _detect_sequential_patterns(self) -> List[Dict[str, Any]]:
        """Detectar patrones secuenciales."""
        patterns = []
        if len(self.log_buffer) < 20:
            return patterns
            
        # Buscar secuencias repetitivas
        sequences = defaultdict(list)
        for entry in list(self.log_buffer)[-50:]:
            key = f"{entry.category.value}_{entry.level.name}"
            sequences[key].append(entry.timestamp)
        
        # Detectar secuencias con intervalos regulares
        for seq_key, timestamps in sequences.items():
            if len(timestamps) >= 5:
                intervals = []
                for i in range(1, len(timestamps)):
                    interval = (timestamps[i] - timestamps[i-1]).total_seconds()
                    intervals.append(interval)
                
                # Buscar intervalos consistentes
                if len(intervals) >= 3:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                    
                    if variance < (avg_interval * 0.1) ** 2:  # Baja varianza
                        patterns.append({
                            'type': PatternType.CYCLE.value,
                            'severity': 'low',
                            'description': f'Secuencia detectada: {seq_key} con intervalo promedio {avg_interval:.2f}s',
                            'timestamp': datetime.now().isoformat(),
                            'sequence': seq_key,
                            'interval': avg_interval,
                            'occurrences': len(timestamps)
                        })
        
        return patterns
    
    def _detect_correlations(self) -> List[Dict[str, Any]]:
        """Detectar correlaciones entre diferentes tipos de logs."""
        patterns = []
        if len(self.log_buffer) < 100:
            return patterns
            
        # Contar co-ocurrencias de categorías
        co_occurrences = defaultdict(lambda: defaultdict(int))
        recent_logs = list(self.log_buffer)[-100:]
        
        for i, entry1 in enumerate(recent_logs):
            for entry2 in recent_logs[i+1:]:
                if (entry1.timestamp - entry2.timestamp).total_seconds() <= 300:  # 5 minutos
                    co_occurrences[entry1.category.value][entry2.category.value] += 1
        
        # Detectar correlaciones fuertes
        for cat1, cat2_counts in co_occurrences.items():
            total = sum(cat2_counts.values())
            for cat2, count in cat2_counts.items():
                if count >= 5 and cat1 != cat2:  # Al menos 5 co-ocurrencias
                    correlation = count / total
                    if correlation > 0.3:  # 30% correlación
                        patterns.append({
                            'type': PatternType.CORRELATION.value,
                            'severity': 'medium',
                            'description': f'Correlación detectada: {cat1} <-> {cat2} ({correlation:.2%})',
                            'timestamp': datetime.now().isoformat(),
                            'categories': [cat1, cat2],
                            'correlation': correlation,
                            'co_occurrences': count
                        })
        
        return patterns
    
    def _detect_advanced_anomalies(self) -> List[Dict[str, Any]]:
        """Detección avanzada de anomalías."""
        anomalies = []
        
        # Anomalías de frecuencia
        frequency_anomaly = self._detect_frequency_anomaly()
        if frequency_anomaly:
            anomalies.append(frequency_anomaly)
        
        # Anomalías de contexto
        context_anomaly = self._detect_context_anomaly()
        if context_anomaly:
            anomalies.append(context_anomaly)
        
        return anomalies
    
    def _detect_frequency_anomaly(self) -> Optional[Dict[str, Any]]:
        """Detectar anomalías de frecuencia."""
        if len(self.log_buffer) < 200:
            return None
            
        # Calcular tasa de logging
        time_window = 300  # 5 minutos
        recent_logs = [entry for entry in self.log_buffer 
                      if (datetime.now() - entry.timestamp).total_seconds() <= time_window]
        
        log_rate = len(recent_logs) / time_window
        
        # Detectar tasas inusuales
        if log_rate > 10:  # Más de 10 logs por segundo
            return {
                'type': 'frequency_anomaly',
                'severity': 'high',
                'description': f'Tasa de logging inusualmente alta: {log_rate:.2f} logs/segundo',
                'timestamp': datetime.now().isoformat(),
                'log_rate': log_rate,
                'window_size': time_window
            }
        elif log_rate < 0.01 and len(recent_logs) > 0:  # Menos de 0.01 logs por segundo
            return {
                'type': 'frequency_anomaly',
                'severity': 'medium',
                'description': f'Tasa de logging inusualmente baja: {log_rate:.4f} logs/segundo',
                'timestamp': datetime.now().isoformat(),
                'log_rate': log_rate,
                'window_size': time_window
            }
        
        return None
    
    def _detect_context_anomaly(self) -> Optional[Dict[str, Any]]:
        """Detectar anomalías de contexto."""
        if len(self.log_buffer) < 50:
            return None
            
        # Buscar logs con contexto inusual
        recent_logs = list(self.log_buffer)[-50:]
        unusual_contexts = []
        
        for entry in recent_logs:
            # Detectar logs con contexto faltante o inconsistente
            if (not entry.user_id and entry.category == LogCategory.SECURITY) or \
               (not entry.trace_id and entry.level == LogLevel.CRITICAL):
                unusual_contexts.append({
                    'timestamp': entry.timestamp.isoformat(),
                    'category': entry.category.value,
                    'level': entry.level.name,
                    'issue': 'missing_context'
                })
        
        if unusual_contexts:
            return {
                'type': 'context_anomaly',
                'severity': 'medium',
                'description': f'Detección de {len(unusual_contexts)} entradas con contexto inusual',
                'timestamp': datetime.now().isoformat(),
                'unusual_contexts': unusual_contexts
            }
        
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas del analizador."""
        with self.lock:
            return {
                'total_logs': len(self.log_buffer),
                'error_counts': dict(self.error_counts),
                'performance_metrics': {
                    name: {
                        'count': len(values),
                        'avg': sum(values) / len(values) if values else 0,
                        'min': min(values) if values else 0,
                        'max': max(values) if values else 0
                    }
                    for name, values in self.performance_metrics.items()
                },
                'patterns_detected': len(self.patterns)
            }


class AdvancedLogger:
    """Logger avanzado con capacidades de análisis y patrón detection."""
    
    def __init__(self, name: str, level: int = logging.INFO, 
                 log_dir: str = "logs", db_path: str = "logs/jarvis_logs.db",
                 ml_enabled: bool = True, anomaly_detection: bool = True):
        self.name = name
        self.level = level
        self.log_dir = Path(log_dir)
        self.db_path = Path(db_path)
        self.ml_enabled = ml_enabled
        self.anomaly_detection = anomaly_detection
        
        # Inicializar componentes avanzados
        self.analyzer = LogAnalyzer(ml_enabled=ml_enabled, anomaly_detection=anomaly_detection)
        self.metrics = AdvancedLogMetrics()
        self.log_queue = queue.Queue()
        self.running = False
        self.worker_thread = None
        
        # Configuración avanzada
        self.alerts = []
        self.filters = {}
        self.formatters = {}
        self.custom_handlers = []
        
        # Crear directorios y base de datos
        self._setup_logging_infrastructure()
        
        # Configurar logger base
        self.base_logger = logging.getLogger(name)
        self.base_logger.setLevel(level)
        
        # Evitar duplicados de handlers
        if not self.base_logger.handlers:
            self._setup_handlers()
    
    def _setup_logging_infrastructure(self) -> None:
        """Configurar infraestructura de logging."""
        # Crear directorio de logs
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Crear base de datos SQLite
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_database()
        
        # Iniciar worker para procesamiento asíncrono
        self.running = True
        self.worker_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.worker_thread.start()
    
    def _create_database(self) -> None:
        """Crear base de datos para logs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabla de logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    function TEXT,
                    line INTEGER,
                    thread_id TEXT,
                    process_id TEXT,
                    user_id TEXT,
                    session_id TEXT,
                    trace_id TEXT,
                    span_id TEXT,
                    parent_span_id TEXT,
                    tags TEXT,
                    metadata TEXT,
                    exception TEXT
                )
            ''')
            
            # Tabla de patrones detectados
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT NOT NULL,
                    data TEXT,
                    acknowledged BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Tabla de métricas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT,
                    metadata TEXT
                )
            ''')
            
            conn.commit()
    
    def _setup_handlers(self) -> None:
        """Configurar handlers del logger."""
        import sys
        
        # Console handler con formato JSON
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.level)
        console_handler.setFormatter(JsonFormatter())
        self.base_logger.addHandler(console_handler)
        
        # File handler para logs en disco
        file_handler = logging.FileHandler(
            self.log_dir / f"{self.name}.log",
            mode='a',
            encoding='utf-8'
        )
        file_handler.setLevel(self.level)
        file_handler.setFormatter(JsonFormatter())
        self.base_logger.addHandler(file_handler)
    
    def _log_worker(self) -> None:
        """Worker asíncrono para procesamiento de logs."""
        while self.running:
            try:
                entry = self.log_queue.get(timeout=1)
                if entry is None:  # Señal de parada
                    break
                    
                # Almacenar en base de datos
                self._store_log_entry(entry)
                
                # Analizar entrada
                patterns = self.analyzer.analyze_log_entry(entry)
                
                # Almacenar patrones detectados
                for pattern in patterns:
                    self._store_pattern(pattern)
                    
                # Generar alertas si es necesario
                self._generate_alerts(patterns, entry)
                
                self.log_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                # Loggear error en el logger base para evitar recursión
                self.base_logger.error(f"Error en log worker: {e}")
    
    def _store_log_entry(self, entry: LogEntry) -> None:
        """Almacenar entrada de log en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (
                    timestamp, level, category, message, module, function, line,
                    thread_id, process_id, user_id, session_id, trace_id,
                    span_id, parent_span_id, tags, metadata, exception
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.timestamp.isoformat(),
                entry.level.name,
                entry.category.value,
                entry.message,
                entry.module,
                entry.function,
                entry.line,
                entry.thread_id,
                entry.process_id,
                entry.user_id,
                entry.session_id,
                entry.trace_id,
                entry.span_id,
                entry.parent_span_id,
                json.dumps(entry.tags or {}),
                json.dumps(entry.metadata or {}),
                entry.exception
            ))
            conn.commit()
    
    def _store_pattern(self, pattern: Dict[str, Any]) -> None:
        """Almacenar patrón detectado."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO patterns (timestamp, type, severity, description, data)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                pattern['type'],
                pattern['severity'],
                pattern['description'],
                json.dumps(pattern)
            ))
            conn.commit()
    
    def _generate_alerts(self, patterns: List[Dict[str, Any]], entry: LogEntry) -> None:
        """Generar alertas basadas en patrones detectados."""
        for pattern in patterns:
            if pattern['severity'] in ['high', 'critical']:
                alert = {
                    'timestamp': datetime.now().isoformat(),
                    'type': 'pattern_detected',
                    'severity': pattern['severity'],
                    'pattern': pattern['type'],
                    'description': pattern['description'],
                    'log_entry': entry.to_dict(),
                    'source': self.name
                }
                
                # Aquí se podría integrar con el sistema de alertas existente
                self.base_logger.warning(f"ALERTA: {alert['description']}")
    
    def log(self, _level: LogLevel, category: LogCategory = None, message: str = None, 
            **kwargs) -> None:
        """Método principal de logging - soporta ambas interfaces:
        1. log(level, category, message, **kwargs) - interfaz completa
        2. log(message, level="INFO", category="SYSTEM", **kwargs) - interfaz simple
        """
        # Detectar si se usa la interfaz simple: log("message", level="INFO", ...)
        # En este caso, '_level' (primer parámetro) es el mensaje (str),
        # y 'level' viene en kwargs
        if isinstance(_level, str) and 'level' in kwargs:
            # Interfaz simple: log(message, level="INFO", category="SYSTEM", **kwargs)
            msg = _level
            lvl_str = kwargs.pop('level', 'INFO')
            cat_str = kwargs.pop('category', 'SYSTEM')
            return self.log_simple(msg, lvl_str, cat_str, **kwargs)
        
        # Interfaz completa: log(level, category, message, **kwargs)
        level = _level
        
        # Interfaz completa: log(level, category, message, **kwargs)
        # Crear entrada de log
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            category=category,
            message=message,
            module=kwargs.get('module', self.name),
            function=kwargs.get('function', ''),
            line=kwargs.get('line', 0),
            thread_id=str(threading.current_thread().ident),
            process_id=str(os.getpid()),
            user_id=kwargs.get('user_id'),
            session_id=kwargs.get('session_id'),
            trace_id=kwargs.get('trace_id'),
            span_id=kwargs.get('span_id'),
            parent_span_id=kwargs.get('parent_span_id'),
            tags=kwargs.get('tags'),
            metadata=kwargs.get('metadata'),
            exception=kwargs.get('exception')
        )
        
        # Añadir a cola para procesamiento asíncrono
        self.log_queue.put(entry)
        
        # Enviar datos al predictor para entrenamiento si está disponible
        if hasattr(self, 'predictor') and self.predictor:
            try:
                log_data = {
                    'timestamp': entry.timestamp.isoformat(),
                    'level': level.name,
                    'category': entry.category.value,
                    'message': message,
                    'module': entry.module,
                    'function': entry.function,
                    'line': entry.line,
                    'logger_name': entry.logger_name
                }
                self.predictor.add_log_data(log_data)
            except Exception as e:
                # No fallar si el predictor no funciona
                pass
        
        # También loggear inmediatamente para retrocompatibilidad
        self.base_logger.log(level.value, message, **kwargs)

    def log_simple(self, message: str, level: str = "INFO", category: str = "SYSTEM", **kwargs) -> None:
        """Interfaz simple de logging compatible con código existente.
        
        Args:
            message: Mensaje a loggear
            level: Nivel de log (DEBUG, INFO, WARNING, ERROR, CRITICAL, SUCCESS, PERFORMANCE)
            category: Categoría (SYSTEM, APPLICATION, NETWORK, PERFORMANCE, SECURITY, BUSINESS, DEBUG, ERROR)
            **kwargs: Argumentos adicionales
        """
        # Convertir level string a LogLevel
        level_map = {
            'DEBUG': LogLevel.DEBUG,
            'INFO': LogLevel.INFO,
            'WARNING': LogLevel.WARNING,
            'ERROR': LogLevel.ERROR,
            'CRITICAL': LogLevel.CRITICAL,
            'SUCCESS': LogLevel.SUCCESS,
            'PERFORMANCE': LogLevel.PERFORMANCE,
        }
        log_level = level_map.get(level.upper(), LogLevel.INFO)
        
        # Convertir category string a LogCategory
        category_map = {
            'SYSTEM': LogCategory.SYSTEM,
            'APPLICATION': LogCategory.APPLICATION,
            'NETWORK': LogCategory.NETWORK,
            'PERFORMANCE': LogCategory.PERFORMANCE,
            'SECURITY': LogCategory.SECURITY,
            'BUSINESS': LogCategory.BUSINESS,
            'DEBUG': LogCategory.DEBUG,
            'ERROR': LogCategory.ERROR,
        }
        log_category = category_map.get(category.upper(), LogCategory.SYSTEM)
        
        self.log(log_level, log_category, message, **kwargs)

    def debug(self, message: str, category: LogCategory = LogCategory.DEBUG, **kwargs) -> None:
        """Log de nivel DEBUG."""
        self.log(LogLevel.DEBUG, category, message, **kwargs)
    
    def info(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
        """Log de nivel INFO."""
        self.log(LogLevel.INFO, category, message, **kwargs)
    
    def warning(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
        """Log de nivel WARNING."""
        self.log(LogLevel.WARNING, category, message, **kwargs)
    
    def error(self, message: str, category: LogCategory = LogCategory.ERROR, **kwargs) -> None:
        """Log de nivel ERROR."""
        self.log(LogLevel.ERROR, category, message, **kwargs)
    
    def critical(self, message: str, category: LogCategory = LogCategory.ERROR, **kwargs) -> None:
        """Log de nivel CRITICAL."""
        self.log(LogLevel.CRITICAL, category, message, **kwargs)
    
    def success(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
        """Log de nivel SUCCESS."""
        self.log(LogLevel.SUCCESS, category, message, **kwargs)
    
    def performance(self, message: str, category: LogCategory = LogCategory.PERFORMANCE, **kwargs) -> None:
        """Log de nivel PERFORMANCE."""
        self.log(LogLevel.PERFORMANCE, category, message, **kwargs)
    
    def log_with_trace(self, message: str, category: LogCategory = LogCategory.SYSTEM, 
                      trace_id: str = None, **kwargs) -> None:
        """Log con trace ID para seguimiento distribuido."""
        kwargs['trace_id'] = trace_id or str(uuid.uuid4())
        self.log(LogLevel.INFO, category, message, **kwargs)
    
    def log_with_span(self, message: str, category: LogCategory = LogCategory.SYSTEM,
                     span_id: str = None, parent_span_id: str = None, **kwargs) -> None:
        """Log con span ID para microservicios."""
        kwargs['span_id'] = span_id or str(uuid.uuid4())
        kwargs['parent_span_id'] = parent_span_id
        self.log(LogLevel.INFO, category, message, **kwargs)
    
    def query_logs(self, start_time: datetime = None, end_time: datetime = None,
                   level: LogLevel = None, category: LogCategory = None,
                   module: str = None, limit: int = 100) -> List[LogEntry]:
        """Consultar logs desde la base de datos."""
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if level:
            query += " AND level = ?"
            params.append(level.name)
        
        if category:
            query += " AND category = ?"
            params.append(category.value)
        
        if module:
            query += " AND module = ?"
            params.append(module)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                entry = LogEntry(
                    timestamp=datetime.fromisoformat(row[1]),
                    level=LogLevel[row[2]],
                    category=LogCategory[row[3]],
                    message=row[4],
                    module=row[5],
                    function=row[6],
                    line=row[7],
                    thread_id=row[8],
                    process_id=row[9],
                    user_id=row[10],
                    session_id=row[11],
                    trace_id=row[12],
                    span_id=row[13],
                    parent_span_id=row[14],
                    tags=json.loads(row[15]) if row[15] else {},
                    metadata=json.loads(row[16]) if row[16] else {},
                    exception=row[17]
                )
                logs.append(entry)
            
            return logs
    
    def get_patterns(self, acknowledged: bool = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener patrones detectados."""
        query = "SELECT * FROM patterns WHERE 1=1"
        params = []
        
        if acknowledged is not None:
            query += " AND acknowledged = ?"
            params.append(acknowledged)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            patterns = []
            for row in rows:
                pattern = {
                    'id': row[0],
                    'timestamp': row[1],
                    'type': row[2],
                    'severity': row[3],
                    'description': row[4],
                    'data': json.loads(row[5]) if row[5] else {},
                    'acknowledged': bool(row[6])
                }
                patterns.append(pattern)
            
            return patterns
    
    def acknowledge_pattern(self, pattern_id: int) -> None:
        """Marcar patrón como reconocido."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE patterns SET acknowledged = TRUE WHERE id = ?", (pattern_id,))
            conn.commit()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas del sistema de logging."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Estadísticas generales
            cursor.execute("SELECT COUNT(*) FROM logs")
            total_logs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM patterns")
            total_patterns = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM patterns WHERE acknowledged = FALSE")
            active_patterns = cursor.fetchone()[0]
            
            # Estadísticas por nivel
            cursor.execute("SELECT level, COUNT(*) FROM logs GROUP BY level")
            level_stats = dict(cursor.fetchall())
            
            # Estadísticas por categoría
            cursor.execute("SELECT category, COUNT(*) FROM logs GROUP BY category")
            category_stats = dict(cursor.fetchall())
            
            # Estadísticas del analizador
            analyzer_stats = self.analyzer.get_statistics()
            
            return {
                'total_logs': total_logs,
                'total_patterns': total_patterns,
                'active_patterns': active_patterns,
                'level_statistics': level_stats,
                'category_statistics': category_stats,
                'analyzer_statistics': analyzer_stats
            }
    
    def export_logs(self, start_time: datetime = None, end_time: datetime = None,
                   format: str = 'json') -> str:
        """Exportar logs en formato especificado."""
        logs = self.query_logs(start_time, end_time, limit=10000)
        
        if format == 'json':
            return json.dumps([log.to_dict() for log in logs], indent=2, ensure_ascii=False)
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow(['timestamp', 'level', 'category', 'message', 'module', 'function', 'line'])
            
            # Datos
            for log in logs:
                writer.writerow([
                    log.timestamp.isoformat(),
                    log.level.name,
                    log.category.value,
                    log.message,
                    log.module,
                    log.function,
                    log.line
                ])
            
            return output.getvalue()
        else:
            raise ValueError(f"Formato no soportado: {format}")
    
    def shutdown(self) -> None:
        """Detener el logger de forma graceful."""
        self.running = False
        self.log_queue.put(None)  # Señal de parada
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        
        # Cerrar handlers personalizados
        for handler in self.custom_handlers:
            handler.close()
    
    def add_custom_filter(self, filter_name: str, filter_func: callable) -> None:
        """Añadir filtro personalizado."""
        self.filters[filter_name] = filter_func
        
    def add_custom_formatter(self, formatter_name: str, formatter: logging.Formatter) -> None:
        """Añadir formateador personalizado."""
        self.formatters[formatter_name] = formatter
        
    def add_custom_handler(self, handler: logging.Handler) -> None:
        """Añadir handler personalizado."""
        self.custom_handlers.append(handler)
        self.base_logger.addHandler(handler)
    
    def log_with_metrics(self, level: LogLevel, category: LogCategory, message: str, 
                        metrics: Dict[str, float] = None, **kwargs) -> None:
        """Log con métricas asociadas."""
        # Añadir métricas al sistema
        if metrics:
            for name, value in metrics.items():
                self.metrics.add_metric(name, value, kwargs.get('tags', {}))
        
        # Log normal con métricas en metadata
        if metrics:
            kwargs['metadata'] = kwargs.get('metadata', {})
            kwargs['metadata']['metrics'] = metrics
        
        self.log(level, category, message, **kwargs)
    
    def log_with_context(self, level: LogLevel, category: LogCategory, message: str,
                        context: Dict[str, Any] = None, **kwargs) -> None:
        """Log con contexto enriquecido."""
        # Añadir contexto a tags
        if context:
            kwargs['tags'] = kwargs.get('tags', {})
            kwargs['tags'].update(context)
        
        self.log(level, category, message, **kwargs)
    
    def log_batch(self, entries: List[Dict[str, Any]]) -> None:
        """Logear múltiples entradas de forma eficiente."""
        for entry in entries:
            self.log(
                level=entry.get('level', LogLevel.INFO),
                category=entry.get('category', LogCategory.SYSTEM),
                message=entry['message'],
                module=entry.get('module'),
                function=entry.get('function'),
                line=entry.get('line'),
                user_id=entry.get('user_id'),
                session_id=entry.get('session_id'),
                trace_id=entry.get('trace_id'),
                tags=entry.get('tags'),
                metadata=entry.get('metadata')
            )
    
    def search_logs(self, query: str, start_time: datetime = None, 
                   end_time: datetime = None, limit: int = 100) -> List[LogEntry]:
        """Buscar logs usando consulta de texto completo."""
        # Primero buscar en base de datos
        db_results = self.query_logs(start_time, end_time, limit=limit)
        
        # Filtrar por consulta
        if query:
            query_lower = query.lower()
            filtered_results = []
            for entry in db_results:
                if query_lower in entry.message.lower() or \
                   query_lower in entry.module.lower() or \
                   query_lower in str(entry.tags).lower():
                    filtered_results.append(entry)
            
            return filtered_results[:limit]
        
        return db_results
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Obtener métricas en tiempo real."""
        with self.lock:
            # Métricas del analizador
            analyzer_stats = self.analyzer.get_statistics()
            
            # Métricas de tendencias
            trend_metrics = {}
            for metric_name in self.metrics.metrics:
                trend_analysis = self.metrics.get_trend_analysis(metric_name)
                trend_metrics[metric_name] = trend_analysis
            
            # Estado actual del sistema
            return {
                'timestamp': datetime.now().isoformat(),
                'analyzer_statistics': analyzer_stats,
                'trend_metrics': trend_metrics,
                'queue_size': self.log_queue.qsize(),
                'running': self.running,
                'ml_enabled': self.ml_enabled,
                'anomaly_detection': self.anomaly_detection
            }
    
    def set_alert_threshold(self, pattern_type: str, threshold: Dict[str, Any]) -> None:
        """Establecer umbral de alerta para un tipo de patrón."""
        if not hasattr(self, 'alert_thresholds'):
            self.alert_thresholds = {}
        self.alert_thresholds[pattern_type] = threshold
    
    def get_alerts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Obtener alertas activas."""
        if active_only:
            return [alert for alert in self.alerts if not alert.get('acknowledged', False)]
        return self.alerts
    
    def acknowledge_alert(self, alert_id: str) -> None:
        """Marcar alerta como reconocida."""
        for alert in self.alerts:
            if alert.get('id') == alert_id:
                alert['acknowledged'] = True
                alert['acknowledged_at'] = datetime.now().isoformat()
                break
    
    def export_analytics(self, start_time: datetime = None, end_time: datetime = None,
                        format: str = 'json') -> str:
        """Exportar análisis avanzado de logs."""
        # Obtener logs en el rango
        logs = self.query_logs(start_time, end_time, limit=10000)
        
        # Generar análisis
        analytics = {
            'period': {
                'start': start_time.isoformat() if start_time else None,
                'end': end_time.isoformat() if end_time else None
            },
            'summary': {
                'total_logs': len(logs),
                'unique_modules': len(set(log.module for log in logs)),
                'time_range': (max(log.timestamp for log in logs) - min(log.timestamp for log in logs)).total_seconds() if logs else 0
            },
            'patterns': self.analyzer.get_statistics(),
            'trends': {},
            'top_errors': self._get_top_errors(logs),
            'performance_analysis': self._analyze_performance_logs(logs)
        }
        
        # Añadir análisis de tendencias
        for metric_name in self.metrics.metrics:
            trend_analysis = self.metrics.get_trend_analysis(metric_name)
            analytics['trends'][metric_name] = trend_analysis
        
        if format == 'json':
            return json.dumps(analytics, indent=2, ensure_ascii=False, default=str)
        else:
            raise ValueError(f"Formato no soportado: {format}")
    
    def _get_top_errors(self, logs: List[LogEntry]) -> List[Dict[str, Any]]:
        """Obtener errores más frecuentes."""
        error_counts = defaultdict(int)
        for log in logs:
            if log.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                error_counts[log.message] += 1
        
        top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return [{'message': msg, 'count': count} for msg, count in top_errors]
    
    def _analyze_performance_logs(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Analizar logs de rendimiento."""
        performance_logs = [log for log in logs if log.category == LogCategory.PERFORMANCE]
        
        if not performance_logs:
            return {'message': 'No hay logs de rendimiento'}
        
        response_times = []
        success_rates = []
        
        for log in performance_logs:
            # Extraer tiempos de respuesta
            time_match = re.search(r'time=(\d+(?:\.\d+)?)', log.message)
            if time_match:
                response_times.append(float(time_match.group(1)))
            
            # Extraer tasas de éxito
            success_match = re.search(r'success_rate=(\d+(?:\.\d+)?)', log.message)
            if success_match:
                success_rates.append(float(success_match.group(1)))
        
        return {
            'total_performance_logs': len(performance_logs),
            'avg_response_time': sum(response_times) / len(response_times) if response_times else 0,
            'avg_success_rate': sum(success_rates) / len(success_rates) if success_rates else 0,
            'min_response_time': min(response_times) if response_times else 0,
            'max_response_time': max(response_times) if response_times else 0
        }
    
    @contextmanager
    def log_context(self, context: Dict[str, Any]):
        """Context manager para logging con contexto temporal."""
        original_tags = getattr(self, '_current_context', {})
        self._current_context = original_tags.copy()
        self._current_context.update(context)
        
        try:
            yield self
        finally:
            self._current_context = original_tags
    
    def log_with_trace_context(self, message: str, trace_data: Dict[str, Any] = None, **kwargs):
        """Log con contexto de trazado distribuido."""
        # Añadir información de trazado
        trace_context = {
            'trace_id': str(uuid.uuid4()),
            'span_id': str(uuid.uuid4()),
            'parent_span_id': trace_data.get('parent_span_id') if trace_data else None,
            'service_name': self.name,
            'start_time': datetime.now().isoformat()
        }
        
        # Combinar con contexto existente
        if hasattr(self, '_current_context'):
            trace_context.update(self._current_context)
        
        kwargs['tags'] = kwargs.get('tags', {})
        kwargs['tags'].update(trace_context)
        
        if trace_data:
            kwargs['metadata'] = kwargs.get('metadata', {})
            kwargs['metadata'].update(trace_data)
        
        self.log(LogLevel.INFO, LogCategory.SYSTEM, message, **kwargs)


class JsonFormatter(logging.Formatter):
    """Formateador JSON mejorado."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Formatear log record como JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread': record.thread,
            'process': record.process,
        }
        
        # Añadir campos extra
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Añadir contexto de categorías
        if hasattr(record, 'category'):
            log_data['category'] = record.category
        
        # Añadir información de excepción
        if hasattr(record, 'exc_info') and record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


# Importación para compatibilidad con logger existente
def get_advanced_logger(name: str, level: int = logging.INFO, 
                      log_dir: str = "logs", db_path: str = "logs/jarvis_logs.db") -> AdvancedLogger:
    """Obtener un logger avanzado."""
    return AdvancedLogger(name, level, log_dir, db_path)


class StatisticalAnomalyDetector:
    """Detector de anomalías usando métodos estadísticos."""
    
    def __init__(self, window_size: int = 100, threshold: float = 2.0):
        self.window_size = window_size
        self.threshold = threshold
        self.data_windows = defaultdict(lambda: deque(maxlen=window_size))
        self.means = {}
        self.stdevs = {}
        
    def add_data_point(self, metric_name: str, value: float) -> bool:
        """Añadir punto de datos y detectar anomalía."""
        window = self.data_windows[metric_name]
        window.append(value)
        
        if len(window) >= 10:  # Mínimo para calcular estadísticas
            mean = sum(window) / len(window)
            stdev = (sum((x - mean) ** 2 for x in window) / len(window)) ** 0.5
            
            # Actualizar medias
            if metric_name not in self.means:
                self.means[metric_name] = []
            self.means[metric_name].append(mean)
            
            # Detectar anomalía
            z_score = abs(value - mean) / stdev if stdev > 0 else 0
            is_anomaly = z_score > self.threshold
            
            if is_anomaly:
                return {
                    'type': 'anomaly',
                    'metric': metric_name,
                    'value': value,
                    'mean': mean,
                    'stdev': stdev,
                    'z_score': z_score,
                    'severity': 'high' if z_score > 3 else 'medium'
                }
        
        return None


class PatternRecognizer:
    """Reconocedor de patrones usando métodos de secuencia."""
    
    def __init__(self, min_pattern_length: int = 3, max_pattern_length: int = 10):
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        self.patterns = {}
        self.sequences = defaultdict(list)
        
    def add_log_sequence(self, category: str, level: LogLevel, module: str) -> Optional[Dict[str, Any]]:
        """Añadir secuencia de logs y detectar patrones."""
        sequence_key = f"{category}_{level.name}_{module}"
        self.sequences[sequence_key].append({
            'timestamp': datetime.now(),
            'category': category,
            'level': level.name,
            'module': module
        })
        
        # Detectar patrones repetitivos
        pattern = self._detect_repetitive_pattern(sequence_key)
        if pattern:
            return pattern
        
        return None
        
    def _detect_repetitive_pattern(self, sequence_key: str) -> Optional[Dict[str, Any]]:
        """Detectar patrones repetitivos en secuencias."""
        sequence = self.sequences[sequence_key]
        if len(sequence) < self.min_pattern_length * 2:
            return None
            
        # Buscar patrones repetitivos
        for pattern_length in range(self.min_pattern_length, min(self.max_pattern_length, len(sequence) // 2 + 1)):
            pattern = sequence[-pattern_length:]
            
            # Contar ocurrencias del patrón
            count = 0
            for i in range(len(sequence) - pattern_length):
                if sequence[i:i+pattern_length] == pattern:
                    count += 1
                    
            if count >= 2:  # Patrón repetido al menos 2 veces
                return {
                    'type': 'repetitive_pattern',
                    'pattern_length': pattern_length,
                    'occurrences': count,
                    'sequence': sequence_key,
                    'severity': 'medium'
                }
        
        return None


class AdvancedLogMetrics:
    """Métricas avanzadas de logging y análisis de rendimiento."""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.baselines = {}
        self.alert_thresholds = {}
        
    def add_metric(self, name: str, value: float, tags: Dict[str, Any] = None) -> None:
        """Añadir métrica con análisis de tendencias."""
        timestamp = datetime.now()
        self.metrics[name].append({
            'timestamp': timestamp,
            'value': value,
            'tags': tags or {}
        })
        
        # Actualizar línea base
        if name not in self.baselines:
            self.baselines[name] = {
                'count': 0,
                'sum': 0,
                'avg': 0,
                'min': float('inf'),
                'max': float('-inf')
            }
        
        baseline = self.baselines[name]
        baseline['count'] += 1
        baseline['sum'] += value
        baseline['avg'] = baseline['sum'] / baseline['count']
        baseline['min'] = min(baseline['min'], value)
        baseline['max'] = max(baseline['max'], value)
        
    def get_trend_analysis(self, metric_name: str, window_size: int = 100) -> Dict[str, Any]:
        """Análisis de tendencias para una métrica."""
        if metric_name not in self.metrics or len(self.metrics[metric_name]) < 10:
            return {'trend': 'insufficient_data'}
            
        recent_data = self.metrics[metric_name][-window_size:]
        values = [d['value'] for d in recent_data]
        
        # Calcular tendencia usando regresión lineal simple
        n = len(values)
        x = list(range(n))
        
        # Media de x y y
        mean_x = sum(x) / n
        mean_y = sum(values) / n
        
        # Covarianza y varianza
        covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
        variance = sum((xi - mean_x) ** 2 for xi in x)
        
        if variance == 0:
            slope = 0
        else:
            slope = covariance / variance
            
        # Determinar tendencia
        if slope > 0.1:
            trend = 'increasing'
        elif slope < -0.1:
            trend = 'decreasing'
        else:
            trend = 'stable'
            
        return {
            'trend': trend,
            'slope': slope,
            'current_value': values[-1],
            'average_value': mean_y,
            'min_value': min(values),
            'max_value': max(values),
            'volatility': self._calculate_volatility(values)
        }
        
    def _calculate_volatility(self, values: List[float]) -> float:
        """Calcular volatilidad de una serie de valores."""
        if len(values) < 2:
            return 0
            
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# Logger predeterminado para Jarvis
jarvis_logger = get_advanced_logger("Jarvis")