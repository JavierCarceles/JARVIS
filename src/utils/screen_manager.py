


# src/utils/screen_manager.py

"""
Gestor unificado de pantallas y configuración del sistema Jarvis.

La geometría real de los monitores se obtiene directamente de Windows mediante
la API Win32. config/config.json se mantiene como configuración auxiliar y
fallback si la detección nativa no está disponible.

Las coordenadas internas son píxeles nativos del escritorio virtual. No se
aplican offsets fijos para s2 ni resoluciones fijas.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pyautogui
import pygetwindow as gw
from PIL import ImageGrab

from src.utils.config import (
    get_chrome_config,
    get_project_root,
    get_screen_config,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# TIPOS WIN32
# ============================================================================


if os.name == "nt":

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
        ]

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("showCmd", ctypes.c_uint),
            ("ptMinPosition", POINT),
            ("ptMaxPosition", POINT),
            ("rcNormalPosition", RECT),
        ]


# ============================================================================
# TIPOS
# ============================================================================


class ScreenSetupType(Enum):
    SINGLE = "single"
    DUAL_HORIZONTAL = "dual_horizontal"
    DUAL_VERTICAL = "dual_vertical"
    ULTRAWIDE = "ultrawide"
    UNKNOWN = "unknown"


@dataclass
class MonitorInfo:
    """Información física/lógica de un monitor en el escritorio virtual."""

    handle: int
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    is_primary: bool = False
    scale_factor: float = 1.0
    index: int = 0
    monitor_id: int = 0
    name: str = ""
    dpi: int = 96
    device_name: str = ""
    scaled_width: int = 0
    scaled_height: int = 0
    coordinate_system: str = "native_pixels"

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2

    @property
    def center(self) -> Tuple[int, int]:
        return self.center_x, self.center_y

    @property
    def screen_key(self) -> str:
        return f"s{self.monitor_id}"

    def contains_point(self, x: int, y: int) -> bool:
        try:
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            return False
        return self.left <= x < self.right and self.top <= y < self.bottom

    def contains_window(self, window: Any) -> bool:
        try:
            center_x = int(window.left) + int(window.width) // 2
            center_y = int(window.top) + int(window.height) // 2
        except Exception:
            return False
        return self.contains_point(center_x, center_y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.monitor_id,
            "handle": self.handle,
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "is_primary": self.is_primary,
            "scale_factor": self.scale_factor,
            "index": self.index,
            "monitor_id": self.monitor_id,
            "name": self.name,
            "dpi": self.dpi,
            "device_name": self.device_name,
            "scaled_width": self.scaled_width,
            "scaled_height": self.scaled_height,
            "coordinate_system": self.coordinate_system,
        }


# ============================================================================
# SCREEN MANAGER
# ============================================================================


class ScreenManager:
    """Gestor centralizado de topología, ventanas y capturas."""

    def __init__(self) -> None:
        self._make_dpi_aware()
        self.screen_config = get_screen_config()
        self.chrome_config = get_chrome_config()
        self.project_root = Path(get_project_root())

        detected = self._load_monitors_from_windows()
        if detected:
            self.monitors: List[MonitorInfo] = detected
            logger.info(
                "[SCREEN-MANAGER] Topología detectada directamente desde Windows."
            )
        else:
            self.monitors = self._load_monitors_from_config()
            logger.warning(
                "[SCREEN-MANAGER] Detección Win32 no disponible; se utiliza "
                "config.json como fallback."
            )

        self.setup = self._analyze_setup()
        self.multi_screen_offset = int(self.setup.get("multi_screen_offset", 0) or 0)

        logger.info(
            f"[SCREEN-MANAGER] Setup={self.setup['setup_type']} | monitores={len(self.monitors)} | virtual={self.setup['total_width']}x{self.setup['total_height']}",
        )

        bounds = self.setup["virtual_bounds"]
        logger.info(
            f"[SCREEN-MANAGER] Límites virtuales: min=({bounds['min_x']},{bounds['min_y']}) max=({bounds['max_x']},{bounds['max_y']})",
        )

        for monitor in self.monitors:
            logger.info(
                f"[SCREEN-MANAGER] {monitor.screen_key} | {monitor.device_name or monitor.name or 'sin_nombre'} | pos=({monitor.left},{monitor.top}) | size={monitor.width}x{monitor.height} | "
                f"dpi={monitor.dpi} | scale={monitor.scale_factor:.2f} | primary={monitor.is_primary}",
            )

    # ========================================================================
    # DPI
    # ========================================================================

    def _make_dpi_aware(self) -> None:
        if os.name != "nt":
            return

        try:
            user32 = ctypes.windll.user32

            set_context = getattr(
                user32,
                "SetProcessDpiAwarenessContext",
                None,
            )
            if set_context is not None:
                try:
                    set_context.argtypes = [ctypes.c_void_p]
                    set_context.restype = ctypes.c_bool
                    if set_context(ctypes.c_void_p(-4)):
                        logger._print_log("info", "[SCREEN-MANAGER] DPI awareness: Per Monitor V2", "screen_manager.py", "method", 238)
                        return
                except Exception as exc:
                    logger.debug(
                        "[SCREEN-MANAGER] No se pudo activar Per Monitor V2: _make_dpi_aware",
                        exc,
                    )

            try:
                shcore = ctypes.windll.shcore
                shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
                shcore.SetProcessDpiAwareness.restype = ctypes.c_long
                result = shcore.SetProcessDpiAwareness(2)
                if result in (0, -5):
                    logger._print_log("info", "[SCREEN-MANAGER] DPI awareness: Per Monitor", "screen_manager.py", "method", 252)
                    return
            except Exception as exc:
                logger.debug(
                    "[SCREEN-MANAGER] No se pudo activar SetProcessDpiAwareness: _make_dpi_aware",
                    exc,
                )

            try:
                user32.SetProcessDPIAware()
                logger._print_log("info", "[SCREEN-MANAGER] DPI awareness: legacy DPI aware", "screen_manager.py", "method", 262)
            except Exception:
                pass

        except Exception as exc:
            logger.warning(
                "[SCREEN-MANAGER] No se pudo configurar DPI awareness: _make_dpi_aware",
                exc,
            )

    @staticmethod
    def _get_monitor_dpi(handle: int) -> int:
        if os.name != "nt" or not handle:
            return 96

        try:
            shcore = ctypes.windll.shcore
            shcore.GetDpiForMonitor.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint),
                ctypes.POINTER(ctypes.c_uint),
            ]
            shcore.GetDpiForMonitor.restype = ctypes.c_long

            dpi_x = ctypes.c_uint(96)
            dpi_y = ctypes.c_uint(96)
            result = shcore.GetDpiForMonitor(
                ctypes.c_void_p(handle),
                0,
                ctypes.byref(dpi_x),
                ctypes.byref(dpi_y),
            )
            if result == 0 and dpi_x.value > 0:
                return int(dpi_x.value)
        except Exception as exc:
            logger.debug(
                f"[SCREEN-MANAGER] No se pudo obtener DPI del monitor _get_monitor_dpi: {handle}",
                exc,
            )
        return 96

    # ========================================================================
    # DETECCIÓN WIN32
    # ========================================================================

    def _load_monitors_from_windows(self) -> List[MonitorInfo]:
        if os.name != "nt":
            return []

        monitors_raw: List[Dict[str, Any]] = []

        try:
            user32 = ctypes.windll.user32
            callback_type = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(RECT),
                ctypes.c_void_p,
            )

            def _monitor_callback(
                hmonitor,
                _hdc,
                _lprc_monitor,
                _lparam,
            ):
                try:
                    info = MONITORINFOEXW()
                    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                    if not user32.GetMonitorInfoW(
                        ctypes.c_void_p(hmonitor),
                        ctypes.byref(info),
                    ):
                        return True

                    rect = info.rcMonitor
                    left = int(rect.left)
                    top = int(rect.top)
                    right = int(rect.right)
                    bottom = int(rect.bottom)
                    width = right - left
                    height = bottom - top
                    if width <= 0 or height <= 0:
                        return True

                    handle = int(
                        ctypes.cast(
                            hmonitor,
                            ctypes.c_void_p,
                        ).value
                        or 0
                    )
                    device_name = str(info.szDevice or "").strip()

                    monitors_raw.append(
                        {
                            "handle": handle,
                            "left": left,
                            "top": top,
                            "right": right,
                            "bottom": bottom,
                            "width": width,
                            "height": height,
                            "is_primary": bool(info.dwFlags & 1),
                            "device_name": device_name,
                        }
                    )
                except Exception as exc:
                    logger.debug(
                        "[SCREEN-MANAGER] Error leyendo monitor Win32: _monitor_callback",
                        exc,
                    )
                return True

            callback = callback_type(_monitor_callback)
            user32.EnumDisplayMonitors(None, None, callback, 0)

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return []

        if not monitors_raw:
            return []

        monitors_raw.sort(
            key=lambda item: (
                not item["is_primary"],
                item["top"],
                item["left"],
                item["device_name"],
            )
        )

        monitors: List[MonitorInfo] = []
        for index, raw in enumerate(monitors_raw):
            dpi = self._get_monitor_dpi(raw["handle"])
            scale_factor = max(1.0, float(dpi) / 96.0)
            monitor_id = index + 1

            monitors.append(
                MonitorInfo(
                    handle=raw["handle"],
                    left=raw["left"],
                    top=raw["top"],
                    right=raw["right"],
                    bottom=raw["bottom"],
                    width=raw["width"],
                    height=raw["height"],
                    is_primary=raw["is_primary"],
                    scale_factor=scale_factor,
                    index=index,
                    monitor_id=monitor_id,
                    name=raw["device_name"] or f"Monitor {monitor_id}",
                    dpi=dpi,
                    device_name=raw["device_name"],
                    scaled_width=max(
                        1,
                        int(round(raw["width"] / scale_factor)),
                    ),
                    scaled_height=max(
                        1,
                        int(round(raw["height"] / scale_factor)),
                    ),
                    coordinate_system="native_pixels",
                )
            )

        if monitors and not any(m.is_primary for m in monitors):
            monitors[0].is_primary = True

        return monitors

    # ========================================================================
    # FALLBACK CONFIG
    # ========================================================================

    def _load_monitors_from_config(self) -> List[MonitorInfo]:
        monitors: List[MonitorInfo] = []
        configured_monitors = list(getattr(self.screen_config, "monitors", []) or [])

        if not configured_monitors:
            width = max(
                1,
                int(
                    getattr(
                        self.screen_config,
                        "primary_screen_width",
                        1,
                    )
                ),
            )
            height = max(
                1,
                int(
                    getattr(
                        self.screen_config,
                        "primary_screen_height",
                        1,
                    )
                ),
            )
            scale = max(
                1.0,
                float(getattr(self.screen_config, "scale_factor", 1.0) or 1.0),
            )

            monitors.append(
                MonitorInfo(
                    handle=0,
                    left=0,
                    top=0,
                    right=width,
                    bottom=height,
                    width=width,
                    height=height,
                    is_primary=True,
                    scale_factor=scale,
                    index=0,
                    monitor_id=1,
                    name="Monitor Principal",
                    dpi=int(round(96 * scale)),
                    device_name=r"\\.\DISPLAY1",
                    scaled_width=max(1, int(round(width / scale))),
                    scaled_height=max(1, int(round(height / scale))),
                    coordinate_system="native_pixels",
                )
            )
            return monitors

        try:
            configured_monitors.sort(key=lambda item: int(getattr(item, "id", 0)))
        except Exception:
            pass

        for index, monitor_cfg in enumerate(configured_monitors):
            width = max(1, int(getattr(monitor_cfg, "width", 1)))
            height = max(1, int(getattr(monitor_cfg, "height", 1)))
            left = int(getattr(monitor_cfg, "x", 0))
            top = int(getattr(monitor_cfg, "y", 0))
            scale = max(
                1.0,
                float(getattr(monitor_cfg, "scale_factor", 1.0) or 1.0),
            )
            monitor_id = int(getattr(monitor_cfg, "id", index + 1))
            dpi = int(getattr(monitor_cfg, "dpi", 0) or round(96 * scale))
            scaled_width = int(
                getattr(monitor_cfg, "scaled_width", 0) or round(width / scale)
            )
            scaled_height = int(
                getattr(monitor_cfg, "scaled_height", 0) or round(height / scale)
            )

            monitors.append(
                MonitorInfo(
                    handle=0,
                    left=left,
                    top=top,
                    right=left + width,
                    bottom=top + height,
                    width=width,
                    height=height,
                    is_primary=bool(getattr(monitor_cfg, "is_primary", False)),
                    scale_factor=scale,
                    index=index,
                    monitor_id=monitor_id,
                    name=str(getattr(monitor_cfg, "name", "") or ""),
                    dpi=dpi,
                    device_name=str(getattr(monitor_cfg, "device_name", "") or ""),
                    scaled_width=max(1, scaled_width),
                    scaled_height=max(1, scaled_height),
                    coordinate_system=str(
                        getattr(
                            monitor_cfg,
                            "coordinate_system",
                            "native_pixels",
                        )
                        or "native_pixels"
                    ),
                )
            )

        if monitors and not any(m.is_primary for m in monitors):
            monitors[0].is_primary = True

        return monitors

    # ========================================================================
    # REFRESH / SETUP
    # ========================================================================

    def refresh_monitors(self) -> bool:
        detected = self._load_monitors_from_windows()
        if not detected:
            logger.warning(
                "[SCREEN-MANAGER] Refresh Win32 fallido; se conserva la "
                "topología actualmente cargada."
            )
            return False

        self.monitors = detected
        self.setup = self._analyze_setup()
        self.multi_screen_offset = int(self.setup.get("multi_screen_offset", 0) or 0)
        logger.info(
            f"[SCREEN-MANAGER] Topología actualizada: {len(self.monitors)} monitor(es).",
        )
        return True

    def _calculate_virtual_bounds(self) -> Tuple[int, int, int, int]:
        if not self.monitors:
            return 0, 0, 0, 0
        return (
            min(m.left for m in self.monitors),
            min(m.top for m in self.monitors),
            max(m.right for m in self.monitors),
            max(m.bottom for m in self.monitors),
        )

    def _analyze_setup(self) -> Dict[str, Any]:
        if not self.monitors:
            return {
                "setup_type": ScreenSetupType.SINGLE.value,
                "total_width": 0,
                "total_height": 0,
                "is_multi_screen": False,
                "screen_count": 0,
                "monitors": [],
                "scale_factor": 1.0,
                "multi_screen_offset": 0,
                "virtual_bounds": {
                    "min_x": 0,
                    "min_y": 0,
                    "max_x": 0,
                    "max_y": 0,
                },
                "screen_boundaries": {},
                "coordinate_system": "native_pixels",
                "use_scaled_coordinates": False,
                "coordinate_conversion": {
                    "to_native": {"method": "identity", "factor": 1.0},
                    "from_native": {"method": "identity", "factor": 1.0},
                },
            }

        min_x, min_y, max_x, max_y = self._calculate_virtual_bounds()
        count = len(self.monitors)

        if count == 1:
            monitor = self.monitors[0]
            setup_type = (
                ScreenSetupType.ULTRAWIDE.value
                if monitor.width / max(1, monitor.height) >= 2.5
                else ScreenSetupType.SINGLE.value
            )
        elif count == 2:
            first, second = self.monitors
            if first.top == second.top:
                setup_type = ScreenSetupType.DUAL_HORIZONTAL.value
            elif first.left == second.left:
                setup_type = ScreenSetupType.DUAL_VERTICAL.value
            else:
                setup_type = ScreenSetupType.UNKNOWN.value
        else:
            setup_type = ScreenSetupType.UNKNOWN.value

        average_scale = sum(m.scale_factor for m in self.monitors) / count
        return {
            "setup_type": setup_type,
            "total_width": max_x - min_x,
            "total_height": max_y - min_y,
            "is_multi_screen": count > 1,
            "screen_count": count,
            "monitors": [m.to_dict() for m in self.monitors],
            "scale_factor": average_scale,
            "multi_screen_offset": 0,
            "virtual_bounds": {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
            },
            "screen_boundaries": {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
            },
            "coordinate_system": "native_pixels",
            "use_scaled_coordinates": False,
            "coordinate_conversion": {
                "to_native": {"method": "identity", "factor": 1.0},
                "from_native": {"method": "identity", "factor": 1.0},
            },
        }

    # ========================================================================
    # MONITORES / FOREGROUND
    # ========================================================================

    def get_monitor(self, monitor_num: int) -> Optional[MonitorInfo]:
        try:
            monitor_num = int(monitor_num)
        except (TypeError, ValueError):
            return None
        if monitor_num < 1:
            return None

        for monitor in self.monitors:
            if monitor.monitor_id == monitor_num:
                return monitor

        index = monitor_num - 1
        if 0 <= index < len(self.monitors):
            return self.monitors[index]
        return None

    def get_primary_monitor(self) -> Optional[MonitorInfo]:
        for monitor in self.monitors:
            if monitor.is_primary:
                return monitor
        return self.monitors[0] if self.monitors else None

    def get_monitor_by_point(self, x: int, y: int) -> Optional[MonitorInfo]:
        try:
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            return None
        for monitor in self.monitors:
            if monitor.contains_point(x, y):
                return monitor
        return None

    def _get_window_geometry(self, window: Any) -> Optional[Tuple[int, int, int, int]]:
        """Obtiene la geometría real de una ventana Win32.

        Se prioriza GetWindowRect para ventanas restauradas/maximizadas y
        rcNormalPosition para ventanas minimizadas. Así no dependemos de los
        valores que pygetwindow pueda mantener en caché.
        """
        if window is None:
            return None

        hwnd = self._get_window_handle(window)

        if os.name == "nt" and hwnd:
            try:
                user32 = ctypes.windll.user32

                is_minimized = bool(user32.IsIconic(ctypes.c_void_p(hwnd)))

                if not is_minimized:
                    rect = RECT()
                    if user32.GetWindowRect(
                        ctypes.c_void_p(hwnd),
                        ctypes.byref(rect),
                    ):
                        width = int(rect.right) - int(rect.left)
                        height = int(rect.bottom) - int(rect.top)
                        if width > 0 and height > 0:
                            return (
                                int(rect.left),
                                int(rect.top),
                                width,
                                height,
                            )

                placement = WINDOWPLACEMENT()
                placement.length = ctypes.sizeof(WINDOWPLACEMENT)
                if user32.GetWindowPlacement(
                    ctypes.c_void_p(hwnd),
                    ctypes.byref(placement),
                ):
                    normal = placement.rcNormalPosition
                    width = int(normal.right) - int(normal.left)
                    height = int(normal.bottom) - int(normal.top)
                    if width > 0 and height > 0:
                        return (
                            int(normal.left),
                            int(normal.top),
                            width,
                            height,
                        )
            except Exception as exc:
                logger.debug(
                    "[SCREEN-MANAGER] No se pudo obtener geometría Win32 "
                    "para HWND %s: %s",
                    hwnd,
                    exc,
                )

        try:
            return (
                int(window.left),
                int(window.top),
                max(1, int(window.width)),
                max(1, int(window.height)),
            )
        except Exception:
            return None

    def get_monitor_for_window(self, window: Any) -> Optional[MonitorInfo]:
        """Obtiene el monitor físico de una ventana, incluso minimizada."""
        geometry = self._get_window_geometry(window)
        if geometry is None:
            return None

        left, top, width, height = geometry
        center_x = left + width // 2
        center_y = top + height // 2
        monitor = self.get_monitor_by_point(center_x, center_y)

        if monitor is not None:
            return monitor

        hwnd = self._get_window_handle(window)
        if os.name == "nt" and hwnd:
            try:
                monitor_handle = ctypes.windll.user32.MonitorFromWindow(
                    ctypes.c_void_p(hwnd),
                    2,  # MONITOR_DEFAULTTONEAREST
                )
                if monitor_handle:
                    for candidate in self.monitors:
                        if int(candidate.handle) == int(monitor_handle):
                            return candidate
            except Exception:
                pass

        return None

    @staticmethod
    def _get_window_handle(window: Any) -> Optional[int]:
        if window is None:
            return None
        if isinstance(window, int):
            return int(window)
        for attr in ("_hWnd", "_hwnd", "hwnd"):
            value = getattr(window, attr, None)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def get_foreground_window(self) -> Optional[Any]:
        if os.name != "nt":
            return None
        try:
            hwnd = int(ctypes.windll.user32.GetForegroundWindow())
            if hwnd == 0:
                return None
            for window in gw.getAllWindows():
                if self._get_window_handle(window) == hwnd:
                    return window
        except Exception as exc:
            logger.debug(
                "[SCREEN-MANAGER] No se pudo obtener la ventana foreground: get_foreground_window",
                exc,
            )
        return None

    def get_foreground_monitor(self) -> Optional[MonitorInfo]:
        window = self.get_foreground_window()
        if window is not None:
            monitor = self.get_monitor_for_window(window)
            if monitor is not None:
                return monitor

        try:
            cursor_x, cursor_y = pyautogui.position()
            monitor = self.get_monitor_by_point(cursor_x, cursor_y)
            if monitor is not None:
                return monitor
        except Exception as exc:
            logger.debug(
                "[SCREEN-MANAGER] No se pudo usar la posición del ratón: get_foreground_monitor",
                exc,
            )

        return self.get_primary_monitor()

    def get_active_monitor(self) -> Optional[MonitorInfo]:
        return self.get_foreground_monitor()

    def get_alternate_monitor(
        self,
        monitor_num: Optional[int] = None,
    ) -> Optional[MonitorInfo]:
        if len(self.monitors) < 2:
            return None

        current = self.get_monitor(monitor_num) if monitor_num is not None else None
        if current is None:
            current = self.get_active_monitor()
        if current is None:
            current = self.get_primary_monitor()
        if current is None:
            return None

        candidates = [
            monitor
            for monitor in self.monitors
            if monitor.monitor_id != current.monitor_id
        ]
        if not candidates:
            return None

        primary_candidates = [monitor for monitor in candidates if monitor.is_primary]
        return primary_candidates[0] if primary_candidates else candidates[0]

    # ========================================================================
    # CHROME - DETECCIÓN
    # ========================================================================

    @staticmethod
    def _get_window_class(hwnd: Optional[int]) -> str:
        if os.name != "nt" or not hwnd:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(
                ctypes.c_void_p(hwnd),
                buffer,
                len(buffer),
            )
            return buffer.value
        except Exception:
            return ""

    @staticmethod
    def _get_window_process_id(window: Any) -> Optional[int]:
        hwnd = ScreenManager._get_window_handle(window)
        if os.name != "nt" or not hwnd:
            return None
        try:
            pid = ctypes.c_ulong()
            result = ctypes.windll.user32.GetWindowThreadProcessId(
                ctypes.c_void_p(hwnd),
                ctypes.byref(pid),
            )
            return int(pid.value) if result and pid.value else None
        except Exception:
            return None

    @staticmethod
    def _get_window_process_name(window: Any) -> str:
        pid = ScreenManager._get_window_process_id(window)
        if not pid:
            return ""
        try:
            import psutil

            return str(psutil.Process(pid).name() or "")
        except Exception:
            return ""

    def _is_chrome_window(self, window: Any) -> bool:
        """Identifica Chrome por su proceso real, no por Chrome_WidgetWin."""
        if window is None:
            return False
        try:
            process_name = self._get_window_process_name(window).casefold()
            if process_name:
                return process_name == "chrome.exe"

            # Fallback únicamente cuando no se pudo consultar el proceso.
            hwnd = self._get_window_handle(window)
            window_class = self._get_window_class(hwnd).casefold()
            title = str(getattr(window, "title", "") or "").strip().casefold()
            if window_class == "chrome_widgetwin_1" and "chrome" in title:
                return True
            return title == "google chrome" or title.endswith(" - google chrome")
        except Exception:
            return False

    @staticmethod
    def _window_has_valid_size(window: Any) -> bool:
        try:
            return (
                int(getattr(window, "width", 0) or 0) > 0
                and int(getattr(window, "height", 0) or 0) > 0
            )
        except Exception:
            return False

    @staticmethod
    def _window_is_visible(window: Any) -> bool:
        """Comprueba visibilidad real mediante Win32 cuando es posible."""
        hwnd = ScreenManager._get_window_handle(window)
        if os.name == "nt" and hwnd:
            try:
                return bool(ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(hwnd)))
            except Exception:
                pass

        try:
            return bool(getattr(window, "is_visible", True))
        except Exception:
            return True

    @staticmethod
    def _window_is_minimized(window: Any) -> bool:
        """Comprueba si una ventana está minimizada según Windows."""
        hwnd = ScreenManager._get_window_handle(window)
        if os.name == "nt" and hwnd:
            try:
                return bool(ctypes.windll.user32.IsIconic(ctypes.c_void_p(hwnd)))
            except Exception:
                pass

        try:
            return bool(getattr(window, "isMinimized", False))
        except Exception:
            return False

    def _restore_and_maximize_window(self, window: Any) -> bool:
        """Restaura y maximiza temporalmente una ventana existente."""
        if window is None:
            return False

        hwnd = self._get_window_handle(window)

        if os.name == "nt" and hwnd:
            try:
                user32 = ctypes.windll.user32
                user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
                time.sleep(0.25)
                user32.ShowWindow(ctypes.c_void_p(hwnd), 3)  # SW_MAXIMIZE
                time.sleep(0.5)

                rect = RECT()
                if user32.GetWindowRect(
                    ctypes.c_void_p(hwnd),
                    ctypes.byref(rect),
                ):
                    width = int(rect.right) - int(rect.left)
                    height = int(rect.bottom) - int(rect.top)
                    if width > 0 and height > 0:
                        logger.info(
                            "[SCREEN-MANAGER] Ventana HWND=%s restaurada/maximizada -> "
                            "pos=(%s,%s) size=%sx%s",
                            hwnd,
                            rect.left,
                            rect.top,
                            width,
                            height,
                        )
                return True
            except Exception as exc:
                logger.debug(
                    "[SCREEN-MANAGER] Win32 no pudo restaurar/maximizar HWND %s: %s",
                    hwnd,
                    exc,
                )

        try:
            if hasattr(window, "restore"):
                window.restore()
                time.sleep(0.25)
            if hasattr(window, "maximize"):
                window.maximize()
                time.sleep(0.5)
            return True
        except Exception as exc:
            logger.debug(
                "[SCREEN-MANAGER] No se pudo restaurar/maximizar ventana: %s",
                exc,
            )
            return False

    def get_chrome_windows(self) -> List[Any]:
        """
        Enumera ventanas reales de Chrome evitando depender del orden que
        devuelva pygetwindow.

        En Windows se reconstruye el orden Z con EnumWindows. Así, cuando
        existen varias ventanas de Chrome, la primera ventana visible/no
        minimizada representa la candidata que el usuario está viendo, en
        lugar de elegir arbitrariamente una ventana auxiliar o minimizada.
        """
        windows_by_hwnd: Dict[int, Any] = {}
        try:
            for window in gw.getAllWindows():
                hwnd = self._get_window_handle(window)
                if hwnd is None:
                    continue
                windows_by_hwnd[hwnd] = window
        except Exception as exc:
            logger.debug(
                "[SCREEN-MANAGER] No se pudo construir el índice de ventanas: %s",
                exc,
            )

        ordered_windows: List[Any] = []
        seen_handles: Set[int] = set()

        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                callback_type = ctypes.WINFUNCTYPE(
                    ctypes.c_bool,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                )

                def _enum_callback(hwnd, _lparam):
                    try:
                        hwnd_int = int(
                            ctypes.cast(
                                hwnd,
                                ctypes.c_void_p,
                            ).value
                            or 0
                        )
                        if not hwnd_int or hwnd_int in seen_handles:
                            return True

                        window = windows_by_hwnd.get(hwnd_int)
                        if window is None:
                            return True

                        if not self._is_chrome_window(window):
                            return True

                        if not self._window_has_valid_size(window):
                            return True

                        seen_handles.add(hwnd_int)
                        ordered_windows.append(window)
                    except Exception:
                        pass
                    return True

                callback = callback_type(_enum_callback)
                user32.EnumWindows(callback, 0)
            except Exception as exc:
                logger.debug(
                    "[SCREEN-MANAGER] EnumWindows no disponible para Chrome: %s",
                    exc,
                )

        # Fallback para plataformas/entornos donde EnumWindows no esté disponible.
        if not ordered_windows:
            try:
                for window in gw.getAllWindows():
                    try:
                        if not self._is_chrome_window(window):
                            continue
                        if not self._window_has_valid_size(window):
                            continue
                        hwnd = self._get_window_handle(window)
                        if hwnd is not None and hwnd in seen_handles:
                            continue
                        if hwnd is not None:
                            seen_handles.add(hwnd)
                        ordered_windows.append(window)
                    except Exception:
                        continue
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)

        # Las ventanas visibles y no minimizadas siempre preceden a las
        # minimizadas. Dentro de cada grupo se conserva el orden Z detectado
        # por Windows.
        ordered_windows.sort(
            key=lambda window: (
                self._window_is_minimized(window),
                not self._window_is_visible(window),
            )
        )

        return ordered_windows

    def get_chrome_window_on_monitor(
        self,
        monitor_num: int,
        prefer_foreground: bool = True,
    ) -> Optional[Any]:
        monitor = self.get_monitor(monitor_num)
        if monitor is None:
            return None

        chrome_windows = self.get_chrome_windows()
        if not chrome_windows:
            return None

        if prefer_foreground:
            foreground = self.get_foreground_window()
            if foreground is not None and self._is_chrome_window(foreground):
                foreground_monitor = self.get_monitor_for_window(foreground)
                if (
                    foreground_monitor is not None
                    and foreground_monitor.monitor_id == monitor.monitor_id
                ):
                    if self._window_is_minimized(foreground):
                        self._restore_and_maximize_window(foreground)
                    return foreground

        candidates = []
        for window in chrome_windows:
            window_monitor = self.get_monitor_for_window(window)
            if (
                window_monitor is not None
                and window_monitor.monitor_id == monitor.monitor_id
            ):
                candidates.append(window)

        if not candidates:
            return None

        # Como get_chrome_windows() ya prioriza ventanas visibles y no
        # minimizadas, candidates[0] es la opción más fiable. Si la ventana
        # está minimizada, la restauramos/maximizamos antes de usarla.
        selected = candidates[0]
        if self._window_is_minimized(selected):
            self._restore_and_maximize_window(selected)
        return selected

    def get_chrome_monitor(
        self,
        prefer_foreground: bool = True,
    ) -> Optional[MonitorInfo]:
        """Detecta el monitor real de Chrome.

        Si Chrome está minimizado, primero se identifica su posición normal,
        después se restaura y maximiza esa misma ventana y finalmente se lee
        su rectángulo Win32 real para decidir el monitor.

        Cuando existen varias ventanas, una ventana visible en el monitor
        primario tiene prioridad. Si no queda ninguna visible, se prioriza la
        ventana minimizada cuya posición restaurada pertenece al monitor
        primario. Esto evita que una ventana auxiliar en otro monitor se elija
        solo porque sea la ventana foreground.
        """
        windows = self.get_chrome_windows()
        if not windows:
            return None

        visible_candidates: List[Tuple[Any, MonitorInfo]] = []
        minimized_candidates: List[Tuple[Any, MonitorInfo]] = []

        for window in windows:
            monitor = self.get_monitor_for_window(window)
            if monitor is None:
                continue

            visible = self._window_is_visible(window)
            minimized = self._window_is_minimized(window)
            title = str(getattr(window, "title", "") or "").strip()

            logger.info(
                "[SCREEN-MANAGER] Chrome candidato hwnd=%s monitor=%s visible=%s minimized=%s title=%r",
                self._get_window_handle(window),
                monitor.monitor_id,
                visible,
                minimized,
                title[:120],
            )

            if visible and not minimized:
                visible_candidates.append((window, monitor))
            else:
                minimized_candidates.append((window, monitor))

        primary = self.get_primary_monitor()

        # 1. Chrome visible y ya restaurado.
        if visible_candidates:
            if primary is not None:
                primary_candidates = [
                    item
                    for item in visible_candidates
                    if item[1].monitor_id == primary.monitor_id
                ]
                if primary_candidates:
                    window, monitor = max(
                        primary_candidates,
                        key=lambda item: self._get_window_area(item[0]),
                    )
                    logger.info(
                        "[SCREEN-MANAGER] Chrome visible en monitor primario -> monitor %s.",
                        monitor.monitor_id,
                    )
                    return monitor

            if prefer_foreground:
                foreground = self.get_foreground_window()
                if foreground is not None and self._is_chrome_window(foreground):
                    foreground_monitor = self.get_monitor_for_window(foreground)
                    if foreground_monitor is not None:
                        for window, monitor in visible_candidates:
                            if self._get_window_handle(
                                window
                            ) == self._get_window_handle(foreground):
                                logger.info(
                                    "[SCREEN-MANAGER] Chrome foreground -> monitor %s.",
                                    foreground_monitor.monitor_id,
                                )
                                return foreground_monitor

            try:
                cursor_x, cursor_y = pyautogui.position()
                for window, monitor in visible_candidates:
                    if monitor.contains_point(cursor_x, cursor_y):
                        logger.info(
                            "[SCREEN-MANAGER] Chrome bajo cursor -> monitor %s.",
                            monitor.monitor_id,
                        )
                        return monitor
            except Exception as exc:
                logger.debug(
                    "[SCREEN-MANAGER] No se pudo usar cursor para seleccionar Chrome: %s",
                    exc,
                )

            window, monitor = max(
                visible_candidates,
                key=lambda item: self._get_window_area(item[0]),
            )
            logger.info(
                "[SCREEN-MANAGER] Chrome visible seleccionado -> monitor %s.",
                monitor.monitor_id,
            )
            return monitor

        # 2. No hay Chrome visible/restaurado. Elegimos una ventana minimizada
        #    usando primero su posición normal conocida.
        if minimized_candidates:
            candidates = minimized_candidates
            if primary is not None:
                primary_candidates = [
                    item
                    for item in candidates
                    if item[1].monitor_id == primary.monitor_id
                ]
                if primary_candidates:
                    candidates = primary_candidates

            window, normal_monitor = max(
                candidates,
                key=lambda item: self._get_window_area(item[0]),
            )

            hwnd = self._get_window_handle(window)
            logger.info(
                "[SCREEN-MANAGER] Chrome minimizado detectado (hwnd=%s) en posición normal "
                "sobre monitor %s; restaurando y maximizando para verificar monitor real.",
                hwnd,
                normal_monitor.monitor_id,
            )

            self._restore_and_maximize_window(window)
            time.sleep(0.5)

            actual_monitor = self.get_monitor_for_window(window)
            if actual_monitor is not None:
                logger.info(
                    "[SCREEN-MANAGER] Chrome restaurado/maximizado -> monitor %s.",
                    actual_monitor.monitor_id,
                )
                return actual_monitor

            logger.info(
                "[SCREEN-MANAGER] No se pudo releer la geometría después de maximizar; "
                "se conserva monitor %s de la posición normal.",
                normal_monitor.monitor_id,
            )
            return normal_monitor

        return None

    @staticmethod
    def _get_window_area(window: Any) -> int:
        """Devuelve el área aproximada de una ventana en píxeles."""
        try:
            width = max(0, int(getattr(window, "width", 0) or 0))
            height = max(0, int(getattr(window, "height", 0) or 0))
            return width * height
        except Exception:
            return 0

    def get_calibration_monitor(self) -> Optional[MonitorInfo]:
        chrome_monitor = self.get_chrome_monitor(prefer_foreground=True)
        if chrome_monitor is not None:
            logger.info(
                "[SCREEN-MANAGER] Chrome abierto en monitor %s.",
                chrome_monitor.monitor_id,
            )
            return chrome_monitor

        if len(self.monitors) <= 1:
            monitor = self.get_primary_monitor()
            if monitor:
                logger.info(
                    "[SCREEN-MANAGER] Setup de una pantalla: monitor %s.",
                    monitor.monitor_id,
                )
            return monitor

        active_monitor = self.get_active_monitor()
        alternate = self.get_alternate_monitor(
            active_monitor.monitor_id if active_monitor else None
        )
        if alternate is not None:
            logger.info(
                "[SCREEN-MANAGER] Monitor activo=%s; monitor de calibración=%s.",
                active_monitor.monitor_id if active_monitor else "desconocido",
                alternate.monitor_id,
            )
            return alternate
        return active_monitor or self.get_primary_monitor()

    # ========================================================================
    # MOVIMIENTO DE VENTANAS
    # ========================================================================

    def is_window_minimized(self, window: Any) -> bool:
        """Indica si una ventana está minimizada según Win32."""
        hwnd = self._get_window_handle(window)
        if os.name != "nt" or not hwnd:
            try:
                return bool(getattr(window, "isMinimized", False))
            except Exception:
                return False
        try:
            return bool(ctypes.windll.user32.IsIconic(ctypes.c_void_p(hwnd)))
        except Exception:
            return False

    def prepare_window_for_calibration(self, window: Any) -> Optional[MonitorInfo]:
        """Restaura/maximiza cualquier ventana y devuelve su monitor real.

        No conoce ninguna aplicación concreta y no mueve la ventana de monitor.
        La posición final se determina mediante Win32 + la topología real.
        """
        hwnd = self._get_window_handle(window)
        if not hwnd or os.name != "nt":
            return None

        try:
            user32 = ctypes.windll.user32
            if not user32.IsWindow(ctypes.c_void_p(hwnd)):
                return None

            if bool(user32.IsIconic(ctypes.c_void_p(hwnd))):
                logger.info(
                    "[SCREEN-MANAGER] Restaurando ventana minimizada para calibración | HWND=%s",
                    hwnd,
                )
                user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
                time.sleep(0.6)

            user32.ShowWindow(ctypes.c_void_p(hwnd), 3)  # SW_MAXIMIZE
            time.sleep(0.8)

            try:
                user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            except Exception:
                pass
            time.sleep(0.2)

            refreshed = None
            for candidate in gw.getAllWindows():
                if self._get_window_handle(candidate) == hwnd:
                    refreshed = candidate
                    break
            if refreshed is not None:
                window = refreshed

            monitor = self.get_monitor_for_window(window)
            if monitor is None:
                return None

            geometry = self._get_window_geometry(window)
            logger.info(
                "[SCREEN-MANAGER] Ventana preparada para calibración | HWND=%s | monitor=%s | geometría=%s",
                hwnd,
                monitor.monitor_id,
                geometry,
            )
            return monitor
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return None

    def move_window_to_monitor(
        self,
        window_title: str,
        monitor_num: int,
    ) -> bool:
        try:
            monitor = self.get_monitor(monitor_num)
            if monitor is None:
                return False

            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return False

            window = windows[0]
            try:
                if hasattr(window, "restore"):
                    window.restore()
            except Exception:
                pass

            window.moveTo(monitor.left, monitor.top)

            if self.chrome_config.maximized and hasattr(window, "maximize"):
                try:
                    window.maximize()
                except Exception:
                    pass

            time.sleep(0.5)
            current_monitor = self.get_monitor_for_window(window)
            return bool(
                current_monitor is not None
                and current_monitor.monitor_id == monitor.monitor_id
            )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

    # ========================================================================
    # CHROME - APERTURA SEGURA
    # ========================================================================

    def _find_chrome_executable(self) -> Optional[str]:
        if os.name != "nt":
            return None

        candidates: List[Path] = []
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(env_name)
            if root:
                candidates.append(
                    Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
                )

        for path in candidates:
            try:
                if path.exists():
                    return str(path)
            except OSError:
                continue
        return None

    def _snapshot_chrome_handles(self) -> Set[int]:
        return {
            hwnd
            for hwnd in (
                self._get_window_handle(window) for window in self.get_chrome_windows()
            )
            if hwnd is not None
        }

    def _find_new_chrome_window(
        self,
        previous_handles: Set[int],
        monitor: Optional[MonitorInfo] = None,
        timeout: float = 8.0,
    ) -> Optional[Any]:
        deadline = time.monotonic() + max(0.0, float(timeout))

        while time.monotonic() < deadline:
            new_windows: List[Any] = []
            for window in self.get_chrome_windows():
                hwnd = self._get_window_handle(window)
                if hwnd is not None and hwnd in previous_handles:
                    continue
                new_windows.append(window)

            if monitor is not None:
                target = [
                    window
                    for window in new_windows
                    if (
                        self.get_monitor_for_window(window) is not None
                        and self.get_monitor_for_window(window).monitor_id
                        == monitor.monitor_id
                    )
                ]
                if target:
                    return target[-1]

            if new_windows:
                return new_windows[-1]

            time.sleep(0.25)
        return None

    @staticmethod
    def _activate_window(window: Any) -> bool:
        if window is None:
            return False
        try:
            window.activate()
            return True
        except Exception:
            return False

    def _launch_chrome_for_calibration(
        self,
        monitor: MonitorInfo,
    ) -> bool:
        chrome_exe = self._find_chrome_executable()
        if not chrome_exe:
            logger.ERROR("[SCREEN-MANAGER] No se encontró chrome.exe  [file:screen_manager.py, method:open_chrome_window, line:1574]")
            return False

        previous_handles = self._snapshot_chrome_handles()

        width = min(
            max(1, int(self.chrome_config.default_width)),
            monitor.width,
        )
        height = min(
            max(1, int(self.chrome_config.default_height)),
            monitor.height,
        )
        x = monitor.left + max(0, (monitor.width - width) // 2)
        y = monitor.top + max(0, (monitor.height - height) // 2)

        command = [
            chrome_exe,
            "--new-window",
            f"--window-position={x},{y}",
            f"--window-size={width},{height}",
            "https://www.google.com",
        ]
        if self.chrome_config.maximized:
            command.append("--start-maximized")

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

        window = self._find_new_chrome_window(
            previous_handles,
            monitor=monitor,
            timeout=10.0,
        )
        if window is None:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

        try:
            current_monitor = self.get_monitor_for_window(window)
            if (
                current_monitor is None
                or current_monitor.monitor_id != monitor.monitor_id
            ):
                if hasattr(window, "restore"):
                    try:
                        window.restore()
                    except Exception:
                        pass
                window.moveTo(monitor.left, monitor.top)
                time.sleep(0.5)
                current_monitor = self.get_monitor_for_window(window)

            if current_monitor is not None and self.chrome_config.maximized:
                try:
                    window.maximize()
                except Exception:
                    pass

            self._activate_window(window)
        except Exception as exc:
            logger.warning(
                "[SCREEN-MANAGER] Chrome se abrió, pero no se pudo verificar "
                "completamente su posición: %s",
                exc,
            )

        return True

    def open_chrome_calibration_tab(self, monitor_num: int) -> bool:
        try:
            monitor = self.get_monitor(monitor_num)
            if monitor is None:
                return False

            chrome_windows = self.get_chrome_windows()
            if chrome_windows:
                selected = self.get_chrome_window_on_monitor(
                    monitor_num,
                    prefer_foreground=True,
                )
                if selected is None:
                    logger.warning(
                        "[SCREEN-MANAGER] Chrome está abierto, pero no hay "
                        "ninguna ventana en %s. No se moverá ninguna ventana existente.",
                        monitor.screen_key,
                    )
                    return False

                if not self._activate_window(selected):
                    logger.warning(
                        "[SCREEN-MANAGER] No se pudo activar Chrome en %s",
                        monitor.screen_key,
                    )

                time.sleep(0.5)
                pyautogui.hotkey("ctrl", "t")
                time.sleep(0.5)
                pyautogui.write("https://www.google.com", interval=0.01)
                pyautogui.press("enter")
                time.sleep(0.8)

                logger.info(
                    "[SCREEN-MANAGER] Nueva pestaña de calibración abierta "
                    "en Chrome existente, monitor %s.",
                    monitor.screen_key,
                )
                return True

            return self._launch_chrome_for_calibration(monitor)

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

    # ========================================================================
    # CHROME - APERTURA NORMAL
    # ========================================================================

    def open_chrome_on_monitor(self, monitor_num: int) -> bool:
        try:
            monitor = self.get_monitor(monitor_num)
            if monitor is None:
                return False

            chrome_exe = self._find_chrome_executable()
            previous_handles = self._snapshot_chrome_handles()

            width = min(
                max(1, int(self.chrome_config.default_width)),
                monitor.width,
            )
            height = min(
                max(1, int(self.chrome_config.default_height)),
                monitor.height,
            )
            x = monitor.left + max(0, (monitor.width - width) // 2)
            y = monitor.top + max(0, (monitor.height - height) // 2)

            if not chrome_exe:
                import webbrowser

                webbrowser.open_new("https://www.google.com")
            else:
                command = [
                    chrome_exe,
                    "--new-window",
                    f"--window-position={x},{y}",
                    f"--window-size={width},{height}",
                    "https://www.google.com",
                ]
                if self.chrome_config.maximized:
                    command.append("--start-maximized")
                subprocess.Popen(command)

            window = self._find_new_chrome_window(
                previous_handles,
                monitor=monitor,
                timeout=10.0,
            )
            if window is None:
                return False

            current_monitor = self.get_monitor_for_window(window)
            if (
                current_monitor is None
                or current_monitor.monitor_id != monitor.monitor_id
            ):
                try:
                    if hasattr(window, "restore"):
                        window.restore()
                except Exception:
                    pass
                try:
                    window.moveTo(monitor.left, monitor.top)
                except Exception:
                    return False
                time.sleep(0.5)
                current_monitor = self.get_monitor_for_window(window)

            if (
                current_monitor is None
                or current_monitor.monitor_id != monitor.monitor_id
            ):
                return False

            if self.chrome_config.maximized and hasattr(window, "maximize"):
                try:
                    window.maximize()
                except Exception:
                    pass

            self._activate_window(window)
            logger.info(
                "[SCREEN-MANAGER] Chrome abierto en %s.",
                monitor.screen_key,
            )
            return True

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

    # ========================================================================
    # CAPTURA
    # ========================================================================

    def capture_monitor(self, monitor_num: int) -> Optional[str]:
        """
        Captura exactamente el rectángulo físico del monitor.

        En Windows se prioriza ImageGrab con all_screens=True para que los
        monitores con coordenadas negativas del escritorio virtual se capturen
        correctamente. PyAutoGUI queda como fallback.
        """
        logger.info(
            "[SCREEN-MANAGER] Iniciando captura del monitor %s...",
            monitor_num,
        )

        try:
            monitor = self.get_monitor(monitor_num)
            if monitor is None:
                logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
                return None

            expected_size = (monitor.width, monitor.height)
            bbox = (
                monitor.left,
                monitor.top,
                monitor.right,
                monitor.bottom,
            )

            screenshot = None

            # Primero el backend que entiende explícitamente el escritorio
            # virtual completo en Windows.
            if os.name == "nt":
                try:
                    screenshot = ImageGrab.grab(
                        bbox=bbox,
                        all_screens=True,
                    )
                except TypeError:
                    screenshot = ImageGrab.grab(bbox=bbox)
                except Exception as exc:
                    logger.warning(
                        "[SCREEN-MANAGER] ImageGrab falló en %s: %s. "
                        "Se intentará PyAutoGUI.",
                        monitor.screen_key,
                        exc,
                    )

            # Fallback para sistemas sin all_screens o si ImageGrab falla.
            if screenshot is None:
                try:
                    screenshot = pyautogui.screenshot(
                        region=(
                            monitor.left,
                            monitor.top,
                            monitor.width,
                            monitor.height,
                        )
                    )
                except Exception as exc:
                    logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
                    return None

            # Si el backend no devolvió el tamaño exacto, repetir con ImageGrab.
            if screenshot.size != expected_size:
                logger.warning(
                    "[SCREEN-MANAGER] Captura inicial de %s: %sx%s; esperado=%sx%s. "
                    "Se reintenta con ImageGrab.",
                    monitor.screen_key,
                    screenshot.width,
                    screenshot.height,
                    expected_size[0],
                    expected_size[1],
                )
                try:
                    screenshot = ImageGrab.grab(
                        bbox=bbox,
                        all_screens=True,
                    )
                except TypeError:
                    screenshot = ImageGrab.grab(bbox=bbox)
                except Exception as exc:
                    logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
                    return None

            if screenshot.size != expected_size:
                logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
                return None

            timestamp = int(time.time() * 1000)
            temp_path = self.project_root / (
                f"temp_monitor_{monitor.monitor_id}_{timestamp}.png"
            )
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(temp_path)

            logger.info(
                "[SCREEN-MANAGER] Captura de %s guardada: %s",
                monitor.screen_key,
                temp_path,
            )
            return str(temp_path)

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return None

    # ========================================================================
    # CIERRE EXPLÍCITO DE CHROME
    # ========================================================================

    def close_chrome(self) -> bool:
        """Cierra Chrome como acción explícita del usuario."""
        try:
            chrome_windows = self.get_chrome_windows()
            if not chrome_windows:
                return False

            closed_count = 0
            for window in chrome_windows:
                try:
                    window.close()
                    closed_count += 1
                except Exception as exc:
                    logger.warning(
                        "[SCREEN-MANAGER] No se pudo cerrar una ventana de Chrome: %s",
                        exc,
                    )

            time.sleep(1.0)
            return closed_count > 0

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_manager.py", "method", 382)
            return False

    # ========================================================================
    # COMPATIBILIDAD
    # ========================================================================

    def move_window_to_screen(
        self,
        window_title: str,
        screen_num: int = 1,
    ) -> bool:
        return self.move_window_to_monitor(window_title, screen_num)


# ============================================================================
# SINGLETON
# ============================================================================


_screen_manager_instance: Optional[ScreenManager] = None


def get_screen_manager() -> ScreenManager:
    global _screen_manager_instance
    if _screen_manager_instance is None:
        _screen_manager_instance = ScreenManager()
    return _screen_manager_instance


def get_monitor_info(monitor_num: int) -> Optional[MonitorInfo]:
    return get_screen_manager().get_monitor(monitor_num)


def get_monitor_setup() -> Dict[str, Any]:
    return get_screen_manager().setup
