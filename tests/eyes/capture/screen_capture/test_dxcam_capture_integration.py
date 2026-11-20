# -*- coding: utf-8 -*-
"""
Tests de integracion de DXcamCapture como backend opcional de captura continua
de frames (unidad 3.8.6.3.3.13.4).

Se separan claramente:
- TestDXcamCaptureContrato: tests unitarios de contrato con fakes/mocks. No
  dependen de hardware real ni capturan la pantalla.
- TestDXcamCaptureRealHardware: pruebas reales sobre el equipo (dxcam instalado,
  GPU/drivers de Windows, salidas de monitor reales). Se saltan si dxcam no
  esta instalado. Capturan la pantalla de forma pasiva; no abren ventanas GUI
  ni interactuan con ninguna aplicacion.
- TestMssCaptureReal: pruebas reales del fallback mss sobre el equipo.
"""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import time

from src.eyes.capture.screen_capture import (
    DXcamCapture,
    MssCapture,
    evaluate_dxcam_backends,
    get_cursor_position,
    _MSS_AVAILABLE,
)
from src.desktop.screen_manager import get_screen_manager, get_monitor_info


# ---------------------------------------------------------------------------
# Fakes para tests de contrato (no hardware real)
# ---------------------------------------------------------------------------

class _FakeCamera:
    """Camara dxcam falsa para tests de contrato."""

    def __init__(self, backend="dxgi", region=None):
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


def _fake_mss_frame(self, monitor_num):
    return np.zeros((10, 10, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Tests unitarios de contrato (sin hardware real)
# ---------------------------------------------------------------------------

class TestDXcamCaptureContrato:
    def test_init_guarda_configuracion(self):
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

    def test_init_con_dxcam_marca_disponible(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap._dxcam is not None
        assert cap.available is True
        assert cap.error is None


class TestDXcamCaptureInicioParadaLiberacion:
    def test_inicio_crea_camara_y_arranca(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        assert cap.is_capturing is True
        assert cap._camera is not None
        assert cap.effective_backend == "dxgi"
        cap.release()
        assert cap.is_released is True

    def test_inicio_fallback_winrt_a_dxgi(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="winrt")

        def _crear_que_falla_winrt(**kwargs):
            if kwargs.get("backend") == "winrt":
                raise RuntimeError("winrt no disponible")
            return _FakeCamera(
                backend=kwargs.get("backend", "dxgi"),
                region=kwargs.get("region"),
            )

        cap._dxcam.create = _crear_que_falla_winrt
        assert cap.start() is True
        assert cap.effective_backend == "dxgi"
        cap.release()

    def test_inicio_sin_camara_retorna_falso(self):
        cap = DXcamCapture.__new__(DXcamCapture)
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
        assert cap.start() is False
        assert cap.available is False
        assert cap.effective_backend is None

    def test_parada_establece_no_capturando(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        cap.stop()
        assert cap.is_capturing is False

    def test_liberacion_establece_liberado_y_limpia_backend(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        cap.release()
        assert cap.is_released is True
        assert cap.effective_backend is None
        assert cap.available is False


class TestDXcamCaptureGrab:
    def test_grab_devuelve_frame_y_actualiza_estado(self, monkeypatch):
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
        assert cap.effective_backend == "dxgi"
        assert cap.fallback_active is False
        cap.release()

    def test_frame_repetido_degradara_a_mss(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap._monitor_info = SimpleNamespace(monitor_id=1)
        cap.start()
        frame1 = cap.grab()
        assert frame1 is not None
        assert cap.fallback_active is False
        # Forzar ticks repetidos: dxcam reporta el mismo frame -> caducado -> mss.
        cap._camera.latest_frame_ticks = cap.last_frame_ticks
        monkeypatch.setattr(MssCapture, "capture_monitor", _fake_mss_frame)
        frame2 = cap.grab()
        assert frame2 is not None
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None
        cap.release()

    def test_frame_nulo_degradara_a_mss(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap._monitor_info = SimpleNamespace(monitor_id=1)
        cap.start()
        cap._camera.grab = lambda: None
        monkeypatch.setattr(MssCapture, "capture_monitor", _fake_mss_frame)
        frame = cap.grab()
        assert frame is not None
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None
        cap.release()

    def test_get_latest_frame(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        cap.start()
        frame = cap.get_latest_frame()
        assert isinstance(frame, np.ndarray)
        assert cap.last_frame is frame
        cap.release()


class TestDXcamCaptureMapeoMonitor:
    def test_mapeo_usa_resolucion_y_primario_no_indice(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        m_primario = SimpleNamespace(
            monitor_id=1, width=3840, height=2160, is_primary=True
        )
        m_secundario = SimpleNamespace(
            monitor_id=2, width=3840, height=2160, is_primary=False
        )
        fake_sm = SimpleNamespace(monitors=[m_primario, m_secundario])
        # output_idx 0 (dxcam primaria) -> monitor primaria
        assert cap.match_monitor(fake_sm) is m_primario
        # output_idx 1 (dxcam secundaria) -> monitor secundaria, no por indice
        cap2 = DXcamCapture(output_idx=1, backend="dxgi")
        assert cap2.match_monitor(fake_sm) is m_secundario

    def test_mapeo_sin_salidas_retorna_none(self, monkeypatch):
        _install_fake_dxcam(monkeypatch)
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        with patch.object(cap, "enumerate_outputs", return_value=[]):
            assert cap.match_monitor() is None


class TestDXcamCaptureBackendNoDisponible:
    def test_inicio_sin_dxcam_reporta_fallo(self):
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
        try:
            assert cap.start() is False
        finally:
            cap._mss_fallback.close()
        assert cap.available is False
        assert cap.error is not None
        assert cap.effective_backend is None

    def test_grab_sin_dxcam_y_sin_mss_retorna_none_sin_ocultar_error(
        self, monkeypatch
    ):
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
        monkeypatch.setattr("src.eyes.capture.screen_capture._MSS_AVAILABLE", False)
        monkeypatch.setattr("src.eyes.capture.screen_capture._MssClass", None)
        cap._mss_fallback = MssCapture()
        assert cap.mss_fallback_available is False
        frame = cap.grab()
        assert frame is None
        assert cap.effective_backend is None
        assert cap.error is not None
        assert cap.fallback_active is True


class TestMssCaptureContrato:
    def test_mss_disponible(self):
        cap = MssCapture()
        assert cap.available is _MSS_AVAILABLE
        cap.close()

    def test_capture_monitor_monitor_inexistente_retorna_none_con_error(self):
        cap = MssCapture()
        try:
            arr = cap.capture_monitor(9999)
        finally:
            cap.close()
        assert arr is None
        assert cap.error is not None


class TestEvaluateDXcamBackends:
    def test_evaluate_devuelve_estructura_esperada(self):
        results = evaluate_dxcam_backends(output_idx=0)
        assert "dxcam_available" in results
        assert "backends" in results
        assert "effective_backend" in results
        assert "frame_shape" in results
        assert "frame_dtype" in results
        assert "cursor_position" in results
        assert "error" in results
        assert "mss_available" in results
        assert isinstance(results["backends"], list)

    def test_cursor_position_via_api_del_so(self):
        pos = get_cursor_position()
        assert isinstance(pos, tuple)
        assert len(pos) == 2
        assert all(isinstance(v, int) for v in pos)


# ---------------------------------------------------------------------------
# Pruebas reales de hardware (se saltan si dxcam no esta instalado)
# ---------------------------------------------------------------------------

class TestDXcamCaptureRealHardware:
    @pytest.fixture(autouse=True)
    def _saltar_si_no_hay_dxcam(self):
        try:
            import dxcam  # noqa: F401
        except ImportError:
            pytest.skip("dxcam no instalado en este equipo")

    def _frame_dxcam(self, cap, intentos=15, pausa=0.1):
        """Devuelve el primer frame entregado por dxcam (no por fallback mss).

        El primer grab despues de start puede devolver None (frame todavia no
        listo) y provocar el fallback mss; se reintentan hasta obtener un
        frame de dxcam (fallback_active False).
        """
        frame = None
        for _ in range(intentos):
            frame = cap.grab()
            if frame is not None and cap.fallback_active is False:
                return frame
            time.sleep(pausa)
        return frame

    def test_captura_frame_real_forma_dimensiones_y_timestamp(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        assert getattr(cap._camera, "backend", None) == "dxgi"
        frame = self._frame_dxcam(cap)
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (2160, 3840, 3)
        assert cap.last_frame_time is not None
        assert cap.last_frame_ticks is not None
        assert cap.fallback_active is False
        cap.stop()
        cap.release()

    def test_region_real(self):
        # output 1 (monitor secundario) con region: salida distinta a output 0.
        cap = DXcamCapture(output_idx=1, backend="dxgi", region=(100, 100, 300, 300))
        assert cap.start() is True
        frame = self._frame_dxcam(cap)
        assert frame is not None
        assert frame.shape == (200, 200, 3)
        cap.stop()
        cap.release()

    def test_inicio_parada_liberacion_ciclo_vida_real(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        assert cap.is_capturing is True
        cap.stop()
        assert cap.is_capturing is False
        cap.release()
        assert cap.is_released is True

    def test_mapeo_monitor_real_mediante_screen_manager(self):
        # match_monitor no crea camara: solo enumera salidas dxcam y las compara
        # con los monitores reales de ScreenManager (resolucion + primario).
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        sm = cap.match_monitor()
        assert sm is not None
        assert sm.width == 3840
        assert sm.height == 2160
        assert sm.is_primary is True

    def test_cursor_independiente_de_dxcam(self):
        pos = get_cursor_position()
        assert isinstance(pos, tuple) and len(pos) == 2
        assert all(isinstance(v, int) for v in pos)

    def test_fallback_mss_frame_nulo_real(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        frame1 = self._frame_dxcam(cap)
        assert frame1 is not None
        assert cap.fallback_active is False
        # Forzar frame nulo de dxcam: el siguiente grab degrada a mss.
        with patch.object(DXcamCapture, "_grab_dxcam_frame", return_value=None):
            frame2 = cap.grab()
        assert frame2 is not None
        assert isinstance(frame2, np.ndarray)
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None
        cap.stop()
        cap.release()

    def test_fallback_mss_frame_repetido_real(self):
        cap = DXcamCapture(output_idx=0, backend="dxgi")
        assert cap.start() is True
        frame1 = self._frame_dxcam(cap)
        assert frame1 is not None
        assert cap.fallback_active is False
        # Forzar frame caducado (repetido): dxcam no produce frame nuevo -> mss.
        with patch.object(DXcamCapture, "_grab_dxcam_frame", return_value=None):
            frame2 = cap.grab()
        assert frame2 is not None
        assert isinstance(frame2, np.ndarray)
        assert cap.effective_backend == "mss"
        assert cap.fallback_active is True
        assert cap.error is not None
        cap.stop()
        cap.release()


class TestMssCaptureReal:
    @pytest.fixture(autouse=True)
    def _saltar_si_no_hay_mss(self):
        from src.eyes.capture.screen_capture import _MSS_AVAILABLE

        if not _MSS_AVAILABLE:
            pytest.skip("mss no instalado en este equipo")

    def test_mss_captura_monitor_primario_real(self):
        cap = MssCapture()
        try:
            mon = get_monitor_info(1)
            arr = cap.capture_monitor(1)
        finally:
            cap.close()
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.ndim == 3
        assert arr.shape == (mon.height, mon.width, 4)

    def test_mss_captura_monitor_secundario_real(self):
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

    def test_mss_captura_region_real(self):
        cap = MssCapture()
        try:
            arr = cap.capture_region(0, 0, 200, 150)
        finally:
            cap.close()
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (150, 200, 4)

    def test_mss_monitor_inexistente_retorna_none(self):
        cap = MssCapture()
        try:
            arr = cap.capture_monitor(9999)
        finally:
            cap.close()
        assert arr is None
        assert cap.error is not None
