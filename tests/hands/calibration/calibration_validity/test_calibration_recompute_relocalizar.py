# -*- coding: ascii -*-
"""
Tests de unidad del recalculo de coordenadas absolutas y la relocalizacion
de controles al cambiar de monitor (unidad 3.8.6.9.2).

Cubre:
- recompute_absolute / recompute_absolute_boxes: convierte geometria
  normalizada relativa al area cliente en puntos/cajas absolutas de
  escritorio usando el rectangulo cliente real de la ventana.
- build_absolute_cache: construye la cache invalidable de absolutas.
- evaluate_profile_validity: misma escala y monitor distinto -> recompute
  (recalcular absolutas sin recalibrar); cambio de escala -> recalibrar
  todos los controles; version de detector -> invalida solo lo afectado.
- CalibrationValidityService: load_valid_profile devuelve el perfil con la
  cache absoluta recalculada para la ventana actual y
  resources_for_planner publica solo controles VALIDADO con metodo real y
  punto recalculado.

Todos los tests son deterministas, sin GUI ni SO real. El almacen usa una
base SQLite temporal y el adaptador de escritorio es un doble controlado.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DisplayInfo,
    PlatformError,
    PlatformErrorCode,
    PlatformResult,
    Rect,
    WindowInfo,
)
from src.hands.calibration.calibration_profile_storage import (
    CalibrationProfile,
    CalibratedControlRecord,
    CalibrationProfileStore,
    CalibrationState,
)
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_RECOMPUTE,
    ACTION_USE,
    CalibrationValidityService,
    EnvironmentFingerprint,
    ProfileValidity,
    build_absolute_cache,
    evaluate_profile_validity,
    recompute_absolute,
    recompute_absolute_boxes,
)

MAQUINA = "maquina-prueba-1"
APP = "app_bloc_de_notas"
MON1 = "monitor-1"
MON2 = "monitor-2"
WINDOW_ID = 1001


def _display(
    display_id=MON1,
    scale=1.25,
    dpi=120,
    pw=1707,
    ph=960,
    orientation="landscape",
    is_primary=False,
) -> DisplayInfo:
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


def _window(
    window_id=WINDOW_ID,
    client_bounds=None,
    display_id=MON1,
    scale=1.25,
    dpi=120,
    is_maximized=True,
    is_visible=True,
    is_minimized=False,
) -> WindowInfo:
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
        display_id=display_id,
        scale_factor=scale,
        dpi=dpi,
    )


def _control(
    control_id="ctrl_boton",
    app_id=APP,
    name="Boton",
    semantic_state=CalibrationState.VALIDADO,
    geometric_state=CalibrationState.VALIDADO,
    action_state=CalibrationState.VALIDADO,
    box=(0.10, 0.10, 0.40, 0.40),
    safe_point_normalized=(0.25, 0.25),
    interaction_method="pointer",
    provenance=None,
    detector_versions=None,
    calibrated_at="2026-01-15T10:30:00+00:00",
) -> CalibratedControlRecord:
    return CalibratedControlRecord(
        control_id=control_id,
        app_id=app_id,
        name=name,
        control_type="button",
        semantic_state=semantic_state,
        geometric_state=geometric_state,
        action_state=action_state,
        client_box_normalized=box,
        safe_point_normalized=safe_point_normalized,
        interaction_method=interaction_method,
        provenance=list(provenance or ["uia"]),
        detector_versions=dict(detector_versions or {"qwen3-vl": "8b"}),
        confidences={
            "detection": 0.90,
            "semantic": 0.80,
            "interactivity": 0.85,
            "geometry": 0.90,
        },
        calibrated_at=calibrated_at,
    )


def _profile(
    app_id=APP,
    machine_id=MAQUINA,
    platform="Windows",
    topology="topologia-a",
    window_fingerprint="huella-ventana-1",
    display_id=MON1,
    scale=1.25,
    dpi=120,
    pixel_size=(1707, 960),
    orientation="landscape",
    window_state="maximized",
    client_size=(780, 560),
    status=CalibrationState.VALIDADO,
    controls=None,
) -> CalibrationProfile:
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
    )


def _abrir_store(tmp_path, machine_id=MAQUINA):
    store = CalibrationProfileStore(db_path=str(tmp_path / "calibracion.sqlite3"), machine_id=machine_id)
    assert store.initialize() is True
    assert store.is_blocked is False
    return store


# ---------------------------------------------------------------------------
# recompute_absolute y recompute_absolute_boxes
# ---------------------------------------------------------------------------


def test_recompute_absolute_convierte_centro_normalizado_a_punto_escritorio():
    profile = _profile(controls=[_control(control_id="ctrl_1", box=(0.10, 0.10, 0.40, 0.40), safe_point_normalized=(0.25, 0.25))])
    window = _window(client_bounds=Rect(100, 100, 500, 400))
    puntos = recompute_absolute(profile, window)
    assert puntos == {"ctrl_1": (200.0, 175.0)}


def test_recompute_absolute_usar_centro_de_caja_sin_punto_seguro():
    profile = _profile(controls=[_control(control_id="ctrl_1", box=(0.10, 0.20, 0.30, 0.60), safe_point_normalized=None)])
    window = _window(client_bounds=Rect(100, 100, 500, 400))
    puntos = recompute_absolute(profile, window)
    # centro de la caja: (0.20, 0.40) -> (100 + 0.20*400, 100 + 0.40*300) = (180, 220)
    assert puntos == {"ctrl_1": (180.0, 220.0)}


def test_recompute_absolute_salta_control_sin_caja_valida():
    profile = _profile(
        controls=[
            _control(control_id="ctrl_valido", box=(0.10, 0.10, 0.40, 0.40)),
            _control(control_id="ctrl_invalido", box=(1.10, 0.10, 0.40, 0.40)),
        ]
    )
    window = _window(client_bounds=Rect(100, 100, 500, 400))
    puntos = recompute_absolute(profile, window)
    assert puntos == {"ctrl_valido": (200.0, 175.0)}


def test_recompute_absolute_boxes_convierte_caja_normalizada_a_escritorio():
    profile = _profile(controls=[_control(control_id="ctrl_1", box=(0.10, 0.20, 0.50, 0.60))])
    window = _window(client_bounds=Rect(100, 100, 500, 400))
    cajas = recompute_absolute_boxes(profile, window)
    # (100+0.10*400, 100+0.20*300, 100+0.50*400, 100+0.60*300)
    assert cajas == {"ctrl_1": (140.0, 160.0, 300.0, 280.0)}


def test_build_absolute_cache_estructura():
    profile = _profile()
    window = _window()
    current = EnvironmentFingerprint(
        machine_id=MAQUINA,
        platform="Windows",
        display_id=MON1,
        scale_factor=1.25,
        dpi=120,
        display_pixel_size=(1707, 960),
        orientation="landscape",
        window_state="maximized",
        client_size=(780, 560),
        topology_fingerprint="topo",
        client_bounds=Rect(0, 0, 780, 560),
        window_id=WINDOW_ID,
        coordinate_space=DESKTOP_PIXELS,
    )
    cache = build_absolute_cache(profile, window, current)
    assert cache["client_bounds"] == [0, 0, 780, 560]
    assert cache["display_id"] == MON1
    assert cache["topology_fingerprint"] == "topo"
    assert cache["coordinate_space"] == DESKTOP_PIXELS
    assert "ctrl_boton" in cache["points"]
    assert "ctrl_boton" in cache["boxes"]
    assert len(cache["points"]) == 1
    assert len(cache["boxes"]) == 1


# ---------------------------------------------------------------------------
# evaluate_profile_validity: recompute al cambiar de monitor con igual escala
# ---------------------------------------------------------------------------


def test_mismo_escala_otro_monitor_devuelve_recompute_sin_recalibrar():
    env = EnvironmentFingerprint(
        machine_id=MAQUINA,
        platform="Windows",
        display_id=MON2,
        scale_factor=1.25,
        dpi=120,
        display_pixel_size=(1707, 960),
        orientation="landscape",
        window_state="maximized",
        client_size=(780, 560),
        topology_fingerprint="topo",
        client_bounds=Rect(0, 0, 780, 560),
        window_id=WINDOW_ID,
        coordinate_space=DESKTOP_PIXELS,
    )
    perfil = _profile(display_id=MON1, window_fingerprint=env.window_fingerprint())
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "monitor" in val.changes


def test_cambio_escala_recalibra_y_afecta_a_todos_los_controles():
    env = EnvironmentFingerprint(
        machine_id=MAQUINA,
        platform="Windows",
        display_id=MON1,
        scale_factor=1.25,
        dpi=120,
        display_pixel_size=(1707, 960),
        orientation="landscape",
        window_state="maximized",
        client_size=(780, 560),
        topology_fingerprint="topo",
        client_bounds=Rect(0, 0, 780, 560),
        window_id=WINDOW_ID,
        coordinate_space=DESKTOP_PIXELS,
    )
    perfil = _profile(
        scale=1.50,
        window_fingerprint=env.window_fingerprint(),
        controls=[_control("c1"), _control("c2")],
    )
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "escala" in val.changes
    assert set(val.affected_controls) == {"c1", "c2"}


def test_version_detector_distinta_invalida_solo_lo_afectado():
    env = EnvironmentFingerprint(
        machine_id=MAQUINA,
        platform="Windows",
        display_id=MON1,
        scale_factor=1.25,
        dpi=120,
        display_pixel_size=(1707, 960),
        orientation="landscape",
        window_state="maximized",
        client_size=(780, 560),
        topology_fingerprint="topo",
        client_bounds=Rect(0, 0, 780, 560),
        window_id=WINDOW_ID,
        coordinate_space=DESKTOP_PIXELS,
    )
    c1 = _control("c1", detector_versions={"qwen3-vl": "8b"})
    c2 = _control("c2", detector_versions={"qwen3-vl": "9b"})
    perfil = _profile(controls=[c1, c2], window_fingerprint=env.window_fingerprint())
    val = evaluate_profile_validity(perfil, env, current_detector_versions={"qwen3-vl": "8b"})
    assert "version_detector" in val.changes
    assert val.valid is True
    assert "c2" in val.affected_controls
    assert "c1" in val.usable_controls


# ---------------------------------------------------------------------------
# CalibrationValidityService: carga de perfil y recursos para el planificador
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """Doble controlado del contrato de escritorio para tests de servicio."""

    def __init__(self, window: Optional[WindowInfo], displays: List[DisplayInfo]):
        self.window = window
        self.displays = list(displays)
        self.platform_name = "Windows"
        self.desktop_space = DESKTOP_PIXELS

    def get_window(self, window_id: int) -> PlatformResult:
        if self.window is None:
            return PlatformResult(
                False,
                None,
                PlatformError(PlatformErrorCode.NOT_FOUND, "ventana no encontrada", "get_window"),
            )
        return PlatformResult(True, self.window)

    def enumerate_displays(self) -> PlatformResult:
        return PlatformResult(True, list(self.displays))

    def get_window_dpi_info(self, window_id: int) -> PlatformResult:
        return PlatformResult(True, None)


def _guardar_perfil_valido(store: CalibrationProfileStore, window_fingerprint: str, display_id: str = MON1) -> CalibrationProfile:
    profile = _profile(
        machine_id=MAQUINA,
        window_fingerprint=window_fingerprint,
        display_id=display_id,
        status=CalibrationState.VALIDADO,
    )
    store.save_profile(profile)
    return profile


def test_load_valid_profile_mismo_escala_otro_monitor_devuelve_perfil_y_cache(tmp_path):
    store = _abrir_store(tmp_path)
    window = _window(display_id=MON2)
    adapter = _FakeAdapter(window, [_display(display_id=MON2), _display(display_id=MON1)])
    service = CalibrationValidityService(store=store, adapter=adapter)

    current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
    huella = current.window_fingerprint()
    _guardar_perfil_valido(store, huella, display_id=MON1)

    profile, val = service.load_valid_profile(APP, WINDOW_ID)
    assert profile is not None
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "monitor" in val.changes
    assert profile.absolute_cache is not None
    assert "ctrl_boton" in (profile.absolute_cache or {}).get("points", {})
    # La cache absoluta se persidio en el almacen
    persistida = store.get_profile(profile.profile_id)
    assert persistida is not None
    assert "ctrl_boton" in (persistida.absolute_cache or {}).get("points", {})


def test_load_valid_profile_ventana_desaparecida_devuelve_rechazo(tmp_path):
    store = _abrir_store(tmp_path)
    adapter = _FakeAdapter(None, [_display(display_id=MON1)])
    service = CalibrationValidityService(store=store, adapter=adapter)
    profile, val = service.load_valid_profile(APP, WINDOW_ID)
    assert profile is None
    assert val.action == "reject"
    assert val.valid is False


def test_resources_for_planner_publica_controles_validos_con_punto(tmp_path):
    store = _abrir_store(tmp_path)
    window = _window(display_id=MON2)
    adapter = _FakeAdapter(window, [_display(display_id=MON2), _display(display_id=MON1)])
    service = CalibrationValidityService(store=store, adapter=adapter)

    current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
    huella = current.window_fingerprint()
    _guardar_perfil_valido(store, huella, display_id=MON1)

    service.load_valid_profile(APP, WINDOW_ID)
    recursos = service.resources_for_planner(APP, WINDOW_ID)
    assert len(recursos) == 1
    r = recursos[0]
    assert r["control_id"] == "ctrl_boton"
    assert r["app_id"] == APP
    assert r["point"] is not None
    assert r["box"] is not None
    assert r["coordinate_space"] == DESKTOP_PIXELS
    assert r["display_id"] == MON2
    assert r["validity_action"] == ACTION_RECOMPUTE
    # El punto recalculado cae dentro del area cliente de la ventana real
    px, py = r["point"]
    client = window.client_bounds
    assert client.left <= px < client.right
    assert client.top <= py < client.bottom


def test_calibration_required_sin_perfil_devuelve_true(tmp_path):
    store = _abrir_store(tmp_path)
    adapter = _FakeAdapter(_window(display_id=MON1), [_display(display_id=MON1)])
    service = CalibrationValidityService(store=store, adapter=adapter)
    assert service.calibration_required(APP, WINDOW_ID) is True


# ---------------------------------------------------------------------------
# 3.8.6.9.3: obsoleto y recalibracion automatica al cargar el perfil
# ---------------------------------------------------------------------------

def test_load_valid_profile_modelo_distinto_marca_obsoleto_en_almacen(tmp_path):
    """Modelo de detector distinto en todos los controles: el servicio devuelve
    None (forzando recalibracion) y persiste OBSOLETO en el almacen, sin
    reutilizar coordenadas antiguas en silencio."""
    store = _abrir_store(tmp_path)
    window = _window(display_id=MON1)
    adapter = _FakeAdapter(window, [_display(display_id=MON1)])
    service = CalibrationValidityService(store=store, adapter=adapter)

    current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
    huella = current.window_fingerprint()
    profile = _guardar_perfil_valido(store, huella, display_id=MON1)
    assert profile.status == CalibrationState.VALIDADO

    # Todos los controles se calibraron con el detector "8b"; el entorno usa "9b".
    perfil_obsoleto, val = service.load_valid_profile(
        APP, WINDOW_ID, current_detector_versions={"qwen3-vl": "9b"}
    )
    assert perfil_obsoleto is None
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert "version_detector" in val.changes
    # La obsolescencia se persiste en el almacen real.
    persistida = store.get_profile(profile.profile_id)
    assert persistida is not None
    assert persistida.status == CalibrationState.OBSOLETO
    assert persistida.obsolete_reason == "todos los controles requieren recalibrar"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
