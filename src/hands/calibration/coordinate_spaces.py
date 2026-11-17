"""
Espacios de coordenadas, transformaciones, punto seguro y verificacion del puntero.

Toda coordenada lleva su espacio declarado; esta prohibido mezclar espacios sin
una transformacion explicita. Espacios:

* ``FRAME_PIXELS``: pixeles de una captura (origen arriba-izquierda de la
  imagen). Requiere el ``CaptureResult`` que la produjo (region capturada en
  el escritorio y pixeles por unidad).
* ``MONITOR_PIXELS``: pixeles fisicos relativos al origen del monitor. En
  Windows (escritorio en pixeles, proceso Per-Monitor DPI aware) la relacion
  pixeles/escritorio sale de ``pixel_width / bounds.width`` del monitor
  (normalmente 1). En macOS son pixeles de respaldo (``backingScaleFactor``),
  los mismos que devuelve una captura Retina.
* ``DESKTOP_PIXELS``: escritorio virtual de Windows (origen en el monitor
  principal; puede haber coordenadas negativas).
* ``DESKTOP_POINTS``: escritorio global de macOS en puntos de Quartz (origen
  arriba-izquierda del monitor principal, y hacia abajo).
* ``WINDOW_RECT``: relativo a la esquina del rectangulo exterior de la
  ventana (``WindowInfo.bounds``), en unidades de escritorio.
* ``WINDOW_CLIENT``: relativo al origen del area cliente
  (``WindowInfo.client_bounds``), en unidades de escritorio.
* ``CLIENT_NORMALIZED``: 0..1 relativo al ancho/alto del area cliente.

Solo el espacio de escritorio del SO actual es valido en cada contexto
(Windows: ``DESKTOP_PIXELS``; macOS: ``DESKTOP_POINTS``). Las escalas se
obtienen exclusivamente de ``CaptureResult.pixels_per_unit_*`` (comprobadas
contra las dimensiones del frame) y de ``DisplayInfo``; nunca se multiplica a
ciegas por un factor de escala. Si falta un dato necesario se levanta
``CoordinateTransformError``.

Tambien contiene:

* Conversion Cocoa (origen abajo-izquierda) <-> Quartz (origen arriba-izquierda)
  y puntos <-> pixeles para macOS.
* ``compute_safe_point``: punto seguro dentro de un control (preferir el punto
  de accesibilidad; si no, centro de la zona util evitando bordes y vecinos).
* ``PointerVerifier``: mueve el puntero, lee su posicion REAL, comprueba la
  ventana raiz y el elemento bajo el puntero y aborta si el error supera la
  tolerancia. Nunca hace click.

Cubre las unidades 3.8.6.7.1, 3.8.6.7.4, 3.8.6.7.5 y 3.8.6.7.6 del roadmap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DESKTOP_POINTS,
    PLATFORM_MACOS,
    PLATFORM_WINDOWS,
    CaptureResult,
    DesktopPlatformAdapter,
    DisplayInfo,
    Rect,
    WindowInfo,
    get_desktop_platform,
)

logger = get_logger(__name__)

# Tolerancia (pixeles de frame) entre ``pixel_width`` y
# ``region.width * pixels_per_unit_x`` para aceptar una captura como
# transformacion verificable (absorbe redondeos de un pixel por lado).
_FRAME_SIZE_TOLERANCE_PX = 2.0
_FRAME_SIZE_TOLERANCE_RATIO = 0.01


class CoordinateSpace(str, Enum):
    """Espacios de coordenadas formales."""

    FRAME_PIXELS = "FRAME_PIXELS"
    MONITOR_PIXELS = "MONITOR_PIXELS"
    DESKTOP_PIXELS = "DESKTOP_PIXELS"
    DESKTOP_POINTS = "DESKTOP_POINTS"
    WINDOW_RECT = "WINDOW_RECT"
    WINDOW_CLIENT = "WINDOW_CLIENT"
    CLIENT_NORMALIZED = "CLIENT_NORMALIZED"

    @classmethod
    def from_value(cls, value: Any) -> "CoordinateSpace":
        """Acepta el enum, su valor o los nombres heredados del validador.

        Equivalencias heredadas (``RECOGNIZED_COORDINATE_SPACES`` de
        ``window_evidence_validator``): ``image_pixels`` -> FRAME_PIXELS,
        ``monitor_relative`` -> MONITOR_PIXELS, ``window_relative`` ->
        WINDOW_RECT. ``absolute_desktop`` depende del SO y se resuelve con
        ``desktop_space_for_platform``. ``normalized_0_1000`` no es un espacio
        de este modulo: usar ``normalized_1000_box_to_frame``.
        """
        if isinstance(value, CoordinateSpace):
            return value
        text = str(value or "").strip()
        legacy = {
            "image_pixels": cls.FRAME_PIXELS,
            "monitor_relative": cls.MONITOR_PIXELS,
            "window_relative": cls.WINDOW_RECT,
        }
        if text in legacy:
            return legacy[text]
        try:
            return cls(text.upper())
        except ValueError:
            raise CoordinateTransformError("espacio de coordenadas desconocido: %r" % value)


class CoordinateTransformError(ValueError):
    """Transformacion imposible o no verificable con la informacion disponible."""


DESKTOP_SPACES = (CoordinateSpace.DESKTOP_PIXELS, CoordinateSpace.DESKTOP_POINTS)


def desktop_space_for_platform(platform: str) -> CoordinateSpace:
    """Espacio de escritorio nativo del SO (``windows``/``macos``)."""
    if platform == PLATFORM_WINDOWS:
        return CoordinateSpace.DESKTOP_PIXELS
    if platform == PLATFORM_MACOS:
        return CoordinateSpace.DESKTOP_POINTS
    raise CoordinateTransformError("plataforma sin espacio de escritorio definido: %r" % platform)


# ============================================================================
# PUNTOS Y CAJAS CON ESPACIO
# ============================================================================


@dataclass(frozen=True)
class SpacePoint:
    """Punto con su espacio de coordenadas."""

    x: float
    y: float
    space: CoordinateSpace

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "space": self.space.value}


@dataclass(frozen=True)
class SpaceBox:
    """Caja (left, top, right, bottom) con su espacio de coordenadas."""

    left: float
    top: float
    right: float
    bottom: float
    space: CoordinateSpace

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def is_valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def center(self) -> SpacePoint:
        return SpacePoint(
            self.left + self.width / 2.0,
            self.top + self.height / 2.0,
            self.space,
        )

    def contains(self, point: SpacePoint) -> bool:
        if point.space != self.space:
            raise CoordinateTransformError(
                "punto en %s y caja en %s: transformar antes de comparar"
                % (point.space.value, self.space.value)
            )
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom

    def to_rect(self) -> Rect:
        return Rect(self.left, self.top, self.right, self.bottom)

    @classmethod
    def from_rect(cls, rect: Rect, space: CoordinateSpace) -> "SpaceBox":
        return cls(rect.left, rect.top, rect.right, rect.bottom, CoordinateSpace.from_value(space))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "space": self.space.value,
        }


# ============================================================================
# CONTEXTO Y TRANSFORMADOR
# ============================================================================


@dataclass
class TransformContext:
    """Datos geometricos necesarios para transformar entre espacios.

    ``display`` es el monitor de referencia para ``MONITOR_PIXELS`` (el de la
    ventana o el capturado). ``window`` hace falta para ``WINDOW_*`` y
    ``CLIENT_NORMALIZED``; ``capture`` para ``FRAME_PIXELS``. Todos los
    rectangulos deben estar en el espacio de escritorio del ``platform``.
    """

    platform: str
    display: DisplayInfo
    window: Optional[WindowInfo] = None
    capture: Optional[CaptureResult] = None

    @property
    def desktop_space(self) -> CoordinateSpace:
        return desktop_space_for_platform(self.platform)

    def validate(self) -> None:
        desktop = self.desktop_space.value
        if self.display is None or self.display.bounds is None or not self.display.bounds.is_valid():
            raise CoordinateTransformError("monitor de referencia sin geometria valida")
        if str(self.display.coordinate_space) != desktop:
            raise CoordinateTransformError(
                "el monitor esta en %s y la plataforma usa %s"
                % (self.display.coordinate_space, desktop)
            )
        if self.window is not None and str(self.window.coordinate_space) != desktop:
            raise CoordinateTransformError(
                "la ventana esta en %s y la plataforma usa %s"
                % (self.window.coordinate_space, desktop)
            )
        if self.capture is not None and str(self.capture.coordinate_space) != desktop:
            raise CoordinateTransformError(
                "la captura esta en %s y la plataforma usa %s"
                % (self.capture.coordinate_space, desktop)
            )


def monitor_pixel_ratio(display: DisplayInfo, platform: str) -> Tuple[float, float]:
    """Pixeles de monitor por unidad de escritorio (x, y) a partir de datos reales.

    * Windows: ``pixel_width / bounds.width`` (y analogo en vertical); con el
      proceso Per-Monitor DPI aware vale 1. Si las dimensiones fisicas vienen
      en la orientacion contraria a ``bounds`` (monitor girado) se emparejan
      por orientacion.
    * macOS: ``backingScaleFactor`` del monitor (pixeles de respaldo, los de
      una captura Retina).
    """
    bounds = display.bounds
    if platform == PLATFORM_MACOS:
        scale = float(display.scale_factor or 0.0)
        if scale <= 0:
            raise CoordinateTransformError("monitor %s sin backingScaleFactor valido" % display.display_id)
        return (scale, scale)
    pw = float(display.pixel_width or 0)
    ph = float(display.pixel_height or 0)
    if bounds is None or not bounds.is_valid() or pw <= 0 or ph <= 0:
        raise CoordinateTransformError("monitor %s sin resolucion fisica valida" % display.display_id)
    if (pw > ph) != (bounds.width > bounds.height) and pw != ph and bounds.width != bounds.height:
        pw, ph = ph, pw
    return (pw / bounds.width, ph / bounds.height)


def capture_pixels_per_unit(capture: CaptureResult) -> Tuple[float, float]:
    """Pixeles de frame por unidad de escritorio, VERIFICADOS contra el frame.

    Usa ``pixels_per_unit_x/y`` declarados por el adaptador y comprueba que
    ``pixel_width ~= region.width * ppu_x`` (y en vertical). Si no cuadran, la
    transformacion no es verificable y se rechaza.
    """
    region = capture.region
    if region is None or not region.is_valid():
        raise CoordinateTransformError("captura sin region de escritorio valida")
    ppu_x = float(capture.pixels_per_unit_x or 0.0)
    ppu_y = float(capture.pixels_per_unit_y or 0.0)
    if ppu_x <= 0 or ppu_y <= 0:
        raise CoordinateTransformError("captura sin pixeles por unidad validos")
    pw = float(capture.pixel_width or 0)
    ph = float(capture.pixel_height or 0)
    if pw <= 0 or ph <= 0:
        raise CoordinateTransformError("captura sin dimensiones de frame")
    expected_w = region.width * ppu_x
    expected_h = region.height * ppu_y
    tol_w = max(_FRAME_SIZE_TOLERANCE_PX, _FRAME_SIZE_TOLERANCE_RATIO * pw)
    tol_h = max(_FRAME_SIZE_TOLERANCE_PX, _FRAME_SIZE_TOLERANCE_RATIO * ph)
    if abs(expected_w - pw) > tol_w or abs(expected_h - ph) > tol_h:
        raise CoordinateTransformError(
            "frame %dx%d no cuadra con region %.1fx%.1f y escala %.3f/%.3f: transformacion no verificable"
            % (int(pw), int(ph), region.width, region.height, ppu_x, ppu_y)
        )
    return (ppu_x, ppu_y)


class CoordinateTransformer:
    """Transforma puntos y cajas entre espacios con un ``TransformContext``.

    Todas las transformaciones pasan por el espacio de escritorio nativo del
    SO. Los resultados son flotantes; el redondeo solo se aplica de forma
    explicita al pasar a entrada (``to_input_point``).
    """

    def __init__(self, context: TransformContext) -> None:
        context.validate()
        self.context = context

    # ------------------------------------------------------------------
    # Requisitos
    # ------------------------------------------------------------------

    def _require_window_rect(self) -> Rect:
        window = self.context.window
        if window is None or window.bounds is None or not window.bounds.is_valid():
            raise CoordinateTransformError("falta el rectangulo de la ventana para WINDOW_RECT")
        return window.bounds

    def _require_client_rect(self) -> Rect:
        window = self.context.window
        if window is None or window.client_bounds is None or not window.client_bounds.is_valid():
            raise CoordinateTransformError("falta el area cliente de la ventana")
        return window.client_bounds

    def _require_capture(self) -> Tuple[CaptureResult, float, float]:
        capture = self.context.capture
        if capture is None:
            raise CoordinateTransformError("falta la captura para FRAME_PIXELS")
        ppu_x, ppu_y = capture_pixels_per_unit(capture)
        return capture, ppu_x, ppu_y

    def _check_space(self, space: CoordinateSpace) -> CoordinateSpace:
        space = CoordinateSpace.from_value(space)
        if space in DESKTOP_SPACES and space != self.context.desktop_space:
            raise CoordinateTransformError(
                "%s no es el espacio de escritorio de %s (%s)"
                % (space.value, self.context.platform, self.context.desktop_space.value)
            )
        return space

    # ------------------------------------------------------------------
    # Hacia y desde el escritorio
    # ------------------------------------------------------------------

    def _to_desktop(self, x: float, y: float, space: CoordinateSpace) -> Tuple[float, float]:
        if space == self.context.desktop_space:
            return (x, y)
        if space == CoordinateSpace.FRAME_PIXELS:
            capture, ppu_x, ppu_y = self._require_capture()
            return (capture.region.left + x / ppu_x, capture.region.top + y / ppu_y)
        if space == CoordinateSpace.MONITOR_PIXELS:
            rx, ry = monitor_pixel_ratio(self.context.display, self.context.platform)
            bounds = self.context.display.bounds
            return (bounds.left + x / rx, bounds.top + y / ry)
        if space == CoordinateSpace.WINDOW_RECT:
            rect = self._require_window_rect()
            return (rect.left + x, rect.top + y)
        if space == CoordinateSpace.WINDOW_CLIENT:
            rect = self._require_client_rect()
            return (rect.left + x, rect.top + y)
        if space == CoordinateSpace.CLIENT_NORMALIZED:
            rect = self._require_client_rect()
            return (rect.left + x * rect.width, rect.top + y * rect.height)
        raise CoordinateTransformError("transformacion desde %s no soportada" % space.value)

    def _from_desktop(self, x: float, y: float, space: CoordinateSpace) -> Tuple[float, float]:
        if space == self.context.desktop_space:
            return (x, y)
        if space == CoordinateSpace.FRAME_PIXELS:
            capture, ppu_x, ppu_y = self._require_capture()
            return ((x - capture.region.left) * ppu_x, (y - capture.region.top) * ppu_y)
        if space == CoordinateSpace.MONITOR_PIXELS:
            rx, ry = monitor_pixel_ratio(self.context.display, self.context.platform)
            bounds = self.context.display.bounds
            return ((x - bounds.left) * rx, (y - bounds.top) * ry)
        if space == CoordinateSpace.WINDOW_RECT:
            rect = self._require_window_rect()
            return (x - rect.left, y - rect.top)
        if space == CoordinateSpace.WINDOW_CLIENT:
            rect = self._require_client_rect()
            return (x - rect.left, y - rect.top)
        if space == CoordinateSpace.CLIENT_NORMALIZED:
            rect = self._require_client_rect()
            return ((x - rect.left) / rect.width, (y - rect.top) / rect.height)
        raise CoordinateTransformError("transformacion hacia %s no soportada" % space.value)

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def transform_point(self, point: SpacePoint, target: CoordinateSpace) -> SpacePoint:
        source = self._check_space(point.space)
        target = self._check_space(target)
        if source == target:
            return point
        dx, dy = self._to_desktop(float(point.x), float(point.y), source)
        tx, ty = self._from_desktop(dx, dy, target)
        return SpacePoint(tx, ty, target)

    def transform_box(self, box: SpaceBox, target: CoordinateSpace) -> SpaceBox:
        if not box.is_valid():
            raise CoordinateTransformError("caja vacia o degenerada")
        top_left = self.transform_point(SpacePoint(box.left, box.top, box.space), target)
        bottom_right = self.transform_point(SpacePoint(box.right, box.bottom, box.space), target)
        left, right = sorted((top_left.x, bottom_right.x))
        top, bottom = sorted((top_left.y, bottom_right.y))
        return SpaceBox(left, top, right, bottom, CoordinateSpace.from_value(target))

    @property
    def input_space(self) -> CoordinateSpace:
        """Espacio que consume el puntero del SO (escritorio nativo)."""
        return self.context.desktop_space

    def to_input_point(self, point: SpacePoint) -> SpacePoint:
        """Transforma al espacio del puntero con redondeo EXPLICITO.

        Windows: entero mas cercano en pixeles (mitades hacia arriba).
        macOS: puntos redondeados al pixel fisico mas cercano del monitor de
        referencia (``round(v * escala) / escala``).
        """
        desktop = self.transform_point(point, self.context.desktop_space)
        if self.context.platform == PLATFORM_MACOS:
            scale = float(self.context.display.scale_factor or 1.0)
            if scale <= 0:
                raise CoordinateTransformError("escala de monitor invalida")
            return SpacePoint(
                math.floor(desktop.x * scale + 0.5) / scale,
                math.floor(desktop.y * scale + 0.5) / scale,
                desktop.space,
            )
        return SpacePoint(
            float(math.floor(desktop.x + 0.5)),
            float(math.floor(desktop.y + 0.5)),
            desktop.space,
        )


def build_transform_context(
    window: WindowInfo,
    displays: Sequence[DisplayInfo],
    platform: str,
    capture: Optional[CaptureResult] = None,
) -> TransformContext:
    """Contexto para una ventana: monitor declarado por el SO o el de mayor interseccion."""
    display: Optional[DisplayInfo] = None
    if window.display_id:
        for candidate in displays:
            if str(candidate.display_id) == str(window.display_id):
                display = candidate
                break
    if display is None:
        rect = window.frame_bounds or window.bounds
        best_area = 0.0
        for candidate in displays:
            area = candidate.bounds.intersection_area(rect) if rect else 0.0
            if area > best_area:
                best_area = area
                display = candidate
    if display is None:
        raise CoordinateTransformError("la ventana %s no esta en ningun monitor actual" % window.window_id)
    return TransformContext(platform=platform, display=display, window=window, capture=capture)


def normalized_1000_box_to_frame(values: Sequence[float], frame_width: int, frame_height: int) -> SpaceBox:
    """Caja normalizada 0..1000 (formato de Qwen3-VL) -> ``FRAME_PIXELS``."""
    try:
        x1, y1, x2, y2 = [float(v) for v in values]
    except (TypeError, ValueError):
        raise CoordinateTransformError("caja 0..1000 invalida: %r" % (values,))
    if frame_width <= 0 or frame_height <= 0:
        raise CoordinateTransformError("dimensiones de frame invalidas")
    for v in (x1, y1, x2, y2):
        if v < 0 or v > 1000:
            raise CoordinateTransformError("caja 0..1000 fuera de rango: %r" % (values,))
    box = SpaceBox(
        x1 * frame_width / 1000.0,
        y1 * frame_height / 1000.0,
        x2 * frame_width / 1000.0,
        y2 * frame_height / 1000.0,
        CoordinateSpace.FRAME_PIXELS,
    )
    if not box.is_valid():
        raise CoordinateTransformError("caja 0..1000 degenerada: %r" % (values,))
    return box


# ============================================================================
# UTILIDADES macOS (Cocoa <-> Quartz, puntos <-> pixeles)
# ============================================================================


def cocoa_to_quartz_rect(rect: Rect, primary_height: float) -> Rect:
    """Rect de Cocoa (origen abajo-izquierda del principal, y hacia arriba) a Quartz.

    Convencion del ``Rect`` de entrada en Cocoa: ``top`` = minY (borde
    inferior en pantalla) y ``bottom`` = maxY (borde superior), es decir,
    valores numericos crecientes. ``primary_height`` es el alto en puntos del
    monitor principal (``NSScreen.screens()[0].frame().size.height``).
    """
    if primary_height <= 0:
        raise CoordinateTransformError("alto del monitor principal invalido")
    return Rect(rect.left, primary_height - rect.bottom, rect.right, primary_height - rect.top)


def quartz_to_cocoa_rect(rect: Rect, primary_height: float) -> Rect:
    """Inversa de ``cocoa_to_quartz_rect`` (la formula es simetrica)."""
    return cocoa_to_quartz_rect(rect, primary_height)


def cocoa_to_quartz_point(x: float, y: float, primary_height: float) -> Tuple[float, float]:
    if primary_height <= 0:
        raise CoordinateTransformError("alto del monitor principal invalido")
    return (x, primary_height - y)


def quartz_to_cocoa_point(x: float, y: float, primary_height: float) -> Tuple[float, float]:
    return cocoa_to_quartz_point(x, y, primary_height)


def points_to_pixels(value: float, scale: float) -> float:
    if scale <= 0:
        raise CoordinateTransformError("escala invalida: %r" % scale)
    return float(value) * float(scale)


def pixels_to_points(value: float, scale: float) -> float:
    if scale <= 0:
        raise CoordinateTransformError("escala invalida: %r" % scale)
    return float(value) / float(scale)


def visible_window_rect(window: Optional[WindowInfo]) -> Optional[Rect]:
    """Rectangulo visible de la ventana sin sombra/borde invisible.

    Windows: limites extendidos de DWM (``frame_bounds``) que excluyen el
    borde invisible de redimensionado; macOS: frame AX sin sombra. Si no se
    dispone, ``bounds``. Devuelve ``None`` si no hay ventana.
    """
    if window is None:
        return None
    return window.frame_bounds or window.bounds


# ============================================================================
# PUNTO SEGURO DENTRO DE UN CONTROL
# ============================================================================


def _point_in_box(x: float, y: float, box: SpaceBox) -> bool:
    return box.left <= x <= box.right and box.top <= y <= box.bottom


def _distance_to_box_outside(x: float, y: float, box: SpaceBox) -> float:
    dx = max(box.left - x, 0.0, x - box.right)
    dy = max(box.top - y, 0.0, y - box.bottom)
    return math.hypot(dx, dy)


def compute_safe_point(
    box: SpaceBox,
    accessibility_point: Optional[SpacePoint] = None,
    neighbors: Sequence[SpaceBox] = (),
    margin_ratio: float = 0.25,
    grid_steps: int = 7,
) -> Optional[SpacePoint]:
    """Punto seguro dentro de un control.

    1. Si la accesibilidad da un punto (``ClickablePoint`` de UIA / centro del
       frame AX), se usa si cae dentro de la caja y fuera de controles vecinos.
    2. Si no, se busca en la zona util (caja recortada ``margin_ratio`` del
       ancho/alto por cada lado, sin dejarla vacia) el punto mas alejado de
       los vecinos que se solapan y de los bordes; se prefiere el centro.
    3. ``None`` si la caja es degenerada o toda la zona util esta tapada por
       vecinos.

    Todas las cajas y el punto deben estar en el mismo espacio.
    """
    if box is None or not box.is_valid():
        return None
    for other in neighbors:
        if other.space != box.space:
            raise CoordinateTransformError("vecino en %s y caja en %s" % (other.space.value, box.space.value))
    blockers = [
        n for n in neighbors
        if n.is_valid()
        and not (n.left <= box.left and n.top <= box.top and n.right >= box.right and n.bottom >= box.bottom)
        and n.to_rect().intersection(box.to_rect()) is not None
    ]

    def _free(x: float, y: float) -> bool:
        return not any(_point_in_box(x, y, n) for n in blockers)

    if accessibility_point is not None:
        if accessibility_point.space != box.space:
            raise CoordinateTransformError(
                "punto de accesibilidad en %s y caja en %s"
                % (accessibility_point.space.value, box.space.value)
            )
        if _point_in_box(accessibility_point.x, accessibility_point.y, box) and _free(
            accessibility_point.x, accessibility_point.y
        ):
            return accessibility_point

    ratio = min(max(float(margin_ratio), 0.0), 0.45)
    inner_left = box.left + box.width * ratio
    inner_right = box.right - box.width * ratio
    inner_top = box.top + box.height * ratio
    inner_bottom = box.bottom - box.height * ratio
    if inner_right <= inner_left:
        inner_left = inner_right = box.left + box.width / 2.0
    if inner_bottom <= inner_top:
        inner_top = inner_bottom = box.top + box.height / 2.0

    cx = box.left + box.width / 2.0
    cy = box.top + box.height / 2.0
    if inner_left <= cx <= inner_right and inner_top <= cy <= inner_bottom and _free(cx, cy):
        clearance = min(
            [_distance_to_box_outside(cx, cy, n) for n in blockers] or [float("inf")]
        )
        if not blockers or clearance > 0:
            return SpacePoint(cx, cy, box.space)

    steps = max(2, int(grid_steps))
    best: Optional[Tuple[float, float, float]] = None
    for i in range(steps):
        for j in range(steps):
            x = inner_left + (inner_right - inner_left) * i / (steps - 1)
            y = inner_top + (inner_bottom - inner_top) * j / (steps - 1)
            if not _free(x, y):
                continue
            edge = min(x - box.left, box.right - x, y - box.top, box.bottom - y)
            clearance = min([_distance_to_box_outside(x, y, n) for n in blockers] or [edge])
            score = min(edge, clearance)
            if best is None or score > best[0]:
                best = (score, x, y)
    if best is None:
        return None
    return SpacePoint(best[1], best[2], box.space)


# ============================================================================
# VERIFICACION DEL PUNTERO ANTES DE UN CLICK
# ============================================================================


@dataclass
class PointerVerification:
    """Resultado de mover el puntero y verificar que esta donde debe.

    ``element_ok`` es ``None`` cuando la accesibilidad no permite comprobar el
    elemento bajo el puntero (control solo visual): no bloquea, pero el
    consumidor lo ve. ``ok`` exige tolerancia de posicion, punto dentro de la
    caja esperada (si se da), ventana correcta y ``element_ok`` distinto de
    False. Este verificador NUNCA hace click.
    """

    ok: bool
    requested: Optional[SpacePoint]
    actual: Optional[SpacePoint]
    error_px: Optional[float]
    error_ratio: Optional[float]
    window_ok: bool
    element_ok: Optional[bool]
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "requested": self.requested.to_dict() if self.requested else None,
            "actual": self.actual.to_dict() if self.actual else None,
            "error_px": self.error_px,
            "error_ratio": self.error_ratio,
            "window_ok": self.window_ok,
            "element_ok": self.element_ok,
            "reason": self.reason,
            "details": dict(self.details),
        }


class PointerVerifier:
    """Mueve el puntero (posicionamiento absoluto) y verifica la posicion real.

    El DPI/CPI del raton y la aceleracion no son factores de escala de
    pantalla: se usa posicionamiento absoluto del contrato y se lee la
    posicion real despues de mover.

    Tolerancia: si se da ``expected_box``, el error debe ser <=
    ``tolerance_ratio`` x lado menor de la caja; si se da ``tolerance_px``,
    ademas <= ``tolerance_px`` (unidades de escritorio x ``pixels_per_unit``
    del monitor). Sin caja ni ``tolerance_px`` se exige
    ``default_tolerance_units`` (absorbe el redondeo a pixel entero).
    Los valores deben fijarse con mediciones reales (fixture).
    """

    def __init__(
        self,
        adapter: Optional[DesktopPlatformAdapter] = None,
        tolerance_px: Optional[float] = None,
        tolerance_ratio: float = 0.15,
        default_tolerance_units: float = 1.5,
        require_foreground: bool = True,
    ) -> None:
        self._adapter = adapter
        self.tolerance_px = tolerance_px
        self.tolerance_ratio = float(tolerance_ratio)
        self.default_tolerance_units = float(default_tolerance_units)
        self.require_foreground = bool(require_foreground)

    @property
    def adapter(self) -> DesktopPlatformAdapter:
        if self._adapter is None:
            self._adapter = get_desktop_platform()
        return self._adapter

    def _fail(
        self,
        reason: str,
        requested: Optional[SpacePoint],
        actual: Optional[SpacePoint] = None,
        error_px: Optional[float] = None,
        error_ratio: Optional[float] = None,
        window_ok: bool = False,
        element_ok: Optional[bool] = None,
        **details: Any,
    ) -> PointerVerification:
        logger.warning("Verificacion de puntero abortada: %s", reason)
        return PointerVerification(False, requested, actual, error_px, error_ratio, window_ok, element_ok, reason, dict(details))

    def move_and_verify(
        self,
        target: SpacePoint,
        expected_window_id: int,
        expected_pid: Optional[int] = None,
        expected_box: Optional[SpaceBox] = None,
        pixels_per_unit: float = 1.0,
    ) -> PointerVerification:
        adapter = self.adapter
        desktop_value = getattr(adapter, "desktop_space", DESKTOP_PIXELS)
        try:
            desktop_space = CoordinateSpace.from_value(desktop_value)
        except CoordinateTransformError:
            return self._fail("el adaptador declara un espacio de escritorio desconocido", target)
        if target.space != desktop_space:
            return self._fail(
                "el destino esta en %s y el puntero usa %s (usar to_input_point)"
                % (target.space.value, desktop_space.value),
                target,
            )
        if expected_box is not None and expected_box.space != desktop_space:
            return self._fail("la caja esperada no esta en el espacio del escritorio", target)
        if expected_box is not None and not expected_box.contains(target):
            return self._fail("el destino no esta dentro de la caja del control", target)

        if self.require_foreground and not adapter.is_foreground(int(expected_window_id)):
            return self._fail("la ventana objetivo no esta en primer plano", target)

        moved = adapter.move_pointer(target.x, target.y)
        if not moved.ok:
            return self._fail("no se pudo mover el puntero: %s" % moved.error, target)

        position = adapter.get_pointer_position()
        if not position.ok or position.value is None:
            return self._fail("no se pudo leer la posicion real del puntero: %s" % position.error, target)
        pos = position.value
        if str(pos.coordinate_space) != desktop_space.value:
            return self._fail("posicion leida en un espacio inesperado: %s" % pos.coordinate_space, target)
        actual = SpacePoint(float(pos.x), float(pos.y), desktop_space)

        error_units = math.hypot(actual.x - target.x, actual.y - target.y)
        error_px = error_units * float(pixels_per_unit or 1.0)
        error_ratio: Optional[float] = None
        limits: List[str] = []
        within = True
        if expected_box is not None:
            side = min(expected_box.width, expected_box.height)
            error_ratio = error_units / side if side > 0 else None
            if error_ratio is None or error_ratio > self.tolerance_ratio:
                within = False
                limits.append("error relativo %.3f > %.3f" % (error_ratio or -1.0, self.tolerance_ratio))
            if not expected_box.contains(actual):
                within = False
                limits.append("el puntero quedo fuera de la caja del control")
        if self.tolerance_px is not None and error_px > float(self.tolerance_px):
            within = False
            limits.append("error %.2f px > %.2f px" % (error_px, float(self.tolerance_px)))
        if expected_box is None and self.tolerance_px is None and error_units > self.default_tolerance_units:
            within = False
            limits.append("error %.2f > %.2f unidades" % (error_units, self.default_tolerance_units))
        if not within:
            return self._fail("; ".join(limits), target, actual, error_px, error_ratio)

        under = adapter.window_at_point(actual.x, actual.y)
        if not under.ok:
            return self._fail(
                "no se puede verificar la ventana bajo el puntero: %s" % under.error,
                target, actual, error_px, error_ratio,
            )
        window = under.value
        window_ok = window is not None and int(window.window_id) == int(expected_window_id)
        if window_ok and expected_pid is not None:
            window_ok = int(window.pid) == int(expected_pid)  # type: ignore[union-attr]
        if not window_ok:
            return self._fail(
                "la ventana bajo el puntero no es la objetivo",
                target, actual, error_px, error_ratio, False, None,
                window_under_pointer=window.window_id if window is not None else None,
            )

        element_ok: Optional[bool] = None
        element_detail: Dict[str, Any] = {}
        if expected_box is not None:
            element = adapter.element_at_point(actual.x, actual.y)
            if element.ok and element.value is not None:
                node_box = getattr(element.value, "bbox", None)
                if isinstance(node_box, Rect) and node_box.is_valid():
                    expected_rect = expected_box.to_rect()
                    inter = node_box.intersection_area(expected_rect)
                    smaller = min(node_box.area, expected_rect.area)
                    element_ok = bool(smaller > 0 and inter / smaller >= 0.5)
                    element_detail = {
                        "element_box": node_box.to_dict(),
                        "element_role": getattr(element.value, "native_role", ""),
                    }
            else:
                element_detail = {"element_check": "no_verificable"}
        if element_ok is False:
            return self._fail(
                "el elemento bajo el puntero no coincide con el control esperado",
                target, actual, error_px, error_ratio, True, False, **element_detail,
            )
        return PointerVerification(
            True, target, actual, error_px, error_ratio, True, element_ok,
            "puntero verificado sobre la ventana y el control esperados", element_detail,
        )


__all__ = [
    "CoordinateSpace",
    "CoordinateTransformError",
    "DESKTOP_SPACES",
    "desktop_space_for_platform",
    "SpacePoint",
    "SpaceBox",
    "TransformContext",
    "CoordinateTransformer",
    "monitor_pixel_ratio",
    "capture_pixels_per_unit",
    "build_transform_context",
    "normalized_1000_box_to_frame",
    "cocoa_to_quartz_rect",
    "quartz_to_cocoa_rect",
    "cocoa_to_quartz_point",
    "quartz_to_cocoa_point",
    "points_to_pixels",
    "pixels_to_points",
    "visible_window_rect",
    "compute_safe_point",
    "PointerVerification",
    "PointerVerifier",
]
