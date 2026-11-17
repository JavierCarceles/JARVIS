# -*- coding: utf-8 -*-
"""Tests de DXcamCapture (backend opcional de captura continua de frames).

Se separan claramente:
- TestDXcamCaptureCore: tests unitarios con mocks (contrato de la clase).
- TestDXcamCaptureRealHardware: pruebas reales sobre el equipo (dxcam
  instalado, GPU/drivers de Windows, salidas de monitor reales).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import time

from src.eyes.capture.screen_capture import (
    DXcamCapture,
    MssCapture,
    AdaptiveCapture,
    evaluate_dxcam_backends,
    get_cursor_position,
)
from src.desktop.screen_manager import get_screen_manager


class _FakeCamera:
    """Camara dxcam falsa para tests de contrato."""

    def __init__(self, backend="dxgi", region=(0, 0, 800, 600)):
        self.backend = backend
        self.region = region
        self.width = 3840
        self.height = 2160
        self._capturing = False
        self._released = False
        self.latest_frame_time = 1234.5
        self.latest_frame_ticks = 12345

    def start(self):
        self._capturing = True

    def stop(self):
        self._capturing = False

    def release(self):
        self._released = True

    def grab(self):
        return np.zeros((600, 800, 3), dtype=np.uint8)

    def get_latest_frame(self):
        return np.zeros((600, 800, 3), dtype=np.uint8)

    @property
    def is_capturing(self):
        return self._capturing

    @property
    def is_released(self):
        return self._released


def _install_fake_dxcam(monkeypatch):
    """Sustituye dxcam por un modulo falso para tests de contrato."""
    fake_dxcam = SimpleNamespace(
        create=lambda **kwargs: _FakeCamera(
            backend=kwargs.get("backend", "dxgi"),
            region=kwargs.get("region"),
        ),
        output_info=lambda: (
            "Device[0] Output[0]: Res:(3840, 2160) Rot:0 Primary:True\n"
            "Device[0] Output[1]: Res:(3840, 2160) Rot:0 Primary:False\n"
        ),
    )

    def _fake_import(self):
        self._dxcam = fake_dxcam
        self._available = True
        self._error = None

    monkeypatch.setattr(DXcamCapture, "_import_dxcam", _fake_import)


class TestDXcamCaptureInit:
    def test_init_stores_config(self):
        cap = DXcamCapture.__new__(DXcamCapture)
        cap.output_idx = 1
        cap.backend = "winrt"
        cap.region = (0, 0, 800, 600)
        cap._dxcam = None
        cap._available = False
        cap._error = None
        assert cap.output_idx == 1
        assert cap.backend == "winrt"
        assert cap.region == (0, 0, 800, 600)

    def test_init_with_real_dxcam_marks_available(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap._dxcam is not None
        assert cap.available is True
        assert cap.error is None


class TestDXcamCaptureStartStopRelease:
    def test_start_creates_camera_and_starts(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        assert cap.is_capturing is True
        assert cap._camera is not None
        assert cap.effective_backend == "dxgi"
        cap.release()
        assert cap.is_released is True

    def test_start_backend_fallback_to_dxgi(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="winrt")
        # Forzar que winrt falle para ejercitar el fallback a dxgi.
        def _create_that_fails_winrt(**kwargs):
            if kwargs.get("backend") == "winrt":
                raise RuntimeError("winrt no disponible")
            return _FakeCamera(
                backend=kwargs.get("backend", "dxgi"), region=kwargs.get("region")
            )
        cap._dxcam.create = _create_that_fails_winrt
        assert cap.start() is True
        assert cap.effective_backend == "dxgi"
        cap.release()

    def test_start_no_camera_returns_false(self):
        cap = DXcamCapture.__new__(DXcamCapture)
        cap._dxcam = None
        cap._available = False
        cap._error = "dxcam no instalado"
        assert cap.start() is False
        assert cap.available is False

    def test_stop_sets_not_capturing(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        cap.stop()
        assert cap.is_capturing is False

    def test_release_sets_released_and_clears_backend(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        cap.release()
        assert cap.is_released is True
        assert cap.effective_backend is None
        assert cap.available is False


class TestDXcamCaptureGrab:
    def test_grab_returns_frame_and_updates_state(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi", region=(0, 0, 800, 600))
        cap.start()
        frame = cap.grab()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (600, 800, 3)
        assert cap.last_frame is frame
        assert cap.last_frame_time is not None
        assert cap.last_frame_ticks is not None
        cap.release()

    def test_grab_sin_camara_degrada_a_mss_reportando_fallo(self):
        # Sin camara activa: grab degrada a mss y reporta el backend efectivo
        # y el fallo, en lugar de devolver None silenciosamente.
        cap = DXcamCapture.__new__(DXcamCapture)
        cap.output_idx = 0
        cap.backend = "dxgi"
        cap.region = None
        cap._dxcam = None
        cap._camera = None
        cap._monitor_info = None
        cap._effective_backend = None
        cap._available = False
        cap._error = "dxcam sin camara"
        cap._last_frame = None
        cap._last_frame_time = None
        cap._last_frame_ticks = None
        cap._using_fallback = False
        cap._mss_fallback = MssCapture()
        try:
            frame = cap.grab()
        finally:
            cap._mss_fallback.close()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None

    def test_get_latest_frame(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        frame = cap.get_latest_frame()
        assert isinstance(frame, np.ndarray)
        assert cap.last_frame is frame
        cap.release()


class TestDXcamCaptureMonitorMapping:
    def test_match_monitor_uses_resolution_and_primary_not_index(
        self, monkeypatch
    ):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        m_primary = SimpleNamespace(
            monitor_id=1, width=3840, height=2160, is_primary=True
        )
        m_secondary = SimpleNamespace(
            monitor_id=2, width=3840, height=2160, is_primary=False
        )
        fake_sm = SimpleNamespace(monitors=[m_primary, m_secondary])
        # output_idx 0 (dxcam primaria) -> monitor primaria
        assert cap.match_monitor(fake_sm) is m_primary
        # output_idx 1 (dxcam no primaria) -> monitor no primaria, no por indice
        cap2 = DXcamCapture(output_idx=1, backend="dxgi")
        assert cap2.match_monitor(fake_sm) is m_secondary

    def test_match_monitor_falls_back_to_same_resolution(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        # Sin bandera primaria coincidente, pero misma resolucion
        m = SimpleNamespace(
            monitor_id=9, width=3840, height=2160, is_primary=False
        )
        fake_sm = SimpleNamespace(monitors=[m])
        assert cap.match_monitor(fake_sm) is m

    def test_match_monitor_no_outputs_returns_none(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        with patch.object(cap, "enumerate_outputs", return_value=[]):
            assert cap.match_monitor() is None


class TestEvaluateDXcamBackends:
    def test_evaluate_returns_expected_structure(self):
        results = evaluate_dxcam_backends(output_idx=0)
        assert "dxcam_available" in results
        assert "backends" in results
        assert "effective_backend" in results
        assert "frame_shape" in results
        assert "frame_dtype" in results
        assert "cursor_position" in results
        assert "error" in results
        assert isinstance(results["backends"], list)

    def test_evaluate_dxgi_available_on_this_machine(self):
        results = evaluate_dxcam_backends(output_idx=0)
        # dxcam esta instalado y dxgi funciona en este equipo
        assert results["dxcam_available"] is True
        dxgi = [b for b in results["backends"] if b["backend"] == "dxgi"][0]
        assert dxgi["available"] is True
        assert dxgi["frame_shape"] == (2160, 3840, 3)
        assert results["effective_backend"] == "dxgi"

    def test_evaluate_winrt_not_available(self):
        results = evaluate_dxcam_backends(output_idx=0)
        winrt = [b for b in results["backends"] if b["backend"] == "winrt"][0]
        assert winrt["available"] is False
        assert winrt["error"] is not None

    def test_cursor_position_via_os_api(self):
        pos = get_cursor_position()
        assert isinstance(pos, tuple)
        assert len(pos) == 2
        assert all(isinstance(v, int) for v in pos)


class TestDXcamCaptureRealHardware:
    @pytest.fixture(autouse=True)
    def _skip_if_no_dxcam(self):
        try:
            import dxcam  # noqa: F401
        except ImportError:
            pytest.skip("dxcam no instalado en este equipo")

    def test_real_capture_frame_shape_and_timestamp(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        frame = cap.get_latest_frame()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (2160, 3840, 3)
        assert cap.last_frame_time is not None
        assert cap.last_frame_ticks is not None
        cap.stop()
        cap.release()

    def test_real_region_crop(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi", region=(100, 100, 300, 300))
        assert cap.start() is True
        frame = cap.get_latest_frame()
        assert frame is not None
        assert frame.shape == (200, 200, 3)
        cap.stop()
        cap.release()

    def test_real_start_stop_release_lifecycle(self):
        cap = DXcamCapture(output_idx=1, backend="dxgi")
        assert cap.start() is True
        assert cap.is_capturing is True
        cap.stop()
        assert cap.is_capturing is False
        cap.release()
        assert cap.is_released is True

    def test_real_monitor_mapping_through_screen_manager(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        sm = cap.match_monitor()
        assert sm is not None
        assert sm.width == 3840
        assert sm.height == 2160
        # output 0 de dxcam es primaria
        assert sm.is_primary is True

    def test_real_cursor_independent_of_dxcam(self):
        pos = get_cursor_position()
        assert isinstance(pos, tuple) and len(pos) == 2
        # Se verifica por API del SO, no se asume que dxcam pinte el cursor.


class TestMssCapture:
    """Contrato de MssCapture con mss real (sin mocks del resultado)."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_mss(self):
        from src.eyes.capture.screen_capture import _MSS_AVAILABLE

        if not _MSS_AVAILABLE:
            pytest.skip("mss no instalado en este equipo")

    def test_mss_disponible_en_este_entorno(self):
        cap = MssCapture()
        assert cap.available is True
        assert cap.error is None
        cap.close()

    def test_capture_monitor_devuelve_frame_real(self):
        from src.desktop.screen_manager import get_monitor_info

        cap = MssCapture()
        try:
            mon = get_monitor_info(2)
            arr = cap.capture_monitor(2)
        finally:
            cap.close()
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.ndim == 3
        assert arr.shape == (mon.height, mon.width, 4)

    def test_capture_region_devuelve_frame_real(self):
        cap = MssCapture()
        try:
            arr = cap.capture_region(4000, 100, 200, 150)
        finally:
            cap.close()
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (150, 200, 4)

    def test_capture_monitor_monitor_inexistente_retorna_none_con_error(self):
        cap = MssCapture()
        try:
            arr = cap.capture_monitor(9999)
        finally:
            cap.close()
        assert arr is None
        assert cap.error is not None


class TestDXcamCaptureMssFallback:
    """Fallback a mss cuando dxcam no esta disponible, falla o devuelve frame caducado."""

    def _cap_sin_dxcam(self):
        # Estado real de la clase cuando dxcam no esta instalado.
        cap = DXcamCapture.__new__(DXcamCapture)
        cap.output_idx = 0
        cap.backend = "dxgi"
        cap.region = None
        cap._dxcam = None
        cap._camera = None
        cap._monitor_info = None
        cap._effective_backend = None
        cap._available = False
        cap._error = "dxcam no instalado"
        cap._last_frame = None
        cap._last_frame_time = None
        cap._last_frame_ticks = None
        cap._using_fallback = False
        cap._mss_fallback = MssCapture()
        return cap

    def test_grab_sin_dxcam_degrada_a_mss_y_reporta_backend(self):
        cap = self._cap_sin_dxcam()
        try:
            frame = cap.grab()
        finally:
            cap._mss_fallback.close()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.using_mss_fallback is True
        assert cap.error is not None  # el fallo de dxcam no se oculta
        assert cap.mss_fallback_available is True

    def test_grab_frame_fresco_de_dxcam_no_usa_fallback(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        try:
            frame = cap.grab()
            assert frame is not None
            assert cap.effective_backend == "dxgi"
            assert cap.fallback_active is False
            assert cap.error is None
        finally:
            cap.release()

    def test_grab_frame_nulo_de_dxcam_degrada_a_mss(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        cap._camera.grab = lambda: None
        try:
            frame = cap.grab()
            assert frame is not None
            assert cap.effective_backend == "mss"
            assert cap.fallback_active is True
            assert cap.error is not None
        finally:
            cap.release()

    def test_grab_frame_caducado_degrada_a_mss(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        frame1 = cap.grab()
        assert frame1 is not None
        assert cap.fallback_active is False
        # El siguiente grab lee los mismos ticks: frame caducado -> fallback mss.
        frame2 = cap.grab()
        assert frame2 is not None
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None
        cap.release()

    def test_start_dxcam_no_disponible_queda_reportado(self):
        cap = self._cap_sin_dxcam()
        assert cap.start() is False
        assert cap.available is False
        assert cap.error is not None
        assert cap.effective_backend is None

    def test_grab_sin_dxcam_y_sin_mss_retorna_none_sin_ocultar_error(self, monkeypatch):
        cap = self._cap_sin_dxcam()
        monkeypatch.setattr("src.eyes.capture.screen_capture._MSS_AVAILABLE", False)
        monkeypatch.setattr("src.eyes.capture.screen_capture._MssClass", None)
        cap._mss_fallback = MssCapture()
        assert cap.mss_fallback_available is False
        frame = cap.grab()
        assert frame is None
        assert cap.effective_backend is None
        assert cap.error is not None
        assert cap.fallback_active is True


class TestDXcamCaptureMssRealEntorno:
    """Pruebas reales sobre el equipo: mss real y degradacion con el estado real de dxcam."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_mss(self):
        from src.eyes.capture.screen_capture import _MSS_AVAILABLE

        if not _MSS_AVAILABLE:
            pytest.skip("mss no instalado en este equipo")

    def test_mss_captura_monitor_secundario_real(self):
        from src.desktop.screen_manager import get_monitor_info

        cap = MssCapture()
        try:
            mon = get_monitor_info(2)
            arr = cap.capture_monitor(2)
        finally:
            cap.close()
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (mon.height, mon.width, 4)

    def test_dxcam_no_disponible_degrada_a_mss_real(self):
        # dxcam esta instalado en este equipo; se fuerza el estado real de
        # no-disponibilidad para verificar el fallback con la implementacion real.
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap._dxcam is not None
        cap._dxcam = None
        cap._camera = None
        cap._available = False
        cap._error = "dxcam no disponible"
        try:
            frame = cap.grab()
        finally:
            cap._mss_fallback.close()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None


# ---------------------------------------------------------------------------
# Tests de captura adaptativa (unidad 3.8.6.3.3.13.3).
# ---------------------------------------------------------------------------


class _FakeClock(object):
    """Reloj manual controlable para pruebas deterministas de cadencia."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


class _FakeAdaptiveCamera(object):
    """Camara falsa con frames programables para AdaptiveCapture."""

    def __init__(self, frames=None):
        self.frames = list(frames or [])
        self.index = 0
        self.started = False
        self.stopped = False
        self.released = False
        self.latest_frame_time = 1000.0
        self.latest_frame_ticks = 1000
        self.grab_count = 0
        self.fail_next = False

    def start(self):
        self.started = True
        self.stopped = False

    def stop(self):
        self.stopped = True

    def release(self):
        self.released = True

    @property
    def is_capturing(self):
        return self.started and not self.stopped

    @property
    def is_released(self):
        return self.released

    @property
    def available(self):
        return True

    @property
    def effective_backend(self):
        return "fake"

    @property
    def fallback_active(self):
        return False

    def grab(self):
        self.grab_count += 1
        if self.fail_next:
            self.fail_next = False
            return None
        if self.index < len(self.frames):
            frame = self.frames[self.index]
            self.index += 1
            return frame
        if self.frames:
            return self.frames[-1]
        return np.zeros((10, 10, 3), dtype=np.uint8)


class TestAdaptiveCaptureUnit(object):
    """Tests unitarios de AdaptiveCapture con camara y reloj falsos."""

    def _stable_frame(self):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    def _changed_frame(self):
        return np.full((8, 8, 3), 200, dtype=np.uint8)

    def test_estado_inicial_inactivo(self):
        cam = _FakeAdaptiveCamera()
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=2.0)
        assert cap.state == "IDLE"
        assert cap.cadence == "low"
        assert cap.buffer_size == 0
        assert cap.last_frame is None
        assert cap.last_timestamp is None
        assert cam.started is False

    def test_start_pasa_a_estable_y_arranca_camara(self):
        cam = _FakeAdaptiveCamera()
        clock = _FakeClock(10.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=2.0)
        assert cap.start() is True
        assert cap.state == "STABLE"
        assert cap.cadence == "low"
        assert cam.started is True
        assert cap.is_capturing is True

    def test_grab_sin_start_arranca_camara_automaticamente(self):
        cam = _FakeAdaptiveCamera([self._stable_frame()])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=2.0)
        # La primera entrega arranca la camara aunque no se haya llamado start().
        r0 = cap.grab_adaptive()
        assert r0 is not None
        assert r0.frame is not None
        assert cam.started is True
        assert cap.state == "STABLE"

    def test_primera_entrega_no_reporta_transicion(self):
        cam = _FakeAdaptiveCamera([self._stable_frame(), self._changed_frame()])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0)
        cap.start()
        r0 = cap.grab_adaptive()
        assert r0 is not None
        assert r0.frame is not None
        assert r0.transition_detected is False
        assert r0.cadence == "low"
        assert r0.is_burst is False
        assert r0.frame_index == 1
        assert r0.backend == "fake"

    def test_cadencia_baja_respeta_intervalo_reloj(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()] * 4)
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock,
                              low_cadence_fps=2.0, burst_cadence_fps=2.0)
        cap.start()
        r0 = cap.grab_adaptive()
        assert r0 is not None
        assert cap.grab_adaptive() is None  # mismo instante, intervalo 0.5s
        clock.t += 0.4
        assert cap.grab_adaptive() is None  # 0.4 < 0.5
        clock.t += 0.2  # t = 0.6
        r1 = cap.grab_adaptive()
        assert r1 is not None
        assert r1.timestamp >= r0.timestamp

    def test_transicion_desencadena_rafaga_con_intervalo_corto(self):
        cam = _FakeAdaptiveCamera([self._stable_frame(), self._stable_frame(),
                                   self._changed_frame(), self._changed_frame(),
                                   self._changed_frame()])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock,
                              low_cadence_fps=2.0,      # intervalo 0.5s
                              burst_cadence_fps=20.0,   # intervalo 0.05s
                              burst_window_seconds=1.0,
                              transition_threshold=0.05)
        cap.start()
        r0 = cap.grab_adaptive()  # t=0, estable
        assert r0.transition_detected is False
        assert r0.cadence == "low"
        clock.t += 0.6  # t=0.6
        r1 = cap.grab_adaptive()  # estable vs estable -> sin transicion
        assert r1.transition_detected is False
        assert r1.cadence == "low"
        clock.t += 0.6  # t=1.2
        r2 = cap.grab_adaptive()  # estable vs cambiado -> TRANSICION
        assert r2.transition_detected is True
        assert r2.cadence == "burst"
        assert r2.is_burst is True
        assert cap.state == "BURST"
        clock.t += 0.04  # t=1.24, intervalo de rafaga 0.05s aun no cumplido
        assert cap.grab_adaptive() is None
        clock.t += 0.02  # t=1.26
        r3 = cap.grab_adaptive()  # cambiado vs cambiado, sigue en rafaga
        assert r3.cadence == "burst"
        assert r3.is_burst is True
        clock.t += 1.1  # t=2.36, ventana de rafaga (hasta 2.26) expiro
        r4 = cap.grab_adaptive()
        assert r4.cadence == "low"
        assert r4.is_burst is False
        assert cap.state == "STABLE"

    def test_frames_iguales_no_generan_transicion(self):
        frame = self._stable_frame()
        cam = _FakeAdaptiveCamera(frames=[frame, frame, frame])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock,
                              low_cadence_fps=10.0, burst_cadence_fps=1000.0)
        cap.start()
        resultados = []
        for _ in range(3):
            clock.t += 0.2
            resultados.append(cap.grab_adaptive())
        assert all(r.transition_detected is False for r in resultados)
        assert all(r.cadence == "low" for r in resultados)

    def test_buffer_acotado_descarta_antiguos(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()] * 6)
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock,
                              low_cadence_fps=1000.0, max_buffer_frames=3)
        cap.start()
        for _ in range(6):
            clock.t += 0.01
            cap.grab_adaptive()
        assert cap.buffer_size == 3

    def test_marcas_temporales_monotonas(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()] * 5)
        clock = _FakeClock(100.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0)
        cap.start()
        timestamps = []
        for _ in range(5):
            clock.t += 0.01
            r = cap.grab_adaptive()
            assert r is not None
            timestamps.append(r.timestamp)
        assert all(b >= a for a, b in zip(timestamps, timestamps[1:]))

    def test_frame_index_incremental(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()] * 3)
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0)
        cap.start()
        indexes = []
        for _ in range(3):
            clock.t += 0.01
            r = cap.grab_adaptive()
            indexes.append(r.frame_index)
        assert indexes == [1, 2, 3]

    def test_close_libera_camara_inyectada(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0)
        cap.start()
        clock.t += 0.01
        cap.grab_adaptive()
        assert cam.released is False
        assert cap.buffer_size == 1
        cap.close()
        assert cam.released is True
        assert cap.is_released is True
        assert cap.buffer_size == 0

    def test_context_manager_libera_recursos(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()])
        clock = _FakeClock(0.0)
        with AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0) as cap:
            cap.start()
            clock.t += 0.01
            cap.grab_adaptive()
            assert cam.released is False
        assert cam.released is True

    def test_liberacion_por_inactividad_detiene_stream(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()])
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock,
                              low_cadence_fps=1000.0, idle_release_seconds=0.5)
        cap.start()
        clock.t += 0.01
        cap.grab_adaptive()  # t=0.01, estable, idle_since=0.01
        clock.t += 0.6  # t=0.61, supera idle_release_seconds sin transicion
        cap.grab_adaptive()  # detiene stream por inactividad
        assert cam.stopped is True
        assert cap.state == "IDLE"
        assert cap.cadence == "low"
        # siguiente entrega reactiva la camara
        clock.t += 0.01
        r = cap.grab_adaptive()
        assert r is not None
        assert cam.started is True
        assert cap.state == "STABLE"

    def test_camara_que_devuelve_none_no_bloquea(self):
        cam = _FakeAdaptiveCamera(frames=[self._stable_frame()])
        cam.fail_next = True
        clock = _FakeClock(0.0)
        cap = AdaptiveCapture(camera=cam, clock=clock, low_cadence_fps=1000.0)
        cap.start()
        clock.t += 0.01
        r = cap.grab_adaptive()
        assert r is not None
        assert r.frame is None
        assert cap.error is not None
        clock.t += 0.01
        r2 = cap.grab_adaptive()
        assert r2 is not None
        assert r2.frame is not None


class TestAdaptiveCaptureReal(object):
    """Pruebas reales con dxcam sobre el equipo (no abren aplicaciones GUI).

    dxcam es una dependencia requerida para estas pruebas reales; no se skipea.
    Si dxcam no estuviera instalado, la recoleccion de la clase falla con
    ImportError (no se saltea).
    """

    import dxcam  # noqa: F401  # requerido para pruebas reales de hardware

    def _esperar_frame_real(self, cap, timeout_s=10.0):
        """Espera a una entrega con frame no nulo (dxcam puede devolver None
        intermitentemente y caer al fallback mss, que es comportamiento real)."""
        inicio = time.perf_counter()
        while True:
            r = cap.grab_adaptive()
            if r is not None and r.frame is not None:
                return r
            if time.perf_counter() - inicio > timeout_s:
                return None
            time.sleep(0.02)

    def test_real_capture_frame_y_backend(self):
        cap = AdaptiveCapture(output_idx=0, backend="dxgi", low_cadence_fps=20.0)
        assert cap.start() is True
        r = self._esperar_frame_real(cap)
        assert r is not None
        assert isinstance(r.frame, np.ndarray)
        assert r.frame.ndim == 3
        # dxcam puede ceder al fallback mss si no hay frame fresco; ambos son
        # backends reales y validos.
        assert r.backend in ("dxgi", "mss")
        assert r.timestamp is not None
        cap.close()
        assert cap.is_released is True

    def test_real_marcas_temporales_monotonas(self):
        cap = AdaptiveCapture(output_idx=0, backend="dxgi", low_cadence_fps=10.0)
        assert cap.start() is True
        eventos = []
        for _ in range(4):
            r = self._esperar_frame_real(cap)
            assert r is not None
            eventos.append((r.frame, r.timestamp))
        cap.close()
        assert len(eventos) == 4
        assert all(frame is not None for frame, _ in eventos)
        ts = [ts for _, ts in eventos]
        assert all(b >= a for a, b in zip(ts, ts[1:]))

    def test_real_cadencia_baja_respetada(self):
        cap = AdaptiveCapture(output_idx=0, backend="dxgi", low_cadence_fps=2.0)
        assert cap.start() is True
        r0 = self._esperar_frame_real(cap)
        assert r0 is not None
        t_primera = time.perf_counter()
        r1 = self._esperar_frame_real(cap)
        assert r1 is not None
        t_segunda = time.perf_counter()
        # La cadencia baja impone un intervalo minimo entre entregas (0.5s).
        assert t_segunda - t_primera >= 0.45
        cap.close()

    def test_real_buffer_acotado(self):
        cap = AdaptiveCapture(output_idx=0, backend="dxgi", low_cadence_fps=20.0,
                              max_buffer_frames=3)
        assert cap.start() is True
        for _ in range(6):
            r = self._esperar_frame_real(cap)
            assert r is not None
        # El buffer nunca supera el maximo configurado; se descarta lo mas antiguo.
        assert cap.buffer_size <= 3
        assert cap.buffer_size == 3
        cap.close()

    def test_real_close_libera_y_no_entrega_mas(self):
        cap = AdaptiveCapture(output_idx=0, backend="dxgi", low_cadence_fps=20.0)
        assert cap.start() is True
        r = self._esperar_frame_real(cap)
        assert r.frame is not None
        cap.close()
        assert cap.is_released is True
        assert cap.grab_adaptive() is None



