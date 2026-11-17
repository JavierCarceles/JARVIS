"""
Health Monitor for JARVIS System
Comprehensive health monitoring with proactive error detection
"""

import time
import threading
import logging
import psutil
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import queue

class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class ComponentType(Enum):
    """System component types"""
    CORE = "core"
    DATABASE = "database"
    NETWORK = "network"
    MEMORY = "memory"
    DISK = "disk"
    PROCESS = "process"
    EXTERNAL = "external"

class HealthMetric:
    """Individual health metric"""
    
    def __init__(self, name: str, value: float, threshold: float, 
                 component: ComponentType, metric_type: str = "gauge"):
        self.name = name
        self.value = value
        self.threshold = threshold
        self.component = component
        self.metric_type = metric_type
        self.timestamp = datetime.now()
    
    def is_healthy(self) -> bool:
        """Check if metric is within healthy bounds"""
        if self.metric_type == "gauge":
            return self.value <= self.threshold
        elif self.metric_type == "counter":
            return self.value >= self.threshold  # For counters, higher is better
        return True
    
    def get_status(self) -> HealthStatus:
        """Get health status based on value"""
        if self.is_healthy():
            return HealthStatus.HEALTHY
        elif self.value * 1.5 <= self.threshold:  # 50% over threshold
            return HealthStatus.CRITICAL
        else:
            return HealthStatus.WARNING

class HealthMonitor:
    """Main health monitoring system"""
    
    def __init__(self, db_path: str = "data/health_monitor.db", check_interval: float = 30.0):
        self.db_path = db_path
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self.metrics = {}
        self.health_callbacks = {}
        self.running = False
        self.monitor_thread = None
        self.alert_queue = queue.Queue()
        
        # Initialize database
        self._init_database()
        
        # Register default metrics
        self._register_default_metrics()
        
    def _init_database(self):
        """Initialize health monitoring database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Health metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS health_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    component TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    threshold REAL NOT NULL,
                    status TEXT NOT NULL,
                    metric_type TEXT DEFAULT 'gauge'
                )
            ''')
            
            # Health history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS health_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    component TEXT NOT NULL,
                    overall_status TEXT NOT NULL,
                    metrics_count INTEGER NOT NULL,
                    healthy_count INTEGER NOT NULL,
                    warning_count INTEGER NOT NULL,
                    critical_count INTEGER NOT NULL,
                    additional_data TEXT
                )
            ''')
            
            # Alerts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS health_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    component TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_timestamp DATETIME
                )
            ''')
            
            conn.commit()
    
    def _register_default_metrics(self):
        """Register default health metrics"""
        # System metrics
        self.register_metric("cpu_usage", 80.0, ComponentType.CORE, "gauge")
        self.register_metric("memory_usage", 85.0, ComponentType.MEMORY, "gauge")
        self.register_metric("disk_usage", 90.0, ComponentType.DISK, "gauge")
        self.register_metric("network_errors", 100.0, ComponentType.NETWORK, "counter")
        
    def register_metric(self, name: str, threshold: float, 
                       component: ComponentType, metric_type: str = "gauge"):
        """Register a health metric"""
        self.metrics[name] = {
            'threshold': threshold,
            'component': component,
            'metric_type': metric_type,
            'last_check': None,
            'status': HealthStatus.UNKNOWN
        }
        self.logger.info(f"Registered health metric: {name}")
    
    def register_health_callback(self, component: ComponentType, callback: Callable):
        """Register callback for health status changes"""
        if component not in self.health_callbacks:
            self.health_callbacks[component] = []
        self.health_callbacks[component].append(callback)
        self.logger.info(f"Registered health callback for: {component.value}")
    
    def check_metric(self, name: str, value: float) -> HealthMetric:
        """Check a specific metric"""
        if name not in self.metrics:
            raise ValueError(f"Unknown metric: {name}")
        
        metric_config = self.metrics[name]
        metric = HealthMetric(
            name=name,
            value=value,
            threshold=metric_config['threshold'],
            component=metric_config['component'],
            metric_type=metric_config['metric_type']
        )
        
        # Update metric status
        old_status = metric_config['status']
        new_status = metric.get_status()
        metric_config['status'] = new_status
        metric_config['last_check'] = datetime.now()
        
        # Log metric to database
        self._log_metric(metric)
        
        # Check for status changes and trigger callbacks
        if old_status != new_status:
            self._trigger_health_callbacks(metric_config['component'], name, old_status, new_status)
            self._create_alert(name, new_status)
        
        return metric
    
    def check_all_metrics(self) -> Dict[str, HealthMetric]:
        """Check all registered metrics"""
        results = {}
        
        # Check system metrics
        results['cpu_usage'] = self.check_metric("cpu_usage", psutil.cpu_percent(interval=1))
        results['memory_usage'] = self.check_metric("memory_usage", psutil.virtual_memory().percent)
        results['disk_usage'] = self.check_metric("disk_usage", psutil.disk_usage('/').percent)
        
        # Check network errors (simulate)
        network_errors = len(psutil.net_io_counters()._asdict().get('errin', 0))
        results['network_errors'] = self.check_metric("network_errors", network_errors)
        
        # Log overall health status
        self._log_health_summary(results)
        
        return results
    
    def _log_metric(self, metric: HealthMetric):
        """Log metric to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO health_metrics 
                (component, metric_name, value, threshold, status, metric_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (metric.component.value, metric.name, metric.value, 
                  metric.threshold, metric.get_status().value, metric.metric_type))
            conn.commit()
    
    def _log_health_summary(self, metrics: Dict[str, HealthMetric]):
        """Log overall health summary"""
        total_count = len(metrics)
        healthy_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.HEALTHY)
        warning_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.WARNING)
        critical_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.CRITICAL)
        
        # Determine overall status
        if critical_count > 0:
            overall_status = HealthStatus.CRITICAL.value
        elif warning_count > 0:
            overall_status = HealthStatus.WARNING.value
        else:
            overall_status = HealthStatus.HEALTHY.value
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO health_history 
                (component, overall_status, metrics_count, healthy_count, warning_count, critical_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('system', overall_status, total_count, healthy_count, warning_count, critical_count))
            conn.commit()
    
    def _trigger_health_callbacks(self, component: ComponentType, metric_name: str, 
                                 old_status: HealthStatus, new_status: HealthStatus):
        """Trigger registered health callbacks"""
        if component in self.health_callbacks:
            for callback in self.health_callbacks[component]:
                try:
                    callback(component, metric_name, old_status, new_status)
                except Exception as e:
                    self.logger.error(f"Health callback error: {e}")
    
    def _create_alert(self, metric_name: str, status: HealthStatus):
        """Create health alert"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO health_alerts 
                (component, alert_type, severity, message)
                VALUES (?, ?, ?, ?)
            ''', ('system', 'metric_threshold', status.value, 
                  f"Metric {metric_name} status changed to {status.value}"))
            conn.commit()
    
    def start_monitoring(self):
        """Start continuous health monitoring"""
        if self.running:
            self.logger.warning("Health monitor is already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Health monitoring started")
    
    def stop_monitoring(self):
        """Stop continuous health monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        self.logger.info("Health monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self.check_all_metrics()
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Health monitoring error: {e}")
                time.sleep(self.check_interval)
    
    def get_current_health(self) -> Dict[str, Any]:
        """Get current health status"""
        metrics = self.check_all_metrics()
        
        healthy_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.HEALTHY)
        warning_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.WARNING)
        critical_count = sum(1 for m in metrics.values() if m.get_status() == HealthStatus.CRITICAL)
        
        if critical_count > 0:
            overall_status = HealthStatus.CRITICAL
        elif warning_count > 0:
            overall_status = HealthStatus.WARNING
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            'overall_status': overall_status.value,
            'metrics_count': len(metrics),
            'healthy_count': healthy_count,
            'warning_count': warning_count,
            'critical_count': critical_count,
            'metrics': {name: {
                'value': metric.value,
                'status': metric.get_status().value,
                'threshold': metric.threshold
            } for name, metric in metrics.items()}
        }
    
    def get_health_history(self, hours: int = 24) -> List[Dict]:
        """Get health history for specified hours"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM health_history 
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            ''', (start_time,))
            
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in results]
    
    def get_active_alerts(self) -> List[Dict]:
        """Get list of active (unresolved) alerts"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM health_alerts 
                WHERE resolved = FALSE 
                ORDER BY timestamp DESC
            ''')
            
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in results]
    
    def resolve_alert(self, alert_id: int):
        """Resolve a specific alert"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE health_alerts 
                SET resolved = TRUE, resolved_timestamp = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (alert_id,))
            conn.commit()
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old health data"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Clean up old metrics
            cursor.execute('''
                DELETE FROM health_metrics 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            # Clean up old history
            cursor.execute('''
                DELETE FROM health_history 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            # Clean up resolved alerts older than cutoff
            cursor.execute('''
                DELETE FROM health_alerts 
                WHERE resolved = TRUE AND resolved_timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            self.logger.info(f"Cleaned up {deleted_count} old health records")
            return deleted_count
    
    def __str__(self):
        return f"HealthMonitor(db_path='{self.db_path}', metrics={len(self.metrics)}, running={self.running})"


def get_health_monitor():
    """Get a singleton instance of HealthMonitor"""
    if not hasattr(get_health_monitor, '_instance'):
        get_health_monitor._instance = HealthMonitor()
    return get_health_monitor._instance


def start_health_monitoring():
    """Start health monitoring"""
    monitor = get_health_monitor()
    return monitor.start()


def stop_health_monitoring():
    """Stop health monitoring"""
    monitor = get_health_monitor()
    return monitor.stop()