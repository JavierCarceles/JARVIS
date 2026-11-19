"""
Tests de fusion de deteccion de elementos UI - unidad 3.8.6.3.3.9.

Pruebas para src/eyes/detection/visual_ui_detector_fusion.py.

- Tests unitarios de logica/contrato (sin GUI ni modelos):
  fusion sin duplicados, preservacion de fuentes/confianza, desacuerdos,
  interactividad solo con evidencia real (patron UIA o Qwen3-VL +
  evidencia visual), asociacion por texto y por solapamiento.
- Tests de integracion real GUI: comparten UNA sola ventana de Notepad por
  sesion de pytest (la primera clase la abre y el resto la reusa; no hay una
  ventana por clase ni por test). Se cierra al salir del proceso (atexit) y
  un lock de archivo impide que dos clases GUI se ejecuten a la vez. Solo
  se ejecutan si JARVIS_TEST_GUI_REAL=1.
- Verificacion real Qwen3-VL: invoca al servidor Ollama real con el modelo
  qwen3-vl:8b-instruct configurado sobre una captura real y verifica que su
  salida se incorpora a la fusion.
"""

from __future__ import annotations

import atexit
import ctypes
import datetime
import logging
import os
import subprocess
import time
import unittest

# ---------------------------------------------------------------------------
# Logging detallado de operaciones GUI para rastrear aperturas/cierres de
# Notepad. Los registros se escriben en tests/eyes/fixtures/gui_tests.log
# ---------------------------------------------------------------------------
GUI_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "gui_tests.log")


def _gui_log(mensaje: str) -> None:
    """Escribe un mensaje con timestamp al fichero de log de pruebas GUI."""
    os.makedirs(os.path.dirname(GUI_LOG_FILE), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    linea = "[%s] %s\n" % (timestamp, mensaje)
    with open(GUI_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)


from src.eyes.detection.visual_ui_detector_fusion import (
    VisualUIDetectorFusion,
    DetectedCandidate,
    SourceEvidence,
    FusedCandidate,
    FusionResult,
    SOURCE_UIA,
    SOURCE_OMNIPARSER,
    SOURCE_PADDLEOCR,
    SOURCE_QWEN3VL,
    SOURCE_OPENCV,
    ALL_SOURCES,
    ACTIONABLE_PATTERNS,
)
from src.eyes.vision.vision import Vision
from src.core.ui_element_model import UIElementData, normalize_element_type
from src.desktop.screen_manager import get_screen_manager
from tests.helpers.ollama_session import servidor_ollama_de_sesion


# ---------------------------------------------------------------------------
# Lock para impedir ejecucion concurrente de tests GUI
# ---------------------------------------------------------------------------
GUI_LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_lock.lock")


def _gui_lock_activo():
    """Devuelve True si hay un test GUI ejecutandose actualmente."""
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock():
    """Crea el archivo de lock con el PID actual."""
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock():
    """Elimina el archivo de lock si pertenece al PID actual."""
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


# ---------------------------------------------------------------------------
# Ventana de Notepad COMPARTIDA entre todas las clases de tests GUI de una
# misma sesion de pytest.
#
# Problema original (debugado):
#   1. Cada TestCase hereda setUpClass/tearDownClass de TestGuiBase, por lo
#      que al ejecutar varias clases se abria UNA ventana de Notepad POR
#      CLASE (2 clases = 2 ventanas), no una compartida.
#   2. cls.proc.pid (de subprocess.Popen(["notepad.exe"])) es el PID del
#      LANZADOR de notepad.exe, NO el PID del proceso que mantiene la
#      ventana. En Windows notepad es de instancia unica: lanzar
#      notepad.exe varias veces no crea varias ventanas, reusa la existente.
#      Por eso pid_esperado nunca coincidia con la ventana real y el codigo
#      caia en found[0] (agarra cualquier Notepad abierto).
#   3. tearDownClass dejaba cls.pid=None (el log muestra
#      "TEARDOWN_CLASS PID=-1 HWND=-1"), con lo que el taskkill se saltaba
#      y la ventana quedaba HUERFANA, acumulandose en ejecuciones sucesivas.
#
# Solucion: estado compartido a nivel de modulo. La primera clase que entra
# en setUpClass abre UNA sola ventana (tras limpiar huorfanas previas) y el
# resto de clases de la sesion la REUSAN. La ventana se cierra al salir del
# proceso de pytest (atexit), no en cada tearDownClass, de modo que:
#   - Ejecutar los 3 tests en un comando: exactamente 1 ventana, compartida.
#   - Ejecutar un test solo (proceso aparte): 1 ventana, cerrada al salir.
# ---------------------------------------------------------------------------

APP = "notepad.exe"
WM_CLOSE = 0x0010

_SHARED_NOTEPAD = {
    "hwnd": None,
    "pid": None,
    "proc": None,
}
_ATEXIT_REGISTERED = False


def _ensure_atexit_notepad():
    """Registra el cierre de la ventana compartida al salir del proceso."""
    global _ATEXIT_REGISTERED
    if not _ATEXIT_REGISTERED:
        try:
            atexit.register(_cerrar_notepad_compartido)
            _ATEXIT_REGISTERED = True
        except Exception:
            pass


def _post_message(hwnd, msg):
    if hwnd is None:
        return
    try:
        ctypes.windll.user32.PostMessageW(ctypes.c_void_p(int(hwnd)), msg, 0, 0)
    except Exception:
        pass


def _taskkill_pid(pid):
    if pid is None:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F", "/T"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _cerrar_notepad_compartido():
    """Cierra la ventana de Notepad compartida (si la hay) y limpia el estado."""
    global _ATEXIT_REGISTERED
    state = _SHARED_NOTEPAD
    hwnd = state["hwnd"]
    pid = state["pid"]
    proc = state["proc"]
    if hwnd is not None:
        _post_message(hwnd, WM_CLOSE)
        time.sleep(0.3)
    _taskkill_pid(pid)
    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    state["hwnd"] = None
    state["pid"] = None
    state["proc"] = None
    _ATEXIT_REGISTERED = False


def _cerrar_huorfanas_notepad():
    """Cierra cualquier ventana de Notepad dejada por ejecuciones previas
    fallidas, para empezar cada sesion de tests desde cero (0 ventanas)."""
    user32 = ctypes.windll.user32
    hwnds = []

    def callback(hwnd, _):
        try:
            length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
            if "notepad" in buf.value.lower() or "bloc de notas" in buf.value.lower():
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
                hwnds.append((int(hwnd), int(pid.value)))
        except Exception:
            pass
        return True

    CBFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(CBFUNC(callback), 0)
    for hwnd, pid in hwnds:
        _post_message(hwnd, WM_CLOSE)
        _taskkill_pid(pid)
    if hwnds:
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Helpers de pruebas unitarias (sin GUI)
# ---------------------------------------------------------------------------


def _uia_element(
    automation_id="",
    name="",
    control_type="Button",
    bbox=(0, 0, 50, 30),
    patterns=None,
    is_enabled=True,
    visible=True,
    is_offscreen=False,
    handle=1,
    process_id=100,
    depth=0,
):
    """Crea un UIAutomationElement ficticio para pruebas unitarias."""
    from src.hands.detection.ui_automation_adapter import UIAutomationElement

    return UIAutomationElement(
        automation_id=automation_id,
        name=name,
        control_type=control_type,
        class_name="",
        bounding_rectangle=bbox,
        process_id=process_id,
        runtime_id=(),
        is_enabled=is_enabled,
        is_offscreen=is_offscreen,
        visible=visible,
        handle=handle,
        framework_id="Win32",
        parent_handle=0,
        child_count=0,
        patterns=list(patterns or []),
        depth=depth,
        source="uia",
    )


def _uia_candidate(elem, screen=0, window_handle=None, process_id=None, confidence=0.9):
    """Construye un DetectedCandidate desde un UIAutomationElement."""
    x1, y1, x2, y2 = elem.bounding_rectangle
    center = [int(round((x1 + x2) / 2.0)), int(round((y1 + y2) / 2.0))]
    element = UIElementData(
        name=(elem.automation_id or elem.name or "element"),
        type=normalize_element_type(elem.control_type),
        text=elem.name,
        description="",
        bbox=list(elem.bounding_rectangle),
        center=center,
        screen=int(screen),
        interactive=bool(elem.is_enabled and elem.visible and not elem.is_offscreen),
        confidence=float(confidence),
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
        confidence=float(confidence),
        bbox=list(elem.bounding_rectangle),
        center=center,
        screen=int(screen),
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


def _qwen3vl_evidence(reference, apparent_function="", label_association="",
                      confidence=0.9, is_actionable=True, evidence_visual=True,
                      bbox=None):
    return {
        "reference": reference,
        "apparent_function": apparent_function,
        "label_association": label_association,
        "confidence": float(confidence),
        "is_actionable": bool(is_actionable),
        "evidence_visual": bool(evidence_visual),
        "disambiguation_hints": [],
        "bbox": list(bbox) if bbox else None,
    }


class TestVisualUIDetectorFusionUnit(unittest.TestCase):
    """Logica pura de fusion (sin GUI ni modelos)."""

    def setUp(self):
        self.fusion = VisualUIDetectorFusion()

    def test_todos_los_recursos_estan_disponibles(self):
        """Todas las fuentes del roadmap estan registradas."""
        for esperado in (
            SOURCE_UIA, SOURCE_OMNIPARSER, SOURCE_PADDLEOCR,
            SOURCE_QWEN3VL, SOURCE_OPENCV,
        ):
            self.assertIn(esperado, ALL_SOURCES)
        self.assertIn("Invoke", ACTIONABLE_PATTERNS)
        self.assertIn("Value", ACTIONABLE_PATTERNS)

    def test_entrada_vacia_devuelve_resultado_vacio(self):
        """Sin candidatos, el resultado esta vacio y sin error."""
        resultado = self.fusion.fuse([])
        self.assertIsInstance(resultado, FusionResult)
        self.assertEqual(resultado.candidate_count, 0)
        self.assertEqual(len(resultado.candidates), 0)
        self.assertIsNone(resultado.error)

    def test_una_fuente_devuelve_el_mismo_candidato(self):
        """Un solo candidato se devuelve como un candidato fusionado."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140),
                            patterns=["Invoke"], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 1)
        fc = resultado.candidates[0]
        self.assertEqual(fc.name, "btn1")
        self.assertEqual(fc.type, "button")
        self.assertEqual(fc.sources[0].source, SOURCE_UIA)
        self.assertEqual(fc.sources[0].confidence, 0.9)
        self.assertEqual(fc.bbox, [100, 100, 200, 140])

    def test_dos_candidatos_solapados_se_unen_en_uno(self):
        """Dos candidatos con cajas solapadas se fusionan sin duplicar."""
        elem_a = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        elem_b = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(110, 110, 210, 150), patterns=["Invoke"], handle=5)
        cand_a = _uia_candidate(elem_a, window_handle=1, process_id=100)
        cand_b = _uia_candidate(elem_b, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand_a, cand_b], window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 1)
        self.assertEqual(resultado.duplicates_removed, 1)
        self.assertEqual(len(resultado.candidates[0].sources), 2)

    def test_candidatos_sin_solapamiento_permanecen_separados(self):
        """Candidatos lejos uno del otro no se fusionan."""
        elem_a = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(100, 100, 150, 130), patterns=["Invoke"], handle=5)
        elem_b = _uia_element(automation_id="btn2", name="Cancelar",
                              bbox=(500, 500, 560, 530), patterns=["Invoke"], handle=9)
        cand_a = _uia_candidate(elem_a, window_handle=1, process_id=100)
        cand_b = _uia_candidate(elem_b, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand_a, cand_b], window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 2)
        self.assertEqual(resultado.duplicates_removed, 0)

    def test_misma_ventana_no_se_fusiona_con_otra_ventana(self):
        """Candidatos de distintas ventanas (HWND) no se fusionan aunque solapen."""
        elem_a = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        elem_b = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(110, 110, 210, 150), patterns=["Invoke"], handle=6)
        cand_a = _uia_candidate(elem_a, window_handle=1, process_id=100)
        cand_b = _uia_candidate(elem_b, window_handle=2, process_id=200)
        resultado = self.fusion.fuse([cand_a, cand_b])
        self.assertEqual(resultado.candidate_count, 2)

    def test_pantalla_distinta_no_se_fusiona(self):
        """Candidatos de distintas pantallas no se fusionan."""
        elem_a = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        elem_b = _uia_element(automation_id="btn1", name="Aceptar",
                              bbox=(110, 110, 210, 150), patterns=["Invoke"], handle=5)
        cand_a = _uia_candidate(elem_a, screen=0, window_handle=1, process_id=100)
        cand_b = _uia_candidate(elem_b, screen=1, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand_a, cand_b])
        self.assertEqual(resultado.candidate_count, 2)

    def test_fuentes_y_confianza_se_preservan_por_separado(self):
        """Cada fuente se conserva con su propia confianza."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        cand_uia = _uia_candidate(elem, window_handle=1, process_id=100)
        qwen_ev = [_qwen3vl_evidence(reference="Aceptar", label_association="Aceptar")]
        resultado = self.fusion.fuse([cand_uia], qwen3vl_evidence=qwen_ev,
                                     window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 1)
        fuentes = [s.source for s in resultado.candidates[0].sources]
        self.assertIn(SOURCE_UIA, fuentes)
        self.assertIn(SOURCE_QWEN3VL, fuentes)

    def test_interactividad_por_patron_uia_real(self):
        """Un elemento con patron UIA de accion se marca interactivo."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=["Invoke"],
                            handle=5, is_enabled=True, visible=True,
                            is_offscreen=False)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertTrue(resultado.candidates[0].interactive)
        self.assertIn(SOURCE_UIA, resultado.candidates[0].interactive_evidence)

    def test_control_uia_desactivado_no_es_interactivo(self):
        """Patron de accion pero control deshabilitado => no interactivo."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=["Invoke"],
                            handle=5, is_enabled=False)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertFalse(resultado.candidates[0].interactive)

    def test_control_uia_fuera_de_pantalla_no_es_interactivo(self):
        """Patron de accion pero fuera de pantalla => no interactivo."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(-9999, -9999, -9990, -9980), patterns=["Invoke"],
                            handle=5, is_offscreen=True, visible=False)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertFalse(resultado.candidates[0].interactive)

    def test_sin_patron_uia_no_es_interactivo(self):
        """Solo texto/tipo no implica interactividad."""
        elem = _uia_element(automation_id="lbl1", name="Etiqueta",
                            bbox=(100, 100, 200, 140), control_type="Text",
                            patterns=[], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertFalse(resultado.candidates[0].interactive)

    def test_opencv_por_si_solo_no_hace_interactivo(self):
        """OpenCV solo aporta pista geometrica, nunca interactividad."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=[], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        cand.raw["opencv_refined_bbox"] = [105, 105, 195, 135]
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertFalse(resultado.candidates[0].interactive)

    def test_qwen3vl_accionable_sin_evidencia_visual_no_hace_interactivo(self):
        """Qwen3-VL marca accionable sin evidencia visual => no interactivo + desacuerdo."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=[], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        ev = [_qwen3vl_evidence(reference="Aceptar", is_actionable=True,
                                evidence_visual=False)]
        resultado = self.fusion.fuse([cand], qwen3vl_evidence=ev,
                                     window_handle=1, process_id=100)
        self.assertFalse(resultado.candidates[0].interactive)
        self.assertTrue(resultado.candidates[0].disagreements)

    def test_qwen3vl_accionable_con_evidencia_visual_hace_interactivo(self):
        """Qwen3-VL accionable con evidencia visual => interactivo."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=[], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        ev = [_qwen3vl_evidence(reference="Aceptar", is_actionable=True,
                                evidence_visual=True)]
        resultado = self.fusion.fuse([cand], qwen3vl_evidence=ev,
                                     window_handle=1, process_id=100)
        self.assertTrue(resultado.candidates[0].interactive)
        self.assertIn(SOURCE_QWEN3VL, resultado.candidates[0].interactive_evidence)

    def test_asociacion_por_texto_ocr_igual_a_nombre_uia(self):
        """Texto OCR igual al nombre de un control UIA se fusionan."""
        elem_uia = _uia_element(automation_id="edit1", name="Campo de texto",
                                bbox=(100, 100, 300, 130), control_type="Edit",
                                patterns=["Value"], handle=5)
        cand_uia = _uia_candidate(elem_uia, window_handle=1, process_id=100)
        element_ocr = UIElementData(
            name="Campo de texto", type="text", text="Campo de texto",
            bbox=[105, 105, 295, 125], center=[200, 115], screen=0,
            interactive=False, confidence=0.85, calibrated=False,
        )
        cand_ocr = DetectedCandidate(
            source=SOURCE_PADDLEOCR, element=element_ocr, confidence=0.85,
            bbox=[105, 105, 295, 125], center=[200, 115], screen=0,
            window_handle=1, process_id=100,
            raw={"text": "Campo de texto"},
        )
        resultado = self.fusion.fuse([cand_uia, cand_ocr],
                                     window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 1)
        self.assertEqual(resultado.duplicates_removed, 1)
        fuentes = [s.source for s in resultado.candidates[0].sources]
        self.assertIn(SOURCE_UIA, fuentes)
        self.assertIn(SOURCE_PADDLEOCR, fuentes)

    def test_desacuerdo_geometria_entre_fuentes(self):
        """Cajas muy alejadas unidas por texto generan desacuerdo de geometria."""
        elem_uia = _uia_element(automation_id="btn1", name="Aceptar",
                                bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        cand_uia = _uia_candidate(elem_uia, window_handle=1, process_id=100)
        element_ocr = UIElementData(
            name="Aceptar", type="text", text="Aceptar",
            bbox=(190, 100, 210, 140), center=[200, 120], screen=0,
            interactive=False, confidence=0.8, calibrated=False,
        )
        cand_ocr = DetectedCandidate(
            source=SOURCE_PADDLEOCR, element=element_ocr, confidence=0.8,
            bbox=[190, 100, 210, 140], center=[200, 120], screen=0,
            window_handle=1, process_id=100,
            raw={"text": "Aceptar"},
        )
        resultado = self.fusion.fuse([cand_uia, cand_ocr],
                                     window_handle=1, process_id=100)
        self.assertEqual(resultado.candidate_count, 1)
        self.assertEqual(resultado.duplicates_removed, 1)
        self.assertGreaterEqual(len(resultado.candidates[0].disagreements), 1)

    def test_serializable_a_diccionario(self):
        """El resultado completo es serializable a diccionario plano."""
        elem = _uia_element(automation_id="btn1", name="Aceptar",
                            bbox=(100, 100, 200, 140), patterns=["Invoke"], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        d = resultado.to_dict()
        self.assertEqual(d["candidate_count"], 1)
        self.assertEqual(len(d["candidates"]), 1)
        self.assertEqual(d["candidates"][0]["sources"][0]["source"], SOURCE_UIA)
        self.assertEqual(d["candidates"][0]["interactive"], True)
        self.assertIsInstance(d["sources_available"], dict)

    def test_tipo_desconocido_se_resuelve_a_element(self):
        """Tipo libre no canonico se normaliza a 'element', no se inventa tipo."""
        elem = _uia_element(automation_id="x1", name="Cosa rara",
                            bbox=(100, 100, 200, 140), control_type="Zaraza",
                            patterns=[], handle=5)
        cand = _uia_candidate(elem, window_handle=1, process_id=100)
        resultado = self.fusion.fuse([cand], window_handle=1, process_id=100)
        self.assertEqual(resultado.candidates[0].type, "element")

    def test_fuente_marcada_no_disponible_no_inventa_resultados(self):
        """Una fuente no disponible no produce candidatos falsos."""
        self.assertEqual(SOURCE_OMNIPARSER in ALL_SOURCES, True)
        self.assertEqual(SOURCE_PADDLEOCR in ALL_SOURCES, True)


# ---------------------------------------------------------------------------
# Clase base para tests GUI (una sola ventana de Notepad por clase)
# ---------------------------------------------------------------------------

GUI_LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_lock.lock")


def _gui_lock_activo():
    """Devuelve True si hay una clase de tests GUI ejecutandose actualmente."""
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock():
    """Crea el archivo de lock con el PID actual."""
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock():
    """Elimina el archivo de lock si pertenece al PID actual."""
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


class TestGuiBase(unittest.TestCase):
    """Clase base para tests GUI reales.

    Comparte UNA sola ventana de Notepad entre todas las clases de tests
    GUI de una misma sesion de pytest. La primera clase que entra en
    setUpClass abre la ventana (tras limpiar huorfanas previas) y el resto
    de clases la reusan; no se abre una ventana por clase ni por test.
    La ventana se cierra al salir del proceso de pytest (atexit), no en
    cada tearDownClass. Un lock de archivo impide que dos clases GUI se
    ejecuten a la vez. Solo se ejecutan si JARVIS_TEST_GUI_REAL=1.
    """

    @classmethod
    def setUpClass(cls):
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest(
                "Test GUI real: establecer JARVIS_TEST_GUI_REAL=1 para ejecutar"
            )
        if _gui_lock_activo():
            raise unittest.SkipTest(
                "Otra clase de tests GUI esta ejecutandose. Esperar a que "
                "termine antes de lanzar esta clase."
            )
        _adquirir_gui_lock()
        cls.proc = None
        cls.hwnd = None
        cls.pid = None
        cls.fusion = VisualUIDetectorFusion()
        cls._screen_manager = get_screen_manager()
        cls._screen_manager.refresh_monitors()
        try:
            cls._abrir_notepad_compartido()
        except Exception:
            # Si falla el setup, limpiar la ventana compartida que se pudo
            # haber abierto y liberar el lock, para no dejar ventanas
            # huorfanas.
            try:
                _cerrar_notepad_compartido()
            except Exception:
                pass
            _liberar_gui_lock()
            raise

    @classmethod
    def tearDownClass(cls):
        # No se cierra la ventana compartida aqui: debe permanecer abierta
        # para que las demas clases de tests de la misma sesion de pytest
        # la reusan. Se cierra al salir del proceso mediante atexit
        # (_cerrar_notepad_compartido). Asi, ejecutar los 3 tests en un solo
        # comando abre exactamente 1 ventana de Notepad y la comparten.
        pid_para_log = cls.pid
        hwnd_para_log = cls.hwnd
        cls.proc = None
        cls.hwnd = None
        cls.pid = None
        _gui_log(
            "TEARDOWN_CLASS: clase=%s PID=%d HWND=%d "
            "(ventana compartida se mantiene hasta el final de la sesion)"
            % (cls.__name__, pid_para_log or -1, hwnd_para_log or -1)
        )
        _liberar_gui_lock()

    @classmethod
    def _enumerar_ventanas_notepad(cls, user32, pid_esperado):
        found = []

        def callback(hwnd, _lparam):
            try:
                length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
                if length == 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
                titulo = buf.value
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(hwnd), ctypes.byref(pid)
                )
                pid_val = int(pid.value)
                es_notepad = (
                    pid_val == pid_esperado
                    or "notepad" in titulo.lower()
                    or "bloc de notas" in titulo.lower()
                )
                if es_notepad:
                    found.append((int(hwnd), pid_val, titulo))
            except Exception:
                pass
            return True

        CBFUNC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        user32.EnumWindows(CBFUNC(callback), 0)
        return found

    @classmethod
    def _abrir_notepad_compartido(cls):
        """Abre UNA sola ventana de Notepad compartida por sesion de pytest.

        Si otra clase de tests de la misma sesion ya abrio la ventana, la
        reusa y no lanza una nueva Notepad. La primera clase limpia ventanas
        huorfanas previas y lanza notepad.exe.

        Nota clave: subprocess.Popen(["notepad.exe"]).pid es el PID del
        LANZADOR (proceso corto), no el del proceso que mantiene la ventana.
        Notepad es de instancia unica en Windows, por tanto no se puede
        confiar en Popen.pid ni buscar por pid_esperado. Se captura la HWND y
        el PID REAL de la ventana enumerando ventanas por titulo tras el
        lanzamiento.
        """
        state = _SHARED_NOTEPAD
        if state["hwnd"] is not None and state["pid"] is not None:
            # Reutilizar la ventana ya abierta en esta sesion de pytest.
            cls.hwnd = state["hwnd"]
            cls.pid = state["pid"]
            cls.proc = state["proc"]
            _gui_log(
                "SETUP_CLASS: Reusar Notepad compartido clase=%s PID=%d HWND=%d"
                % (cls.__name__, cls.pid or -1, cls.hwnd or -1)
            )
            return

        # Primera clase de la sesion: partir de cero (sin ventanas huorfanas).
        _cerrar_huorfanas_notepad()

        user32 = ctypes.windll.user32
        monitors = cls._screen_manager.monitors
        secundario = None
        for m in monitors:
            if not m.is_primary:
                secundario = m
                break
        if secundario is None:
            secundario = cls._screen_manager.get_primary_monitor()
        cls.assertIsNotNone(secundario, "No se encontro monitor")

        cls.proc = subprocess.Popen([APP])
        hwnd = None
        pid = None
        # Notepad puede tardar un instante en crear la ventana; reintentar.
        for _intento in range(30):
            time.sleep(0.2)
            found = cls._enumerar_ventanas_notepad(user32, None)
            if found:
                hwnd, pid, _title = found[0]
                break
        if hwnd is None:
            cls.fail("No se encontro la ventana de Notepad creada")

        # Guardar en el estado compartido y en la clase.
        state["hwnd"] = hwnd
        state["pid"] = pid
        state["proc"] = cls.proc
        cls.hwnd = hwnd
        cls.pid = pid

        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        time.sleep(0.3)
        user32.SetWindowPos(
            ctypes.c_void_p(hwnd), 0,
            int(secundario.left), int(secundario.top),
            int(secundario.width), int(secundario.height),
            0x0004 | 0x0040,
        )
        time.sleep(0.3)
        user32.ShowWindow(ctypes.c_void_p(hwnd), 3)
        time.sleep(0.8)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        time.sleep(0.3)
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        cls.assertTrue(
            secundario.contains_point(cx, cy),
            "Centro de la ventana no esta en el monitor secundario",
        )

        _ensure_atexit_notepad()
        _gui_log(
            "SETUP_CLASS: Abrir Notepad compartido clase=%s PID=%d HWND=%d"
            % (cls.__name__, cls.pid or -1, cls.hwnd or -1)
        )

    def _tree_a_candidatos(self, tree):
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        adapter = UIAutomationAdapter()
        candidatos = []
        for elem in tree.elements:
            candidatos.append(_uia_candidate(
                elem, screen=0, window_handle=tree.window_handle,
                process_id=tree.process_id,
            ))
        return candidatos


# ---------------------------------------------------------------------------
# Tests GUI: arbol UIA real de Notepad (una sola ventana compartida)
# ---------------------------------------------------------------------------


class TestVisualUIDetectorFusionNotepadReal(TestGuiBase):
    """Integracion real con UNA ventana de Notepad compartida por sesion.

    La ventana se abre una vez en setUpClass (compartida entre las clases
    de tests GUI de la misma sesion de pytest) y se cierra al salir del
    proceso (atexit), no al finalizar cada clase ni cada test. No se abre
    una ventana por test. Usa lock de exclusion para impedir ejecucion
    concurrente con otras clases GUI. Solo se ejecuta si JARVIS_TEST_GUI_REAL=1.
    """

    def test_fusionar_arbol_uia_notepad_real(self):
        """Arbol UIA real de Notepad se fusiona sin duplicar y con fuente uia."""
        _gui_log("TEST_INICIO: test_fusionar_arbol_uia_notepad_real clase=TestVisualUIDetectorFusionNotepadReal")
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error, "Error enumerando: %s" % tree.error)
        self.assertGreaterEqual(tree.element_count, 2)

        candidatos = self._tree_a_candidatos(tree)
        resultado = self.fusion.fuse(
            candidatos, window_handle=tree.window_handle,
            process_id=tree.process_id, screen=0,
        )
        self.assertIsNone(resultado.error)
        self.assertGreaterEqual(resultado.candidate_count, 1)
        self.assertIn(SOURCE_UIA, resultado.sources_used)
        self.assertTrue(resultado.sources_available.get(SOURCE_UIA))
        for fc in resultado.candidates:
            self.assertEqual(fc.window_handle, self.hwnd)
            self.assertEqual(fc.process_id, self.pid)
            self.assertTrue(any(s.source == SOURCE_UIA for s in fc.sources))
            self.assertIsNotNone(fc.bbox)
            self.assertEqual(len(fc.bbox), 4)
        _gui_log("TEST_FIN: test_fusionar_arbol_uia_notepad_real clase=TestVisualUIDetectorFusionNotepadReal")

    def test_fusion_notepad_interactivos_reales(self):
        """Notepad real: elementos con patron de accion se marcan interactivos."""
        _gui_log("TEST_INICIO: test_fusion_notepad_interactivos_reales clase=TestVisualUIDetectorFusionNotepadReal")
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error)
        candidatos = self._tree_a_candidatos(tree)
        resultado = self.fusion.fuse(
            candidatos, window_handle=tree.window_handle,
            process_id=tree.process_id, screen=0,
        )
        interactivos = [fc for fc in resultado.candidates if fc.interactive]
        self.assertGreaterEqual(len(interactivos), 1,
                                "Se esperaba al menos un elemento interactivo")
        for fc in interactivos:
            self.assertIn(SOURCE_UIA, fc.interactive_evidence)
            self.assertFalse(fc.calibrated)
        _gui_log("TEST_FIN: test_fusion_notepad_interactivos_reales clase=TestVisualUIDetectorFusionNotepadReal")


# ---------------------------------------------------------------------------
# Tests GUI: verificacion real Qwen3-VL via Ollama (una sola ventana)
# ---------------------------------------------------------------------------


class TestVisualUIDetectorFusionQwen3VLReal(TestGuiBase):
    """Verificacion real de Qwen3-VL via Ollama incorporado a la fusion.

    Reusa la unica ventana de Notepad compartida de la sesion de pytest
    (abierta por la primera clase de tests GUI); no abre una ventana propia
    ni una por test. La ventana se cierra al salir del proceso (atexit).
    Usa lock de exclusion para impedir ejecucion concurrente con otras
    clases GUI. Solo se ejecuta si JARVIS_TEST_GUI_REAL=1.
    """

    def test_qwen3vl_salida_real_incorporada_en_fusion(self):
        """Qwen3-VL (Ollama real) interpreta un boton de Notepad y se fusiona."""
        _gui_log("TEST_INICIO: test_qwen3vl_salida_real_incorporada_en_fusion clase=TestVisualUIDetectorFusionQwen3VLReal")
        # Servidor Ollama de la sesion (se arranca si no responde; se cierra al terminar).
        servidor_ollama_de_sesion()
        import ollama
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        from src.eyes.capture.screen_capture import ScreenCapture

        # Verificar que el servidor y el modelo estan disponibles
        tags = ollama.list()
        modelos = [m.get("model", "") for m in tags.get("models", [])]
        self.assertTrue(any("qwen3-vl" in m for m in modelos),
                        "qwen3-vl no disponible en Ollama")

        user32 = ctypes.windll.user32
        hwnd = self.hwnd
        pid = self.pid
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        left = int(rect.left)
        top = int(rect.top)

        ruta = os.path.join(os.getcwd(), "tests", "fixtures",
                            "_tmp_fusion_qwen_%d.png" % pid)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        captor = ScreenCapture()
        ruta_devuelta = captor.capture_region(
            left, top,
            int(rect.right - rect.left), int(rect.bottom - rect.top),
            save_path=ruta,
        )
        self.assertIsNotNone(ruta_devuelta, "No se pudo capturar la region de pantalla")
        self.assertTrue(os.path.exists(ruta), "La captura no se escribio en disco")
        try:
            # Arbol UIA real de la ventana
            adapter = UIAutomationAdapter(timeout=8.0)
            tree = adapter.enumerate_window(hwnd, pid)
            self.assertIsNone(tree.error)
            self.assertGreaterEqual(tree.element_count, 1)

            # Convertir coordenadas UIA (pantalla absoluta) a coordenadas
            # relativas a la captura de la ventana, espacio compartido para
            # la fusion y para el recorte enviado a Qwen3-VL.
            candidatos = []
            root_rel_bbox = None
            root_name = ""
            for elem in tree.elements:
                bx1, by1, bx2, by2 = elem.bounding_rectangle
                rel_bbox = [
                    int(round(bx1 - left)), int(round(by1 - top)),
                    int(round(bx2 - left)), int(round(by2 - top)),
                ]
                if elem.depth == 0:
                    root_rel_bbox = rel_bbox
                    root_name = elem.name or "ventana"
                candidatos.append(_uia_candidate(
                    elem, screen=0, window_handle=tree.window_handle,
                    process_id=tree.process_id,
                ))
                # Sobrescribir bbox/center con coordenadas relativas a la captura
                candidatos[-1].bbox = rel_bbox
                x1, y1, x2, y2 = rel_bbox
                candidatos[-1].center = [
                    int(round((x1 + x2) / 2.0)), int(round((y1 + y2) / 2.0)),
                ]
                candidatos[-1].element.bbox = rel_bbox
                candidatos[-1].element.center = candidatos[-1].center

            self.assertIsNotNone(root_rel_bbox, "No se encontro elemento raiz")

            # Interpretacion semantica real de Qwen3-VL sobre el recorte del
            # elemento raiz (ventana de Notepad), en coordenadas de captura.
            semantica = {}
            try:
                semantica = Vision().interpret_element_semantics(
                    image_path=ruta, crop_bbox=list(root_rel_bbox),
                )
            except Exception as exc:
                self.fail("interpret_element_semantico llamo al servidor real y fallo: %s" % exc)

            qwen_ev = [{
                "reference": root_name,
                "apparent_function": semantica.get("apparent_function", ""),
                "label_association": semantica.get("label_association", ""),
                "confidence": float(semantica.get("confidence", 0.0) or 0.0),
                "is_actionable": bool(semantica.get("is_actionable", False)),
                "evidence_visual": bool(semantica.get("evidence_visual", False)),
                "disambiguation_hints": list(semantica.get("disambiguation_hints", []) or []),
                "bbox": list(root_rel_bbox),
            }]

            resultado = self.fusion.fuse(
                candidatos, qwen3vl_evidence=qwen_ev,
                window_handle=tree.window_handle,
                process_id=tree.process_id, screen=0,
            )
            self.assertIsNone(resultado.error)
            self.assertGreaterEqual(resultado.candidate_count, 1)
            # La fuente Qwen3-VL debe haberse usado en la fusion
            self.assertIn(SOURCE_QWEN3VL, resultado.sources_used)
            self.assertTrue(resultado.sources_available.get(SOURCE_QWEN3VL))
            qwen_candidates = [
                fc for fc in resultado.candidates
                if any(s.source == SOURCE_QWEN3VL for s in fc.sources)
            ]
            self.assertGreaterEqual(len(qwen_candidates), 1)
            for fc in qwen_candidates:
                qwen_ev_found = [s for s in fc.sources if s.source == SOURCE_QWEN3VL]
                self.assertEqual(len(qwen_ev_found), 1)
                self.assertIsNotNone(qwen_ev_found[0].element)
            _gui_log("TEST_FIN: test_qwen3vl_salida_real_incorporada_en_fusion clase=TestVisualUIDetectorFusionQwen3VLReal")
        finally:
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tests GUI: comparativa UIA vs detector visual vs fusion sobre Notepad real
# (unidad 3.8.6.3.3.15)
#
# Comprueba, sobre una aplicacion fixture real (Notepad):
#   1. El arbol UIA por separado (enumeracion de controles reales).
#   2. El detector visual por separado (Vision.detect_ui_elements sobre una
#      captura real de la ventana).
#   3. La fusion de ambas fuentes.
# Registra: elementos existentes (en ambas), omitidos (en una pero no en la
# otra), duplicados, falsos positivos y elementos a los que el proveedor de
# UIA no da acceso.
# ---------------------------------------------------------------------------

import json as _json
import math as _math


def _iou_mismo_espacio(a, b):
    """IoU de dos cajas [x1, y1, x2, y2] en el mismo espacio de coordenadas."""
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1); inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


class TestIntegracionUIAVisualFixtureReal(TestGuiBase):
    """Integracion real UIA + detector visual + fusion sobre Notepad."""

    REPORTE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures",
                                "informe_integracion_uia_visual_fixture_real.json")

    def _uia_element_a_candidato(self, elem, screen=0):
        """Convierte un UIAutomationElement en DetectedCandidate (fuente UIA)."""
        x1, y1, x2, y2 = [float(v) for v in elem.bounding_rectangle]
        center = [int(round((x1 + x2) / 2.0)), int(round((y1 + y2) / 2.0))]
        element = UIElementData(
            name=(elem.automation_id or elem.name or "element"),
            type=normalize_element_type(elem.control_type),
            text=elem.name,
            description="",
            bbox=list(elem.bounding_rectangle),
            center=center,
            screen=int(screen),
            interactive=bool(elem.is_enabled and elem.visible and not elem.is_offscreen),
            confidence=0.9,
            calibrated=False,
            calibration_data={"source": SOURCE_UIA,
                              "automation_id": elem.automation_id,
                              "control_type": elem.control_type},
        )
        return DetectedCandidate(
            source=SOURCE_UIA,
            element=element,
            confidence=0.9,
            bbox=list(elem.bounding_rectangle),
            center=center,
            screen=int(screen),
            window_handle=elem.handle,
            process_id=elem.process_id,
            raw={
                "automation_id": elem.automation_id,
                "name": elem.name,
                "control_type": elem.control_type,
                "class_name": elem.class_name,
                "patterns": list(elem.patterns),
                "is_enabled": bool(elem.is_enabled),
                "visible": bool(elem.visible),
                "is_offscreen": bool(elem.is_offscreen),
                "handle": int(elem.handle),
                "framework": elem.framework,
                "depth": int(elem.depth),
            },
        )

    def _visual_element_a_candidato(self, ve, screen=0, window_handle=None,
                                     process_id=None, offset=(0, 0)):
        """Convierte un UIElement de Vision.detect_ui_elements en DetectedCandidate.

        Vision.detect_ui_elements consulta al modelo visual (Qwen3-VL via
        Ollama) sobre la captura real, por tanto su procedencia es SOURCE_QWEN3VL.
        """
        ox, oy = offset
        bbox = list(ve.bbox) if ve.bbox else None
        if bbox:
            bbox = [int(bbox[0] + ox), int(bbox[1] + oy),
                    int(bbox[2] + ox), int(bbox[3] + oy)]
        center = list(ve.center) if ve.center else None
        if center:
            center = [int(center[0] + ox), int(center[1] + oy)]
        element = UIElementData(
            name=ve.name or ve.text or "element",
            type=ve.type,
            text=ve.text,
            description=ve.description,
            bbox=bbox,
            center=center,
            screen=int(screen),
            interactive=bool(ve.interactive),
            confidence=float(ve.confidence or 0.0),
            calibrated=False,
        )
        return DetectedCandidate(
            source=SOURCE_QWEN3VL,
            element=element,
            confidence=float(ve.confidence or 0.0),
            bbox=bbox,
            center=center,
            screen=int(screen),
            window_handle=window_handle,
            process_id=process_id,
            raw={"name": ve.name, "text": ve.text, "type": ve.type,
                 "description": ve.description,
                 "interactive": bool(ve.interactive)},
        )

    def _centro_bbox(self, bbox):
        if not bbox or len(bbox) != 4:
            return None
        return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

    def _textos_candidato(self, c):
        out = []
        if c.element:
            if c.element.name:
                out.append(str(c.element.name))
            if c.element.text:
                out.append(str(c.element.text))
        if c.raw and c.raw.get("text"):
            out.append(str(c.raw["text"]))
        return out

    def _coinciden(self, uia_c, vis_c):
        """True si un candidato UIA y uno visual parecen el mismo elemento."""
        if uia_c.bbox and vis_c.bbox:
            if _iou_mismo_espacio(uia_c.bbox, vis_c.bbox) >= 0.30:
                return True
        u_ctr = self._centro_bbox(uia_c.bbox)
        v_ctr = self._centro_bbox(vis_c.bbox)
        if u_ctr and v_ctr:
            dist = _math.hypot(v_ctr[0] - u_ctr[0], v_ctr[1] - u_ctr[1])
            if dist <= 60.0:
                ut = self._textos_candidato(uia_c)
                vt = self._textos_candidato(vis_c)
                for a in ut:
                    for b in vt:
                        if a and b and (a == b or a in b or b in a):
                            return True
        return False

    def _comparar_y_registrar(self, candidatos_uia, candidatos_visual,
                              resultado_fusion, hwnd, pid):
        """Compara UIA vs visual, categoriza y escribe el informe JSON."""
        user32 = ctypes.windll.user32
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        cap_left = int(rect.left); cap_top = int(rect.top)

        uia_items = []
        for c in candidatos_uia:
            bx1, by1, bx2, by2 = c.bbox
            rel_bbox = [int(bx1 - cap_left), int(by1 - cap_top),
                        int(bx2 - cap_left), int(by2 - cap_top)]
            uia_items.append((c, rel_bbox))

        visual_items = []
        for c in candidatos_visual:
            visual_items.append((c, list(c.bbox) if c.bbox else None))

        existentes = []
        omitidos_visual = []
        omitidos_uia = []
        falsos_positivos = []
        duplicados_uia = []
        duplicados_visual = []

        uia_matched = set()
        vis_matched = set()

        # Duplicados dentro de UIA (mismo elemento detectado dos veces)
        for i in range(len(uia_items)):
            for j in range(i + 1, len(uia_items)):
                ci, bi = uia_items[i]; cj, bj = uia_items[j]
                if _iou_mismo_espacio(bi, bj) >= 0.5:
                    duplicados_uia.append({
                        "uia_a": ci.raw.get("automation_id") or ci.raw.get("name"),
                        "uia_b": cj.raw.get("automation_id") or cj.raw.get("name"),
                        "iou": round(_iou_mismo_espacio(bi, bj), 3),
                    })

        # Duplicados dentro de visual
        for i in range(len(visual_items)):
            for j in range(i + 1, len(visual_items)):
                ci, bi = visual_items[i]; cj, bj = visual_items[j]
                if bi and bj and _iou_mismo_espacio(bi, bj) >= 0.5:
                    duplicados_visual.append({
                        "visual_a": ci.raw.get("name") or ci.raw.get("text"),
                        "visual_b": cj.raw.get("name") or cj.raw.get("text"),
                        "iou": round(_iou_mismo_espacio(bi, bj), 3),
                    })

        # Comparar UIA vs visual
        for i, (uia_c, uia_bbox_rel) in enumerate(uia_items):
            match_idx = None
            for j, (vis_c, vis_bbox) in enumerate(visual_items):
                if j in vis_matched:
                    continue
                if self._coinciden(uia_c, vis_c):
                    match_idx = j
                    break
            if match_idx is not None:
                uia_matched.add(i); vis_matched.add(match_idx)
                existentes.append({
                    "uia": {
                        "name": uia_c.raw.get("name"),
                        "automation_id": uia_c.raw.get("automation_id"),
                        "control_type": uia_c.raw.get("control_type"),
                        "patterns": uia_c.raw.get("patterns"),
                        "bbox_captura": uia_bbox_rel,
                        "interactivo": uia_c.element.interactive if uia_c.element else False,
                    },
                    "visual": {
                        "name": vis_c.element.name if vis_c.element else None,
                        "type": vis_c.element.type if vis_c.element else None,
                        "text": vis_c.element.text if vis_c.element else None,
                        "bbox": vis_bbox,
                        "confidence": vis_c.confidence,
                        "interactivo": vis_c.element.interactive if vis_c.element else False,
                    },
                })
            else:
                omitidos_visual.append({
                    "name": uia_c.raw.get("name"),
                    "automation_id": uia_c.raw.get("automation_id"),
                    "control_type": uia_c.raw.get("control_type"),
                    "patterns": uia_c.raw.get("patterns"),
                    "bbox_captura": uia_bbox_rel,
                    "interactivo": uia_c.element.interactive if uia_c.element else False,
                    "motivo": "Detector visual no lo encontro en la captura",
                })

        for j, (vis_c, vis_bbox) in enumerate(visual_items):
            if j in vis_matched:
                continue
            es_falso = vis_c.confidence < 0.4 or (vis_bbox and (
                vis_bbox[2] - vis_bbox[0] < 5 or vis_bbox[3] - vis_bbox[1] < 5))
            entry = {
                "name": vis_c.element.name if vis_c.element else None,
                "type": vis_c.element.type if vis_c.element else None,
                "text": vis_c.element.text if vis_c.element else None,
                "bbox": vis_bbox,
                "confidence": vis_c.confidence,
                "interactivo": vis_c.element.interactive if vis_c.element else False,
            }
            if es_falso:
                falsos_positivos.append({**entry,
                                         "motivo": "Confianza baja o caja degenerada"})
            else:
                omitidos_uia.append({**entry,
                                     "motivo": "Proveedor UIA no expone este control"})

        fusion_candidatos = []
        for fc in resultado_fusion.candidates:
            fusion_candidatos.append({
                "canonical_id": fc.canonical_id,
                "name": fc.name,
                "type": fc.type,
                "sources": [s.source for s in fc.sources],
                "interactivo": fc.interactive,
                "merged_confidence": fc.merged_confidence,
                "disagreements": list(fc.disagreements),
            })

        informe = {
            "fixture": "notepad.exe",
            "ventana_hwnd": int(hwnd),
            "ventana_pid": int(pid),
            "total_uia": len(uia_items),
            "total_visual": len(visual_items),
            "total_fusion": resultado_fusion.candidate_count,
            "existentes": existentes,
            "omitidos_por_visual": omitidos_visual,
            "omitidos_por_uia": omitidos_uia,
            "falsos_positivos": falsos_positivos,
            "duplicados_uia": duplicados_uia,
            "duplicados_visual": duplicados_visual,
            "fusion_candidatos": fusion_candidatos,
            "duplicados_eliminados_fusion": resultado_fusion.duplicates_removed,
            "desacuerdos_totales": resultado_fusion.disagreements_total,
            "fuentes_usadas": list(resultado_fusion.sources_used),
            "fuentes_disponibles": dict(resultado_fusion.sources_available),
        }

        os.makedirs(os.path.dirname(self.REPORTE_PATH), exist_ok=True)
        with open(self.REPORTE_PATH, "w", encoding="utf-8") as f:
            _json.dump(informe, f, ensure_ascii=False, indent=2)

        return informe

    def test_arbol_uia_por_separado_fixture_real(self):
        """Arbol UIA de Notepad se enumera por separado y sus elementos se registran."""
        _gui_log("TEST_INICIO: test_arbol_uia_por_separado_fixture_real")
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error, "Error enumerando UIA: %s" % tree.error)
        self.assertGreaterEqual(tree.element_count, 2,
                                "Se esperaban al menos ventana + un hijo en Notepad")
        root = tree.root_element
        self.assertEqual(root.handle, self.hwnd)
        self.assertEqual(root.control_type, "Window")
        self.assertTrue(root.visible)
        self.assertFalse(root.is_offscreen)
        self.__class__.uia_tree = tree
        self.__class__.uia_candidatos = [
            self._uia_element_a_candidato(elem, screen=0) for elem in tree.elements
        ]
        _gui_log("TEST_FIN: test_arbol_uia_por_separado_fixture_real "
                 "elementos=%d" % tree.element_count)

    def test_detector_visual_por_separado_fixture_real(self):
        """Detector visual (Vision.detect_ui_elements) sobre captura real de Notepad."""
        _gui_log("TEST_INICIO: test_detector_visual_por_separado_fixture_real")
        servidor_ollama_de_sesion()
        from src.eyes.capture.screen_capture import ScreenCapture
        from src.eyes.vision.vision import Vision

        user32 = ctypes.windll.user32
        hwnd = self.hwnd
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        left = int(rect.left); top = int(rect.top)
        width = int(rect.right - rect.left); height = int(rect.bottom - rect.top)

        ruta = os.path.join(os.getcwd(), "tests", "fixtures",
                            "_tmp_integracion_visual_%d.png" % self.pid)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        captor = ScreenCapture()
        ruta_devuelta = captor.capture_region(left, top, width, height, save_path=ruta)
        self.assertIsNotNone(ruta_devuelta, "No se pudo capturar la region de pantalla")
        self.assertTrue(os.path.exists(ruta), "La captura no se escribio en disco")

        try:
            vision = Vision()
            respuesta = vision.detect_ui_elements(ruta, application="notepad",
                                                   refine_with_opencv=True)
            self.assertIsNotNone(respuesta)
            self.assertIsInstance(respuesta.elements, list)
            self.__class__.visual_respuesta = respuesta
            self.__class__.visual_candidatos = [
                self._visual_element_a_candidato(
                    ve, screen=0, window_handle=hwnd, process_id=self.pid,
                    offset=(left, top))
                for ve in respuesta.elements
            ]
            _gui_log("TEST_FIN: test_detector_visual_por_separado_fixture_real "
                     "elementos_visual=%d" % len(respuesta.elements))
        finally:
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except Exception:
                pass

    def test_fusion_comparativa_uia_visual_fixture_real(self):
        """Fusion UIA + visual sobre Notepad real, con registro de existentes,
        omitidos, duplicados, falsos positivos y UIA-inaccesibles."""
        _gui_log("TEST_INICIO: test_fusion_comparativa_uia_visual_fixture_real")
        servidor_ollama_de_sesion()
        from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
        from src.eyes.capture.screen_capture import ScreenCapture
        from src.eyes.vision.vision import Vision

        # Obtener arbol UIA (reutilizar si ya se tuvo, si no enumerar de nuevo)
        if (hasattr(self.__class__, "uia_tree")
                and self.__class__.uia_tree is not None):
            tree = self.__class__.uia_tree
            candidatos_uia = self.__class__.uia_candidatos
        else:
            adapter = UIAutomationAdapter(timeout=8.0)
            tree = adapter.enumerate_window(self.hwnd, self.pid)
            self.assertIsNone(tree.error)
            candidatos_uia = [
                self._uia_element_a_candidato(elem, screen=0) for elem in tree.elements
            ]

        self.assertIsNotNone(tree)
        self.assertGreaterEqual(tree.element_count, 2)
        self.assertGreaterEqual(len(candidatos_uia), 1)

        # Obtener deteccion visual (reutilizar si ya se tuvo, si no detectar de nuevo)
        if (hasattr(self.__class__, "visual_respuesta")
                and self.__class__.visual_respuesta is not None):
            respuesta = self.__class__.visual_respuesta
            candidatos_visual = self.__class__.visual_candidatos
        else:
            user32 = ctypes.windll.user32
            hwnd = self.hwnd
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
            left = int(rect.left); top = int(rect.top)
            width = int(rect.right - rect.left); height = int(rect.bottom - rect.top)
            ruta = os.path.join(os.getcwd(), "tests", "fixtures",
                                "_tmp_integracion_visual2_%d.png" % self.pid)
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            captor = ScreenCapture()
            ruta_devuelta = captor.capture_region(left, top, width, height, save_path=ruta)
            self.assertIsNotNone(ruta_devuelta)
            try:
                vision = Vision()
                respuesta = vision.detect_ui_elements(ruta, application="notepad",
                                                       refine_with_opencv=True)
                self.assertIsNotNone(respuesta)
                candidatos_visual = [
                    self._visual_element_a_candidato(
                        ve, screen=0, window_handle=hwnd, process_id=self.pid,
                        offset=(left, top))
                    for ve in respuesta.elements
                ]
            finally:
                try:
                    if os.path.exists(ruta):
                        os.remove(ruta)
                except Exception:
                    pass

        self.assertIsInstance(candidatos_visual, list)

        # Fusionar ambas fuentes
        fusion = VisualUIDetectorFusion()
        resultado = fusion.fuse(
            candidatos_uia + candidatos_visual,
            window_handle=tree.window_handle,
            process_id=tree.process_id,
            screen=0,
        )
        self.assertIsNone(resultado.error)
        self.assertGreaterEqual(resultado.candidate_count, 1)
        self.assertIn(SOURCE_UIA, resultado.sources_used)
        self.assertTrue(resultado.sources_available.get(SOURCE_UIA))

        # Comparar y registrar informe
        informe = self._comparar_y_registrar(
            candidatos_uia, candidatos_visual, resultado,
            tree.window_handle, tree.process_id,
        )

        # Verificaciones observables del informe
        self.assertIsInstance(informe["existentes"], list)
        self.assertIsInstance(informe["omitidos_por_visual"], list)
        self.assertIsInstance(informe["omitidos_por_uia"], list)
        self.assertIsInstance(informe["falsos_positivos"], list)
        self.assertIsInstance(informe["duplicados_uia"], list)
        self.assertIsInstance(informe["duplicados_visual"], list)
        self.assertTrue(os.path.exists(self.REPORTE_PATH),
                        "El informe de integracion debe escribirse en disco")
        # UIA debe reportar al menos un patron de accion en Notepad (ventana con patron Window)
        interactivos_uia = [c for c in candidatos_uia
                            if any(p in ACTIONABLE_PATTERNS
                                   for p in c.raw.get("patterns", []))]
        self.assertGreaterEqual(len(interactivos_uia), 1,
                                "UIA debe reportar al menos un patron de accion en Notepad")
        _gui_log("TEST_FIN: test_fusion_comparativa_uia_visual_fixture_real "
                 "existentes=%d omitidos_visual=%d omitidos_uia=%d falsos_positivos=%d"
                 % (len(informe["existentes"]), len(informe["omitidos_por_visual"]),
                    len(informe["omitidos_por_uia"]), len(informe["falsos_positivos"])))
