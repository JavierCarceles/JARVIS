# -*- coding: ascii -*-
"""
Tests unitarios de `click_element` con verificacion del puntero (unidad
3.8.6.7.6): antes de cada clic se mueve el puntero, se lee su posicion real,
se comprueba la ventana y el control bajo el puntero y se aborta (sin clic)
si la diferencia supera la tolerancia medida.

Todos los tests usan un adaptador de escritorio falso: no tocan el SO real,
ni mueven el puntero real, ni abren ventanas.
"""

from unittest.mock import patch

from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    PlatformErrorCode,
    PlatformResult,
    Rect,
)
from src.hands.calibration.coordinate_spaces import CoordinateSpace, SpaceBox, SpacePoint
from src.hands.input.mouse import click_element


class _FakePosition:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.coordinate_space = DESKTOP_PIXELS
        self.display_id = None


class _FakeWindow:
    def __init__(self, window_id, pid):
        self.window_id = window_id
        self.pid = pid


class _FakeElement:
    def __init__(self, bbox=None, native_role="button"):
        self.bbox = bbox
        self.native_role = native_role


class _FakeAdapter:
    desktop_space = DESKTOP_PIXELS

    def __init__(self):
        self.pos = (100.0, 100.0)
        self.move_ok = True
        self.position_ok = True
        self.window_result_ok = True
        self.element_result_ok = True
        self.window = None
        self.element = None
        self.foreground_ids = set()
        self.move_calls = []
        self.click_calls = []
        self.position_calls = 0

    def enumerate_displays(self):
        primary = type("D", (), {})()
        primary.bounds = Rect(0, 0, 3840, 2160)
        primary.is_primary = True
        return PlatformResult.success([primary])

    def get_pointer_position(self):
        if not self.position_ok:
            return PlatformResult.failure(
                PlatformErrorCode.NATIVE_ERROR, "GetCursorPos fallo (falso)"
            )
        return PlatformResult.success(_FakePosition(*self.pos))

    def move_pointer(self, x, y):
        self.move_calls.append((float(x), float(y)))
        if not self.move_ok:
            return PlatformResult.failure(
                PlatformErrorCode.NATIVE_ERROR, "SetCursorPos fallo (falso)"
            )
        self.pos = (float(x), float(y))
        return PlatformResult.success(_FakePosition(*self.pos), error_px=0.0)

    def window_at_point(self, x, y):
        if not self.window_result_ok:
            return PlatformResult.failure(
                PlatformErrorCode.NATIVE_ERROR, "WindowFromPoint fallo (falso)"
            )
        return PlatformResult.success(self.window)

    def element_at_point(self, x, y):
        if not self.element_result_ok:
            return PlatformResult.failure(
                PlatformErrorCode.NATIVE_ERROR, "element_at_point fallo (falso)"
            )
        return PlatformResult.success(self.element)

    def click(self, button, count=1):
        self.click_calls.append((button, count))
        return PlatformResult.success(None)

    def is_foreground(self, window_id):
        return int(window_id) in self.foreground_ids


def _adapter_con_ventana(window_id=10, pid=100, elemento_en_puntero=None):
    adapter = _FakeAdapter()
    adapter.window = _FakeWindow(window_id, pid)
    adapter.element = elemento_en_puntero
    adapter.foreground_ids = {window_id}
    return adapter


def _click_ok(adapter, **kwargs):
    defaults = dict(
        x=100.0,
        y=100.0,
        window_id=10,
        pid=100,
        expected_box=SpaceBox(90.0, 90.0, 110.0, 110.0, CoordinateSpace.DESKTOP_PIXELS),
        wait_after=0.0,
    )
    defaults.update(kwargs)
    with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
        return click_element(**defaults)


class TestClickElementVerificacionPuntero:
    def test_click_mueve_lee_posicion_real_y_hace_clic_cuando_todo_coincide(self):
        adapter = _adapter_con_ventana()
        ok = _click_ok(adapter)
        assert ok is True
        assert adapter.move_calls == [(100.0, 100.0)]
        assert adapter.click_calls == [("left", 1)]

    def test_click_usa_posicion_actual_cuando_no_se_pide_destino(self):
        adapter = _adapter_con_ventana()
        adapter.pos = (250.0, 300.0)
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                window_id=10,
                pid=100,
                wait_after=0.0,
            )
        assert ok is True
        assert adapter.move_calls == [(250.0, 300.0)]
        assert adapter.click_calls == [("left", 1)]

    def test_click_aborta_si_error_supera_tolerancia_px(self):
        adapter = _adapter_con_ventana()
        # El adaptador dice que el puntero quedo a 10 px del destino.
        def move_pointer(x, y):
            adapter.move_calls.append((float(x), float(y)))
            adapter.pos = (110.0, 100.0)
            return PlatformResult.success(
                _FakePosition(*adapter.pos), error_px=10.0
            )

        adapter.move_pointer = move_pointer
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=100.0,
                y=100.0,
                window_id=10,
                pid=100,
                tolerance_px=5.0,
                wait_after=0.0,
            )
        assert ok is False
        assert adapter.click_calls == []

    def test_click_aborta_si_destino_fuera_de_caja_esperada(self):
        adapter = _adapter_con_ventana()
        caja_lejos = SpaceBox(900.0, 900.0, 1000.0, 1000.0, CoordinateSpace.DESKTOP_PIXELS)
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=100.0,
                y=100.0,
                window_id=10,
                pid=100,
                expected_box=caja_lejos,
                wait_after=0.0,
            )
        assert ok is False
        assert adapter.move_calls == []
        assert adapter.click_calls == []

    def test_click_aborta_si_ventana_bajo_puntero_no_es_la_esperada(self):
        adapter = _adapter_con_ventana(window_id=10, pid=100)
        adapter.window = _FakeWindow(99, 1)  # ventana bajo el puntero distinta
        adapter.foreground_ids = {10}
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=100.0,
                y=100.0,
                window_id=10,
                pid=100,
                wait_after=0.0,
            )
        assert ok is False
        assert adapter.click_calls == []

    def test_click_aborta_si_elemento_bajo_puntero_no_coincide(self):
        adapter = _adapter_con_ventana()
        # Elemento bajo el puntero con caja fuera de la esperada: sin solapamiento.
        adapter.element = _FakeElement(bbox=Rect(900.0, 900.0, 1000.0, 1000.0))
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=100.0,
                y=100.0,
                window_id=10,
                pid=100,
                expected_box=SpaceBox(90.0, 90.0, 110.0, 110.0, CoordinateSpace.DESKTOP_PIXELS),
                wait_after=0.0,
            )
        assert ok is False
        assert adapter.click_calls == []

    def test_click_aborta_si_no_se_puede_mover_el_puntero(self):
        adapter = _adapter_con_ventana()
        adapter.move_ok = False
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(x=100.0, y=100.0, wait_after=0.0)
        assert ok is False
        assert adapter.click_calls == []

    def test_click_aborta_si_no_se_puede_leer_la_posicion_real(self):
        adapter = _adapter_con_ventana()
        adapter.position_ok = False
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(window_id=10, wait_after=0.0)
        assert ok is False
        assert adapter.click_calls == []

    def test_click_aborta_si_falla_el_clic(self):
        adapter = _adapter_con_ventana()

        def click(button, count=1):
            return PlatformResult.failure(
                PlatformErrorCode.NATIVE_ERROR, "SendInput fallo (falso)"
            )

        adapter.click = click
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(x=100.0, y=100.0, wait_after=0.0)
        assert ok is False

    def test_click_sin_adapter_usa_respaldo_pyautogui(self):
        with patch("src.hands.input.mouse._desktop_platform", return_value=None):
            with patch("pyautogui.click") as click_falso:
                ok = click_element(button="right", wait_after=0.0)
        assert ok is True
        click_falso.assert_called_once_with(button="right")

    def test_click_aborta_por_failsafe(self):
        adapter = _adapter_con_ventana()
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            with patch("src.hands.input.mouse._failsafe_triggered", return_value=True):
                ok = click_element(x=100.0, y=100.0, wait_after=0.0)
        assert ok is False
        assert adapter.move_calls == []
        assert adapter.click_calls == []

    def test_click_boton_invalido_no_hace_nada(self):
        adapter = _adapter_con_ventana()
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(button="derecho", wait_after=0.0)
        assert ok is False
        assert adapter.move_calls == []
        assert adapter.click_calls == []

    def test_click_tolerancia_ratio_con_pixels_per_unit(self):
        adapter = _adapter_con_ventana()
        # Caja grande: lado menor 1000 unidades. El adaptador devuelve el
        # puntero a 250 unidades del destino => ratio 0.25 > 0.1 => aborta.
        def move_pointer(x, y):
            adapter.move_calls.append((float(x), float(y)))
            return PlatformResult.success(
                _FakePosition(float(x) + 250.0, float(y)), error_px=250.0
            )

        adapter.move_pointer = move_pointer
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=350.0,
                y=100.0,
                window_id=10,
                pid=100,
                expected_box=SpaceBox(0.0, 0.0, 1000.0, 1000.0, CoordinateSpace.DESKTOP_PIXELS),
                tolerance_ratio=0.1,
                wait_after=0.0,
            )
        assert ok is False
        assert adapter.click_calls == []

    def test_click_pasa_con_tolerancia_ratio_suficiente(self):
        adapter = _adapter_con_ventana()
        with patch("src.hands.input.mouse._desktop_platform", return_value=adapter):
            ok = click_element(
                x=150.0,
                y=100.0,
                window_id=10,
                pid=100,
                expected_box=SpaceBox(0.0, 0.0, 1000.0, 1000.0, CoordinateSpace.DESKTOP_PIXELS),
                tolerance_ratio=0.1,
                wait_after=0.0,
            )
        assert ok is True
        assert adapter.click_calls == [("left", 1)]
