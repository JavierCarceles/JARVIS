"""
Sistema de verificacion de salud para JARVIS.

Este modulo proporciona herramientas para verificar el estado de los componentes
criticos del sistema y generar reportes de salud.
"""

import importlib
import inspect
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime, timedelta
import json
from enum import Enum

from src.core.log import get_logger


class HealthStatus(Enum):
    """Estados de salud de un componente."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Resultado de una verificacion de salud."""
    
    component_name: str
    status: HealthStatus
    message: str
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    response_time_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el resultado a un diccionario serializable."""
        return {
            'component_name': self.component_name,
            'status': self.status.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details,
            'response_time_ms': self.response_time_ms
        }


@dataclass
class HealthCheckConfig:
    """Configuracion para las verificaciones de salud."""
    
    # Tiempos de espera
    timeout_seconds: float = 10.0
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    
    # Umbrales de respuesta
    response_time_warning_ms: float = 1000.0
    response_time_critical_ms: float = 5000.0
    
    # Frecuencia de chequeo
    check_interval_seconds: float = 60.0
    
    # Componentes a verificar
    critical_components: List[str] = field(default_factory=lambda: [
        'action_registry',
        'planner',
        'memory',
        'network'
    ])
    
    optional_components: List[str] = field(default_factory=lambda: [
        'voice',
        'vision',
        'calibration'
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuracion a un diccionario."""
        return {
            'timeout_seconds': self.timeout_seconds,
            'retry_attempts': self.retry_attempts,
            'retry_delay_seconds': self.retry_delay_seconds,
            'response_time_warning_ms': self.response_time_warning_ms,
            'response_time_critical_ms': self.response_time_critical_ms,
            'check_interval_seconds': self.check_interval_seconds,
            'critical_components': self.critical_components,
            'optional_components': self.optional_components
        }


class HealthChecker:
    """Verificador de salud del sistema JARVIS."""
    
    def __init__(self, config: Optional[HealthCheckConfig] = None):
        """
        Inicializa el verificador de salud.
        
        Args:
            config: Configuracion personalizada para las verificaciones
        """
        self.logger = get_logger("HealthChecker")
        self.config = config or HealthCheckConfig()
        
        # Historial de verificaciones
        self.health_history: List[HealthCheck] = []
        self.max_history_size = 1000
        
        # Estado del checker
        self.is_running = False
        self.check_thread: Optional[threading.Thread] = None
        self.last_check_time: Optional[datetime] = None
        
        # Callbacks para notificaciones
        self.health_change_callbacks: List[Callable[[HealthCheck], None]] = []
        
        # Registro de componentes disponibles
        self.available_components: Dict[str, bool] = {}
        
        # Inicializacion
        self.logger.info("[HEALTH-CHECKER] Verificador de salud inicializado")
        
    def start_health_checks(self) -> None:
        """Inicia las verificaciones periodicas de salud."""
        if self.is_running:
            self.logger.warning("[HEALTH-CHECKER] Las verificaciones ya estan en ejecucion")
            return
            
        self.is_running = True
        self.check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.check_thread.start()
        
        self.logger.info(f"[HEALTH-CHECKER] Verificaciones iniciadas con intervalo de {self.config.check_interval_seconds}s")
        
    def stop_health_checks(self) -> None:
        """Detiene las verificaciones de salud."""
        if not self.is_running:
            self.logger.warning("[HEALTH-CHECKER] Las verificaciones no estan en ejecucion")
            return
            
        self.is_running = False
        if self.check_thread and self.check_thread.is_alive():
            self.check_thread.join(timeout=5.0)
            
        self.logger.info("[HEALTH-CHECKER] Verificaciones detenidas")
        
    def _health_check_loop(self) -> None:
        """Bucle principal de verificacion de salud."""
        while self.is_running:
            try:
                start_time = time.time()
                results = self.perform_comprehensive_health_check()
                
                # Procesar resultados y notificar cambios
                for result in results:
                    self._process_health_check(result)
                    self._notify_health_change(result)
                
                self.last_check_time = datetime.now()
                
                # Calcular tiempo de espera hasta la siguiente verificacion
                elapsed = time.time() - start_time
                sleep_time = max(0, self.config.check_interval_seconds - elapsed)
                time.sleep(sleep_time)
                
            except Exception as exc:
                self.logger.error(f"[HEALTH-CHECKER] Error en verificacion de salud: {exc}")
                time.sleep(self.config.check_interval_seconds)
                
    def perform_comprehensive_health_check(self) -> List[HealthCheck]:
        """Realiza una verificacion completa de salud de todos los componentes."""
        results = []
        
        # Verificar componentes criticos
        for component in self.config.critical_components:
            result = self.check_component_health(component)
            results.append(result)
            
        # Verificar componentes opcionales
        for component in self.config.optional_components:
            result = self.check_component_health(component)
            results.append(result)
            
        # Verificar sistema general
        system_result = self.check_system_health()
        results.append(system_result)
        
        return results
        
    def check_component_health(self, component_name: str) -> HealthCheck:
        """Verifica la salud de un componente especifico."""
        start_time = time.time()
        
        try:
            # Intentar importar el componente
            module_path = self._get_component_module_path(component_name)
            if module_path:
                try:
                    module = importlib.import_module(module_path)
                    
                    # Verificar si el componente tiene un metodo de autoverificacion
                    if hasattr(module, 'check_health'):
                        health_func = getattr(module, 'check_health')
                        if callable(health_func):
                            result = health_func()
                            if isinstance(result, dict):
                                return HealthCheck(
                                    component_name=component_name,
                                    status=HealthStatus(result.get('status', 'unknown')),
                                    message=result.get('message', 'Componente verificado'),
                                    timestamp=datetime.now(),
                                    details=result,
                                    response_time_ms=(time.time() - start_time) * 1000
                                )
                    
                    # Verificar si el componente tiene un metodo basico
                    if hasattr(module, 'get_instance') or hasattr(module, '__init__'):
                        return HealthCheck(
                            component_name=component_name,
                            status=HealthStatus.HEALTHY,
                            message=f"Componente {component_name} disponible",
                            timestamp=datetime.now(),
                            details={'module_path': module_path},
                            response_time_ms=(time.time() - start_time) * 1000
                        )
                        
                except ImportError as exc:
                    return HealthCheck(
                        component_name=component_name,
                        status=HealthStatus.CRITICAL,
                        message=f"Componente no importable: {exc}",
                        timestamp=datetime.now(),
                        details={'error': str(exc)},
                        response_time_ms=(time.time() - start_time) * 1000
                    )
                except Exception as exc:
                    return HealthCheck(
                        component_name=component_name,
                        status=HealthStatus.WARNING,
                        message=f"Componente con problemas: {exc}",
                        timestamp=datetime.now(),
                        details={'error': str(exc)},
                        response_time_ms=(time.time() - start_time) * 1000
                    )
            else:
                return HealthCheck(
                    component_name=component_name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Componente no encontrado: {component_name}",
                    timestamp=datetime.now(),
                    details={'component': component_name},
                    response_time_ms=(time.time() - start_time) * 1000
                )
                
        except Exception as exc:
            return HealthCheck(
                component_name=component_name,
                status=HealthStatus.CRITICAL,
                message=f"Error cr\u00edtico en verificaci\u00f3n: {exc}",
                timestamp=datetime.now(),
                details={'error': str(exc)},
                response_time_ms=(time.time() - start_time) * 1000
            )
            
    def check_system_health(self) -> HealthCheck:
        """Verifica la salud general del sistema."""
        start_time = time.time()
        
        try:
            import sys
            import psutil
            
            # Verificar recursos del sistema
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determinar estado del sistema
            status = HealthStatus.HEALTHY
            message = "Sistema operativo saludable"
            details = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'python_version': sys.version,
                'platform': sys.platform
            }
            
            # Evaluar umbrales
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
                status = HealthStatus.CRITICAL
                message = "Sistema con recursos cr\u00edticos"
            elif cpu_percent > 70 or memory.percent > 70 or disk.percent > 70:
                status = HealthStatus.WARNING
                message = "Sistema con recursos limitados"
                
            return HealthCheck(
                component_name="system",
                status=status,
                message=message,
                timestamp=datetime.now(),
                details=details,
                response_time_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as exc:
            return HealthCheck(
                component_name="system",
                status=HealthStatus.CRITICAL,
                message=f"Error en verificaci\u00f3n del sistema: {exc}",
                timestamp=datetime.now(),
                details={'error': str(exc)},
                response_time_ms=(time.time() - start_time) * 1000
            )
            
    def _get_component_module_path(self, component_name: str) -> Optional[str]:
        """Obtiene la ruta del modulo para un componente."""
        # Mapeo de nombres de componentes a rutas de modulos
        component_map = {
            'action_registry': 'src.hands.actions.action_registry',
            'planner': 'src.hands.planner.planner',
            'memory': 'src.memory.world_state',
            'network': 'src.network.client',
            'voice': 'src.voice.synthesizer',
            'vision': 'src.vision.detector',
            'calibration': 'src.hands.calibration.calibration_manager'
        }
        
        return component_map.get(component_name)
        
    def _process_health_check(self, result: HealthCheck) -> None:
        """Procesa un resultado de verificacion de salud."""
        # Agregar al historial
        self.health_history.append(result)
        
        # Mantener tamano maximo del historial
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size:]
            
        # Actualizar estado del componente
        self.available_components[result.component_name] = result.status == HealthStatus.HEALTHY
        
        # Loggear resultado
        log_level = "error" if result.status == HealthStatus.CRITICAL else "warning" if result.status == HealthStatus.WARNING else "info"
        self.logger.info(f"[HEALTH-CHECKER] {result.component_name}: {result.status.value} - {result.message}")
        
    def _notify_health_change(self, result: HealthCheck) -> None:
        """Notifica callbacks sobre cambios en la salud."""
        for callback in self.health_change_callbacks:
            try:
                callback(result)
            except Exception as exc:
                self.logger.error(f"[HEALTH-CHECKER] Error en callback de salud: {exc}")
                
    def add_health_change_callback(self, callback: Callable[[HealthCheck], None]) -> None:
        """Agrega un callback para recibir notificaciones de cambios de salud."""
        self.health_change_callbacks.append(callback)
        
    def remove_health_change_callback(self, callback: Callable[[HealthCheck], None]) -> None:
        """Remueve un callback de notificaciones de salud."""
        if callback in self.health_change_callbacks:
            self.health_change_callbacks.remove(callback)
            
    def get_health_status(self, component_name: Optional[str] = None) -> Union[HealthCheck, List[HealthCheck]]:
        """Obtiene el estado de salud de un componente o todos los componentes."""
        if component_name:
            for check in self.health_history:
                if check.component_name == component_name:
                    return check
            return HealthCheck(
                component_name=component_name,
                status=HealthStatus.UNKNOWN,
                message="No hay informaci\u00f3n de salud disponible",
                timestamp=datetime.now()
            )
        else:
            # Devolver los resultados mas recientes de cada componente
            component_results = {}
            for check in reversed(self.health_history):
                if check.component_name not in component_results:
                    component_results[check.component_name] = check
                    
            return list(component_results.values())
            
    def get_health_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen del estado de salud actual."""
        current_checks = self.get_health_status()
        
        if isinstance(current_checks, HealthCheck):
            current_checks = [current_checks]
            
        # Contar por estado
        status_counts = {status.value: 0 for status in HealthStatus}
        for check in current_checks:
            status_counts[check.status.value] += 1
            
        # Determinar estado general
        if status_counts[HealthStatus.CRITICAL.value] > 0:
            overall_status = HealthStatus.CRITICAL
        elif status_counts[HealthStatus.WARNING.value] > 0:
            overall_status = HealthStatus.WARNING
        else:
            overall_status = HealthStatus.HEALTHY
            
        return {
            'overall_status': overall_status.value,
            'status_counts': status_counts,
            'total_components': len(current_checks),
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'monitoring_active': self.is_running,
            'components': [check.to_dict() for check in current_checks]
        }
        
    def get_component_health_history(self, component_name: str, limit: Optional[int] = None) -> List[HealthCheck]:
        """Obtiene el historial de salud de un componente especifico."""
        history = [check for check in self.health_history if check.component_name == component_name]
        if limit:
            history = history[-limit:]
        return history
        
    def export_health_report(self, filepath: str, include_history: bool = False) -> None:
        """Exporta un reporte de salud a un archivo JSON."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': self.get_health_summary(),
            'config': self.config.to_dict()
        }
        
        if include_history:
            report['history'] = [check.to_dict() for check in self.health_history]
            
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"[HEALTH-CHECKER] Reporte de salud exportado a {filepath}")
        
    def clear_history(self) -> None:
        """Limpia el historial de verificaciones de salud."""
        self.health_history.clear()
        self.logger.info("[HEALTH-CHECKER] Historial de salud limpiado")
        
    def is_component_healthy(self, component_name: str) -> bool:
        """Verifica si un componente esta saludable."""
        health_check = self.get_health_status(component_name)
        if isinstance(health_check, HealthCheck):
            return health_check.status == HealthStatus.HEALTHY
        return False
        
    def get_unhealthy_components(self) -> List[str]:
        """Obtiene una lista de componentes no saludables."""
        unhealthy = []
        current_checks = self.get_health_status()
        
        if isinstance(current_checks, HealthCheck):
            current_checks = [current_checks]
            
        for check in current_checks:
            if check.status != HealthStatus.HEALTHY:
                unhealthy.append(check.component_name)
                
        return unhealthy
        
    def __enter__(self):
        """Context manager entry."""
        self.start_health_checks()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_health_checks()


# Instancia global unica
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Obtiene la instancia global del verificador de salud."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def start_health_checks() -> None:
    """Inicia las verificaciones de salud globales."""
    checker = get_health_checker()
    checker.start_health_checks()


def stop_health_checks() -> None:
    """Detiene las verificaciones de salud globales."""
    checker = get_health_checker()
    checker.stop_health_checks()