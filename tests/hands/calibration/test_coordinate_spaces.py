# -*- coding: utf-8 -*-
"""
Tests unitarios (deterministas, sin SO ni GUI) de los espacios de coordenadas
formales y sus transformaciones (unidad 3.8.6.7.1 del roadmap).

Cubren: los siete espacios formales (FRAME_PIXELS, MONITOR_PIXELS,
DESKTOP_PIXELS, DESKTOP_POINTS, WINDOW_RECT, WINDOW_CLIENT,
CLIENT_NORMALIZED), la resolucion por valor y los alias heredados, el espacio
de escritorio nativo por SO, la validacion del contexto de transformacion,
los recorridos redondo entre todos los espacios con geometria sintetica de
Windows y macOS, el punto de entrada con redondeo explicito, la conversion
Cocoa<->Quartz y puntos<->pixeles de macOS, el punto seguro dentro de un
control y la prohibicion de mezclar espacios sin transformacion explicita.

Todas las pruebas usan geometria sintetica en memoria; no capturan pantalla,
no leen el SO real y no abren ventanas.
"""

import pytest  # noqa: E402

from src.desktop.platform_contract import (
    CaptureResult,
    DESKTOP_PIXELS,
    DESKTOP_POINTS,
    DisplayInfo,
    PLATFORM_MACOS,
    PLATFORM_WINDOWS,
    Rect,
    WindowInfo,
)
from src.hands.calibration.coordinate_spaces import (
    CoordinateSpace,
    CoordinateTransformError,
    DESKTOP_SPACES,
    SpaceBox,
    SpacePoint,
    TransformContext,
    CoordinateTransformer,
    build_transform_context,
    capture_pixels_per_unit,
    compute_safe_point,
    cocoa_to_quartz_point,
    cocoa_to_quartz_rect,
    desktop_space_for_platform,
    monitor_pixel_ratio,
    normalized_1000_box_to_frame,
    points_to_pixels,
    pixels_to_points,
    quartz_to_cocoa_point,
    quartz_to_cocoa_rect,
    visible_window_rect,
)

# ---------------------------------------------------------------------------
# Helpers de geometria sintetica (Windows y macOS)
# ---------------------------------------------------------------------------

def _display_windows(display_id=r"\\.\DISPLAY1", left=0, top=0, width=1920,
                     height=1080, scale=1.0, primary=True,
                     pixel_width=None, pixel_height=None):
    return DisplayInfo(
        display_id=display_id,
        name="Monitor",
        bounds=Rect(float(left), float(top), float(left + width), float(top + height)),
        work_area=Rect(float(left), float(top), float(left + width), float(top + height)),
        pixel_width=int(width) if pixel_width is None else int(pixel_width),
        pixel_height=int(height) if pixel_height is None else int(pixel_height),
        scale_factor=float(scale),
        dpi=int(round(96.0 * float(scale))),
        is_primary=bool(primary),
        rotation=0,
        coordinate_space=DESKTOP_PIXELS,
    )


def _display_macos(display_id="CGDisplay-1", left=0, top=0, width=1440,
                   height=900, scale=2.0, primary=True):
    return DisplayInfo(
        display_id=display_id,
        name="Monitor",
        bounds=Rect(float(left), float(top), float(left + width), float(top + height)),
        work_area=Rect(float(left), float(top), float(left + width), float(top + height)),
        pixel_width=int(round(width * float(scale))),
        pixel_height=int(round(height * float(scale))),
        scale_factor=float(scale),
        dpi=int(round(132.0 * float(scale))),
        is_primary=bool(primary),
        rotation=0,
        coordinate_space=DESKTOP_POINTS,
    )


def _window(window_id=1001, pid=1234, bounds=None, client_bounds=None,
            frame_bounds=None, display_id=r"\\.\DISPLAY1",
            coordinate_space=DESKTOP_PIXELS):
    if bounds is None:
        bounds = Rect(100.0, 100.0, 900.0, 700.0)
    if client_bounds is None:
        client_bounds = Rect(110.0, 110.0, 890.0, 690.0)
    if frame_bounds is None:
        frame_bounds = Rect(98.0, 98.0, 902.0, 702.0)
    return WindowInfo(
        window_id=window_id,
        pid=pid,
        title="Ventana de prueba",
        app_identity="app.test",
        bounds=bounds,
        client_bounds=client_bounds,
        frame_bounds=frame_bounds,
        is_visible=True,
        is_minimized=False,
        is_maximized=False,
        is_foreground=True,
        display_id=display_id,
        scale_factor=1.0,
        dpi=96,
        dpi_awareness="per_monitor",
        coordinate_space=coordinate_space,
    )


def _capture(region=None, pixel_width=1920, pixel_height=1080, ppu_x=1.0,
             ppu_y=1.0, coordinate_space=DESKTOP_PIXELS):
    if region is None:
        region = Rect(0.0, 0.0, 1920.0, 1080.0)
    return CaptureResult(
        region=region,
        pixel_width=int(pixel_width),
        pixel_height=int(pixel_height),
        backend="mss",
        pixels_per_unit_x=ppu_x,
        pixels_per_unit_y=ppu_y,
        coordinate_space=coordinate_space,
    )


# ---------------------------------------------------------------------------
# Espacios formales
# ---------------------------------------------------------------------------

def test_coordinate_spaces_definen_los_siete_espacios_formales():
    esperados = {
        CoordinateSpace.FRAME_PIXELS,
        CoordinateSpace.MONITOR_PIXELS,
        CoordinateSpace.DESKTOP_PIXELS,
        CoordinateSpace.DESKTOP_POINTS,
        CoordinateSpace.WINDOW_RECT,
        CoordinateSpace.WINDOW_CLIENT,
        CoordinateSpace.CLIENT_NORMALIZED,
    }
    assert set(CoordinateSpace) == esperados
    assert DESKTOP_SPACES == (CoordinateSpace.DESKTOP_PIXELS, CoordinateSpace.DESKTOP_POINTS)


def test_from_value_resuelve_todos_los_espacios_y_alias_legados():
    for espacio in CoordinateSpace:
        assert CoordinateSpace.from_value(espacio) is espacio
        assert CoordinateSpace.from_value(espacio.value) is espacio
    assert CoordinateSpace.from_value("image_pixels") is CoordinateSpace.FRAME_PIXELS
    assert CoordinateSpace.from_value("monitor_relative") is CoordinateSpace.MONITOR_PIXELS
    assert CoordinateSpace.from_value("window_relative") is CoordinateSpace.WINDOW_RECT
    with pytest.raises(CoordinateTransformError):
        CoordinateSpace.from_value("espacio_inexistente")
    with pytest.raises(CoordinateTransformError):
        CoordinateSpace.from_value("")


def test_desktop_space_for_platform_por_sistema():
    assert desktop_space_for_platform(PLATFORM_WINDOWS) is CoordinateSpace.DESKTOP_PIXELS
    assert desktop_space_for_platform(PLATFORM_MACOS) is CoordinateSpace.DESKTOP_POINTS
    with pytest.raises(CoordinateTransformError):
        desktop_space_for_platform("linux")


# ---------------------------------------------------------------------------
# SpacePoint y SpaceBox llevan su espacio
# ---------------------------------------------------------------------------

def test_space_point_y_space_box_llevan_espacio_y_comparan_mismo_espacio():
    punto = SpacePoint(10.0, 20.0, CoordinateSpace.WINDOW_RECT)
    assert punto.to_tuple() == (10.0, 20.0)
    assert punto.to_dict() == {"x": 10.0, "y": 20.0, "space": "WINDOW_RECT"}
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_RECT)
    assert caja.contains(SpacePoint(50.0, 50.0, CoordinateSpace.WINDOW_RECT))
    assert not caja.contains(SpacePoint(150.0, 50.0, CoordinateSpace.WINDOW_RECT))
    centro = caja.center()
    assert centro == SpacePoint(50.0, 50.0, CoordinateSpace.WINDOW_RECT)
    assert caja.to_rect() == Rect(0.0, 0.0, 100.0, 100.0)
    caja2 = SpaceBox.from_rect(Rect(5.0, 5.0, 55.0, 55.0), CoordinateSpace.DESKTOP_PIXELS)
    assert caja2.space is CoordinateSpace.DESKTOP_PIXELS
    assert caja2.to_dict()["space"] == "DESKTOP_PIXELS"
    with pytest.raises(CoordinateTransformError):
        caja.contains(SpacePoint(50.0, 50.0, CoordinateSpace.DESKTOP_PIXELS))


# ---------------------------------------------------------------------------
# TransformContext valida coherencia de espacio de escritorio
# ---------------------------------------------------------------------------

def test_transform_context_valida_coherencia_de_espacio_de_escritorio():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    contexto.validate()
    assert contexto.desktop_space is CoordinateSpace.DESKTOP_PIXELS

    pantalla_mal = _display_macos()
    contexto_mal = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla_mal, window=ventana)
    with pytest.raises(CoordinateTransformError):
        contexto_mal.validate()

    ventana_mal = _window(coordinate_space=DESKTOP_POINTS)
    contexto_mal2 = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana_mal)
    with pytest.raises(CoordinateTransformError):
        contexto_mal2.validate()


# ---------------------------------------------------------------------------
# CoordinateTransformer: recorridos redondo entre espacios
# ---------------------------------------------------------------------------

def _transformador_windows():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    return CoordinateTransformer(contexto), pantalla, ventana


def test_transformador_redondo_ventana_y_cliente_windows():
    transformer, _, _ = _transformador_windows()
    punto = SpacePoint(500.0, 400.0, CoordinateSpace.DESKTOP_PIXELS)

    en_ventana = transformer.transform_point(punto, CoordinateSpace.WINDOW_RECT)
    assert en_ventana.space is CoordinateSpace.WINDOW_RECT
    assert en_ventana.x == 400.0 and en_ventana.y == 300.0
    assert transformer.transform_point(en_ventana, CoordinateSpace.DESKTOP_PIXELS) == punto

    en_cliente = transformer.transform_point(punto, CoordinateSpace.WINDOW_CLIENT)
    assert en_cliente.space is CoordinateSpace.WINDOW_CLIENT
    assert en_cliente.x == 390.0 and en_cliente.y == 290.0
    assert transformer.transform_point(en_cliente, CoordinateSpace.DESKTOP_PIXELS) == punto

    normalizado = transformer.transform_point(punto, CoordinateSpace.CLIENT_NORMALIZED)
    assert normalizado.space is CoordinateSpace.CLIENT_NORMALIZED
    assert abs(normalizado.x - 0.5) < 1e-9 and abs(normalizado.y - 0.5) < 1e-9
    assert transformer.transform_point(normalizado, CoordinateSpace.DESKTOP_PIXELS) == punto

    # mismo espacio: devuelve el mismo objeto sin transformar
    assert transformer.transform_point(punto, CoordinateSpace.DESKTOP_PIXELS) is punto


def test_transformador_redondo_frame_y_monitor_windows():
    pantalla = _display_windows()
    ventana = _window()
    captura = _capture(region=Rect(0.0, 0.0, 1920.0, 1080.0), ppu_x=1.0, ppu_y=1.0)
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana, capture=captura)
    transformer = CoordinateTransformer(contexto)
    punto = SpacePoint(500.0, 400.0, CoordinateSpace.DESKTOP_PIXELS)

    en_frame = transformer.transform_point(punto, CoordinateSpace.FRAME_PIXELS)
    assert en_frame.space is CoordinateSpace.FRAME_PIXELS
    assert en_frame.x == 500.0 and en_frame.y == 400.0
    assert transformer.transform_point(en_frame, CoordinateSpace.DESKTOP_PIXELS) == punto

    en_monitor = transformer.transform_point(punto, CoordinateSpace.MONITOR_PIXELS)
    assert en_monitor.space is CoordinateSpace.MONITOR_PIXELS
    assert en_monitor.x == 500.0 and en_monitor.y == 400.0  # proporcion 1:1 en windows escala 1
    assert transformer.transform_point(en_monitor, CoordinateSpace.DESKTOP_PIXELS) == punto


def test_transformador_redondo_todos_los_espacios_macos():
    pantalla = _display_macos()  # 1440x900 puntos, 2880x1800 pixeles, escala 2
    ventana = _window(display_id="CGDisplay-1", coordinate_space=DESKTOP_POINTS,
                      bounds=Rect(100.0, 100.0, 900.0, 700.0),
                      client_bounds=Rect(110.0, 110.0, 890.0, 690.0))
    contexto = TransformContext(platform=PLATFORM_MACOS, display=pantalla, window=ventana)
    transformer = CoordinateTransformer(contexto)
    punto = SpacePoint(720.0, 450.0, CoordinateSpace.DESKTOP_POINTS)

    en_pixeles_monitor = transformer.transform_point(punto, CoordinateSpace.MONITOR_PIXELS)
    assert en_pixeles_monitor.space is CoordinateSpace.MONITOR_PIXELS
    assert en_pixeles_monitor.x == 1440.0 and en_pixeles_monitor.y == 900.0  # * escala 2
    assert transformer.transform_point(en_pixeles_monitor, CoordinateSpace.DESKTOP_POINTS) == punto

    en_ventana = transformer.transform_point(punto, CoordinateSpace.WINDOW_RECT)
    assert en_ventana.x == 620.0 and en_ventana.y == 350.0
    assert transformer.transform_point(en_ventana, CoordinateSpace.DESKTOP_POINTS) == punto

    en_cliente = transformer.transform_point(punto, CoordinateSpace.WINDOW_CLIENT)
    assert en_cliente.x == 610.0 and en_cliente.y == 340.0
    assert transformer.transform_point(en_cliente, CoordinateSpace.DESKTOP_POINTS) == punto


def test_transformador_rechaza_espacio_de_escritorio_ajeno_al_sistema():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    transformer = CoordinateTransformer(contexto)
    punto = SpacePoint(100.0, 100.0, CoordinateSpace.DESKTOP_POINTS)
    with pytest.raises(CoordinateTransformError):
        transformer.transform_point(punto, CoordinateSpace.WINDOW_RECT)
    with pytest.raises(CoordinateTransformError):
        transformer.transform_point(SpacePoint(100.0, 100.0, CoordinateSpace.DESKTOP_PIXELS), CoordinateSpace.DESKTOP_POINTS)


def test_transformador_redondo_caja_entre_espacios():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    transformer = CoordinateTransformer(contexto)
    caja = SpaceBox(100.0, 100.0, 900.0, 700.0, CoordinateSpace.DESKTOP_PIXELS)
    en_cliente = transformer.transform_box(caja, CoordinateSpace.WINDOW_CLIENT)
    assert en_cliente.space is CoordinateSpace.WINDOW_CLIENT
    # la caja exterior de la ventana queda desplazada por el borde de la zona cliente (110,110)
    assert en_cliente.left == -10.0 and en_cliente.top == -10.0
    assert en_cliente.right == 790.0 and en_cliente.bottom == 590.0
    assert transformer.transform_box(en_cliente, CoordinateSpace.DESKTOP_PIXELS) == caja
    with pytest.raises(CoordinateTransformError):
        transformer.transform_box(SpaceBox(0.0, 0.0, 0.0, 0.0, CoordinateSpace.WINDOW_CLIENT), CoordinateSpace.DESKTOP_PIXELS)


# ---------------------------------------------------------------------------
# Punto de entrada con redondeo explicito
# ---------------------------------------------------------------------------

def test_to_input_point_redondea_windows_a_enteros_y_macos_a_pixels_fisicos():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    transformer = CoordinateTransformer(contexto)
    punto = SpacePoint(500.4, 400.6, CoordinateSpace.DESKTOP_PIXELS)
    entrada = transformer.to_input_point(punto)
    assert entrada.space is CoordinateSpace.DESKTOP_PIXELS
    assert entrada.x == 500.0 and entrada.y == 401.0  # floor(v + 0.5)

    pantalla_m = _display_macos()  # escala 2
    ventana_m = _window(display_id="CGDisplay-1", coordinate_space=DESKTOP_POINTS,
                        bounds=Rect(100.0, 100.0, 900.0, 700.0),
                        client_bounds=Rect(110.0, 110.0, 890.0, 690.0))
    contexto_m = TransformContext(platform=PLATFORM_MACOS, display=pantalla_m, window=ventana_m)
    transformer_m = CoordinateTransformer(contexto_m)
    punto_m = SpacePoint(720.25, 450.75, CoordinateSpace.DESKTOP_POINTS)
    entrada_m = transformer_m.to_input_point(punto_m)
    # floor(720.25*2+0.5)/2 = floor(1441.0)/2 = 720.5 ; floor(450.75*2+0.5)/2 = floor(902.0)/2 = 451.0
    assert entrada_m.x == 720.5 and entrada_m.y == 451.0


# ---------------------------------------------------------------------------
# build_transform_context asigna monitor y falla sin cobertura
# ---------------------------------------------------------------------------

def test_build_transform_context_asigna_monitor_de_ventana_y_falla_sin_cobertura():
    pantalla = _display_windows()
    ventana = _window(display_id=r"\\.\DISPLAY1")
    contexto = build_transform_context(ventana, [pantalla], PLATFORM_WINDOWS)
    assert contexto.display.display_id == pantalla.display_id
    assert contexto.window is ventana

    ventana_huerfana = WindowInfo(
        window_id=9999, pid=9999, title="Huerfana", app_identity="app.orfan",
        bounds=Rect(9000.0, 9000.0, 9100.0, 9100.0),
        client_bounds=Rect(9000.0, 9000.0, 9100.0, 9100.0),
        frame_bounds=Rect(9000.0, 9000.0, 9100.0, 9100.0),
        is_visible=True, is_minimized=False, is_maximized=False, is_foreground=False,
        display_id="NOEXISTE", scale_factor=1.0, dpi=96, dpi_awareness="per_monitor",
        coordinate_space=DESKTOP_PIXELS,
    )
    with pytest.raises(CoordinateTransformError):
        build_transform_context(ventana_huerfana, [pantalla], PLATFORM_WINDOWS)


# ---------------------------------------------------------------------------
# monitor_pixel_ratio a partir de datos reales
# ---------------------------------------------------------------------------

def test_monitor_pixel_ratio_windows_y_macos():
    assert monitor_pixel_ratio(_display_windows(scale=1.0), PLATFORM_WINDOWS) == (1.0, 1.0)
    assert monitor_pixel_ratio(_display_windows(scale=1.25, pixel_width=2400, pixel_height=1350),
                               PLATFORM_WINDOWS) == (1.25, 1.25)
    assert monitor_pixel_ratio(_display_macos(scale=2.0), PLATFORM_MACOS) == (2.0, 2.0)
    with pytest.raises(CoordinateTransformError):
        monitor_pixel_ratio(_display_macos(scale=0.0), PLATFORM_MACOS)
    pantalla_sin_bounds = _display_windows()
    pantalla_sin_bounds.bounds = None
    with pytest.raises(CoordinateTransformError):
        monitor_pixel_ratio(pantalla_sin_bounds, PLATFORM_WINDOWS)


# ---------------------------------------------------------------------------
# capture_pixels_per_unit verifica el frame contra la region
# ---------------------------------------------------------------------------

def test_capture_pixels_per_unit_valida_frame_contra_region():
    captura = _capture(region=Rect(0.0, 0.0, 1920.0, 1080.0),
                       pixel_width=1920, pixel_height=1080, ppu_x=1.0, ppu_y=1.0)
    assert capture_pixels_per_unit(captura) == (1.0, 1.0)
    captura_mal = _capture(region=Rect(0.0, 0.0, 1920.0, 1080.0),
                           pixel_width=100, pixel_height=100, ppu_x=1.0, ppu_y=1.0)
    with pytest.raises(CoordinateTransformError):
        capture_pixels_per_unit(captura_mal)
    captura_sin_ppu = _capture(ppu_x=0.0, ppu_y=1.0)
    with pytest.raises(CoordinateTransformError):
        capture_pixels_per_unit(captura_sin_ppu)
    captura_sin_region = CaptureResult(
        region=None, pixel_width=1920, pixel_height=1080, backend="mss",
        pixels_per_unit_x=1.0, pixels_per_unit_y=1.0, coordinate_space=DESKTOP_PIXELS,
    )
    with pytest.raises(CoordinateTransformError):
        capture_pixels_per_unit(captura_sin_region)


# ---------------------------------------------------------------------------
# Caja normalizada 0..1000 (Qwen3-VL) -> FRAME_PIXELS
# ---------------------------------------------------------------------------

def test_normalized_1000_box_to_frame_convierte_y_valida_rango():
    caja = normalized_1000_box_to_frame([100, 200, 500, 700], 1920, 1080)
    assert caja.space is CoordinateSpace.FRAME_PIXELS
    assert caja.left == 192.0 and caja.top == 216.0
    assert caja.right == 960.0 and caja.bottom == 756.0
    assert caja.is_valid()
    with pytest.raises(CoordinateTransformError):
        normalized_1000_box_to_frame([-10, 200, 500, 700], 1920, 1080)
    with pytest.raises(CoordinateTransformError):
        normalized_1000_box_to_frame([100, 1100, 500, 700], 1920, 1080)
    with pytest.raises(CoordinateTransformError):
        normalized_1000_box_to_frame([100, 200, 100, 700], 1920, 1080)  # degenerada
    with pytest.raises(CoordinateTransformError):
        normalized_1000_box_to_frame([100, 200, 500], 1920, 1080)  # pocos valores
    with pytest.raises(CoordinateTransformError):
        normalized_1000_box_to_frame([100, 200, 500, 700], 0, 1080)  # frame invalido


# ---------------------------------------------------------------------------
# Conversion Cocoa <-> Quartz y puntos <-> pixeles de macOS
# ---------------------------------------------------------------------------

def test_conversion_cocoa_quartz_macos_es_redondo_y_depende_de_alto_principal():
    rect_cocoa = Rect(100.0, 200.0, 300.0, 400.0)
    cuarzo = cocoa_to_quartz_rect(rect_cocoa, 900.0)
    assert cuarzo.top == 900.0 - 400.0  # primary_height - rect.bottom
    assert cuarzo.bottom == 900.0 - 200.0  # primary_height - rect.top
    assert cuarzo.left == 100.0 and cuarzo.right == 300.0
    assert quartz_to_cocoa_rect(cuarzo, 900.0) == rect_cocoa
    punto_cuarzo = cocoa_to_quartz_point(10.0, 20.0, 900.0)
    assert punto_cuarzo == (10.0, 880.0)
    assert quartz_to_cocoa_point(10.0, 880.0, 900.0) == (10.0, 20.0)
    with pytest.raises(CoordinateTransformError):
        cocoa_to_quartz_rect(rect_cocoa, 0.0)
    with pytest.raises(CoordinateTransformError):
        cocoa_to_quartz_point(10.0, 20.0, -5.0)


def test_puntos_a_pixeles_y_a_puntos_respetan_escala():
    assert points_to_pixels(100.0, 2.0) == 200.0
    assert pixels_to_points(200.0, 2.0) == 100.0
    assert points_to_pixels(100.0, 1.0) == 100.0
    with pytest.raises(CoordinateTransformError):
        points_to_pixels(100.0, 0.0)
    with pytest.raises(CoordinateTransformError):
        pixels_to_points(100.0, -1.0)


# ---------------------------------------------------------------------------
# Rectangulo visible de ventana
# ---------------------------------------------------------------------------

def test_visible_window_rect_prefiere_frame_bounds_y_casca_bounds():
    ventana_con_frame = _window(frame_bounds=Rect(98.0, 98.0, 902.0, 702.0))
    assert visible_window_rect(ventana_con_frame) == Rect(98.0, 98.0, 902.0, 702.0)
    ventana_sin_frame = WindowInfo(
        window_id=1002, pid=1234, title="Sin frame", app_identity="app.test",
        bounds=Rect(100.0, 100.0, 900.0, 700.0),
        client_bounds=Rect(110.0, 110.0, 890.0, 690.0),
        frame_bounds=None,
        is_visible=True, is_minimized=False, is_maximized=False, is_foreground=True,
        display_id=r"\\.\DISPLAY1", scale_factor=1.0, dpi=96, dpi_awareness="per_monitor",
        coordinate_space=DESKTOP_PIXELS,
    )
    assert visible_window_rect(ventana_sin_frame) == Rect(100.0, 100.0, 900.0, 700.0)
    assert visible_window_rect(None) is None


# ---------------------------------------------------------------------------
# Punto seguro dentro de un control
# ---------------------------------------------------------------------------

def test_compute_safe_point_devuelve_centro_cuando_esta_libre():
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    punto = compute_safe_point(caja)
    assert punto is not None
    assert punto.space is CoordinateSpace.WINDOW_CLIENT
    assert caja.contains(punto)
    assert punto.x == 50.0 and punto.y == 50.0


def test_compute_safe_point_devuelve_punto_de_accesibilidad_si_es_valido():
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    acc = SpacePoint(10.0, 10.0, CoordinateSpace.WINDOW_CLIENT)
    punto = compute_safe_point(caja, accessibility_point=acc)
    assert punto == acc


def test_compute_safe_point_caja_degenerada_devuelve_none():
    assert compute_safe_point(SpaceBox(0.0, 0.0, 0.0, 0.0, CoordinateSpace.WINDOW_CLIENT)) is None
    assert compute_safe_point(None) is None


def test_compute_safe_point_vecino_bloquea_busca_alternativa_libre():
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    vecino = SpaceBox(40.0, 40.0, 60.0, 60.0, CoordinateSpace.WINDOW_CLIENT)  # tapa el centro
    punto = compute_safe_point(caja, neighbors=(vecino,), grid_steps=9)
    assert punto is not None
    assert caja.contains(punto)
    assert not vecino.contains(punto)


def test_compute_safe_point_todo_tapado_devuelve_none():
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    # dos vecinos que cubren juntos toda la zona utilizable (sin contener la caja entera)
    vecino_arriba = SpaceBox(25.0, 25.0, 75.0, 50.0, CoordinateSpace.WINDOW_CLIENT)
    vecino_abajo = SpaceBox(25.0, 50.0, 75.0, 75.0, CoordinateSpace.WINDOW_CLIENT)
    assert compute_safe_point(caja, neighbors=(vecino_arriba, vecino_abajo), grid_steps=9) is None


def test_compute_safe_point_rechaza_vecino_en_otro_espacio():
    caja = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    vecino = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.DESKTOP_PIXELS)
    with pytest.raises(CoordinateTransformError):
        compute_safe_point(caja, neighbors=(vecino,))


# ---------------------------------------------------------------------------
# Prohibicion de mezclar espacios sin transformacion explicita
# ---------------------------------------------------------------------------

def test_no_se_mezclan_espacios_sin_transformacion_explicita():
    pantalla = _display_windows()
    ventana = _window()
    contexto = TransformContext(platform=PLATFORM_WINDOWS, display=pantalla, window=ventana)
    transformer = CoordinateTransformer(contexto)
    punto_frame = SpacePoint(100.0, 100.0, CoordinateSpace.FRAME_PIXELS)
    # sin captura, FRAME_PIXELS no es transformable a escritorio
    with pytest.raises(CoordinateTransformError):
        transformer.transform_point(punto_frame, CoordinateSpace.DESKTOP_PIXELS)
    caja_a = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.WINDOW_CLIENT)
    caja_b = SpaceBox(0.0, 0.0, 100.0, 100.0, CoordinateSpace.DESKTOP_PIXELS)
    with pytest.raises(CoordinateTransformError):
        caja_a.contains(SpacePoint(50.0, 50.0, CoordinateSpace.DESKTOP_PIXELS))
