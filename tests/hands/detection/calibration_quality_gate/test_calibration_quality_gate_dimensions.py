# -*- coding: utf-8 -*-
"""
Tests unitarios (deterministas, sin SO ni GUI) de la separacion de las cuatro
dimensiones de calidad de la puerta de calibracion (unidad 3.8.6.4.4 del
roadmap).

Cuben: confianza de deteccion, confianza semantica, evidencia de
interactividad y precision geometrica como dimensiones independientes;
QualityAssessment.passed exige que pasen las cuatro y ninguna puntuacion
agregada compensa una dimension insuficiente.
"""

import pytest  # noqa: E402

from src.core.ui_element_model import ElementClassification
from src.desktop.platform_contract import Rect
from src.hands.detection.calibration_quality_gate import (
    ActionabilityStatus,
    ALL_DIMENSIONS,
    DetectionMethod,
    DIM_DETECTION,
    DIM_GEOMETRY,
    DIM_INTERACTIVITY,
    DIM_SEMANTIC,
    DetectionThresholds,
    MethodThresholds,
    QualityAssessment,
    assess_candidate,
    decide_actionability,
)

WINDOW = Rect(0, 0, 1000, 800)
BOX_OK = Rect(100, 100, 200, 200)


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


def _ev_qwen(confidence=0.80, label="boton", bbox=None):
    return {
        "source": "qwen3vl",
        "confidence": confidence,
        "available": True,
        "bbox": bbox,
        "raw": {"label_association": label, "apparent_function": "boton"},
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


def _default_thresholds():
    return DetectionThresholds.defaults()


# ---------------------------------------------------------------------------
# Estructura de las cuatro dimensiones
# ---------------------------------------------------------------------------

def test_cuatro_dimensiones_independientes_y_distintas():
    assert ALL_DIMENSIONS == (DIM_DETECTION, DIM_SEMANTIC, DIM_INTERACTIVITY, DIM_GEOMETRY)
    nombres = [DIM_DETECTION, DIM_SEMANTIC, DIM_INTERACTIVITY, DIM_GEOMETRY]
    assert len(set(nombres)) == 4
    assert DIM_DETECTION == "detection_confidence"
    assert DIM_SEMANTIC == "semantic_confidence"
    assert DIM_INTERACTIVITY == "interactivity_evidence"
    assert DIM_GEOMETRY == "geometric_precision"


def test_quality_assessment_expone_cuatro_dimensiones():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert isinstance(a, QualityAssessment)
    assert set(a.dimensions.keys()) == set(ALL_DIMENSIONS)
    assert all(d.passed for d in a.dimensions.values())
    assert a.passed is True
    assert a.detected_ok is True


# ---------------------------------------------------------------------------
# Ninguna puntuacion agregada compensa una dimension insuficiente
# ---------------------------------------------------------------------------

def test_interactividad_insuficiente_no_es_compensada_por_las_otras_tres():
    """Deteccion, semantica y geometria pasan; interactividad solo visual -> no aprueba."""
    cand = _candidate(
        sources=[_ev_qwen(bbox=BOX_OK)],
        bbox=BOX_OK,
        interactive=False,
        classification="button",
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.dimension_passed(DIM_DETECTION) is True
    assert a.dimension_passed(DIM_SEMANTIC) is True
    assert a.dimension_passed(DIM_GEOMETRY) is True
    assert a.dimension_passed(DIM_INTERACTIVITY) is False
    assert a.passed is False
    assert any(DIM_INTERACTIVITY in r for r in a.reasons)


def test_deteccion_falla_proveedor_desconocido_no_aprueba():
    cand = _candidate(
        sources=[{"source": "fuente_rara", "confidence": 0.9, "available": True,
                  "bbox": BOX_OK, "raw": {}, "element": {}}],
        bbox=BOX_OK,
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.dimension_passed(DIM_DETECTION) is False
    assert a.passed is False


def test_semantica_falla_sin_identidad_no_aprueba():
    cand = _candidate(
        sources=[_ev_uia(name="", patterns=["Invoke"], bbox=BOX_OK,
                         raw_extra={"name": "", "automation_id": "", "identifier": ""})],
        bbox=BOX_OK,
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.dimension_passed(DIM_SEMANTIC) is False
    assert a.passed is False


def test_interactividad_falla_control_deshabilitado_no_aprueba():
    cand = _candidate(
        sources=[_ev_uia(enabled=False, patterns=["Invoke"], bbox=BOX_OK)],
        bbox=BOX_OK,
        classification=ElementClassification.DISABLED.value,
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.dimension_passed(DIM_INTERACTIVITY) is False
    assert a.passed is False


def test_geometria_falla_caja_fuera_de_ventana_no_aprueba():
    cand = _candidate(
        sources=[_ev_uia(bbox=BOX_OK)],
        bbox=Rect(1000, 100, 1100, 200),
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.dimension_passed(DIM_GEOMETRY) is False
    assert a.passed is False


def test_geometria_falla_error_de_centro_alto_no_aprueba():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    referencia_lejos = Rect(400, 400, 500, 500)
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=referencia_lejos)
    assert a.dimension_passed(DIM_GEOMETRY) is False
    assert a.passed is False


def test_geometria_falla_sin_referencia_verificable_no_aprueba():
    cand = _candidate(sources=[_ev_qwen(bbox=BOX_OK)], bbox=BOX_OK)
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW)
    assert a.dimension_passed(DIM_GEOMETRY) is False
    assert a.passed is False


# ---------------------------------------------------------------------------
# detected_ok es distinta de passed (deteccion+semantica+geometria sin interactividad)
# ---------------------------------------------------------------------------

def test_detected_ok_puede_ser_true_cuando_interactividad_no_pasa():
    cand = _candidate(
        sources=[_ev_qwen(bbox=BOX_OK)],
        bbox=BOX_OK,
        interactive=False,
        classification="button",
    )
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    assert a.detected_ok is True
    assert a.passed is False


# ---------------------------------------------------------------------------
# Umbrales por metodo y control afectan a cada dimension de forma independiente
# ---------------------------------------------------------------------------

def test_umbral_personalizado_por_metodo_afecta_solo_la_dimension_de_esa_medida():
    thr = DetectionThresholds.defaults()
    thr.set(DetectionMethod.QWEN3VL.value, "button",
            MethodThresholds(min_detection_confidence=0.90, min_semantic_confidence=0.30))
    cand = _candidate(sources=[_ev_qwen(confidence=0.80, bbox=BOX_OK)], bbox=BOX_OK)
    # Con umbral 0.30 por defecto aprueba deteccion.
    a_def = assess_candidate(cand, thresholds=_default_thresholds(),
                             window_rect=WINDOW, reference_box=BOX_OK)
    assert a_def.dimension_passed(DIM_DETECTION) is True
    # Con umbral 0.90 para qwen3vl, deteccion falla y arrastra el conjunto.
    a_personal = assess_candidate(cand, thresholds=thr,
                                  window_rect=WINDOW, reference_box=BOX_OK)
    assert a_personal.dimension_passed(DIM_DETECTION) is False
    assert a_personal.passed is False


# ---------------------------------------------------------------------------
# Serializacion
# ---------------------------------------------------------------------------

def test_to_dict_serializa_cuatro_dimensiones_y_estado():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    a = assess_candidate(cand, thresholds=_default_thresholds(),
                         window_rect=WINDOW, reference_box=BOX_OK)
    d = a.to_dict()
    assert d["passed"] is True
    assert d["detected_ok"] is True
    assert set(d["dimensions"].keys()) == set(ALL_DIMENSIONS)
    for nombre in ALL_DIMENSIONS:
        dim = d["dimensions"][nombre]
        assert "name" in dim and "value" in dim and "threshold" in dim
        assert "passed" in dim and "reason" in dim and "details" in dim


# ---------------------------------------------------------------------------
# Integracion con la decision de accionabilidad del mismo modulo
# ---------------------------------------------------------------------------

def test_decide_actionability_aprueba_cuando_todas_las_dimensiones_pasan():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    decision = decide_actionability(cand)
    assert decision.actionable is True
    assert decision.status == ActionabilityStatus.ACTIONABLE
    assert decision.keep_logical_definition is True
    assert "canonical_id" in decision.logical_definition


def test_decide_actionability_no_aprueba_si_interactividad_no_verificada():
    cand = _candidate(
        sources=[_ev_uia(patterns=[], bbox=BOX_OK)],
        bbox=BOX_OK,
        interactive=False,
        classification="button",
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.NOT_VERIFIED_INTERACTIVITY
    assert decision.keep_logical_definition is True
    assert "canonical_id" in decision.logical_definition


# ---------------------------------------------------------------------------
# Estados no accionables de la puerta de calidad (unidad 3.8.6.4.5)
# ---------------------------------------------------------------------------

def test_decide_actionability_control_deshabilitado_no_es_accionable():
    cand = _candidate(
        sources=[_ev_uia(enabled=False, patterns=["Invoke"], bbox=BOX_OK)],
        bbox=BOX_OK,
        classification=ElementClassification.DISABLED.value,
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.DISABLED
    assert decision.reason == "control deshabilitado"
    assert decision.keep_logical_definition is True
    assert decision.logical_definition["canonical_id"] == "btn1"


def test_decide_actionability_control_fuera_de_pantalla_no_es_accionable():
    cand = _candidate(
        sources=[_ev_uia(offscreen=True, patterns=["Invoke"], bbox=BOX_OK)],
        bbox=BOX_OK,
        classification=ElementClassification.OFFSCREEN.value,
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.OFFSCREEN
    assert decision.reason == "control fuera de pantalla o no visible"
    assert decision.keep_logical_definition is True


def test_decide_actionability_control_cubierto_no_es_accionable():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    decision = decide_actionability(cand, covered=True)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.COVERED
    assert decision.reason == "control cubierto por otra ventana o elemento"
    assert decision.keep_logical_definition is True


def test_decide_actionability_control_ambiguo_no_es_accionable():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    decision = decide_actionability(cand, ambiguous=True)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.AMBIGUOUS
    assert decision.reason == "solapamiento ambiguo con otro control"
    assert decision.keep_logical_definition is True


def test_decide_actionability_elemento_transitorio_no_es_accionable():
    cand = _candidate(
        sources=[_ev_uia(patterns=["Invoke"], bbox=BOX_OK,
                         raw_extra={"control_type": "Menu", "native_role": "Menu"})],
        bbox=BOX_OK,
        type="menu",
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.TRANSIENT
    assert decision.reason == "elemento transitorio (menu, popup o tooltip)"
    assert decision.keep_logical_definition is True


def test_decide_actionability_transiente_por_parametro_no_es_accionable():
    cand = _candidate(sources=[_ev_uia(bbox=BOX_OK)], bbox=BOX_OK)
    decision = decide_actionability(cand, transient=True)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.TRANSIENT
    assert decision.keep_logical_definition is True


def test_decide_actionability_proveedor_desconocido_no_es_accionable():
    cand = _candidate(
        sources=[{"source": "fuente_rara", "confidence": 0.9, "available": True,
                  "bbox": BOX_OK, "raw": {}, "element": {}}],
        bbox=BOX_OK,
        name="Boton sin fuente conocida",
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.UNKNOWN_PROVIDER
    assert decision.reason == "proveedor de deteccion desconocido"
    assert decision.keep_logical_definition is True
    assert decision.logical_definition["name"] == "Boton sin fuente conocida"


def test_decide_actionability_calidad_insuficiente_no_es_accionable():
    cand = _candidate(
        sources=[_ev_qwen(confidence=0.10, bbox=BOX_OK)],
        bbox=BOX_OK,
        interactive=False,
        classification="button",
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.INSUFFICIENT_QUALITY
    assert decision.keep_logical_definition is True


def test_decide_actionability_orden_prioridad_deshabilitado_antes_que_interactividad():
    cand = _candidate(
        sources=[_ev_uia(enabled=False, patterns=["Invoke"], bbox=BOX_OK)],
        bbox=BOX_OK,
        classification=ElementClassification.DISABLED.value,
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.DISABLED
    assert decision.status != ActionabilityStatus.NOT_VERIFIED_INTERACTIVITY


def test_decide_actionability_sin_definicion_logica_util_no_la_conserva():
    cand = _candidate(
        sources=[_ev_uia(enabled=False, patterns=[], bbox=BOX_OK,
                         raw_extra={"name": "", "automation_id": "", "identifier": ""})],
        bbox=BOX_OK,
        name="",
        text="",
        description="",
        classification=ElementClassification.DISABLED.value,
    )
    decision = decide_actionability(cand)
    assert decision.actionable is False
    assert decision.status == ActionabilityStatus.DISABLED
    assert decision.keep_logical_definition is False
    assert decision.logical_definition == {}
