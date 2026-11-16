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
from collections import deque
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import pyautogui
from PIL import ImageGrab

import numpy as np

try:
    from mss import MSS as _MssClass
    _MSS_AVAILABLE = True
    _MSS_ERROR = None
except Exception as _mss_exc:  # mss no instalado en este entorno
    _MssClass = None
    _MSS_AVAILABLE = False
    _MSS_ERROR = "mss no disponible: %s" % _mss_exc

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


def _mss_region_for_monitor(monitor_num):
    """Resuelve la geometria real de un monitor para mss.

    Usa ScreenManager (monitor fisico real con rectangulo absoluto) y nunca
    asume que el indice de mss coincide con DISPLAYn ni con el de
    ScreenManager. Retorna (region_dict, monitor) o None si no se resuelve.
    """
    try:
        monitor = get_monitor_info(int(monitor_num))
    except Exception:
        monitor = None
    if monitor is None:
        return None
    return (
        {
            "left": int(monitor.left),
            "top": int(monitor.top),
            "width": int(monitor.width),
            "height": int(monitor.height),
        },
        monitor,
    )


class MssCapture:
    """
    Captura puntual (un solo frame) mediante mss.

    Es la ruta de respaldo y el punto de captura puntual cuando DXcam no
    esta disponible. mss captura el escritorio real por region y devuelve
    un array numpy (BGRA) o None si no se puede capturar. No guarda ni
    devuelve coordenadas fisicas como parte de un catalogo global: solo
    produce el frame solicitado.
    """

    def __init__(self):
        self._available = _MSS_AVAILABLE and _MssClass is not None
        self._error = _MSS_ERROR
        self._sct = None

    @property
    def available(self):
        return self._available

    @property
    def error(self):
        return self._error

    def _open(self):
        if self._sct is None:
            if _MssClass is None:
                return None
            self._sct = _MssClass()
        return self._sct

    def close(self):
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def capture_monitor(self, monitor_num):
        """Captura un monitor real mediante mss y devuelve su frame (numpy)."""
        if not self._available:
            self._error = _MSS_ERROR or "mss no disponible"
            return None
        sct = self._open()
        if sct is None:
            self._error = "mss no disponible"
            return None
        resolved = _mss_region_for_monitor(monitor_num)
        if resolved is None:
            self._error = "no se resolvio la geometria del monitor %s" % monitor_num
            return None
        region, _monitor = resolved
        try:
            shot = sct.grab(region)
        except Exception as exc:
            self._error = "mss capture_monitor fallo: %s" % exc
            return None
        if shot is None:
            self._error = "mss devolvio frame nulo para monitor %s" % monitor_num
            return None
        self._error = None
        return np.asarray(shot)

    def capture_region(self, x, y, width, height):
        """Captura una region absoluta del escritorio mediante mss (numpy)."""
        if not self._available:
            self._error = _MSS_ERROR or "mss no disponible"
            return None
        sct = self._open()
        if sct is None:
            self._error = "mss no disponible"
            return None
        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)
        except (TypeError, ValueError):
            self._error = "coordenadas de region invalidas"
            return None
        if width <= 0 or height <= 0:
            self._error = "dimensiones de region invalidas"
            return None
        region = {"left": x, "top": y, "width": width, "height": height}
        try:
            shot = sct.grab(region)
        except Exception as exc:
            self._error = "mss capture_region fallo: %s" % exc
            return None
        if shot is None:
            self._error = "mss devolvio frame nulo para la region"
            return None
        self._error = None
        return np.asarray(shot)


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
        self._mss_fallback = MssCapture()
        self._using_fallback = False

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

        Si la camara dxcam no devuelve un frame fresco (no hay camara, la
        captura devuelve None o devuelve un frame caducado con los mismos
        ticks/tiempo que el anterior), se degrada al fallback mss: captura
        un punto real de la pantalla asignada y reporta
        `effective_backend` como "mss" sin ocultar el fallo (`error` y
        `fallback_active` quedan poblados para que el llamador lo detecte).
        Actualiza _last_frame, _last_frame_time y _last_frame_ticks.
        """
        frame = self._grab_dxcam_frame()
        if frame is not None:
            self._using_fallback = False
            self._error = None
            self._effective_backend = (
                self._effective_backend
                or getattr(self._camera, "backend", self.backend)
            )
            return frame
        return self._grab_via_mss_fallback()

    def _grab_dxcam_frame(self):
        """Intenta un frame fresco de la camara dxcam.

        Retorna None si no hay camara, la captura falla o el frame esta
        caducado (mismos ticks/tiempo que el frame previo).
        """
        if self._camera is None:
            return None
        try:
            frame = self._camera.grab()
        except Exception:
            return None
        if frame is None:
            return None
        ticks = getattr(self._camera, "latest_frame_ticks", None)
        frame_time = getattr(self._camera, "latest_frame_time", None)
        is_stale = False
        if self._last_frame is not None:
            if (
                ticks is not None
                and self._last_frame_ticks is not None
                and ticks == self._last_frame_ticks
            ):
                is_stale = True
            elif (
                ticks is None
                and frame_time is not None
                and self._last_frame_time is not None
                and frame_time == self._last_frame_time
            ):
                is_stale = True
        if is_stale:
            # Frame caducado: dxcam no produjo un frame nuevo.
            return None
        self._last_frame = frame
        self._last_frame_time = frame_time
        self._last_frame_ticks = ticks
        return frame

    def _grab_via_mss_fallback(self):
        """Fallback a mss: captura un punto real de la pantalla asignada.

        Nunca oculta el fallo de dxcam: `error` se mantiene y
        `effective_backend` se informa como "mss" solo cuando el fallback
        efectivamente captura un frame.
        """
        self._using_fallback = True
        if self._error is None:
            self._error = "dxcam sin frame disponible o camara ausente"
        if not self._mss_fallback.available:
            self._error = "dxcam sin frame disponible y fallback mss no disponible: %s" % (
                self._mss_fallback.error or "mss no instalado"
            )
            self._effective_backend = None
            return None
        monitor_num = None
        if self._monitor_info is not None:
            monitor_num = getattr(self._monitor_info, "monitor_id", None)
        if monitor_num is None:
            try:
                primary = get_screen_manager().get_primary_monitor()
                monitor_num = (
                    getattr(primary, "monitor_id", None) if primary is not None else None
                )
            except Exception:
                monitor_num = None
        if monitor_num is None:
            self._error = "dxcam sin frame disponible y no se resolvio monitor para el fallback mss"
            return None
        try:
            frame = self._mss_fallback.capture_monitor(monitor_num)
        except Exception as exc:
            self._error = "fallback mss fallo: %s" % exc
            return None
        if frame is None:
            self._error = self._error or "dxcam sin frame disponible y fallback mss devolvio None"
            self._effective_backend = None
            return None
        self._effective_backend = "mss"
        self._last_frame = frame
        self._last_frame_time = time.time()
        self._last_frame_ticks = None
        return frame

    def get_latest_frame(self):
        """Devuelve el ultimo frame capturado en modo continuo sin bloquear.

        Si no hay camara dxcam o esta no devuelve frame, degrada a una
        captura puntual mss en lugar de devolver silenciosamente None.
        """
        if self._camera is not None:
            try:
                frame = self._camera.get_latest_frame()
            except Exception:
                frame = None
            if frame is not None:
                self._using_fallback = False
                self._last_frame = frame
                self._last_frame_time = getattr(self._camera, "latest_frame_time", None)
                self._last_frame_ticks = getattr(self._camera, "latest_frame_ticks", None)
                self._effective_backend = (
                    self._effective_backend
                    or getattr(self._camera, "backend", self.backend)
                )
                return frame
            return self._grab_via_mss_fallback()
        return self._grab_via_mss_fallback()

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

    @property
    def fallback_active(self):
        """True si la ultima captura sirvio mediante el fallback mss."""
        return self._using_fallback

    @property
    def using_mss_fallback(self):
        """Alias de fallback_active."""
        return self._using_fallback

    @property
    def mss_fallback_available(self):
        """Indica si el fallback mss esta disponible en este entorno."""
        return self._mss_fallback.available

    @property
    def mss_fallback_error(self):
        """Error del fallback mss, si lo hay."""
        return self._mss_fallback.error


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
        "mss_available": _MSS_AVAILABLE,
        "mss_error": _MSS_ERROR,
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


# ---------------------------------------------------------------------------
# Captura adaptativa de frames (unidad 3.8.6.3.3.13.3).
# ---------------------------------------------------------------------------


@dataclass
class FrameInfo:
    """Metadatos de un frame entregado por la captura adaptativa.

    frame: array numpy del frame capturado, o None si no se pudo entregar.
    timestamp: marca temporal monotona (time.monotonic) de la entrega.
    backend: backend efectivo que sirvio el frame ("dxgi", "mss" o None).
    cadence: cadencia vigente en la entrega ("low" o "burst").
    is_burst: True si la entrega ocurrio dentro de una ventana de rafaga.
    transition_detected: True si este frame se interpreto como una transicion
        respecto del frame previamente entregado.
    frame_index: indice secuencial de entrega (0-based).
    fallback_active: True si el frame sirvio mediante el fallback mss.
    """

    frame: object = None
    timestamp: float = 0.0
    backend: str = None
    cadence: str = "low"
    is_burst: bool = False
    transition_detected: bool = False
    frame_index: int = 0
    fallback_active: bool = False


class AdaptiveCapture:
    """
    Captura adaptativa de frames sobre DXcamCapture (con fallback mss).

    Politica de cadencia:
    * Durante espera estable (sin transiciones) se usa cadencia baja: entre
      dos entregas transcurre al menos 1 / low_cadence_fps segundos, de modo
      que no se satura la GPU ni se mantiene un stream activo sin necesidad.
    * Al detectar una transicion (diferencia entre frames consecutivos por
      encima de transition_threshold) se entra en modo rafaga durante
      burst_window_seconds a cadencia burst_cadence_fps para capturar el
      transito completo.
    * Si no hay nuevas transiciones durante la rafaga, se vuelve a cadencia
      baja. Si transcurre idle_release_seconds sin transiciones, el stream
      subyacente se detiene y no se reactiva hasta la siguiente entrega.

    Buffer: cola acotada (deque con maxlen=max_buffer_frames) que descarta
    los frames mas antiguos al llegar los nuevos; nunca crece sin limite.

    Marca temporal: time.monotonic por entrega, monotona y no retroactiva,
    complementada con latest_frame_time/latest_frame_ticks de la camara.

    La camara subyacente se inicia en la primera entrega y se detiene/libera
    con close() o al salir del context manager; nunca se deja activa mas
    tiempo del necesario.

    Los parametros camera y clock son inyectables para pruebas deterministas.
    """

    _STATE_IDLE = "IDLE"
    _STATE_STABLE = "STABLE"
    _STATE_BURST = "BURST"

    def __init__(
        self,
        output_idx=0,
        backend="dxgi",
        region=None,
        low_cadence_fps=2.0,
        burst_cadence_fps=15.0,
        burst_window_seconds=3.0,
        transition_threshold=0.05,
        max_buffer_frames=8,
        idle_release_seconds=10.0,
        camera=None,
        clock=time.monotonic,
    ):
        self.output_idx = int(output_idx)
        self.backend = str(backend)
        self.region = region
        self.low_cadence_fps = float(low_cadence_fps)
        self.burst_cadence_fps = float(burst_cadence_fps)
        self.burst_window_seconds = float(burst_window_seconds)
        self.transition_threshold = float(transition_threshold)
        self.max_buffer_frames = int(max_buffer_frames)
        self.idle_release_seconds = float(idle_release_seconds)
        self._camera = camera
        self._owns_camera = camera is None
        self._clock = clock
        self._dxcam_capture = None
        self._capturing = False
        self._released = False
        self._state = self._STATE_IDLE
        self._last_grab_time = None
        self._last_frame = None
        self._burst_until = None
        self._idle_since = None
        self._buffer = deque(maxlen=self.max_buffer_frames)
        self._frame_index = 0
        self._last_timestamp = None
        self._error = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def _ensure_camera(self):
        """Crea y arranca la camara subyacente si todavia no esta activa."""
        if self._released:
            self._error = "AdaptiveCapture ya esta liberado"
            return None
        cam = self._dxcam_capture if self._owns_camera else self._camera
        if cam is None:
            if self._dxcam_capture is None:
                self._dxcam_capture = DXcamCapture(
                    output_idx=self.output_idx,
                    backend=self.backend,
                    region=self.region,
                )
            cam = self._dxcam_capture
        if not getattr(cam, "is_capturing", False):
            try:
                cam.start()
            except Exception as exc:
                self._error = "no se pudo iniciar la camara de captura: %s" % exc
                return None
        self._capturing = True
        self._error = None
        return cam

    def _stop_stream(self):
        """Detiene el stream subyacente sin descartar la camara (reanudable)."""
        cam = self._dxcam_capture if self._owns_camera else self._camera
        if cam is not None:
            try:
                cam.stop()
            except Exception:
                pass
        self._capturing = False
        self._state = self._STATE_IDLE
        self._burst_until = None
        self._idle_since = None

    def _release_resources(self):
        """Libera la camara y todos sus recursos (no reanudable sin nuevo objeto)."""
        cam = self._dxcam_capture if self._owns_camera else self._camera
        if cam is not None:
            try:
                cam.stop()
            except Exception:
                pass
            try:
                cam.release()
            except Exception:
                pass
        if self._owns_camera:
            self._dxcam_capture = None
        self._capturing = False
        self._released = True
        self._state = self._STATE_IDLE
        self._last_frame = None
        self._burst_until = None
        self._idle_since = None
        self._buffer.clear()
        self._error = None

    def start(self):
        """Arranca la captura adaptiva (camara subyacente en espera estable)."""
        if self._released:
            self._error = "AdaptiveCapture ya esta liberado"
            return False
        cam = self._ensure_camera()
        if cam is None:
            return False
        self._state = self._STATE_STABLE
        self._idle_since = self._clock()
        self._last_grab_time = None
        self._error = None
        return True

    def stop(self):
        """Detiene la entrega de frames sin liberar la camara."""
        self._stop_stream()

    def close(self):
        """Libera todos los recursos de captura de forma garantizada."""
        self._release_resources()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    # ------------------------------------------------------------------
    # Captura adaptativa
    # ------------------------------------------------------------------

    def _min_interval(self):
        if self._state == self._STATE_BURST and self.burst_cadence_fps > 0:
            return 1.0 / self.burst_cadence_fps
        if self.low_cadence_fps > 0:
            return 1.0 / self.low_cadence_fps
        return 0.0

    def _frame_diff(self, a, b):
        """Diferencia normalizada entre dos frames (0.0 iguales, 1.0 muy distintos)."""
        if a is None or b is None:
            return 0.0
        try:
            if a.shape != b.shape:
                return 1.0
            diff = np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()
            return float(diff / 255.0)
        except Exception:
            return 1.0

    def _monotonic_timestamp(self, now):
        """Garantiza una marca temporal monotonica y no retroactiva."""
        if self._last_timestamp is None:
            self._last_timestamp = now
            return now
        if now <= self._last_timestamp:
            self._last_timestamp += 1e-6
            return self._last_timestamp
        self._last_timestamp = now
        return now

    def _current_cadence_name(self):
        return "burst" if self._state == self._STATE_BURST else "low"

    def grab_adaptive(self):
        """
        Entrega el siguiente frame respetando la cadencia adaptativa.

        Retorna un FrameInfo cuando toca entregar segun la cadencia vigente,
        o None si aun no ha transcurrido el intervalo minimo (el llamador
        debe reintentar despues). Nunca bloquea.
        """
        now = self._clock()
        if self._released:
            self._error = "AdaptiveCapture ya esta liberado"
            return None

        interval = self._min_interval()
        if (
            self._last_grab_time is not None
            and interval > 0
            and now - self._last_grab_time < interval
        ):
            return None

        self._last_grab_time = now

        cam = self._ensure_camera()
        if cam is None:
            return FrameInfo(
                frame=None,
                timestamp=self._monotonic_timestamp(now),
                backend=None,
                cadence=self._current_cadence_name(),
                is_burst=self._state == self._STATE_BURST,
                transition_detected=False,
                frame_index=self._frame_index,
                fallback_active=False,
            )

        frame = None
        backend = None
        fallback_active = False
        try:
            frame = cam.grab()
        except Exception as exc:
            self._error = "captura de frame fallo: %s" % exc
            frame = None
        if frame is None:
            self._error = self._error or "camara devolvio frame nulo"
            return FrameInfo(
                frame=None,
                timestamp=self._monotonic_timestamp(now),
                backend=None,
                cadence=self._current_cadence_name(),
                is_burst=self._state == self._STATE_BURST,
                transition_detected=False,
                frame_index=self._frame_index,
                fallback_active=False,
            )

        if hasattr(cam, "effective_backend"):
            backend = cam.effective_backend
        if hasattr(cam, "fallback_active"):
            fallback_active = bool(cam.fallback_active)

        transition_detected = False
        if self._last_frame is not None:
            diff = self._frame_diff(frame, self._last_frame)
            if diff > self.transition_threshold:
                transition_detected = True

        # Maquina de estados: estable / rafaga / inactivo.
        if self._state == self._STATE_IDLE:
            self._state = self._STATE_STABLE
            self._idle_since = now
        if transition_detected:
            self._state = self._STATE_BURST
            self._burst_until = now + self.burst_window_seconds
            self._idle_since = None
        elif self._state == self._STATE_BURST and (
            self._burst_until is not None and now >= self._burst_until
        ):
            self._state = self._STATE_STABLE
            self._idle_since = now
        elif self._state == self._STATE_STABLE:
            if self._idle_since is None:
                self._idle_since = now
            elif (
                self.idle_release_seconds > 0
                and now - self._idle_since >= self.idle_release_seconds
            ):
                self._stop_stream()
                return FrameInfo(
                    frame=frame,
                    timestamp=self._monotonic_timestamp(now),
                    backend=backend,
                    cadence=self._current_cadence_name(),
                    is_burst=False,
                    transition_detected=transition_detected,
                    frame_index=self._frame_index,
                    fallback_active=fallback_active,
                )

        self._last_frame = frame
        self._frame_index += 1
        info = FrameInfo(
            frame=frame,
            timestamp=self._monotonic_timestamp(now),
            backend=backend,
            cadence=self._current_cadence_name(),
            is_burst=self._state == self._STATE_BURST,
            transition_detected=transition_detected,
            frame_index=self._frame_index,
            fallback_active=fallback_active,
        )
        self._buffer.append(info)
        self._error = None
        return info

    def get_latest(self):
        """Devuelve el ultimo FrameInfo entregado, o None si no hay ninguno."""
        if not self._buffer:
            return None
        return self._buffer[-1]

    # ------------------------------------------------------------------
    # Estado y propiedades
    # ------------------------------------------------------------------

    @property
    def is_capturing(self):
        return self._capturing

    @property
    def is_released(self):
        return self._released

    @property
    def state(self):
        return self._state

    @property
    def cadence(self):
        return self._current_cadence_name()

    @property
    def available(self):
        cam = self._dxcam_capture if self._owns_camera else self._camera
        if cam is None:
            return False
        return bool(getattr(cam, "available", False))

    @property
    def error(self):
        return self._error

    @property
    def buffer_size(self):
        return len(self._buffer)

    @property
    def last_frame(self):
        if not self._buffer:
            return None
        return self._buffer[-1].frame

    @property
    def last_timestamp(self):
        return self._last_timestamp