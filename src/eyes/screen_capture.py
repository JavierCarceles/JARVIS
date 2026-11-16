# src/eyes/screen_capture.py

"""
Sistema de captura de pantalla sin dependencias del cerebro.

Este módulo proporciona funcionalidades de captura de pantalla
sin importar el Brain class para evitar circular imports.
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import pyautogui
from PIL import ImageGrab

from src.utils.logger import get_logger
from src.utils.screen_manager import get_monitor_info, get_screen_manager

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


# ---------------------------------------------------------------------------
# DXcam: backend opcional de captura continua de frames (Windows).
# Unidad 3.8.6.3.3.13 (hija 3.8.6.3.3.13.1).
# ---------------------------------------------------------------------------

try:
    _USER32 = ctypes.windll.user32
except Exception:
    _USER32 = None


def get_cursor_position():
    """Devuelve la posicion del cursor mediante la API del SO (GetCursorPos).

    Es independiente de dxcam: no se asume que dxcam pinte el cursor en la
    captura, por lo que la posicion del cursor se verifica por separado.
    Retorna (x, y) o None si la API no esta disponible.
    """
    if _USER32 is None or os.name != "nt":
        return None
    try:
        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = _POINT()
        _USER32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
        _USER32.GetCursorPos.restype = wintypes.BOOL
        if _USER32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except Exception:
        pass
    return None


class DXcamCapture:
    """
    Backend opcional de captura continua de frames basado en dxcam (Windows).

    Se crea una camara por salida real (output_idx). La salida de dxcam NO se
    asume que coincida con DISPLAYn ni con el indice de ScreenManager: se
    mapea a la identidad de monitor de ScreenManager comparando resolucion,
    posicion y bandera de monitor primario.

    Si dxcam no esta instalada o la camara no puede crearse, se reporta el
    backend efectivo y el error, sin ocultar el fallo. El fallback a mss se
    define en la unidad 3.8.6.3.3.13.2.
    """

    def __init__(self, output_idx: int = 0, backend: str = "dxgi", region=None):
        self.output_idx = int(output_idx)
        self.backend = str(backend)
        self.region = region
        self._dxcam = None
        self._camera = None
        self._monitor_info = None
        self._effective_backend = None
        self._available = False
        self._error = None
        self._last_frame = None
        self._last_frame_time = None
        self._last_frame_ticks = None
        self._import_dxcam()

    def _import_dxcam(self):
        try:
            import dxcam as _dxcam

            self._dxcam = _dxcam
            self._available = True
        except ImportError as exc:
            self._dxcam = None
            self._available = False
            self._error = "dxcam no instalado: %s" % exc

    def enumerate_outputs(self):
        """Lista las salidas de dxcam con resolucion y bandera primaria.

        Los datos se leen de dxcam.output_info() y se devuelven como lista de
        diccionarios: output_idx, width, height, rotation, primary.
        """
        outputs = []
        if self._dxcam is None:
            return outputs
        try:
            raw = self._dxcam.output_info()
        except Exception as exc:
            self._error = "No se pudieron enumerar salidas dxcam: %s" % exc
            return outputs
        pattern = re.compile(
            r"Output\[(\d+)\]\s*:\s*Res:\((\d+)\s*,\s*(\d+)\)\s*Rot:(\d+)\s*Primary:(True|False)"
        )
        for line in str(raw).splitlines():
            line = line.strip()
            if not line:
                continue
            match = pattern.search(line)
            if match:
                outputs.append(
                    {
                        "output_idx": int(match.group(1)),
                        "width": int(match.group(2)),
                        "height": int(match.group(3)),
                        "rotation": int(match.group(4)),
                        "primary": match.group(5) == "True",
                    }
                )
        return outputs

    def match_monitor(self, screen_manager=None):
        """Mapea la salida dxcam de output_idx a un MonitorInfo de ScreenManager.

        La comparacion usa resolucion y bandera primaria (y posicion cuando
        este disponible), nunca el indice numerico, porque el indice de dxcam
        no tiene por que coincidir con DISPLAYn ni con el de ScreenManager.
        """
        if screen_manager is None:
            screen_manager = get_screen_manager()
        outputs = self.enumerate_outputs()
        target = None
        for out in outputs:
            if out["output_idx"] == self.output_idx:
                target = out
                break
        if target is None and outputs:
            target = outputs[0]
        if target is None:
            self._monitor_info = None
            return None
        candidates = list(getattr(screen_manager, "monitors", []) or [])
        for monitor in candidates:
            if (
                int(monitor.width) == int(target["width"])
                and int(monitor.height) == int(target["height"])
                and bool(monitor.is_primary) == bool(target["primary"])
            ):
                self._monitor_info = monitor
                return monitor
        for monitor in candidates:
            if int(monitor.width) == int(target["width"]) and int(monitor.height) == int(target["height"]):
                self._monitor_info = monitor
                return monitor
        if candidates:
            self._monitor_info = candidates[0]
            return candidates[0]
        self._monitor_info = None
        return None

    def start(self):
        """Crea la camara dxcam y comienza la captura continua.

        Retorna True si la captura inicio. Si el backend solicitado no esta
        disponible, se informa el backend efectivo y se degrada sin ocultar
        el fallo (self._error y self._effective_backend quedan poblados).
        """
        if self._dxcam is None:
            self._error = self._error or "dxcam no disponible"
            return False
        backends = [self.backend]
        if self.backend != "dxgi":
            backends.append("dxgi")
        last_exc = None
        for backend in backends:
            try:
                camera = self._dxcam.create(
                    device_idx=0,
                    output_idx=self.output_idx,
                    region=self.region,
                    output_color="RGB",
                    backend=backend,
                )
                camera.start()
                self._camera = camera
                self._effective_backend = getattr(camera, "backend", backend)
                self._available = True
                self._error = None
                self._last_frame = None
                self._last_frame_time = None
                self._last_frame_ticks = None
                return True
            except Exception as exc:
                last_exc = exc
                self._error = "backend %s no disponible: %s" % (backend, exc)
        self._camera = None
        self._effective_backend = None
        self._available = False
        return False

    def stop(self):
        """Detiene la captura continua sin liberar la camara."""
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass

    def release(self):
        """Libera la camara y sus recursos."""
        if self._camera is not None:
            try:
                self._camera.release()
            except Exception:
                pass
            self._camera = None
        self._available = False
        self._effective_backend = None

    def grab(self):
        """Captura un frame puntual y lo devuelve como array numpy.

        Actualiza _last_frame, _last_frame_time y _last_frame_ticks.
        Retorna None si no hay camara.
        """
        if self._camera is None:
            return None
        try:
            frame = self._camera.grab()
        except Exception:
            return None
        if frame is None:
            return None
        self._last_frame = frame
        self._last_frame_time = getattr(self._camera, "latest_frame_time", None)
        self._last_frame_ticks = getattr(self._camera, "latest_frame_ticks", None)
        return frame

    def get_latest_frame(self):
        """Devuelve el ultimo frame capturado en modo continuo sin bloquear."""
        if self._camera is None:
            return None
        try:
            frame = self._camera.get_latest_frame()
        except Exception:
            return None
        if frame is not None:
            self._last_frame = frame
            self._last_frame_time = getattr(self._camera, "latest_frame_time", None)
            self._last_frame_ticks = getattr(self._camera, "latest_frame_ticks", None)
        return frame

    @property
    def is_capturing(self):
        if self._camera is None:
            return False
        return bool(getattr(self._camera, "is_capturing", False))

    @property
    def is_released(self):
        if self._camera is None:
            return True
        return bool(getattr(self._camera, "is_released", True))

    @property
    def effective_backend(self):
        return self._effective_backend

    @property
    def available(self):
        return self._available

    @property
    def error(self):
        return self._error

    @property
    def monitor_info(self):
        return self._monitor_info

    @property
    def last_frame(self):
        return self._last_frame

    @property
    def last_frame_time(self):
        return self._last_frame_time

    @property
    def last_frame_ticks(self):
        return self._last_frame_ticks


def evaluate_dxcam_backends(output_idx: int = 0):
    """Evalua dxcam en el equipo real: backends, formatos de pixel y cursor.

    Compara dxgi y winrt (cuando este disponible), reporta el backend efectivo,
    resolucion y formato de frame, y verifica la posicion del cursor mediante
    la API del SO (GetCursorPos), sin confiar en que dxcam lo pinte.
    """
    results = {
        "dxcam_available": False,
        "backends": [],
        "effective_backend": None,
        "frame_shape": None,
        "frame_dtype": None,
        "cursor_position": get_cursor_position(),
        "error": None,
    }
    try:
        import dxcam as dxcam_mod

        results["dxcam_available"] = True
    except ImportError as exc:
        results["error"] = "dxcam no instalado: %s" % exc
        return results
    for backend in ("dxgi", "winrt"):
        backend_result = {"backend": backend, "available": False, "error": None}
        try:
            cam = dxcam_mod.create(
                device_idx=0, output_idx=output_idx, backend=backend
            )
            backend_result["available"] = True
            backend_result["width"] = int(cam.width)
            backend_result["height"] = int(cam.height)
            backend_result["region"] = cam.region
            frame = cam.grab()
            if frame is not None:
                backend_result["frame_shape"] = tuple(frame.shape)
                backend_result["frame_dtype"] = str(frame.dtype)
                if results["effective_backend"] is None:
                    results["effective_backend"] = backend
                    results["frame_shape"] = tuple(frame.shape)
                    results["frame_dtype"] = str(frame.dtype)
            cam.release()
        except Exception as exc:
            backend_result["available"] = False
            backend_result["error"] = str(exc)
        results["backends"].append(backend_result)
    return results