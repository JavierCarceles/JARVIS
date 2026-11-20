# -*- coding: ascii -*-
"""
Prueba GUI real en Windows de calibracion de aplicaciones inocuas (unidad 3.8.6.13.2).

Calibra, UNA aplicacion por vez y solo con la instancia propia de la prueba:
- Bloc de notas (notepad): se calibra por el pipeline de produccion y se
  verifica exito, persistencia del perfil y monitor de pruebas.

La aplicacion se elige entre las que PASAN el preflight en este equipo
(condicion "(si pasan preflight)" del roadmap). Calculadora es una UWP cuya
ruta no resuelve en el preflight de este equipo y Microsoft Edge / Chrome no
tienen un objetivo de lanzamiento resuelto por el servicio de lanzamiento
(microsoft edge ya esta en ejecucion por el usuario; chrome no esta disponible
segun el servicio de lanzamiento), por lo que no se pueden calibrar aqui sin
iniciar procesos ajenos o saltarse el preflight. Se documentan en el registro
de la unidad y se dejan como seguimiento para equipos donde resuelvan.

No escribe texto ni ejecuta operaciones con efecto sobre la aplicacion bajo prueba.
Usa el pipeline de produccion UICalibrationPipeline con politica de pruebas
(TestMonitorPolicy: monitor no principal mas a la derecha por geometria real).

Requiere JARVIS_TEST_GUI_REAL=1 y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: el pipeline cierra
solo la ventana que abrio JARVIS (o restaura la del usuario). No toca Visual
Studio Code (bloqueado por politica de calibracion).
"""

from __future__ import annotations

import os
import unittest

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.calibration.calibration_pipeline import (
    POLICY_TEST,
    UICalibrationPipeline,
)

APLICACION_PRINCIPAL = "notepad"

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_calibracion_aplicaciones_lock.lock"
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


def _monitor_esperado(adapter):
    """Monitor no principal mas a la derecha (misma logica que TestMonitorPolicy)."""
    resultado = adapter.enumerate_displays()
    if not resultado.ok:
        raise AssertionError("No se pudieron enumerar monitores: %s" % resultado.error)
    pantallas = resultado.value
    no_principales = [p for p in pantallas if not p.is_primary]
    objetivo = (
        max(
            no_principales,
            key=lambda p: (p.bounds.right, p.bounds.center[0], p.bounds.top),
        )
        if no_principales
        else pantallas[0]
    )
    return objetivo


class TestCalibracionAplicacionesEntornoReal(unittest.TestCase):
    """Calibracion real de una aplicacion inocua, en el monitor de pruebas."""

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
        cls.monitor_esperado = _monitor_esperado(cls.adapter)

    @classmethod
    def tearDownClass(cls):
        try:
            _liberar_gui_lock()
        finally:
            cls.adapter = None
            cls.monitor_esperado = None

    def test_calibra_bloc_de_notas_entorno_real(self):
        """Calibra Bloc de notas por el pipeline de produccion y verifica el resultado real."""
        nombre = APLICACION_PRINCIPAL
        pipeline = UICalibrationPipeline()
        report = pipeline.calibrate(nombre, policy=POLICY_TEST, reuse_window=True)
        self.assertIsNotNone(report, "El informe de calibracion no debe ser None")
        self.assertTrue(
            report.success,
            "Calibracion de %s fallo en etapa %s: %s"
            % (nombre, report.stage_failed, report.error),
        )
        self.assertIsNone(
            report.stage_failed,
            "La calibracion de %s no debe fallar en ninguna etapa" % nombre,
        )
        self.assertIsNotNone(
            report.profile_id, "El perfil de calibracion debe persistirse en SQLite"
        )
        self.assertGreaterEqual(
            len(report.validated_elements()),
            1,
            "Debe validarse al menos un elemento interactivo",
        )
        self.assertEqual(
            report.display["display_id"],
            self.monitor_esperado.display_id,
            "La aplicacion debe calibrarse en el monitor de pruebas",
        )


if __name__ == "__main__":
    unittest.main()
