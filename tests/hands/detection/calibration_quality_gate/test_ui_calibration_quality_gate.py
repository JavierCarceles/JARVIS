"""
Tests unitarios (deterministas, sin SO ni GUI) de la puerta de calidad y
calibracion UI - unidad 3.8.6.4.8 del roadmap.

Cubren para src/hands/detection/calibration_quality_gate.py:
- confianza insuficiente (deteccion/semantica por debajo del umbral);
- identidad incorrecta (sin nombre/etiqueta usable, caja que no coincide con la
  verdad-terreno de la fixture);
- ventana oculta;
- control deshabilitado y fuera de pantalla;
- captura obsoleta;
- caja truncada o fuera de ventana/imagen, y solapamiento ambiguo;
- cambio entre deteccion y accion (control_box, estado UI, PID, foco, escala,
  resolucion).
- Fachada CalibrationQualityGate.evaluate (aceptado/rechazado/detectado no
  accionable).

Tests unitarios (sin SO ni GUI): adaptador de escritorio inyectado que devuelve
WindowInfo / DisplayInfo / WindowDpiInfo sinteticos. No se abren ventanas ni se
envian entradas.
"""

from __future__ import annotations

import unittest

from src.core.ui_element_model import ElementClassification
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DesktopPlatformAdapter,
    DisplayInfo,
    PlatformErrorCode,
    PlatformResult,
    Rect,
    WindowDpiInfo,
    WindowInfo,
)
from src.hands.detection.calibration_quality_gate import (
    ActionabilityStatus,
    CalibrationQualityGate,
    DIM_DETECTION,
    DIM_GEOMETRY,
    DIM_INTERACTIVITY,
    DIM_SEMANTIC,
    DetectionMethod,
    DetectionThresholds,
    DRIFT_PROCEED,
    DRIFT_RECAPTURE,
    DRIFT_RECALIBRATE,
    GateResult,
    MethodThresholds,
    QualityAssessment,
    assess_candidate,
    check_box_geometry,
    decide_actionability,
    take_detection_snapshot,
    verify_before_action,
)

WINDOW = Rect(0, 0, 1000, 800)
BOX_OK = Rect(100, 100, 200, 200)
BOX_FUERA = Rect(1000, 100, 1100, 200)
BOX_SOBRELAP = Rect(120, 120, 220, 220)
REFERENCIA_LEJANA = Rect(400, 400, 500, 500)


def _ev_uia(confidence=0.95, name="Aceptar", enabled=True, visible=True,
            offscreen=False, patterns=None, bbox=None, raw_extra=None):
    raw = {
        "name": name,
        "automation_id": "btnAceptar",
        "identifier": "btnAceptar",
        "is_enabled": enabled,
        "visible": visible,
        "is_offscreen": offscreen,
        "patterns": patterns if patterns is not None else ["Invoke"],
        "control_type": "Button",
        "native_role": "Button",
    }
    if raw_extra:
        raw.update(raw_extra)
    element = {"interactive": enabled and bool(patterns), "name": name}
    return {
        "source": "uia",
        "confidence": confidence,
        "available": True,
        "bbox": bbox,
        "raw": raw,
        "element": element,
    }


def _ev_qwen(confidence=0.80, label="boton", apparent_function="boton",
             bbox=None):
    return {
        "source": "qwen3vl",
        "confidence": confidence,
        "available": True,
        "bbox": bbox,
        "raw": {"label_association": label, "apparent_function": apparent_function},
        "element": {"name": label},
    }


def _candidate(sources=None, type="button", bbox=None, name="Aceptar", text="",
               description="", classification=ElementClassification.UIA_ACTIONABLE.value,
               interactive=False, canonical_id="btn1"):
    return {
        "sources": sources or [],
        "type": type,
        "bbox": bbox,
        "name": name,
        "text": text,
        "description": description,
        "classification": classification,
        "interactive": interactive,
        "canonical_id": canonical_id,
    }


def _thresholds():
    return DetectionThresholds.defaults()


def _assess(cand, thr=None, window_rect=WINDOW, reference_box=BOX_OK):
    return assess_candidate(
        cand, thresholds=thr or _thresholds(),
        window_rect=window_rect, reference_box=reference_box,
    )


# ---------------------------------------------------------------------------
# Adaptador de escritorio sintetico (inyeccion, sin SO ni GUI)
# ---------------------------------------------------------------------------

def _window(window_id=1001, pid=100, bounds=None, client_bounds=None,
            is_visible=True, is_minimized=False, display_id="d1",
            scale_factor=1.25, dpi=120):
    if bounds is None:
        bounds = Rect(100, 100, 900, 700)
    if client_bounds is None:
        client_bounds = Rect(110, 110, 890, 690)
    return WindowInfo(
        window_id=window_id, pid=pid, title="Notepad", app_identity="notepad",
        bounds=bounds, client_bounds=client_bounds,
        is_visible=is_visible, is_minimized=is_minimized, is_foreground=True,
        display_id=display_id, scale_factor=scale_factor, dpi=dpi,
        coordinate_space=DESKTOP_PIXELS,
    )


def _display(display_id="d1", name="Monitor", bounds=None,
             pixel_width=3840, pixel_height=2160, scale_factor=1.25,
             dpi=120, is_primary=True):
    if bounds is None:
        bounds = Rect(0, 0, pixel_width, pixel_height)
    return DisplayInfo(
        display_id=display_id, name=name, bounds=bounds, work_area=bounds,
        pixel_width=pixel_width, pixel_height=pixel_height,
        scale_factor=scale_factor, dpi=dpi, is_primary=is_primary,
        coordinate_space=DESKTOP_PIXELS,
    )


def _dpi_info(window_id=1001, dpi=120, scale_factor=1.25):
    return WindowDpiInfo(window_id=window_id, dpi=dpi, scale_factor=scale_factor)


class _FakeDesktopAdapter(DesktopPlatformAdapter):
    """Adaptador inyectado que devuelve estado de escritorio sintetico."""

    def __init__(self, window=None, foreground_window_id=None, displays=None,
                 dpi_info=None):
        super().__init__()
        self.platform_name = "fake"
        self.window = window
        self.foreground_window_id = foreground_window_id
        self.displays = list(displays or [])
        self.dpi_info = dpi_info
        self.calls = []

    def get_window(self, window_id):
        self.calls.append(("get_window", int(window_id)))
        if self.window is None:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "ventana no encontrada",
                operation="get_window", platform="fake",
            )
        return PlatformResult.success(self.window)

    def get_foreground_window(self):
        self.calls.append(("get_foreground_window",))
        if self.foreground_window_id is None:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "sin ventana en primer plano",
                operation="get_foreground_window", platform="fake",
            )
        return PlatformResult.success(
            WindowInfo(window_id=int(self.foreground_window_id), pid=0,
                       title="", app_identity=""))

    def enumerate_displays(self):
        self.calls.append(("enumerate_displays",))
        return PlatformResult.success(list(self.displays))

    def get_window_dpi_info(self, window_id):
        self.calls.append(("get_window_dpi_info", int(window_id)))
        if self.dpi_info is None:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "sin dpi",
                operation="get_window_dpi_info", platform="fake",
            )
        return PlatformResult.success(self.dpi_info)


def _base_adapter(window=None, foreground_window_id=1001, displays=None,
                  dpi_info=None):
    return _FakeDesktopAdapter(
        window=window or _window(),
        foreground_window_id=foreground_window_id,
        displays=displays or [_display()],
        dpi_info=dpi_info or _dpi_info(),
    )


def _base_snapshot(adapter=None):
    adapter = adapter or _base_adapter()
    snap = take_detection_snapshot(
        adapter, 1001,
        control_box=Rect(300, 300, 400, 400),
        ui_state_hash="hash1",
    )
    return adapter, snap


# ---------------------------------------------------------------------------
# Confianza insuficiente
# ---------------------------------------------------------------------------

class TestConfianzaInsuficiente(unittest.TestCase):
    """Fuentes por debajo del umbral no acreditan deteccion ni calidad."""

    def test_deteccion_falla_confianza_uia_por_debajo_del_umbral(self):
        cand = _candidate(sources=[_ev_uia(confidence=0.20, bbox=BOX_OK)],
                          bbox=BOX_OK)
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_DETECTION))
        self.assertFalse(a.passed)
        self.assertIn("ninguna fuente supera su umbral de confianza", a.reasons[0])

    def test_deteccion_falla_qwen3vl_confianza_insuficiente(self):
        cand = _candidate(sources=[_ev_qwen(confidence=0.20, bbox=BOX_OK)],
                          bbox=BOX_OK)
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_DETECTION))
        self.assertFalse(a.passed)

    def test_opencv_no_acredita_deteccion_por_si_sola(self):
        cand = _candidate(sources=[{
            "source": "opencv", "confidence": 0.9, "available": True,
            "bbox": BOX_OK, "raw": {}, "element": {},
        }], bbox=BOX_OK)
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_DETECTION))
        self.assertFalse(a.passed)

    def test_decide_actionability_calidad_insuficiente_por_confianza_baja(self):
        cand = _candidate(sources=[_ev_uia(confidence=0.20, patterns=["Invoke"],
                                           bbox=BOX_OK)], bbox=BOX_OK)
        a = _assess(cand)
        decision = decide_actionability(cand, assessment=a)
        self.assertFalse(decision.actionable)
        self.assertEqual(decision.status, ActionabilityStatus.INSUFFICIENT_QUALITY)
        self.assertTrue(decision.keep_logical_definition)


# ---------------------------------------------------------------------------
# Identidad incorrecta
# ---------------------------------------------------------------------------

class TestIdentidadIncorrecta(unittest.TestCase):
    """Sin identidad usable (nombre/etiqueta) la semantica falla; y una caja que
    no coincide con la verdad-terreno de la fixture falla la geometria."""

    def test_semantica_falla_sin_nombre_ni_etiqueta_usable(self):
        cand = _candidate(
            sources=[_ev_uia(name="", patterns=["Invoke"], bbox=BOX_OK,
                             raw_extra={"name": "", "automation_id": "",
                                        "identifier": ""})],
            bbox=BOX_OK, name="", text="", description="",
        )
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_SEMANTIC))
        self.assertFalse(a.passed)

    def test_semantica_falla_qwen_sin_label_ni_funcion(self):
        cand = _candidate(
            sources=[_ev_qwen(confidence=0.90, label="",
                              apparent_function="", bbox=BOX_OK)],
            bbox=BOX_OK,
        )
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_SEMANTIC))
        self.assertFalse(a.passed)

    def test_geometria_falla_error_de_centro_alto_respecto_a_referencia(self):
        cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
        a = _assess(cand, reference_box=REFERENCIA_LEJANA)
        self.assertFalse(a.dimension_passed(DIM_GEOMETRY))
        self.assertFalse(a.passed)
        self.assertIn("error de centro", a.dimensions[DIM_GEOMETRY].reason)

    def test_geometria_falla_iou_bajo_respecto_a_referencia(self):
        cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
        a = _assess(cand, reference_box=REFERENCIA_LEJANA)
        self.assertLess(a.dimensions[DIM_GEOMETRY].value["iou_with_reference"],
                        0.15)
        self.assertFalse(a.passed)

    def test_decide_actionability_sin_identidad_no_conserva_definicion_util(self):
        cand = _candidate(
            sources=[_ev_uia(name="", patterns=[], bbox=BOX_OK,
                             raw_extra={"name": "", "automation_id": "",
                                        "identifier": ""})],
            bbox=BOX_OK, name="", text="", description="",
            classification=ElementClassification.DISABLED.value,
        )
        a = _assess(cand)
        decision = decide_actionability(cand, assessment=a)
        self.assertFalse(decision.actionable)
        self.assertFalse(decision.keep_logical_definition)
        self.assertEqual(decision.logical_definition, {})


# ---------------------------------------------------------------------------
# Ventana oculta
# ---------------------------------------------------------------------------

class TestVentanaOculta(unittest.TestCase):
    """Un control en ventana no visible no es accionable y no se reutiliza su
    deteccion antes de actuar."""

    def test_decide_actionability_control_oculto_es_offscreen(self):
        cand = _candidate(sources=[_ev_uia(visible=False, patterns=["Invoke"],
                                           bbox=BOX_OK)],
                          bbox=BOX_OK, classification=ElementClassification.OFFSCREEN.value)
        decision = decide_actionability(cand)
        self.assertFalse(decision.actionable)
        self.assertEqual(decision.status, ActionabilityStatus.OFFSCREEN)

    def test_assess_interactividad_falla_control_oculto(self):
        cand = _candidate(sources=[_ev_uia(visible=False, patterns=["Invoke"],
                                           bbox=BOX_OK)], bbox=BOX_OK)
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_INTERACTIVITY))
        self.assertFalse(a.passed)

    def test_verify_before_action_ventana_oculta_devuelve_recapture(self):
        _, snap = _base_snapshot()
        adapter = _base_adapter(window=_window(is_visible=False))
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("window_hidden", drift.changes)


# ---------------------------------------------------------------------------
# Control deshabilitado y fuera de pantalla
# ---------------------------------------------------------------------------

class TestControlDeshabilitadoFueraPantalla(unittest.TestCase):
    """Controles deshabilitados o fuera de pantalla no se calibran como
    accionables, aunque se conserva su definicion logica."""

    def test_decide_actionability_control_deshabilitado(self):
        cand = _candidate(sources=[_ev_uia(enabled=False, patterns=["Invoke"],
                                           bbox=BOX_OK)],
                          bbox=BOX_OK,
                          classification=ElementClassification.DISABLED.value)
        decision = decide_actionability(cand)
        self.assertFalse(decision.actionable)
        self.assertEqual(decision.status, ActionabilityStatus.DISABLED)
        self.assertEqual(decision.reason, "control deshabilitado")
        self.assertTrue(decision.keep_logical_definition)

    def test_decide_actionability_control_fuera_de_pantalla(self):
        cand = _candidate(sources=[_ev_uia(offscreen=True, patterns=["Invoke"],
                                           bbox=BOX_OK)],
                          bbox=BOX_OK,
                          classification=ElementClassification.OFFSCREEN.value)
        decision = decide_actionability(cand)
        self.assertFalse(decision.actionable)
        self.assertEqual(decision.status, ActionabilityStatus.OFFSCREEN)
        self.assertEqual(decision.reason, "control fuera de pantalla o no visible")

    def test_assess_interactividad_falla_control_deshabilitado(self):
        cand = _candidate(sources=[_ev_uia(enabled=False, patterns=["Invoke"],
                                           bbox=BOX_OK)], bbox=BOX_OK)
        a = _assess(cand)
        self.assertFalse(a.dimension_passed(DIM_INTERACTIVITY))
        self.assertFalse(a.passed)


# ---------------------------------------------------------------------------
# Captura obsoleta
# ---------------------------------------------------------------------------

class TestCapturaObsoleta(unittest.TestCase):
    """Una captura demasiado antigua obliga a recapturar antes de actuar."""

    def test_verify_before_action_captura_obsoleta_devuelve_recapture(self):
        adapter = _base_adapter()
        snap_vieja = take_detection_snapshot(
            adapter, 1001,
            control_box=Rect(300, 300, 400, 400),
            ui_state_hash="hash1",
            clock=lambda: 1000.0,
        )
        drift = verify_before_action(snap_vieja, adapter, max_age_seconds=1.0)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("capture_stale", drift.changes)
        self.assertGreater(drift.details["age_seconds"], 1.0)

    def test_verify_before_action_sin_max_age_no_marca_captura_obsoleta(self):
        adapter, snap = _base_snapshot()
        drift = verify_before_action(snap, adapter)
        self.assertEqual(drift.action, DRIFT_PROCEED)
        self.assertTrue(drift.unchanged)


# ---------------------------------------------------------------------------
# Caja truncada
# ---------------------------------------------------------------------------

class TestCajaTruncada(unittest.TestCase):
    """Una caja vacia, fuera de la ventana objetivo, fuera de la captura o
    solapada ambiguamente se rechaza."""

    def test_check_box_geometry_caja_fuera_de_ventana(self):
        cand = _candidate(bbox=BOX_FUERA)
        razones, ambiguo = check_box_geometry(cand, [], window_rect=WINDOW)
        self.assertFalse(ambiguo)
        self.assertTrue(any("fuera de la ventana objetivo" in r for r in razones))

    def test_check_box_geometry_caja_fuera_de_imagen(self):
        cand = _candidate(bbox=Rect(600, 100, 700, 200))
        razones, ambiguo = check_box_geometry(cand, [], image_rect=Rect(0, 0, 500, 500))
        self.assertFalse(ambiguo)
        self.assertTrue(any("fuera de la imagen o captura" in r for r in razones))

    def test_check_box_geometry_caja_vacia_o_degenerada(self):
        cand = _candidate(bbox=None)
        razones, ambiguo = check_box_geometry(cand, [])
        self.assertFalse(ambiguo)
        self.assertTrue(any("caja vacia, ausente o degenerada" in r for r in razones))

    def test_check_box_geometry_solapamiento_ambiguo_distinta_identidad(self):
        c1 = _candidate(bbox=BOX_OK, canonical_id="c1")
        c2 = _candidate(bbox=BOX_SOBRELAP, canonical_id="c2")
        razones, ambiguo = check_box_geometry(c1, [c1, c2])
        self.assertTrue(ambiguo)
        self.assertTrue(any("solapamiento ambiguo" in r for r in razones))

    def test_assess_geometria_falla_caja_truncada_fuera_de_ventana(self):
        cand = _candidate(sources=[_ev_uia(bbox=BOX_FUERA)], bbox=BOX_FUERA)
        a = _assess(cand, window_rect=WINDOW)
        self.assertFalse(a.dimension_passed(DIM_GEOMETRY))
        self.assertFalse(a.passed)
        self.assertIn("fuera de la ventana objetivo",
                      a.dimensions[DIM_GEOMETRY].reason)


# ---------------------------------------------------------------------------
# Cambio entre deteccion y accion
# ---------------------------------------------------------------------------

class TestCambioEntreDeteccionYAccion(unittest.TestCase):
    """Cualquier deriva entre la deteccion y el momento de actuar impide
    reutilizarla: recapture para foco/monitor/geometria/caja/estado, recalibrate
    para identidad/escala/resolucion/topologia."""

    def test_sin_cambios_devuelve_proceed(self):
        adapter, snap = _base_snapshot()
        drift = verify_before_action(snap, adapter)
        self.assertTrue(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_PROCEED)
        self.assertEqual(drift.changes, [])
        self.assertIn("sin cambios", drift.reason)

    def test_caja_control_cambia_devuelve_recapture(self):
        _, snap = _base_snapshot()
        drift = verify_before_action(
            snap, _base_adapter(),
            current_control_box=Rect(500, 500, 600, 600))
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("control_box_changed", drift.changes)

    def test_estado_ui_cambia_devuelve_recapture(self):
        _, snap = _base_snapshot()
        drift = verify_before_action(snap, _base_adapter(),
                                     current_ui_state_hash="hash2")
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("ui_state_changed", drift.changes)

    def test_pid_cambia_devuelve_recalibrate(self):
        _, snap = _base_snapshot()
        adapter = _base_adapter(window=_window(pid=999))
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("pid_changed", drift.changes)

    def test_foco_pierde_devuelve_recapture(self):
        _, snap = _base_snapshot()
        adapter = _base_adapter(foreground_window_id=2002)
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("focus_lost", drift.changes)

    def test_ventana_no_legible_devuelve_recalibrate(self):
        _, snap = _base_snapshot()
        adapter = _FakeDesktopAdapter(window=None, foreground_window_id=1001,
                                      displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("window_gone", drift.changes)

    def test_escala_cambia_devuelve_recalibrate(self):
        _, snap = _base_snapshot()
        adapter = _base_adapter(
            window=_window(scale_factor=1.0),
            displays=[_display(scale_factor=1.0)],
            dpi_info=_dpi_info(scale_factor=1.0))
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("scale_changed", drift.changes)

    def test_resolucion_cambia_devuelve_recalibrate(self):
        _, snap = _base_snapshot()
        adapter = _base_adapter(
            displays=[_display(pixel_width=1920, pixel_height=1080,
                               scale_factor=1.25, dpi=120)],
            dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("resolution_changed", drift.changes)


# ---------------------------------------------------------------------------
# Fachada CalibrationQualityGate.evaluate
# ---------------------------------------------------------------------------

class TestFachadaPuertaCalidad(unittest.TestCase):
    """CalibrationQualityGate.evaluate combina geometria, dimensiones y
    accionabilidad sobre un conjunto de candidatos."""

    def test_evaluate_acepta_valido_y_rechaza_deshabilitado(self):
        thr = _thresholds()
        gate = CalibrationQualityGate(thresholds=thr)
        valido = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK,
                            canonical_id="btnBueno")
        deshabilitado = _candidate(
            sources=[_ev_uia(enabled=False, patterns=["Invoke"],
                             bbox=Rect(300, 300, 400, 400))],
            bbox=Rect(300, 300, 400, 400),
            classification=ElementClassification.DISABLED.value,
            canonical_id="btnDeshabilitado",
        )
        resultado: GateResult = gate.evaluate([valido, deshabilitado],
                                              window_rect=WINDOW)
        self.assertIn(valido, resultado.accepted)
        self.assertTrue(any(c is deshabilitado for c, _ in resultado.rejected))
        decision = resultado.decisions["btnDeshabilitado"]
        self.assertFalse(decision.actionable)
        self.assertEqual(decision.status, ActionabilityStatus.DISABLED)

    def test_evaluate_detectado_ok_pero_sin_interactividad_va_a_detected_not_actionable(self):
        thr = _thresholds()
        gate = CalibrationQualityGate(thresholds=thr)
        cand = _candidate(sources=[_ev_qwen(bbox=BOX_OK)], bbox=BOX_OK,
                          canonical_id="btnVisual",
                          classification=ElementClassification.TEXT_LABEL.value,
                          interactive=False)
        resultado: GateResult = gate.evaluate([cand], window_rect=WINDOW,
                                              reference_boxes={"btnVisual": BOX_OK})
        self.assertTrue(any(c is cand for c in resultado.detected_not_actionable))
        self.assertFalse(resultado.decisions["btnVisual"].actionable)
        self.assertEqual(resultado.decisions["btnVisual"].status,
                         ActionabilityStatus.NOT_VERIFIED_INTERACTIVITY)

    def test_evaluate_umbral_personalizado_rechaza_confianza_baja(self):
        thr = DetectionThresholds.defaults()
        thr.set(DetectionMethod.QWEN3VL.value, "button",
                MethodThresholds(min_detection_confidence=0.90))
        gate = CalibrationQualityGate(thresholds=thr)
        cand = _candidate(sources=[_ev_qwen(confidence=0.80, bbox=BOX_OK)],
                          bbox=BOX_OK, canonical_id="btnBajo")
        resultado: GateResult = gate.evaluate([cand], window_rect=WINDOW,
                                              reference_boxes={"btnBajo": BOX_OK})
        self.assertEqual(len(resultado.accepted), 0)
        self.assertEqual(resultado.decisions["btnBajo"].status,
                         ActionabilityStatus.INSUFFICIENT_QUALITY)


if __name__ == "__main__":
    unittest.main()
