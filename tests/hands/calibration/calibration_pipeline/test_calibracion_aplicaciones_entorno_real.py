# -*- coding: ascii -*-
"""
Prueba GUI real en Windows de calibracion de aplicaciones inocuas.

Calibra por el pipeline de produccion (`UICalibrationPipeline.calibrate` con
politica de pruebas: monitor no principal mas a la derecha por geometria real)
UNA aplicacion por vez y solo con una instancia propia abierta por la prueba:

- Bloc de notas (`notepad`).
- Calculadora (`calculadora`, o `calculator` si el menu Inicio esta en ingles):
  aplicacion empaquetada (UWP) lanzada por su AUMID.
- Una aplicacion de otra familia: navegador Chromium (`chrome` o, si Chrome no
  esta disponible o tiene ventanas abiertas, `microsoft edge`).

Para cada aplicacion verifica: exito sin etapa fallida, perfil persistido en
SQLite, al menos un control validado, monitor de pruebas, instancia abierta por
JARVIS (no reutiliza una ventana del usuario), ventana propia cerrada al
terminar y ventanas de Visual Studio Code sin cambios de posicion ni estado.

No escribe texto ni pulsa controles: el pipeline solo mueve el puntero para
verificar puntos seguros. Nunca cierra procesos ni ventanas preexistentes.

Precondicion: la aplicacion bajo prueba no debe tener ventanas abiertas por el
usuario (para el navegador basta con que uno de los dos candidatos no las
tenga). Si las tiene, la prueba falla indicando que ventana cerrar; no se salta.

Requiere Windows y JARVIS_TEST_GUI_REAL=1. Ejecutar de uno en uno (lock de
fichero; nunca en paralelo con otros tests GUI):
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/calibration_pipeline/test_calibracion_aplicaciones_entorno_real.py -v -s
"""

from __future__ import annotations

import os
import time
import unittest
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.calibration.calibration_pipeline import (
    POLICY_TEST,
    STAGE_LAUNCH,
    UICalibrationPipeline,
)

NOMBRES_BLOC_DE_NOTAS = ("notepad",)
NOMBRES_CALCULADORA = ("calculadora", "calculator")
# (nombre para JARVIS, nombre del proceso del navegador)
NAVEGADORES_CHROMIUM = (("chrome", "chrome.exe"), ("microsoft edge", "msedge.exe"))

CODIGOS_NO_ENCONTRADA = ("not_found", "not_installed")
ESPERA_CIERRE_SEGUNDOS = 15.0

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_calibracion_aplicaciones_lock.lock"
)


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


def _monitor_esperado(adapter: Any) -> Any:
    """Monitor no principal mas a la derecha (misma regla que TestMonitorPolicy)."""
    resultado = adapter.enumerate_displays()
    if not resultado.ok:
        raise AssertionError("No se pudieron enumerar monitores: %s" % resultado.error)
    pantallas = resultado.value
    no_principales = [p for p in pantallas if not p.is_primary]
    if not no_principales:
        return pantallas[0]
    return max(no_principales, key=lambda p: (p.bounds.right, p.bounds.center[0], p.bounds.top))


def _estado_ventanas_vscode(adapter: Any) -> List[Tuple[int, Any, bool, bool]]:
    """Posicion y estado de las ventanas de VS Code (solo lectura)."""
    resultado = adapter.list_windows(app_identity="Code.exe", visible_only=False)
    if not resultado.ok:
        return []
    estado = []
    for ventana in resultado.value or []:
        bounds = ventana.bounds.to_dict() if ventana.bounds is not None else None
        estado.append((int(ventana.window_id), bounds, bool(ventana.is_maximized), bool(ventana.is_minimized)))
    return sorted(estado, key=lambda e: e[0])


def _tiene_ventana_visible(adapter: Any, nombre_proceso: str) -> bool:
    resultado = adapter.list_windows(app_identity=nombre_proceso, visible_only=True)
    return bool(resultado.ok and resultado.value)


def _codigo_error_lanzamiento(report: Any) -> str:
    evidencia = (report.evidence or {}).get(STAGE_LAUNCH) or {}
    error = evidencia.get("error") if isinstance(evidencia, dict) else None
    codigo = error.get("code") if isinstance(error, dict) else ""
    return str(getattr(codigo, "value", codigo) or "").lower()


class TestCalibracionAplicacionesEntornoReal(unittest.TestCase):
    """Calibracion real de aplicaciones inocuas, una por vez, en el monitor de pruebas."""

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows (excepcion (a): APIs nativas de Windows)")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest("Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real")
        if _gui_lock_activo():
            raise AssertionError("Otro test GUI esta en ejecucion (lock activo); esperar a que termine")
        _adquirir_gui_lock()
        cls.adapter = get_desktop_platform()
        cls.monitor_esperado = _monitor_esperado(cls.adapter)

    @classmethod
    def tearDownClass(cls):
        _liberar_gui_lock()
        cls.adapter = None
        cls.monitor_esperado = None

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _calibrar(self, nombres: Sequence[str]) -> Tuple[str, Any]:
        """Calibra el primer nombre que el lanzador localiza en este equipo.

        Solo se prueba el siguiente nombre cuando el anterior no se encuentra
        (idioma del menu Inicio); cualquier otro fallo se devuelve tal cual.
        """
        ultimo: Optional[Tuple[str, Any]] = None
        for nombre in nombres:
            pipeline = UICalibrationPipeline(adapter=self.adapter)
            report = pipeline.calibrate(nombre, policy=POLICY_TEST, reuse_window=False)
            ultimo = (nombre, report)
            if report.success or report.stage_failed != STAGE_LAUNCH:
                return ultimo
            if _codigo_error_lanzamiento(report) not in CODIGOS_NO_ENCONTRADA:
                return ultimo
        assert ultimo is not None
        return ultimo

    def _esperar_cierre(self, window_id: int) -> bool:
        limite = time.monotonic() + ESPERA_CIERRE_SEGUNDOS
        while time.monotonic() < limite:
            actual = self.adapter.get_window(int(window_id))
            if not actual.ok or actual.value is None or not actual.value.is_visible:
                return True
            time.sleep(0.25)
        return False

    def _verificar(self, nombre: str, report: Any, vscode_antes: List[Any]) -> None:
        metricas = report.metrics or {}
        diagnostico = {
            "tiempos_s": metricas.get("timings"),
            "total_s": metricas.get("total_seconds"),
            "candidatos_por_fuente": metricas.get("candidates_by_source"),
            "qwen3vl": metricas.get("qwen3vl"),
            "puerta": {
                "aceptados": metricas.get("gate_accepted"),
                "rechazados": metricas.get("gate_rejected"),
            },
            "puntero": {
                "comprobados": metricas.get("pointer_checks"),
                "verificados": metricas.get("pointer_verified"),
            },
            "foco_restaurado": metricas.get("focus_restored"),
        }
        # Visible con -s: tiempos por etapa, detectores y foco aunque pase.
        print("\n[CALIBRACION %s] %s" % (nombre, diagnostico))
        detalle = "%s: etapa=%s error=%s avisos=%s diagnostico=%s" % (
            nombre, report.stage_failed, report.error, report.warnings, diagnostico,
        )
        if report.stage_failed == STAGE_LAUNCH and "ya estaba abierta" in str(report.error or ""):
            self.fail(
                "%s ya tenia una ventana abierta por el usuario; cerrarla y repetir la prueba (%s)"
                % (nombre, detalle)
            )
        self.assertTrue(report.success, detalle)
        self.assertIsNone(report.stage_failed, detalle)
        self.assertTrue(report.launched_by_jarvis, "Debe abrirse una instancia propia: " + detalle)
        self.assertFalse(report.reused_window, detalle)
        self.assertIsNotNone(report.profile_id, "El perfil debe persistirse en SQLite: " + detalle)
        self.assertGreaterEqual(len(report.validated_elements()), 1, detalle)
        self.assertEqual(
            report.display["display_id"], self.monitor_esperado.display_id,
            "La calibracion debe hacerse en el monitor de pruebas: " + detalle,
        )
        window_id = int(report.window["window_id"])
        self.assertTrue(
            self._esperar_cierre(window_id),
            "La ventana abierta por la prueba sigue abierta tras la calibracion: " + detalle,
        )
        self.assertEqual(
            _estado_ventanas_vscode(self.adapter), vscode_antes,
            "Las ventanas de Visual Studio Code no deben cambiar: " + detalle,
        )

    # ------------------------------------------------------------------
    # Pruebas (una aplicacion por test; los tests se ejecutan en serie)
    # ------------------------------------------------------------------

    def test_01_calibra_bloc_de_notas_entorno_real(self):
        vscode_antes = _estado_ventanas_vscode(self.adapter)
        nombre, report = self._calibrar(NOMBRES_BLOC_DE_NOTAS)
        self._verificar(nombre, report, vscode_antes)

    def test_02_calibra_calculadora_entorno_real(self):
        vscode_antes = _estado_ventanas_vscode(self.adapter)
        nombre, report = self._calibrar(NOMBRES_CALCULADORA)
        self._verificar(nombre, report, vscode_antes)

    def test_03_calibra_navegador_chromium_entorno_real(self):
        candidatos = [
            nombre for nombre, proceso in NAVEGADORES_CHROMIUM
            if not _tiene_ventana_visible(self.adapter, proceso)
        ]
        if not candidatos:
            self.fail(
                "Chrome y Edge tienen ventanas abiertas por el usuario; cerrar las de uno de "
                "los dos (por ejemplo Chrome) y repetir la prueba"
            )
        vscode_antes = _estado_ventanas_vscode(self.adapter)
        nombre, report = self._calibrar(candidatos)
        self._verificar(nombre, report, vscode_antes)


if __name__ == "__main__":
    unittest.main()
