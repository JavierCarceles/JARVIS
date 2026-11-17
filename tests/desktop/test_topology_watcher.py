# -*- coding: ascii -*-
"""
Pruebas unitarias y de integracion para TopologyWatcher (unidad 3.8.6.6.5).

Verifica:
* baseline() fija la topologia de referencia y limpia eventos pendientes.
* check() re-enumerita y compara con el baseline: sin cambios (changed=False),
  monitor anadido, monitor removido, monitor modificado (cambio de escala).
* assert_unchanged(fingerprint) devuelve True si coincide y False si no.
* diff_topologies() detecta anadidos, removidos y modificados.
* start()/stop() del listener de cambios de pantalla del adaptador.
* Integracion real en Windows: check() sobre la topologia real del equipo.

Todas las pruebas unitarias usan un adaptador mockeado (sin GUI ni SO real),
salvo la prueba de integracion real que llama a get_current_topology() en
Windows y solo lee la topologia del equipo sin modificarla.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.desktop.monitor_topology import (
    MonitorTopology,
    TopologyWatcher,
    compute_topology_fingerprint,
    diff_topologies,
    get_current_topology,
)
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DisplayInfo,
    PlatformError,
    PlatformErrorCode,
    PlatformResult,
    Rect,
)


# ---------------------------------------------------------------------------
# Adaptador mockeado
# ---------------------------------------------------------------------------


class _MockAdapter:
    """Adaptador de escritorio simulado para pruebas de TopologyWatcher."""

    def __init__(self, displays: List[DisplayInfo], platform_name: str = "windows") -> None:
        self.displays = list(displays)
        self.platform_name = platform_name
        self.start_calls = 0
        self.stop_calls = 0
        self.listener_handle: Optional[Any] = None
        self.start_fail = False
        self.stop_fail = False

    def enumerate_displays(self) -> PlatformResult[List[DisplayInfo]]:
        return PlatformResult.success(list(self.displays), count=len(self.displays))

    def start_display_change_listener(self, callback: Any) -> PlatformResult[Any]:
        self.start_calls += 1
        if self.start_fail:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_SUPPORTED, "listener no disponible", operation="start_display_change_listener"
            )
        self.listener_handle = object()
        return PlatformResult.success(self.listener_handle, mechanism="mock")

    def stop_display_change_listener(self, handle: Any) -> PlatformResult[None]:
        self.stop_calls += 1
        if self.stop_fail or handle is None:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "no existe listener", operation="stop_display_change_listener"
            )
        return PlatformResult.success(None)


def _disp(
    display_id: str,
    name: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
    primary: bool = False,
    scale_factor: float = 1.0,
    dpi: int = 96,
    rotation: int = 0,
) -> DisplayInfo:
    bounds = Rect(float(left), float(top), float(right), float(bottom))
    work = Rect(float(left), float(top), float(right), float(bottom) - 40.0)
    return DisplayInfo(
        display_id=display_id,
        name=name,
        bounds=bounds,
        work_area=work,
        pixel_width=int(round(bounds.width)),
        pixel_height=int(round(bounds.height)),
        scale_factor=scale_factor,
        dpi=dpi,
        is_primary=primary,
        rotation=rotation,
        coordinate_space=DESKTOP_PIXELS,
    )


def _two_displays() -> List[DisplayInfo]:
    return [
        _disp("d1", "Principal", 0, 0, 1920, 1080, primary=True, scale_factor=1.0),
        _disp("d2", "Secundaria", 1920, 0, 3840, 1080, primary=False, scale_factor=1.0),
    ]


def _watcher_with(displays: List[DisplayInfo]) -> tuple:
    adapter = _MockAdapter(displays)
    return TopologyWatcher(adapter=adapter), adapter


# ---------------------------------------------------------------------------
# baseline()
# ---------------------------------------------------------------------------


class TestTopologyWatcherBaseline:
    def test_baseline_fija_topologia_y_limpia_eventos(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        topology = watcher.baseline()
        assert topology is not None
        assert len(topology.displays) == 2
        assert topology.fingerprint == compute_topology_fingerprint(_two_displays())
        assert watcher.pending_events() == []
        assert watcher.current_baseline is topology

    def test_baseline_reenumerita_sin_reutilizar_historico(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        primera = watcher.baseline()
        adapter.displays = [_disp("d3", "Nueva", 0, 0, 1280, 720, primary=True)]
        segunda = watcher.baseline()
        assert len(segunda.displays) == 1
        assert segunda.displays[0].display_id == "d3"
        assert segunda.fingerprint != primera.fingerprint


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestTopologyWatcherCheck:
    def test_check_sin_cambios_devuelve_changed_false(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        change = watcher.check()
        assert change.changed is False
        assert change.previous_fingerprint == change.current_fingerprint
        assert change.added == []
        assert change.removed == []
        assert change.modified == {}
        assert change.error is None

    def test_check_monitor_anadido(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        adapter.displays = _two_displays() + [
            _disp("d3", "Tercera", 3840, 0, 5760, 1080, primary=False, scale_factor=1.0)
        ]
        change = watcher.check()
        assert change.changed is True
        assert "d3" in change.added
        assert change.removed == []
        assert change.modified == {}

    def test_check_monitor_removido(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        adapter.displays = [_two_displays()[0]]
        change = watcher.check()
        assert change.changed is True
        assert change.added == []
        assert "d2" in change.removed

    def test_check_cambio_escala_marcado_como_modificado(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        d1, d2 = adapter.displays
        d2_modificado = DisplayInfo(
            display_id=d2.display_id,
            name=d2.name,
            bounds=d2.bounds,
            work_area=d2.work_area,
            pixel_width=d2.pixel_width,
            pixel_height=d2.pixel_height,
            scale_factor=2.0,
            dpi=192,
            is_primary=d2.is_primary,
            rotation=d2.rotation,
            coordinate_space=d2.coordinate_space,
        )
        adapter.displays = [d1, d2_modificado]
        change = watcher.check()
        assert change.changed is True
        assert d2.display_id in change.modified
        assert "scale_factor" in change.modified[d2.display_id]

    def test_check_sin_baseline_devuelve_cambio_false_con_primera_topologia(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        change = watcher.check()
        assert change.changed is False
        assert change.previous_fingerprint == change.current_fingerprint
        assert watcher.current_baseline is not None

    def test_check_topologia_no_disponible_devuelve_error(self) -> None:
        adapter = _MockAdapter([], platform_name="windows")

        def falla() -> PlatformResult[List[DisplayInfo]]:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "sin monitores", operation="enumerate_displays"
            )

        adapter.enumerate_displays = falla  # type: ignore[method-assign]
        watcher = TopologyWatcher(adapter=adapter)
        change = watcher.check()
        assert change.changed is True
        assert change.current_fingerprint == ""
        assert change.error is not None


# ---------------------------------------------------------------------------
# assert_unchanged()
# ---------------------------------------------------------------------------


class TestTopologyWatcherAssertUnchanged:
    def test_assert_unchanged_coincide_devuelve_true(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        assert watcher.assert_unchanged(watcher.current_baseline.fingerprint) is True

    def test_assert_unchanged_no_coincide_devuelve_false(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        adapter.displays = [_disp("d3", "Nueva", 0, 0, 1280, 720, primary=True)]
        assert watcher.assert_unchanged(watcher.current_baseline.fingerprint) is False

    def test_assert_unchanged_fingerprint_vacio_devuelve_false_si_hay_monitores(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        assert watcher.assert_unchanged("") is False

    def test_assert_unchanged_topologia_no_disponible_devuelve_false(self) -> None:
        adapter = _MockAdapter([], platform_name="windows")

        def falla() -> PlatformResult[List[DisplayInfo]]:
            return PlatformResult.failure(
                PlatformErrorCode.NOT_FOUND, "sin monitores", operation="enumerate_displays"
            )

        adapter.enumerate_displays = falla  # type: ignore[method-assign]
        watcher = TopologyWatcher(adapter=adapter)
        assert watcher.assert_unchanged("cualquier-huella") is False

    def test_assert_unchanged_usa_topologia_actual_no_el_baseline(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        watcher.baseline()
        adapter.displays = [_disp("d3", "Nueva", 0, 0, 1280, 720, primary=True)]
        assert watcher.assert_unchanged(watcher.current_baseline.fingerprint) is False


# ---------------------------------------------------------------------------
# diff_topologies()
# ---------------------------------------------------------------------------


class TestDiffTopologies:
    def test_diff_sin_cambios(self) -> None:
        displays = _two_displays()
        t1 = MonitorTopology.from_displays(displays, platform="windows")
        t2 = MonitorTopology.from_displays(displays, platform="windows")
        change = diff_topologies(t1, t2)
        assert change.changed is False
        assert change.added == []
        assert change.removed == []
        assert change.modified == {}

    def test_diff_anadido_y_removido(self) -> None:
        t1 = MonitorTopology.from_displays(_two_displays(), platform="windows")
        t2 = MonitorTopology.from_displays(
            [_two_displays()[0], _disp("d3", "Tercera", 3840, 0, 5760, 1080)], platform="windows"
        )
        change = diff_topologies(t1, t2)
        assert change.changed is True
        assert "d3" in change.added
        assert "d2" in change.removed

    def test_diff_modificado(self) -> None:
        d1, d2 = _two_displays()
        d2_mod = DisplayInfo(
            display_id=d2.display_id,
            name=d2.name,
            bounds=d2.bounds,
            work_area=d2.work_area,
            pixel_width=d2.pixel_width,
            pixel_height=d2.pixel_height,
            scale_factor=1.5,
            dpi=144,
            is_primary=d2.is_primary,
            rotation=d2.rotation,
            coordinate_space=d2.coordinate_space,
        )
        t1 = MonitorTopology.from_displays([d1, d2], platform="windows")
        t2 = MonitorTopology.from_displays([d1, d2_mod], platform="windows")
        change = diff_topologies(t1, t2)
        assert change.changed is True
        assert d2.display_id in change.modified
        assert "scale_factor" in change.modified[d2.display_id]


# ---------------------------------------------------------------------------
# start() / stop()
# ---------------------------------------------------------------------------


class TestTopologyWatcherStartStop:
    def test_start_con_adaptador_disponible_devuelve_true(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        resultado = watcher.start(callback=lambda motivo: None)
        assert resultado is True
        assert watcher.listening is True
        assert adapter.start_calls == 1
        watcher.stop()
        assert watcher.listening is False
        assert adapter.stop_calls == 1

    def test_start_con_adaptador_no_soportado_devuelve_false(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        adapter.start_fail = True
        resultado = watcher.start(callback=lambda motivo: None)
        assert resultado is False
        assert watcher.listening is False

    def test_stop_sin_listener_no_hace_nada(self) -> None:
        watcher, _ = _watcher_with(_two_displays())
        watcher.stop()
        assert watcher.listening is False

    def test_stop_con_handle_invalido_devuelve_false_en_adaptador(self) -> None:
        watcher, adapter = _watcher_with(_two_displays())
        adapter.stop_fail = True
        watcher.start(callback=lambda motivo: None)
        watcher.stop()
        assert watcher.listening is False
        assert adapter.stop_calls == 1


# ---------------------------------------------------------------------------
# Integracion real en Windows
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_windows(), reason="Solo Windows: adaptador de escritorio real")
class TestTopologyWatcherEntornoReal:
    def test_check_sobre_topologia_real_devuelve_sin_cambios(self) -> None:
        watcher = TopologyWatcher()
        topology = watcher.baseline()
        assert topology is not None
        assert len(topology.displays) >= 1
        assert topology.fingerprint != ""
        change = watcher.check()
        assert change.changed is False
        assert change.previous_fingerprint == change.current_fingerprint

    def test_assert_unchanged_con_huella_real_devuelve_true(self) -> None:
        watcher = TopologyWatcher()
        topology = watcher.baseline()
        assert watcher.assert_unchanged(topology.fingerprint) is True

    def test_assert_unchanged_con_huella_inventada_devuelve_false(self) -> None:
        watcher = TopologyWatcher()
        watcher.baseline()
        assert watcher.assert_unchanged("huella-inexistente-0000") is False
