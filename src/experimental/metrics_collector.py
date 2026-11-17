"""
Sistema de recoleccion de metricas para JARVIS.

Este modulo proporciona herramientas para recopilar, almacenar y gestionar
metricas del sistema de manera estructurada y persistente.
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

from src.core.log import get_logger


@dataclass
class MetricData:
    """Datos de una metrica individual."""
    
    timestamp: datetime
    metric_name: str
    value: Union[float, int, str, bool]
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte los datos de la metrica a un diccionario."""
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
    """Configuracion para la recoleccion de metricas."""
    
    # Configuracion de base de datos
    db_path: str = "data/metrics/jarvis_metrics.db"
    backup_path: str = "data/metrics/backups/"
    
    # Configuracion de retencion
    retention_days: int = 30
    max_metrics_per_name: int = 10000
    
    # Configuracion de recoleccion
    collection_interval_seconds: float = 60.0
    batch_size: int = 100
    
    # Metricas predeterminadas a recolectar
    default_metrics: List[str] = field(default_factory=lambda: [
        'system.cpu_percent',
        'system.memory_percent',
        'system.disk_percent',
        'jarvis.actions_executed',
        'jarvis.actions_failed',
        'jarvis.response_time'
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuracion a un diccionario."""
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
    """Recolector de metricas para JARVIS."""
    
    def __init__(self, config: Optional[MetricConfig] = None):
        """
        Inicializa el recolector de metricas.
        
        Args:
            config: Configuracion personalizada para la recoleccion
        """
        self.logger = get_logger("MetricsCollector")
        self.config = config or MetricConfig()
        
        # Estado del recolector
        self.is_running = False
        self.collection_thread: Optional[threading.Thread] = None
        
        # Buffer para metricas en lote
        self.metrics_buffer: List[MetricData] = []
        self.buffer_lock = threading.Lock()
        
        # Inicializar base de datos
        self._initialize_database()
        
        # Inicializar directorios
        self._ensure_directories()
        
        # Inicializacion
        self.logger.info("[METRICS-COLLECTOR] Recolector de metricas inicializado")
        
    def _initialize_database(self) -> None:
        """Inicializa la base de datos SQLite para metricas."""
        try:
            # Crear directorio si no existe
            db_dir = os.path.dirname(self.config.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            # Conectar y crear tablas
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                
                # Tabla principal de metricas
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
                
                # Indices para rendimiento
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_metric_name ON metrics(metric_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metrics(metric_name, timestamp)')
                
                conn.commit()
                
            self.logger.info(f"[METRICS-COLLECTOR] Base de datos inicializada en {self.config.db_path}")
            
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error al inicializar base de datos: {exc}")
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
            self.logger.error(f"[METRICS-COLLECTOR] Error al crear directorios: {exc}")
            
    def start_collection(self) -> None:
        """Inicia la recoleccion continua de metricas."""
        if self.is_running:
            self.logger.warning("[METRICS-COLLECTOR] La recoleccion ya esta en ejecucion")
            return
            
        self.is_running = True
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
        
        self.logger.info(f"[METRICS-COLLECTOR] Recoleccion iniciada con intervalo de {self.config.collection_interval_seconds}s")
        
    def stop_collection(self) -> None:
        """Detiene la recoleccion de metricas."""
        if not self.is_running:
            self.logger.warning("[METRICS-COLLECTOR] La recoleccion no esta en ejecucion")
            return
            
        self.is_running = False
        
        # Vaciar buffer final
        self._flush_buffer()
        
        if self.collection_thread and self.collection_thread.is_alive():
            self.collection_thread.join(timeout=5.0)
            
        self.logger.info("[METRICS-COLLECTOR] Recoleccion detenida")
        
    def _collection_loop(self) -> None:
        """Bucle principal de recoleccion de metricas."""
        while self.is_running:
            try:
                # Recolectar metricas predeterminadas
                for metric_name in self.config.default_metrics:
                    self.collect_metric(metric_name)
                
                # Recolectar metricas personalizadas
                self._collect_custom_metrics()
                
                # Vaciar buffer si alcanza el tamano de lote
                with self.buffer_lock:
                    if len(self.metrics_buffer) >= self.config.batch_size:
                        self._flush_buffer()
                
                time.sleep(self.config.collection_interval_seconds)
                
            except Exception as exc:
                self.logger.error(f"[METRICS-COLLECTOR] Error en recoleccion: {exc}")
                time.sleep(self.config.collection_interval_seconds)
                
    def _collect_custom_metrics(self) -> None:
        """Recolecta metricas personalizadas del sistema."""
        try:
            import psutil
            
            # Metricas del sistema
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
            self.logger.error(f"[METRICS-COLLECTOR] Error al recolectar metricas personalizadas: {exc}")
            
    def add_metric(self, 
                   metric_name: str, 
                   value: Union[float, int, str, bool],
                   tags: Optional[Dict[str, str]] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Anade una metrica al buffer.
        
        Args:
            metric_name: Nombre de la metrica
            value: Valor de la metrica
            tags: Etiquetas para clasificar la metrica
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
            
            # Limitar tamano del buffer
            if len(self.metrics_buffer) > self.config.batch_size * 2:
                self._flush_buffer()
                
    def _flush_buffer(self) -> None:
        """Vacia el buffer de metricas a la base de datos."""
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
                
            self.logger.debug(f"[METRICS-COLLECTOR] Almacenadas {len(metrics_to_store)} metricas")
            
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error al almacenar metricas: {exc}")
            
    def get_metrics(self, 
                   metric_name: Optional[str] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None,
                   tags: Optional[Dict[str, str]] = None) -> List[MetricData]:
        """
        Obtiene metricas de la base de datos.
        
        Args:
            metric_name: Filtrar por nombre de metrica
            start_time: Tiempo de inicio
            end_time: Tiempo de fin
            limit: Limite de resultados
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
            self.logger.error(f"[METRICS-COLLECTOR] Error al obtener metricas: {exc}")
            return []
            
    def get_metric_statistics(self, 
                              metric_name: str,
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Obtiene estadisticas de una metrica especifica.
        
        Args:
            metric_name: Nombre de la metrica
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
        """Obtiene todos los nombres de metricas disponibles."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT metric_name FROM metrics ORDER BY metric_name")
                rows = cursor.fetchall()
                return [row[0] for row in rows]
                
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error al obtener nombres de metricas: {exc}")
            return []
            
    def cleanup_old_metrics(self) -> None:
        """Limpia metricas antiguas segun la configuracion de retencion."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
            
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff_date.isoformat(),))
                deleted_count = cursor.rowcount
                conn.commit()
                
            # Limitar metricas por nombre
            for metric_name in self.get_metric_names():
                metrics = self.get_metrics(metric_name, limit=self.config.max_metrics_per_name)
                if len(metrics) > self.config.max_metrics_per_name:
                    # Eliminar las mas antiguas
                    cutoff_time = metrics[-1].timestamp
                    with sqlite3.connect(self.config.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM metrics WHERE metric_name = ? AND timestamp < ?", 
                                     (metric_name, cutoff_time.isoformat()))
                        conn.commit()
                        
            self.logger.info(f"[METRICS-COLLECTOR] Limpieza completada: {deleted_count} metricas eliminadas")
            
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error en limpieza de metricas: {exc}")
            
    def backup_metrics(self) -> str:
        """Realiza una copia de seguridad de la base de datos de metricas."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"metrics_backup_{timestamp}.db"
            backup_path = os.path.join(self.config.backup_path, backup_file)
            
            # Copiar la base de datos
            import shutil
            shutil.copy2(self.config.db_path, backup_path)
            
            self.logger.info(f"[METRICS-COLLECTOR] Copia de seguridad creada: {backup_path}")
            return backup_path
            
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error en copia de seguridad: {exc}")
            raise
            
    def export_metrics(self, 
                      filepath: str,
                      metric_name: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> None:
        """
        Exporta metricas a un archivo JSON.
        
        Args:
            filepath: Ruta del archivo de exportacion
            metric_name: Filtrar por nombre de metrica
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
            
        self.logger.info(f"[METRICS-COLLECTOR] Metricas exportadas a {filepath}")
        
    def get_collector_status(self) -> Dict[str, Any]:
        """Obtiene el estado actual del recolector de metricas."""
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
        """Obtiene el total de metricas en la base de datos."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM metrics")
                return cursor.fetchone()[0]
        except Exception:
            return 0
            
    def _get_last_cleanup_time(self) -> Optional[str]:
        """Obtiene la ultima fecha de limpieza."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(timestamp) FROM metrics")
                result = cursor.fetchone()[0]
                return result if result else None
        except Exception:
            return None
            
    def clear_all_metrics(self) -> None:
        """Elimina todas las metricas de la base de datos."""
        try:
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metrics")
                conn.commit()
                
            with self.buffer_lock:
                self.metrics_buffer.clear()
                
            self.logger.info("[METRICS-COLLECTOR] Todas las metricas eliminadas")
            
        except Exception as exc:
            self.logger.error(f"[METRICS-COLLECTOR] Error al eliminar metricas: {exc}")
            
    def __enter__(self):
        """Context manager entry."""
        self.start_collection()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_collection()


# Instancia global unica
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Obtiene la instancia global del recolector de metricas."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def start_metrics_collection() -> None:
    """Inicia la recoleccion de metricas globales."""
    collector = get_metrics_collector()
    collector.start_collection()


def stop_metrics_collection() -> None:
    """Detiene la recoleccion de metricas globales."""
    collector = get_metrics_collector()
    collector.stop_collection()