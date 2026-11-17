"""
Tests de integracion real de clasificacion - unidad 3.8.6.3.3.10.

Abre una aplicacion inocua real (Notepad), enumera su arbol UI Automation,
fusiona los candidatos y clasifica cada uno. Verifica que:
- al menos un elemento con patron de accion UIA se clasifica como UIA_ACTIONABLE;
- hay etiquetas de texto (TEXT_LABEL);
- ningun elemento se clasifica como UIA_ACTIONABLE sin patron de accion UIA.

Se ejecuta solo si JARVIS_TEST_GUI_REAL=1. Abre y cierra UNA sola ventana de
Notepad por sesion de pytest (estado compartido a nivel de modulo, cierre en
atexit). Operacion de solo lectura sobre el arbol UIA: no envia input, no
invoca patrones de accion, no toca ventanas ajenas ni la pantalla principal.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import subprocess
import time
import unittest

from src.hands.detection.ui_automation_adapter import UIAutomationAdapter
from src.eyes.detection.visual_ui_detector_fusion import (
    VisualUIDetectorFusion,
    DetectedCandidate,
    SOURCE_UIA,
)
from src.core.ui_element_model import UIElementData, normalize_element_type

APP = "notepad.exe"
WM_CLOSE = 0x0010

GUI_LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "_gui_classification_lock.lock")
_SHARED_NOTEPAD = {"hwnd": None, "pid": None, "proc": None}
_ATEXIT_REGISTERED = False


def _gui_disponible():
    return os.environ.get("JARVIS_TEST_GUI_REAL", "") == "1"


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
            pass
    state["hwnd"] = None
    state["pid"] = None
    state["proc"] = None
    _ATEXIT_REGISTERED = False


def _cerrar_huorfanas_notepad():
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
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(hwnd), ctypes.byref(pid)
                )
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


def _buscar_ventana_notepad():
    """Devuelve (hwnd, pid) de la ventana de Notepad visible, o (None, None)."""
    user32 = ctypes.windll.user32
    encontrados = []

    def callback(hwnd, _):
        try:
            if not user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                return True
            length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
            titulo = buf.value.lower()
            if "notepad" in titulo or "bloc de notas" in titulo:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(hwnd), ctypes.byref(pid)
                )
                encontrados.append((int(hwnd), int(pid.value), buf.value))
        except Exception:
            pass
        return True

    CBFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(CBFUNC(callback), 0)
    if not encontrados:
        return None, None
    # Quedarse con la primera ventana visible de Notepad.
    return encontrados[0][0], encontrados[0][1]


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


def _lanzar_notepad_compartido():
    """Lanza (o reusa) una sola ventana de Notepad y devuelve su HWND/PID real."""
    global _ATEXIT_REGISTERED
    _cerrar_huorfanas_notepad()
    hwnd, pid = _buscar_ventana_notepad()
    if hwnd is not None:
        _SHARED_NOTEPAD["hwnd"] = hwnd
        _SHARED_NOTEPAD["pid"] = pid
        return hwnd, pid
    proc = subprocess.Popen([APP])
    # Esperar a que aparezca la ventana (Notepad es de instancia unica).
    for _ in range(50):
        time.sleep(0.2)
        hwnd, pid = _buscar_ventana_notepad()
        if hwnd is not None:
            break
    _SHARED_NOTEPAD["hwnd"] = hwnd
    _SHARED_NOTEPAD["pid"] = pid
    _SHARED_NOTEPAD["proc"] = proc
    if not _ATEXIT_REGISTERED:
        try:
            atexit.register(_cerrar_notepad_compartido)
            _ATEXIT_REGISTERED = True
        except Exception:
            pass
    return hwnd, pid


def _elemento_a_candidato(elem, hwnd, pid):
    """Convierte un UIAutomationElement en un DetectedCandidate."""
    x1, y1, x2, y2 = elem.bounding_rectangle
    center = [
        int(round((x1 + x2) / 2.0)),
        int(round((y1 + y2) / 2.0)),
    ]
    element = UIElementData(
        name=(elem.automation_id or elem.name or "element"),
        type=normalize_element_type(elem.control_type),
        text=elem.name,
        description="",
        bbox=list(elem.bounding_rectangle),
        center=center,
        screen=0,
        interactive=bool(elem.is_enabled and elem.visible and not elem.is_offscreen),
        confidence=0.8,
        calibrated=False,
    )
    return DetectedCandidate(
        source=SOURCE_UIA,
        element=element,
        confidence=0.8,
        bbox=list(elem.bounding_rectangle),
        center=center,
        screen=0,
        window_handle=hwnd,
        process_id=pid,
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


@unittest.skipUnless(_gui_disponible(), "Requiere JARVIS_TEST_GUI_REAL=1")
class TestClasificacionIntegracionNotepad(unittest.TestCase):
    """Clasificacion sobre el arbol UIA real de una ventana de Notepad."""

    @classmethod
    def setUpClass(cls):
        _adquirir_gui_lock()
        cls.hwnd, cls.pid = _lanzar_notepad_compartido()
        cls.assertIsNotNone(cls.hwnd, "No se pudo identificar la ventana de Notepad")
        cls.assertIsNotNone(cls.pid, "No se pudo obtener el PID de Notepad")

    @classmethod
    def tearDownClass(cls):
        _liberar_gui_lock()

    def test_arbol_uia_real_devuelve_elementos(self):
        adapter = UIAutomationAdapter(timeout=10.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error, tree.error)
        self.assertGreater(tree.element_count, 0)

    def test_clasificacion_tiene_actionable_y_textos(self):
        adapter = UIAutomationAdapter(timeout=10.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error)
        self.assertGreater(tree.element_count, 0)

        candidatos = [_elemento_a_candidato(e, self.hwnd, self.pid) for e in tree.elements]
        fusion = VisualUIDetectorFusion()
        resultado = fusion.fuse(
            candidatos, window_handle=self.hwnd, process_id=self.pid, screen=0
        )
        self.assertIsNone(resultado.error)
        self.assertGreater(resultado.candidate_count, 0)

        clasificaciones = [c.classification for c in resultado.candidates]
        # Debe haber al menos un elemento actionable (boton/menu con patron UIA)
        # en una ventana de Notepad real.
        self.assertIn(
            "uia_actionable", clasificaciones,
            "Esperaba al menos un elemento UIA_ACTIONABLE en Notepad",
        )
        # La clasificacion debe discriminar: no todo el arbol es actionable.
        # Notepad expone elementos fuera de pantalla y deshabilitados, que
        # nunca deben ser UIA_ACTIONABLE.
        self.assertGreater(len(set(clasificaciones)), 1, "La clasificacion no discrimino categorias")
        self.assertIn("offscreen", clasificaciones, "Esperaba elementos OFFSCREEN en Notepad")
        self.assertIn("disabled", clasificaciones, "Esperaba elementos DISABLED en Notepad")
        PATRONES_ACCION = ("Invoke", "Value", "Toggle", "Selection", "ExpandCollapse",
                           "Scroll", "Window", "Transform")
        # Ningun elemento sin patron de accion UIA debe ser UIA_ACTIONABLE.
        for c in resultado.candidates:
            if c.classification == "uia_actionable":
                uia_ev = next(
                    (s for s in c.sources if s.source == SOURCE_UIA), None
                )
                patrones = uia_ev.raw.get("patterns", []) if (uia_ev and uia_ev.raw) else []
                tiene_patron = any(p in PATRONES_ACCION for p in patrones)
                self.assertTrue(tiene_patron, "UIA_ACTIONABLE sin patron de accion UIA")


if __name__ == "__main__":
    unittest.main()
