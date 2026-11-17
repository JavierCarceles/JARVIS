# -*- coding: ascii -*-
"""
Prueba de integracion real en Windows (unidad 3.8.6.7.2): DPI por monitor y
por ventana.

Abre UNA sola instancia de Notepad (aplicacion inocua, controlada por la
prueba), la mueve al monitor no principal situado mas a la derecha segun la
enumeracion real (politica de pruebas de 3.8.6.6.4) y verifica que
`DesktopPlatformAdapter.get_window_dpi_info` devuelve:
* el DPI real de la ventana (`GetDpiForWindow`),
* el DPI del monitor donde esta (`GetDpiForMonitor`),
* la awareness de la ventana (`GetWindowDpiAwarenessContext`),
* la awareness del proceso (`GetProcessDpiAwareness`),
* la awareness de JARVIS (proceso actual),
sin tocar Visual Studio Code ni ventanas preexistentes del usuario.

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de Notepad que esta prueba abrio.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import time
import unittest

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform

APP_NAME = "notepad.exe"
GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "fixtures", "_gui_dpi_lock.lock")

# Awareness validas que devuelven las APIs de DPI de Windows.
AWARENESS_VALIDAS = (
    "unaware",
    "system_aware",
    "per_monitor_aware",
    "per_monitor_aware_v2",
    "unknown",
    "invalid",
)


def _gui_lock_activo():
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock():
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock():
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


def _notepad_handles(adapter):
    res = adapter.list_windows(app_identity=APP_NAME, visible_only=True)
    if not res.ok:
        return []
    return [int(w.window_id) for w in res.value]


class TestWindowDpiInfoRealWindows(unittest.TestCase):
    """Verifica DPI y awareness reales de una ventana sobre Windows."""

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        if _gui_lock_activo():
            raise unittest.SkipTest("Otra clase de tests GUI esta ejecutandose. Esperar a que termine.")
        _adquirir_gui_lock()
        cls.adapter = get_desktop_platform()
        cls.proc = None
        cls.hwnd = None
        cls.monitor_id = None
        try:
            cls._abrir_notepad_propietario()
        except Exception:
            try:
                cls._cerrar_notepad_propietario()
            except Exception:
                pass
            _liberar_gui_lock()
            raise

    @classmethod
    def _abrir_notepad_propietario(cls):
        """Lanza Notepad y se queda con la ventana que esta prueba creo."""
        antes = set(_notepad_handles(cls.adapter))
        cls.proc = subprocess.Popen([APP_NAME])
        deadline = time.time() + 10
        cls.hwnd = None
        while time.time() < deadline:
            despues = set(_notepad_handles(cls.adapter))
            nuevos = despues - antes
            if nuevos:
                cls.hwnd = sorted(nuevos)[0]
                break
            time.sleep(0.2)
        if cls.hwnd is None:
            raise RuntimeError("No se detecto una ventana propia de Notepad tras lanzarla")

        # Monitor destino: el no principal situado mas a la derecha (real).
        disp = cls.adapter.enumerate_displays()
        assert disp.ok is True, "No se pudieron enumerar monitores: %s" % disp.error
        pantallas = disp.value
        no_principales = [p for p in pantallas if not p.is_primary]
        objetivo = max(no_principales, key=lambda p: p.bounds.left) if no_principales else pantallas[0]
        cls.monitor_id = objetivo.display_id

        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor_id)
        assert mv.ok is True, "No se pudo mover Notepad al monitor de pruebas: %s" % mv.error

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True
        assert win.value.display_id == cls.monitor_id, "Notepad no quedo en el monitor objetivo"

        atexit.register(cls._cerrar_notepad_propietario)

    def test_dpi_por_ventana_y_monitor_en_windows_real(self):
        res = self.adapter.get_window_dpi_info(self.hwnd)
        self.assertTrue(res.ok, "get_window_dpi_info fallo: %s" % res.error)
        info = res.value
        self.assertEqual(info.window_id, self.hwnd)
        self.assertIsNotNone(info.dpi)
        self.assertGreater(int(info.dpi), 0, "El DPI de la ventana debe ser positivo")
        self.assertIsNotNone(info.scale_factor)
        self.assertGreater(float(info.scale_factor), 0.0, "El factor de escala debe ser positivo")
        self.assertIsNot(info.window_awareness, None, "Falta awareness de la ventana")
        self.assertIn(info.window_awareness, AWARENESS_VALIDAS)
        self.assertIsNot(info.process_awareness, None, "Falta awareness del proceso")
        self.assertIn(info.process_awareness, AWARENESS_VALIDAS)
        self.assertIsNot(info.jarvis_awareness, None, "Falta awareness de JARVIS")
        self.assertIn(info.jarvis_awareness, AWARENESS_VALIDAS)
        self.assertEqual(info.display_id, self.monitor_id)
        self.assertTrue(info.details.get("get_dpi_for_window_available") is True)
        self.assertIsNotNone(info.details.get("monitor_dpi"))
        self.assertGreater(int(info.details["monitor_dpi"]), 0, "El DPI del monitor debe ser positivo")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_notepad_propietario()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor_id = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_notepad_propietario(cls):
        if cls.hwnd is not None:
            try:
                cls.adapter.close_window(cls.hwnd)
                deadline = time.time() + 10
                while time.time() < deadline:
                    restante = [w for w in _notepad_handles(cls.adapter) if int(w) == cls.hwnd]
                    if not restante:
                        break
                    time.sleep(0.25)
            except Exception:
                pass
            cls.hwnd = None
        if cls.proc is not None and cls.proc.poll() is None:
            try:
                cls.proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
