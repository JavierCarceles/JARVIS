"""
Tests del validador de pertenencia de evidencia a ventana objetivo - unidad 3.8.6.4.1.

Pruebas para src/hands/detection/window_evidence_validator.py.

- Tests unitarios de contrato/logica (sin GUI ni modelos): identidad HWND/PID,
  contenimiento geometrico de la region de captura, rechazo de captura de
  escritorio entero, y candidatos con window_handle/process_id/bbox/pantalla
  contradictorios. No se utilizan mocks que decidan el resultado que se valida.
- Tests de integracion real GUI: comparten UNA sola ventana de Notepad por
  sesion de pytest (TestGuiBase de tests/eyes/test_visual_ui_detector_fusion,
  abierta en el monitor secundario derecho). Valida el arbol UIA real, una
  captura real de la ventana y los candidatos construidos del arbol contra la
  ventana de Notepad, y comprueba que la captura de escritorio entero se
  rechace. Solo se ejecutan si JARVIS_TEST_GUI_REAL=1.
"""

from __future__ import annotations

import ctypes
from types import SimpleNamespace
import unittest

from src.hands.detection.ui_automation_adapter import (
    UIAutomationAdapter,
    UIAutomationElement,
    UIAutomationTree,
)
from src.hands.detection.window_evidence_validator import (
    WindowEvidenceValidator,
    WindowEvidenceValidation,
    validate_evidence_for_window,
)
from src.eyes.detection.visual_ui_detector_fusion import (
    FusedCandidate,
    SOURCE_UIA,
)
from src.core.ui_element_model import UIElementData
from src.desktop.screen_manager import get_screen_manager

# Reusa la infraestructura de ventana compartida (una Notepad por sesion de
# pytest, monitor secundario derecho, lock de exclusion, cierre por atexit).
from tests.eyes.detection.test_visual_ui_detector_fusion import TestGuiBase  # noqa: E402


def _sintetico_elemento(
    automation_id="",
    name="",
    control_type="Button",
    bbox=(10, 10, 60, 30),
    patterns=None,
    is_enabled=True,
    visible=True,
    is_offscreen=False,
    handle=1,
    process_id=100,
    depth=0,
):
    """Crea un UIAutomationElement sintetico para pruebas de contrato."""
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
        framework="win32",
        parent_handle=0,
        child_count=0,
        patterns=list(patterns or []),
        depth=depth,
        source="uia",
    )


def _sintetico_arbol(window_handle, process_id, elementos, titulo="Ventana", clase="Clase"):
    """Crea un UIAutomationTree sintetico con raiz de ventana y elementos dados."""
    raiz = _sintetico_elemento(
        name=titulo,
        control_type="Window",
        bbox=(0, 0, 800, 600),
        handle=window_handle,
        process_id=process_id,
        patterns=["Window"],
        depth=0,
    )
    todos = [raiz] + list(elementos)
    return UIAutomationTree(
        window_handle=window_handle,
        process_id=process_id,
        window_title=titulo,
        window_class=clase,
        root_element=raiz,
        elements=todos,
        element_count=len(todos),
        source="uia",
    )


def _candidato_fused(
    name="element",
    type="button",
    bbox=(10, 10, 60, 30),
    window_handle=None,
    process_id=None,
    screen=0,
    interactive=False,
):
    """Crea un FusedCandidate sintetico para pruebas de contrato."""
    return FusedCandidate(
        canonical_id="elem_%s" % name,
        name=name,
        type=type,
        text=name,
        description="",
        bbox=list(bbox),
        center=[(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2],
        screen=int(screen),
        window_handle=window_handle,
        process_id=process_id,
        sources=[{"source": SOURCE_UIA, "confidence": 0.9}],
        merged_confidence=0.9,
        agreement=True,
        disagreements=[],
        interactive=bool(interactive),
        interactive_evidence=[],
        calibrated=False,
    )


class TestWindowEvidenceValidatorContract(unittest.TestCase):
    """Contrato y logica pura del validador (sin GUI)."""

    def setUp(self):
        self.hwnd = 1234
        self.pid = 5678
        self.validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        # Rectangulo de ventana sintetico para pruebas sin ventana real.
        self.validator._window_rect_cache = (100, 100, 500, 400)

    def test_validador_instancia_con_objetivo(self):
        self.assertEqual(self.validator.target_hwnd, self.hwnd)
        self.assertEqual(self.validator.target_pid, self.pid)

    def test_validar_arbol_uia_ventana_correcta_valido(self):
        arbol = _sintetico_arbol(
            self.hwnd,
            self.pid,
            [
                _sintetico_elemento(
                    name="btn",
                    control_type="Button",
                    bbox=(10, 10, 60, 30),
                    handle=2,
                    process_id=self.pid,
                    patterns=["Invoke"],
                    depth=1,
                )
            ],
        )
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertTrue(res.valid)
        self.assertTrue(res.accepted)
        self.assertTrue(res.checks["window_identity"])
        self.assertTrue(res.checks["root_handle"])
        self.assertTrue(res.checks["process_identity"])
        self.assertTrue(res.checks["no_foreign_process"])
        self.assertTrue(res.checks["no_desktop_leak"])
        self.assertEqual(res.rejected_evidence, [])

    def test_validar_arbol_uia_hwnd_diferente_invalido(self):
        arbol = _sintetico_arbol(9999, self.pid, [])
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["window_identity"])
        self.assertIn("HWND", res.reason)

    def test_validar_arbol_uia_pid_extrano_invalido(self):
        arbol = _sintetico_arbol(self.hwnd, 1111, [])
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["process_identity"])

    def test_validar_arbol_uia_elemento_proceso_extrano_invalido(self):
        arbol = _sintetico_arbol(
            self.hwnd,
            self.pid,
            [
                _sintetico_elemento(
                    name="extra",
                    control_type="Button",
                    bbox=(10, 10, 60, 30),
                    handle=3,
                    process_id=9999,
                    patterns=[],
                    depth=1,
                )
            ],
        )
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["no_foreign_process"])
        self.assertIn("arbol_uiA_proceso_extrano", res.rejected_evidence)

    def test_validar_arbol_uia_sin_elementos_y_con_error_invalido(self):
        arbol = UIAutomationTree(
            window_handle=self.hwnd,
            process_id=self.pid,
            window_title="",
            window_class="",
            root_element=UIAutomationElement(),
            elements=[],
            element_count=0,
            error="timeout",
            source="uia",
        )
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["no_enumeration_error"])

    def test_validar_arbol_uia_truncado_no_invalido_por_si_solo(self):
        raiz = _sintetico_elemento(
            name="win",
            control_type="Window",
            bbox=(0, 0, 800, 600),
            handle=self.hwnd,
            process_id=self.pid,
            patterns=["Window"],
            depth=0,
        )
        arbol = UIAutomationTree(
            window_handle=self.hwnd,
            process_id=self.pid,
            window_title="V",
            window_class="C",
            root_element=raiz,
            elements=[raiz],
            element_count=1,
            truncated=True,
            error=None,
            source="uia",
        )
        res = self.validator.validate_ui_automation_tree(arbol)
        self.assertTrue(res.valid)

    def test_validar_captura_region_dentro_de_ventana_valido(self):
        res = self.validator.validate_capture_region((120, 120, 200, 200))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["geometria_dentro_de_ventana"])
        self.assertTrue(res.checks["no_evidencia_escritorio_entero"])

    def test_validar_captura_region_igual_ventana_valido(self):
        res = self.validator.validate_capture_region((100, 100, 500, 400))
        self.assertTrue(res.valid)

    def test_rechazar_captura_escritorio_entero(self):
        escritorio = (0, 0, 3840, 2160)
        res = self.validator.validate_capture_region(escritorio)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["no_evidencia_escritorio_entero"])
        self.assertIn("captura_escritorio_entero", res.rejected_evidence)

    def test_rechazar_captura_region_fuera_de_ventana(self):
        res = self.validator.validate_capture_region((600, 600, 700, 700))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["geometria_dentro_de_ventana"])

    def test_region_invalida_rechazada(self):
        res = self.validator.validate_capture_region(None)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["region_valida"])
        res = self.validator.validate_capture_region((100, 100, 100, 200))
        self.assertFalse(res.valid)

    def test_validar_candidatos_todos_dentro_valido(self):
        cands = [
            _candidato_fused(
                "btn1", "button", (120, 120, 200, 160),
                window_handle=self.hwnd, process_id=self.pid, screen=0,
            ),
            _candidato_fused(
                "edit1", "input", (150, 200, 250, 230),
                window_handle=self.hwnd, process_id=self.pid, screen=0,
            ),
        ]
        res = self.validator.validate_candidates(cands, screen=0)
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["todos_candidatos_pertenecen_a_ventana"])

    def test_candidato_window_handle_extrano_rechazado(self):
        cands = [
            _candidato_fused(
                "btn", "button", (120, 120, 200, 160),
                window_handle=9999, process_id=self.pid, screen=0,
            )
        ]
        res = self.validator.validate_candidates(cands, screen=0)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["todos_candidatos_pertenecen_a_ventana"])
        self.assertIn("candidato_0", res.rejected_evidence)

    def test_candidato_pid_extrano_rechazado(self):
        cands = [
            _candidato_fused(
                "btn", "button", (120, 120, 200, 160),
                window_handle=self.hwnd, process_id=1111, screen=0,
            )
        ]
        res = self.validator.validate_candidates(cands, screen=0)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["todos_candidatos_pertenecen_a_ventana"])

    def test_candidato_bbox_fuera_ventana_rechazado(self):
        cands = [
            _candidato_fused(
                "btn", "button", (600, 600, 700, 700),
                window_handle=self.hwnd, process_id=self.pid, screen=0,
            )
        ]
        res = self.validator.validate_candidates(cands, screen=0)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["todos_candidatos_pertenecen_a_ventana"])

    def test_candidato_pantalla_extrana_rechazado(self):
        cands = [
            _candidato_fused(
                "btn", "button", (120, 120, 200, 160),
                window_handle=self.hwnd, process_id=self.pid, screen=9,
            )
        ]
        res = self.validator.validate_candidates(cands, screen=0)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["todos_candidatos_pertenecen_a_ventana"])

    def test_validar_todo_combinado_valido(self):
        arbol = _sintetico_arbol(self.hwnd, self.pid, [])
        cands = [
            _candidato_fused(
                "btn", "button", (120, 120, 200, 160),
                window_handle=self.hwnd, process_id=self.pid, screen=0,
            )
        ]
        res = self.validator.validate_all(
            tree=arbol, capture_region=(120, 120, 200, 200), candidates=cands, screen=0,
        )
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["arbol_uiA.window_identity"])
        self.assertTrue(res.checks["captura.geometria_dentro_de_ventana"])
        self.assertTrue(res.checks["candidatos.todos_candidatos_pertenecen_a_ventana"])

    def test_validar_todo_con_captura_escritorio_entero_rechazado(self):
        arbol = _sintetico_arbol(self.hwnd, self.pid, [])
        res = self.validator.validate_all(
            tree=arbol, capture_region=(0, 0, 3840, 2160),
        )
        self.assertFalse(res.valid)
        self.assertTrue(
            any("captura_escritorio_entero" in r for r in res.rejected_evidence),
            res.rejected_evidence,
        )

    def test_validar_todo_sin_evidencia_invalido(self):
        res = self.validator.validate_all()
        self.assertFalse(res.valid)
        self.assertEqual(res.reason, "no hay evidencia que validar")

    def test_funcion_conveniencia_ventana_inexistente_invalida(self):
        arbol = _sintetico_arbol(self.hwnd, self.pid, [])
        res = validate_evidence_for_window(0xBADF00D, target_pid=self.pid, tree=arbol)
        self.assertFalse(res.valid)
        self.assertIn("no existe o no es accesible", res.reason)

    def test_to_dict_serializable(self):
        res = WindowEvidenceValidation(
            True, True, "ok", {"a": True}, ["x"], {"k": 1}
        )
        d = res.to_dict()
        self.assertEqual(d["valid"], True)
        self.assertEqual(d["accepted"], True)
        self.assertEqual(d["reason"], "ok")
        self.assertEqual(d["checks"], {"a": True})
        self.assertEqual(d["rejected_evidence"], ["x"])
        self.assertEqual(d["details"]["k"], 1)

    # ------------------------------------------------------------------
    # Puerta de calidad geometrica de candidatos (unidad 3.8.6.4.2)
    # ------------------------------------------------------------------

    def test_geometria_caja_valida_dentro_ventana_aceptada(self):
        cand = _candidato_fused(
            "btn", "button", (120, 120, 200, 160),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["caja_valida"])
        self.assertTrue(res.checks["caja_dentro_de_ventana"])
        self.assertTrue(res.checks["control_no_obstruido"])
        self.assertTrue(res.checks["no_solapamiento_ambiguo"])
        self.assertEqual(res.rejected_evidence, [])

    def test_geometria_caja_degenerada_rechazada(self):
        cand = _candidato_fused(
            "btn", "button", (120, 120, 120, 160),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["caja_valida"])
        self.assertIn("candidato:caja_degenerada", res.rejected_evidence)

    def test_geometria_caja_ausente_rechazada(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=None,
            canonical_id="btn", window_handle=self.hwnd,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["caja_valida"])
        self.assertIn("candidato:caja_degenerada", res.rejected_evidence)

    def test_geometria_caja_fuera_ventana_rechazada(self):
        cand = _candidato_fused(
            "btn", "button", (600, 600, 700, 700),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["caja_dentro_de_ventana"])
        self.assertIn("candidato:caja_fuera_ventana", res.rejected_evidence)

    def test_geometria_caja_parcialmente_fuera_ventana_rechazada(self):
        cand = _candidato_fused(
            "btn", "button", (450, 350, 550, 450),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["caja_dentro_de_ventana"])
        self.assertIn("candidato:caja_fuera_ventana", res.rejected_evidence)

    def test_geometria_caja_fuera_imagen_rechazada(self):
        cand = _candidato_fused(
            "btn", "button", (120, 120, 200, 160),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, image_rect=(0, 0, 150, 150), window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["caja_dentro_de_imagen"])
        self.assertIn("candidato:caja_fuera_imagen", res.rejected_evidence)

    def test_geometria_caja_dentro_imagen_aceptada(self):
        cand = _candidato_fused(
            "btn", "button", (120, 120, 200, 160),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, image_rect=(0, 0, 1000, 1000), window_rect=(100, 100, 500, 400))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["caja_dentro_de_imagen"])

    def test_geometria_control_offscreen_rechazado(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=(120, 120, 200, 160),
            canonical_id="btn", window_handle=self.hwnd,
            is_offscreen=True, visible=True,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["control_no_obstruido"])
        self.assertIn("candidato:control_obstruido", res.rejected_evidence)

    def test_geometria_control_no_visible_rechazado(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=(120, 120, 200, 160),
            canonical_id="btn", window_handle=self.hwnd,
            is_offscreen=False, visible=False,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["control_no_obstruido"])

    def test_geometria_control_visible_aceptado(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=(120, 120, 200, 160),
            canonical_id="btn", window_handle=self.hwnd,
            is_offscreen=False, visible=True,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["control_no_obstruido"])

    def test_geometria_solapamiento_ambiguo_rechazado(self):
        cand_a = _candidato_fused(
            "btn_a", "button", (100, 100, 200, 200),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        cand_b = _candidato_fused(
            "btn_b", "button", (120, 120, 220, 220),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand_a, window_rect=(100, 100, 500, 400), otros_candidatos=[cand_b])
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["no_solapamiento_ambiguo"])
        self.assertIn("candidato:solapamiento_ambiguo", res.rejected_evidence)

    def test_geometria_solapamiento_misma_identidad_no_rechazado(self):
        cand_a = _candidato_fused(
            "btn", "button", (100, 100, 200, 200),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        cand_b = _candidato_fused(
            "btn", "button", (120, 120, 220, 220),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand_a, window_rect=(100, 100, 500, 400), otros_candidatos=[cand_b])
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["no_solapamiento_ambiguo"])

    def test_geometria_espacio_coordenadas_desconocido_rechazado(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=(120, 120, 200, 160),
            canonical_id="btn", window_handle=self.hwnd,
            coordinate_space="espacio_inventado",
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["espacio_coordenadas_conocido"])
        self.assertIn(
            "candidato:espacio_coordenadas_desconocido", res.rejected_evidence)

    def test_geometria_espacio_coordenadas_conocido_aceptado(self):
        cand = SimpleNamespace(
            name="btn", type="button", bbox=(120, 120, 200, 160),
            canonical_id="btn", window_handle=self.hwnd,
            coordinate_space="image_pixels",
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["espacio_coordenadas_conocido"])

    def test_geometria_sin_espacio_coordenadas_no_rechazado_por_eso(self):
        cand = _candidato_fused(
            "btn", "button", (120, 120, 200, 160),
            window_handle=self.hwnd, process_id=self.pid, screen=0,
        )
        res = self.validator.validate_geometria_candidato(
            cand, window_rect=(100, 100, 500, 400))
        self.assertTrue(res.valid)
        self.assertTrue(res.checks["espacio_coordenadas_conocido"])

class TestWindowEvidenceValidatorNotepadReal(TestGuiBase):
    """Integracion real con UNA ventana de Notepad compartida por sesion.

    Valida que el arbol UIA real, una captura real de la ventana y los
    candidatos construidos del arbol pertenezcan a la ventana de Notepad
    (HWND/PID), y que la captura de escritorio entero se rechace.
    """

    def _rectangulo_ventana(self, hwnd):
        rect = ctypes.wintypes.RECT()
        ok = ctypes.windll.user32.GetWindowRect(
            ctypes.c_void_p(int(hwnd)), ctypes.byref(rect)
        )
        self.assertTrue(ok)
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

    def test_validar_arbol_uia_notepad_real_pertenece_a_ventana_objetivo(self):
        """Arbol UIA real de Notepad: window_handle, PID y elementos del mismo proceso."""
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error, "enumeracion UIA fallo: %s" % tree.error)
        self.assertGreater(int(tree.element_count or 0), 0)
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        res = validator.validate_ui_automation_tree(tree)
        self.assertTrue(res.valid, "arbol UIA invalido: %s" % res.reason)
        self.assertTrue(res.checks["window_identity"])
        self.assertTrue(res.checks["root_handle"])
        self.assertTrue(res.checks["process_identity"])
        self.assertTrue(res.checks["no_foreign_process"])
        self.assertTrue(res.checks["no_desktop_leak"])
        self.assertEqual(res.rejected_evidence, [])

    def test_validar_captura_region_ventana_notepad_real(self):
        """Region de captura real (mss) del rectangulo de Notepad pertenece a la ventana."""
        from src.eyes.capture.screen_capture import MssCapture

        win_rect = self._rectangulo_ventana(self.hwnd)
        left, top, right, bottom = win_rect
        cap = MssCapture()
        frame = cap.capture_region(left, top, right - left, bottom - top)
        cap.close()
        self.assertIsNotNone(frame, "captura real de la region de Notepad devolvio None")
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        res = validator.validate_capture_region(win_rect, backend="mss", source="MssCapture")
        self.assertTrue(res.valid, "captura de ventana invalida: %s" % res.reason)
        self.assertTrue(res.checks["geometria_dentro_de_ventana"])
        self.assertTrue(res.checks["no_evidencia_escritorio_entero"])

    def test_rechazar_captura_escritorio_entero_notepad_real(self):
        """Captura de escritorio entero (union de monitores) se rechaza como no separable."""
        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitores = list(screen_manager.monitors or [])
        self.assertGreater(len(monitores), 0)
        escritorio = (
            min(int(m.left) for m in monitores),
            min(int(m.top) for m in monitores),
            max(int(m.right) for m in monitores),
            max(int(m.bottom) for m in monitores),
        )
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        res = validator.validate_capture_region(escritorio, backend="mss", source="escritorio")
        self.assertFalse(res.valid, "escritorio entero debio rechazarse: %s" % res.reason)
        self.assertFalse(res.checks["no_evidencia_escritorio_entero"])
        self.assertIn("captura_escritorio_entero", res.rejected_evidence)

    def test_validar_candidatos_desde_arbol_uia_notepad_real(self):
        """Candidatos construidos del arbol UIA real pertenecen a la ventana de Notepad."""
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        candidatos = []
        for elem in tree.elements:
            x1, y1, x2, y2 = elem.bounding_rectangle
            candidatos.append(
                FusedCandidate(
                    canonical_id="uia_%d" % int(elem.handle or 0),
                    name=elem.name or "element",
                    type=elem.control_type or "element",
                    text=elem.name or "",
                    description="",
                    bbox=list(elem.bounding_rectangle),
                    center=[(x1 + x2) // 2, (y1 + y2) // 2],
                    screen=0,
                    window_handle=int(tree.window_handle or 0),
                    process_id=int(tree.process_id or 0),
                    sources=[],
                    merged_confidence=0.9,
                    agreement=True,
                    disagreements=[],
                    interactive=False,
                    interactive_evidence=[],
                    calibrated=False,
                )
            )
        self.assertGreater(len(candidatos), 0)
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        target_screen = validator._target_screen()
        for c in candidatos:
            c.screen = target_screen
        res = validator.validate_candidates(candidatos, screen=target_screen)
        self.assertTrue(res.valid, "candidatos invalidos: %s" % res.reason)
        self.assertTrue(res.checks["todos_candidatos_pertenecen_a_ventana"])
        self.assertEqual(res.rejected_evidence, [])

    def test_validar_candidato_window_handle_extrano_rechazado_notepad_real(self):
        """Candidato con window_handle ajeno se rechaza aunque su geometria este dentro."""
        win_rect = self._rectangulo_ventana(self.hwnd)
        left, top, right, bottom = win_rect
        val = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        target_screen = val._target_screen()
        cands = [
            FusedCandidate(
                canonical_id="extra",
                name="extra",
                type="button",
                text="extra",
                description="",
                bbox=(left + 10, top + 10, left + 60, top + 40),
                center=[left + 35, top + 25],
                screen=target_screen,
                window_handle=999999,
                process_id=self.pid,
                sources=[],
                merged_confidence=0.9,
                agreement=True,
                disagreements=[],
                interactive=False,
                interactive_evidence=[],
                calibrated=False,
            )
        ]
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        res = validator.validate_candidates(cands, screen=0)
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["todos_candidatos_pertenecen_a_ventana"])
        self.assertIn("candidato_0", res.rejected_evidence)

    def test_validar_todo_combinado_notepad_real(self):
        """Validacion combinada (arbol + captura + candidatos) sobre Notepad real."""
        from src.eyes.capture.screen_capture import MssCapture

        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        win_rect = self._rectangulo_ventana(self.hwnd)
        cap = MssCapture()
        frame = cap.capture_region(
            int(win_rect[0]), int(win_rect[1]),
            int(win_rect[2] - win_rect[0]), int(win_rect[3] - win_rect[1]),
        )
        cap.close()
        self.assertIsNotNone(frame)
        candidatos = []
        for elem in tree.elements:
            x1, y1, x2, y2 = elem.bounding_rectangle
            candidatos.append(
                FusedCandidate(
                    canonical_id="uia_%d" % int(elem.handle or 0),
                    name=elem.name or "element",
                    type=elem.control_type or "element",
                    text=elem.name or "",
                    description="",
                    bbox=list(elem.bounding_rectangle),
                    center=[(x1 + x2) // 2, (y1 + y2) // 2],
                    screen=0,
                    window_handle=int(tree.window_handle or 0),
                    process_id=int(tree.process_id or 0),
                    sources=[],
                    merged_confidence=0.9,
                    agreement=True,
                    disagreements=[],
                    interactive=False,
                    interactive_evidence=[],
                    calibrated=False,
                )
            )
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        target_screen = validator._target_screen()
        for c in candidatos:
            c.screen = target_screen
        res = validator.validate_all(
            tree=tree,
            capture_region=win_rect,
            candidates=candidatos,
            screen=target_screen,
            backend="mss",
            source="MssCapture",
        )
        self.assertTrue(res.valid, "validacion combinada fallo: %s" % res.reason)
        self.assertTrue(res.checks["arbol_uiA.window_identity"])
        self.assertTrue(res.checks["captura.geometria_dentro_de_ventana"])
        self.assertTrue(res.checks["candidatos.todos_candidatos_pertenecen_a_ventana"])

    def test_hwnd_inexistente_rechazado(self):
        """Validador con HWND inexistente rechaza cualquier validacion."""
        validator = WindowEvidenceValidator(0xBADF00D, target_pid=self.pid)
        res = validator.validate_capture_region((0, 0, 100, 100))
        self.assertFalse(res.valid)
        self.assertFalse(res.checks["window_exists"])
        res = validator.validate_all()
        self.assertFalse(res.valid)
        self.assertEqual(res.reason, "no hay evidencia que validar")

    def test_validar_geometria_candidatos_notepad_real(self):
        """La puerta de calidad geometrica acepta candidatos UIA reales con
        buena geometria y rechaza los degenerados u obstruidos del arbol real.
        No se exige que todos pasen: el arbol UIA real contiene elementos sin
        geometria util (caja (0,0,0,0) o fuera de pantalla)."""
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error)
        self.assertGreater(int(tree.element_count or 0), 0)
        win_rect = self._rectangulo_ventana(self.hwnd)
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        aceptados = 0
        rechazados = 0
        for elem in tree.elements:
            br = list(elem.bounding_rectangle)
            cand = SimpleNamespace(
                name=elem.name or "element",
                type=elem.control_type or "element",
                bbox=br,
                canonical_id="uia_%d" % int(elem.handle or 0),
                window_handle=int(tree.window_handle or 0),
                is_offscreen=bool(elem.is_offscreen),
                visible=bool(elem.visible),
            )
            res = validator.validate_geometria_candidato(
                cand, window_rect=win_rect)
            if res.valid:
                aceptados += 1
            else:
                # Toda rechazada de la puerta de geometria es una razon de
                # geometria (caja fuera de ventana, caja degenerada, control
                # obstruido, solapamiento ambiguo o espacio desconocido).
                rechazados += 1
                if not br or br[2] <= br[0] or br[3] <= br[1]:
                    self.assertIn(
                        "candidato:caja_degenerada", res.rejected_evidence,
                        "caja real degenerada debio rechazarse como tal: %s" % res.reason)
        self.assertGreater(
            aceptados, 0,
            "la puerta de geometria debio aceptar al menos un candidato real valido")

    def test_rechazar_candidato_geometria_degenerada_notepad_real(self):
        """Un candidato sintetico con caja degenerada se rechaza con la puerta
        de calidad geometrica sobre la ventana real de Notepad."""
        adapter = UIAutomationAdapter(timeout=8.0)
        tree = adapter.enumerate_window(self.hwnd, self.pid)
        self.assertIsNone(tree.error)
        win_rect = self._rectangulo_ventana(self.hwnd)
        validator = WindowEvidenceValidator(self.hwnd, target_pid=self.pid)
        # Candidato sintetico con caja degenerada (ancho cero).
        cand = SimpleNamespace(
            name="degenerado", type="button", bbox=[150, 150, 150, 190],
            canonical_id="sintetico_degenerado",
            window_handle=int(tree.window_handle or 0),
        )
        res = validator.validate_geometria_candidato(cand, window_rect=win_rect)
        self.assertFalse(res.valid, "caja degenerada debio rechazarse: %s" % res.reason)
        self.assertFalse(res.checks["caja_valida"])
        self.assertIn("candidato:caja_degenerada", res.rejected_evidence)
        # Un candidato real con buena geometria se acepta.
        validos = 0
        for elem in tree.elements:
            br = list(elem.bounding_rectangle)
            if br[2] > br[0] and br[3] > br[1]:
                cand2 = SimpleNamespace(
                    name=elem.name or "element",
                    type=elem.control_type or "element",
                    bbox=br,
                    canonical_id="uia_%d" % int(elem.handle or 0),
                    window_handle=int(tree.window_handle or 0),
                    is_offscreen=bool(elem.is_offscreen),
                    visible=bool(elem.visible),
                )
                res2 = validator.validate_geometria_candidato(
                    cand2, window_rect=win_rect)
                if res2.valid:
                    validos += 1
        self.assertGreater(validos, 0, "deben aceptarse candidatos reales validos")
