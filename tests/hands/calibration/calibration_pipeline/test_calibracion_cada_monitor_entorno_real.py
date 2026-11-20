# -*- coding: ascii -*-
"""
Prueba GUI real en Windows: misma calibracion en cada monitor del equipo.

Abre UNA sola ventana propia del Bloc de notas (instancia lanzada por la
prueba, nunca una ventana del usuario), la deja maximizada en el monitor de
pruebas (no principal mas a la derecha por geometria real) y, para cada monitor
de la topologia real (no solo el de pruebas), la calibra por el pipeline de
produccion con ``monitor_reference="display:<id>"`` reutilizando esa misma
ventana. El pipeline mueve la ventana al monitor pedido, la maximiza, calibra,
persiste el perfil y al terminar la devuelve al monitor de pruebas y la deja
maximizada (restauracion del estado original de una ventana reutilizada): el
uso de un monitor distinto al de pruebas dura solo lo que dura su calibracion
y solo afecta a la ventana de prueba.

Para cada monitor comprueba:
- exito sin etapa fallida, ventana reutilizada = la ventana de la prueba;
- el informe y el perfil persistido en SQLite corresponden a ESE monitor
  (``display_id``, escala y DPI del monitor real);
- la ventana vuelve al monitor de pruebas al terminar;
- recalculo entre monitores: con la ventana de nuevo en el monitor de pruebas,
  ``CalibrationValidityService.load_valid_profile`` decide segun el contrato
  documentado en ``calibration_validity``: si escala, DPI, tamano del area
  cliente y estado de ventana coinciden, el perfil es utilizable y sus
  absolutas se recalculan para la posicion actual (``recompute``, con cambio
  ``monitor`` si el perfil se calibro en otro monitor); si alguno difiere, el
  perfil NO se reutiliza y se pide recalibrar (``recalibrate``).

Al terminar cierra solo la ventana abierta por la prueba y comprueba que las
ventanas de Visual Studio Code no cambiaron. No escribe texto ni pulsa
controles (el pipeline solo mueve el puntero para verificar puntos seguros).

Con un solo monitor la prueba calibra ese unico monitor (no se salta).

Precondicion: el Bloc de notas no debe tener ventanas abiertas por el usuario;
si las tiene, la prueba falla pidiendo cerrarlas (no SKIP).

Requiere Windows y JARVIS_TEST_GUI_REAL=1. Ejecutar de uno en uno:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/calibration_pipeline/test_calibracion_cada_monitor_entorno_real.py -v -s
"""

from __future__ import annotations

import atexit
import os
import time
import unittest
from typing import Any, Dict, List, Optional, Tuple

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.calibration.calibration_pipeline import POLICY_TEST, UICalibrationPipeline
from src.hands.calibration.calibration_profile_storage import CalibrationProfileStore
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_RECOMPUTE,
    ACTION_USE,
    CLIENT_SIZE_TOLERANCE,
    SCALE_TOLERANCE,
    CalibrationValidityService,
)

APLICACION = "notepad"
PROCESO = "notepad.exe"
ESPERA_CIERRE_SEGUNDOS = 15.0

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_calibracion_cada_monitor_lock.lock"
)

# Estado compartido de la sesion (seccion 21 de las reglas): una sola ventana.
_ESTADO: Dict[str, Any] = {"window_id": None, "pid": None}


def _gui_lock_activo() -> bool:
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        import psutil

        return psutil.pid_exists(int(pid_texto)) and int(pid_texto) != os.getpid()
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock() -> None:
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock() -> None:
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


def _cerrar_ventana_de_prueba() -> None:
    """Cierra solo la ventana abierta por la prueba (WM_CLOSE por HWND)."""
    window_id = _ESTADO.get("window_id")
    if not window_id:
        return
    try:
        get_desktop_platform().close_window(int(window_id))
    except Exception:
        pass
    _ESTADO["window_id"] = None
    _ESTADO["pid"] = None


atexit.register(_cerrar_ventana_de_prueba)


def _pantallas(adapter: Any) -> List[Any]:
    resultado = adapter.enumerate_displays()
    if not resultado.ok or not resultado.value:
        raise AssertionError("No se pudieron enumerar monitores: %s" % resultado.error)
    return list(resultado.value)


def _monitor_de_pruebas(pantallas: List[Any]) -> Any:
    """Monitor no principal mas a la derecha (misma regla que TestMonitorPolicy)."""
    no_principales = [p for p in pantallas if not p.is_primary]
    if not no_principales:
        return pantallas[0]
    return max(no_principales, key=lambda p: (p.bounds.right, p.bounds.center[0], p.bounds.top))


def _orden_de_calibracion(pantallas: List[Any], pruebas: Any) -> List[Any]:
    """Primero el monitor de pruebas y despues el resto, de izquierda a derecha."""
    resto = [p for p in pantallas if p.display_id != pruebas.display_id]
    resto.sort(key=lambda p: (p.bounds.left, p.bounds.top))
    return [pruebas] + resto


def _estado_ventanas_vscode(adapter: Any) -> List[Tuple[int, Any, bool, bool]]:
    resultado = adapter.list_windows(app_identity="Code.exe", visible_only=False)
    if not resultado.ok:
        return []
    estado = []
    for ventana in resultado.value or []:
        bounds = ventana.bounds.to_dict() if ventana.bounds is not None else None
        estado.append((int(ventana.window_id), bounds, bool(ventana.is_maximized), bool(ventana.is_minimized)))
    return sorted(estado, key=lambda e: e[0])


def _mismo_tamano(a: Optional[Tuple[int, int]], b: Optional[Tuple[int, int]]) -> bool:
    if not a or not b:
        return False
    return abs(int(a[0]) - int(b[0])) <= CLIENT_SIZE_TOLERANCE and abs(int(a[1]) - int(b[1])) <= CLIENT_SIZE_TOLERANCE


class TestCalibracionCadaMonitorEntornoReal(unittest.TestCase):
    """Calibra la misma ventana de prueba en cada monitor y comprueba el recalculo."""

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows (excepcion (a): APIs nativas de Windows)")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        if _gui_lock_activo():
            raise AssertionError("Otro test GUI esta en ejecucion (lock activo); esperar a que termine")
        _adquirir_gui_lock()
        try:
            cls.adapter = get_desktop_platform()
            usuario = cls.adapter.list_windows(app_identity=PROCESO, visible_only=True)
            if usuario.ok and usuario.value:
                raise AssertionError(
                    "El Bloc de notas ya tiene ventanas abiertas por el usuario; cerrarlas y repetir la prueba"
                )
            cls.pantallas = _pantallas(cls.adapter)
            cls.monitor_pruebas = _monitor_de_pruebas(cls.pantallas)
            cls.store = CalibrationProfileStore()
            cls.store.initialize()
            cls.validity = CalibrationValidityService(store=cls.store, adapter=cls.adapter)
            cls.vscode_antes = _estado_ventanas_vscode(cls.adapter)
            cls._abrir_ventana_de_prueba()
        except Exception:
            _cerrar_ventana_de_prueba()
            _liberar_gui_lock()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            _cerrar_ventana_de_prueba()
        finally:
            _liberar_gui_lock()

    @classmethod
    def _abrir_ventana_de_prueba(cls) -> None:
        from src.hands.apps.platform_launch import ApplicationLaunchService

        outcome = ApplicationLaunchService(desktop=cls.adapter).open(APLICACION, timeout=15.0)
        if not outcome.success or outcome.window is None:
            raise AssertionError("No se pudo abrir el Bloc de notas: %s" % (outcome.error,))
        if outcome.reused_existing:
            raise AssertionError("Se reutilizo una ventana existente; la prueba necesita una instancia propia")
        window_id = int(outcome.window.window_id)
        _ESTADO["window_id"] = window_id
        _ESTADO["pid"] = int(outcome.window.pid)
        destino = cls.monitor_pruebas.display_id
        for paso, resultado in (
            ("mover", cls.adapter.move_window_to_display(window_id, destino)),
            ("maximizar", cls.adapter.maximize_window(window_id)),
        ):
            if not resultado.ok:
                raise AssertionError("No se pudo %s la ventana de prueba: %s" % (paso, resultado.error))

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _ventana(self) -> Any:
        resultado = self.adapter.get_window(int(_ESTADO["window_id"]))
        self.assertTrue(resultado.ok and resultado.value is not None, "La ventana de prueba ya no existe")
        return resultado.value

    def _calibrar_en(self, pantalla: Any) -> Any:
        pipeline = UICalibrationPipeline(adapter=self.adapter, store=self.store)
        return pipeline.calibrate(
            APLICACION,
            monitor_reference="display:%s" % pantalla.display_id,
            policy=POLICY_TEST,
            reuse_window=True,
        )

    def _verificar_calibracion(self, pantalla: Any, report: Any) -> Any:
        detalle = "monitor=%s etapa=%s error=%s avisos=%s" % (
            pantalla.display_id, report.stage_failed, report.error, report.warnings,
        )
        self.assertTrue(report.success, detalle)
        self.assertIsNone(report.stage_failed, detalle)
        self.assertTrue(report.reused_window, "Debe reutilizar la ventana de la prueba: " + detalle)
        self.assertEqual(int(report.window["window_id"]), int(_ESTADO["window_id"]), detalle)
        self.assertEqual(report.display["display_id"], pantalla.display_id, detalle)
        self.assertEqual(report.metrics.get("display_source"), "display_id", detalle)
        self.assertGreaterEqual(len(report.validated_elements()), 1, detalle)
        self.assertIsNotNone(report.profile_id, "El perfil debe persistirse en SQLite: " + detalle)

        perfil = self.store.get_profile(report.profile_id)
        self.assertIsNotNone(perfil, "El perfil persistido no se puede leer: " + detalle)
        self.assertEqual(perfil.display_id, pantalla.display_id, detalle)
        self.assertLessEqual(abs(float(perfil.scale_factor) - float(pantalla.scale_factor)), SCALE_TOLERANCE, detalle)
        self.assertEqual(int(perfil.dpi), int(pantalla.dpi), detalle)
        self.assertEqual(perfil.window_state, "maximized", detalle)
        self.assertEqual(perfil.topology_fingerprint, report.topology_fingerprint, detalle)
        # Ningun control validado puede quedar en otro monitor.
        for elemento in report.validated_elements():
            if elemento.display_id is not None:
                self.assertEqual(elemento.display_id, pantalla.display_id, elemento.control_id + ": " + detalle)
        return perfil

    def _verificar_regreso_al_monitor_de_pruebas(self, pantalla: Any) -> Any:
        ventana = self._ventana()
        self.assertEqual(
            ventana.display_id, self.monitor_pruebas.display_id,
            "Tras calibrar en %s la ventana debe volver al monitor de pruebas" % pantalla.display_id,
        )
        self.assertTrue(ventana.is_maximized, "La ventana de prueba debe quedar maximizada como estaba")
        return ventana

    def _verificar_recalculo(self, pantalla: Any, perfil: Any, ventana: Any) -> None:
        entorno = self.validity.capture_environment(int(_ESTADO["window_id"]))
        compatible = (
            entorno.scale_factor is not None
            and abs(float(perfil.scale_factor) - float(entorno.scale_factor)) <= SCALE_TOLERANCE
            and (perfil.dpi is None or entorno.dpi is None or int(perfil.dpi) == int(entorno.dpi))
            and _mismo_tamano(perfil.client_size, entorno.client_size)
            and perfil.window_state == entorno.window_state
        )
        recuperado, validez = self.validity.load_valid_profile(APLICACION, int(_ESTADO["window_id"]))
        detalle = "monitor calibrado=%s entorno=%s validez=%s" % (
            pantalla.display_id, entorno.to_dict(), validez.to_dict(),
        )
        if compatible:
            self.assertTrue(validez.valid, "Misma escala y tamano: el perfil debe ser utilizable: " + detalle)
            self.assertIsNotNone(recuperado, detalle)
            self.assertEqual(recuperado.profile_id, perfil.profile_id, detalle)
            if pantalla.display_id != self.monitor_pruebas.display_id:
                self.assertEqual(validez.action, ACTION_RECOMPUTE, detalle)
                self.assertIn("monitor", validez.changes, detalle)
            else:
                self.assertIn(validez.action, (ACTION_USE, ACTION_RECOMPUTE), detalle)
            cache = recuperado.absolute_cache or {}
            self.assertIn("client_bounds", cache, detalle)
            self.assertIsNotNone(ventana.client_bounds, detalle)
            esperado = ventana.client_bounds.to_int_tuple()
            from src.desktop.platform_contract import Rect

            obtenido = Rect.from_any(cache["client_bounds"])
            self.assertIsNotNone(obtenido, detalle)
            self.assertEqual(
                obtenido.to_int_tuple(), esperado,
                "Las absolutas deben recalcularse para la posicion actual de la ventana: " + detalle,
            )
        else:
            self.assertFalse(
                validez.valid,
                "Escala, DPI, tamano o estado distintos: el perfil no puede reutilizarse: " + detalle,
            )
            self.assertIsNone(recuperado, detalle)
            self.assertEqual(validez.action, ACTION_RECALIBRATE, detalle)

    # ------------------------------------------------------------------
    # Prueba
    # ------------------------------------------------------------------

    def test_calibra_la_misma_ventana_en_cada_monitor_entorno_real(self):
        orden = _orden_de_calibracion(self.pantallas, self.monitor_pruebas)
        print(
            "\n[cada-monitor] %d monitor(es); pruebas=%s; orden=%s"
            % (len(orden), self.monitor_pruebas.display_id, [p.display_id for p in orden])
        )
        perfiles: Dict[str, Any] = {}
        for pantalla in orden:
            with self.subTest(monitor=pantalla.display_id):
                report = self._calibrar_en(pantalla)
                perfil = self._verificar_calibracion(pantalla, report)
                perfiles[pantalla.display_id] = perfil
                ventana = self._verificar_regreso_al_monitor_de_pruebas(pantalla)
                self._verificar_recalculo(pantalla, perfil, ventana)
                print(
                    "[cada-monitor] %s: escala=%s dpi=%s cliente=%s validados=%d perfil=%s"
                    % (
                        pantalla.display_id, perfil.scale_factor, perfil.dpi, perfil.client_size,
                        len(report.validated_elements()), report.profile_id,
                    )
                )
        self.assertEqual(set(perfiles), {p.display_id for p in orden}, "Debe calibrarse cada monitor")

        # La ventana sigue siendo la de la prueba y VS Code no cambio.
        self.assertEqual(int(self._ventana().pid), int(_ESTADO["pid"]))
        window_id = int(_ESTADO["window_id"])
        _cerrar_ventana_de_prueba()
        limite = time.monotonic() + ESPERA_CIERRE_SEGUNDOS
        cerrada = False
        while time.monotonic() < limite:
            actual = self.adapter.get_window(window_id)
            if not actual.ok or actual.value is None or not actual.value.is_visible:
                cerrada = True
                break
            time.sleep(0.25)
        self.assertTrue(cerrada, "La ventana abierta por la prueba sigue abierta")
        self.assertEqual(
            _estado_ventanas_vscode(self.adapter), self.vscode_antes,
            "Las ventanas de Visual Studio Code no deben cambiar",
        )


if __name__ == "__main__":
    unittest.main()
