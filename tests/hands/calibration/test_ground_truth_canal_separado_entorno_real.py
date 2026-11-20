# -*- coding: ascii -*-
"""
Pruebas de la separacion entre la verdad-terreno de la fixture y el detector
evaluado (unidad 3.8.6.10.2).

Verifica que:
  1. La fixture expone su verdad-terreno en runtime/truth_ground.json
     (geometria de referencia de cada control) como canal separado.
  2. El detector evaluado (UI Automation + VisualUIDetectorFusion) detecta
     los controles de la fixture SOLO a partir del arbol de accesibilidad
     de la ventana, sin leer runtime/truth_ground.json.

La parte GUI real lanza UNA sola instancia de la fixture (aplicacion propia,
controlada por la prueba) en el monitor no principal situado mas a la derecha
segun la enumeracion real, la maximiza y cierra solo esa ventana al terminar.
Requiere `JARVIS_TEST_GUI_REAL=1` y Windows. Sin la variable se salta.
Nunca cierra procesos ni ventanas preexistentes del usuario: solo cierra la
ventana de la fixture que esta prueba abrio.
"""

from __future__ import annotations

import atexit
import builtins
import json
import os
import subprocess
import sys
import time
import unittest

from pywinauto import Desktop

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import get_desktop_platform
from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
from src.eyes.detection.visual_ui_detector_fusion import (
    VisualUIDetectorFusion,
    DetectedCandidate,
    SOURCE_UIA,
)
from src.core.ui_element_model import UIElementData

from tests.fixtures.gui_calibration_app.controls import CONTROL_SPECS, CONTROL_BY_ID
from tests.fixtures.gui_calibration_app.truth_ground import (
    TRUTH_GROUND_PATH,
    ACTION_COUNTS_PATH,
    construir_truth_ground,
)

TITULO_FIXTURE = "JARVIS GUI Calibration Fixture"
FIXTURE_RUN = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "fixtures",
        "gui_calibration_app", "run.py",
    )
)
IDS_ESPERADOS = [item["id"] for item in CONTROL_SPECS]

GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "_gui_ground_truth_lock.lock")


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


def _leer_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _elem_a_candidato(elem, window_handle, process_id):
    """Convierte un UIAutomationElement en un DetectedCandidate (fuente UIA)."""
    x1, y1, x2, y2 = [float(v) for v in elem.bounding_rectangle]
    centro = [int(round((x1 + x2) / 2.0)), int(round((y1 + y2) / 2.0))]
    element = UIElementData(
        name=(elem.automation_id or elem.name or "element"),
        type=elem.control_type,
        text=elem.name,
        description="",
        bbox=[int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
        center=centro,
        screen=0,
        interactive=bool(elem.is_enabled and elem.visible and not elem.is_offscreen),
        confidence=0.9,
        calibrated=False,
        calibration_data={
            "source": SOURCE_UIA,
            "automation_id": elem.automation_id,
            "control_type": elem.control_type,
        },
    )
    return DetectedCandidate(
        source=SOURCE_UIA,
        element=element,
        confidence=0.9,
        bbox=[int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
        center=centro,
        screen=0,
        window_handle=window_handle,
        process_id=process_id,
        raw={
            "automation_id": elem.automation_id,
            "name": elem.name,
            "control_type": elem.control_type,
            "patterns": list(elem.patterns),
            "is_enabled": bool(elem.is_enabled),
            "visible": bool(elem.visible),
            "is_offscreen": bool(elem.is_offscreen),
            "handle": int(elem.handle),
        },
    )


# ---------------------------------------------------------------------------
# Prueba fuera de pantalla: la verdad-terreno expuesta es correcta
# ---------------------------------------------------------------------------


class TestVerdadTerrenoEstructura(unittest.TestCase):
    """Verifica que construir_truth_ground() refleja CONTROL_SPECS sin GUI."""

    def test_estructura_coincide_con_controles(self):
        verdad = construir_truth_ground().a_dict()
        self.assertEqual(verdad["tamanio_ventana"], [1200, 800])
        ids = [c["id"] for c in verdad["controles"]]
        for id_ in IDS_ESPERADOS:
            self.assertIn(id_, ids, "Falta el control %s en la verdad-terreno" % id_)
        for c in verdad["controles"]:
            for clave in ("id", "kind", "label", "geometry", "action"):
                self.assertIn(clave, c, "Falta la clave %s en %s" % (clave, c.get("id")))
            self.assertIsInstance(c["geometry"], list)
            self.assertEqual(len(c["geometry"]), 4)
        self.assertIn("canvas_mano", verdad["controles_sin_accesibilidad"])


# ---------------------------------------------------------------------------
# Prueba GUI real: detector no consume la verdad-terreno
# ---------------------------------------------------------------------------


class TestDetectorNoConsumeVerdadTerrenoReal(unittest.TestCase):
    """Verifica la fixture en el equipo real y la no-consumicion del detector."""

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest(
                "Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar esta prueba GUI real"
            )
        if _gui_lock_activo():
            raise unittest.SkipTest(
                "Otra clase de tests GUI esta ejecutandose. Esperar a que termine."
            )
        _adquirir_gui_lock()
        cls.proc = None
        cls.hwnd = None
        cls.monitor_id = None
        cls.adapter = None
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

        cls.adapter = get_desktop_platform()
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

    def test_canal_separado_verdad_terreno_escrito(self):
        """La fixture escribio runtime/truth_ground.json con los 16 controles."""
        self.assertTrue(os.path.exists(TRUTH_GROUND_PATH),
                        "truth_ground.json no existe tras lanzar la fixture")
        datos = _leer_json(TRUTH_GROUND_PATH)
        self.assertEqual(datos["tamanio_ventana"], [1200, 800])
        ids = [c["id"] for c in datos["controles"]]
        for id_ in IDS_ESPERADOS:
            self.assertIn(id_, ids,
                          "El control %s no esta en truth_ground.json" % id_)
        for c in datos["controles"]:
            for clave in ("id", "kind", "label", "geometry", "action"):
                self.assertIn(clave, c, "Falta %s en el control %s" % (clave, c.get("id")))
        self.assertIn("canvas_mano", datos["controles_sin_accesibilidad"])
        self.assertTrue(os.path.exists(ACTION_COUNTS_PATH),
                        "action_counts.json no existe (canal separado de acciones)")

    def test_detector_no_consume_truth_ground(self):
        """El detector encuentra los controles por UIA sin abrir truth_ground.json."""
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd)
        self.assertIsNone(tree.error, "Error enumerando: %s" % tree.error)
        self.assertGreaterEqual(tree.element_count, 1)

        candidatos = []
        for elem in tree.elements:
            candidatos.append(_elem_a_candidato(elem, tree.window_handle, tree.process_id))

        # Bloquear la apertura de truth_ground.json SOLO durante la fusion:
        # si el detector lo necesitara, fallaria aqui.
        original_open = builtins.open
        verdad_abierta = []

        def open_bloqueada(path, *args, **kwargs):
            if os.path.abspath(path) == os.path.abspath(TRUTH_GROUND_PATH):
                verdad_abierta.append(path)
                raise AssertionError(
                    "El detector intento leer truth_ground.json: %s" % path
                )
            return original_open(path, *args, **kwargs)

        fusion = VisualUIDetectorFusion()
        builtins.open = open_bloqueada
        try:
            resultado = fusion.fuse(
                candidatos, window_handle=tree.window_handle,
                process_id=tree.process_id, screen=0,
            )
        finally:
            builtins.open = original_open

        self.assertIsNone(resultado.error, "Error de fusion: %s" % resultado.error)
        self.assertEqual(len(verdad_abierta), 0,
                         "El detector no debe consumir truth_ground.json")
        self.assertIn(SOURCE_UIA, resultado.sources_used)
        nombres = set(fc.name for fc in resultado.candidates)

        def _tiene_id(id_):
            return any(n == id_ or n.endswith("." + id_) for n in nombres)

        # Los controles de nivel superior separados se detectan por UIA.
        for id_ in ("btn_aceptar", "btn_cancelar", "lbl_estado", "lnk_ayuda"):
            self.assertTrue(_tiene_id(id_),
                            "El control %s no fue detectado por UIA" % id_)
        # canvas_mano (dibujo a mano sin accesibilidad) se detecta como control
        # generico pero sin nombre semantico en el arbol UIA: confirma que es
        # el control sin accesibilidad de la verdad-terreno.
        encontrado_canvas = False
        for fc in resultado.candidates:
            if fc.name == "canvas_mano" or fc.name.endswith(".canvas_mano"):
                encontrado_canvas = True
                uia_raw = {}
                for ev in fc.sources:
                    if ev.source == SOURCE_UIA and ev.raw:
                        uia_raw = ev.raw
                        break
                self.assertEqual(uia_raw.get("name", ""), "",
                                 "canvas_mano no debe exponer nombre semantico en UIA")
                break
        self.assertTrue(encontrado_canvas, "canvas_mano no fue detectado por UIA")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_fixture_propietaria()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor_id = None
            cls.adapter = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_fixture_propietaria(cls):
        if cls.hwnd is not None and cls.adapter is not None:
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
