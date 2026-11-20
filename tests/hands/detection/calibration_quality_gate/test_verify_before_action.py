"""
Tests de deriva entre deteccion y accion - unidad 3.8.6.4.7.

Pruebas para src/hands/detection/calibration_quality_gate.py:
take_detection_snapshot(adapter, window_id, control_box, ui_state_hash, topology, capture_ui_state)
registra el estado de ventana/PID, foco, monitor, escala/DPI, resolucion,
topologia y caja de control. verify_before_action(snapshot, adapter, ...)
compara el estado actual con el de la deteccion y devuelve:
- proceed si no hay cambios;
- recapture si cambia foco, monitor, geometria de ventana, caja del control,
  estado UI, la captura esta obsoleta o el estado no se pudo leer;
- recalibrate si cambia la identidad (ventana/PID), la escala/DPI, la
  resolucion o la topologia.
Nunca se reutiliza la deteccion anterior ante cualquier cambio.

Tests unitarios (sin SO ni GUI): adaptador de escritorio inyectado que devuelve
WindowInfo / DisplayInfo / WindowDpiInfo sinteticos. No se abren ventanas ni se
envian entradas.
"""

from __future__ import annotations

import unittest

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
    DRIFT_PROCEED,
    DRIFT_RECAPTURE,
    DRIFT_RECALIBRATE,
    take_detection_snapshot,
    verify_before_action,
)


def _window(window_id=1001, pid=100, bounds=None, client_bounds=None,
          is_visible=True, is_minimized=False, display_id="d1",
          scale_factor=1.0, dpi=96):
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
             pixel_width=3840, pixel_height=2160, scale_factor=1.0, dpi=96,
             is_primary=True):
    if bounds is None:
        bounds = Rect(0, 0, pixel_width, pixel_height)
    return DisplayInfo(
        display_id=display_id, name=name, bounds=bounds, work_area=bounds,
        pixel_width=pixel_width, pixel_height=pixel_height,
        scale_factor=scale_factor, dpi=dpi, is_primary=is_primary,
        coordinate_space=DESKTOP_PIXELS,
    )


def _dpi_info(window_id=1001, dpi=96, scale_factor=1.0):
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


def _base():
    """Estado base sin cambios: snapshot obtenido del adaptador actual."""
    adapter = _FakeDesktopAdapter(
        window=_window(),
        foreground_window_id=1001,
        displays=[_display()],
        dpi_info=_dpi_info(),
    )
    snap = take_detection_snapshot(
        adapter, 1001,
        control_box=Rect(300, 300, 400, 400),
        ui_state_hash="hash1",
    )
    return adapter, snap


class TestVerifyBeforeActionSinCambios(unittest.TestCase):
    """Ninguna deriva: verify_before_action devuelve proceed."""

    def test_sin_cambios_devuelve_proceed(self):
        adapter, snap = _base()
        drift = verify_before_action(snap, adapter)
        self.assertTrue(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_PROCEED)
        self.assertEqual(drift.changes, [])
        self.assertIn("sin cambios", drift.reason)

    def test_sin_max_age_no_marca_captura_obsoleta(self):
        adapter, snap = _base()
        drift = verify_before_action(snap, adapter)
        self.assertEqual(drift.action, DRIFT_PROCEED)


class TestVerifyBeforeActionIdentidad(unittest.TestCase):
    """Cambios de identidad (ventana/PID) => recalibrate."""

    def test_ventana_no_legible_devuelve_window_gone_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(window=None, foreground_window_id=1001,
                                      displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("window_gone", drift.changes)

    def test_pid_cambia_devuelve_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(pid=999), foreground_window_id=1001,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("pid_changed", drift.changes)


class TestVerifyBeforeActionFocoMonitor(unittest.TestCase):
    """Cambios de foco y monitor => recapture."""

    def test_foco_pierde_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(), foreground_window_id=2002,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("focus_lost", drift.changes)

    def test_foreground_no_legible_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(), foreground_window_id=None,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("foreground_unverifiable", drift.changes)

    def test_monitor_cambia_devuelve_recalibrate(self):
        # Cambiar el monitor tambien cambia la huella de topologia, asi que
        # disparan monitor_changed (recapture) y topology_changed (recalibrate);
        # gana la accion mas severa (recalibrate).
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(display_id="d2"),
            foreground_window_id=1001,
            displays=[_display(display_id="d2")],
            dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("monitor_changed", drift.changes)
        self.assertIn("topology_changed", drift.changes)


class TestVerifyBeforeActionEscalaDPIResolucion(unittest.TestCase):
    """Cambios de escala/DPI/resolucion/topologia => recalibrate."""

    def test_resolucion_cambia_devuelve_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(), foreground_window_id=1001,
            displays=[_display(display_id="d1", pixel_width=1920, pixel_height=1080)],
            dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("resolution_changed", drift.changes)

    def test_escala_cambia_devuelve_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(scale_factor=1.5), foreground_window_id=1001,
            displays=[_display(scale_factor=1.0)],
            dpi_info=_dpi_info(scale_factor=1.5))
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("scale_changed", drift.changes)

    def test_dpi_cambia_devuelve_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(dpi=144), foreground_window_id=1001,
            displays=[_display(dpi=96)], dpi_info=_dpi_info(dpi=144))
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("dpi_changed", drift.changes)

    def test_topologia_cambia_devuelve_recalibrate(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(), foreground_window_id=1001,
            displays=[_display(pixel_width=1920, pixel_height=1080)],
            dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("topology_changed", drift.changes)


class TestVerifyBeforeActionVentanaYCaja(unittest.TestCase):
    """Cambios de geometria de ventana y caja de control => recapture."""

    def test_ventana_movida_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(bounds=Rect(200, 200, 1000, 800)),
            foreground_window_id=1001, displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("window_moved_or_resized", drift.changes)

    def test_area_cliente_cambia_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(client_bounds=Rect(120, 120, 900, 700)),
            foreground_window_id=1001, displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("client_area_changed", drift.changes)

    def test_caja_control_cambia_devuelve_recapture(self):
        _, snap = _base()
        drift = verify_before_action(
            snap, _base()[0], current_control_box=Rect(500, 500, 600, 600))
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("control_box_changed", drift.changes)

    def test_caja_control_ausente_con_require_devuelve_recapture(self):
        _, snap = _base()
        adapter = _base()[0]
        drift = verify_before_action(
            snap, adapter, current_control_box=None,
            require_control_box=True)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("control_box_unverified", drift.changes)


class TestVerifyBeforeActionEstadoUI(unittest.TestCase):
    """Cambios de estado de UI y captura obsoleta => recapture."""

    def test_estado_ui_cambia_devuelve_recapture(self):
        _, snap = _base()
        drift = verify_before_action(
            snap, _base()[0], current_ui_state_hash="hash2")
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("ui_state_changed", drift.changes)

    def test_captura_obsoleta_devuelve_recapture(self):
        # El snapshot se captura con un reloj fijado en el pasado; al verificar
        # con el reloj real (ahora) la antiguedad supera max_age_seconds.
        _, snap = _base()
        adapter = _base()[0]
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

    def test_ventana_minimizada_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(is_minimized=True), foreground_window_id=1001,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("window_minimized", drift.changes)

    def test_ventana_oculta_devuelve_recapture(self):
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(is_visible=False), foreground_window_id=1001,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertFalse(drift.unchanged)
        self.assertEqual(drift.action, DRIFT_RECAPTURE)
        self.assertIn("window_hidden", drift.changes)


class TestVerifyBeforeActionGravedad(unittest.TestCase):
    """Cuando hay varios cambios, gana la accion mas severa (recalibrate > recapture)."""

    def test_recalibrate_primera_sobre_recapture(self):
        # pid_changed (recalibrate) + focus_lost (recapture) => recalibrate.
        _, snap = _base()
        adapter = _FakeDesktopAdapter(
            window=_window(pid=999), foreground_window_id=2002,
            displays=[_display()], dpi_info=_dpi_info())
        drift = verify_before_action(snap, adapter)
        self.assertEqual(drift.action, DRIFT_RECALIBRATE)
        self.assertIn("pid_changed", drift.changes)
        self.assertIn("focus_lost", drift.changes)


class TestTakeDetectionSnapshot(unittest.TestCase):
    """take_detection_snapshot copia el estado del adaptador al snapshot."""

    def test_copia_ventana_pid_foco_monitor_escala_dpi(self):
        window = _window(pid=123, display_id="d2", scale_factor=1.25, dpi=120)
        adapter = _FakeDesktopAdapter(
            window=window, foreground_window_id=1001,
            displays=[_display(display_id="d2", pixel_width=1920, pixel_height=1080,
                             scale_factor=1.25, dpi=120)],
            dpi_info=_dpi_info(dpi=120, scale_factor=1.25))
        snap = take_detection_snapshot(adapter, 1001,
                                       control_box=Rect(300, 300, 400, 400))
        self.assertEqual(snap.window_id, 1001)
        self.assertEqual(snap.pid, 123)
        self.assertEqual(snap.foreground_window_id, 1001)
        self.assertEqual(snap.display_id, "d2")
        self.assertEqual(snap.scale_factor, 1.25)
        self.assertEqual(snap.dpi, 120)
        self.assertIsNotNone(snap.control_box)
        self.assertEqual(snap.control_box, Rect(300, 300, 400, 400))
        self.assertIsInstance(snap.captured_at, float)
        self.assertIsNotNone(snap.topology_fingerprint)


if __name__ == "__main__":
    unittest.main()
