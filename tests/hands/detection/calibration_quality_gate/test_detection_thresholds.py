# -*- coding: utf-8 -*-
"""
Tests unitarios (deterministas, sin SO ni GUI) de la puerta de calidad y los
umbrales de deteccion (unidad 3.8.6.4.3 del roadmap).

Cubren: umbrales por metodo (accesibilidad, OmniParser, OCR, OpenCV, Qwen3-VL)
y por tipo de control, derivacion a partir de mediciones de fixture, congelado
antes de la aceptacion y persistencia. Todos los umbrales son relativos
(confianzas 0..1, IoU, ratios de centro y tamano); nunca pixeles absolutos.
"""

import os
import tempfile

import pytest  # noqa: E402

from src.hands.detection.calibration_quality_gate import (
    DetectionMethod,
    DetectionThresholds,
    MethodThresholds,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_PENDING,
    ThresholdsFrozenError,
    ThresholdsIntegrityError,
    WILDCARD_CONTROL_TYPE,
)


# ---------------------------------------------------------------------------
# Fixtures de mediciones de fixture (verdaderos positivos y falsos positivos)
# ---------------------------------------------------------------------------

def _medicion(method, control_type, confidence, semantic_confidence, iou,
              center_error_ratio, is_true_positive):
    return {
        "method": method,
        "control_type": control_type,
        "confidence": confidence,
        "semantic_confidence": semantic_confidence,
        "iou": iou,
        "center_error_ratio": center_error_ratio,
        "is_true_positive": is_true_positive,
    }


def _mediciones_button_accesibilidad():
    """5 verdaderos positivos y 3 falsos positivos para botones por accesibilidad."""
    return [
        _medicion("accessibility", "button", 0.95, 0.90, 0.90, 0.02, True),
        _medicion("accessibility", "button", 0.92, 0.88, 0.88, 0.03, True),
        _medicion("accessibility", "button", 0.90, 0.85, 0.85, 0.05, True),
        _medicion("accessibility", "button", 0.88, 0.80, 0.82, 0.07, True),
        _medicion("accessibility", "button", 0.85, 0.78, 0.80, 0.09, True),
        _medicion("accessibility", "button", 0.60, 0.50, 0.50, 0.20, False),
        _medicion("accessibility", "button", 0.55, 0.45, 0.45, 0.25, False),
        _medicion("accessibility", "button", 0.50, 0.40, 0.40, 0.30, False),
    ]


# ---------------------------------------------------------------------------
# Umbrales por defecto (valor de partida, pendiente de medicion en fixture)
# ---------------------------------------------------------------------------

def test_default_thresholds_por_metodo_son_relativos_y_por_control_comodin():
    t = DetectionThresholds.defaults()
    assert t.source == "defaults"
    assert not t.is_frozen

    esperados = {
        DetectionMethod.ACCESSIBILITY.value: 0.30,
        DetectionMethod.OMNIPARSER.value: 0.25,
        DetectionMethod.OCR.value: 0.50,
        DetectionMethod.QWEN3VL.value: 0.30,
    }
    for metodo, conf in esperados.items():
        thr = t.get(metodo, WILDCARD_CONTROL_TYPE)
        assert thr.min_detection_confidence == conf
        assert thr.status == MEASUREMENT_STATUS_PENDING
        assert thr.samples == 0

    # OpenCV no acredita deteccion por si sola (umbral > 1.0).
    thr_opencv = t.get(DetectionMethod.OPENCV.value, WILDCARD_CONTROL_TYPE)
    assert thr_opencv.min_detection_confidence > 1.0
    assert not DetectionMethod.OPENCV.can_detect_alone


def test_default_thresholds_no_usen_pixeles_absolutos():
    """Todos los umbrales son relativos: confianzas 0..1, IoU, ratios."""
    t = DetectionThresholds.defaults()
    for metodo in DetectionMethod:
        thr = t.get(metodo.value, WILDCARD_CONTROL_TYPE)
        assert 0.0 <= thr.min_detection_confidence <= 1.01
        assert 0.0 <= thr.min_semantic_confidence <= 1.01
        assert 0.0 <= thr.max_center_error_ratio <= 1.0
        assert 0.0 <= thr.min_iou_with_reference <= 1.0
        assert 0.0 <= thr.max_ambiguous_iou <= 1.0
        assert thr.min_box_size_ratio >= 0.0


# ---------------------------------------------------------------------------
# Busqueda por tipo de control con fallback a comodin "*"
# ---------------------------------------------------------------------------

def test_get_umbral_tipo_concreto_con_fallback_a_comodin():
    t = DetectionThresholds.defaults()
    # Ningun tipo concreto definido -> fallback al comodin "*".
    thr_boton = t.get(DetectionMethod.ACCESSIBILITY.value, "button")
    thr_comodin = t.get(DetectionMethod.ACCESSIBILITY.value, WILDCARD_CONTROL_TYPE)
    assert thr_boton.min_detection_confidence == thr_comodin.min_detection_confidence
    assert thr_boton.notes == thr_comodin.notes


def test_get_umbral_metodo_desconocido_devuelve_valores_genericos():
    t = DetectionThresholds.defaults()
    thr = t.get("metodo_inexistente", "button")
    assert thr.min_detection_confidence == MethodThresholds().min_detection_confidence
    assert "sin umbrales definidos" in thr.notes


# ---------------------------------------------------------------------------
# Derivacion a partir de mediciones de la fixture
# ---------------------------------------------------------------------------

def test_derivar_umbrales_desde_mediciones_marcadas_como_medidas():
    t = DetectionThresholds.derive_from_measurements(
        _mediciones_button_accesibilidad(), tp_quantile=0.05, min_samples=5
    )
    assert t.source == "measured"
    thr = t.get(DetectionMethod.ACCESSIBILITY.value, "button")
    assert thr.status == MEASUREMENT_STATUS_MEASURED
    assert thr.samples == 5
    # La confianza minima separa verdaderos positivos de falsos positivos:
    # superior al mejor falso positivo y cercana al peor TP.
    mejores_fp = max(r["confidence"] for r in _mediciones_button_accesibilidad() if not r["is_true_positive"])
    assert mejores_fp < thr.min_detection_confidence <= 0.90
    assert thr.min_detection_confidence > mejores_fp
    assert "mediciones" in thr.notes or "falso positivo" in thr.notes


def test_derivar_con_muestras_insuficientes_conserva_valor_de_partida():
    poucas = _mediciones_button_accesibilidad()[:3]  # solo 3 verdaderos positivos < 5
    t = DetectionThresholds.derive_from_measurements(
        poucas, tp_quantile=0.05, min_samples=5
    )
    thr = t.get(DetectionMethod.ACCESSIBILITY.value, "button")
    assert thr.status == MEASUREMENT_STATUS_PENDING
    assert thr.samples == 3
    assert thr.min_detection_confidence == 0.30  # valor de partida conservado
    assert "muestras insuficientes" in thr.notes


def test_derivar_establece_umbrales_de_semantica_iou_y_error_de_centro():
    t = DetectionThresholds.derive_from_measurements(
        _mediciones_button_accesibilidad(), tp_quantile=0.05, min_samples=5
    )
    thr = t.get(DetectionMethod.ACCESSIBILITY.value, "button")
    assert thr.min_semantic_confidence > 0.0
    assert 0.0 < thr.min_iou_with_reference <= 1.0
    assert 0.0 < thr.max_center_error_ratio <= 1.0


def test_derivar_agrupa_por_tipo_concreto_y_comodin():
    mediciones = _mediciones_button_accesibilidad() + [
        _medicion("accessibility", "textbox", 0.93, 0.89, 0.89, 0.03, True),
        _medicion("accessibility", "textbox", 0.91, 0.87, 0.87, 0.04, True),
        _medicion("accessibility", "textbox", 0.89, 0.85, 0.85, 0.05, True),
        _medicion("accessibility", "textbox", 0.87, 0.82, 0.82, 0.06, True),
        _medicion("accessibility", "textbox", 0.85, 0.80, 0.80, 0.08, True),
    ]
    t = DetectionThresholds.derive_from_measurements(
        mediciones, tp_quantile=0.05, min_samples=5
    )
    thr_boton = t.get(DetectionMethod.ACCESSIBILITY.value, "button")
    thr_texto = t.get(DetectionMethod.ACCESSIBILITY.value, "textbox")
    assert thr_boton.status == MEASUREMENT_STATUS_MEASURED
    assert thr_texto.status == MEASUREMENT_STATUS_MEASURED
    # El comodin recibe todas las filas del metodo.
    thr_comodin = t.get(DetectionMethod.ACCESSIBILITY.value, WILDCARD_CONTROL_TYPE)
    assert thr_comodin.status == MEASUREMENT_STATUS_MEASURED


# ---------------------------------------------------------------------------
# Congelado: fijar antes de la aceptacion, no cambiar despues de ver un fallo
# ---------------------------------------------------------------------------

def test_freeze_bloquea_modificaciones_posteriores():
    t = DetectionThresholds.derive_from_measurements(
        _mediciones_button_accesibilidad(), tp_quantile=0.05, min_samples=5
    )
    fingerprint_antes = t.fingerprint()
    t.freeze(reason="Aceptacion 3.8.6.4.3: umbrales medidos en fixture, fijados antes de aceptar")
    assert t.is_frozen
    assert t.frozen_reason
    assert t.frozen_at
    assert t.frozen_fingerprint == fingerprint_antes

    with pytest.raises(ThresholdsFrozenError):
        t.set(DetectionMethod.ACCESSIBILITY.value, "button",
              MethodThresholds(min_detection_confidence=0.99))


def test_freeze_exige_motivo_explicito():
    t = DetectionThresholds.defaults()
    with pytest.raises(ValueError):
        t.freeze(reason="")


def test_unfreeze_es_explicito_y_registrado_en_historial():
    t = DetectionThresholds.derive_from_measurements(
        _mediciones_button_accesibilidad(), tp_quantile=0.05, min_samples=5
    )
    t.freeze(reason="motivo de prueba")
    fingerprint_congelado = t.frozen_fingerprint
    t.unfreeze(reason="recalibracion planificada despues de revisar la fixture")
    assert not t.is_frozen
    assert any(e["event"] == "unfreeze" for e in t.history)
    assert any(e["event"] == "freeze" for e in t.history)
    # Tras descongelar se puede volver a fijar.
    t.set(DetectionMethod.ACCESSIBILITY.value, "button",
          MethodThresholds(min_detection_confidence=0.90))
    t.freeze(reason="segundo congelado")
    assert t.is_frozen


# ---------------------------------------------------------------------------
# Persistencia en fichero (ruta temporal, nunca config/ de produccion en tests)
# ---------------------------------------------------------------------------

def test_save_y_load_restan_umbrales_y_estado_congelado():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "umbrales_prueba.json")
    t = DetectionThresholds.derive_from_measurements(
        _mediciones_button_accesibilidad(), tp_quantile=0.05, min_samples=5
    )
    t.freeze(reason="prueba de persistencia")
    t.save(path)

    cargado = DetectionThresholds.load(path)
    assert cargado.is_frozen
    assert cargado.frozen_reason == "prueba de persistencia"
    assert cargado.fingerprint() == t.fingerprint()
    thr = cargado.get(DetectionMethod.ACCESSIBILITY.value, "button")
    assert thr.status == MEASUREMENT_STATUS_MEASURED
    assert thr.samples == 5


def test_load_sin_fichero_devuelve_valores_de_partida():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "no_existe.json")
    t = DetectionThresholds.load(path)
    assert not t.is_frozen
    assert t.source == "defaults"


def test_load_fichero_congelado_alterado_lanza_integridad():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "umbrales_alterados.json")
    t = DetectionThresholds.defaults()
    t.save(path)  # no congelado, guarda huella actual

    # Alterar el fichero directamente (simula manipulacion posterior).
    import json
    data = json.loads(open(path, encoding="utf-8").read())
    data["frozen"] = True
    data["frozen_reason"] = "alterado"
    data["fingerprint"] = "huella_falsa"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ThresholdsIntegrityError):
        DetectionThresholds.load(path)


# ---------------------------------------------------------------------------
# Huella y IoU de ambiguedad entre metodos
# ---------------------------------------------------------------------------

def test_fingerprint_cambia_si_cambia_un_umbral():
    t1 = DetectionThresholds.defaults()
    t2 = DetectionThresholds.defaults()
    assert t1.fingerprint() == t2.fingerprint()

    t2.set(DetectionMethod.OCR.value, "button",
           MethodThresholds(min_detection_confidence=0.70))
    assert t1.fingerprint() != t2.fingerprint()


def test_ambiguous_iou_es_el_mas_estricto_entre_metodos():
    t = DetectionThresholds.defaults()
    valor = t.ambiguous_iou("button")
    assert valor == 0.30  # minimo entre los metodos por defecto


def test_units_son_relativas_no_pixeles():
    """Comprueba explicitamente que no hay umbrales en pixeles absolutos."""
    t = DetectionThresholds.defaults()
    for metodo in DetectionMethod:
        for ctype in (WILDCARD_CONTROL_TYPE, "button"):
            thr = t.get(metodo.value, ctype)
            # Ningun umbral expresado en unidades absolutas de pantalla.
            assert thr.min_box_size_ratio >= 0.0  # fraccion de la ventana
            assert thr.max_center_error_ratio <= 1.0  # fraccion de la diagonal
            assert thr.min_iou_with_reference <= 1.0  # IoU
