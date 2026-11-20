# -*- coding: ascii -*-
"""
Prueba GUI real en Windows: recuperar el perfil de calibracion tras reiniciar
el gestor, solo si la huella coincide.

Abre UNA sola ventana propia del Bloc de notas (instancia lanzada por la
prueba), la deja maximizada en el monitor de pruebas (no principal mas a la
derecha por geometria real) y:

1. La calibra por el pipeline de produccion (``UICalibrationPipeline.calibrate``
   reutilizando esa ventana) y comprueba que el informe registra topologia
   (fingerprint), escala/DPI del monitor, PID y ventana, arbol de accesibilidad
   (nodos, origen y hash cuando hay nodos), detectores usados y metricas por
   etapa.
2. "Reinicia" el gestor: en un proceso Python NUEVO (sin estado en memoria del
   proceso de la prueba) crea un pipeline y un almacen nuevos y llama a
   ``UICalibrationPipeline.recover_profile``. El perfil se recupera (mismo
   ``profile_id``, misma topologia) porque la huella de ventana/escala coincide.
3. Cambia la huella de la ventana (la restaura y la deja a la mitad del area
   util del monitor de pruebas: cambia el estado y el tamano del area cliente)
   y repite la recuperacion en otro proceso nuevo: el perfil NO se recupera y
   se pide recalibrar.
4. Control positivo: vuelve a maximizar la ventana en el monitor de pruebas y
   el perfil se recupera de nuevo en otro proceso nuevo.

Al terminar cierra solo la ventana abierta por la prueba y comprueba que las
ventanas de Visual Studio Code no cambiaron. No escribe texto ni pulsa
controles. Ningun dato fisico se escribe en entities.json (el perfil va a la
SQLite local por machine_id).

Precondicion: el Bloc de notas no debe tener ventanas abiertas por el usuario;
si las tiene, la prueba falla pidiendo cerrarlas (no SKIP).

Requiere Windows y JARVIS_TEST_GUI_REAL=1. Ejecutar de uno en uno:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/calibration_pipeline/test_recuperacion_perfil_reinicio_entorno_real.py -v -s
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.desktop.monitor_topology import get_current_topology
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import Rect, get_desktop_platform
from src.hands.calibration.calibration_pipeline import (
    POLICY_TEST,
    STAGE_ACCESSIBILITY,
    STAGE_LAUNCH,
    STAGE_PERSISTENCE,
    UICalibrationPipeline,
)
from src.hands.calibration.calibration_profile_storage import CalibrationProfileStore
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_RECOMPUTE,
    ACTION_USE,
    CalibrationValidityService,
)

# tests/hands/calibration/calibration_pipeline/ -> ... -> raiz del proyecto
RAIZ = Path(__file__).resolve().parents[4]

APLICACION = "notepad"
PROCESO = "notepad.exe"
ESPERA_CIERRE_SEGUNDOS = 15.0
TIMEOUT_REINICIO_SEGUNDOS = 120.0
MARCA_RESULTADO = "RESULTADO_RECUPERACION_JSON:"

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_recuperacion_perfil_lock.lock"
)

# Estado compartido de la sesion (seccion 21 de las reglas): una sola ventana.
_ESTADO: Dict[str, Any] = {"window_id": None, "pid": None, "report": None}

# Proceso nuevo: pipeline y almacen recien creados, sin estado del proceso de la prueba.
_SCRIPT_REINICIO = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from src.desktop.platform_contract import get_desktop_platform\n"
    "from src.hands.calibration.calibration_pipeline import UICalibrationPipeline\n"
    "pipeline = UICalibrationPipeline(adapter=get_desktop_platform())\n"
    "info = pipeline.recover_profile(sys.argv[2], int(sys.argv[3]))\n"
    "print(%r + json.dumps(info, default=str))\n" % MARCA_RESULTADO
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


def _monitor_de_pruebas(adapter: Any) -> Any:
    resultado = adapter.enumerate_displays()
    if not resultado.ok or not resultado.value:
        raise AssertionError("No se pudieron enumerar monitores: %s" % resultado.error)
    pantallas = resultado.value
    no_principales = [p for p in pantallas if not p.is_primary]
    if not no_principales:
        return pantallas[0]
    return max(no_principales, key=lambda p: (p.bounds.right, p.bounds.center[0], p.bounds.top))


def _estado_ventanas_vscode(adapter: Any) -> List[Tuple[int, Any, bool, bool]]:
    resultado = adapter.list_windows(app_identity="Code.exe", visible_only=False)
    if not resultado.ok:
        return []
    estado = []
    for ventana in resultado.value or []:
        bounds = ventana.bounds.to_dict() if ventana.bounds is not None else None
        estado.append((int(ventana.window_id), bounds, bool(ventana.is_maximized), bool(ventana.is_minimized)))
    return sorted(estado, key=lambda e: e[0])


def _recuperar_en_proceso_nuevo(app_id: str, window_id: int) -> Dict[str, Any]:
    """Ejecuta ``recover_profile`` en un interprete nuevo y devuelve su resultado."""
    completado = subprocess.run(
        [sys.executable, "-c", _SCRIPT_REINICIO, str(RAIZ), app_id, str(int(window_id))],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_REINICIO_SEGUNDOS,
    )
    for linea in (completado.stdout or "").splitlines():
        if linea.startswith(MARCA_RESULTADO):
            return json.loads(linea[len(MARCA_RESULTADO):])
    raise AssertionError(
        "El proceso reiniciado no devolvio resultado (codigo %s): stdout=%r stderr=%r"
        % (completado.returncode, (completado.stdout or "")[-2000:], (completado.stderr or "")[-2000:])
    )


class TestRecuperacionPerfilReinicioEntornoReal(unittest.TestCase):
    """Recupera el perfil tras reiniciar solo si la huella coincide."""

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
            cls.monitor_pruebas = _monitor_de_pruebas(cls.adapter)
            cls.store = CalibrationProfileStore()
            cls.store.initialize()
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
        _ESTADO["window_id"] = int(outcome.window.window_id)
        _ESTADO["pid"] = int(outcome.window.pid)
        cls._maximizar_en_monitor_de_pruebas()

    @classmethod
    def _maximizar_en_monitor_de_pruebas(cls) -> None:
        window_id = int(_ESTADO["window_id"])
        for paso, resultado in (
            ("mover", cls.adapter.move_window_to_display(window_id, cls.monitor_pruebas.display_id)),
            ("maximizar", cls.adapter.maximize_window(window_id)),
        ):
            if not resultado.ok:
                raise AssertionError("No se pudo %s la ventana de prueba: %s" % (paso, resultado.error))

    def _report(self) -> Any:
        report = _ESTADO.get("report")
        if report is None:
            self.fail("test_01 debe calibrar antes (los tests se ejecutan en orden)")
        return report

    def _verificar_recuperado(self, info: Dict[str, Any], momento: str) -> None:
        report = self._report()
        detalle = "%s: %s" % (momento, info)
        self.assertTrue(info.get("recovered"), "El perfil debe recuperarse tras reiniciar: " + detalle)
        perfil = info.get("profile") or {}
        self.assertEqual(perfil.get("profile_id"), report.profile_id, detalle)
        self.assertEqual(perfil.get("topology_fingerprint"), report.topology_fingerprint, detalle)
        self.assertEqual(perfil.get("display_id"), self.monitor_pruebas.display_id, detalle)
        self.assertGreaterEqual(int(perfil.get("controls") or 0), 1, detalle)
        accion = (info.get("validity") or {}).get("action")
        self.assertIn(accion, (ACTION_USE, ACTION_RECOMPUTE), detalle)
        ventana = info.get("window") or {}
        self.assertEqual(int(ventana.get("window_id") or 0), int(_ESTADO["window_id"]), detalle)
        self.assertEqual(int(ventana.get("pid") or 0), int(_ESTADO["pid"]), detalle)

    # ------------------------------------------------------------------
    # Pruebas (en orden; comparten la ventana y el informe)
    # ------------------------------------------------------------------

    def test_01_calibra_y_registra_topologia_ventana_arbol_y_detectores(self):
        pipeline = UICalibrationPipeline(adapter=self.adapter, store=self.store)
        report = pipeline.calibrate(APLICACION, policy=POLICY_TEST, reuse_window=True)
        detalle = "etapa=%s error=%s avisos=%s" % (report.stage_failed, report.error, report.warnings)
        self.assertTrue(report.success, detalle)
        self.assertIsNone(report.stage_failed, detalle)
        self.assertTrue(report.reused_window, detalle)
        self.assertIsNotNone(report.profile_id, detalle)
        _ESTADO["report"] = report

        # Topologia.
        self.assertTrue(report.topology_fingerprint, detalle)
        self.assertEqual(report.topology_fingerprint, get_current_topology(self.adapter).fingerprint, detalle)
        self.assertGreaterEqual(int(report.metrics.get("displays") or 0), 1, detalle)
        # Monitor y escala.
        self.assertEqual(report.display["display_id"], self.monitor_pruebas.display_id, detalle)
        self.assertIsNotNone(report.display.get("scale_factor"), detalle)
        self.assertIsNotNone(report.display.get("dpi"), detalle)
        # PID y ventana.
        self.assertEqual(int(report.window["window_id"]), int(_ESTADO["window_id"]), detalle)
        self.assertEqual(int(report.window["pid"]), int(_ESTADO["pid"]), detalle)
        self.assertIsNotNone(report.window.get("scale_factor"), detalle)
        # Arbol de accesibilidad.
        self.assertIn("tree_nodes", report.metrics, detalle)
        if int(report.metrics["tree_nodes"]) > 0:
            self.assertTrue(report.metrics.get("tree_hash"), detalle)
            self.assertTrue(report.metrics.get("tree_source"), detalle)
        # Detectores y metricas.
        self.assertTrue(report.metrics.get("detectors"), "Deben registrarse los detectores usados: " + detalle)
        self.assertIn("candidates_by_source", report.metrics, detalle)
        self.assertGreaterEqual(int(report.metrics.get("pointer_verified") or 0), 1, detalle)
        tiempos = report.metrics.get("timings") or {}
        for etapa in (STAGE_LAUNCH, STAGE_ACCESSIBILITY, STAGE_PERSISTENCE):
            self.assertIn(etapa, tiempos, "Falta el tiempo de la etapa %s: %s" % (etapa, detalle))
        self.assertIn("total_seconds", report.metrics, detalle)
        print(
            "\n[recuperacion] topologia=%s monitor=%s escala=%s dpi=%s pid=%s ventana=%s nodos=%s "
            "detectores=%s validados=%d"
            % (
                report.topology_fingerprint[:12], report.display["display_id"], report.display.get("scale_factor"),
                report.display.get("dpi"), report.window["pid"], report.window["window_id"],
                report.metrics.get("tree_nodes"), report.metrics.get("detectors"), len(report.validated_elements()),
            )
        )

    def test_02_reinicio_recupera_el_perfil_con_la_misma_huella(self):
        info = _recuperar_en_proceso_nuevo(APLICACION, int(_ESTADO["window_id"]))
        self._verificar_recuperado(info, "tras reiniciar")
        # La huella persistida coincide con la del entorno actual.
        entorno = CalibrationValidityService(store=self.store, adapter=self.adapter).capture_environment(
            int(_ESTADO["window_id"])
        )
        perfil = self.store.get_profile(self._report().profile_id)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.window_fingerprint, entorno.window_fingerprint())

    def test_03_huella_distinta_no_recupera_y_control_positivo(self):
        window_id = int(_ESTADO["window_id"])
        area = self.monitor_pruebas.work_area
        mitad = Rect(
            area.left + area.width / 4.0,
            area.top + area.height / 4.0,
            area.left + area.width * 3.0 / 4.0,
            area.top + area.height * 3.0 / 4.0,
        )
        restaurada = self.adapter.restore_window(window_id)
        self.assertTrue(restaurada.ok, "No se pudo restaurar la ventana de prueba: %s" % restaurada.error)
        redimensionada = self.adapter.set_window_bounds(window_id, mitad)
        self.assertTrue(redimensionada.ok, "No se pudo redimensionar la ventana de prueba: %s" % redimensionada.error)
        actual = self.adapter.get_window(window_id)
        self.assertTrue(actual.ok and actual.value is not None)
        self.assertFalse(actual.value.is_maximized, "La ventana debe quedar sin maximizar para cambiar la huella")

        info = _recuperar_en_proceso_nuevo(APLICACION, window_id)
        detalle = "huella cambiada: %s" % info
        self.assertFalse(info.get("recovered"), "Con otra huella el perfil NO debe recuperarse: " + detalle)
        validez = info.get("validity") or {}
        self.assertEqual(validez.get("action"), ACTION_RECALIBRATE, detalle)
        self.assertFalse(validez.get("valid"), detalle)

        # Control positivo: misma huella otra vez -> se recupera.
        self._maximizar_en_monitor_de_pruebas()
        info = _recuperar_en_proceso_nuevo(APLICACION, window_id)
        self._verificar_recuperado(info, "tras volver a maximizar")

    def test_04_cierra_solo_la_ventana_de_prueba_y_no_toca_vscode(self):
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
