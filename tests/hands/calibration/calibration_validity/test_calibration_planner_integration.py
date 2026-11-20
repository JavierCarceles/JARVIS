# -*- coding: ascii -*-
"""
Tests de integracion de la unidad 3.8.6.9.4: Integracion entre
ApplicationManager y CoordinateManager para el Planner.

Objetivo verificable:
- CoordinateManager.get_planner_resources publica solo recursos VALIDADO
  para la ventana y monitor actuales (filtrados por machine_id, huella de
  ventana/escala y vigencia), delegando en
  CalibrationValidityService.resources_for_planner.
- CoordinateManager.calibration_required delega en el servicio.
- CoordinateManager.publish_validated_resources publica UIResources desde
  perfiles vigentes y retira los recursos legacy de la misma aplicacion
  (nunca acumula coordenadas de otra ventana o monitor).
- ApplicationManager.get_calibration_status expone solo
  {application, registered, calibration_required}: nunca coordenadas,
  monitores, escala ni identificadores de ventana.

Todos los tests son deterministas, sin GUI ni SO real. El almacen usa una
base SQLite temporal y el adaptador de escritorio es un doble controlado.
"""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import patch

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
from src.hands.calibration.coordinate_manager import (
    CalibrationStrategy,
    CoordinateManager,
    ResourceType,
    UIResource,
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
from src.hands.apps.applications_core import ApplicationManager

MAQUINA = "maquina-prueba-1"
MAQUINA_OTRA = "maquina-prueba-2"
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


class _FakeMonitor:
    def __init__(self, screen_key="s2"):
        self.screen_key = screen_key


class _FakeScreenManager:
    def __init__(self, monitor=None):
        self.monitor = monitor

    def get_monitor_by_point(self, x, y):
        return self.monitor


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


def _cm_con_servicio(store: CalibrationProfileStore, adapter: _FakeAdapter):
    """CoordinateManager con el servicio de vigencia inyectado."""
    cm = CoordinateManager.__new__(CoordinateManager)
    cm.ui_resources = {}
    cm.ui_capabilities = {}
    cm.ui_knowledge = {}
    cm.calibration_policies = {}
    cm.screen_manager = _FakeScreenManager()
    service = CalibrationValidityService(store=store, adapter=adapter)
    cm.set_validity_service(service)
    return cm, service


# ---------------------------------------------------------------------------
# CoordinateManager.get_planner_resources
# ---------------------------------------------------------------------------

class TestCoordinateManagerGetPlannerResources:
    """get_planner_resources devuelve solo recursos vigentes para la ventana y
    monitor actuales, filtrados por machine_id, huella y vigencia."""

    def test_devuelve_recursos_validos_de_la_ventana_actual(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON2)
        adapter = _FakeAdapter(window, [_display(display_id=MON2), _display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)

        service.load_valid_profile(APP, WINDOW_ID)
        recursos = cm.get_planner_resources(APP, WINDOW_ID)

        assert len(recursos) == 1
        r = recursos[0]
        assert r["control_id"] == "ctrl_boton"
        assert r["app_id"] == APP
        assert r["point"] is not None
        assert r["box"] is not None
        assert r["coordinate_space"] == DESKTOP_PIXELS
        assert r["display_id"] == MON2
        assert r["window_id"] == WINDOW_ID
        assert r["validity_action"] == ACTION_RECOMPUTE

    def test_devuelve_vacio_sin_perfil_valido(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        recursos = cm.get_planner_resources(APP, WINDOW_ID)
        assert recursos == []

    def test_devuelve_vacio_cuando_perfil_no_es_utilizable(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)

        # Modelo de detector distinto en todos los controles: el perfil queda
        # OBSOLETO y no hay recursos utilizables para el planificador.
        service.load_valid_profile(APP, WINDOW_ID, current_detector_versions={"qwen3-vl": "9b"})
        recursos = cm.get_planner_resources(APP, WINDOW_ID)
        assert recursos == []

    def test_filtrado_por_maquina_id(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)

        service.load_valid_profile(APP, WINDOW_ID)
        recursos_propias = cm.get_planner_resources(APP, WINDOW_ID)
        assert len(recursos_propias) == 1

        # La misma consulta contra un machine_id distinto no devuelve recursos
        # (el store filtra por machine_id en todas sus lecturas).
        cm_otra = CoordinateManager.__new__(CoordinateManager)
        cm_otra.ui_resources = {}
        cm_otra.ui_capabilities = {}
        cm_otra.ui_knowledge = {}
        cm_otra.calibration_policies = {}
        cm_otra.screen_manager = _FakeScreenManager()
        service_otra = CalibrationValidityService(
            store=CalibrationProfileStore(
                db_path=str(tmp_path / "calibracion_otra.sqlite3"), machine_id=MAQUINA_OTRA
            ),
            adapter=adapter,
        )
        cm_otra.set_validity_service(service_otra)
        recursos_otra = cm_otra.get_planner_resources(APP, WINDOW_ID)
        assert recursos_otra == []


# ---------------------------------------------------------------------------
# CoordinateManager.calibration_required
# ---------------------------------------------------------------------------

class TestCoordinateManagerCalibrationRequired:
    """calibration_required delega en CalibrationValidityService.calibration_required."""

    def test_devuelve_true_sin_perfil(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        assert cm.calibration_required(APP, WINDOW_ID) is True

    def test_devuelve_false_con_perfil_valido_utilizable(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)

        service.load_valid_profile(APP, WINDOW_ID)
        assert cm.calibration_required(APP, WINDOW_ID) is False

    def test_devuelve_true_cuando_servicio_falla(self, tmp_path):
        store = _abrir_store(tmp_path)
        cm = CoordinateManager.__new__(CoordinateManager)
        cm.ui_resources = {}
        cm.ui_capabilities = {}
        cm.ui_knowledge = {}
        cm.calibration_policies = {}
        cm.screen_manager = _FakeScreenManager()

        class _ServicioQueFalla:
            def calibration_required(self, app_id, window_id=None):
                raise RuntimeError("servicio caido")

        cm.set_validity_service(_ServicioQueFalla())
        # Ante un error se asume que hace falta calibrar (nunca se asume
        # calibrado sin evidencia).
        assert cm.calibration_required(APP, WINDOW_ID) is True


# ---------------------------------------------------------------------------
# CoordinateManager.publish_validated_resources
# ---------------------------------------------------------------------------

class TestCoordinateManagerPublishValidatedResources:
    """publish_validated_resources publica UIResources desde perfiles vigentes
    y retira los recursos legacy de la misma aplicacion."""

    def test_publica_recursos_vigentes_y_marca_legacy_como_superseded(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON2)
        adapter = _FakeAdapter(window, [_display(display_id=MON2), _display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)

        # Un recurso legacy (macros_coords.json) de la misma aplicacion esta
        # ya registrado antes de publicar el perfil vigente.
        legacy_id = f"{APP}.boton_legacy"
        legacy = UIResource(
            id=legacy_id,
            name="boton_legacy",
            resource_type=ResourceType.ELEMENT,
            application=APP,
            element_type="button",
            calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
            calibrated_coordinates={1: (100, 200)},
            calibrated_regions={},
            confidence=0.8,
            is_available=True,
            is_calibrated=True,
            metadata={"source": "macros_coords.json", "app_id": APP},
        )
        cm.register_ui_resource(legacy)
        assert cm.get_ui_resource(legacy_id).is_available is True

        service.load_valid_profile(APP, WINDOW_ID)
        publicados = cm.publish_validated_resources(APP, WINDOW_ID, APP)

        # Se publicaron recursos desde el perfil vigente.
        assert len(publicados) == 1
        assert publicados[0].metadata["source"] == "calibration_profile_store"
        assert publicados[0].application == APP

        # El recurso legacy de la misma aplicacion quedo no disponible y
        # marcado como sustituido por el perfil local.
        legacy_despues = cm.get_ui_resource(legacy_id)
        assert legacy_despues is not None
        assert legacy_despues.is_available is False
        assert legacy_despues.metadata.get("superseded_by_local_profile") is True

    def test_publicar_sin_perfil_valido_no_publica_nada(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        publicados = cm.publish_validated_resources(APP, WINDOW_ID, APP)
        assert publicados == []

    def test_publicar_retira_recursos_previos_del_mismo_almacen(self, tmp_path):
        store = _abrir_store(tmp_path)
        window = _window(display_id=MON1)
        adapter = _FakeAdapter(window, [_display(display_id=MON1)])
        cm, service = _cm_con_servicio(store, adapter)

        current = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
        huella = current.window_fingerprint()
        _guardar_perfil_valido(store, huella, display_id=MON1)
        service.load_valid_profile(APP, WINDOW_ID)

        primera = cm.publish_validated_resources(APP, WINDOW_ID, APP)
        assert len(primera) == 1

        # Volver a publicar sustituye los recursos previos del almacen (no
        # se acumulan).
        segunda = cm.publish_validated_resources(APP, WINDOW_ID, APP)
        assert len(segunda) == 1
        store_ids = [
            rid
            for rid, res in cm.ui_resources.items()
            if res.metadata.get("source") == "calibration_profile_store"
        ]
        assert len(store_ids) == 1


# ---------------------------------------------------------------------------
# ApplicationManager.get_calibration_status
# ---------------------------------------------------------------------------

class TestApplicationManagerGetCalibrationStatus:
    """El catalogo expone solo calibration_required, nunca coordenadas."""

    def test_devuelve_solo_claves_permitidas_sin_coordenadas(self):
        manager = ApplicationManager()
        status = manager.get_calibration_status("chrome", WINDOW_ID)

        assert set(status.keys()) == {"application", "registered", "calibration_required"}
        assert isinstance(status["application"], str) and len(status["application"]) > 0
        assert isinstance(status["registered"], bool)
        assert isinstance(status["calibration_required"], bool)
        # Nunca se exponen coordenadas, monitores, escala ni identificadores
        # de ventana en el catalogo global.
        for clave in ("coordinates", "x", "y", "monitor", "screen", "scale", "dpi", "window_id", "display_id"):
            assert clave not in status, ("el catalogo no debe exponer %s" % clave)

    def test_app_no_registrada_devuelve_calibration_required_true(self):
        manager = ApplicationManager()
        status = manager.get_calibration_status("aplicacion_que_no_existe_xyz", WINDOW_ID)

        assert status["registered"] is False
        assert status["calibration_required"] is True

    def test_error_en_coordinate_manager_devuelve_calibration_required_true(self):
        manager = ApplicationManager()

        class _CmQueFalla:
            def calibration_required(self, app_id, window_id=None):
                raise RuntimeError("coordinate manager caido")

        with patch("src.hands.calibration.coordinate_manager.get_coordinate_manager", return_value=_CmQueFalla()):
            status = manager.get_calibration_status("chrome", WINDOW_ID)

        assert status["calibration_required"] is True

    def test_calibration_required_false_cuando_servicio_devuelve_false(self):
        manager = ApplicationManager()

        class _CmQueDevuelveFalse:
            def calibration_required(self, app_id, window_id=None):
                return False

        with patch(
            "src.hands.calibration.coordinate_manager.get_coordinate_manager",
            return_value=_CmQueDevuelveFalse(),
        ):
            status = manager.get_calibration_status("chrome", WINDOW_ID)

        assert status["calibration_required"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
