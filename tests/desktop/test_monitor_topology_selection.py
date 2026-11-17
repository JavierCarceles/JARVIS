# -*- coding: ascii -*-
"""
Pruebas de seleccion del monitor destino por referencia del usuario (unidad 3.8.6.6.6).

Verifica resolve_monitor_reference con geometria sintetica:
* 1, 2, 3 y 4 monitores
* origenes negativos (monitores a la izquierda o arriba del principal)
* monitores verticales (retrato) y horizontales (paisaje)
* escalas mixtas (100, 125, 150, 175, 200 y 225 por ciento)
* referencias resueltas unicamente: direccion, principal, secundaria, otra,
  actual, la siguiente, numero visual, nombre del monitor y tamano
* referencias ambiguas: varios candidatos cumplen; hay que preguntar, nunca adivina
* referencias no encontradas o no reconocidas

Integracion real en Windows: llama a get_current_topology() y solo lee la
topologia real del equipo sin modificarla, resolviendo contra ella las
referencias del usuario.
"""

from __future__ import annotations

from typing import List

import pytest

from src.desktop.monitor_topology import (
    AMBIGUOUS,
    MonitorReferenceResult,
    MonitorTopology,
    NOT_FOUND,
    RESOLVED,
    TestMonitorPolicy,
    get_current_topology,
    resolve_monitor_reference,
)
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import DESKTOP_PIXELS, DisplayInfo, Rect


def _disp(
    display_id: str,
    name: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
    primary: bool = False,
    scale_factor: float = 1.0,
) -> DisplayInfo:
    """DisplayInfo sintetico: area de trabajo un poco menor que el borde y
    resolucion fisica igual al borde."""
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
        dpi=int(round(96 * scale_factor)),
        is_primary=primary,
        rotation=0,
        refresh_rate=60.0,
        coordinate_space=DESKTOP_PIXELS,
    )


def _topologia(displays: List[DisplayInfo]) -> MonitorTopology:
    return MonitorTopology.from_displays(displays, platform="windows")


def _dos_lado_a_lado() -> MonitorTopology:
    # a: principal a la izquierda; b: secundaria a la derecha.
    return _topologia([
        _disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor B", 1920, 0, 3840, 1080, primary=False),
    ])


def _tres_lado_a_lado() -> MonitorTopology:
    return _topologia([
        _disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor B", 1920, 0, 3840, 1080, primary=False),
        _disp("c", "Monitor C", 3840, 0, 5760, 1080, primary=False),
    ])


def _cuatro_con_negativos() -> MonitorTopology:
    # c a la izquierda (origen negativo), a principal, b mas ancho a la derecha
    # y d debajo de a.
    return _topologia([
        _disp("c", "Monitor C", -1920, 0, 0, 1080, primary=False),
        _disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor B mas ancho", 1920, 0, 4000, 1080, primary=False),
        _disp("d", "Monitor D abajo", 0, 1080, 1920, 2160, primary=False),
    ])


def _con_vertical() -> MonitorTopology:
    # a horizontal principal; e vertical (retrato) a la derecha de a.
    return _topologia([
        _disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True),
        _disp("e", "Monitor E vertical", 1920, 0, 2280, 2160, primary=False),
    ])


def _escalas_mixtas() -> MonitorTopology:
    return _topologia([
        _disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True, scale_factor=1.0),
        _disp("b", "Monitor B", 1920, 0, 3840, 1080, primary=False, scale_factor=1.5),
        _disp("c", "Monitor C", 3840, 0, 5760, 1080, primary=False, scale_factor=2.25),
    ])


def _con_nombres() -> MonitorTopology:
    return _topologia([
        _disp("a", "Monitor de referencia alfa", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor de referencia beta", 1920, 0, 3840, 1080, primary=False),
    ])


def _apilados_vertical() -> MonitorTopology:
    # Dos monitores del mismo ancho, uno encima del otro: "derecha" no los distingue.
    return _topologia([
        _disp("a", "Monitor A arriba", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor B abajo", 0, 1080, 1920, 2160, primary=False),
    ])


# ---------------------------------------------------------------------------
# resolve_monitor_reference (geometria sintetica, sin GUI ni SO real)
# ---------------------------------------------------------------------------


class TestMonitorReferenceResolution:
    def test_un_solo_monitor_principal_resuelto(self) -> None:
        t = _topologia([_disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True)])
        ref = resolve_monitor_reference("principal", t)
        assert ref.resolved is True
        assert ref.display is not None
        assert ref.display.display_id == "a"
        assert ref.status == RESOLVED
        ref = resolve_monitor_reference("la 1", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"
        # Con un solo monitor, cualquier direccion resuelve a ese monitor.
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"

    def test_un_solo_monitor_la_2_no_existe(self) -> None:
        t = _topologia([_disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True)])
        ref = resolve_monitor_reference("la 2", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None
        assert ref.candidates == []

    def test_esta_sin_monitor_actual_no_adivina(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("esta", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_referencia_vacia_not_found(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("", t)
        assert ref.status == NOT_FOUND
        ref = resolve_monitor_reference("   ", t)
        assert ref.status == NOT_FOUND

    def test_referencia_no_reconocida_not_found(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("monitor azul brillante", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_dos_lado_a_lado_derecha_resuelve_b(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display is not None
        assert ref.display.display_id == "b"

    def test_dos_lado_a_lado_izquierda_resuelve_a(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("izquierda", t)
        assert ref.resolved is True
        assert ref.display is not None
        assert ref.display.display_id == "a"

    def test_dos_lado_a_lado_la_2_orden_visual(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("la 2", t)
        assert ref.resolved is True
        assert ref.display is not None
        assert ref.display.display_id == "b"
        # "pantalla dos" tambien funciona (numero en palabras).
        ref = resolve_monitor_reference("pantalla dos", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_dos_lado_a_lado_grande_empate_ambiguo(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("grande", t)
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 2
        ref = resolve_monitor_reference("pequena", t)
        assert ref.status == AMBIGUOUS
        assert len(ref.candidates) == 2

    def test_dos_lado_a_lado_principal_resuelve_a(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("principal", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"

    def test_dos_lado_a_lado_secundaria_resuelve_b(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("secundaria", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_dos_lado_a_lado_otra_resuelve_b(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("otra", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_un_solo_monitor_otra_no_hay_otra(self) -> None:
        t = _topologia([_disp("a", "Monitor A", 0, 0, 1920, 1080, primary=True)])
        ref = resolve_monitor_reference("otra", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_principal_negada_resuelve_secundaria(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("no es la principal", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_tres_lado_a_lado_derecha_resuelve_la_mas_derecha(self) -> None:
        t = _tres_lado_a_lado()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display.display_id == "c"

    def test_tres_lado_a_lado_la_3_resuelve_c(self) -> None:
        t = _tres_lado_a_lado()
        ref = resolve_monitor_reference("la 3", t)
        assert ref.resolved is True
        assert ref.display.display_id == "c"

    def test_tres_lado_a_lado_centro_resuelve_b(self) -> None:
        t = _tres_lado_a_lado()
        ref = resolve_monitor_reference("centro", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_tres_lado_a_lado_sin_vertical_not_found(self) -> None:
        t = _tres_lado_a_lado()
        ref = resolve_monitor_reference("vertical", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_cuatro_negativos_derecha_resuelve_b(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_cuatro_negativos_actual_izquierda_resuelve_c(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("a la izquierda de esta", t, current_display_id="a")
        assert ref.resolved is True
        assert ref.display.display_id == "c"

    def test_cuatro_negativos_esta_resuelve_actual(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("la actual", t, current_display_id="b")
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_cuatro_negativos_actual_siguiente_ambiguo(self) -> None:
        # Vecinos de a: c (izquierda), b (derecha) y d (abajo) -> varios candidatos.
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("la siguiente", t, current_display_id="a")
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 3

    def test_cuatro_negativos_otra_que_actual_ambiguo(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("otra", t, current_display_id="a")
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 3

    def test_cuatro_negativos_numero_visual(self) -> None:
        # Orden visual: c, a, d, b (por centro, no por orden de enumeracion).
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("la 2", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"
        ref = resolve_monitor_reference("la 4", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_cuatro_negativos_secundaria_ambiguo(self) -> None:
        # No principal: c, b y d -> ambiguo.
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("secundaria", t)
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 3

    def test_cuatro_negativos_centro_ambiguo_dos_en_centro(self) -> None:
        # a y d comparten columna central -> sin centro unico.
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("centro", t)
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 2

    def test_cuatro_negativos_grande_resuelve_b_mas_ancho(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("grande", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_cuatro_negativos_pequena_ambiguo_tres_iguales(self) -> None:
        t = _cuatro_con_negativos()
        ref = resolve_monitor_reference("pequena", t)
        assert ref.status == AMBIGUOUS
        assert len(ref.candidates) == 3

    def test_con_vertical_resuelve_vertical(self) -> None:
        t = _con_vertical()
        ref = resolve_monitor_reference("vertical", t)
        assert ref.resolved is True
        assert ref.display.display_id == "e"

    def test_con_vertical_horizontal_resuelve_a(self) -> None:
        t = _con_vertical()
        ref = resolve_monitor_reference("horizontal", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"

    def test_con_vertical_derecha_resuelve_la_vertical_por_geometria(self) -> None:
        t = _con_vertical()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display.display_id == "e"

    def test_escalas_mixtas_derecha_por_geometria_no_por_escala(self) -> None:
        # c es el mas a la derecha aunque no tenga la escala mayor unica que decida.
        t = _escalas_mixtas()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert ref.display.display_id == "c"
        # "grande" por area de escritorio: las tres tienen el mismo area -> ambiguo.
        ref = resolve_monitor_reference("grande", t)
        assert ref.status == AMBIGUOUS
        assert len(ref.candidates) == 3

    def test_nombre_de_monitor_resuelve_por_identidad(self) -> None:
        t = _con_nombres()
        ref = resolve_monitor_reference("alfa", t)
        assert ref.resolved is True
        assert ref.display.display_id == "a"
        ref = resolve_monitor_reference("beta", t)
        assert ref.resolved is True
        assert ref.display.display_id == "b"
        # Dos nombres a la vez: varios candidatos -> ambiguo.
        ref = resolve_monitor_reference("alfa beta", t)
        assert ref.status == AMBIGUOUS
        assert len(ref.candidates) == 2

    def test_nombre_inexistente_not_found(self) -> None:
        t = _con_nombres()
        ref = resolve_monitor_reference("gamma", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_dos_apilados_derecha_ambiguo(self) -> None:
        t = _apilados_vertical()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.status == AMBIGUOUS
        assert ref.display is None
        assert len(ref.candidates) == 2

    def test_izquierda_y_derecha_a_la_vez_not_found(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("izquierda derecha", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_arriba_y_abajo_a_la_vez_not_found(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("arriba abajo", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_numero_fuera_de_rango_not_found(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("la 99", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None
        ref = resolve_monitor_reference("monitor numero 0", t)
        assert ref.status == NOT_FOUND

    def test_topologia_vacia_not_found(self) -> None:
        t = _topologia([])
        ref = resolve_monitor_reference("principal", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_resolucion_no_usa_indice_de_enumeracion(self) -> None:
        t = _dos_lado_a_lado()
        invertida = MonitorTopology.from_displays(list(reversed(t.displays)), platform="windows")
        ref = resolve_monitor_reference("derecha", invertida)
        assert ref.resolved is True
        assert ref.display.display_id == "b"
        ref = resolve_monitor_reference("la 2", invertida)
        # Orden visual no cambia aunque se invierta la lista de enumeracion.
        assert ref.resolved is True
        assert ref.display.display_id == "b"

    def test_resultado_contiene_criterios_y_razon(self) -> None:
        t = _dos_lado_a_lado()
        ref = resolve_monitor_reference("derecha", t)
        assert ref.resolved is True
        assert len(ref.criteria) > 0
        assert "right" in ref.criteria
        assert ref.reason != ""
        d = ref.to_dict()
        assert d["status"] == RESOLVED
        assert d["display_id"] == "b"
        assert d["candidates"] == ["b"]


# ---------------------------------------------------------------------------
# Geometria sintetica al estilo macOS (puntos, origen negativo, sin SO real)
# ---------------------------------------------------------------------------


class TestMonitorReferenceGeometriaSinteticaMacOS:
    def test_puntos_con_origen_negativo_y_escala_retina(self) -> None:
        t = _topologia([
            _disp("p", "Principal", 0, 0, 1440, 900, primary=True, scale_factor=2.0),
            _disp("n", "Negativa", -1440, 0, 0, 900, primary=False, scale_factor=2.0),
        ])
        ref = resolve_monitor_reference("izquierda", t)
        assert ref.resolved is True
        assert ref.display.display_id == "n"
        ref = resolve_monitor_reference("principal", t)
        assert ref.resolved is True
        assert ref.display.display_id == "p"


# ---------------------------------------------------------------------------
# Integracion real en Windows: solo lectura de la topologia del equipo
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_windows(), reason="Solo Windows: get_current_topology usa el adaptador de escritorio real")
class TestMonitorReferenceEntornoReal:
    def test_principal_real_resuelve_monitor_primario(self) -> None:
        t = get_current_topology()
        assert t.fingerprint != ""
        ref = resolve_monitor_reference("principal", t)
        assert ref.resolved is True
        assert ref.display is not None
        assert ref.display.is_primary is True

    def test_la_1_real_resuelve_primero_en_orden_visual(self) -> None:
        t = get_current_topology()
        assert t.fingerprint != ""
        ref = resolve_monitor_reference("la 1", t)
        assert ref.resolved is True
        assert ref.display is not None
        orden = t.visual_order()
        assert ref.display.display_id == orden[0].display_id

    def test_derecha_real_resuelto_o_ambiguo_nunca_adivina(self) -> None:
        t = get_current_topology()
        assert t.fingerprint != ""
        ref = resolve_monitor_reference("derecha", t)
        if ref.resolved:
            assert ref.display is not None
            assert ref.display.is_primary is False
        elif ref.status == AMBIGUOUS:
            assert ref.display is None
            assert len(ref.candidates) >= 1
        else:
            assert ref.status == NOT_FOUND
            assert ref.display is None

    def test_inexistente_real_not_found(self) -> None:
        t = get_current_topology()
        assert t.fingerprint != ""
        ref = resolve_monitor_reference("monitor inexistente zzz", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_esta_sin_actual_real_not_found(self) -> None:
        t = get_current_topology()
        assert t.fingerprint != ""
        ref = resolve_monitor_reference("esta", t)
        assert ref.status == NOT_FOUND
        assert ref.display is None

    def test_dos_enumeraciones_misma_huella(self) -> None:
        t1 = get_current_topology()
        t2 = get_current_topology()
        assert t1.fingerprint == t2.fingerprint
        assert t1.fingerprint != ""

    def test_resolucion_real_coherente_con_politica_de_pruebas(self) -> None:
        t = get_current_topology()
        ref = resolve_monitor_reference("derecha", t)
        sel = TestMonitorPolicy().select(t)
        assert sel.topology_fingerprint == t.fingerprint
        if ref.resolved:
            assert sel.ok is True
            assert sel.display is not None
            assert sel.display.display_id == ref.display.display_id
        elif ref.status == AMBIGUOUS:
            assert sel.ambiguous is True or sel.ok is False
