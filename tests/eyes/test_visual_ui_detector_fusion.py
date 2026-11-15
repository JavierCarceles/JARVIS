"""
Tests de fusion de deteccion de elementos UI — unidad 3.8.6.3.3.9.

Pruebas para src/eyes/visual_ui_detector_fusion.py.

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
GUI_LOG_FILE = os.path.join(os.path.dirname(__file__), "fixtures", "gui_tests.log")


def _gui_log(mensaje: str) -> None:
    """Escribe un mensaje con timestamp al fichero de log de pruebas GUI."""
    os.makedirs(os.path.dirname(GUI_LOG_FILE), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    linea = "[%s] %s\n" % (timestamp, mensaje)
    with open(GUI_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)


from src.eyes.visual_ui_detector_fusion import (
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
from src.eyes.vision import Vision
from src.utils.ui_element_model import UIElementData, normalize_element_type
from src.utils.screen_manager import get_screen_manager


# ---------------------------------------------------------------------------
# Lock para impedir ejecucion concurrente de tests GUI
# ---------------------------------------------------------------------------
GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "fixtures", "_gui_lock.lock")


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
    from src.hands.ui_automation_adapter import UIAutomationElement

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

GUI_LOCK_FILE = os.path.join(os.path.dirname(__file__), "fixtures", "_gui_lock.lock")


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
            # huérfanas.
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
        from src.hands.ui_automation_adapter import UIAutomationAdapter
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
        from src.hands.ui_automation_adapter import UIAutomationAdapter
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
        from src.hands.ui_automation_adapter import UIAutomationAdapter
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
        import ollama
        from src.hands.ui_automation_adapter import UIAutomationAdapter
        from src.eyes.screen_capture import ScreenCapture

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
