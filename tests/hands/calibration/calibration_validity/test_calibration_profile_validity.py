"""
Tests de unidad de la evaluacion de vigencia de perfiles de calibracion
(unidad 3.8.6.9.1).

Al cargar un perfil se exige coincidencia de machine_id, monitor,
escala/DPI, resolucion, orientacion y estado de ventana; no se aplican
perfiles de otro equipo o de una topologia no equivalente.

Todos los tests son deterministas, sin GUI ni SO real: construyen
EnvironmentFingerprint y CalibrationProfile sinteticos y llaman a
evaluate_profile_validity.
"""

from __future__ import annotations

from typing import Optional

import pytest

from src.desktop.platform_contract import DisplayInfo, Rect, WindowInfo
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_REJECT,
    ACTION_RECOMPUTE,
    ACTION_USE,
    EnvironmentFingerprint,
    ProfileValidity,
    evaluate_profile_validity,
)
from src.hands.calibration.calibration_profile_storage import (
    CalibrationProfile,
    CalibrationState,
    CalibratedControlRecord,
)

MAQUINA = "maquina-prueba-1"
OTRA_MAQUINA = "maquina-otra-2"
APP = "app_bloc_de_notas"
HUELLA = "huella-ventana-1"
MONITOR = "monitor-1"
OTRO_MONITOR = "monitor-2"


def _display(display_id=MONITOR, scale=1.25, dpi=120, pw=1920, ph=1080,
             orientation="landscape", is_primary=False) -> DisplayInfo:
    return DisplayInfo(
        display_id=display_id,
        name="Monitor prueba",
        bounds=Rect(0, 0, float(pw), float(ph)),
        work_area=Rect(0, 0, float(pw), float(ph)),
        pixel_width=pw,
        pixel_height=ph,
        scale_factor=scale,
        dpi=dpi,
        is_primary=is_primary,
        rotation=0,
        coordinate_space="DESKTOP_PIXELS",
    )


def _window(window_id=1001, client_bounds=None, is_minimized=False,
            is_visible=True, is_maximized=True, display_id=MONITOR) -> WindowInfo:
    return WindowInfo(
        window_id=window_id,
        pid=1234,
        title="Bloc de notas",
        app_identity=APP,
        bounds=client_bounds or Rect(0, 0, 800, 600),
        client_bounds=client_bounds or Rect(0, 0, 780, 560),
        is_visible=is_visible,
        is_minimized=is_minimized,
        is_maximized=is_maximized,
        is_foreground=True,
    )


def _env(machine_id=MAQUINA, platform="Windows", display_id=MONITOR,
         scale=1.25, dpi=120, pw=1920, ph=1080, orientation="landscape",
         window_state="maximized", client_size=(780, 560),
         topology="topologia-a", layout_hash=None,
         client_bounds=None, window_id=1001) -> EnvironmentFingerprint:
    disp = _display(display_id, scale, dpi, pw, ph, orientation)
    win = _window(window_id, client_bounds,
                  is_minimized=(window_state == "minimized"),
                  is_visible=(window_state not in ("minimized", "hidden")),
                  is_maximized=(window_state == "maximized"),
                  display_id=display_id)
    return EnvironmentFingerprint(
        machine_id=machine_id,
        platform=platform,
        display_id=display_id,
        scale_factor=scale,
        dpi=dpi,
        display_pixel_size=(pw, ph),
        orientation=orientation,
        window_state=window_state,
        client_size=client_size,
        topology_fingerprint=topology,
        layout_hash=layout_hash,
        client_bounds=client_bounds or Rect(0, 0, 780, 560),
        window_id=window_id,
        coordinate_space="DESKTOP_PIXELS",
    )


def _control(control_id="ctrl_boton", app_id=APP) -> CalibratedControlRecord:
    return CalibratedControlRecord(
        control_id=control_id,
        app_id=app_id,
        name="Boton",
        control_type="button",
        semantic_state=CalibrationState.VALIDADO,
        geometric_state=CalibrationState.VALIDADO,
        action_state=CalibrationState.VALIDADO,
        client_box_normalized=(0.10, 0.10, 0.40, 0.40),
        interaction_method="pointer",
        provenance=["accessibility"],
        detector_versions={"qwen3-vl": "8b"},
        confidences={"detection": 0.90, "semantic": 0.80,
                     "interactivity": 0.85, "geometry": 0.90},
        calibrated_at="2026-01-15T10:30:00+00:00",
    )


def _profile(app_id=APP, machine_id=MAQUINA, platform="Windows",
             topology="topologia-a", window_fingerprint=HUELLA,
             display_id=MONITOR, scale=1.25, dpi=120,
             pixel_size=(1920, 1080), orientation="landscape",
             window_state="maximized", client_size=(780, 560),
             status=CalibrationState.VALIDADO, controls=None,
             layout_hash=None, absolute_cache=None) -> CalibrationProfile:
    return CalibrationProfile(
        profile_id="",
        machine_id=machine_id,
        app_id=app_id,
        platform=platform,
        topology_fingerprint=topology,
        window_fingerprint=window_fingerprint,
        display_id=display_id,
        scale_factor=scale,
        dpi=dpi,
        display_pixel_size=pixel_size,
        orientation=orientation,
        window_state=window_state,
        client_size=client_size,
        status=status,
        controls=list(controls if controls is not None else [_control()]),
        metadata={"layout_hash": layout_hash} if layout_hash else {},
        absolute_cache=dict(absolute_cache) if absolute_cache else {},
    )


# ---------------------------------------------------------------------------
# Casos base
# ---------------------------------------------------------------------------

def test_sin_perfil_devuelve_recalibrar():
    val = evaluate_profile_validity(None, _env())
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False


def test_perfil_vigente_todo_coincide_devuelve_use():
    env = _env()
    perfil = _profile(absolute_cache={"client_bounds": [0, 0, 780, 560]})
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_USE
    assert val.valid is True
    assert val.reason == "perfil vigente para la ventana y monitor actuales"


# ---------------------------------------------------------------------------
# 3.8.6.9.1: exigir coincidencia de machine_id y plataforma
# ---------------------------------------------------------------------------

def test_otro_machine_id_rechaza():
    env = _env()
    perfil = _profile(machine_id=OTRA_MAQUINA)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "otro equipo" in val.reason


def test_otra_plataforma_rechaza():
    env = _env(platform="Windows")
    perfil = _profile(platform="macOS")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "otro SO" in val.reason


# ---------------------------------------------------------------------------
# 3.8.6.9.1: exigir coincidencia de escala y DPI
# ---------------------------------------------------------------------------

def test_distinta_escala_recalibra():
    env = _env(scale=1.25)
    perfil = _profile(scale=1.50)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "escala" in val.changes


def test_distinto_dpi_recalibra():
    env = _env(dpi=120)
    perfil = _profile(dpi=96)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "dpi" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: exigir coincidencia de tamano de area cliente
# ---------------------------------------------------------------------------

def test_distinto_tamano_cliente_recalibra():
    env = _env(client_size=(780, 560))
    perfil = _profile(client_size=(800, 600))
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "tamano_cliente" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: exigir coincidencia de estado de ventana
# ---------------------------------------------------------------------------

def test_distinto_estado_ventana_recalibra():
    env = _env(window_state="maximized")
    perfil = _profile(window_state="normal")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "estado_ventana" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: exigir coincidencia de monitor y resolucion / orientacion
# ---------------------------------------------------------------------------

def test_distinto_monitor_recomputa():
    env = _env(display_id=MONITOR)
    perfil = _profile(display_id=OTRO_MONITOR)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "monitor" in val.changes


def test_distinta_resolucion_mismo_monitor_recalibra():
    env = _env(pw=1920, ph=1080)
    perfil = _profile(pixel_size=(1366, 768))
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "resolucion" in val.changes


def test_distinta_orientacion_mismo_monitor_recalibra():
    env = _env(orientation="landscape")
    perfil = _profile(orientation="portrait")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "orientacion" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: topologia diferente (sin cambios de monitor/escala) -> recompute
# ---------------------------------------------------------------------------

def test_distinta_topologia_recomputa():
    env = _env(topology="topologia-a")
    perfil = _profile(topology="topologia-b")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "topologia" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: ventana no visible (minimizada/oculta) -> rechazar para la accion
# ---------------------------------------------------------------------------

def test_ventana_minimizada_rechaza():
    env = _env(window_state="minimized")
    perfil = _profile()
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "ventana_no_visible" in val.changes


def test_ventana_oculta_rechaza():
    env = _env(window_state="hidden")
    perfil = _profile()
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False


# ---------------------------------------------------------------------------
# 3.8.6.9.1: perfil sin estado VALIDADO -> recalibrar
# ---------------------------------------------------------------------------

def test_perfil_no_validado_recalibra():
    env = _env()
    perfil = _profile(status=CalibrationState.PENDIENTE)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "estado_perfil" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: datos incompletos del perfil -> recalibrar y marcar obsoleto
# ---------------------------------------------------------------------------

def test_perfil_sin_client_size_recalibra_obsoleto():
    env = _env()
    perfil = _profile(client_size=None)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert val.changes == ["datos_incompletos"]
    assert "client_size" in val.reason


def test_perfil_sin_scale_factor_recalibra_obsoleto():
    env = _env()
    perfil = _profile(scale=None)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert val.changes == ["datos_incompletos"]
    assert "scale_factor" in val.reason


def test_perfil_sin_window_fingerprint_recalibra_obsoleto():
    env = _env()
    perfil = _profile(window_fingerprint="")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert val.changes == ["datos_incompletos"]
    assert "window_fingerprint" in val.reason


# ---------------------------------------------------------------------------
# 3.8.6.9.1: transformacion no verificable en el entorno (sin area cliente)
# ---------------------------------------------------------------------------

def test_sin_area_cliente_entorno_recalibra():
    env = _env(client_bounds=None, client_size=None)
    perfil = _profile()
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "transformacion_no_verificable" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.3: modelo (detector) distinto en todos los controles -> obsoleto y recalibrar
# ---------------------------------------------------------------------------

def test_todos_controles_version_detector_distinta_marca_obsoleto():
    env = _env()
    c1 = _control("c1")
    c2 = _control("c2")
    perfil = _profile(controls=[c1, c2])
    val = evaluate_profile_validity(perfil, env, current_detector_versions={"qwen3-vl": "9b"})
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert "version_detector" in val.changes
    assert set(val.affected_controls) == {"c1", "c2"}


# ---------------------------------------------------------------------------
# 3.8.6.9.3: todos los controles con caja incompleta -> obsoleto y recalibrar
# ---------------------------------------------------------------------------

def test_todos_controles_caja_incompleta_marca_obsoleto():
    env = _env()
    c1 = CalibratedControlRecord(
        control_id="c1", app_id=APP, name="Boton 1", control_type="button",
        semantic_state=CalibrationState.VALIDADO, geometric_state=CalibrationState.VALIDADO,
        action_state=CalibrationState.VALIDADO,
        client_box_normalized=(1.10, 0.10, 0.40, 0.40),
        interaction_method="pointer", provenance=["accessibility"],
        detector_versions={"qwen3-vl": "8b"},
        confidences={"detection": 0.90, "semantic": 0.80, "interactivity": 0.85, "geometry": 0.90},
        calibrated_at="2026-01-15T10:30:00+00:00",
    )
    c2 = CalibratedControlRecord(
        control_id="c2", app_id=APP, name="Boton 2", control_type="button",
        semantic_state=CalibrationState.VALIDADO, geometric_state=CalibrationState.VALIDADO,
        action_state=CalibrationState.VALIDADO,
        client_box_normalized=(0.10, 0.10, 0.10, 0.10),
        interaction_method="pointer", provenance=["accessibility"],
        detector_versions={"qwen3-vl": "8b"},
        confidences={"detection": 0.90, "semantic": 0.80, "interactivity": 0.85, "geometry": 0.90},
        calibrated_at="2026-01-15T10:30:00+00:00",
    )
    perfil = _profile(controls=[c1, c2])
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert "controles_incompletos" in val.changes
    assert set(val.affected_controls) == {"c1", "c2"}


# ---------------------------------------------------------------------------
# 3.8.6.9.1: mismo monitor pero posicion de ventana distinta -> recompute
# ---------------------------------------------------------------------------

def test_misma_escala_posicion_ventana_distinta_recomputa():
    env = _env(client_bounds=Rect(0, 0, 780, 560))
    perfil = _profile(absolute_cache={"client_bounds": [100, 100, 880, 660]})
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "posicion_ventana" in val.changes


# ---------------------------------------------------------------------------
# 3.8.6.9.1: multiples cambios a la vez
# ---------------------------------------------------------------------------

def test_cambios_escala_y_estado_recalibra():
    env = _env(scale=1.25, window_state="maximized")
    perfil = _profile(scale=1.50, window_state="normal")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "escala" in val.changes
    assert "estado_ventana" in val.changes


# ---------------------------------------------------------------------------
# Tolerancias: diferencias minimas no provocan recalibracion de ese campo
# ---------------------------------------------------------------------------

def test_escala_dentro_de_tolerancia_no_cambia_ese_campo():
    env = _env(scale=1.25)
    perfil = _profile(scale=1.2505)  # diferencia < SCALE_TOLERANCE (1e-3)
    val = evaluate_profile_validity(perfil, env)
    assert "escala" not in val.changes


def test_tamano_cliente_dentro_de_tolerancia_no_cambia_ese_campo():
    env = _env(client_size=(780, 560))
    perfil = _profile(client_size=(781, 560))  # diferencia de 1 unidad
    val = evaluate_profile_validity(perfil, env)
    assert "tamano_cliente" not in val.changes


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
