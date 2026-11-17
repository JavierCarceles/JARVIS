# -*- coding: ascii -*-
"""
Prueba de integracion real en Windows (unidad 3.8.6.7.6): verificacion del
puntero antes de cada clic en `src.hands.input.mouse.click_element`.

Abre UNA sola instancia de Notepad (aplicacion inocua, controlada por la
prueba), la situa en el monitor no principal situado mas a la derecha segun
la enumeracion real (o en el unico monitor), la activa y verifica con la
implementacion de produccion:

* clic sobre el area cliente de Notepad pasando window_id, pid y la caja del
  area cliente: se verifica el puntero (posicion real, ventana y control bajo
  el puntero) y se hace clic -> True.
* clic con una caja esperada que no contiene el destino: aborta sin clic ->
  False.
* clic con el puntero sobre el escritorio (ventana bajo el puntero distinta a
  Notepad): aborta sin clic -> False.

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
    Rect,
    get_desktop_platform,
)
from src.hands.calibration.coordinate_spaces import (
    CoordinateSpace,
    SpaceBox,
    SpacePoint,
)

APP_NAME = "notepad.exe"
GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_click_verificacion_puntero.lock"
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


class TestClickVerificacionPunteroEntornoReal(unittest.TestCase):
    """Verifica el puntero antes de cada clic con recursos reales de Windows."""

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
            raise RuntimeError(
                "No se detecto una ventana propia de Notepad tras lanzarla"
            )

        # Monitor destino: el no principal situado mas a la derecha (real).
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

        # La ventana debe estar en primer plano para la verificacion del puntero.
        av = cls.adapter.activate_window(cls.hwnd)
        assert av.ok is True, "No se pudo activar Notepad: %s" % av.error
        deadline = time.time() + 5
        while time.time() < deadline:
            fg = cls.adapter.get_foreground_window()
            if fg.ok and fg.value is not None and int(fg.value.window_id) == cls.hwnd:
                break
            time.sleep(0.1)

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True, "No se pudo leer la ventana de Notepad: %s" % win.error
        assert str(win.value.display_id) == str(
            cls.monitor.display_id
        ), "Notepad no quedo en el monitor objetivo: %s vs %s" % (
            win.value.display_id, cls.monitor.display_id
        )

        atexit.register(cls._cerrar_notepad_propietario)

    def test_hace_clic_verificando_puntero_sobre_area_cliente(self):
        ventana = self.adapter.get_window(self.hwnd)
        assert ventana.ok is True
        client = ventana.value.client_bounds
        self.assertIsNotNone(client, "Notepad sin area cliente")
        self.assertTrue(client.is_valid(), "Area cliente invalida")

        # Destino: centro del area cliente (espacio de escritorio).
        target = SpacePoint(client.center[0], client.center[1], CoordinateSpace.DESKTOP_PIXELS)
        caja_esperada = SpaceBox(
            client.left, client.top, client.right, client.bottom, CoordinateSpace.DESKTOP_PIXELS
        )

        from src.hands.input.mouse import click_element

        resultado = click_element(
            x=target.x,
            y=target.y,
            window_id=int(ventana.value.window_id),
            pid=int(ventana.value.pid),
            expected_box=caja_esperada,
            pixels_per_unit=1.0,
            tolerance_ratio=0.15,
            wait_after=0.0,
        )
        self.assertTrue(resultado, "El clic verificado no se pudo realizar: %s" % resultado)

    def test_click_aborta_si_caja_esperada_no_contiene_el_destino(self):
        from src.hands.input.mouse import click_element

        ventana = self.adapter.get_window(self.hwnd)
        assert ventana.ok is True
        client = ventana.value.client_bounds
        self.assertIsNotNone(client)

        # Punto dentro de Notepad pero caja esperada lejos de ahi (otro monitor).
        destino_x = float(client.left) + 10.0
        destino_y = float(client.top) + 10.0
        caja_lejos = SpaceBox(
            90000.0,
            90000.0,
            91000.0,
            91000.0,
            CoordinateSpace.DESKTOP_PIXELS,
        )

        resultado = click_element(
            x=destino_x,
            y=destino_y,
            window_id=int(ventana.value.window_id),
            pid=int(ventana.value.pid),
            expected_box=caja_lejos,
            wait_after=0.0,
        )
        self.assertFalse(
            resultado,
            "Se esperaba aborto cuando el destino esta fuera de la caja del control",
        )

    def test_click_aborta_si_ventana_bajo_puntero_no_es_notepad(self):
        from src.hands.input.mouse import click_element

        ventana = self.adapter.get_window(self.hwnd)
        assert ventana.ok is True
        client = ventana.value.client_bounds
        self.assertIsNotNone(client)

        # Puntero sobre el escritorio (area del monitor principal fuera de Notepad).
        disp = self.adapter.enumerate_displays()
        assert disp.ok is True
        principal = next(
            (p for p in disp.value if p.is_primary), disp.value[0]
        )
        escritorio_x = float(principal.bounds.left) + 50.0
        escritorio_y = float(principal.bounds.top) + 50.0

        resultado = click_element(
            x=escritorio_x,
            y=escritorio_y,
            window_id=int(ventana.value.window_id),
            pid=int(ventana.value.pid),
            wait_after=0.0,
        )
        self.assertFalse(
            resultado,
            "Se esperaba aborto cuando la ventana bajo el puntero no es la objetivo",
        )

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
