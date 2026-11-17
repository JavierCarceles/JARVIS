# -*- coding: ascii -*-
"""
Pruebas unitarias del modelo de topologia de monitores (unidad 3.8.6.6.2).

Verifica:
* Construccion de MonitorTopology a partir de DisplayInfo y descarte de
  geometria invalida.
* Relaciones espaciales izquierda/derecha/arriba/abajo entre monitores.
* Monitores centrales (centro) de una disposicion.
* Tamano relativo (mayor/menor), orientacion (retrato/paisaje) y principal.
* Huella digital de topologia (orden independiente, invalida ante cambios).
* Consultas de punto/rectangulo y orden visual.

Todas las pruebas usan DisplayInfo sinteticos (sin GUI ni SO real), salvo la
prueba de integracion real que llama a get_current_topology() en Windows y
solo lee la topologia del equipo sin modificarla.
"""

from __future__ import annotations

from typing import List

import pytest

from src.desktop.monitor_topology import (
    DIRECTION_ABOVE,
    DIRECTION_BELOW,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    MonitorTopology,
    compute_topology_fingerprint,
    get_current_topology,
)
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import DESKTOP_PIXELS, DisplayInfo, Rect


# ---------------------------------------------------------------------------
# Constructores de monitores sinteticos
# ---------------------------------------------------------------------------


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
    refresh_rate: float = 60.0,
) -> DisplayInfo:
    """Crea un DisplayInfo sintetico con area de trabajo un poco menor que el
    borde (simula barra de tareas) y resolucion fisica igual al borde."""
    bounds = Rect(float(left), float(top), float(right), float(bottom))
    work = Rect(float(left), float(top), float(right), float(bottom) - 40.0)
    pw = int(round(bounds.width))
    ph = int(round(bounds.height))
    return DisplayInfo(
        display_id=display_id,
        name=name,
        bounds=bounds,
        work_area=work,
        pixel_width=pw,
        pixel_height=ph,
        scale_factor=scale_factor,
        dpi=dpi,
        is_primary=primary,
        rotation=rotation,
        refresh_rate=refresh_rate,
        coordinate_space=DESKTOP_PIXELS,
    )


def _topologia(displays: List[DisplayInfo]) -> MonitorTopology:
    return MonitorTopology.from_displays(displays, platform="windows")


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------


class TestMonitorTopologyConstruction:
    def test_longitud_y_vacia(self) -> None:
        t = _topologia([])
        assert len(t) == 0
        assert t.is_empty is True

    def test_descarte_geometria_invalida(self) -> None:
        valido = _disp("d1", "V", 0, 0, 100, 100)
        sin_bounds = DisplayInfo(
            display_id="d2",
            name="S",
            bounds=None,  # type: ignore[arg-type]
            work_area=Rect(0, 0, 10, 10),
            pixel_width=10,
            pixel_height=10,
        )
        invalido = _disp("d3", "I", 100, 100, 100, 100)  # right == left, invalido
        t = _topologia([valido, sin_bounds, invalido])
        assert len(t) == 1
        assert t.get("d1") is valido
        assert t.get("d2") is None
        assert t.get("d3") is None

    def test_get_por_display_id(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.get("a") is a
        assert t.get("b") is b
        assert t.get("inesistente") is None
        assert t.get(None) is None

    def test_virtual_bounds(self) -> None:
        a = _disp("a", "A", -1920, 0, 0, 1080)
        b = _disp("b", "B", 0, 0, 1920, 1080, primary=True)
        t = _topologia([a, b])
        vb = t.virtual_bounds()
        assert vb is not None
        assert vb.to_tuple() == (-1920.0, 0.0, 1920.0, 1080.0)


# ---------------------------------------------------------------------------
# Relaciones espaciales
# ---------------------------------------------------------------------------


class TestRelacionesEspaciales:
    def test_dos_monitores_lado_a_lado(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080, primary=True)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        rel = t.relations("a")
        assert rel[DIRECTION_RIGHT] == ["b"]
        assert rel[DIRECTION_LEFT] == []
        assert rel[DIRECTION_ABOVE] == []
        assert rel[DIRECTION_BELOW] == []
        rel_b = t.relations("b")
        assert rel_b[DIRECTION_LEFT] == ["a"]
        assert rel_b[DIRECTION_RIGHT] == []

    def test_dos_monitores_apilados_verticalmente(self) -> None:
        arriba = _disp("up", "Arriba", 0, -1080, 1920, 0)
        abajo = _disp("down", "Abajo", 0, 0, 1920, 1080, primary=True)
        t = _topologia([arriba, abajo])
        rel_arriba = t.relations("up")
        assert rel_arriba[DIRECTION_BELOW] == ["down"]
        rel_abajo = t.relations("down")
        assert rel_abajo[DIRECTION_ABOVE] == ["up"]

    def test_monitor_sin_vecinos_devuelve_listas_vacias(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        t = _topologia([a])
        for direccion in (DIRECTION_LEFT, DIRECTION_RIGHT, DIRECTION_ABOVE, DIRECTION_BELOW):
            assert t.relations("a")[direccion] == []

    def test_relaciones_desconoce_monitor_inexistente(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        t = _topologia([a])
        assert t.relations("no-existe") == {
            DIRECTION_LEFT: [],
            DIRECTION_RIGHT: [],
            DIRECTION_ABOVE: [],
            DIRECTION_BELOW: [],
        }

    def test_rejilla_cuatro_monitores(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080, primary=True)      # abajo-izquierda
        b = _disp("b", "B", 1920, 0, 3840, 1080)                  # abajo-derecha
        c = _disp("c", "C", 0, -1080, 1920, 0)                   # arriba-izquierda
        d = _disp("d", "D", 1920, -1080, 3840, 0)                # arriba-derecha
        t = _topologia([a, b, c, d])
        assert t.relations("a")[DIRECTION_RIGHT] == ["b"]
        assert t.relations("a")[DIRECTION_ABOVE] == ["c"]
        assert t.relations("b")[DIRECTION_LEFT] == ["a"]
        assert t.relations("b")[DIRECTION_ABOVE] == ["d"]
        assert t.relations("c")[DIRECTION_RIGHT] == ["d"]
        assert t.relations("c")[DIRECTION_BELOW] == ["a"]
        assert t.relations("d")[DIRECTION_LEFT] == ["c"]
        assert t.relations("d")[DIRECTION_BELOW] == ["b"]


# ---------------------------------------------------------------------------
# Centro, tamano relativo, orientacion y principal
# ---------------------------------------------------------------------------


class TestCentroTamanoOrientacionPrincipal:
    def test_central_displays_tres_en_fila(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080, primary=True)
        c = _disp("c", "C", 3840, 0, 5760, 1080)
        t = _topologia([a, b, c])
        centrales = [d.display_id for d in t.central_displays()]
        assert centrales == ["b"]

    def test_central_displays_dos_monitores_no_hay_central(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.central_displays() == []

    def test_central_displays_vacia(self) -> None:
        assert _topologia([]).central_displays() == []

    def test_largest_y_smallest(self) -> None:
        pequena = _disp("p", "P", 0, 0, 800, 600)
        grande = _disp("g", "G", 0, 0, 1920, 1080, primary=True)
        t = _topologia([pequena, grande])
        assert [d.display_id for d in t.largest()] == ["g"]
        assert [d.display_id for d in t.smallest()] == ["p"]

    def test_largest_empate_devuelve_ambos(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 0, 0, 1920, 1080)
        t = _topologia([a, b])
        assert set(d.display_id for d in t.largest()) == {"a", "b"}
        assert set(d.display_id for d in t.smallest()) == {"a", "b"}

    def test_primary_explicito(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080, primary=True)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.primary() is a
        assert t.primary().is_primary is True

    def test_primary_sin_marcado_usa_origen_cero(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)  # contiene (0,0)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.primary() is a

    def test_primary_none_sin_ningun_monitor(self) -> None:
        assert _topologia([]).primary() is None

    def test_portrait_y_landscape(self) -> None:
        paisaje = _disp("p", "P", 0, 0, 1920, 1080)
        retrato = _disp("r", "R", 0, 0, 1080, 1920)
        t = _topologia([paisaje, retrato])
        assert [d.display_id for d in t.landscape_displays()] == ["p"]
        assert [d.display_id for d in t.portrait_displays()] == ["r"]

    def test_orientacion_propiedad(self) -> None:
        assert _disp("x", "X", 0, 0, 1920, 1080).orientation == "landscape"
        assert _disp("y", "Y", 0, 0, 1080, 1920).orientation == "portrait"


# ---------------------------------------------------------------------------
# Huella digital de topologia
# ---------------------------------------------------------------------------


class TestHuellaDigital:
    def test_fingerprint_independiente_del_orden(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        f1 = compute_topology_fingerprint([a, b])
        f2 = compute_topology_fingerprint([b, a])
        assert f1 == f2
        assert len(f1) == 64  # sha256 hex

    def test_fingerprint_cambia_si_cambia_geometria(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        f1 = compute_topology_fingerprint([a, b])
        b_movido = _disp("b", "B", 2000, 0, 3920, 1080)
        f2 = compute_topology_fingerprint([a, b_movido])
        assert f1 != f2

    def test_fingerprint_cambia_si_cambia_escala(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b1 = _disp("b", "B", 1920, 0, 3840, 1080, scale_factor=1.0)
        b2 = _disp("b", "B", 1920, 0, 3840, 1080, scale_factor=2.0)
        assert compute_topology_fingerprint([a, b1]) != compute_topology_fingerprint([a, b2])

    def test_fingerprint_deterministico(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        assert compute_topology_fingerprint([a, b]) == compute_topology_fingerprint([a, b])

    def test_monitor_topology_calcula_huella_al_instanciar(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.fingerprint == compute_topology_fingerprint([a, b])
        assert t.platform == "windows"


# ---------------------------------------------------------------------------
# Consultas de punto, rectangulo y orden visual
# ---------------------------------------------------------------------------


class TestConsultasGeometricas:
    def test_display_for_point(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        assert t.display_for_point(500, 500) is a
        assert t.display_for_point(3000, 500) is b
        assert t.display_for_point(-100, 500) is None

    def test_display_for_rect_usa_mayor_interseccion(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        t = _topologia([a, b])
        rect = Rect(1800, 0, 2100, 200)  # cruza la frontera, mas area en B
        assert t.display_for_rect(rect) is b

    def test_visual_order_izquierda_a_derecha(self) -> None:
        a = _disp("a", "A", 0, 0, 1920, 1080, primary=True)
        b = _disp("b", "B", 1920, 0, 3840, 1080)
        c = _disp("c", "C", 3840, 0, 5760, 1080)
        t = _topologia([c, a, b])  # orden de enumeracion alterado
        ids = [d.display_id for d in t.visual_order()]
        assert ids == ["a", "b", "c"]
        assert t.visual_number("b") == 2
        assert t.visual_number("inexistente") is None


# ---------------------------------------------------------------------------
# Integracion real en Windows (solo lectura de la topologia del equipo)
# ---------------------------------------------------------------------------


class TestGetCurrentTopologyEntornoReal:
    @pytest.mark.skipif(not is_windows(), reason="Solo Windows: adaptador de escritorio real")
    def test_get_current_topology_devuelve_topologia_real(self) -> None:
        t = get_current_topology()
        assert t.platform == "windows"
        assert len(t.displays) >= 1
        principales = [d for d in t.displays if d.is_primary]
        assert len(principales) == 1
        for d in t.displays:
            assert d.display_id != ""
            assert d.name != ""
            assert d.bounds.is_valid()
            assert d.work_area.is_valid()
            assert d.pixel_width > 0
            assert d.pixel_height > 0
            assert d.scale_factor > 0.0
            assert d.dpi > 0
            assert d.rotation in (0, 90, 180, 270)
            assert d.orientation in ("landscape", "portrait")
            assert d.coordinate_space == DESKTOP_PIXELS
            # Las relaciones se pueden computar para cada monitor real.
            rel = t.relations(str(d.display_id))
            assert set(rel.keys()) == {
                DIRECTION_LEFT,
                DIRECTION_RIGHT,
                DIRECTION_ABOVE,
                DIRECTION_BELOW,
            }

    @pytest.mark.skipif(not is_windows(), reason="Solo Windows: adaptador de escritorio real")
    def test_get_current_topology_fingerprint_coincide_con_monitor_topology(self) -> None:
        t = get_current_topology()
        assert t.fingerprint == compute_topology_fingerprint(t.displays)
        # Dos enumeraciones consecutivas dan la misma huella sin cambios de hardware.
        t2 = get_current_topology()
        assert t.fingerprint == t2.fingerprint
