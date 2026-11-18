# -*- coding: ascii -*-
"""
Prueba de integracion real en Windows (unidad 3.8.6.9.2): recalculo de
coordenadas absolutas al mover una ventana a otro monitor con igual escala.

Abre UNA sola instancia de Notepad, la situa en el monitor no principal
situado mas a la derecha (enumeracion real) y verifica con
`recompute_absolute` de `src.hands.calibration.calibration_validity` que
las coordenadas absolutas se recalculan desde la geometria relativa del
area cliente sin recalibrar: el punto resultante cae dentro del area
cliente real de la ventana en el monitor de destino.

Requiere JARVIS_TEST_GUI_REAL=1 y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra
la ventana de Notepad que esta prueba abrio. No envia teclado ni raton a
ninguna ventana y no toca Visual Studio Code.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import time
import unittest

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    Rect,
    get_desktop_platform,
)
from src.hands.calibration.calibration_profile_storage import (
    CalibratedControlRecord,
    CalibrationProfile,
    CalibrationState,
)
from src.hands.calibration.calibration_validity import recompute_absolute

APP_NAME = "notepad.exe"
GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_recalc_absoluto_monitor_lock.lock"
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


class TestRecalculoAbsolutoMonitorCambioEntornoReal(unittest.TestCase):
    """Verifica el recalculo de absolutas con recursos reales de Windows."""

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
        cls.monitor = None
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

        disp = cls.adapter.enumerate_displays()
        assert disp.ok is True, "No se pudieron enumerar monitores: %s" % disp.error
        pantallas = disp.value
        assert len(pantallas) >= 1, "Se espera al menos un monitor real"
        no_principales = [p for p in pantallas if not p.is_primary]
        if no_principales:
            cls.monitor = max(no_principales, key=lambda p: p.bounds.left)
        else:
            cls.monitor = pantallas[0]

        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor.display_id)
        assert mv.ok is True, "No se pudo mover Notepad al monitor de pruebas: %s" % mv.error

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True, "No se pudo leer la ventana de Notepad: %s" % win.error
        assert win.value.display_id == cls.monitor.display_id, "Notepad no quedo en el monitor objetivo"

        atexit.register(cls._cerrar_notepad_propietario)

    def test_recompute_absoluto_ventana_en_monitor_secundario(self):
        """El punto absoluto se recalcula desde la geometria relativa en el monitor destino."""
        ventana = self.adapter.get_window(self.hwnd)
        self.assertTrue(ventana.ok, "get_window fallo: %s" % ventana.error)
        win = ventana.value
        client = win.client_bounds
        self.assertIsNotNone(client, "la ventana real no expone area cliente")
        self.assertTrue(client.is_valid(), "area cliente invalida")

        control = CalibratedControlRecord(
            control_id="ctrl_centro",
            app_id="app_bloc_de_notas",
            name="Centro",
            control_type="button",
            semantic_state=CalibrationState.VALIDADO,
            geometric_state=CalibrationState.VALIDADO,
            action_state=CalibrationState.VALIDADO,
            client_box_normalized=(0.25, 0.25, 0.75, 0.75),
            safe_point_normalized=(0.50, 0.50),
            interaction_method="pointer",
            provenance=["uia"],
            detector_versions={"qwen3-vl": "8b"},
            calibrated_at="2026-01-15T10:30:00+00:00",
        )
        perfil = CalibrationProfile(
            profile_id="perfil-prueba",
            machine_id="maquina-prueba-1",
            app_id="app_bloc_de_notas",
            platform="Windows",
            topology_fingerprint="topo",
            window_fingerprint="huella",
            display_id=self.monitor.display_id,
            scale_factor=1.25,
            dpi=120,
            display_pixel_size=(int(self.monitor.pixel_width), int(self.monitor.pixel_height)),
            orientation=self.monitor.orientation,
            window_state="maximized",
            client_size=(int(round(client.width)), int(round(client.height))),
            status=CalibrationState.VALIDADO,
            controls=[control],
        )

        puntos = recompute_absolute(perfil, win)
        self.assertIn("ctrl_centro", puntos)
        px, py = puntos["ctrl_centro"]
        # El punto recalculado debe caer dentro del area cliente real
        self.assertGreaterEqual(px, client.left, "el punto X queda fuera del area cliente")
        self.assertLess(px, client.right, "el punto X queda fuera del area cliente")
        self.assertGreaterEqual(py, client.top, "el punto Y queda fuera del area cliente")
        self.assertLess(py, client.bottom, "el punto Y queda fuera del area cliente")
        # Y dentro del monitor de destino (segundo monitor, a la derecha)
        self.assertGreaterEqual(px, self.monitor.bounds.left, "el punto queda fuera del monitor destino")
        self.assertLess(px, self.monitor.bounds.right, "el punto queda fuera del monitor destino")
        self.assertGreaterEqual(py, self.monitor.bounds.top, "el punto queda fuera del monitor destino")
        self.assertLess(py, self.monitor.bounds.bottom, "el punto queda fuera del monitor destino")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_notepad_propietario()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_notepad_propietario(cls):
        if cls.hwnd is not None:
            try:
                res = cls.adapter.close_window(cls.hwnd)
                if not res.ok:
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
