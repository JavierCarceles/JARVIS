# -*- coding: ascii -*-
"""
Tests de invalidacion de perfiles de calibracion UI (unidad 3.8.6.9.5).

Cubre, de forma sintetica y determinista (sin GUI ni SO real), las reglas de
inactivacion y recalculo de evaluate_profile_validity y CalibrationValidityService:
- cambio de monitor con igual escala -> recompute (recalcular absolutas sin recalibrar)
- cambio de escala/DPI -> recalibrate
- cambio de resolucion en el mismo monitor -> recalibrate
- cambio de orientacion en el mismo monitor -> recalibrate
- cambio de tamano del area cliente de la ventana -> recalibrate
- cambio de posicion de la ventana (mismo tamano) -> recompute
- ventana minimizada u oculta -> reject para la accion actual
- otro machine_id o otro SO -> reject
- sin perfil -> recalibrate
- desconexion de monitores o ventana no encontrada -> entorno_no_disponible (reject)
- salida de captura: la ventana desaparece entre llamadas -> entorno no disponible
- version de detector distinta -> invalida solo los controles afectados

Los tests GUI reales (solo Windows con JARVIS_TEST_GUI_REAL=1) abren una unica
instancia de Notepad en el monitor de pruebas (no principal situado mas a la
derecha, o el unico monitor), verifican el recalculo de absolutas y los
recursos para el planificador sobre geometria real, y cierran solo la ventana
que abrieron. Nunca tocan la configuracion de monitores del equipo ni
Visual Studio Code.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import List, Optional

import pytest

from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DisplayInfo,
    PlatformError,
    PlatformErrorCode,
    PlatformResult,
    Rect,
    WindowInfo,
    get_desktop_platform,
)
from src.hands.calibration.calibration_profile_storage import (
    CalibratedControlRecord,
    CalibrationProfile,
    CalibrationProfileStore,
    CalibrationState,
)
from src.hands.calibration.calibration_validity import (
    ACTION_RECALIBRATE,
    ACTION_RECOMPUTE,
    ACTION_REJECT,
    ACTION_USE,
    CalibrationEnvironmentError,
    CalibrationValidityService,
    EnvironmentFingerprint,
    ProfileValidity,
    build_absolute_cache,
    evaluate_profile_validity,
    recompute_absolute,
)

MAQUINA = "maquina-prueba-1"
APP = "app_bloc_de_notas"
APP_NAME = "notepad.exe"
MON1 = "monitor-1"
MON2 = "monitor-2"
WINDOW_ID = 1001

GUI_LOCK_FILE = os.path.join(
    os.path.dirname(__file__), "fixtures", "_gui_calibracion_invalidad.lock"
)


def _gui_lock_activo() -> bool:
    if not os.path.exists(GUI_LOCK_FILE):
        return False
    try:
        with open(GUI_LOCK_FILE, "r") as f:
            pid_texto = f.read().strip()
        if not pid_texto:
            return False
        pid = int(pid_texto)
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _adquirir_gui_lock() -> None:
    os.makedirs(os.path.dirname(GUI_LOCK_FILE), exist_ok=True)
    with open(GUI_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def _liberar_gui_lock() -> None:
    try:
        if os.path.exists(GUI_LOCK_FILE):
            with open(GUI_LOCK_FILE, "r") as f:
                pid_texto = f.read().strip()
            if pid_texto and int(pid_texto) == os.getpid():
                os.remove(GUI_LOCK_FILE)
    except (ValueError, OSError):
        pass


def _notepad_handles(adapter) -> List[int]:
    res = adapter.list_windows(app_identity=APP_NAME, visible_only=True)
    if not res.ok:
        return []
    return [int(w.window_id) for w in res.value]


def _display(
    display_id=MON1,
    scale=1.25,
    dpi=120,
    pw=1707,
    ph=960,
    orientation="paisaje",
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


def _env(
    machine_id=MAQUINA,
    platform="Windows",
    display_id=MON1,
    scale=1.25,
    dpi=120,
    pw=1707,
    ph=960,
    orientation="landscape",
    window_state="maximizado",
    client_size=(780, 560),
    topology="topologia-a",
    layout_hash=None,
    client_bounds=None,
    window_id=WINDOW_ID,
) -> EnvironmentFingerprint:
    disp = _display(display_id, scale, dpi, pw, ph, orientation)
    win = _window(
        window_id,
        client_bounds,
        is_minimized=(window_state == "minimizado"),
        is_visible=(window_state not in ("minimizado", "oculto")),
        is_maximized=(window_state == "maximizado"),
        display_id=display_id,
        scale=scale,
        dpi=dpi,
    )
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
    window_state="maximizado",
    client_size=(780, 560),
    status=CalibrationState.VALIDADO,
    controls=None,
    absolute_cache=None,
    layout_hash=None,
) -> CalibrationProfile:
    perfil = CalibrationProfile(
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
    if absolute_cache is not None:
        perfil.absolute_cache = dict(absolute_cache)
    if layout_hash is not None:
        perfil.metadata = {"layout_hash": layout_hash}
    return perfil


def _abrir_store(tmp_path, machine_id=MAQUINA) -> CalibrationProfileStore:
    store = CalibrationProfileStore(db_path=str(tmp_path / "calibracion.sqlite3"), machine_id=machine_id)
    assert store.initialize() is True
    assert store.is_blocked is False
    return store


class _FakeAdapter:
    """Doble controlado del contrato de escritorio para tests sinteticos."""

    def __init__(self, window: Optional[WindowInfo], displays: List[DisplayInfo]) -> None:
        self.window = window
        self.displays = list(displays)
        self.platform_name = "Windows"
        self.desktop_space = DESKTOP_PIXELS
        self.get_window_ok = True

    def get_window(self, window_id: int) -> PlatformResult:
        if not self.get_window_ok or self.window is None:
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


# ---------------------------------------------------------------------------
# Invalidacion sintetica con evaluate_profile_validity
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
    assert "perfil vigente" in val.reason


def test_cambio_de_monitor_igual_escala_devuelve_recompute():
    env = _env(display_id=MON1)
    perfil = _profile(display_id=MON2)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "monitor" in val.changes


def test_cambio_de_escala_devuelve_recalibrate():
    env = _env(scale=1.25)
    perfil = _profile(scale=1.50)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "escala" in val.changes


def test_cambio_de_resolucion_mismo_monitor_devuelve_recalibrate():
    env = _env(pw=1707, ph=960)
    perfil = _profile(pixel_size=(1366, 768))
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "resolucion" in val.changes


def test_cambio_de_orientacion_mismo_monitor_devuelve_recalibrate():
    env = _env(orientation="paisaje")
    perfil = _profile(orientation="retrato")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "orientacion" in val.changes


def test_cambio_de_tamano_area_cliente_devuelve_recalibrate():
    env = _env(client_size=(780, 560))
    perfil = _profile(client_size=(800, 600))
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "tamano_cliente" in val.changes


def test_cambio_de_posicion_ventana_mismo_tamano_devuelve_recompute():
    env = _env(client_bounds=Rect(0, 0, 780, 560))
    perfil = _profile(absolute_cache={"client_bounds": [100, 100, 880, 660]})
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "posicion_ventana" in val.changes


def test_ventana_minimizada_devuelve_reject_para_accion():
    env = _env(window_state="minimized")
    perfil = _profile()
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "ventana_no_visible" in val.changes


def test_ventana_oculta_devuelve_reject_para_accion():
    env = _env(window_state="hidden")
    perfil = _profile()
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "ventana_no_visible" in val.changes


def test_estado_ventana_distinto_devuelve_recalibrate():
    env = _env(window_state="maximizado")
    perfil = _profile(window_state="normal")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "estado_ventana" in val.changes


def test_otro_machine_id_devuelve_reject():
    env = _env()
    perfil = _profile(machine_id="maquina-otra")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "machine_id" in val.changes


def test_otra_plataforma_devuelve_reject():
    env = _env(platform="Windows")
    perfil = _profile(platform="macOS")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_REJECT
    assert val.valid is False
    assert "plataforma" in val.changes


def test_cambio_de_topologia_devuelve_recompute():
    env = _env(topology="topologia-a")
    perfil = _profile(topology="topologia-b")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECOMPUTE
    assert val.valid is True
    assert "topologia" in val.changes


def test_cambio_de_layout_hash_devuelve_recalibrate():
    env = _env(layout_hash="hash-a")
    perfil = _profile(layout_hash="hash-b")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "layout" in val.changes


def test_perfil_con_datos_incompletos_devuelve_recalibrate_y_obsoleto():
    env = _env()
    perfil = _profile(client_size=None)
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert "datos_incompletos" in val.changes


def test_version_detector_distinta_invalida_solo_controles_afectados():
    env = _env()
    c1 = _control("c1", detector_versions={"qwen3-vl": "8b"})
    c2 = _control("c2", detector_versions={"qwen3-vl": "9b"})
    perfil = _profile(controls=[c1, c2])
    val = evaluate_profile_validity(perfil, env, current_detector_versions={"qwen3-vl": "8b"})
    assert "version_detector" in val.changes
    assert val.valid is True
    assert "c2" in val.affected_controls
    assert "c1" in val.usable_controls


def test_version_detector_distinta_todos_controles_devuelve_recalibrate_y_obsoleto():
    env = _env()
    c1 = _control("c1", detector_versions={"qwen3-vl": "8b"})
    c2 = _control("c2", detector_versions={"qwen3-vl": "8b"})
    perfil = _profile(controls=[c1, c2])
    val = evaluate_profile_validity(perfil, env, current_detector_versions={"qwen3-vl": "9b"})
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert val.mark_obsolete is True
    assert "version_detector" in val.changes
    assert set(val.affected_controls) == {"c1", "c2"}


def test_varios_cambios_a_la_vez_devuelve_recalibrate():
    env = _env(scale=1.25, window_state="maximizado")
    perfil = _profile(scale=1.50, window_state="normal")
    val = evaluate_profile_validity(perfil, env)
    assert val.action == ACTION_RECALIBRATE
    assert val.valid is False
    assert "escala" in val.changes
    assert "estado_ventana" in val.changes


def test_recompute_absolute_punto_dentro_del_area_cliente():
    perfil = _profile(
        controls=[_control(box=(0.10, 0.10, 0.40, 0.40), safe_point_normalized=(0.25, 0.25))]
    )
    ventana = _window(client_bounds=Rect(100, 100, 500, 400))
    puntos = recompute_absolute(perfil, ventana)
    assert puntos == {"ctrl_boton": (200.0, 175.0)}


def test_build_absolute_cache_contiene_client_bounds_y_puntos():
    perfil = _profile()
    ventana = _window()
    actual = _env()
    cache = build_absolute_cache(perfil, ventana, actual)
    assert cache["client_bounds"] == [0, 0, 780, 560]
    assert cache["display_id"] == actual.display_id
    assert cache["coordinate_space"] == DESKTOP_PIXELS
    assert "ctrl_boton" in cache.get("points", {})
    assert "ctrl_boton" in cache.get("boxes", {})


# ---------------------------------------------------------------------------
# Invalidacion sintetica mediante CalibrationValidityService
# ---------------------------------------------------------------------------


class TestCalibrationValidityServiceInvalidad:
    def test_captura_entorno_lanza_error_si_ventana_no_encontrada(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(None, [_display()])
            service = CalibrationValidityService(store=store, adapter=adapter)
            with pytest.raises(CalibrationEnvironmentError):
                service.capture_environment(WINDOW_ID)
        finally:
            store.close()

    def test_captura_sin_monitores_devuelve_entorno_no_disponible(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(_window(), [])
            service = CalibrationValidityService(store=store, adapter=adapter)
            perfil, val = service.load_valid_profile(APP, WINDOW_ID)
            assert perfil is None
            assert val.action == ACTION_REJECT
            assert val.valid is False
            assert "entorno_no_disponible" in val.changes
        finally:
            store.close()

    def test_salida_de_captura_ventana_desaparece_entre_llamadas(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(_window(), [_display()])
            service = CalibrationValidityService(store=store, adapter=adapter)

            env = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
            perfil = _profile(
                window_fingerprint=env.window_fingerprint(),
                display_id=env.display_id,
                window_state="maximized",
            )
            store.save_profile(perfil)

            perfil_cargado, val = service.load_valid_profile(APP, WINDOW_ID)
            assert perfil_cargado is not None
            assert val.valid is True

            # Salida de captura: la ventana deja de estar disponible.
            adapter.get_window_ok = False
            perfil2, val2 = service.load_valid_profile(APP, WINDOW_ID)
            assert perfil2 is None
            assert val2.action == ACTION_REJECT
            assert val2.valid is False
            assert "entorno_no_disponible" in val2.changes
        finally:
            store.close()

    def test_calibracion_requerida_sin_perfil_devuelve_true(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(_window(), [_display()])
            service = CalibrationValidityService(store=store, adapter=adapter)
            assert service.calibration_required(APP, WINDOW_ID) is True
        finally:
            store.close()

    def test_carga_perfil_mismo_escala_otro_monitor_devuelve_recompute(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(
                _window(display_id=MON2), [_display(display_id=MON2), _display(display_id=MON1)]
            )
            service = CalibrationValidityService(store=store, adapter=adapter)
            env = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
            perfil = _profile(
                window_fingerprint=env.window_fingerprint(),
                display_id=MON1,
                window_state="maximized",
            )
            store.save_profile(perfil)

            perfil_cargado, val = service.load_valid_profile(APP, WINDOW_ID)
            assert perfil_cargado is not None
            assert val.action == ACTION_RECOMPUTE
            assert val.valid is True
            assert "monitor" in val.changes
            assert perfil_cargado.absolute_cache is not None
            assert "ctrl_boton" in (perfil_cargado.absolute_cache or {}).get("points", {})
        finally:
            store.close()

    def test_invalidate_for_change_marca_perfiles_obsoletos(self, tmp_path: Path):
        store = _abrir_store(tmp_path)
        try:
            adapter = _FakeAdapter(_window(), [_display()])
            service = CalibrationValidityService(store=store, adapter=adapter)
            env = EnvironmentFingerprint.capture(adapter, WINDOW_ID, machine_id=MAQUINA)
            perfil = _profile(window_fingerprint=env.window_fingerprint())
            store.save_profile(perfil)
            pid = perfil.profile_id

            n = service.invalidate_for_change(APP, "cambio de escala")
            assert n >= 1

            marcada = store.get_profile(pid)
            assert marcada is not None
            assert marcada.status == CalibrationState.OBSOLETO
            assert "cambio de escala" in (marcada.obsolete_reason or "")
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Invalidacion en entorno real (solo Windows con JARVIS_TEST_GUI_REAL=1)
# ---------------------------------------------------------------------------


class TestInvalidacionEntornoReal(unittest.TestCase):
    """Verifica invalidacion y recalculo sobre geometria real de Notepad.

    Abre una unica instancia de Notepad en el monitor de pruebas y cierra solo
    esa ventana. Nunca toca la configuracion de monitores ni Visual Studio Code.
    """

    @classmethod
    def setUpClass(cls):
        if not is_windows():
            raise unittest.SkipTest("Solo Windows")
        if os.environ.get("JARVIS_TEST_GUI_REAL") != "1":
            raise unittest.SkipTest(
                "Establecer JARVIS_TEST_GUI_REAL=1 para ejecutar este test GUI real"
            )
        if _gui_lock_activo():
            raise unittest.SkipTest(
                "Otra prueba GUI esta ejecutandose. Esperar a que termine."
            )
        _adquirir_gui_lock()
        cls.adapter = None
        cls.proc = None
        cls.hwnd = None
        cls.monitor = None
        try:
            cls.adapter = get_desktop_platform()
            cls._abrir_notepad_propietario()
        except Exception:
            try:
                cls._cerrar_notepad_propietario()
            except Exception:
                pass
            _liberar_gui_lock()
            raise

    @classmethod
    def _abrir_notepad_propietario(cls):
        antes = set(_notepad_handles(cls.adapter))
        cls.proc = subprocess.Popen([APP_NAME])
        deadline = time.time() + 10
        cls.hwnd = None
        while time.time() < deadline:
            despues = set(_notepad_handles(cls.adapter))
            nuevos = despues - antes
            if nuevos:
                cls.hwnd = sorted(nuevos)[0]
                break
            time.sleep(0.2)
        if cls.hwnd is None:
            raise RuntimeError(
                "No se detecto una ventana propia de Notepad tras lanzarla"
            )
        disp = cls.adapter.enumerate_displays()
        assert disp.ok is True, "No se pudieron enumerar monitores: %s" % disp.error
        pantallas = disp.value
        assert len(pantallas) >= 1, "Se espera al menos un monitor real"
        no_principales = [p for p in pantallas if not p.is_primary]
        if no_principales:
            cls.monitor = max(no_principales, key=lambda p: p.bounds.left)
        else:
            cls.monitor = pantallas[0]
        mv = cls.adapter.move_window_to_display(cls.hwnd, cls.monitor.display_id)
        assert mv.ok is True, "No se pudo mover Notepad al monitor de pruebas: %s" % mv.error
        win = cls.adapter.get_window(cls.hwnd)
        assert win.ok is True, "No se pudo leer la ventana de Notepad: %s" % win.error
        assert (
            win.value.display_id == cls.monitor.display_id
        ), "Notepad no quedo en el monitor objetivo"
        atexit.register(cls._cerrar_notepad_propietario)

    def test_recompute_y_recursos_planificador_notepad_real(self):
        adapter = self.adapter
        win_res = adapter.get_window(self.hwnd)
        self.assertTrue(win_res.ok, "get_window fallo: %s" % win_res.error)
        win = win_res.value
        client = win.client_bounds
        self.assertIsNotNone(client, "la ventana real no expone area cliente")
        self.assertTrue(client.is_valid(), "area cliente invalida")

        disp_res = adapter.enumerate_displays()
        self.assertTrue(disp_res.ok)
        pantallas = disp_res.value
        self.assertGreaterEqual(len(pantallas), 1)
        no_principales = [p for p in pantallas if not p.is_primary]
        monitor_destino = (
            max(no_principales, key=lambda p: p.bounds.left) if no_principales else pantallas[0]
        )

        env = EnvironmentFingerprint.capture(adapter, self.hwnd, machine_id=MAQUINA)

        # Perfil VALIDADO para la huella actual; si hay otro monitor se declara
        # para el distinto (escenario de cambio de monitor sin tocar el equipo).
        display_id_perfil = win.display_id
        otro = [p for p in pantallas if p.display_id != win.display_id]
        if otro:
            display_id_perfil = otro[0].display_id

        control = CalibratedControlRecord(
            control_id="ctrl_boton_notepad",
            app_id=APP,
            name="Boton",
            control_type="button",
            semantic_state=CalibrationState.VALIDADO,
            geometric_state=CalibrationState.VALIDADO,
            action_state=CalibrationState.VALIDADO,
            client_box_normalized=(0.10, 0.10, 0.40, 0.40),
            safe_point_normalized=(0.25, 0.25),
            interaction_method="pointer",
            provenance=["uia"],
            detector_versions={"qwen3-vl": "8b"},
            calibrated_at="2026-01-15T10:30:00+00:00",
        )
        perfil = CalibrationProfile(
            profile_id="",
            machine_id=MAQUINA,
            app_id=APP,
            platform=env.platform,
            topology_fingerprint=env.topology_fingerprint,
            window_fingerprint=env.window_fingerprint(),
            display_id=display_id_perfil,
            scale_factor=env.scale_factor,
            dpi=env.dpi,
            display_pixel_size=env.display_pixel_size,
            orientation=env.orientation,
            window_state=env.window_state,
            client_size=env.client_size,
            status=CalibrationState.VALIDADO,
            controls=[control],
        )

        tmp = Path(tempfile.mkdtemp(prefix="calib_inval_real_"))
        store = CalibrationProfileStore(db_path=str(tmp / "calibracion.sqlite3"), machine_id=MAQUINA)
        try:
            assert store.initialize() is True
            assert store.is_blocked is False
            store.save_profile(perfil)
            service = CalibrationValidityService(store=store, adapter=adapter)
            perfil_cargado, val = service.load_valid_profile(APP, self.hwnd)
            self.assertIsNotNone(perfil_cargado, "no se cargo el perfil: %s" % val.reason)
            self.assertTrue(val.valid, "perfil no valido: %s" % val.reason)
            self.assertIn(val.action, (ACTION_RECOMPUTE, ACTION_USE))
            if val.action == ACTION_RECOMPUTE:
                self.assertIn("monitor", val.changes)
            self.assertIsNotNone(perfil_cargado.absolute_cache)
            puntos = (perfil_cargado.absolute_cache or {}).get("points", {})
            self.assertIn(control.control_id, puntos)
            px, py = puntos[control.control_id]
            self.assertGreaterEqual(px, client.left, "el punto X queda fuera del area cliente")
            self.assertLess(px, client.right, "el punto X queda fuera del area cliente")
            self.assertGreaterEqual(py, client.top, "el punto Y queda fuera del area cliente")
            self.assertLess(py, client.bottom, "el punto Y queda fuera del area cliente")
            self.assertGreaterEqual(px, monitor_destino.bounds.left, "el punto queda fuera del monitor destino")
            self.assertLess(px, monitor_destino.bounds.right, "el punto queda fuera del monitor destino")
            self.assertGreaterEqual(py, monitor_destino.bounds.top, "el punto queda fuera del monitor destino")
            self.assertLess(py, monitor_destino.bounds.bottom, "el punto queda fuera del monitor destino")

            recursos = service.resources_for_planner(APP, self.hwnd)
            self.assertGreaterEqual(len(recursos), 1)
            r = recursos[0]
            self.assertEqual(r["control_id"], control.control_id)
            self.assertIsNotNone(r["point"])
            self.assertEqual(r["display_id"], win.display_id)
        finally:
            store.close()
            shutil.rmtree(tmp, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cerrar_notepad_propietario()
        finally:
            cls.proc = None
            cls.hwnd = None
            cls.monitor = None
            cls.adapter = None
            _liberar_gui_lock()

    @classmethod
    def _cerrar_notepad_propietario(cls):
        if cls.hwnd is not None:
            try:
                res = cls.adapter.close_window(cls.hwnd)
                if not res.ok:
                    cls.adapter.close_window(cls.hwnd)
                deadline = time.time() + 10
                while time.time() < deadline:
                    restante = [
                        w for w in _notepad_handles(cls.adapter) if int(w) == cls.hwnd
                    ]
                    if not restante:
                        break
                    time.sleep(0.25)
            except Exception:
                pass
            cls.hwnd = None
        if cls.proc is not None and cls.proc.poll() is None:
            try:
                cls.proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
