# -*- coding: utf-8 -*-
"""Test GUI real de captura adaptativa (unidad 3.8.6.3.3.13.3).

Abre UNA sola ventana de Notepad en el monitor secundario derecho, la oculta y
restaura para forzar transiciones reales, y comprueba que la captura adaptativa
entra en modo rafaga. Cierra solo la ventana que abrio.

No se skipea: ejecutar con JARVIS_TEST_GUI_REAL=1. Sin esa variable, setUpClass
lanza RuntimeError explicito (no es un skip).

Esto es una prueba de entorno real aparte de test_dxcam_capture_core.py para
que la suite de unidad (sin variable GUI) no dependa de abrir ventanas.
"""

import os
import subprocess
import time
import ctypes
import unittest

import numpy as np  # noqa: F401  (reserva para posibles aserciones de frame)

from src.eyes.capture.screen_capture import (
    AdaptiveCapture,
    DXcamCapture,
)
from src.desktop.screen_manager import get_screen_manager

GUI_LOCK_FILE_ADAPTIVE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fixtures", "_gui_lock_adaptive.lock"
)
APP_NOTEPAD = "notepad.exe"


def _gui_lock_activo_adaptive():
    """Devuelve True si hay una clase de tests GUI ejecutandose actualmente."""
    if not os.path.exists(GUI_LOCK_FILE_ADAPTIVE):
        return False
    try:
        with open(GUI_LOCK_FILE_ADAPTIVE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock_adaptive():
    """Crea el archivo de lock con el PID actual."""
    os.makedirs(os.path.dirname(GUI_LOCK_FILE_ADAPTIVE), exist_ok=True)
    with open(GUI_LOCK_FILE_ADAPTIVE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock_adaptive():
    """Elimina el archivo de lock si pertenece al PID actual."""
    try:
        if os.path.exists(GUI_LOCK_FILE_ADAPTIVE):
            with open(GUI_LOCK_FILE_ADAPTIVE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE_ADAPTIVE)
    except (ValueError, OSError):
        pass


def _enumerar_ventanas_notepad(user32):
    """Enumera ventanas de Notepad (titulo contiene 'notepad' o 'bloc de notas')."""
    found = []

    def callback(hwnd, _lparam):
        try:
            length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
            titulo = buf.value
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(
                ctypes.c_void_p(hwnd), ctypes.byref(pid)
            )
            pid_val = int(pid.value)
            es_notepad = (
                "notepad" in titulo.lower()
                or "bloc de notas" in titulo.lower()
            )
            if es_notepad:
                found.append((int(hwnd), pid_val, titulo))
        except Exception:
            pass
        return True

    CBFUNC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
    user32.EnumWindows(CBFUNC(callback), 0)
    return found


class TestAdaptiveCaptureGuiReal(unittest.TestCase):
    """Verificacion real de transicion y rafaga con Notepad en el monitor secundario.

    Abre UNA sola ventana de Notepad (propia), la oculta/restaura para forzar
    transiciones reales en la captura y comprueba que la captura adaptativa
    entra en modo rafaga. Cierra solo la ventana que abrio.
    """

    @classmethod
    def setUpClass(cls):
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise RuntimeError(
                "Test GUI real de AdaptiveCapture requiere JARVIS_TEST_GUI_REAL=1 "
                "(abre una unica ventana de Notepad en el monitor secundario derecho). "
                "No se skipea: ejecutar con JARVIS_TEST_GUI_REAL=1."
            )
        if _gui_lock_activo_adaptive():
            raise RuntimeError(
                "Otra clase de tests GUI esta ejecutandose. Esperar a que termine."
            )
        _adquirir_gui_lock_adaptive()
        cls._owns_notepad = False
        cls.hwnd = None
        cls.pid = None
        cls._notepad_hwnds_before = set()
        user32 = ctypes.windll.user32
        for hwnd, pid, _titulo in _enumerar_ventanas_notepad(user32):
            cls._notepad_hwnds_before.add(hwnd)
        try:
            subprocess.Popen([APP_NOTEPAD])
        except Exception:
            pass
        # Esperar a que aparezca una ventana de Notepad nueva (de esta prueba).
        for _ in range(50):
            time.sleep(0.2)
            for hwnd, pid, _titulo in _enumerar_ventanas_notepad(user32):
                if hwnd not in cls._notepad_hwnds_before:
                    cls.hwnd = hwnd
                    cls.pid = pid
                    cls._owns_notepad = True
                    break
            if cls.hwnd is not None:
                break
        if not cls._owns_notepad:
            _liberar_gui_lock_adaptive()
            raise RuntimeError(
                "No se pudo crear una ventana de Notepad propia para el test GUI "
                "(Notepad ya estaba abierto en el equipo)."
            )
        # Colocar y maximizar en el monitor secundario (no principal).
        sm = get_screen_manager()
        secundario = None
        for m in sm.monitors:
            if not m.is_primary:
                secundario = m
                break
        if secundario is None:
            secundario = sm.get_primary_monitor()
        try:
            user32.ShowWindow(cls.hwnd, 3)  # SW_MAXIMIZE
        except Exception:
            pass
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls._owns_notepad and cls.hwnd is not None:
            try:
                ctypes.windll.user32.PostMessageW(cls.hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
            cls.hwnd = None
            cls.pid = None
        _liberar_gui_lock_adaptive()

    def test_transicion_notepad_detecta_rafaga(self):
        sm = get_screen_manager()
        secundario = None
        for m in sm.monitors:
            if not m.is_primary:
                secundario = m
                break
        if secundario is None:
            secundario = sm.get_primary_monitor()
        # Identificar la salida dxcam que mapea al monitor secundario.
        output_idx = None
        for idx in range(4):
            probe = DXcamCapture(output_idx=idx, backend="dxgi")
            try:
                mon = probe.match_monitor(sm)
            except Exception:
                mon = None
            finally:
                probe.release()
            if mon is not None and not mon.is_primary:
                output_idx = idx
                break
        if output_idx is None:
            self.fail(
                "No se pudo mapear el monitor secundario a una salida dxcam"
            )
        cap = AdaptiveCapture(
            output_idx=output_idx,
            backend="dxgi",
            low_cadence_fps=5.0,
            burst_cadence_fps=20.0,
            burst_window_seconds=2.0,
            transition_threshold=0.05,
            max_buffer_frames=4,
            idle_release_seconds=5.0,
        )
        assert cap.start() is True
        try:
            # Entrega base con Notepad visible en el secundario.
            r0 = None
            while r0 is None:
                r0 = cap.grab_adaptive()
                time.sleep(0.05)
            self.assertIsNotNone(r0)
            self.assertIsNotNone(r0.frame)
            # Ocultar Notepad: la ventana desaparece -> transicion real.
            user32 = ctypes.windll.user32
            user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
            time.sleep(0.5)
            r1 = None
            while r1 is None:
                r1 = cap.grab_adaptive()
                time.sleep(0.05)
            self.assertIsNotNone(r1)
            self.assertTrue(
                r1.transition_detected,
                "Se esperaba una transicion al ocultar Notepad",
            )
            self.assertEqual(r1.cadence, "burst")
            self.assertTrue(r1.is_burst)
            # Restaurar Notepad: la ventana reaparece -> otra transicion real.
            user32.ShowWindow(self.hwnd, 3)  # SW_MAXIMIZE
            time.sleep(0.5)
            r2 = None
            while r2 is None:
                r2 = cap.grab_adaptive()
                time.sleep(0.05)
            self.assertIsNotNone(r2)
            self.assertTrue(
                r2.transition_detected,
                "Se esperaba una transicion al restaurar Notepad",
            )
        finally:
            cap.close()
