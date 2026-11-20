# -*- coding: ascii -*-
"""
Prueba GUI real en Windows de la exploracion profunda y segura de la UI.

Lanza UNA sola instancia de la fixture de calibracion (aplicacion propia
controlada por esta prueba), la coloca en el monitor no principal situado
mas a la derecha segun la enumeracion real (politica de pruebas de 3.8.6.6.4),
la maximiza y ejecuta DeepUIExplorer.explore() sobre ella.

Comprueba:
- el mapa de estados UI se construye (estados, raiz y transiciones),
- las acciones prohibidas no se ejecutan (el boton "Borrar" nunca se pulsa y
  ninguna accion de escritura/efecto se realiza),
- la vuelta al estado anterior se verifica (transiciones con retorno verificado),
- los limites de presupuesto se respetan.

Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de la fixture que esta prueba abrio.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
import unittest

from pywinauto import Desktop

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.calibration.ui_exploration import (
    ACTION_EXPAND,
    ACTION_OPEN_DIALOG,
    ACTION_OPEN_MENU,
    ACTION_SELECT_TAB,
    DeepUIExplorer,
    ExplorationBudget,
    element_reference,
)

TITULO_FIXTURE = "JARVIS GUI Calibration Fixture"
FIXTURE_RUN = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "fixtures",
        "gui_calibration_app", "run.py",
    )
)
GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "_gui_deep_exploration.lock")
ID_BORRAR = "btn_borrar"
LABEL_BORRAR = "Borrar"

# Acciones de exploracion admitidas (nunca acciones de escritura o con efecto).
ACCIONES_EXPLORACION = frozenset(
    {ACTION_EXPAND, ACTION_SELECT_TAB, ACTION_OPEN_MENU, ACTION_OPEN_DIALOG}
)

# Acciones que nunca deben ejecutarse durante la exploracion profunda.
ACCIONES_NUNCA = frozenset({"set_value", "toggle", "type_text", "scroll", "invoke_leaf"})


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


def _buscar_nodo_borrar(adapter, window_id, pid):
    """Devuelve la referencia logica del boton 'Borrar' en el arbol de accesibilidad."""
    resultado = adapter.get_accessibility_tree(window_id, pid=pid)
    if not resultado.ok or resultado.value is None:
        return None
    arbol = resultado.value
    for nodo in arbol.nodes:
        if (nodo.name or "") == LABEL_BORRAR or (nodo.identifier or "") == ID_BORRAR:
            return element_reference(nodo, arbol)
    return None


class TestExploracionProfundaUIRealWindows(unittest.TestCase):
    """Verifica la exploracion profunda y segura sobre la fixture real."""

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
        cls.pid = None
        cls.monitor_id = None
        cls.ref_borrar = None
        cls.resultado = None
        cls.explorador = None
        try:
            cls._lanzar_fixture_propietaria()
            cls._ejecutar_exploracion()
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
        deadline = time.time() + 25
        cls.hwnd = None
        escritorio = Desktop(backend="uia")
        while time.time() < deadline:
            try:
                cand = escritorio.window(title=TITULO_FIXTURE)
                if cand.exists() and cand.handle is not None:
                    cls.hwnd = int(cand.handle)
                    cls.pid = int(cand.process_id())
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
        objetivo = (
            max(no_principales, key=lambda p: p.bounds.left)
            if no_principales
            else pantallas[0]
        )
        cls.monitor_id = objetivo.display_id

        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor_id)
        assert mv.ok is True, "No se pudo mover la fixture al monitor de pruebas: %s" % mv.error

        mx = cls.adapter.maximize_window(cls.hwnd)
        assert mx.ok is True, "No se pudo maximizar la fixture: %s" % mx.error

        ac = cls.adapter.activate_window(cls.hwnd)
        assert ac.ok is True, "No se pudo activar la fixture: %s" % ac.error

        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True
        assert (
            win.value.display_id == cls.monitor_id
        ), "La fixture no quedo en el monitor objetivo"

        cls.ref_borrar = _buscar_nodo_borrar(cls.adapter, cls.hwnd, cls.pid)

        atexit.register(cls._cerrar_fixture_propietaria)

    @classmethod
    def _ejecutar_exploracion(cls):
        """Ejecuta una exploracion profunda acotada sobre la ventana de la fixture."""
        presupuesto = ExplorationBudget(
            max_depth=3,
            max_states=40,
            max_actions=60,
            max_seconds=60,
        )
        cls.explorador = DeepUIExplorer(
            adapter=cls.adapter,
            policy=None,
            budget=presupuesto,
            app_id="fixture_calibracion",
        )
        cls.resultado = cls.explorador.explore(cls.hwnd, cls.pid, mode="full")

    def test_exploracion_construye_mapa_estados(self):
        """DeepUIExplorer construye un mapa de estados con raiz y transiciones."""
        resultado = self.resultado
        self.assertIsNotNone(resultado, "la exploracion no se ejecuto")
        self.assertFalse(
            resultado.aborted, "exploracion abortada: %s" % resultado.abort_reason
        )
        self.assertGreaterEqual(
            len(resultado.state_map.states), 1, "debe haber al menos el estado raiz"
        )
        self.assertIsNotNone(
            resultado.state_map.root_state_id, "el mapa debe definir estado raiz"
        )
        self.assertGreaterEqual(resultado.actions_performed, 0)

    def test_accion_borrar_no_ejecutada(self):
        """El boton prohibido 'Borrar' nunca se pulsa durante la exploracion."""
        resultado = self.resultado
        explorador = self.explorador
        self.assertIsNotNone(resultado, "la exploracion no se ejecuto")
        self.assertFalse(
            resultado.aborted, "exploracion abortada: %s" % resultado.abort_reason
        )
        # Ninguna accion ejecutada puede ser una accion de escritura o con efecto
        # (las acciones de retorno como collapse/escape son parte del mecanismo
        # de vuelta al estado anterior y no estan prohibidas).
        for accion in explorador.performed_actions:
            self.assertNotIn(
                accion["action"],
                ACCIONES_NUNCA,
                "se ejecuto una accion prohibida durante la exploracion: %s" % accion,
            )
        # Si se pudo localizar el boton Borrar, nunca fue el objeto de una accion ejecutada.
        if self.ref_borrar is not None:
            ejecutados_sobre_borrar = [
                accion
                for accion in explorador.performed_actions
                if accion.get("element_ref") == self.ref_borrar
            ]
            self.assertEqual(
                ejecutados_sobre_borrar,
                [],
                "el boton prohibido 'Borrar' no debe ser objetivo de ninguna accion ejecutada",
            )
        # Las acciones omitidas por la politica de seguridad nunca aparecen como ejecutadas.
        omitidos_refs = [item.get("element_ref", {}) for item in resultado.skipped_forbidden]
        ejecutados_refs = [a.get("element_ref", {}) for a in explorador.performed_actions]
        for ref_omitido in omitidos_refs:
            self.assertNotIn(
                ref_omitido,
                ejecutados_refs,
                "una accion omitida por la politica aparecio como ejecutada",
            )

    def test_vuelta_a_estados_verificada(self):
        """La exploracion verifica la vuelta al estado anterior tras cada accion."""
        resultado = self.resultado
        explorador = self.explorador
        self.assertIsNotNone(resultado, "la exploracion no se ejecuto")
        self.assertFalse(
            resultado.aborted, "exploracion abortada: %s" % resultado.abort_reason
        )
        self.assertGreaterEqual(
            explorador.performed_actions.__len__(),
            1,
            "la exploracion debe haber ejecutado al menos una accion segura",
        )
        transiciones_con_retorno = [
            t for t in resultado.state_map.transitions if t.verified_return
        ]
        self.assertGreaterEqual(
            len(transiciones_con_retorno),
            1,
            "debe haber al menos una transicion con vuelta al estado anterior verificada",
        )
        for transicion in resultado.state_map.transitions:
            self.assertTrue(
                transicion.verified_return,
                "toda transicion registrada debe tener la vuelta verificada: %s"
                % transicion.action,
            )

    def test_limites_presupuesto_respetados(self):
        """La exploracion no agota el presupuesto de forma destructiva."""
        resultado = self.resultado
        self.assertIsNotNone(resultado, "la exploracion no se ejecuto")
        self.assertFalse(
            resultado.aborted, "exploracion abortada: %s" % resultado.abort_reason
        )
        self.assertLessEqual(
            resultado.actions_performed, 60, "presupuesto de acciones excedido"
        )
        self.assertLessEqual(
            len(resultado.state_map.states), 40, "presupuesto de estados excedido"
        )
        if resultado.budget_exhausted or resultado.checkpoint is not None:
            self.assertIsNotNone(
                resultado.checkpoint,
                "se esperaba punto de control para reanudar la exploracion",
            )

    def test_politica_rechaza_etiqueta_borrar(self):
        """La politica de seguridad rechaza como prohibido un nodo etiquetado 'Borrar'."""
        from src.hands.calibration.ui_exploration import ExplorationSafetyPolicy

        politica = ExplorationSafetyPolicy()
        nodo = type("Nodo", (), {})()
        nodo.name = "Borrar"
        nodo.identifier = "btn_borrar"
        nodo.enabled = True
        nodo.visible = True
        nodo.offscreen = False
        nodo.actions = ["expand", "show_menu"]
        nodo.native_role = "SplitButton"
        nodo.parent_id = None
        prohibido, motivo = politica.is_forbidden_label(nodo)
        self.assertTrue(prohibido, "el nodo 'Borrar' debe ser una etiqueta prohibida")
        self.assertIn("borrar", motivo.lower())
        permitido, motivo2 = politica.is_allowed(nodo, ACTION_OPEN_MENU)
        self.assertFalse(
            permitido, "la politica no debe permitir abrir el menu 'Borrar'"
        )

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_fixture_propietaria()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.pid = None
            cls.monitor_id = None
            cls.ref_borrar = None
            cls.resultado = None
            cls.explorador = None
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
