"""
Información del sistema para Jarvis con arquitectura de planificación.

Este módulo proporciona información estructurada del sistema para construir
el estado del mundo (FASE 3) y soportar la planificación jerárquica.

Recoge:
- Uso de CPU y memoria
- Estado del disco
- Información de ventanas y aplicaciones
- Recursos del sistema
- Contexto para planificación

Integrado con:
- Estado del mundo (FASE 3)
- Memoria de dominio (FASE 5)
- Sistema de planificación
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import psutil
import pygetwindow as gw

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SystemHealth(Enum):
    """Estados de salud del sistema."""
    EXCELLENT = "excellent"
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ApplicationWindow:
    """Información de una ventana de aplicación."""
    title: str
    process_name: str
    handle: int
    position: tuple[int, int]
    size: tuple[int, int]
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    monitor: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return {
            "title": self.title,
            "process_name": self.process_name,
            "handle": self.handle,
            "position": self.position,
            "size": self.size,
            "is_visible": self.is_visible,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
            "monitor": self.monitor
        }


@dataclass
class SystemResources:
    """Recursos del sistema."""
    cpu_percent: float
    ram_total_gb: float
    ram_used_percent: float
    disk_free_gb: float
    disk_total_gb: float
    disk_used_percent: float
    battery_percent: Optional[float]
    battery_power_plugged: bool
    system_health: SystemHealth
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return {
            "cpu_percent": self.cpu_percent,
            "ram_total_gb": self.ram_total_gb,
            "ram_used_percent": self.ram_used_percent,
            "disk_free_gb": self.disk_free_gb,
            "disk_total_gb": self.disk_total_gb,
            "disk_used_percent": self.disk_used_percent,
            "battery_percent": self.battery_percent,
            "battery_power_plugged": self.battery_power_plugged,
            "system_health": self.system_health.value,
            "timestamp": self.timestamp
        }


@dataclass
class SystemContext:
    """Contexto completo del sistema para planificación."""
    resources: SystemResources
    active_windows: List[ApplicationWindow]
    focused_window: Optional[ApplicationWindow]
    running_processes: List[str]
    system_time: str
    uptime_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para estado del mundo."""
        return {
            "resources": self.resources.to_dict(),
            "active_windows": [w.to_dict() for w in self.active_windows],
            "focused_window": self.focused_window.to_dict() if self.focused_window else None,
            "running_processes": self.running_processes,
            "system_time": self.system_time,
            "uptime_seconds": self.uptime_seconds
        }


def _get_system_drive() -> str:
    """
    Obtiene la unidad del sistema.

    En Windows utiliza SystemDrive (normalmente C:).
    En otros sistemas utiliza la raíz '/'.
    """
    system_drive = os.environ.get("SystemDrive")

    if system_drive:
        return f"{system_drive}{os.sep}"

    return os.path.abspath(os.sep)


def _calculate_system_health(cpu_percent: float, ram_percent: float, disk_percent: float) -> SystemHealth:
    """Calcula la salud del sistema basada en recursos."""
    if cpu_percent > 90 or ram_percent > 90 or disk_percent > 95:
        return SystemHealth.CRITICAL
    elif cpu_percent > 75 or ram_percent > 75 or disk_percent > 85:
        return SystemHealth.WARNING
    elif cpu_percent > 50 or ram_percent > 50 or disk_percent > 70:
        return SystemHealth.GOOD
    else:
        return SystemHealth.EXCELLENT


def get_system_stats() -> Dict[str, Any]:
    """
    Lee el estado de CPU, memoria RAM y disco.

    Returns:
        Diccionario con:
        - cpu: porcentaje de uso de CPU.
        - ram_total: RAM total en GB.
        - ram_percent: porcentaje de RAM utilizada.
        - disk_free: espacio libre de la unidad del sistema en GB.
    """
    try:
        cpu_usage = float(psutil.cpu_percent(interval=0.5))

        ram = psutil.virtual_memory()
        ram_total_gb = round(
            ram.total / (1024 ** 3),
            2,
        )
        ram_used_percent = float(ram.percent)

        system_drive = _get_system_drive()
        disk = psutil.disk_usage(system_drive)
        disk_free_gb = round(
            disk.free / (1024 ** 3),
            2,
        )
        disk_total_gb = round(
            disk.total / (1024 ** 3),
            2,
        )
        disk_used_percent = round(
            disk.percent,
            2,
        )

        return {
            "cpu": cpu_usage,
            "ram_total": ram_total_gb,
            "ram_percent": ram_used_percent,
            "disk_free": disk_free_gb,
            "disk_total": disk_total_gb,
            "disk_percent": disk_used_percent,
        }

    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)

        # Mantenemos la misma estructura de retorno para que el resto del
        # proyecto pueda consumirla incluso cuando una métrica falle.
        return {
            "cpu": 0.0,
            "ram_total": 0.0,
            "ram_percent": 0.0,
            "disk_free": 0.0,
            "disk_total": 0.0,
            "disk_percent": 0.0,
        }


def get_battery_info() -> Optional[Dict[str, Any]]:
    """Obtiene información de la batería."""
    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secsleft": battery.secsleft
            }
    except Exception as exc:
        logger._print_log("debug", f"No se pudo obtener información de batería: {exc}", "os_info.py", "method", 222)
    
    return None


def get_open_windows() -> List[ApplicationWindow]:
    """
    Obtiene información detallada de ventanas visibles.

    Returns:
        Lista de ApplicationWindow correspondientes a ventanas visibles
        con dimensiones válidas.
    """
    active_windows: List[ApplicationWindow] = []

    try:
        windows = gw.getWindowsWithTitle("")

        for window in windows:
            try:
                title = str(
                    getattr(window, "title", "") or ""
                ).strip()

                if not title:
                    continue

                visible = bool(
                    getattr(window, "visible", True)
                )

                minimized = bool(
                    getattr(window, "isMinimized", False)
                )

                maximized = bool(
                    getattr(window, "isMaximized", False)
                )

                width = int(
                    getattr(window, "width", 0) or 0
                )

                height = int(
                    getattr(window, "height", 0) or 0
                )

                left = int(
                    getattr(window, "left", 0) or 0
                )

                top = int(
                    getattr(window, "top", 0) or 0
                )

                if not visible or minimized:
                    continue

                if width <= 0 or height <= 0:
                    continue

                # Determinar monitor basado en posición
                monitor = _get_monitor_from_position(left, top)

                # Obtener nombre del proceso
                process_name = _get_process_name(window)

                window_info = ApplicationWindow(
                    title=title,
                    process_name=process_name,
                    handle=window._hWnd if hasattr(window, '_hWnd') else 0,
                    position=(left, top),
                    size=(width, height),
                    is_visible=visible,
                    is_minimized=minimized,
                    is_maximized=maximized,
                    monitor=monitor
                )

                active_windows.append(window_info)

            except Exception:
                # Una ventana concreta puede desaparecer mientras se enumera.
                continue

    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)

    return active_windows


def _get_monitor_from_position(x: int, y: int) -> int:
    """Determina qué monitor contiene la posición dada."""
    try:
        from src.utils.screen_manager import get_monitor_info
        
        for i in range(1, 5):  # Hasta 4 monitores
            monitor = get_monitor_info(i)
            if monitor:
                if (monitor.left <= x < monitor.right and 
                    monitor.top <= y < monitor.bottom):
                    return i
    except Exception as exc:
        logger._print_log("debug", f"No se pudo determinar monitor para posición ({x}, {y}): {exc}", "os_info.py", "method", 325)
    
    return 1


def _get_process_name(window) -> str:
    """Obtiene el nombre del proceso de una ventana."""
    try:
        import psutil
        
        # Intentar obtener el proceso por handle de ventana
        if hasattr(window, '_hWnd') and window._hWnd:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['pid'] == window._hWnd:
                        return proc.info['name']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        # Fallback: usar título para inferir proceso
        title = window.title.lower()
        if 'chrome' in title:
            return 'chrome'
        elif 'firefox' in title:
            return 'firefox'
        elif 'spotify' in title:
            return 'spotify'
        elif 'vscode' in title or 'visual studio code' in title:
            return 'vscode'
        elif 'explorer' in title:
            return 'explorer'
        else:
            return 'unknown'
            
    except Exception as exc:
        logger._print_log("debug", f"No se pudo obtener proceso para ventana: {exc}", "os_info.py", "method", 360)
        return 'unknown'


def get_focused_window() -> Optional[ApplicationWindow]:
    """Obtiene la ventana actualmente enfocada."""
    try:
        active_window = gw.getActiveWindow()
        if active_window:
            # Reutilizar la lógica de get_open_windows
            windows = get_open_windows()
            for window in windows:
                if window.handle == active_window._hWnd:
                    return window
    except Exception as exc:
        logger._print_log("debug", f"No se pudo obtener ventana enfocada: {exc}", "os_info.py", "method", 375)
    
    return None


def get_running_processes() -> List[str]:
    """Obtiene lista de procesos en ejecución."""
    try:
        processes = []
        for proc in psutil.process_iter(['name']):
            try:
                processes.append(proc.info['name'].lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return list(set(processes))  # Eliminar duplicados
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)
        return []


def get_system_resources() -> SystemResources:
    """Obtiene recursos del sistema con estado de salud."""
    try:
        stats = get_system_stats()
        battery = get_battery_info()
        
        # Calcular salud del sistema
        health = _calculate_system_health(
            stats['cpu'], 
            stats['ram_percent'], 
            stats['disk_percent']
        )
        
        return SystemResources(
            cpu_percent=stats['cpu'],
            ram_total_gb=stats['ram_total'],
            ram_used_percent=stats['ram_percent'],
            disk_free_gb=stats['disk_free'],
            disk_total_gb=stats['disk_total'],
            disk_used_percent=stats['disk_percent'],
            battery_percent=battery['percent'] if battery else None,
            battery_power_plugged=battery['power_plugged'] if battery else False,
            system_health=health,
            timestamp=time.time()
        )
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)
        # Devolver recursos por defecto
        return SystemResources(
            cpu_percent=0.0,
            ram_total_gb=0.0,
            ram_used_percent=0.0,
            disk_free_gb=0.0,
            disk_total_gb=0.0,
            disk_used_percent=0.0,
            battery_percent=None,
            battery_power_plugged=False,
            system_health=SystemHealth.GOOD,
            timestamp=time.time()
        )


def get_jarvis_system_context() -> str:
    """
    Empaqueta la información del sistema en un texto para el contexto
    de Jarvis (mantenido para compatibilidad).
    """
    try:
        resources = get_system_resources()
        windows = get_open_windows()
        focused_window = get_focused_window()
        
        windows_str = (
            ", ".join([w.title for w in windows[:5]])  # Mostrar solo primeras 5
            if windows
            else "Ninguna ventana visible."
        )
        
        return (
            "[CONTEXTO DEL SISTEMA]\n"
            f"- CPU: {resources.cpu_percent}%\n"
            f"- RAM en uso: {resources.ram_used_percent}% "
            f"(Total: {resources.ram_total_gb} GB)\n"
            f"- Espacio libre en disco: {resources.disk_free_gb} GB "
            f"(Total: {resources.disk_total_gb} GB)\n"
            f"- Salud del sistema: {resources.system_health.value}\n"
            f"- Ventanas abiertas: {windows_str}\n"
            f"- Ventana enfocada: {focused_window.title if focused_window else 'Ninguna'}\n"
        )
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)
        return "[CONTEXTO DEL SISTEMA] Error al obtener información del sistema."


def get_system_context() -> SystemContext:
    """
    Obtiene el contexto completo del sistema para planificación.
    
    Returns:
        SystemContext con toda la información estructurada del sistema.
    """
    try:
        start_time = time.time()
        
        resources = get_system_resources()
        windows = get_open_windows()
        focused_window = get_focused_window()
        processes = get_running_processes()
        
        # Calcular uptime del sistema
        uptime = time.time() - psutil.boot_time()
        
        context = SystemContext(
            resources=resources,
            active_windows=windows,
            focused_window=focused_window,
            running_processes=processes,
            system_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            uptime_seconds=uptime
        )
        
        logger._print_log("debug", f"Contexto del sistema obtenido en {time.time() - start_time:.3f}s", "os_info.py", "method", 496)
        return context
        
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "os_info.py", "method", 197)
        # Devolver contexto por defecto
        return SystemContext(
            resources=SystemResources(
                cpu_percent=0.0,
                ram_total_gb=0.0,
                ram_used_percent=0.0,
                disk_free_gb=0.0,
                disk_total_gb=0.0,
                disk_used_percent=0.0,
                battery_percent=None,
                battery_power_plugged=False,
                system_health=SystemHealth.GOOD,
                timestamp=time.time()
            ),
            active_windows=[],
            focused_window=None,
            running_processes=[],
            system_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            uptime_seconds=0.0
        )


if __name__ == "__main__":
    # Mostrar contexto completo para depuración
    logger._print_log("info", "=== CONTEXTO COMPLETO DEL SISTEMA ===", "os_info.py", "method", 525)
    context = get_system_context()
    logger._print_log("info", f"Recursos: {context.resources}", "os_info.py", "method", 527)
    logger._print_log("info", f"Ventanas activas: {len(context.active_windows)}", "os_info.py", "method", 528)
    logger._print_log("info", f"Procesos: {len(context.running_processes)}", "os_info.py", "method", 529)
    logger._print_log("info", f"Uptime: {context.uptime_seconds:.0f} segundos", "os_info.py", "method", 530)
    
    logger._print_log("info", "\n=== FORMATO LEGACY ===", "os_info.py", "method", 532)
    logger._print_log("info", get_jarvis_system_context(), "os_info.py", "method", 533)