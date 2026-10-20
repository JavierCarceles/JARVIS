"""
Sistema de recolección de métricas para JARVIS.

Este módulo proporciona herramientas para recopilar, almacenar y gestionar
métricas del sistema de manera estructurada y persistente.
"""

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import os

from src.utils.logger import get_logger


@dataclass
class MetricData:
    """Datos de una métrica individual."""
    
    timestamp: datetime
    metric_name: str
    value: Union[float, int, str, bool]
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte los datos de la métrica a un diccionario."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'metric_name': self.metric_name,
            'value': self.value,
            'tags': self.tags,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MetricData':
        """Crea una instancia de MetricData desde un diccionario."""
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            metric_name=data['metric_name'],
            value=data['value'],
            tags=data.get('tags', {}),
            metadata=data.get('metadata', {})
        )


@dataclass
class MetricConfig:
    """Configuración para la recolección de métricas."""
    
    # Configuración de base de datos
    db_path: str = "data/metrics/jarvis_metrics.db"
    backup_path: str = "data/metrics/backups/"
    
    # Configuración de retención
    retention_days: int = 30
    max_metrics_per_name: int = 10000
    
    # Configuración de recolección
    collection_interval_seconds: float = 60.0
    batch_size: int = 100
    
    # Métricas predeterminadas a recolectar
    default_metrics: List[str] = field(default_factory=lambda: [
        'system.cpu_percent',
        'system.memory_percent',
        'system.disk_percent',
        'jarvis.actions_executed',
        'jarvis.actions_failed',
        'jarvis.response_time'
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a un diccionario."""
        return {
            'db_path': self.db_path,
            'backup_path': self.backup_path,
            'retention_days': self.retention_days,
            'max_metrics_per_name': self.max_metrics_per_name,
            'collection_interval_seconds': self.collection_interval_seconds,
            'batch_size': self.batch_size,
            'default_metrics': self.default_metrics
        }


class MetricsCollector:
    """Recolector de métricas para JARVIS."""
    
    def __init__(self, config: Optional[MetricConfig] = None):
        """
        Inicializa el recolector de métricas.
        
        Args:
            config: Configuración personalizada para la recolección
        """
        self.logger = get_logger("MetricsCollector")
        self.config = config or MetricConfig()
        
        # Estado del recolector
        self.is_running = False
        self.collection_thread: Optional[threading.Thread] = None
        
        # Buffer para métricas en lote
        self.metrics_buffer: List[MetricData] = []
        self.buffer_lock = threading.Lock()
        
        # Inicializar base de datos
        self._initialize_database()
        
        # Inicializar directorios
        self._ensure_directories()
        
        # Inicialización
        self.logger._print_log("info", "[METRICS-COLLECTOR] Recolector de métricas inicializado", "metrics_collector.py", "__init__", 85)
        
    def _initialize_database(self) -> None:
        """Inicializa la base de datos SQLite para métricas."""
        try:
            # Crear directorio si no existe
            db_dir = os.path.dirname(self.config.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            # Conectar y crear tablas
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                
                # Tabla principal de métricas
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        value REAL,
                        tags TEXT,
                        metadata TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Índices para rendimiento
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_metric_name ON metrics(metric_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metrics(metric_name, timestamp)')
                
                conn.commit()
                
            self.logger._print_log("info", f"[METRICS-COLLECTOR] Base de datos inicializada en {self.config.db_path}", "metrics_collector.py", "_initialize_database", 115)
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al inicializar base de datos: {exc}", "metrics_collector.py", "_initialize_database", 119)
            raise
            
    def _ensure_directories(self) -> None:
        """Asegura que los directorios necesarios existan."""
        try:
            # Crear directorio de backups
            backup_dir = os.path.dirname(self.config.backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)
                
            # Crear directorio de datos
            data_dir = os.path.dirname(self.config.db_path)
            if data_dir and not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al crear directorios: {exc}", "metrics_collector.py", "_ensure_directories", 139)
            
    def start_collection(self) -> None:
        """Inicia la recolección continua de métricas."""
        if self.is_running:
            self.logger._print_log("warning", "[METRICS-COLLECTOR] La recolección ya está en ejecución", "metrics_collector.py", "start_collection", 146)
            return
            
        self.is_running = True
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
        
        self.logger._print_log("info", f"[METRICS-COLLECTOR] Recolección iniciada con intervalo de {self.config.collection_interval_seconds}s", "metrics_collector.py", "start_collection", 152)
        
    def stop_collection(self) -> None:
        """Detiene la recolección de métricas."""
        if not self.is_running:
            self.logger._print_log("warning", "[METRICS-COLLECTOR] La recolección no está en ejecución", "metrics_collector.py", "stop_collection", 159)
            return
            
        self.is_running = False
        
        # Vaciar buffer final
        self._flush_buffer()
        
        if self.collection_thread and self.collection_thread.is_alive():
            self.collection_thread.join(timeout=5.0)
            
        self.logger._print_log("info", "[METRICS-COLLECTOR] Recolección detenida", "metrics_collector.py", "stop_collection", 169)
        
    def _collection_loop(self) -> None:
        """Bucle principal de recolección de métricas."""
        while self.is_running:
            try:
                # Recolectar métricas predeterminadas
                for metric_name in self.config.default_metrics:
                    self.collect_metric(metric_name)
                
                # Recolectar métricas personalizadas
                self._collect_custom_metrics()
                
                # Vaciar buffer si alcanza el tamaño de lote
                with self.buffer_lock:
                    if len(self.metrics_buffer) >= self.config.batch_size:
                        self._flush_buffer()
                
                time.sleep(self.config.collection_interval_seconds)
                
            except Exception as exc:
                self.logger._print_log("error", f"[METRICS-COLLECTOR] Error en recolección: {exc}", "metrics_collector.py", "_collection_loop", 192)
                time.sleep(self.config.collection_interval_seconds)
                
    def _collect_custom_metrics(self) -> None:
        """Recolecta métricas personalizadas del sistema."""
        try:
            import psutil
            
            # Métricas del sistema
            current_time = datetime.now()
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            self.add_metric('system.cpu_percent', cpu_percent, {'core': 'overall'}, {'source': 'psutil'})
            
            # Memoria
            memory = psutil.virtual_memory()
            self.add_metric('system.memory_percent', memory.percent, {'type': 'virtual'}, {'source': 'psutil'})
            self.add_metric('system.memory_used_mb', memory.used / (1024*1024), {'type': 'virtual'}, {'source': 'psutil'})
            
            # Disco
            disk = psutil.disk_usage('/')
            self.add_metric('system.disk_percent', disk.percent, {'mount': '/'}, {'source': 'psutil'})
            self.add_metric('system.disk_used_gb', disk.used / (1024*1024*1024), {'mount': '/'}, {'source': 'psutil'})
            
            # Red
            network = psutil.net_io_counters()
            self.add_metric('system.network_sent_mb', network.bytes_sent / (1024*1024), {'interface': 'overall'}, {'source': 'psutil'})
            self.add_metric('system.network_recv_mb', network.bytes_recv / (1024*1024), {'interface': 'overall'}, {'source': 'psutil'})
            
            # Procesos
            process_count = len(psutil.pids())
            self.add_metric('system.process_count', process_count, {'source': 'psutil'}, {'type': 'system'})
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al recolectar métricas personalizadas: {exc}", "metrics_collector.py", "_collect_custom_metrics", 226)
            
    def add_metric(self, 
                   metric_name: str, 
                   value: Union[float, int, str, bool],
                   tags: Optional[Dict[str, str]] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Añade una métrica al buffer.
        
        Args:
            metric_name: Nombre de la métrica
            value: Valor de la métrica
            tags: Etiquetas para clasificar la métrica
            metadata: Metadatos adicionales
        """
        metric_data = MetricData(
            timestamp=datetime.now(),
            metric_name=metric_name,
            value=value,
            tags=tags or {},
            metadata=metadata or {}
        )
        
        with self.buffer_lock:
            self.metrics_buffer.append(metric_data)
            
            # Limitar tamaño del buffer
            if len(self.metrics_buffer) > self.config.batch_size * 2:
                self._flush_buffer()
                
    def _flush_buffer(self) -> None:
        """Vacía el buffer de métricas a la base de datos."""
        if not self.metrics_buffer:
            return
            
        try:
            with self.buffer_lock:
                metrics_to_store = self.metrics_buffer.copy()
                self.metrics_buffer.clear()
                
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                
                for metric in metrics_to_store:
                    cursor.execute('''
                        INSERT INTO metrics (timestamp, metric_name, value, tags, metadata)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        metric.timestamp.isoformat(),
                        metric.metric_name,
                        metric.value,
                        json.dumps(metric.tags),
                        json.dumps(metric.metadata)
                    ))
                    
                conn.commit()
                
            self.logger._print_log("debug", f"[METRICS-COLLECTOR] Almacenadas {len(metrics_to_store)} métricas", "metrics_collector.py", "_flush_buffer", 273)
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al almacenar métricas: {exc}", "metrics_collector.py", "_flush_buffer", 277)
            
    def get_metrics(self, 
                   metric_name: Optional[str] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None,
                   tags: Optional[Dict[str, str]] = None) -> List[MetricData]:
        """
        Obtiene métricas de la base de datos.
        
        Args:
            metric_name: Filtrar por nombre de métrica
            start_time: Tiempo de inicio
            end_time: Tiempo de fin
            limit: Límite de resultados
            tags: Filtrar por etiquetas
        """
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                
                # Construir consulta
                query = "SELECT timestamp, metric_name, value, tags, metadata FROM metrics WHERE 1=1"
                params = []
                
                if metric_name:
                    query += " AND metric_name = ?"
                    params.append(metric_name)
                    
                if start_time:
                    query += " AND timestamp >= ?"
                    params.append(start_time.isoformat())
                    
                if end_time:
                    query += " AND timestamp <= ?"
                    params.append(end_time.isoformat())
                    
                if tags:
                    for key, value in tags.items():
                        query += f" AND tags LIKE ?"
                        params.append(f'%"{key}":"{value}"%')
                        
                query += " ORDER BY timestamp DESC"
                
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                    
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                metrics = []
                for row in rows:
                    metric_data = MetricData(
                        timestamp=datetime.fromisoformat(row[0]),
                        metric_name=row[1],
                        value=row[2],
                        tags=json.loads(row[3]) if row[3] else {},
                        metadata=json.loads(row[4]) if row[4] else {}
                    )
                    metrics.append(metric_data)
                    
                return metrics
                
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al obtener métricas: {exc}", "metrics_collector.py", "get_metrics", 332)
            return []
            
    def get_metric_statistics(self, 
                              metric_name: str,
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Obtiene estadísticas de una métrica específica.
        
        Args:
            metric_name: Nombre de la métrica
            start_time: Tiempo de inicio
            end_time: Tiempo de fin
        """
        metrics = self.get_metrics(metric_name, start_time, end_time)
        
        if not metrics:
            return {}
            
        values = [m.value for m in metrics if isinstance(m.value, (int, float))]
        
        if not values:
            return {}
            
        import statistics
        
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
            'first_timestamp': metrics[0].timestamp.isoformat(),
            'last_timestamp': metrics[-1].timestamp.isoformat()
        }
        
    def get_metric_names(self) -> List[str]:
        """Obtiene todos los nombres de métricas disponibles."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT metric_name FROM metrics ORDER BY metric_name")
                rows = cursor.fetchall()
                return [row[0] for row in rows]
                
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al obtener nombres de métricas: {exc}", "metrics_collector.py", "get_metric_names", 378)
            return []
            
    def cleanup_old_metrics(self) -> None:
        """Limpia métricas antiguas según la configuración de retención."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
            
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff_date.isoformat(),))
                deleted_count = cursor.rowcount
                conn.commit()
                
            # Limitar métricas por nombre
            for metric_name in self.get_metric_names():
                metrics = self.get_metrics(metric_name, limit=self.config.max_metrics_per_name)
                if len(metrics) > self.config.max_metrics_per_name:
                    # Eliminar las más antiguas
                    cutoff_time = metrics[-1].timestamp
                    with sqlite3.connect(self.config.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM metrics WHERE metric_name = ? AND timestamp < ?", 
                                     (metric_name, cutoff_time.isoformat()))
                        conn.commit()
                        
            self.logger._print_log("info", f"[METRICS-COLLECTOR] Limpieza completada: {deleted_count} métricas eliminadas", "metrics_collector.py", "cleanup_old_metrics", 402)
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error en limpieza de métricas: {exc}", "metrics_collector.py", "cleanup_old_metrics", 406)
            
    def backup_metrics(self) -> str:
        """Realiza una copia de seguridad de la base de datos de métricas."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"metrics_backup_{timestamp}.db"
            backup_path = os.path.join(self.config.backup_path, backup_file)
            
            # Copiar la base de datos
            import shutil
            shutil.copy2(self.config.db_path, backup_path)
            
            self.logger._print_log("info", f"[METRICS-COLLECTOR] Copia de seguridad creada: {backup_path}", "metrics_collector.py", "backup_metrics", 422)
            return backup_path
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error en copia de seguridad: {exc}", "metrics_collector.py", "backup_metrics", 426)
            raise
            
    def export_metrics(self, 
                      filepath: str,
                      metric_name: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> None:
        """
        Exporta métricas a un archivo JSON.
        
        Args:
            filepath: Ruta del archivo de exportación
            metric_name: Filtrar por nombre de métrica
            start_time: Tiempo de inicio
            end_time: Tiempo de fin
        """
        metrics = self.get_metrics(metric_name, start_time, end_time)
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_metrics': len(metrics),
            'metrics': [metric.to_dict() for metric in metrics]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
            
        self.logger._print_log("info", f"[METRICS-COLLECTOR] Métricas exportadas a {filepath}", "metrics_collector.py", "export_metrics", 453)
        
    def get_collector_status(self) -> Dict[str, Any]:
        """Obtiene el estado actual del recolector de métricas."""
        with self.buffer_lock:
            buffer_size = len(self.metrics_buffer)
            
        return {
            'is_running': self.is_running,
            'buffer_size': buffer_size,
            'config': self.config.to_dict(),
            'database_path': self.config.db_path,
            'total_metrics': self._get_total_metrics_count(),
            'metric_names': self.get_metric_names(),
            'last_cleanup': self._get_last_cleanup_time()
        }
        
    def _get_total_metrics_count(self) -> int:
        """Obtiene el total de métricas en la base de datos."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM metrics")
                return cursor.fetchone()[0]
        except Exception:
            return 0
            
    def _get_last_cleanup_time(self) -> Optional[str]:
        """Obtiene la última fecha de limpieza."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(timestamp) FROM metrics")
                result = cursor.fetchone()[0]
                return result if result else None
        except Exception:
            return None
            
    def clear_all_metrics(self) -> None:
        """Elimina todas las métricas de la base de datos."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metrics")
                conn.commit()
                
            with self.buffer_lock:
                self.metrics_buffer.clear()
                
            self.logger._print_log("info", "[METRICS-COLLECTOR] Todas las métricas eliminadas", "metrics_collector.py", "clear_all_metrics", 502)
            
        except Exception as exc:
            self.logger._print_log("error", f"[METRICS-COLLECTOR] Error al eliminar métricas: {exc}", "metrics_collector.py", "clear_all_metrics", 506)
            
    def __enter__(self):
        """Context manager entry."""
        self.start_collection()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_collection()


# Instancia global única
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Obtiene la instancia global del recolector de métricas."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def start_metrics_collection() -> None:
    """Inicia la recolección de métricas globales."""
    collector = get_metrics_collector()
    collector.start_collection()


def stop_metrics_collection() -> None:
    """Detiene la recolección de métricas globales."""
    collector = get_metrics_collector()
    collector.stop_collection()