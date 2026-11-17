# -*- coding: ascii -*-
"""
Prueba de integracion real en Windows (unidad 3.8.6.7.4): transformaciones
entre espacios de coordenadas con captura real, ventana real y puntero real.

Abre UNA sola instancia de Notepad (aplicacion inocua, controlada por la
prueba), la situa en el monitor no principal situado mas a la derecha segun
la enumeracion real (o en el unico monitor) y verifica con la implementacion
de produccion de `src.hands.calibration.coordinate_spaces`:

* captura real de una region del monitor y conversion captura <-> monitor <-> escritorio (`capture_pixels_per_unit`, `monitor_pixel_ratio`),
* conversion escritorio <-> rectangulo ventana <-> area cliente <-> normalizado 0..1 (`visible_window_rect` con borde/sombra DWM, `CoordinateTransformer`),
* redondeo explicito al espacio de entrada (`to_input_point`),
* lectura real de la posicion del puntero (`DesktopPlatformAdapter.get_pointer_position`, espacio `DESKTOP_PIXELS`).

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de Notepad que esta prueba abrio. No envia teclado ni raton a ninguna
ventana y no toca Visual Studio Code.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import time
import unittest

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import (
    CaptureResult,
    DESKTOP_PIXELS,
    PLATFORM_WINDOWS,
    Rect,
    get_desktop_platform,
)
from src.hands.calibration.coordinate_spaces import (
    CoordinateSpace,
    CoordinateTransformer,
    SpaceBox,
    SpacePoint,
    TransformContext,
    capture_pixels_per_unit,
    monitor_pixel_ratio,
    visible_window_rect,
)

APP_NAME = "notepad.exe"
GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_transformaciones_coordenadas_lock.lock"
)

_TOLERANCE_PX = 2.0


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


class TestTransformacionesCoordenadasEntornoReal(unittest.TestCase):
    """Verifica las transformaciones de coordenadas con recursos reales de Windows."""

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

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True, "No se pudo leer la ventana de Notepad: %s" % win.error
        assert win.value.display_id == cls.monitor.display_id, "Notepad no quedo en el monitor objetivo"

        atexit.register(cls._cerrar_notepad_propietario)

    @classmethod
    def _contexto_transformacion(cls, capture=None):
        ventana = cls.adapter.get_window(cls.hwnd)
        assert ventana.ok is True
        return TransformContext(
            platform=PLATFORM_WINDOWS,
            display=cls.monitor,
            window=ventana.value,
            capture=capture,
        )

    def test_monitores_reales_tienen_geometria_valida(self):
        disp = self.adapter.enumerate_displays()
        self.assertTrue(disp.ok, "enumerate_displays fallo: %s" % disp.error)
        pantallas = disp.value
        self.assertGreaterEqual(len(pantallas), 1)
        for p in pantallas:
            self.assertIsNotNone(p.bounds)
            self.assertTrue(p.bounds.is_valid(), "Monitor %s sin bounds validos" % p.display_id)
            self.assertGreater(int(p.pixel_width), 0, "pixel_width debe ser positivo")
            self.assertGreater(int(p.pixel_height), 0, "pixel_height debe ser positivo")
        self.assertIsNotNone(self.monitor.bounds)
        self.assertTrue(self.monitor.bounds.is_valid())

    def test_ratio_pixeles_monitor_de_datos_reales(self):
        rx, ry = monitor_pixel_ratio(self.monitor, PLATFORM_WINDOWS)
        bounds = self.monitor.bounds
        esperado_x = float(self.monitor.pixel_width) / float(bounds.width)
        esperado_y = float(self.monitor.pixel_height) / float(bounds.height)
        self.assertAlmostEqual(rx, esperado_x, places=6, msg="pixeles de monitor por unidad de escritorio no coinciden")
        self.assertAlmostEqual(ry, esperado_y, places=6, msg="pixeles de monitor por unidad de escritorio no coinciden")
        self.assertGreater(rx, 0.0)
        self.assertGreater(ry, 0.0)

    def test_captura_region_real_y_transformacion_frame_escritorio_monitor(self):
        bounds = self.monitor.bounds
        # Region real dentro del monitor de pruebas (margen para no tocar bordes).
        ancho = min(300.0, bounds.width / 2.0)
        alto = min(200.0, bounds.height / 2.0)
        region = Rect(
            bounds.left + 50.0,
            bounds.top + 50.0,
            bounds.left + 50.0 + ancho,
            bounds.top + 50.0 + alto,
        )
        cap: CaptureResult = None
        res = self.adapter.capture_region(region)
        self.assertTrue(res.ok, "capture_region fallo: %s" % res.error)
        cap = res.value
        self.assertIsNotNone(cap)
        self.assertEqual(cap.coordinate_space, DESKTOP_PIXELS)
        self.assertAlmostEqual(float(cap.pixel_width), ancho, delta=2.0, msg="el frame capturado debe coincidir con la region solicitada")
        self.assertAlmostEqual(float(cap.pixel_height), alto, delta=2.0, msg="el frame capturado debe coincidir con la region solicitada")

        # La conversion de pixeles por unidad se verifica contra el frame real.
        ppu_x, ppu_y = capture_pixels_per_unit(cap)
        self.assertGreater(ppu_x, 0.0)
        self.assertGreater(ppu_y, 0.0)

        # Recorrido redondo frame <-> escritorio <-> monitor <-> escritorio <-> frame.
        transformer = CoordinateTransformer(self._contexto_transformacion(capture=cap))
        punto_frame = SpacePoint(ancho / 2.0, alto / 2.0, CoordinateSpace.FRAME_PIXELS)
        en_escritorio = transformer.transform_point(punto_frame, CoordinateSpace.DESKTOP_PIXELS)
        self.assertEqual(en_escritorio.space, CoordinateSpace.DESKTOP_PIXELS)
        de_vuelta_frame = transformer.transform_point(en_escritorio, CoordinateSpace.FRAME_PIXELS)
        self.assertAlmostEqual(de_vuelta_frame.x, punto_frame.x, delta=_TOLERANCE_PX)
        self.assertAlmostEqual(de_vuelta_frame.y, punto_frame.y, delta=_TOLERANCE_PX)

        en_monitor = transformer.transform_point(en_escritorio, CoordinateSpace.MONITOR_PIXELS)
        self.assertEqual(en_monitor.space, CoordinateSpace.MONITOR_PIXELS)
        de_vuelta_escritorio = transformer.transform_point(en_monitor, CoordinateSpace.DESKTOP_PIXELS)
        self.assertAlmostEqual(de_vuelta_escritorio.x, en_escritorio.x, delta=_TOLERANCE_PX)
        self.assertAlmostEqual(de_vuelta_escritorio.y, en_escritorio.y, delta=_TOLERANCE_PX)

    def test_ventana_real_visible_rect_y_transformaciones_escritorio_cliente(self):
        ctx = self._contexto_transformacion()
        ventana = ctx.window
        transformer = CoordinateTransformer(ctx)

        visible = visible_window_rect(ventana)
        self.assertIsNotNone(visible, "visible_window_rect no devolvio rectangulo para ventana real")
        self.assertTrue(visible.is_valid())

        # El rectangulo visible (frame, sin borde/sombra DWM) contiene al area cliente.
        client = ventana.client_bounds
        if client is not None and client.is_valid():
            self.assertGreaterEqual(visible.width, client.width, "frame visible debe cubrir el ancho de la zona cliente")
            self.assertGreaterEqual(visible.height, client.height, "frame visible debe cubrir el alto de la zona cliente")

        # Escritorio <-> rectangulo exterior de ventana <-> escritorio.
        punto_escritorio = SpacePoint(visible.center[0], visible.center[1], CoordinateSpace.DESKTOP_PIXELS)
        en_ventana = transformer.transform_point(punto_escritorio, CoordinateSpace.WINDOW_RECT)
        self.assertEqual(en_ventana.space, CoordinateSpace.WINDOW_RECT)
        de_vuelta = transformer.transform_point(en_ventana, CoordinateSpace.DESKTOP_PIXELS)
        self.assertAlmostEqual(de_vuelta.x, punto_escritorio.x, delta=_TOLERANCE_PX)
        self.assertAlmostEqual(de_vuelta.y, punto_escritorio.y, delta=_TOLERANCE_PX)

        # Escritorio <-> zona cliente <-> escritorio.
        # WINDOW_CLIENT es relativo al origen del area cliente (client_bounds), en unidades de escritorio.
        if client is not None and client.is_valid():
            punto_absoluto = SpacePoint(client.center[0], client.center[1], CoordinateSpace.DESKTOP_PIXELS)
            relativo_cliente = SpacePoint(
                punto_absoluto.x - client.left,
                punto_absoluto.y - client.top,
                CoordinateSpace.WINDOW_CLIENT,
            )
            en_escritorio_desde_cliente = transformer.transform_point(relativo_cliente, CoordinateSpace.DESKTOP_PIXELS)
            self.assertAlmostEqual(
                en_escritorio_desde_cliente.x, punto_absoluto.x, delta=_TOLERANCE_PX,
                msg="WINDOW_CLIENT <-> escritorio no es redondo",
            )
            self.assertAlmostEqual(
                en_escritorio_desde_cliente.y, punto_absoluto.y, delta=_TOLERANCE_PX,
                msg="WINDOW_CLIENT <-> escritorio no es redondo",
            )
            self.assertTrue(
                self.monitor.bounds.contains_point(en_escritorio_desde_cliente.x, en_escritorio_desde_cliente.y),
                "la zona cliente de Notepad debe caer dentro del monitor real",
            )
            de_vuelta_cliente = transformer.transform_point(en_escritorio_desde_cliente, CoordinateSpace.WINDOW_CLIENT)
            self.assertAlmostEqual(de_vuelta_cliente.x, relativo_cliente.x, delta=_TOLERANCE_PX)
            self.assertAlmostEqual(de_vuelta_cliente.y, relativo_cliente.y, delta=_TOLERANCE_PX)

            # Zona cliente <-> normalizado 0..1 <-> zona cliente.
            normalizado = transformer.transform_point(relativo_cliente, CoordinateSpace.CLIENT_NORMALIZED)
            self.assertEqual(normalizado.space, CoordinateSpace.CLIENT_NORMALIZED)
            self.assertGreaterEqual(normalizado.x, 0.0)
            self.assertLessEqual(normalizado.x, 1.0)
            self.assertGreaterEqual(normalizado.y, 0.0)
            self.assertLessEqual(normalizado.y, 1.0)
            desde_normalizado = transformer.transform_point(normalizado, CoordinateSpace.WINDOW_CLIENT)
            self.assertAlmostEqual(desde_normalizado.x, relativo_cliente.x, delta=_TOLERANCE_PX)
            self.assertAlmostEqual(desde_normalizado.y, relativo_cliente.y, delta=_TOLERANCE_PX)

    def test_redondeo_explicito_al_espacio_de_entrada(self):
        ctx = self._contexto_transformacion()
        transformer = CoordinateTransformer(ctx)
        punto_escritorio = SpacePoint(self.monitor.bounds.center[0] + 12.3, self.monitor.bounds.center[1] + 7.8, CoordinateSpace.DESKTOP_PIXELS)
        entrada = transformer.to_input_point(punto_escritorio)
        self.assertEqual(entrada.space, CoordinateSpace.DESKTOP_PIXELS)
        # En Windows el espacio de entrada son pixeles enteros: redondeo explicito, nunca multiplicacion a ciegas por escala.
        self.assertEqual(entrada.x, float(int(entrada.x)), "la coordenada X de entrada debe ser un entero de pixel")
        self.assertEqual(entrada.y, float(int(entrada.y)), "la coordenada Y de entrada debe ser un entero de pixel")

    def test_posicion_puntero_real_espacio_escritorio(self):
        res = self.adapter.get_pointer_position()
        self.assertTrue(res.ok, "get_pointer_position fallo: %s" % res.error)
        pos = res.value
        self.assertIsNotNone(pos)
        self.assertEqual(pos.coordinate_space, DESKTOP_PIXELS, "el puntero lee en el espacio de escritorio nativo")
        self.assertIsInstance(float(pos.x), float)
        self.assertIsInstance(float(pos.y), float)

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
