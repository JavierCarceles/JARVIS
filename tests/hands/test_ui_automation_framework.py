"""
Tests de clasificacion de framework y cobertura por framework (unidad 3.8.6.3.3.11).

Pruebas para src/hands/ui_automation_adapter.py:
- classify_framework(): mapeo de framework_id a nombre canonico de framework.
- get_framework_coverage(): cobertura registrada por framework.
- UIAutomationAdapter.get_framework_summary(): resumen de frameworks en un arbol.
- UIAutomationElement.framework: campo poblado en conversion desde UIA/COM.

Los tests unitarios no abren ventanas ni invocan el SO. Los tests de integracion
real abren Notepad (Win32) en el monitor secundario y verifican que la
clasificacion de framework se aplica sobre elementos reales.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
import unittest

from pywinauto import application

from src.hands.ui_automation_adapter import (
    UIAutomationAdapter,
    UIAutomationElement,
    UIAutomationTree,
    FrameworkCoverage,
    FRAMEWORK_COVERAGE,
    classify_framework,
    get_framework_coverage,
    UIA_COVERAGE_FULL,
    UIA_COVERAGE_PARTIAL,
    UIA_COVERAGE_NONE,
    FALLBACK_NONE,
    FALLBACK_VISION_OCR,
    FALLBACK_CDP,
    FALLBACK_QACCESSIBLE,
)
from src.utils.screen_manager import get_screen_manager


# ---------------------------------------------------------------------------
# Tests unitarios: clasificacion de framework
# ---------------------------------------------------------------------------

class TestClassifyFramework(unittest.TestCase):
    """clasify_framework() mapea framework_id a nombres canonicos sin asumir
    comportamiento uniforme entre frameworks."""

    def test_framework_id_win32(self):
        self.assertEqual(classify_framework("Win32"), "win32")
        self.assertEqual(classify_framework("win32"), "win32")
        self.assertEqual(classify_framework("WIN32"), "win32")

    def test_framework_id_winforms(self):
        self.assertEqual(classify_framework("WinForms"), "winforms")

    def test_framework_id_wpf(self):
        self.assertEqual(classify_framework("WPF"), "wpf")

    def test_framework_id_uwp(self):
        self.assertEqual(classify_framework("UWP"), "uwp_appx")
        self.assertEqual(classify_framework("DirectUI"), "uwp_appx")

    def test_framework_id_qt(self):
        self.assertEqual(classify_framework("Qt"), "qt")

    def test_framework_id_chromium_electron(self):
        self.assertEqual(classify_framework("Chrome"), "chromium_electron")
        self.assertEqual(classify_framework("Chromium"), "chromium_electron")
        self.assertEqual(classify_framework("Chrome_RenderWidgetHostHWND"), "chromium_electron")
        self.assertEqual(classify_framework("electron"), "chromium_electron")

    def test_framework_id_browser_legacy(self):
        self.assertEqual(classify_framework("IE"), "browser_legacy")
        self.assertEqual(classify_framework("EdgeHTML"), "browser_legacy")

    def test_framework_id_browser_gecko(self):
        self.assertEqual(classify_framework("Firefox"), "browser_gecko")
        self.assertEqual(classify_framework("Mozilla"), "browser_gecko")

    def test_framework_id_vacio_con_class_name(self):
        """framework_id vacio con class_name se clasifica como custom_drawn
        (pista visual, no inferencia de cobertura)."""
        self.assertEqual(classify_framework("", "CustomWindowClass"), "custom_drawn")

    def test_framework_id_vacio_sin_pista(self):
        """framework_id vacio y sin class_name se clasifica como unknown."""
        self.assertEqual(classify_framework(""), "unknown")
        self.assertEqual(classify_framework(None), "unknown")

    def test_framework_id_no_reconocido(self):
        """framework_id no reconocido pero no vacio se clasifica como unknown."""
        self.assertEqual(classify_framework("SomeUnknownFramework"), "unknown")

    def test_framework_id_directx_opengl(self):
        self.assertEqual(classify_framework("DirectX"), "directx_opengl")
        self.assertEqual(classify_framework("OpenGL"), "directx_opengl")

    def test_framework_id_game(self):
        self.assertEqual(classify_framework("UnrealEngine"), "game")
        self.assertEqual(classify_framework("Unity"), "game")

    def test_framework_id_overlay(self):
        self.assertEqual(classify_framework("OverlayWindow"), "overlay")

    def test_framework_id_remote_content(self):
        self.assertEqual(classify_framework("CitrixReceiver"), "remote_content")
        self.assertEqual(classify_framework("RDP"), "remote_content")

    def test_framework_id_protected_screen(self):
        self.assertEqual(classify_framework("ProtectedContent"), "protected_screen")


# ---------------------------------------------------------------------------
# Tests unitarios: get_framework_coverage
# ---------------------------------------------------------------------------

class TestGetFrameworkCoverage(unittest.TestCase):
    """get_framework_coverage() devuelve la cobertura registrada por framework."""

    def test_win32_cobertura_completa(self):
        cov = get_framework_coverage("win32")
        self.assertIsInstance(cov, FrameworkCoverage)
        self.assertEqual(cov.framework, "win32")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_FULL)
        self.assertTrue(cov.uia_reliable)
        self.assertIsNone(cov.fallback)

    def test_qt_cobertura_parcial(self):
        cov = get_framework_coverage("qt")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_PARTIAL)
        self.assertFalse(cov.uia_reliable)
        self.assertEqual(cov.fallback, FALLBACK_QACCESSIBLE)
        self.assertFalse(cov.fallback_available)

    def test_chromium_cobertura_parcial_con_cdp(self):
        cov = get_framework_coverage("chromium_electron")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_PARTIAL)
        self.assertFalse(cov.uia_reliable)
        self.assertEqual(cov.fallback, FALLBACK_CDP)
        self.assertFalse(cov.fallback_available)

    def test_custom_drawn_sin_cobertura(self):
        cov = get_framework_coverage("custom_drawn")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_NONE)
        self.assertFalse(cov.uia_reliable)
        self.assertEqual(cov.fallback, FALLBACK_VISION_OCR)
        self.assertFalse(cov.fallback_available)

    def test_protected_screen_sin_cobertura(self):
        cov = get_framework_coverage("protected_screen")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_NONE)
        self.assertFalse(cov.uia_reliable)
        self.assertIsNone(cov.fallback)
        self.assertFalse(cov.fallback_available)

    def test_unknown_devuelve_entrada_unknown(self):
        cov = get_framework_coverage("no_existe")
        self.assertEqual(cov.framework, "unknown")
        self.assertEqual(cov.uia_coverage, UIA_COVERAGE_NONE)
        self.assertFalse(cov.uia_reliable)

    def test_todos_los_frameworks_tienen_entrada(self):
        """Cada framework del registro tiene campos obligatorios poblados."""
        for fw, cov in FRAMEWORK_COVERAGE.items():
            self.assertIsInstance(cov.framework, str)
            self.assertIsInstance(cov.category, str)
            self.assertIn(cov.uia_coverage, (UIA_COVERAGE_FULL, UIA_COVERAGE_PARTIAL, UIA_COVERAGE_NONE))
            self.assertIsInstance(cov.uia_reliable, bool)
            self.assertIsInstance(cov.notes, str)


# ---------------------------------------------------------------------------
# Tests unitarios: FrameworkCoverage.to_dict
# ---------------------------------------------------------------------------

class TestFrameworkCoverageSerialization(unittest.TestCase):
    def test_to_dict_estructura_plana(self):
        cov = FrameworkCoverage(
            framework="wpf",
            category="desktop_native",
            uia_coverage=UIA_COVERAGE_FULL,
            uia_reliable=True,
            fallback=None,
            fallback_available=False,
            notes="WPF nativo",
        )
        d = cov.to_dict()
        self.assertEqual(d["framework"], "wpf")
        self.assertEqual(d["uia_coverage"], UIA_COVERAGE_FULL)
        self.assertTrue(d["uia_reliable"])
        self.assertIsNone(d["fallback"])
        self.assertFalse(d["fallback_available"])


# ---------------------------------------------------------------------------
# Tests unitarios: UIAutomationElement.framework
# ---------------------------------------------------------------------------

class TestUIAutomationElementFramework(unittest.TestCase):
    """El campo framework se popula con valor vacio por defecto."""

    def test_framework_valor_por_defecto(self):
        elem = UIAutomationElement(control_type="Button", handle=1)
        self.assertEqual(elem.framework, "")

    def test_to_dict_incluye_framework(self):
        elem = UIAutomationElement(
            automation_id="btn1", name="Aceptar", control_type="Button",
            framework_id="WPF", framework="wpf", handle=1,
        )
        d = elem.to_dict()
        self.assertEqual(d["framework_id"], "WPF")
        self.assertEqual(d["framework"], "wpf")


# ---------------------------------------------------------------------------
# Tests unitarios: UIAutomationAdapter.get_framework_summary
# ---------------------------------------------------------------------------

class TestGetFrameworkSummary(unittest.TestCase):
    """get_framework_summary() resume la distribucion de frameworks de un arbol."""

    def test_arbol_vacio(self):
        adapter = UIAutomationAdapter()
        tree = UIAutomationTree(
            window_handle=1, process_id=1, window_title="V",
            window_class="C", root_element=UIAutomationElement(control_type="Window", handle=1),
            elements=[], element_count=0, source="uia", elapsed_seconds=0.1,
        )
        summary = adapter.get_framework_summary(tree)
        self.assertEqual(summary["total_elements"], 0)
        self.assertEqual(summary["by_framework"], {})
        self.assertEqual(summary["frameworks_detectados"], [])
        self.assertEqual(summary["frameworks_sin_cobertura"], [])
        self.assertEqual(summary["elementos_con_framework_desconocido"], 0)

    def test_resumen_multi_framework(self):
        adapter = UIAutomationAdapter()
        elems = [
            UIAutomationElement(control_type="Window", handle=1, framework_id="Win32", framework="win32"),
            UIAutomationElement(control_type="Button", handle=2, framework_id="Win32", framework="win32"),
            UIAutomationElement(control_type="Button", handle=3, framework_id="WPF", framework="wpf"),
            UIAutomationElement(control_type="Button", handle=4, framework_id="Chrome", framework="chromium_electron"),
            UIAutomationElement(control_type="Button", handle=5, framework="custom_drawn"),
            UIAutomationElement(control_type="Text", handle=6),  # framework vacio -> unknown
        ]
        root = UIAutomationElement(control_type="Window", handle=1, framework_id="Win32", framework="win32")
        tree = UIAutomationTree(
            window_handle=1, process_id=1, window_title="V",
            window_class="C", root_element=root, elements=elems,
            element_count=len(elems), source="uia", elapsed_seconds=0.1,
        )
        summary = adapter.get_framework_summary(tree)
        self.assertEqual(summary["total_elements"], 6)
        self.assertEqual(summary["by_framework"]["win32"]["count"], 2)
        self.assertEqual(summary["by_framework"]["wpf"]["count"], 1)
        self.assertEqual(summary["by_framework"]["chromium_electron"]["count"], 1)
        self.assertEqual(summary["by_framework"]["custom_drawn"]["count"], 1)
        self.assertEqual(summary["by_framework"]["unknown"]["count"], 1)
        self.assertIn("win32", summary["frameworks_detectados"])
        self.assertIn("custom_drawn", summary["frameworks_sin_cobertura"])
        self.assertIn("unknown", summary["frameworks_sin_cobertura"])
        self.assertEqual(summary["elementos_con_framework_desconocido"], 1)

    def test_resumen_cobertura_campos(self):
        adapter = UIAutomationAdapter()
        root = UIAutomationElement(control_type="Window", handle=1, framework_id="Qt", framework="qt")
        elems = [root]
        tree = UIAutomationTree(
            window_handle=1, process_id=1, window_title="V",
            window_class="C", root_element=root, elements=elems,
            element_count=1, source="uia", elapsed_seconds=0.1,
        )
        summary = adapter.get_framework_summary(tree)
        fw_info = summary["by_framework"]["qt"]
        self.assertEqual(fw_info["coverage"], UIA_COVERAGE_PARTIAL)
        self.assertFalse(fw_info["uia_reliable"])
        self.assertEqual(fw_info["fallback"], FALLBACK_QACCESSIBLE)
        self.assertFalse(fw_info["fallback_available"])


# ---------------------------------------------------------------------------
# Integracion real: Notepad (Win32) en monitor secundario
# ---------------------------------------------------------------------------

class TestFrameworkRealNotepad(unittest.TestCase):
    """Integracion real sobre Notepad (framework Win32).

    Abre Notepad, lo mueve al monitor secundario derecho y lo maximiza.
    Verifica que la clasificacion de framework se aplica sobre elementos
    reales del arbol UIA. Solo lectura: no envia input ni invoca patrones.
    """

    APP = "notepad.exe"

    def setUp(self):
        self.proc = None
        self.hwnd = None
        self.pid = None
        self.adapter = UIAutomationAdapter(timeout=8.0)
        self._screen_manager = get_screen_manager()
        self._screen_manager.refresh_monitors()

    def tearDown(self):
        pid_a_cerrar = None
        try:
            if self.pid is not None:
                pid_a_cerrar = int(self.pid)
        except Exception:
            pid_a_cerrar = None
        if pid_a_cerrar is None and self.proc is not None:
            try:
                pid_a_cerrar = int(self.proc.pid)
            except Exception:
                pid_a_cerrar = None
        if pid_a_cerrar is not None:
            try:
                import subprocess as _sp
                _sp.run(
                    ["taskkill", "/PID", str(pid_a_cerrar), "/F", "/T"],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.hwnd = None
        self.pid = None

    def _enumerar_ventanas_notepad(self, user32, pid_esperado):
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

    def _abrir_notepad_maximizado_secundario(self):
        user32 = ctypes.windll.user32
        monitors = self._screen_manager.monitors
        secundario = None
        for m in monitors:
            if not m.is_primary:
                secundario = m
                break
        if secundario is None:
            secundario = self._screen_manager.get_primary_monitor()

        self.assertIsNotNone(secundario, "No se encontro monitor secundario")

        self.proc = subprocess.Popen([self.APP])

        pid_esperado = self.proc.pid
        found = []
        for _intento in range(20):
            time.sleep(0.3)
            found = self._enumerar_ventanas_notepad(user32, pid_esperado)
            if found:
                break

        self.assertGreaterEqual(len(found), 1,
                                "No se encontro la ventana de Notepad creada")

        hwnd, pid, title = None, None, None
        for cand_hwnd, cand_pid, cand_title in found:
            if cand_pid == pid_esperado:
                hwnd, pid, title = cand_hwnd, cand_pid, cand_title
                break
        if hwnd is None:
            hwnd, pid, title = found[0]

        self.hwnd = hwnd
        self.pid = pid

        if not user32.IsWindow(ctypes.c_void_p(hwnd)):
            self.fail("HWND=%s ya no es una ventana valida" % hwnd)

        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
        time.sleep(0.3)
        user32.SetWindowPos(
            ctypes.c_void_p(hwnd), 0,
            int(secundario.left), int(secundario.top),
            int(secundario.width), int(secundario.height),
            0x0004 | 0x0040,  # SWP_NOZORDER | SWP_SHOWWINDOW
        )
        time.sleep(0.3)
        user32.ShowWindow(ctypes.c_void_p(hwnd), 3)  # SW_MAXIMIZE
        time.sleep(0.8)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        time.sleep(0.3)

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        self.assertTrue(
            secundario.contains_point(cx, cy),
            "Centro de la ventana no esta en el monitor secundario",
        )
        self.assertGreater(rect.right - rect.left, 100)
        self.assertGreater(rect.bottom - rect.top, 100)

        return hwnd, pid

    def test_framework_clasificado_en_notepad_real(self):
        """Notepad real: la raiz y los controles tienen framework_id y
        framework clasificados (esperado win32 para controles nativos)."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()

        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error, "Error enumerando: %s" % tree.error)
        self.assertGreaterEqual(tree.element_count, 1)

        # La raiz es la ventana de Notepad (Win32 nativo)
        root = tree.root_element
        self.assertEqual(root.handle, hwnd)
        self.assertEqual(root.control_type, "Window")
        # framework_id debe estar poblado (Win32) y framework clasificado
        self.assertIsInstance(root.framework_id, str)
        self.assertIsInstance(root.framework, str)

        # Al menos un elemento debe tener framework clasificado
        frameworks_encontrados = set()
        for elem in tree.elements:
            if elem.framework:
                frameworks_encontrados.add(elem.framework)
            if elem.framework_id:
                frameworks_encontrados.add(elem.framework_id)

        self.assertGreater(len(frameworks_encontrados), 0,
                           "Se esperaba al menos un framework identificado en el arbol de Notepad")

    def test_resumen_framework_notepad_real(self):
        """get_framework_summary() sobre Notepad real devuelve distribucion
        de frameworks con cobertura y fallbacks."""
        hwnd, pid = self._abrir_notepad_maximizado_secundario()

        tree = self.adapter.enumerate_window(hwnd, pid)
        self.assertIsNone(tree.error)

        summary = self.adapter.get_framework_summary(tree)
        self.assertEqual(summary["total_elements"], tree.element_count)
        self.assertGreater(summary["total_elements"], 0)
        self.assertIsInstance(summary["by_framework"], dict)
        self.assertIsInstance(summary["frameworks_detectados"], list)
        self.assertIsInstance(summary["frameworks_sin_cobertura"], list)
        self.assertIsInstance(summary["elementos_con_framework_desconocido"], int)

        # Cada framework detectado debe tener entrada de cobertura
        for fw in summary["frameworks_detectados"]:
            cov = get_framework_coverage(fw)
            self.assertIsInstance(cov.framework, str)
            self.assertIn(cov.uia_coverage, (UIA_COVERAGE_FULL, UIA_COVERAGE_PARTIAL, UIA_COVERAGE_NONE))


if __name__ == "__main__":
    unittest.main()
