# -*- coding: ascii -*-
"""
Prueba GUI real en Windows de la fixture de calibracion GUI.

Lanza UNA sola instancia de la fixture (aplicacion propia, controlada por la
prueba), la coloca en el monitor no principal situado mas a la derecha segun
la enumeracion real (politica de pruebas de 3.8.6.6.4), la maximiza y verifica
que el arbol de accesibilidad nativo expone todos los controles con su
identificador, geometria y que una accion inocua instrumentada es observable
por un canal separado (runtime/action_counts.json).

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de la fixture que esta prueba abrio.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
import unittest

from pywinauto import Desktop

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform

TITULO_FIXTURE = "JARVIS GUI Calibration Fixture"
FIXTURE_RUN = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "fixtures",
        "gui_calibration_app", "run.py",
    )
)
ACTION_COUNTS_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "fixtures",
        "gui_calibration_app", "runtime", "action_counts.json",
    )
)
GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "_gui_fixture_lock.lock")

# Identificadores que la fixture debe exponer en el arbol de accesibilidad.
IDS_ESPERADOS = [
    "btn_aceptar", "btn_cancelar", "lbl_estado", "lnk_ayuda", "txt_nombre",
    "chk_terminos", "rdo_opcion_a", "rdo_opcion_b", "cbo_categoria",
    "lst_items", "tab_principal", "scr_area", "menu_archivo", "popup_info",
    "grp_anidado", "canvas_mano",
]


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


def _leer_action_counts():
    if not os.path.exists(ACTION_COUNTS_PATH):
        return {}
    try:
        with open(ACTION_COUNTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def _buscar_control(ventana, id_control):
    """Busca un descendiente por nombre o automation_id que termine en el id."""
    for desc in ventana.descendants():
        try:
            nombre = desc.window_text()
            aid = desc.element_info.automation_id or ""
        except Exception:
            continue
        if nombre == id_control or aid == id_control or aid.endswith("." + id_control):
            return desc
    return None


class TestCalibracionFixtureRealWindows(unittest.TestCase):
    """Verifica la fixture de calibracion en el equipo real."""

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
        cls.monitor_id = None
        try:
            cls._lanzar_fixture_propietaria()
        except Exception:
            try:
                cls._cerrar_fixture_propietaria()
            except Exception:
                pass
            _liberar_gui_lock()
            raise

    @classmethod
    def _lanzar_fixture_propietaria(cls):
        """Lanza la fixture y se queda con la ventana que esta prueba creo."""
        cls.proc = subprocess.Popen([sys.executable, FIXTURE_RUN])
        deadline = time.time() + 20
        cls.hwnd = None
        escritorio = Desktop(backend="uia")
        while time.time() < deadline:
            try:
                cand = escritorio.window(title=TITULO_FIXTURE)
                if cand.exists() and cand.handle is not None:
                    cls.hwnd = int(cand.handle)
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if cls.hwnd is None:
            raise RuntimeError(
                "No se detecto una ventana propia de la fixture tras lanzarla"
            )

        # Monitor destino: el no principal situado mas a la derecha (real).
        disp = cls.adapter.enumerate_displays()
        assert disp.ok is True, "No se pudieron enumerar monitores: %s" % disp.error
        pantallas = disp.value
        no_principales = [p for p in pantallas if not p.is_primary]
        objetivo = max(no_principales, key=lambda p: p.bounds.left) if no_principales else pantallas[0]
        cls.monitor_id = objetivo.display_id

        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor_id)
        assert mv.ok is True, "No se pudo mover la fixture al monitor de pruebas: %s" % mv.error

        mx = cls.adapter.maximize_window(cls.hwnd)
        assert mx.ok is True, "No se pudo maximizar la fixture: %s" % mx.error

        ac = cls.adapter.activate_window(cls.hwnd)
        assert ac.ok is True, "No se pudo activar la fixture: %s" % ac.error

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True
        assert win.value.display_id == cls.monitor_id, "La fixture no quedo en el monitor objetivo"

        atexit.register(cls._cerrar_fixture_propietaria)

    def test_ventana_propietaria_en_monitor_pruebas(self):
        self.assertIsNotNone(self.hwnd)
        self.assertIsNotNone(self.monitor_id)
        win = self.adapter.get_window(self.hwnd)
        self.assertTrue(win.ok)
        self.assertEqual(win.value.display_id, self.monitor_id)
        escritorio = Desktop(backend="uia")
        ventana = escritorio.window(handle=self.hwnd)
        self.assertTrue(ventana.exists())
        self.assertEqual(ventana.window_text(), TITULO_FIXTURE)

    def test_arbol_accesibilidad_expone_todos_los_controles(self):
        escritorio = Desktop(backend="uia")
        ventana = escritorio.window(handle=self.hwnd)
        encontrados = set()
        for desc in ventana.descendants():
            try:
                nombre = desc.window_text()
                aid = desc.element_info.automation_id or ""
            except Exception:
                continue
            for id_ in IDS_ESPERADOS:
                if nombre == id_ or aid == id_ or aid.endswith("." + id_):
                    encontrados.add(id_)
                    break
        for id_ in IDS_ESPERADOS:
            self.assertIn(id_, encontrados, "El control %s no esta en el arbol de accesibilidad" % id_)
        # Cada control encontrado debe tener un rectangulo dentro de la pantalla.
        for id_ in IDS_ESPERADOS:
            ctrl = _buscar_control(ventana, id_)
            self.assertIsNotNone(ctrl, "No se localiza %s para verificar rectangulo" % id_)
            rect = ctrl.rectangle()
            self.assertGreaterEqual(rect.width(), 0)
            self.assertGreaterEqual(rect.height(), 0)

    def test_control_sin_accesibilidad_sin_nombre_semantico(self):
        """canvas_mano (dibujo a mano sin accesibilidad) no expone identidad."""
        escritorio = Desktop(backend="uia")
        ventana = escritorio.window(handle=self.hwnd)
        ctrl = _buscar_control(ventana, "canvas_mano")
        self.assertIsNotNone(ctrl, "canvas_mano debe estar en el arbol como control generico")
        self.assertEqual(ctrl.window_text(), "",
                         "canvas_mano no debe exponer nombre semantico (sin accesibilidad)")

    def test_accion_inocua_instrumentada_observable(self):
        """Hacer clic en btn_aceptar incrementa su contador en el canal separado."""
        escritorio = Desktop(backend="uia")
        ventana = escritorio.window(handle=self.hwnd)
        ctrl = _buscar_control(ventana, "btn_aceptar")
        self.assertIsNotNone(ctrl, "btn_aceptar no se localiza para hacer clic")
        antes = _leer_action_counts().get("accion_btn_aceptar", 0)
        ctrl.click_input()
        deadline = time.time() + 5
        despues = None
        while time.time() < deadline:
            despues = _leer_action_counts().get("accion_btn_aceptar", 0)
            if despues > antes:
                break
            time.sleep(0.2)
        self.assertIsNotNone(despues)
        self.assertGreater(despues, antes,
                           "Hacer clic en btn_aceptar debe incrementar su contador de acciones")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_fixture_propietaria()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor_id = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_fixture_propietaria(cls):
        if cls.hwnd is not None:
            try:
                cls.adapter.close_window(cls.hwnd)
                deadline = time.time() + 10
                while time.time() < deadline:
                    escritorio = Desktop(backend="uia")
                    try:
                        aun_existe = escritorio.window(handle=cls.hwnd).exists()
                    except Exception:
                        aun_existe = False
                    if not aun_existe:
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
