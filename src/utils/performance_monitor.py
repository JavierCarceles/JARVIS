"""
Monitor avanzado de rendimiento para Jarvis con análisis predictivo y alertas inteligentes.
"""

import json
import logging
import sqlite3
import threading
import time
import psutil
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import asyncio
import queue


class MetricType(Enum):
    """Tipos de métricas de rendimiento."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    PROCESS = "process"
    DATABASE = "database"
    APPLICATION = "application"
    CUSTOM = "custom"


class AlertSeverity(Enum):
    """Severidad de alertas."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """Métrica de rendimiento."""
    id: str
    name: str
    type: MetricType
    value: float
    unit: str
    timestamp: datetime
    tags: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['type'] = self.type.value
        return data


@dataclass
class PerformanceAlert:
    """Alerta de rendimiento."""
    id: str
    metric_name: str
    current_value: float
    threshold_value: float
    severity: AlertSeverity
    message: str
    timestamp: datetime
    tags: Dict[str, Any] = None
    acknowledged: bool = False
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['severity'] = self.severity.value
        return data


class PerformanceCollector:
    """Colector de métricas de rendimiento."""
    
    def __init__(self, collection_interval: int = 10, max_history: int = 10000):
        self.collection_interval = collection_interval
        self.max_history = max_history
        self.metrics = defaultdict(lambda: deque(maxlen=max_history))
        self.is_collecting = False
        self.collection_thread = None
        self.lock = threading.Lock()
        
    def start_collection(self) -> None:
        """Iniciar recolección de métricas."""
        if self.is_collecting:
            return
            
        self.is_collecting = True
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
        
    def stop_collection(self) -> None:
        """Detener recolección de métricas."""
        self.is_collecting = False
        if self.collection_thread:
            self.collection_thread.join(timeout=5)
    
    def _collection_loop(self) -> None:
        """Bucle de recolección de métricas."""
        while self.is_collecting:
            try:
                # Recolectar métricas del sistema
                self._collect_system_metrics()
                
                # Recolectar métricas de procesos
                self._collect_process_metrics()
                
                # Recolectar métricas de red
                self._collect_network_metrics()
                
                # Recolectar métricas de disco
                self._collect_disk_metrics()
                
                time.sleep(self.collection_interval)
                
            except Exception as e:
                logging.error(f"Error en recolección de métricas: {e}")
                time.sleep(self.collection_interval)
    
    def _collect_system_metrics(self) -> None:
        """Recolectar métricas del sistema."""
        timestamp = datetime.now()
        
        # Uso de CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        self._add_metric("cpu_usage", cpu_percent, "%", timestamp, 
                        {"core_count": psutil.cpu_count()})
        
        # Uso de memoria
        memory = psutil.virtual_memory()
        self._add_metric("memory_usage", memory.percent, "%", timestamp,
                        {"total": memory.total, "available": memory.available})
        
        # Uso de swap
        swap = psutil.swap_memory()
        self._add_metric("swap_usage", swap.percent, "%", timestamp,
                        {"total": swap.total, "used": swap.used})
        
        # Carga del sistema (solo en Unix-like systems)
        try:
            load_avg = psutil.getloadavg()
            for i, load in enumerate(load_avg):
                self._add_metric(f"load_average_{i}", load, "", timestamp,
                                {"core_count": psutil.cpu_count()})
        except (AttributeError, OSError):
            pass  # No disponible en Windows
    
    def _collect_process_metrics(self) -> None:
        """Recolectar métricas de procesos."""
        timestamp = datetime.now()
        
        # Métricas del proceso actual
        process = psutil.Process()
        
        try:
            # Uso de CPU por proceso
            cpu_percent = process.cpu_percent()
            self._add_metric("process_cpu", cpu_percent, "%", timestamp,
                            {"pid": process.pid})
            
            # Uso de memoria por proceso
            memory_info = process.memory_info()
            self._add_metric("process_memory", memory_info.rss / 1024 / 1024, "MB", timestamp,
                            {"pid": process.pid, "memory_percent": process.memory_percent()})
            
            # Conteo de hilos
            thread_count = process.num_threads()
            self._add_metric("process_threads", thread_count, "", timestamp,
                            {"pid": process.pid})
            
            # Conteo de conexiones abiertas
            connections = len(process.connections())
            self._add_metric("process_connections", connections, "", timestamp,
                            {"pid": process.pid})
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # Proceso ya no existe o sin permisos
    
    def _collect_network_metrics(self) -> None:
        """Recolectar métricas de red."""
        timestamp = datetime.now()
        
        # Estadísticas de red
        net_io = psutil.net_io_counters()
        self._add_metric("network_bytes_sent", net_io.bytes_sent, "bytes", timestamp)
        self._add_metric("network_bytes_recv", net_io.bytes_recv, "bytes", timestamp)
        self._add_metric("network_packets_sent", net_io.packets_sent, "packets", timestamp)
        self._add_metric("network_packets_recv", net_io.packets_recv, "packets", timestamp)
        
        # Estadísticas por interfaz
        net_io_per = psutil.net_io_counters(pernic=True)
        for interface, io in net_io_per.items():
            self._add_metric(f"network_{interface}_bytes_sent", io.bytes_sent, "bytes", timestamp,
                           {"interface": interface})
            self._add_metric(f"network_{interface}_bytes_recv", io.bytes_recv, "bytes", timestamp,
                           {"interface": interface})
    
    def _collect_disk_metrics(self) -> None:
        """Recolectar métricas de disco."""
        timestamp = datetime.now()
        
        # Estadísticas de disco
        disk_io = psutil.disk_io_counters()
        if disk_io:
            self._add_metric("disk_read_bytes", disk_io.read_bytes, "bytes", timestamp)
            self._add_metric("disk_write_bytes", disk_io.write_bytes, "bytes", timestamp)
            self._add_metric("disk_read_count", disk_io.read_count, "count", timestamp)
            self._add_metric("disk_write_count", disk_io.write_count, "count", timestamp)
        
        # Uso de disco por partición
        disk_usage = psutil.disk_usage('/')
        self._add_metric("disk_usage", disk_usage.percent, "%", timestamp,
                        {"path": "/", "total": disk_usage.total, "free": disk_usage.free})
        
        # Uso de disco por partición (todas)
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                self._add_metric(f"disk_usage_{partition.device.replace('/', '_')}", 
                               usage.percent, "%", timestamp,
                               {"device": partition.device, "mountpoint": partition.mountpoint})
            except (PermissionError, FileNotFoundError):
                pass  # Sin acceso o montura no disponible
    
    def _add_metric(self, name: str, value: float, unit: str, 
                   timestamp: datetime, tags: Dict[str, Any] = None) -> None:
        """Añadir métrica al colector."""
        with self.lock:
            metric = PerformanceMetric(
                id=f"{name}_{int(timestamp.timestamp())}",
                name=name,
                type=self._get_metric_type(name),
                value=value,
                unit=unit,
                timestamp=timestamp,
                tags=tags or {}
            )
            self.metrics[name].append(metric)
    
    def _get_metric_type(self, name: str) -> MetricType:
        """Determinar el tipo de métrica por nombre."""
        if name.startswith("cpu"):
            return MetricType.CPU
        elif name.startswith("memory") or name.startswith("swap"):
            return MetricType.MEMORY
        elif name.startswith("disk"):
            return MetricType.DISK
        elif name.startswith("network"):
            return MetricType.NETWORK
        elif name.startswith("process"):
            return MetricType.PROCESS
        elif name.startswith("database"):
            return MetricType.DATABASE
        elif name.startswith("application"):
            return MetricType.APPLICATION
        else:
            return MetricType.CUSTOM
    
    def get_metric_history(self, name: str, hours: int = 24) -> List[PerformanceMetric]:
        """Obtener historial de una métrica."""
        with self.lock:
            if name not in self.metrics:
                return []
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            return [metric for metric in self.metrics[name] if metric.timestamp >= cutoff_time]
    
    def get_latest_metrics(self) -> Dict[str, PerformanceMetric]:
        """Obtener las métricas más recientes."""
        with self.lock:
            latest = {}
            for name, metrics in self.metrics.items():
                if metrics:
                    latest[name] = metrics[-1]
            return latest
    
    def get_metric_statistics(self, name: str, hours: int = 24) -> Dict[str, float]:
        """Obtener estadísticas de una métrica."""
        history = self.get_metric_history(name, hours)
        
        if not history:
            return {}
        
        values = [metric.value for metric in history]
        
        return {
            "count": len(values),
            "mean": np.mean(values),
            "median": np.median(values),
            "std": np.std(values),
            "min": np.min(values),
            "max": np.max(values),
            "p95": np.percentile(values, 95),
            "p99": np.percentile(values, 99)
        }


class PerformanceAnalyzer:
    """Analizador de rendimiento con detección de anomalías."""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.anomaly_detectors = {}
        self.scalers = {}
        self.is_trained = False
        self.lock = threading.Lock()
        
    def train_anomaly_detector(self, metric_name: str, history: List[PerformanceMetric]) -> None:
        """Entrenar detector de anomalías para una métrica."""
        with self.lock:
            if len(history) < 50:
                return
            
            # Extraer valores
            values = [metric.value for metric in history]
            
            # Escalar datos
            if metric_name not in self.scalers:
                self.scalers[metric_name] = StandardScaler()
            
            scaled_values = self.scalers[metric_name].fit_transform(np.array(values).reshape(-1, 1))
            
            # Entrenar modelo
            if metric_name not in self.anomaly_detectors:
                self.anomaly_detectors[metric_name] = IsolationForest(
                    contamination=0.1, random_state=42
                )
            
            self.anomaly_detectors[metric_name].fit(scaled_values)
            self.is_trained = True
    
    def detect_anomalies(self, metric_name: str, current_value: float) -> Dict[str, Any]:
        """Detectar anomalías en una métrica."""
        if metric_name not in self.anomaly_detectors or not self.is_trained:
            return {"is_anomaly": False, "score": 0.0}
        
        try:
            # Escalar valor actual
            scaled_value = self.scalers[metric_name].transform([[current_value]])
            
            # Detectar anomalía
            anomaly_score = self.anomaly_detectors[metric_name].decision_function(scaled_value)[0]
            is_anomaly = anomaly_score < -0.5
            
            return {
                "is_anomaly": is_anomaly,
                "score": anomaly_score,
                "severity": "high" if anomaly_score < -0.8 else "medium"
            }
            
        except Exception as e:
            logging.error(f"Error detectando anomalías para {metric_name}: {e}")
            return {"is_anomaly": False, "score": 0.0}
    
    def analyze_trends(self, metric_name: str, history: List[PerformanceMetric]) -> Dict[str, Any]:
        """Analizar tendencias en una métrica."""
        if len(history) < 10:
            return {"trend": "insufficient_data"}
        
        values = [metric.value for metric in history[-50:]]  # Últimos 50 valores
        
        # Calcular tendencia usando regresión lineal simple
        n = len(values)
        x = list(range(n))
        mean_x = sum(x) / n
        mean_y = sum(values) / n
        
        covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
        variance = sum((xi - mean_x) ** 2 for xi in x)
        
        if variance == 0:
            slope = 0
        else:
            slope = covariance / variance
        
        # Determinar dirección de la tendencia
        if slope > 0.1:
            trend = "increasing"
        elif slope < -0.1:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "slope": slope,
            "current_value": values[-1],
            "average_value": mean_y,
            "volatility": np.std(values)
        }


class PerformanceMonitor:
    """Monitor de rendimiento principal."""
    
    def __init__(self, db_path: str = "logs/performance.db"):
        self.db_path = Path(db_path)
        self.collector = PerformanceCollector()
        self.analyzer = PerformanceAnalyzer()
        self.alerts = []
        self.alert_rules = []
        self.is_monitoring = False
        self.monitoring_thread = None
        self.alert_queue = queue.Queue()
        self.lock = threading.Lock()
        
        # Crear base de datos
        self._create_database()
        
        # Cargar reglas de alerta por defecto
        self._load_default_alert_rules()
        
    def _create_database(self) -> None:
        """Crear base de datos para monitor de rendimiento."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabla de métricas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tags TEXT,
                    metadata TEXT
                )
            ''')
            
            # Tabla de alertas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    metric_name TEXT NOT NULL,
                    current_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tags TEXT,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    resolved BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Tabla de reglas de alerta
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    metric_name TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    severity TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    cooldown_minutes INTEGER DEFAULT 60,
                    message_template TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def _load_default_alert_rules(self) -> None:
        """Cargar reglas de alerta por defecto."""
        default_rules = [
            {
                "id": "cpu_high",
                "metric_name": "cpu_usage",
                "condition": "greater_than",
                "threshold": 90.0,
                "severity": "critical",
                "cooldown_minutes": 30,
                "message_template": "Uso de CPU crítico: {value}% (umbral: {threshold}%)"
            },
            {
                "id": "memory_high",
                "metric_name": "memory_usage",
                "condition": "greater_than",
                "threshold": 85.0,
                "severity": "warning",
                "cooldown_minutes": 60,
                "message_template": "Uso de memoria alto: {value}% (umbral: {threshold}%)"
            },
            {
                "id": "disk_high",
                "metric_name": "disk_usage",
                "condition": "greater_than",
                "threshold": 90.0,
                "severity": "error",
                "cooldown_minutes": 120,
                "message_template": "Uso de disco crítico: {value}% (umbral: {threshold}%)"
            },
            {
                "id": "network_errors",
                "metric_name": "network_packets_sent",
                "condition": "less_than",
                "threshold": 100.0,
                "severity": "warning",
                "cooldown_minutes": 15,
                "message_template": "Actividad de red inusualmente baja: {value} paquetes/seg"
            }
        ]
        
        for rule_data in default_rules:
            rule = AlertRule(**rule_data)
            self.alert_rules.append(rule)
            self._save_alert_rule(rule)
    
    def start_monitoring(self) -> None:
        """Iniciar monitoreo de rendimiento."""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.collector.start_collection()
        
        # Iniciar hilo de monitoreo
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        # Iniciar hilo de procesamiento de alertas
        alert_thread = threading.Thread(target=self._alert_processing_loop, daemon=True)
        alert_thread.start()
    
    def stop_monitoring(self) -> None:
        """Detener monitoreo de rendimiento."""
        self.is_monitoring = False
        self.collector.stop_collection()
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
    
    def _monitoring_loop(self) -> None:
        """Bucle principal de monitoreo."""
        last_alert_times = defaultdict(lambda: datetime.now() - timedelta(hours=1))
        
        while self.is_monitoring:
            try:
                # Obtener métricas más recientes
                latest_metrics = self.collector.get_latest_metrics()
                
                # Procesar cada métrica
                for metric_name, metric in latest_metrics.items():
                    # Verificar reglas de alerta
                    for rule in self.alert_rules:
                        if rule.enabled and rule.metric_name == metric_name:
                            # Verificar cooldown
                            if datetime.now() - last_alert_times[rule.id] < timedelta(minutes=rule.cooldown_minutes):
                                continue
                            
                            # Evaluar condición
                            if self._evaluate_alert_condition(rule, metric.value):
                                # Crear alerta
                                alert = self._create_alert(rule, metric)
                                self.alert_queue.put(alert)
                                last_alert_times[rule.id] = datetime.now()
                
                # Entrenar detectores de anomalías periódicamente
                if int(time.time()) % 300 == 0:  # Cada 5 minutos
                    self._train_anomaly_detectors()
                
                time.sleep(5)  # Verificar cada 5 segundos
                
            except Exception as e:
                logging.error(f"Error en bucle de monitoreo: {e}")
                time.sleep(10)
    
    def _alert_processing_loop(self) -> None:
        """Bucle de procesamiento de alertas."""
        while self.is_monitoring:
            try:
                alert = self.alert_queue.get(timeout=1)
                if alert:
                    self._process_alert(alert)
                    self.alert_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error procesando alerta: {e}")
    
    def _evaluate_alert_condition(self, rule: 'AlertRule', value: float) -> bool:
        """Evaluar si se cumple una condición de alerta."""
        if rule.condition == "greater_than":
            return value > rule.threshold
        elif rule.condition == "less_than":
            return value < rule.threshold
        elif rule.condition == "equal_to":
            return abs(value - rule.threshold) < 0.01
        elif rule.condition == "not_equal_to":
            return abs(value - rule.threshold) > 0.01
        return False
    
    def _create_alert(self, rule: 'AlertRule', metric: PerformanceMetric) -> PerformanceAlert:
        """Crear alerta basada en una regla."""
        message = rule.message_template.format(
            value=metric.value,
            threshold=rule.threshold,
            metric_name=metric.name
        )
        
        return PerformanceAlert(
            id=f"alert_{rule.id}_{int(time.time())}",
            metric_name=rule.metric_name,
            current_value=metric.value,
            threshold_value=rule.threshold,
            severity=AlertSeverity(rule.severity),
            message=message,
            timestamp=datetime.now(),
            tags=metric.tags
        )
    
    def _process_alert(self, alert: PerformanceAlert) -> None:
        """Procesar alerta."""
        with self.lock:
            self.alerts.append(alert)
            self._save_alert(alert)
            
            # Notificar (aquí se podría integrar con sistema de notificaciones)
            logging.warning(f"ALERTA: {alert.message}")
            
            # Generar acciones correctivas
            self._generate_corrective_actions(alert)
    
    def _generate_corrective_actions(self, alert: PerformanceAlert) -> None:
        """Generar acciones correctivas basadas en la alerta."""
        actions = []
        
        if alert.metric_name == "cpu_usage":
            actions.extend([
                "Revisar procesos consumidores de CPU",
                "Considerar optimización de consultas",
                "Verificar si es pico normal o problema"
            ])
        elif alert.metric_name == "memory_usage":
            actions.extend([
                "Revisar memory leaks en aplicación",
                "Considerar aumento de memoria RAM",
                "Optimizar uso de recursos"
            ])
        elif alert.metric_name == "disk_usage":
            actions.extend([
                "Limpiar espacio en disco",
                "Mover logs a almacenamiento externo",
                "Considerar expansión de disco"
            ])
        
        # Guardar acciones en metadata de la alerta
        alert.tags['corrective_actions'] = actions
    
    def _train_anomaly_detectors(self) -> None:
        """Entrenar detectores de anomalías."""
        with self.lock:
            for metric_name in self.collector.metrics.keys():
                history = self.collector.get_metric_history(metric_name, hours=24)
                if len(history) >= 50:
                    self.analyzer.train_anomaly_detector(metric_name, history)
    
    def _save_alert(self, alert: PerformanceAlert) -> None:
        """Guardar alerta en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alerts (
                    id, metric_name, current_value, threshold_value, severity,
                    message, timestamp, tags, acknowledged, resolved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                alert.id,
                alert.metric_name,
                alert.current_value,
                alert.threshold_value,
                alert.severity.value,
                alert.message,
                alert.timestamp.isoformat(),
                json.dumps(alert.tags or {}),
                alert.acknowledged,
                alert.resolved
            ))
            conn.commit()
    
    def _save_alert_rule(self, rule: 'AlertRule') -> None:
        """Guardar regla de alerta en base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO alert_rules (
                    id, metric_name, condition, threshold, severity, enabled,
                    cooldown_minutes, message_template, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                rule.id,
                rule.metric_name,
                rule.condition,
                rule.threshold,
                rule.severity,
                rule.enabled,
                rule.cooldown_minutes,
                rule.message_template,
                datetime.now().isoformat()
            ))
            conn.commit()
    
    def add_alert_rule(self, rule: 'AlertRule') -> None:
        """Añadir regla de alerta."""
        with self.lock:
            self.alert_rules.append(rule)
            self._save_alert_rule(rule)
    
    def remove_alert_rule(self, rule_id: str) -> None:
        """Eliminar regla de alerta."""
        with self.lock:
            self.alert_rules = [r for r in self.alert_rules if r.id != rule_id]
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
                conn.commit()
    
    def get_alerts(self, severity: AlertSeverity = None, 
                   acknowledged: bool = None, limit: int = 100) -> List[PerformanceAlert]:
        """Obtener alertas."""
        with self.lock:
            alerts = self.alerts.copy()
            
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            if acknowledged is not None:
                alerts = [a for a in alerts if a.acknowledged == acknowledged]
            
            return alerts[-limit:]
    
    def acknowledge_alert(self, alert_id: str) -> None:
        """Marcar alerta como reconocida."""
        with self.lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    self._save_alert(alert)
                    break
    
    def resolve_alert(self, alert_id: str) -> None:
        """Marcar alerta como resuelta."""
        with self.lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    alert.acknowledged = True
                    self._save_alert(alert)
                    break
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Obtener resumen del rendimiento."""
        with self.lock:
            latest_metrics = self.collector.get_latest_metrics()
            
            summary = {
                "timestamp": datetime.now().isoformat(),
                "total_metrics": len(latest_metrics),
                "alert_count": len(self.alerts),
                "active_alerts": len([a for a in self.alerts if not a.acknowledged]),
                "metrics": {}
            }
            
            for metric_name, metric in latest_metrics.items():
                stats = self.collector.get_metric_statistics(metric_name, hours=1)
                trend_analysis = self.analyzer.analyze_trends(metric_name, 
                    self.collector.get_metric_history(metric_name, hours=1))
                
                summary["metrics"][metric_name] = {
                    "current_value": metric.value,
                    "unit": metric.unit,
                    "statistics": stats,
                    "trend": trend_analysis
                }
            
            return summary
    
    def export_performance_data(self, start_time: datetime = None, 
                              end_time: datetime = None, format: str = 'json') -> str:
        """Exportar datos de rendimiento."""
        query = "SELECT * FROM metrics WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT 10000"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            metrics = []
            for row in rows:
                metric = {
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'value': row[3],
                    'unit': row[4],
                    'timestamp': row[5],
                    'tags': json.loads(row[6]) if row[6] else {},
                    'metadata': json.loads(row[7]) if row[7] else {}
                }
                metrics.append(metric)
            
            if format == 'json':
                return json.dumps(metrics, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Formato no soportado: {format}")


@dataclass
class AlertRule:
    """Regla de alerta."""
    id: str
    metric_name: str
    condition: str  # greater_than, less_than, equal_to, not_equal_to
    threshold: float
    severity: str  # info, warning, error, critical
    enabled: bool = True
    cooldown_minutes: int = 60
    message_template: str = ""
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


# Instancia global del monitor de rendimiento
performance_monitor = PerformanceMonitor()