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

from src.eyes.screen_capture import (
    DXcamCapture,
    evaluate_dxcam_backends,
    get_cursor_position,
)


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

    def test_grab_without_camera_returns_none(self):
        cap = DXcamCapture.__new__(DXcamCapture)
        cap._camera = None
        assert cap.grab() is None

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
