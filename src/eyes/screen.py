# src/eyes/screen.py
"""
Captura de pantalla y análisis para JARVIS con arquitectura de planificación.

Este módulo proporciona:
- Captura de pantalla completa y regional.
- Análisis del estado del mundo.
- Detección de aplicaciones activas.
- Verificación básica de elementos UI calibrados.
- Integración con memoria de dominio.

La geometría de monitores y ventanas pertenece a ScreenManager. Este módulo
no contiene offsets fijos, resoluciones prefijadas ni lógica específica de
Chrome o de otra aplicación.

Las coordenadas de regiones y monitores se expresan en coordenadas absolutas
del escritorio virtual de Windows.
"""

from __future__ import annotations

import glob
import os
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
from PIL import ImageGrab

from src.memory.storage import MemoryType, get_memory_manager
from src.utils.logger import get_logger
from src.utils.screen_manager import get_screen_manager

logger = get_logger(__name__)


class ApplicationState(Enum):
    """Estados conocidos de una aplicación."""

    CLOSED = "closed"
    OPEN = "open"
    ACTIVE = "active"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"


@dataclass
class ApplicationInfo:
    """Información de una aplicación detectada."""

    name: str
    state: ApplicationState
    window_title: Optional[str] = None
    window_class: Optional[str] = None
    monitor: int = 1
    position: Tuple[int, int] = (0, 0)
    size: Tuple[int, int] = (0, 0)
    visible_elements: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.visible_elements is None:
            self.visible_elements = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "window_title": self.window_title,
            "window_class": self.window_class,
            "monitor": self.monitor,
            "position": self.position,
            "size": self.size,
            "visible_elements": list(self.visible_elements or []),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ApplicationInfo":
        payload = dict(data or {})
        state_value = str(payload.get("state", ApplicationState.CLOSED.value)).lower()
        try:
            state = ApplicationState(state_value)
        except ValueError:
            state = ApplicationState.CLOSED

        position = payload.get("position", (0, 0))
        size = payload.get("size", (0, 0))

        try:
            position_tuple = tuple(position)[:2]
        except TypeError:
            position_tuple = (0, 0)
        try:
            size_tuple = tuple(size)[:2]
        except TypeError:
            size_tuple = (0, 0)

        if len(position_tuple) != 2:
            position_tuple = (0, 0)
        if len(size_tuple) != 2:
            size_tuple = (0, 0)

        return cls(
            name=str(payload.get("name", "unknown")),
            state=state,
            window_title=payload.get("window_title"),
            window_class=payload.get("window_class"),
            monitor=max(1, int(payload.get("monitor", 1) or 1)),
            position=(int(position_tuple[0]), int(position_tuple[1])),
            size=(int(size_tuple[0]), int(size_tuple[1])),
            visible_elements=list(payload.get("visible_elements", []) or []),
        )


@dataclass
class WorldState:
    """Estado del mundo usado por las APIs legacy de este módulo."""

    timestamp: float
    applications: Dict[str, ApplicationInfo]
    focused_application: Optional[str] = None
    active_monitor: int = 1
    available_monitors: Optional[List[int]] = None
    calibrated_elements: Optional[Dict[str, Dict[str, Any]]] = None
    known_urls: Optional[Dict[str, str]] = None
    system_resources: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.available_monitors is None:
            self.available_monitors = [1]
        if self.calibrated_elements is None:
            self.calibrated_elements = {}
        if self.known_urls is None:
            self.known_urls = {}
        if self.system_resources is None:
            self.system_resources = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "applications": {
                key: value.to_dict() if hasattr(value, "to_dict") else value
                for key, value in self.applications.items()
            },
            "focused_application": self.focused_application,
            "active_monitor": self.active_monitor,
            "available_monitors": list(self.available_monitors or []),
            "calibrated_elements": dict(self.calibrated_elements or {}),
            "known_urls": dict(self.known_urls or {}),
            "system_resources": dict(self.system_resources or {}),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "WorldState":
        payload = dict(data or {})
        applications: Dict[str, ApplicationInfo] = {}
        for app_name, app_data in (payload.get("applications", {}) or {}).items():
            if isinstance(app_data, dict):
                app_data = dict(app_data)
                app_data.setdefault("name", app_name)
                applications[str(app_name)] = ApplicationInfo.from_dict(app_data)
            else:
                applications[str(app_name)] = ApplicationInfo(
                    name=str(app_name),
                    state=ApplicationState.CLOSED,
                )

        try:
            active_monitor = max(1, int(payload.get("active_monitor", 1) or 1))
        except (TypeError, ValueError):
            active_monitor = 1

        return cls(
            timestamp=float(payload.get("timestamp", time.time())),
            applications=applications,
            focused_application=payload.get("focused_application"),
            active_monitor=active_monitor,
            available_monitors=[
                int(value)
                for value in (payload.get("available_monitors", [1]) or [1])
                if str(value).isdigit()
            ] or [1],
            calibrated_elements=dict(payload.get("calibrated_elements", {}) or {}),
            known_urls=dict(payload.get("known_urls", {}) or {}),
            system_resources=dict(payload.get("system_resources", {}) or {}),
        )


pyautogui.PAUSE = 0.05


# ============================================================================
# UTILIDADES DE MONITORES
# ============================================================================


def _get_available_monitor_numbers() -> List[int]:
    """Obtiene todos los monitores reales detectados por ScreenManager."""

    try:
        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()

        monitors = list(getattr(screen_manager, "monitors", []) or [])
        numbers: List[int] = []
        for position, monitor in enumerate(monitors, start=1):
            number = getattr(monitor, "monitor_id", None)
            if not isinstance(number, int) or number < 1:
                candidate_index = getattr(monitor, "index", None)
                if isinstance(candidate_index, int):
                    # ScreenManager usa index 0-based.
                    number = candidate_index + 1
            if not isinstance(number, int) or number < 1:
                number = position
            if number not in numbers:
                numbers.append(number)

        return numbers or [1]
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_available_monitor_numbers", 225)
        return [1]


def _get_monitor_number(monitor: Any) -> Optional[int]:
    """Obtiene el identificador lógico de un MonitorInfo sin asumir un campo único."""

    if monitor is None:
        return None

    for attribute in ("monitor_id", "screen_number", "number"):
        value = getattr(monitor, attribute, None)
        if isinstance(value, int) and value > 0:
            return value

    index = getattr(monitor, "index", None)
    if isinstance(index, int) and index >= 0:
        return index + 1

    return None


# ============================================================================
# ANÁLISIS DE PANTALLAS Y ESTADO
# ============================================================================


class ScreenAnalyzer:
    """Analizador de pantallas integrado con la capa Vision."""

    def __init__(self) -> None:
        self.memory_manager = get_memory_manager()
        self._vision = None

    def _get_vision(self):
        """Inicializa Vision de forma diferida para evitar importaciones circulares."""

        if self._vision is not None:
            return self._vision

        try:
            from src.eyes.vision import Vision

            self._vision = Vision()
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_vision", 270)
            self._vision = None

        return self._vision

    def analyze_application_state(self, app_name: str) -> ApplicationInfo:
        """Analiza una aplicación en todos los monitores disponibles."""

        target = str(app_name or "").strip()
        if not target:
            return ApplicationInfo(name=target, state=ApplicationState.CLOSED)

        vision = self._get_vision()
        if vision is not None:
            try:
                result = vision.detect_application_state(target)
                if isinstance(result, ApplicationInfo):
                    return result
                if hasattr(result, "to_dict"):
                    return ApplicationInfo.from_dict(result.to_dict())
                if isinstance(result, dict):
                    result = dict(result)
                    result.setdefault("name", target)
                    return ApplicationInfo.from_dict(result)
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "detect_application_state", 296)

        return self._fallback_detect_application_state(target)

    def _fallback_detect_application_state(self, app_name: str) -> ApplicationInfo:
        """Fallback no visual usando la ventana foreground cuando sea posible."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is not None:
                title = str(getattr(active_window, "title", "") or "")
                if app_name.lower() in title.lower():
                    monitor = get_screen_manager().get_monitor_for_window(active_window)
                    monitor_number = _get_monitor_number(monitor) or 1
                    return ApplicationInfo(
                        name=app_name,
                        state=ApplicationState.ACTIVE,
                        window_title=title or None,
                        monitor=monitor_number,
                        position=(
                            int(getattr(active_window, "left", 0)),
                            int(getattr(active_window, "top", 0)),
                        ),
                        size=(
                            max(0, int(getattr(active_window, "width", 0))),
                            max(0, int(getattr(active_window, "height", 0))),
                        ),
                    )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_fallback_detect_application_state", 326)

        return ApplicationInfo(name=app_name, state=ApplicationState.CLOSED)

    def build_world_state(self) -> WorldState:
        """Construye el estado del mundo usando la capa Vision cuando está disponible."""

        logger._print_log("info", r"Construyendo estado del mundo... [file:screen.py, method:build_world_state, line:336]", "screen.py", "method", 333)
        start_time = time.time()
        monitor_numbers = _get_available_monitor_numbers()

        vision = self._get_vision()
        if vision is not None:
            try:
                visual_state = vision.analyze_screen_for_world_state()
                world_state = self._convert_visual_world_state(
                    visual_state,
                    monitor_numbers,
                    start_time,
                )
                self.memory_manager.save_world_state(world_state.to_dict())
                return world_state
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "build_world_state", 349)

        # Fallback: información mínima sin asumir un número fijo de monitores.
        applications: Dict[str, ApplicationInfo] = {}
        for app_name in self._get_known_applications():
            applications[app_name] = self._fallback_detect_application_state(app_name)

        world_state = WorldState(
            timestamp=start_time,
            applications=applications,
            focused_application=self._detect_focused_application(applications),
            active_monitor=self._get_active_monitor(),
            available_monitors=monitor_numbers,
            calibrated_elements=self._get_calibrated_elements(),
            known_urls=self._get_known_urls(),
            system_resources=self._get_system_resources(),
        )

        try:
            self.memory_manager.save_world_state(world_state.to_dict())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "build_world_state", 372)

        logger._print_log("info", r"[SCREEN-ANALYZER] Estado construido en %.2fs [file:screen.py, method:build_world_state, line:372]", "screen.py", "method", 372)
        return world_state

    def _convert_visual_world_state(
        self,
        visual_state: Any,
        monitor_numbers: List[int],
        timestamp: float,
    ) -> WorldState:
        """Adapta el WorldState de memoria de Vision a la API legacy de este módulo."""

        applications: Dict[str, ApplicationInfo] = {}
        visual_apps = getattr(visual_state, "applications", {}) or {}

        state_map = {
            "closed": ApplicationState.CLOSED,
            "open": ApplicationState.OPEN,
            "active": ApplicationState.ACTIVE,
            "minimized": ApplicationState.MINIMIZED,
            "maximized": ApplicationState.MAXIMIZED,
        }

        if isinstance(visual_apps, dict):
            for key, raw in visual_apps.items():
                if isinstance(raw, ApplicationInfo):
                    applications[str(key)] = raw
                    continue
                if not isinstance(raw, dict):
                    applications[str(key)] = ApplicationInfo(
                        name=str(key),
                        state=ApplicationState.CLOSED,
                    )
                    continue

                state_value = str(raw.get("state", "closed") or "closed").lower()
                applications[str(key)] = ApplicationInfo(
                    name=str(raw.get("name", key)),
                    state=state_map.get(state_value, ApplicationState.OPEN),
                    window_title=raw.get("window_title"),
                    window_class=raw.get("window_class"),
                    monitor=max(1, int(raw.get("monitor", 1) or 1)),
                    position=tuple(raw.get("position", (0, 0)))[:2]
                    if isinstance(raw.get("position"), (list, tuple))
                    and len(raw.get("position")) >= 2
                    else (0, 0),
                    size=tuple(raw.get("size", (0, 0)))[:2]
                    if isinstance(raw.get("size"), (list, tuple))
                    and len(raw.get("size")) >= 2
                    else (0, 0),
                    visible_elements=list(raw.get("visible_elements", []) or []),
                )

        system_info = getattr(visual_state, "system_info", {}) or {}
        if not isinstance(system_info, dict):
            system_info = {}

        focused_application = system_info.get("focused_application")
        active_monitor_value = system_info.get("active_monitor")
        try:
            active_monitor = int(active_monitor_value)
        except (TypeError, ValueError):
            active_monitor = self._get_active_monitor()
        if active_monitor not in monitor_numbers:
            active_monitor = monitor_numbers[0] if monitor_numbers else 1

        calibrated_elements = system_info.get("calibrated_elements", {}) or {}
        known_urls = system_info.get("known_urls", {}) or {}

        world_state = WorldState(
            timestamp=timestamp,
            applications=applications,
            focused_application=str(focused_application) if focused_application else None,
            active_monitor=active_monitor,
            available_monitors=monitor_numbers,
            calibrated_elements=dict(calibrated_elements),
            known_urls=dict(known_urls),
            system_resources={
                "visible_text": system_info.get("visible_text", ""),
            },
        )
        return world_state

    def _get_known_applications(self) -> List[str]:
        """Obtiene aplicaciones conocidas desde memoria y descubrimiento global."""

        names: List[str] = []

        try:
            entities = self.memory_manager.get_entities_by_type("application") or []
            names.extend(
                str(entity.name)
                for entity in entities
                if getattr(entity, "name", None)
            )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "get_application_names", 481)

        try:
            entities = self.memory_manager.get_entities_by_type("platform") or []
            names.extend(
                str(entity.name)
                for entity in entities
                if getattr(entity, "name", None)
            )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_known_applications", 480)

        try:
            from src.hands.calibration_manager import get_calibration_manager

            manager = get_calibration_manager()
            discover = getattr(manager, "discover_applications", None)
            if callable(discover):
                discovered = discover() or []
                for app in discovered:
                    if isinstance(app, str):
                        names.append(app)
                    else:
                        name = getattr(app, "name", None)
                        if name:
                            names.append(str(name))
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_known_applications", 497)

        # Fallback mínimo para instalaciones donde la memoria todavía esté vacía.
        names.extend(["chrome", "edge", "firefox", "notepad", "calculator", "paint", "explorer", "cmd", "spotify"])

        unique: List[str] = []
        seen = set()
        for name in names:
            normalized = str(name).strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                unique.append(normalized)
        return unique

    def _detect_focused_application(
        self,
        applications: Dict[str, ApplicationInfo],
    ) -> Optional[str]:
        """Detecta la aplicación enfocada mediante la ventana foreground."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is None:
                return None

            window_title = str(getattr(active_window, "title", "") or "").lower()
            if not window_title:
                return None

            for app_name, app_info in applications.items():
                if app_info.window_title and app_info.window_title.lower() in window_title:
                    return app_name

            for app_name in applications:
                if str(app_name).lower() in window_title:
                    return app_name

            for app_name, app_info in applications.items():
                if app_info.state == ApplicationState.ACTIVE:
                    return app_name
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_detect_focused_application", 541)

        return None

    def _get_active_monitor(self) -> int:
        """Obtiene el monitor de la ventana foreground desde ScreenManager."""

        try:
            screen_manager = get_screen_manager()
            foreground_getter = getattr(screen_manager, "get_foreground_window", None)
            if callable(foreground_getter):
                active_window = foreground_getter()
            else:
                import pygetwindow as gw
                active_window = gw.getActiveWindow()

            if active_window is not None:
                monitor = screen_manager.get_monitor_for_window(active_window)
                number = _get_monitor_number(monitor)
                if number is not None:
                    return number

            active_getter = getattr(screen_manager, "get_active_monitor", None)
            if callable(active_getter):
                monitor = active_getter()
                number = _get_monitor_number(monitor)
                if number is not None:
                    return number

            primary = screen_manager.get_primary_monitor()
            number = _get_monitor_number(primary)
            if number is not None:
                return number
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_active_monitor", 575)

        return _get_available_monitor_numbers()[0]

    def _get_calibrated_elements(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene elementos calibrados desde memoria."""

        try:
            state = self.memory_manager.storage.load(MemoryType.STATE)
            if isinstance(state, dict):
                return dict(state.get("calibrated_elements", {}) or {})
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_calibrated_elements", 587)
        return {}

    def _get_known_urls(self) -> Dict[str, str]:
        """Obtiene URLs conocidas desde memoria de dominio."""

        try:
            streamers = self.memory_manager.get_entities_by_type("streamer") or []
            platforms = self.memory_manager.get_entities_by_type("platform") or []
            urls: Dict[str, str] = {}
            for entity in list(streamers) + list(platforms):
                properties = getattr(entity, "properties", {}) or {}
                url = properties.get("url")
                if url:
                    urls[str(entity.name)] = str(url)
            return urls
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_known_urls", 601)
            return {}

    def _get_system_resources(self) -> Dict[str, Any]:
        """Obtiene recursos básicos del sistema."""

        try:
            import psutil

            if os.name == "nt":
                disk_root = f"{os.environ.get('SystemDrive', 'C:')}\\"
            else:
                disk_root = "/"

            battery = None
            sensors_battery = getattr(psutil, "sensors_battery", None)
            if callable(sensors_battery):
                try:
                    battery_info = sensors_battery()
                    if battery_info is not None:
                        battery = {
                            "percent": getattr(battery_info, "percent", None),
                            "plugged": getattr(battery_info, "power_plugged", None),
                        }
                except Exception:
                    battery = None

            return {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(disk_root).percent,
                "battery": battery,
            }
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_resources", 655)
            return {}


# ============================================================================
# SISTEMA DE CAPTURA
# ============================================================================


class ScreenCapture:
    """Sistema de captura con geometría delegada a ScreenManager."""

    def __init__(self) -> None:
        self.analyzer: Optional[ScreenAnalyzer] = None
        logger._print_log("debug", r"Sistema de captura inicializado [file:screen.py, method:__init__, line:652]", "screen.py", "method", 649)

    def _get_analyzer(self) -> Optional[ScreenAnalyzer]:
        if self.analyzer is None:
            try:
                self.analyzer = ScreenAnalyzer()
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "_get_analyzer", 659)
                self.analyzer = None
        return self.analyzer

    # ========================================================================
    # MONITOR
    # ========================================================================

    def capture_monitor(
        self,
        monitor_num: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura exactamente el monitor indicado mediante ScreenManager."""

        try:
            screen_manager = get_screen_manager()
            result = screen_manager.capture_monitor(int(monitor_num))
            if not result:
                return None

            source_path = Path(str(result))
            if not source_path.exists():
                logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "capture_monitor", 682)
                return None

            if save_path is None:
                return str(source_path.resolve())

            output_path = Path(save_path)
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, output_path)
            return str(output_path.resolve())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225) + ": " + str(exc), "screen.py", "capture_monitor", 692)
            return None

    # ========================================================================
    # REGIÓN
    # ========================================================================

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura una región expresada en coordenadas absolutas del escritorio."""

        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)
            if width <= 0 or height <= 0:
                return None

            bbox = (x, y, x + width, y + height)
            try:
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                screenshot = ImageGrab.grab(bbox=bbox)

            output_path = self._prepare_output_path(save_path, "region")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "capture_region", 730)
            return None

    # ========================================================================
    # ELEMENTO
    # ========================================================================

    def capture_element(
        self,
        element_coords: Dict[str, Any],
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura una región descrita por x/y/width/height."""

        if not isinstance(element_coords, dict):
            return None

        try:
            return self.capture_region(
                x=int(element_coords.get("x", 0)),
                y=int(element_coords.get("y", 0)),
                width=int(element_coords.get("width", 0)),
                height=int(element_coords.get("height", 0)),
                save_path=save_path,
            )
        except (TypeError, ValueError):
            return None

    # ========================================================================
    # VENTANA ACTIVA
    # ========================================================================

    def capture_active_window(
        self,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura la ventana foreground actual."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is None:
                return None

            left = int(getattr(active_window, "left", 0))
            top = int(getattr(active_window, "top", 0))
            width = int(getattr(active_window, "width", 0))
            height = int(getattr(active_window, "height", 0))
            if width <= 0 or height <= 0:
                return None

            bbox = (left, top, left + width, top + height)
            try:
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                screenshot = ImageGrab.grab(bbox=bbox)

            output_path = self._prepare_output_path(save_path, "window")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "capture_active_window", 815)
            return None

    def _prepare_output_path(
        self,
        save_path: Optional[str],
        prefix: str,
    ) -> Path:
        """Prepara la ruta de salida para una captura."""

        if save_path:
            output_path = Path(save_path)
        else:
            timestamp = int(time.time() * 1000)
            output_path = Path.cwd() / f"temp_{prefix}_{timestamp}.png"

        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    # ========================================================================
    # ESCRITORIO COMPLETO
    # ========================================================================

    def capture_desktop(
        self,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura el rectángulo completo del escritorio virtual."""

        try:
            screen_manager = get_screen_manager()
            refresh = getattr(screen_manager, "refresh_monitors", None)
            if callable(refresh):
                refresh()

            monitors = list(getattr(screen_manager, "monitors", []) or [])
            if not monitors:
                return None

            left = min(int(m.left) for m in monitors)
            top = min(int(m.top) for m in monitors)
            right = max(int(m.right) for m in monitors)
            bottom = max(int(m.bottom) for m in monitors)

            try:
                screenshot = ImageGrab.grab(
                    bbox=(left, top, right, bottom),
                    all_screens=True,
                )
            except TypeError:
                screenshot = ImageGrab.grab(
                    bbox=(left, top, right, bottom),
                )

            output_path = self._prepare_output_path(save_path, "desktop")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "capture_desktop", 878)
            return None

    # ========================================================================
    # ESTADO DEL MUNDO
    # ========================================================================

    def get_world_state(self) -> WorldState:
        analyzer = self._get_analyzer()
        if analyzer is None:
            return WorldState(applications={}, timestamp=time.time())
        return analyzer.build_world_state()

    def get_application_state(self, app_name: str) -> ApplicationInfo:
        analyzer = self._get_analyzer()
        if analyzer is None:
            return ApplicationInfo(name=app_name, state=ApplicationState.CLOSED)
        return analyzer.analyze_application_state(app_name)

    def check_element_visibility(self, element_name: str) -> bool:
        """Comprueba visibilidad a partir del estado visual disponible."""

        target = str(element_name or "").strip().lower()
        if not target:
            return False

        try:
            world_state = self.get_world_state()
            if world_state.focused_application:
                info = world_state.applications.get(world_state.focused_application)
                if info and any(
                    target == str(element).strip().lower()
                    for element in (info.visible_elements or [])
                ):
                    return True

            for info in world_state.applications.values():
                if any(
                    target == str(element).strip().lower()
                    for element in (info.visible_elements or [])
                ):
                    return True
            return False
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "is_element_visible", 925)
            return False

    # ========================================================================
    # LIMPIEZA
    # ========================================================================

    def clean_temp_files(self, pattern: str = "temp_*.png") -> None:
        """Elimina capturas temporales del directorio actual."""

        try:
            for file_path in glob.glob(pattern):
                try:
                    Path(file_path).unlink()
                    logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225)
                except Exception as exc:
                    logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "clean_temp_files", 947)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen.py", "method", 225), "screen.py", "clean_temp_files", 920)


# ============================================================================
# FUNCIONES DE COMPATIBILIDAD
# ============================================================================


def capture_screen(filepath: str = "screenshot.png") -> str:
    """Captura el escritorio virtual completo."""

    screen_capture = get_screen_capture()
    return screen_capture.capture_desktop(filepath) or ""


def capture_captcha_area(
    pantalla: str,
    region_captcha: Tuple[int, int, int, int],
    img_captcha_path: str,
) -> bool:
    """Captura una región del escritorio para compatibilidad legacy."""

    del pantalla  # Parámetro legacy; no se usa para calcular coordenadas.
    screen_capture = get_screen_capture()
    x, y, width, height = region_captcha
    result = screen_capture.capture_region(
        x,
        y,
        width,
        height,
        img_captcha_path,
    )
    return result is not None


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================


_screen_capture_instance: Optional[ScreenCapture] = None


def get_screen_capture() -> ScreenCapture:
    """Obtiene la instancia global de captura."""

    global _screen_capture_instance
    if _screen_capture_instance is None:
        _screen_capture_instance = ScreenCapture()
    return _screen_capture_instance


__all__ = [
    "ApplicationState",
    "ApplicationInfo",
    "WorldState",
    "ScreenAnalyzer",
    "ScreenCapture",
    "capture_screen",
    "capture_captcha_area",
    "get_screen_capture",
]
