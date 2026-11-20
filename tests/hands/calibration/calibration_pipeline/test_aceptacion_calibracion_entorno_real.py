# -*- coding: ascii -*-
"""
Prueba de aceptacion GUI real en Windows de la calibracion automatica.

Ciclo completo sobre la fixture Qt de calibracion (objetivo controlado, con un
canal de verdad separado: ``runtime/action_counts.json`` cuenta cada accion
inocua que recibe la ventana) y repeticion en otra familia de GUI:

test_01 (ciclo completo, fixture Qt):
  preflight real del ejecutable que abre la fixture (``ApplicationPreflight``)
  -> abrir una instancia propia -> pipeline de produccion
  (``UICalibrationPipeline.calibrate`` con ``depth="deep"``): elegir monitor de
  pruebas -> mover -> maximizar -> estabilidad -> accesibilidad -> captura ->
  vision/OCR -> fusion -> puerta de calidad -> transformar -> puntero ->
  persistir -> exploracion profunda ACOTADA (presupuesto pequeno) ->
  accion inocua: clic verificado (``click_element``) sobre el recurso del
  boton "Aceptar" que publica el pipeline para el Planner; el canal de verdad
  debe registrar exactamente esa accion y ninguna otra ->
  reiniciar (proceso Python nuevo) -> recuperar el perfil.
test_02 (otra familia de GUI): Bloc de notas (Win32/WinUI, instancia propia
  abierta por el lanzador de produccion: descubrimiento + preflight +
  apertura) calibrado en el monitor de pruebas.
test_03 (metricas): al menos dos familias calibradas, al menos un control
  validado SIN accesibilidad (solo fuentes visuales; en la fixture,
  ``canvas_mano`` se dibuja a mano y no expone UIA) y metricas por tecnologia,
  monitor y escala escritas en ``informe_aceptacion_calibracion.json`` junto a
  este fichero.

No escribe texto. La unica accion con efecto es el clic en "Aceptar" de la
fixture (solo incrementa un contador en memoria). Cierra solo lo que abre y
comprueba que las ventanas de Visual Studio Code no cambian.

Precondicion: el Bloc de notas no debe tener ventanas abiertas por el usuario.

Requiere Windows, Ollama con qwen3-vl (deteccion visual) y
JARVIS_TEST_GUI_REAL=1. Ejecutar de uno en uno:
    $env:JARVIS_TEST_GUI_REAL = "1"
    python -m pytest tests/hands/calibration/calibration_pipeline/test_aceptacion_calibracion_entorno_real.py -v -s
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
from typing import Any, Dict, List, Optional, Tuple

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.eyes.detection.visual_ui_detector_fusion import SOURCE_UIA
from src.hands.calibration.calibration_pipeline import (
    DEPTH_DEEP,
    POLICY_TEST,
    UICalibrationPipeline,
)
from src.hands.calibration.calibration_profile_storage import CalibrationProfileStore
from src.hands.calibration.ui_exploration import ExplorationBudget

RAIZ = Path(__file__).resolve().parents[4]
FIXTURE_RUN = str(RAIZ / "tests" / "fixtures" / "gui_calibration_app" / "run.py")
TITULO_FIXTURE = "JARVIS GUI Calibration Fixture"
APP_FIXTURE = {"name": TITULO_FIXTURE, "app_key": "jarvis_gui_calibration_fixture"}
ACCION_ACEPTAR = "accion_btn_aceptar"
NOMBRES_ACEPTAR = ("btn_aceptar", "aceptar")
INFORME = Path(__file__).resolve().parent / "informe_aceptacion_calibracion.json"

# Exploracion profunda acotada (presupuesto pequeno y explicito).
PRESUPUESTO = ExplorationBudget(max_depth=2, max_states=15, max_seconds=60.0, max_actions=40)
MARGEN_SEGUNDOS = 15.0

MARCA_RESULTADO = "RESULTADO_RECUPERACION_JSON:"
_SCRIPT_REINICIO = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from src.desktop.platform_contract import get_desktop_platform\n"
    "from src.hands.calibration.calibration_pipeline import UICalibrationPipeline\n"
    "pipeline = UICalibrationPipeline(adapter=get_desktop_platform())\n"
    "info = pipeline.recover_profile(sys.argv[2], int(sys.argv[3]))\n"
    "print(%r + json.dumps(info, default=str))\n" % MARCA_RESULTADO
)

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_aceptacion_calibracion_lock.lock"
)

_ESTADO: Dict[str, Any] = {"proc": None, "window_id": None, "pid": None, "reports": {}}


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


def _cerrar_fixture() -> None:
    """Cierra solo la fixture abierta por la prueba (WM_CLOSE y, si sigue, su proceso)."""
    window_id = _ESTADO.get("window_id")
    if window_id:
        try:
            get_desktop_platform().close_window(int(window_id))
        except Exception:
            pass
    proc = _ESTADO.get("proc")
    if proc is not None:
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _ESTADO["window_id"] = None
    _ESTADO["pid"] = None
    _ESTADO["proc"] = None


atexit.register(_cerrar_fixture)


def _leer_contadores() -> Dict[str, int]:
    from tests.fixtures.gui_calibration_app.truth_ground import leer_action_counts

    return dict(leer_action_counts() or {})


def _estado_ventanas_vscode(adapter: Any) -> List[Tuple[int, Any, bool, bool]]:
    resultado = adapter.list_windows(app_identity="Code.exe", visible_only=False)
    if not resultado.ok:
        return []
    estado = []
    for ventana in resultado.value or []:
        bounds = ventana.bounds.to_dict() if ventana.bounds is not None else None
        estado.append((int(ventana.window_id), bounds, bool(ventana.is_maximized), bool(ventana.is_minimized)))
    return sorted(estado, key=lambda e: e[0])


def _monitor_de_pruebas(adapter: Any) -> Any:
    resultado = adapter.enumerate_displays()
    if not resultado.ok or not resultado.value:
        raise AssertionError("No se pudieron enumerar monitores: %s" % resultado.error)
    pantallas = resultado.value
    no_principales = [p for p in pantallas if not p.is_primary]
    if not no_principales:
        return pantallas[0]
    return max(no_principales, key=lambda p: (p.bounds.right, p.bounds.center[0], p.bounds.top))


class _LanzadorFixture:
    """Entrega al pipeline la ventana de la fixture que abrio la prueba.

    La fixture no es una aplicacion instalada (no la descubre el lanzador de
    produccion); su apertura y su preflight los hace la prueba. Se entrega como
    ventana ya abierta para que el pipeline no la cierre al terminar y la
    prueba pueda actuar sobre ella y reiniciar el gestor.
    """

    def __init__(self, window: Any) -> None:
        self.window = window

    def open(self, app_name: str, timeout: float = 15.0) -> Any:
        from src.hands.apps.platform_launch import LaunchOutcome

        return LaunchOutcome(
            True, pid=int(self.window.pid), window=self.window, reused_existing=True,
            app_name=app_name, process_verified=True, window_verified=True,
            evidence={"reuse": "fixture_abierta_por_la_prueba"},
        )


def _recuperar_en_proceso_nuevo(app_key: str, window_id: int) -> Dict[str, Any]:
    completado = subprocess.run(
        [sys.executable, "-c", _SCRIPT_REINICIO, str(RAIZ), app_key, str(int(window_id))],
        cwd=str(RAIZ), capture_output=True, text=True, timeout=120.0,
    )
    for linea in (completado.stdout or "").splitlines():
        if linea.startswith(MARCA_RESULTADO):
            return json.loads(linea[len(MARCA_RESULTADO):])
    raise AssertionError(
        "El proceso reiniciado no devolvio resultado (codigo %s): stderr=%r"
        % (completado.returncode, (completado.stderr or "")[-2000:])
    )


def _es_visual(elemento: Any) -> bool:
    fuentes = {str(s) for s in (elemento.sources or [])}
    return bool(fuentes) and SOURCE_UIA not in fuentes


class TestAceptacionCalibracionEntornoReal(unittest.TestCase):
    """Ciclo completo de calibracion, dos familias de GUI y metricas."""

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
            cls.monitor_pruebas = _monitor_de_pruebas(cls.adapter)
            cls.store = CalibrationProfileStore()
            cls.store.initialize()
            cls.vscode_antes = _estado_ventanas_vscode(cls.adapter)
        except Exception:
            _liberar_gui_lock()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            _cerrar_fixture()
        finally:
            _liberar_gui_lock()

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _abrir_fixture(self) -> Any:
        from src.hands.apps.application_preflight import ApplicationPreflight

        decision = ApplicationPreflight().check_launch_target(
            {"name": TITULO_FIXTURE}, sys.executable, target_type="exe"
        )
        self.assertTrue(decision.get("allowed"), "El preflight debe permitir el ejecutable: %s" % decision)

        existentes = self.adapter.list_windows(visible_only=False)
        antes = {int(w.window_id) for w in (existentes.value or [])} if existentes.ok else set()
        proc = subprocess.Popen([sys.executable, FIXTURE_RUN], cwd=str(RAIZ))
        _ESTADO["proc"] = proc
        limite = time.monotonic() + 30.0
        while time.monotonic() < limite:
            resultado = self.adapter.list_windows(pid=proc.pid, visible_only=True)
            nuevas = [
                w for w in (resultado.value or [])
                if int(w.window_id) not in antes and TITULO_FIXTURE in str(w.title or "")
            ] if resultado.ok else []
            if nuevas:
                _ESTADO["window_id"] = int(nuevas[0].window_id)
                _ESTADO["pid"] = int(nuevas[0].pid)
                return nuevas[0]
            time.sleep(0.3)
        self.fail("No aparecio la ventana propia de la fixture en 30 s")

    def _recurso_aceptar(self, recursos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for recurso in recursos:
            texto = " ".join(str(recurso.get(k) or "") for k in ("name", "control_id")).lower()
            if any(n in texto for n in NOMBRES_ACEPTAR) and recurso.get("point"):
                return recurso
        return None

    # ------------------------------------------------------------------
    # Pruebas
    # ------------------------------------------------------------------

    def test_01_ciclo_completo_en_la_fixture_entorno_real(self):
        ventana = self._abrir_fixture()
        pipeline = UICalibrationPipeline(
            adapter=self.adapter, store=self.store, launcher=_LanzadorFixture(ventana),
            explorer_budget=PRESUPUESTO,
        )
        report = pipeline.calibrate(APP_FIXTURE, policy=POLICY_TEST, depth=DEPTH_DEEP, reuse_window=True)
        detalle = "etapa=%s error=%s avisos=%s" % (report.stage_failed, report.error, report.warnings)
        self.assertTrue(report.success, detalle)
        self.assertIsNone(report.stage_failed, detalle)
        self.assertEqual(report.display["display_id"], self.monitor_pruebas.display_id, detalle)
        self.assertIsNotNone(report.profile_id, detalle)
        self.assertGreaterEqual(len(report.validated_elements()), 3, detalle)
        _ESTADO["reports"]["qt_fixture"] = report

        # Exploracion profunda acotada.
        exploracion = report.exploration or {}
        self.assertFalse(exploracion.get("aborted"), "exploracion abortada: %s" % exploracion.get("abort_reason"))
        self.assertGreaterEqual(int(exploracion.get("states") or 0), 1, detalle)
        self.assertLessEqual(int(exploracion.get("actions_performed") or 0), PRESUPUESTO.max_actions)
        self.assertLessEqual(float(exploracion.get("elapsed_seconds") or 0.0), PRESUPUESTO.max_seconds + MARGEN_SEGUNDOS)

        # Accion inocua verificada por el canal de verdad separado.
        window_id = int(_ESTADO["window_id"])
        recursos = pipeline.resources_for_planner(APP_FIXTURE["app_key"], window_id)
        recurso = self._recurso_aceptar(recursos)
        self.assertIsNotNone(
            recurso,
            "El boton Aceptar debe publicarse al Planner con punto verificado: %s"
            % [(r.get("name"), r.get("interaction_method")) for r in recursos],
        )
        activada = self.adapter.activate_window(window_id)
        self.assertTrue(activada.ok, "No se pudo traer la fixture al frente: %s" % activada.error)
        antes = _leer_contadores()
        from src.hands.input.mouse import click_element

        hecho = click_element(
            x=float(recurso["point"][0]), y=float(recurso["point"][1]),
            window_id=window_id, pid=int(_ESTADO["pid"]),
        )
        self.assertTrue(hecho, "El clic verificado sobre Aceptar se aborto")
        limite = time.monotonic() + 5.0
        despues = _leer_contadores()
        while time.monotonic() < limite and despues.get(ACCION_ACEPTAR, 0) == antes.get(ACCION_ACEPTAR, 0):
            time.sleep(0.1)
            despues = _leer_contadores()
        self.assertEqual(despues.get(ACCION_ACEPTAR, 0) - antes.get(ACCION_ACEPTAR, 0), 1, (antes, despues))
        otras = {k: despues.get(k, 0) - antes.get(k, 0) for k in set(antes) | set(despues) if k != ACCION_ACEPTAR}
        self.assertFalse({k: v for k, v in otras.items() if v}, "Solo debe ejecutarse la accion pedida: %s" % otras)

        # Persistencia, reinicio y recuperacion.
        perfil = self.store.get_profile(report.profile_id)
        self.assertIsNotNone(perfil, detalle)
        info = _recuperar_en_proceso_nuevo(APP_FIXTURE["app_key"], window_id)
        self.assertTrue(info.get("recovered"), "El perfil debe recuperarse tras reiniciar: %s" % info)
        self.assertEqual((info.get("profile") or {}).get("profile_id"), report.profile_id, info)

        _cerrar_fixture()

    def test_02_otra_familia_bloc_de_notas_entorno_real(self):
        usuario = self.adapter.list_windows(app_identity="notepad.exe", visible_only=True)
        if usuario.ok and usuario.value:
            self.fail("El Bloc de notas tiene ventanas abiertas por el usuario; cerrarlas y repetir la prueba")
        pipeline = UICalibrationPipeline(adapter=self.adapter, store=self.store)
        report = pipeline.calibrate("notepad", policy=POLICY_TEST, reuse_window=False)
        detalle = "etapa=%s error=%s avisos=%s" % (report.stage_failed, report.error, report.warnings)
        self.assertTrue(report.success, detalle)
        self.assertTrue(report.launched_by_jarvis, detalle)
        self.assertEqual(report.display["display_id"], self.monitor_pruebas.display_id, detalle)
        self.assertGreaterEqual(len(report.validated_elements()), 1, detalle)
        _ESTADO["reports"]["win32_notepad"] = report

    def test_03_familias_control_sin_accesibilidad_y_metricas(self):
        reports = _ESTADO["reports"]
        self.assertEqual(set(reports), {"qt_fixture", "win32_notepad"}, "Deben calibrarse dos familias de GUI")
        fixture = reports["qt_fixture"]
        visuales = [e for e in fixture.validated_elements() if _es_visual(e)]
        self.assertTrue(
            visuales,
            "Debe validarse al menos un control sin accesibilidad (solo fuentes visuales): %s"
            % [(e.name, e.sources, e.validity) for e in fixture.elements],
        )

        metricas: Dict[str, Any] = {}
        for tecnologia, report in reports.items():
            validados = report.validated_elements()
            por_fuente: Dict[str, int] = {}
            for elemento in validados:
                for fuente in elemento.sources or []:
                    por_fuente[str(fuente)] = por_fuente.get(str(fuente), 0) + 1
            metricas[tecnologia] = {
                "monitor": report.display.get("display_id"),
                "escala": report.display.get("scale_factor"),
                "dpi": report.display.get("dpi"),
                "elementos": len(report.elements),
                "validados": len(validados),
                "validados_sin_accesibilidad": sum(1 for e in validados if _es_visual(e)),
                "validados_por_fuente": por_fuente,
                "punteros_verificados": report.metrics.get("pointer_verified"),
                "candidatos_por_fuente": report.metrics.get("candidates_by_source"),
                "detectores": report.metrics.get("detectors"),
                "segundos": report.metrics.get("total_seconds"),
            }
        INFORME.write_text(json.dumps(metricas, indent=2, sort_keys=True, default=str), encoding="ascii")
        print("\n[aceptacion] metricas por tecnologia, monitor y escala:\n%s" % json.dumps(metricas, indent=2, default=str))
        self.assertEqual(
            _estado_ventanas_vscode(self.adapter), self.vscode_antes,
            "Las ventanas de Visual Studio Code no deben cambiar",
        )


if __name__ == "__main__":
    unittest.main()
