# src/eyes/screen_capture.py

"""
Sistema de captura de pantalla sin dependencias del cerebro.

Este módulo proporciona funcionalidades de captura de pantalla
sin importar el Brain class para evitar circular imports.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pyautogui
from PIL import ImageGrab

from src.utils.logger import get_logger
from src.utils.screen_manager import get_monitor_info

logger = get_logger(__name__)


class ScreenCapture:
    """
    Sistema de captura de pantalla con soporte multipantalla.
    
    Versión simplificada que no usa ScreenAnalyzer para evitar circular imports.
    """

    def __init__(self):
        """Inicializa el sistema de captura."""
        self.analyzer = None
        logger._print_log("debug", "[SCREEN-CAPTURE] Sistema de captura inicializado", "screen_capture.py", "method", 35)

    
    def _get_analyzer(self):
        """Lazy initialization of ScreenAnalyzer to avoid circular imports."""
        if self.analyzer is None:
            try:
                from src.eyes.screen import ScreenAnalyzer
                self.analyzer = ScreenAnalyzer()
            except ImportError:
                logger._print_log("warning", "[SCREEN-CAPTURE] ScreenAnalyzer no disponible (circular import evitada)", "screen_capture.py", "method", 44)

                self.analyzer = None
        return self.analyzer

    def capture_monitor(
        self,
        monitor_num: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Captura un monitor específico.

        Args:
            monitor_num: Número del monitor a capturar
            save_path: Ruta donde guardar la captura

        Returns:
            Ruta del archivo de captura o None si falla
        """
        try:
            monitor = get_monitor_info(monitor_num)

            if monitor is None:
                logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)

                return None

            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


            expected_size = (
                int(monitor.width),
                int(monitor.height),
            )

            # Captura principal
            screenshot = pyautogui.screenshot(
                region=(
                    int(monitor.left),
                    int(monitor.top),
                    int(monitor.width),
                    int(monitor.height),
                )
            )

            # Fallback si PyAutoGUI devuelve una dimensión inesperada
            if screenshot.size != expected_size:
                logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


                try:
                    screenshot = ImageGrab.grab(
                        bbox=(
                            int(monitor.left),
                            int(monitor.top),
                            int(monitor.right),
                            int(monitor.bottom),
                        ),
                        all_screens=True,
                    )
                except TypeError:
                    screenshot = ImageGrab.grab(
                        bbox=(
                            int(monitor.left),
                            int(monitor.top),
                            int(monitor.right),
                            int(monitor.bottom),
                        )
                    )

            # Ruta de salida
            if save_path is None:
                timestamp = int(time.time() * 1000)
                save_path = f"temp_monitor_{monitor.monitor_id}_{timestamp}.png"

            output_path = Path(save_path)

            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            screenshot.save(str(output_path))

            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


            if screenshot.size != expected_size:
                logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


            return str(output_path.resolve())

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)

            return None

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Captura una región del escritorio virtual.

        Las coordenadas x/y son absolutas.
        """
        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)

            bbox = (x, y, x + width, y + height)

            try:
                screenshot = ImageGrab.grab(
                    bbox=bbox,
                    all_screens=True,
                )
            except TypeError:
                screenshot = ImageGrab.grab(bbox=bbox)

            if save_path is None:
                timestamp = int(time.time() * 1000)
                save_path = f"temp_region_{timestamp}.png"

            output_path = Path(save_path)

            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            screenshot.save(str(output_path))

            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


            return str(output_path.resolve())

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)

            return None

    def capture_element(
        self,
        element_coords: dict,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Captura un elemento a partir de sus coordenadas absolutas.

        Soporta:
        - Coordenadas de elementos UI
        """
        try:
            if not isinstance(
                element_coords,
                dict,
            ):
                logger._print_log("error", r"[SCREEN-CAPTURE] Coordenadas de elemento inválidas [file:screen_capture.py, method:capture_element, line:232]", "screen_capture.py", "method", 208)

                return None

            x = int(
                element_coords.get(
                    "x",
                    0,
                )
            )

            y = int(
                element_coords.get(
                    "y",
                    0,
                )
            )

            width = int(
                element_coords.get(
                    "width",
                    0,
                )
            )

            height = int(
                element_coords.get(
                    "height",
                    0,
                )
            )

            return self.capture_region(
                x=x,
                y=y,
                width=width,
                height=height,
                save_path=save_path,
            )

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)

            return None

    def capture_active_window(
        self,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Captura la ventana activa actualmente.
        """
        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()

            if not active_window:
                logger._print_log("error", r"[SCREEN-CAPTURE] No hay ventana activa [file:screen_capture.py, method:capture_active_window, line:279]", "screen_capture.py", "method", 264)

                return None

            left = int(active_window.left)
            top = int(active_window.top)
            width = int(active_window.width)
            height = int(active_window.height)

            if width <= 0 or height <= 0:
                logger._print_log("error", r"[SCREEN-CAPTURE] Dimensiones de ventana activa inválidas [file:screen_capture.py, method:capture_active_window, line:288]", "screen_capture.py", "method", 273)

                return None

            try:
                screenshot = ImageGrab.grab(
                    bbox=(
                        left,
                        top,
                        left + width,
                        top + height,
                    ),
                    all_screens=True,
                )
            except TypeError:
                screenshot = ImageGrab.grab(
                    bbox=(
                        left,
                        top,
                        left + width,
                        top + height,
                    )
                )

            if save_path is None:
                timestamp = int(time.time() * 1000)
                save_path = f"temp_window_{timestamp}.png"

            output_path = Path(save_path)

            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            screenshot.save(str(output_path))

            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)


            return str(output_path.resolve())

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "screen_capture.py", "method", 67)

            return None

    def get_world_state(self):
        """Obtiene el estado actual del mundo."""
        analyzer = self._get_analyzer()
        if analyzer is None:
            logger._print_log("warning", r"[SCREEN-CAPTURE] ScreenAnalyzer no disponible [file:screen_capture.py, method:get_world_state, line:324]", "screen_capture.py", "method", 324)

            from src.eyes.screen import WorldState
            return WorldState(applications={}, timestamp=time.time())
        return analyzer.build_world_state()
    
    def get_application_state(self, app_name: str):
        """Obtiene el estado de una aplicación específica."""
        analyzer = self._get_analyzer()
        if analyzer is None:
            logger._print_log("warning", r"[SCREEN-CAPTURE] ScreenAnalyzer no disponible [file:screen_capture.py, method:get_application_state, line:344]", "screen_capture.py", "method", 333)

            from src.eyes.screen import ApplicationInfo, ApplicationState
            return ApplicationInfo(name=app_name, state=ApplicationState.CLOSED)
        return analyzer.analyze_application_state(app_name)


# Instancia global
_screen_capture_instance: Optional[ScreenCapture] = None


def get_screen_capture() -> ScreenCapture:
    """Obtiene la instancia global del sistema de captura."""
    global _screen_capture_instance

    if _screen_capture_instance is None:
        _screen_capture_instance = ScreenCapture()
    
    return _screen_capture_instance