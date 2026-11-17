# -*- coding: ascii -*-
"""
Prueba de integracion real en Windows (unidad 3.8.6.7.7): mide el error de
transformacion de coordenadas hasta el espacio de entrada del raton, en
pixeles y relativo al tamano del control, para cada monitor y escala reales
del equipo.

Abre UNA sola instancia de Notepad (aplicacion inocua, controlada por la
prueba), la mueve a cada monitor real (el no principal situado mas a la
derecha como monitor de pruebas por defecto; con un solo monitor, ese), y
verifica con la implementacion de produccion:

* para cada monitor: situa Notepad en ese monitor, toma el centro del area
  cliente como punto destino, lo transforma a espacio de entrada
  (``to_input_point``), mueve el puntero alla, lee su posicion real y mide
  ``error_px`` y el error relativo al lado menor del area cliente.

Usa `PointerVerifier` y `CoordinateTransformer` de
`src.hands.calibration.coordinate_spaces` sobre el adaptador de escritorio
real. `PointerVerifier` comprueba la ventana y el elemento bajo el puntero
antes de considerar el movimiento verificado. Registra los errores medidos
por monitor (identificador, escala, resolucion fisica) y los compara contra
tolerancias reales.

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de Notepad que esta prueba abrio. No envia teclado ni raton a VS Code
ni a ventanas ajenas a la prueba.
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
    PLATFORM_WINDOWS,
    get_desktop_platform,
)
from src.hands.calibration.coordinate_spaces import (
    CoordinateSpace,
    PointerVerifier,
    SpaceBox,
    SpacePoint,
    TransformContext,
    CoordinateTransformer,
)

APP_NAME = "notepad.exe"
GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_mouse_coordinate_transform.lock"
)

TOLERANCE_ERROR_PX = 5.0
TOLERANCE_ERROR_RATIO = 0.10


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


class TestMouseCoordinateTransformEntornoReal(unittest.TestCase):
    """Mide el error real del puntero tras transformar coordenadas, por monitor y escala."""

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest(
                "Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real"
            )
        if _gui_lock_activo():
            raise unittest.SkipTest(
                "Otra clase de tests GUI esta ejecutandose. Esperar a que termine."
            )
        _adquirir_gui_lock()
        cls.adapter = get_desktop_platform()
        cls.proc = None
        cls.hwnd = None
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
        cls._esperar_ventana_en_monitor(cls.hwnd, cls.monitor.display_id)

        av = cls.adapter.activate_window(cls.hwnd)
        assert av.ok is True, "No se pudo activar Notepad: %s" % av.error
        cls._esperar_ventana_primer_plano(cls.hwnd)

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True, "No se pudo leer la ventana de Notepad: %s" % win.error
        assert str(win.value.display_id) == str(
            cls.monitor.display_id
        ), "Notepad no quedo en el monitor objetivo"

        atexit.register(cls._cerrar_notepad_propietario)

    @classmethod
    def _esperar_ventana_en_monitor(cls, hwnd, display_id, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            win = cls.adapter.get_window(hwnd)
            if win.ok and win.value is not None and str(win.value.display_id) == str(display_id):
                return
            time.sleep(0.1)
        raise AssertionError("Notepad no se movio al monitor %s" % display_id)

    @classmethod
    def _esperar_ventana_primer_plano(cls, hwnd, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            fg = cls.adapter.get_foreground_window()
            if fg.ok and fg.value is not None and int(fg.value.window_id) == int(hwnd):
                return
            time.sleep(0.1)
        raise AssertionError("Notepad no quedo en primer plano")

    def test_error_puntero_por_monitor_y_escala(self):
        disp = self.adapter.enumerate_displays()
        assert disp.ok is True, "enumerate_displays fallo: %s" % disp.error
        pantallas = disp.value
        assert len(pantallas) >= 1, "Se espera al menos un monitor real"

        mediciones = []
        for monitor in pantallas:
            mv = self.adapter.move_window_to_display(self.hwnd, monitor.display_id)
            assert mv.ok is True, "No se pudo mover Notepad al monitor %s: %s" % (
                monitor.display_id, mv.error,
            )
            self._esperar_ventana_en_monitor(self.hwnd, monitor.display_id)
            av = self.adapter.activate_window(self.hwnd)
            assert av.ok is True, "No se pudo activar Notepad en %s" % monitor.display_id
            self._esperar_ventana_primer_plano(self.hwnd)

            ventana = self.adapter.get_window(self.hwnd)
            assert ventana.ok is True, "No se pudo leer Notepad en %s" % monitor.display_id
            client = ventana.value.client_bounds
            self.assertIsNotNone(client, "Notepad sin area cliente en %s" % monitor.display_id)
            self.assertTrue(client.is_valid(), "Area cliente invalida en %s" % monitor.display_id)

            # Punto destino: centro del area cliente, en espacio de escritorio.
            target = SpacePoint(client.center[0], client.center[1], CoordinateSpace.DESKTOP_PIXELS)

            ctx = TransformContext(
                platform=PLATFORM_WINDOWS,
                display=monitor,
                window=ventana.value,
            )
            transformer = CoordinateTransformer(ctx)
            en_ventana = transformer.transform_point(target, CoordinateSpace.WINDOW_CLIENT)
            de_vuelta = transformer.transform_point(en_ventana, CoordinateSpace.DESKTOP_PIXELS)
            self.assertAlmostEqual(de_vuelta.x, target.x, delta=1.0, msg="WINDOW_CLIENT <-> escritorio no redondo en %s" % monitor.display_id)
            self.assertAlmostEqual(de_vuelta.y, target.y, delta=1.0, msg="WINDOW_CLIENT <-> escritorio no redondo en %s" % monitor.display_id)

            # Error de posicionamiento real del puntero, en pixeles y relativo al control.
            ppu_x = float(monitor.pixel_width) / float(monitor.bounds.width)
            ppu_y = float(monitor.pixel_height) / float(monitor.bounds.height)
            verifier = PointerVerifier(
                adapter=self.adapter,
                tolerance_px=TOLERANCE_ERROR_PX,
                tolerance_ratio=TOLERANCE_ERROR_RATIO,
            )
            caja = SpaceBox(
                client.left, client.top, client.right, client.bottom, CoordinateSpace.DESKTOP_PIXELS
            )
            verification = verifier.move_and_verify(
                target,
                expected_window_id=int(ventana.value.window_id),
                expected_pid=int(ventana.value.pid),
                expected_box=caja,
                pixels_per_unit=ppu_x,
            )
            mediciones.append(
                {
                    "monitor": monitor.display_id,
                    "escala": monitor.scale_factor,
                    "pixel_width": monitor.pixel_width,
                    "pixel_height": monitor.pixel_height,
                    "bounds": monitor.bounds.to_dict(),
                    "error_px": verification.error_px,
                    "error_ratio": verification.error_ratio,
                    "ok": verification.ok,
                    "reason": verification.reason,
                }
            )
            self.assertTrue(
                verification.ok,
                "Puntero no verificado en %s: %s" % (monitor.display_id, verification.reason),
            )
            self.assertIsNotNone(verification.error_px, "error_px no medido en %s" % monitor.display_id)
            self.assertLessEqual(
                verification.error_px,
                TOLERANCE_ERROR_PX,
                "error_px demasiado alto en %s: %s px" % (monitor.display_id, verification.error_px),
            )
            if verification.error_ratio is not None:
                self.assertLessEqual(
                    verification.error_ratio,
                    TOLERANCE_ERROR_RATIO,
                    "error relativo demasiado alto en %s: %s" % (monitor.display_id, verification.error_ratio),
                )

        print("\nMedicion de error del puntero por monitor y escala (unidad 3.8.6.7.7):")
        for m in mediciones:
            print(
                "  monitor=%s escala=%s pixeles=%dx%d error_px=%s error_ratio=%s ok=%s"
                % (
                    m["monitor"],
                    m["escala"],
                    m["pixel_width"],
                    m["pixel_height"],
                    m["error_px"],
                    m["error_ratio"],
                    m["ok"],
                )
            )
        self.assertGreaterEqual(len(mediciones), 1, "No se pudo medir en ningun monitor real")

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
