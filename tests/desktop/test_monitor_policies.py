# -*- coding: ascii -*-
"""
Pruebas de las politicas de monitor destino (unidad 3.8.6.6.4).

Verifica:
* TargetMonitorPolicy: politica de producto (regla 4 de la cabecera del
  roadmap): usuario -> aplicacion ya abierta -> preferencia configurada ->
  ventana activa -> puntero -> principal. Orden configurable; sin indices fijos.
* TestMonitorPolicy: politica de pruebas GUI (regla 5): monitor no principal
  mas a la derecha por geometria real; con un solo monitor, ese.
* Ninguna politica usa indices fijos ni el orden de enumeracion del SO.

Todas las pruebas usan DisplayInfo/WindowInfo/PointerPosition sinteticos
(sin GUI ni SO real), salvo las pruebas de integracion real que llaman a
get_current_topology() en Windows y solo leen la topologia del equipo sin
modificarla.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from src.desktop.monitor_topology import (
    MonitorSelection,
    MonitorTopology,
    STEP_ACTIVE_WINDOW,
    STEP_APP_CURRENT,
    STEP_CONFIGURED,
    STEP_POINTER,
    STEP_PRIMARY,
    STEP_USER,
    TargetMonitorPolicy,
    TestMonitorPolicy,
    get_current_topology,
    resolve_monitor_reference,
)
from src.desktop.native_imports import is_windows
from src.desktop.platform_contract import DESKTOP_PIXELS, DisplayInfo, PointerPosition, Rect, WindowInfo


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
        dpi=96,
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
        _disp("a", "Monitor principal", 0, 0, 1920, 1080, primary=True),
        _disp("b", "Monitor secundario", 1920, 0, 3840, 1080, primary=False),
    ])


def _ventana(display_id: Optional[str], left: float, top: float, right: float, bottom: float) -> WindowInfo:
    return WindowInfo(
        window_id=1,
        pid=111,
        title="win",
        app_identity="app",
        bounds=Rect(left, top, right, bottom),
        frame_bounds=Rect(left, top, right, bottom),
        is_visible=True,
        display_id=display_id,
    )


# ---------------------------------------------------------------------------
# TargetMonitorPolicy (politica de producto, regla 4)
# ---------------------------------------------------------------------------


class TestTargetMonitorPolicy:
    def test_usuario_pide_derecha_devuelve_ese_monitor(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t, user_reference="derecha")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "user"
        assert sel.ambiguous is False
        assert sel.topology_fingerprint == t.fingerprint

    def test_usuario_pide_numero_visual_devuelve_ese_monitor(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t, user_reference="la 2")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "user"

    def test_usuario_referencia_ambigua_devuelve_candidatos_sin_monitor(self) -> None:
        # Dos monitores apilados (misma franja horizontal): "derecha" no los distingue.
        t = _topologia([
            _disp("a", "Arriba", 0, 0, 1920, 1080, primary=True),
            _disp("b", "Abajo", 0, 1080, 1920, 2160, primary=False),
        ])
        sel = TargetMonitorPolicy().select(t, user_reference="derecha")
        assert sel.ok is False
        assert sel.ambiguous is True
        assert sel.display is None
        assert len(sel.candidates) == 2

    def test_usuario_pide_monitor_inexistente_no_monitor_ni_sustituto(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t, user_reference="monitor numero 99")
        assert sel.ok is False
        assert sel.ambiguous is False
        assert sel.display is None
        assert sel.source == "user"
        # No sustituye por el principal aunque sea el ultimo recurso de la politica.

    def test_aplicacion_ya_abierta_se_queda_en_su_monitor(self) -> None:
        t = _dos_lado_a_lado()
        ventana_en_b = _ventana("b", 2000, 100, 2500, 600)
        sel = TargetMonitorPolicy().select(t, window=ventana_en_b)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "app_current"

        ventana_en_a = _ventana("a", 100, 100, 600, 600)
        sel = TargetMonitorPolicy().select(t, window=ventana_en_a)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "app_current"

    def test_aplicacion_fuera_de_monitores_avanza_a_siguiente_paso(self) -> None:
        t = _dos_lado_a_lado()
        ventana_fuera = _ventana(None, 9000, 100, 9500, 600)
        sel = TargetMonitorPolicy().select(t, window=ventana_fuera)
        assert any("fuera de los monitores actuales" in n for n in sel.notes)
        # Con fallback a principal habilitado, se elige la principal como ultimo recurso.
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "primary"
        # Sin fallback, no hay monitor.
        pol = TargetMonitorPolicy(allow_primary_fallback=False)
        sel2 = pol.select(t, window=ventana_fuera)
        assert sel2.ok is False
        assert sel2.display is None

    def test_preferencia_configurada(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t, configured_display_id="b")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "configured_preference"

    def test_monitor_preferido_desconectado_no_se_usa(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t, configured_display_id="c")
        assert any("no esta conectado" in n for n in sel.notes)
        # El monitor pedido no existe; con fallback habilitado se elige la principal.
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "primary"
        # Sin fallback, no hay monitor.
        pol = TargetMonitorPolicy(allow_primary_fallback=False)
        sel2 = pol.select(t, configured_display_id="c")
        assert sel2.ok is False
        assert sel2.display is None

    def test_ventana_activa(self) -> None:
        t = _dos_lado_a_lado()
        win = _ventana("b", 2000, 100, 2500, 600)
        sel = TargetMonitorPolicy().select(t, active_window=win)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "active_window"

    def test_puntero(self) -> None:
        t = _dos_lado_a_lado()
        ptr = PointerPosition(x=2500.0, y=500.0)
        sel = TargetMonitorPolicy().select(t, pointer=ptr)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "pointer"

    def test_puntero_sobre_principal(self) -> None:
        t = _dos_lado_a_lado()
        ptr = PointerPosition(x=500.0, y=500.0)
        sel = TargetMonitorPolicy().select(t, pointer=ptr)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "pointer"

    def test_principal_ultimo_recurso(self) -> None:
        t = _dos_lado_a_lado()
        sel = TargetMonitorPolicy().select(t)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "primary"

    def test_sin_fallback_a_principal_si_se_desactiva(self) -> None:
        t = _dos_lado_a_lado()
        pol = TargetMonitorPolicy(allow_primary_fallback=False)
        sel = pol.select(t)
        assert sel.ok is False
        assert sel.display is None

    def test_orden_configurable_puntero_delante_de_preferencia(self) -> None:
        t = _dos_lado_a_lado()
        ptr = PointerPosition(x=2500.0, y=500.0)  # sobre b
        pol = TargetMonitorPolicy(order=(STEP_POINTER, STEP_CONFIGURED, STEP_PRIMARY))
        sel = pol.select(t, pointer=ptr, configured_display_id="a")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "pointer"

    def test_orden_configurable_peticion_usuario_siempre_primero(self) -> None:
        t = _dos_lado_a_lado()
        pol = TargetMonitorPolicy(order=(STEP_PRIMARY, STEP_APP_CURRENT))
        # Aunque el orden ponga la principal primero, la peticion del usuario se evalua antes.
        sel = pol.select(t, user_reference="derecha")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "user"

    def test_topologia_vacia_sin_monitor(self) -> None:
        t = _topologia([])
        sel = TargetMonitorPolicy().select(t)
        assert sel.ok is False
        assert sel.display is None

    def test_no_usa_indices_fijos_usuario_resuelve_por_geometria(self) -> None:
        # Mismo orden invertido de la lista: "derecha" sigue siendo b por geometria, no por posicion.
        t = _dos_lado_a_lado()
        invertida = MonitorTopology.from_displays(list(reversed(t.displays)), platform="windows")
        sel = TargetMonitorPolicy().select(invertida, user_reference="derecha")
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"


# ---------------------------------------------------------------------------
# TestMonitorPolicy (politica de pruebas GUI, regla 5)
# ---------------------------------------------------------------------------


class TestTestMonitorPolicy:
    def test_elige_no_principal_mas_a_la_derecha(self) -> None:
        t = _dos_lado_a_lado()
        sel = TestMonitorPolicy().select(t)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "b"
        assert sel.source == "test_policy"
        assert sel.display.is_primary is False
        assert "derecha" in sel.reason
        assert sel.topology_fingerprint == t.fingerprint

    def test_un_solo_monitor_ese_monitor(self) -> None:
        t = _topologia([_disp("a", "Unico", 0, 0, 1920, 1080, primary=True)])
        sel = TestMonitorPolicy().select(t)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "a"
        assert sel.source == "single"
        assert "solo hay un monitor" in sel.reason

    def test_side_izquierda_elige_no_principal_mas_a_la_izquierda(self) -> None:
        # c a la izquierda con origen negativo, a principal en el centro, b a la derecha.
        c = _disp("c", "Izquierda", -1920, 0, 0, 1080, primary=False)
        a = _disp("a", "Principal", 0, 0, 1920, 1080, primary=True)
        b = _disp("b", "Derecha", 1920, 0, 3840, 1080, primary=False)
        t = _topologia([c, a, b])
        sel = TestMonitorPolicy(side="left").select(t)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "c"

    def test_prefer_non_primary_false_elige_derecho_incluso_si_es_primario(self) -> None:
        # La principal es la mas a la derecha.
        a = _disp("a", "Izquierda", 0, 0, 1920, 1080, primary=False)
        p = _disp("p", "Principal derecha", 1920, 0, 3840, 1080, primary=True)
        t = _topologia([a, p])
        sel = TestMonitorPolicy(prefer_non_primary=False).select(t)
        assert sel.ok is True
        assert sel.display is not None
        assert sel.display.display_id == "p"

    def test_topologia_vacia_sin_monitor(self) -> None:
        t = _topologia([])
        sel = TestMonitorPolicy().select(t)
        assert sel.ok is False
        assert sel.display is None

    def test_no_usa_indices_fijos_misma_geometria_distinto_orden(self) -> None:
        t = _dos_lado_a_lado()
        invertida = MonitorTopology.from_displays(list(reversed(t.displays)), platform="windows")
        sel_a = TestMonitorPolicy().select(t)
        sel_b = TestMonitorPolicy().select(invertida)
        assert sel_a.display is not None and sel_b.display is not None
        assert sel_a.display.display_id == sel_b.display.display_id == "b"

    def test_rechaza_side_invalido(self) -> None:
        with pytest.raises(ValueError):
            TestMonitorPolicy(side="centro")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integracion real en Windows (solo lectura de la topologia del equipo)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_windows(), reason="Solo Windows: adaptador de escritorio real")
class TestPoliticasEntornoReal:
    def test_politica_pruebas_sobre_topologia_real(self) -> None:
        t = get_current_topology()
        sel = TestMonitorPolicy().select(t)
        assert sel.topology_fingerprint == t.fingerprint
        if len(t.displays) == 1:
            assert sel.source == "single"
            assert sel.display is not None
            assert sel.display.display_id == t.displays[0].display_id
        else:
            assert sel.ok is True
            assert sel.display is not None
            assert sel.display.is_primary is False
            esperado = t.rightmost_non_primary()
            assert esperado is not None
            assert sel.display.display_id == esperado.display_id

    def test_politica_producto_usuario_sobre_topologia_real(self) -> None:
        t = get_current_topology()
        sel = TargetMonitorPolicy().select(t, user_reference="derecha")
        assert sel.topology_fingerprint == t.fingerprint
        assert sel.source == "user"
        if sel.ambiguous:
            assert sel.display is None
            assert len(sel.candidates) >= 1
        elif sel.ok:
            assert sel.display is not None
        else:
            assert sel.display is None

    def test_politica_producto_sin_peticion_no_adivina_ni_usa_indice(self) -> None:
        t = get_current_topology()
        sel = TargetMonitorPolicy().select(t)
        assert sel.topology_fingerprint == t.fingerprint
        assert sel.ok is True
        assert sel.display is not None
        assert sel.source == "primary"

    def test_resolucion_de_usuario_coherente_con_politica_producto(self) -> None:
        t = get_current_topology()
        ref = resolve_monitor_reference("derecha", t)
        sel = TargetMonitorPolicy().select(t, user_reference="derecha")
        if ref.resolved:
            assert sel.ok is True
            assert sel.display is not None
            assert sel.display.display_id == ref.display.display_id
        elif ref.ambiguous:
            assert sel.ambiguous is True
            assert sel.display is None
        else:
            assert sel.display is None
