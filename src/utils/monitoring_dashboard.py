"""
Sistema de dashboard de monitoreo para JARVIS.

Este módulo proporciona una interfaz unificada para visualizar y gestionar
todo el sistema de monitoreo de rendimiento, incluyendo métricas, salud
y alertas.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from src.utils.logger import get_logger
from src.utils.performance_monitor import PerformanceMonitor, PerformanceAlert
from src.utils.health_checker import HealthChecker, HealthCheck, HealthStatus
from src.utils.metrics_collector import MetricsCollector, MetricData


@dataclass
class DashboardConfig:
    """Configuración del dashboard de monitoreo."""
    
    # Configuración de actualización
    update_interval_seconds: float = 5.0
    max_alerts_display: int = 50
    max_metrics_display: int = 100
    
    # Configuración de visualización
    display_cpu: bool = True
    display_memory: bool = True
    display_disk: bool = True
    display_network: bool = True
    display_components: bool = True
    
    # Umbrales de alerta en dashboard
    cpu_warning_threshold: float = 80.0
    cpu_critical_threshold: float = 95.0
    memory_warning_threshold: float = 85.0
    memory_critical_threshold: float = 95.0
    disk_warning_threshold: float = 85.0
    disk_critical_threshold: float = 95.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a un diccionario."""
        return {
            'update_interval_seconds': self.update_interval_seconds,
            'max_alerts_display': self.max_alerts_display,
            'max_metrics_display': self.max_metrics_display,
            'display_cpu': self.display_cpu,
            'display_memory': self.display_memory,
            'display_disk': self.display_disk,
            'display_network': self.display_network,
            'display_components': self.display_components,
            'cpu_warning_threshold': self.cpu_warning_threshold,
            'cpu_critical_threshold': self.cpu_critical_threshold,
            'memory_warning_threshold': self.memory_warning_threshold,
            'memory_critical_threshold': self.memory_critical_threshold,
            'disk_warning_threshold': self.disk_warning_threshold,
            'disk_critical_threshold': self.disk_critical_threshold
        }


@dataclass
class DashboardData:
    """Datos del dashboard en un punto en el tiempo."""
    
    timestamp: datetime
    current_metrics: Dict[str, Any]
    health_status: Dict[str, Any]
    recent_alerts: List[Dict[str, Any]]
    system_summary: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte los datos del dashboard a un diccionario."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'current_metrics': self.current_metrics,
            'health_status': self.health_status,
            'recent_alerts': self.recent_alerts,
            'system_summary': self.system_summary
        }


class MonitoringDashboard:
    """Dashboard unificado de monitoreo para JARVIS."""
    
    def __init__(self, 
                 config: Optional[DashboardConfig] = None,
                 performance_monitor: Optional[PerformanceMonitor] = None,
                 health_checker: Optional[HealthChecker] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        """
        Inicializa el dashboard de monitoreo.
        
        Args:
            config: Configuración del dashboard
            performance_monitor: Instancia del monitor de rendimiento
            health_checker: Instancia del verificador de salud
            metrics_collector: Instancia del recolector de métricas
        """
        self.logger = get_logger("MonitoringDashboard")
        self.config = config or DashboardConfig()
        
        # Componentes de monitoreo
        self.performance_monitor = performance_monitor
        self.health_checker = health_checker
        self.metrics_collector = metrics_collector
        
        # Estado del dashboard
        self.is_running = False
        self.dashboard_thread: Optional[threading.Thread] = None
        
        # Datos del dashboard
        self.current_dashboard_data: Optional[DashboardData] = None
        self.dashboard_history: List[DashboardData] = []
        self.max_history_size = 1000
        
        # Callbacks para actualizaciones
        self.update_callbacks: List[Callable[[DashboardData], None]] = []
        
        # Inicialización
        self.logger._print_log("info", "[MONITORING-DASHBOARD] Dashboard de monitoreo inicializado", "monitoring_dashboard.py", "__init__", 85)
        
    def start_dashboard(self) -> None:
        """Inicia el dashboard de monitoreo."""
        if self.is_running:
            self.logger._print_log("warning", "[MONITORING-DASHBOARD] El dashboard ya está en ejecución", "monitoring_dashboard.py", "start_dashboard", 92)
            return
            
        self.is_running = True
        self.dashboard_thread = threading.Thread(target=self._dashboard_loop, daemon=True)
        self.dashboard_thread.start()
        
        self.logger._print_log("info", f"[MONITORING-DASHBOARD] Dashboard iniciado con intervalo de {self.config.update_interval_seconds}s", "monitoring_dashboard.py", "start_dashboard", 98)
        
    def stop_dashboard(self) -> None:
        """Detiene el dashboard de monitoreo."""
        if not self.is_running:
            self.logger._print_log("warning", "[MONITORING-DASHBOARD] El dashboard no está en ejecución", "monitoring_dashboard.py", "stop_dashboard", 105)
            return
            
        self.is_running = False
        
        if self.dashboard_thread and self.dashboard_thread.is_alive():
            self.dashboard_thread.join(timeout=5.0)
            
        self.logger._print_log("info", "[MONITORING-DASHBOARD] Dashboard detenido", "monitoring-dashboard.py", "stop_dashboard", 111)
        
    def _dashboard_loop(self) -> None:
        """Bucle principal de actualización del dashboard."""
        while self.is_running:
            try:
                # Actualizar datos del dashboard
                dashboard_data = self._update_dashboard_data()
                self.current_dashboard_data = dashboard_data
                
                # Agregar al historial
                self.dashboard_history.append(dashboard_data)
                if len(self.dashboard_history) > self.max_history_size:
                    self.dashboard_history = self.dashboard_history[-self.max_history_size:]
                
                # Notificar callbacks
                for callback in self.update_callbacks:
                    try:
                        callback(dashboard_data)
                    except Exception as exc:
                        self.logger._print_log("error", f"[MONITORING-DASHBOARD] Error en callback de actualización: {exc}", "monitoring_dashboard.py", "_dashboard_loop", 145)
                
                time.sleep(self.config.update_interval_seconds)
                
            except Exception as exc:
                self.logger._print_log("error", f"[MONITORING-DASHBOARD] Error en actualización: {exc}", "monitoring_dashboard.py", "_dashboard_loop", 151)
                time.sleep(self.config.update_interval_seconds)
                
    def _update_dashboard_data(self) -> DashboardData:
        """Actualiza los datos del dashboard."""
        timestamp = datetime.now()
        
        # Obtener métricas de rendimiento
        current_metrics = self._get_current_performance_metrics()
        
        # Obtener estado de salud
        health_status = self._get_current_health_status()
        
        # Obtener alertas recientes
        recent_alerts = self._get_recent_alerts()
        
        # Generar resumen del sistema
        system_summary = self._generate_system_summary(current_metrics, health_status, recent_alerts)
        
        return DashboardData(
            timestamp=timestamp,
            current_metrics=current_metrics,
            health_status=health_status,
            recent_alerts=recent_alerts,
            system_summary=system_summary
        )
        
    def _get_current_performance_metrics(self) -> Dict[str, Any]:
        """Obtiene las métricas de rendimiento actuales."""
        metrics = {}
        
        if self.performance_monitor:
            current_perf_metrics = self.performance_monitor.get_current_metrics()
            if current_perf_metrics:
                metrics = current_perf_metrics.to_dict()
                
                # Aplicar configuración de visualización
                if not self.config.display_cpu:
                    metrics.pop('cpu_percent', None)
                if not self.config.display_memory:
                    metrics.pop('memory_percent', None)
                    metrics.pop('memory_used_mb', None)
                    metrics.pop('memory_total_mb', None)
                if not self.config.display_disk:
                    metrics.pop('disk_percent', None)
                    metrics.pop('disk_used_gb', None)
                    metrics.pop('disk_total_gb', None)
                if not self.config.display_network:
                    metrics.pop('network_sent_mb', None)
                    metrics.pop('network_recv_mb', None)
        
        return metrics
        
    def _get_current_health_status(self) -> Dict[str, Any]:
        """Obtiene el estado de salud actual."""
        health_status = {}
        
        if self.health_checker:
            health_summary = self.health_checker.get_health_summary()
            
            # Filtrar por configuración de visualización
            if not self.config.display_components:
                health_summary.pop('components', None)
            
            health_status = health_summary
            
        return health_status
        
    def _get_recent_alerts(self) -> List[Dict[str, Any]]:
        """Obtiene alertas recientes."""
        alerts = []
        
        if self.performance_monitor:
            perf_alerts = self.performance_monitor.get_alerts(limit=self.config.max_alerts_display)
            alerts.extend([alert.to_dict() for alert in perf_alerts])
            
        # Ordenar por timestamp (más recientes primero)
        alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return alerts[:self.config.max_alerts_display]
        
    def _generate_system_summary(self, 
                               current_metrics: Dict[str, Any],
                               health_status: Dict[str, Any],
                               recent_alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Genera un resumen del estado del sistema."""
        
        # Determinar estado general
        overall_status = "healthy"
        
        # Verificar alertas críticas
        critical_alerts = [alert for alert in recent_alerts if alert.get('severity') == 'critical']
        if critical_alerts:
            overall_status = "critical"
        elif recent_alerts:
            overall_status = "warning"
            
        # Verificar estado de salud
        if health_status.get('overall_status') == 'critical':
            overall_status = "critical"
        elif health_status.get('overall_status') == 'warning' and overall_status != "critical":
            overall_status = "warning"
            
        # Contar alertas por tipo
        alert_counts = {}
        for alert in recent_alerts:
            alert_type = alert.get('alert_type', 'unknown')
            alert_counts[alert_type] = alert_counts.get(alert_type, 0) + 1
            
        return {
            'overall_status': overall_status,
            'total_alerts': len(recent_alerts),
            'critical_alerts': len(critical_alerts),
            'alert_counts': alert_counts,
            'last_update': datetime.now().isoformat(),
            'monitoring_active': self.is_running
        }
        
    def get_dashboard_data(self) -> Optional[DashboardData]:
        """Obtiene los datos actuales del dashboard."""
        return self.current_dashboard_data
        
    def get_dashboard_history(self, limit: Optional[int] = None) -> List[DashboardData]:
        """Obtiene el historial del dashboard."""
        if limit:
            return self.dashboard_history[-limit:]
        return self.dashboard_history
        
    def add_update_callback(self, callback: Callable[[DashboardData], None]) -> None:
        """Agrega un callback para recibir actualizaciones del dashboard."""
        self.update_callbacks.append(callback)
        
    def remove_update_callback(self, callback: Callable[[DashboardData], None]) -> None:
        """Remueve un callback de actualizaciones del dashboard."""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)
            
    def export_dashboard_report(self, filepath: str, include_history: bool = False) -> None:
        """Exporta un reporte del dashboard a un archivo JSON."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'config': self.config.to_dict(),
            'current_data': self.current_dashboard_data.to_dict() if self.current_dashboard_data else None,
            'system_summary': self.current_dashboard_data.system_summary if self.current_dashboard_data else {}
        }
        
        if include_history:
            report['history'] = [data.to_dict() for data in self.dashboard_history]
            
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        self.logger._print_log("info", f"[MONITORING-DASHBOARD] Reporte del dashboard exportado a {filepath}", "monitoring_dashboard.py", "export_dashboard_report", 248)
        
    def get_system_health_score(self) -> float:
        """Calcula un puntaje de salud del sistema (0-100)."""
        if not self.current_dashboard_data:
            return 0.0
            
        summary = self.current_dashboard_data.system_summary
        overall_status = summary.get('overall_status', 'unknown')
        
        if overall_status == 'healthy':
            return 100.0
        elif overall_status == 'warning':
            return 70.0
        elif overall_status == 'critical':
            return 30.0
        else:
            return 0.0
            
    def get_critical_metrics(self) -> List[str]:
        """Obtiene métricas críticas que requieren atención."""
        critical_metrics = []
        
        if self.current_dashboard_data:
            metrics = self.current_dashboard_data.current_metrics
            
            # CPU crítica
            if self.config.display_cpu and metrics.get('cpu_percent', 0) >= self.config.cpu_critical_threshold:
                critical_metrics.append(f"CPU: {metrics['cpu_percent']:.1f}%")
                
            # Memoria crítica
            if self.config.display_memory and metrics.get('memory_percent', 0) >= self.config.memory_critical_threshold:
                critical_metrics.append(f"Memoria: {metrics['memory_percent']:.1f}%")
                
            # Disco crítico
            if self.config.display_disk and metrics.get('disk_percent', 0) >= self.config.disk_critical_threshold:
                critical_metrics.append(f"Disco: {metrics['disk_percent']:.1f}%")
                
        return critical_metrics
        
    def get_unhealthy_components(self) -> List[str]:
        """Obtiene componentes no saludables."""
        unhealthy = []
        
        if self.current_dashboard_data:
            health_status = self.current_dashboard_data.health_status
            components = health_status.get('components', [])
            
            for component in components:
                if component.get('status') != 'healthy':
                    unhealthy.append(component.get('component_name', 'unknown'))
                    
        return unhealthy
        
    def clear_dashboard_history(self) -> None:
        """Limpia el historial del dashboard."""
        self.dashboard_history.clear()
        self.logger._print_log("info", "[MONITORING-DASHBOARD] Historial del dashboard limpiado", "monitoring_dashboard.py", "clear_dashboard_history", 285)
        
    def __enter__(self):
        """Context manager entry."""
        self.start_dashboard()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_dashboard()


# Instancia global única
_dashboard: Optional[MonitoringDashboard] = None


def get_monitoring_dashboard() -> MonitoringDashboard:
    """Obtiene la instancia global del dashboard de monitoreo."""
    global _dashboard
    if _dashboard is None:
        _dashboard = MonitoringDashboard()
    return _dashboard


def start_monitoring_dashboard() -> None:
    """Inicia el dashboard de monitoreo global."""
    dashboard = get_monitoring_dashboard()
    dashboard.start_dashboard()


def stop_monitoring_dashboard() -> None:
    """Detiene el dashboard de monitoreo global."""
    dashboard = get_monitoring_dashboard()
    dashboard.stop_dashboard()