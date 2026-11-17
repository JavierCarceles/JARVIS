"""
Contrato comun de plataforma de escritorio (Windows y macOS).

Define un unico contrato para todo lo que toca el SO en el escritorio:
monitores, ventanas, captura, puntero/teclado, arbol de accesibilidad,
permisos y comprobaciones de entorno antes de interactuar. Brain, Planner,
Executor, calibracion y vision consumen este contrato; nunca APIs nativas.

Hay dos adaptadores:

* ``src.desktop.platform_windows.WindowsDesktopAdapter`` (Win32, UI Automation,
  mss/DXcam, SendInput).
* ``src.desktop.platform_macos.MacOSDesktopAdapter`` (NSScreen/CGDisplay,
  CGWindowList, AXUIElement, CGEvent, ScreenCaptureKit/CGWindowList/mss).

El adaptador se elige en tiempo de ejecucion por el SO detectado con
``get_desktop_platform()``. Si no hay adaptador para el SO, se levanta
``PlatformNotSupportedError``; nunca se sustituye por un adaptador de otro SO.

Reglas del contrato:

* Toda operacion devuelve ``PlatformResult``: ``ok`` + ``value`` o un
  ``PlatformError`` normalizado (codigo estable, operacion, mensaje,
  instrucciones para el usuario cuando falta un permiso). No se lanzan
  excepciones nativas hacia los consumidores.
* Cada capacidad del adaptador se declara por separado (``Capability``) con
  estado ``DISPONIBLE``, ``SIN_PERMISO``, ``NO_SOPORTADO`` o ``NO_VERIFICADO``.
  Que una aplicacion se pueda lanzar no implica que sea automatizable.
* Geometria: los rectangulos de monitores y ventanas se expresan en el espacio
  de escritorio nativo del SO. En Windows es ``DESKTOP_PIXELS`` (pixeles del
  escritorio virtual con proceso Per-Monitor DPI aware); en macOS es
  ``DESKTOP_POINTS`` (puntos globales de Quartz, origen arriba-izquierda del
  monitor principal). El espacio va siempre declarado en los datos.
* El contrato no decide politica (que monitor elegir, que se puede pulsar):
  eso vive en ``src.desktop.monitor_topology`` y en las puertas de calidad.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Sequence, Tuple, TypeVar

from src.core.log import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Espacios de escritorio nativos por SO (ver src.hands.calibration.coordinate_spaces).
DESKTOP_PIXELS = "DESKTOP_PIXELS"
DESKTOP_POINTS = "DESKTOP_POINTS"

PLATFORM_WINDOWS = "windows"
PLATFORM_MACOS = "macos"


# ============================================================================
# CAPACIDADES Y PERMISOS
# ============================================================================


class Capability(str, Enum):
    """Capacidades declaradas por separado por cada adaptador."""

    DISCOVER = "discover"
    RESOLVE = "resolve"
    PREFLIGHT = "preflight"
    LAUNCH = "launch"
    PROCESS_VERIFY = "process_verify"
    WINDOW_VERIFY = "window_verify"
    WINDOW_CONTROL = "window_control"
    DISPLAY_ENUM = "display_enum"
    SCREEN_CAPTURE = "screen_capture"
    INPUT_CONTROL = "input_control"
    ACCESSIBILITY_TREE = "accessibility_tree"
    AUDIO_INPUT = "audio_input"


class CapabilityStatus(str, Enum):
    """Estado de una capacidad en el equipo actual."""

    DISPONIBLE = "DISPONIBLE"
    SIN_PERMISO = "SIN_PERMISO"
    NO_SOPORTADO = "NO_SOPORTADO"
    NO_VERIFICADO = "NO_VERIFICADO"


@dataclass
class CapabilityReport:
    """Estado declarado de una capacidad, con detalle e instrucciones."""

    capability: Capability
    status: CapabilityStatus
    detail: str = ""
    instructions: str = ""
    backend: str = ""

    @property
    def available(self) -> bool:
        return self.status == CapabilityStatus.DISPONIBLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.value,
            "status": self.status.value,
            "detail": self.detail,
            "instructions": self.instructions,
            "backend": self.backend,
        }


class PermissionKind(str, Enum):
    """Permisos de SO que condicionan capacidades."""

    ACCESSIBILITY = "accessibility"
    SCREEN_RECORDING = "screen_recording"
    MICROPHONE = "microphone"
    AUTOMATION = "automation"
    INPUT_INJECTION = "input_injection"
    ELEVATION = "elevation"


@dataclass
class PermissionStatus:
    """Estado de un permiso del SO para el proceso anfitrion de JARVIS."""

    kind: PermissionKind
    status: CapabilityStatus
    detail: str = ""
    instructions: str = ""

    @property
    def granted(self) -> bool:
        return self.status == CapabilityStatus.DISPONIBLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "detail": self.detail,
            "instructions": self.instructions,
        }


# ============================================================================
# ERRORES Y RESULTADOS NORMALIZADOS
# ============================================================================


class PlatformErrorCode(str, Enum):
    """Codigos estables de error del contrato de plataforma."""

    NOT_SUPPORTED = "not_supported"
    PERMISSION_DENIED = "permission_denied"
    DEPENDENCY_MISSING = "dependency_missing"
    NOT_FOUND = "not_found"
    WINDOW_GONE = "window_gone"
    INVALID_ARGUMENT = "invalid_argument"
    TIMEOUT = "timeout"
    PROTECTED = "protected"
    SESSION_LOCKED = "session_locked"
    VERIFICATION_FAILED = "verification_failed"
    NATIVE_ERROR = "native_error"


@dataclass
class PlatformError:
    """Error normalizado de una operacion del contrato."""

    code: PlatformErrorCode
    message: str
    operation: str = ""
    platform: str = ""
    native_error: str = ""
    instructions: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "operation": self.operation,
            "platform": self.platform,
            "native_error": self.native_error,
            "instructions": self.instructions,
            "details": dict(self.details),
        }

    def __str__(self) -> str:
        return "%s[%s]: %s" % (self.operation or "operacion", self.code.value, self.message)


class PlatformOperationError(Exception):
    """Excepcion que transporta un ``PlatformError`` (uso interno/opcional)."""

    def __init__(self, error: PlatformError) -> None:
        super().__init__(str(error))
        self.error = error


class PlatformNotSupportedError(RuntimeError):
    """No existe adaptador de escritorio para el SO actual."""


@dataclass
class PlatformResult(Generic[T]):
    """Resultado normalizado: ``ok`` con ``value`` o ``error``."""

    ok: bool
    value: Optional[T] = None
    error: Optional[PlatformError] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, value: Optional[T] = None, **details: Any) -> "PlatformResult[T]":
        return cls(True, value, None, dict(details))

    @classmethod
    def failure(
        cls,
        code: PlatformErrorCode,
        message: str,
        operation: str = "",
        platform: str = "",
        native_error: Any = "",
        instructions: str = "",
        **details: Any,
    ) -> "PlatformResult[T]":
        error = PlatformError(
            code=code,
            message=message,
            operation=operation,
            platform=platform,
            native_error=str(native_error or ""),
            instructions=instructions,
            details=dict(details),
        )
        return cls(False, None, error, dict(details))

    @classmethod
    def from_error(cls, error: PlatformError) -> "PlatformResult[T]":
        return cls(False, None, error, dict(error.details))

    def unwrap(self) -> T:
        """Devuelve ``value`` o levanta ``PlatformOperationError``."""
        if not self.ok:
            raise PlatformOperationError(
                self.error
                or PlatformError(PlatformErrorCode.NATIVE_ERROR, "resultado fallido sin error")
            )
        return self.value  # type: ignore[return-value]

    def to_dict(self) -> Dict[str, Any]:
        value = self.value
        if hasattr(value, "to_dict"):
            value = value.to_dict()  # type: ignore[union-attr]
        elif isinstance(value, list):
            value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]
        return {
            "ok": self.ok,
            "value": value,
            "error": self.error.to_dict() if self.error else None,
            "details": dict(self.details),
        }


# ============================================================================
# GEOMETRIA
# ============================================================================


@dataclass(frozen=True)
class Rect:
    """Rectangulo (left, top, right, bottom) en un espacio de coordenadas.

    ``right`` y ``bottom`` son exclusivos. Los valores pueden ser negativos
    (monitores a la izquierda o encima del principal) y, en macOS, fraccionarios
    (puntos).
    """

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center(self) -> Tuple[float, float]:
        return (self.left + self.width / 2.0, self.top + self.height / 2.0)

    def is_valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def contains_point(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def contains_rect(self, other: "Rect") -> bool:
        return (
            other.left >= self.left
            and other.top >= self.top
            and other.right <= self.right
            and other.bottom <= self.bottom
        )

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Rect(left, top, right, bottom)

    def intersection_area(self, other: "Rect") -> float:
        inter = self.intersection(other)
        return inter.area if inter else 0.0

    def iou(self, other: "Rect") -> float:
        inter = self.intersection_area(other)
        if inter <= 0:
            return 0.0
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def offset(self, dx: float, dy: float) -> "Rect":
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.left, self.top, self.right, self.bottom)

    def to_int_tuple(self) -> Tuple[int, int, int, int]:
        return (
            int(round(self.left)),
            int(round(self.top)),
            int(round(self.right)),
            int(round(self.bottom)),
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_any(cls, value: Any) -> Optional["Rect"]:
        """Construye un Rect desde tupla/lista ``(l, t, r, b)``, dict o Rect."""
        if value is None:
            return None
        if isinstance(value, Rect):
            return value
        try:
            if isinstance(value, dict):
                if "right" in value and "bottom" in value:
                    return cls(
                        float(value["left"]),
                        float(value["top"]),
                        float(value["right"]),
                        float(value["bottom"]),
                    )
                if "width" in value and "height" in value:
                    left = float(value.get("left", value.get("x", 0)))
                    top = float(value.get("top", value.get("y", 0)))
                    return cls(left, top, left + float(value["width"]), top + float(value["height"]))
                return None
            left, top, right, bottom = [float(v) for v in value]
            return cls(left, top, right, bottom)
        except (TypeError, ValueError, KeyError):
            return None

    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> "Rect":
        return cls(float(x), float(y), float(x) + float(width), float(y) + float(height))


# ============================================================================
# MODELOS DE DATOS
# ============================================================================


@dataclass
class DisplayInfo:
    """Monitor enumerado por el SO con geometria completa.

    Atributos:
        display_id: identificador estable cuando el SO lo da (Windows: nombre
            de dispositivo ``\\\\.\\DISPLAYn`` + ruta de dispositivo si existe;
            macOS: ``CGDirectDisplayID``). No es un indice de orden.
        bounds: rectangulo del monitor en el espacio de escritorio nativo.
        work_area: area util (sin barra de tareas / barra de menus y Dock).
        pixel_width/pixel_height: resolucion fisica en pixeles.
        scale_factor: Windows ``dpi/96``; macOS ``backingScaleFactor``.
        rotation: grados (0, 90, 180, 270).
        coordinate_space: ``DESKTOP_PIXELS`` (Windows) o ``DESKTOP_POINTS`` (macOS).
    """

    display_id: str
    name: str
    bounds: Rect
    work_area: Rect
    pixel_width: int
    pixel_height: int
    scale_factor: float = 1.0
    dpi: int = 96
    is_primary: bool = False
    rotation: int = 0
    refresh_rate: Optional[float] = None
    coordinate_space: str = DESKTOP_PIXELS
    native_handle: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def orientation(self) -> str:
        return "portrait" if self.bounds.height > self.bounds.width else "landscape"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "display_id": self.display_id,
            "name": self.name,
            "bounds": self.bounds.to_dict(),
            "work_area": self.work_area.to_dict(),
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "scale_factor": self.scale_factor,
            "dpi": self.dpi,
            "is_primary": self.is_primary,
            "rotation": self.rotation,
            "orientation": self.orientation,
            "refresh_rate": self.refresh_rate,
            "coordinate_space": self.coordinate_space,
            "native_handle": self.native_handle,
            "extra": dict(self.extra),
        }


@dataclass
class WindowInfo:
    """Ventana de nivel superior identificada por el SO.

    ``window_id`` es el HWND en Windows y el ``CGWindowID`` en macOS.
    ``bounds`` es el rectangulo exterior; ``frame_bounds`` el visible sin
    sombra (DWM extended frame bounds / frame AX); ``client_bounds`` el area
    cliente en el espacio de escritorio nativo. ``title`` solo se usa para
    identificar la ventana: no se persiste ni se envia a servicios externos.
    """

    window_id: int
    pid: int
    title: str = ""
    app_identity: str = ""
    bounds: Optional[Rect] = None
    client_bounds: Optional[Rect] = None
    frame_bounds: Optional[Rect] = None
    is_visible: bool = False
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    display_id: Optional[str] = None
    scale_factor: Optional[float] = None
    dpi: Optional[int] = None
    dpi_awareness: Optional[str] = None
    coordinate_space: str = DESKTOP_PIXELS
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "pid": self.pid,
            "title": self.title,
            "app_identity": self.app_identity,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "client_bounds": self.client_bounds.to_dict() if self.client_bounds else None,
            "frame_bounds": self.frame_bounds.to_dict() if self.frame_bounds else None,
            "is_visible": self.is_visible,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
            "is_foreground": self.is_foreground,
            "display_id": self.display_id,
            "scale_factor": self.scale_factor,
            "dpi": self.dpi,
            "dpi_awareness": self.dpi_awareness,
            "coordinate_space": self.coordinate_space,
            "extra": dict(self.extra),
        }


@dataclass
class PointerPosition:
    """Posicion real del puntero leida del SO."""

    x: float
    y: float
    coordinate_space: str = DESKTOP_PIXELS
    display_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "coordinate_space": self.coordinate_space,
            "display_id": self.display_id,
        }


@dataclass
class CaptureResult:
    """Captura de pantalla con su relacion geometrica con el escritorio.

    ``image`` es un ``numpy.ndarray`` (alto x ancho x canales) o ``None`` si
    solo se guardo en ``path``. ``region`` es el rectangulo capturado en el
    espacio de escritorio nativo. ``pixels_per_unit_x/y`` relaciona pixeles del
    frame con unidades del escritorio (1.0 en Windows; ``backingScaleFactor``
    en macOS Retina). ``captured_at`` usa ``time.monotonic()``.
    """

    region: Rect
    pixel_width: int
    pixel_height: int
    backend: str
    image: Any = None
    path: Optional[str] = None
    channels: str = ""
    pixels_per_unit_x: float = 1.0
    pixels_per_unit_y: float = 1.0
    captured_at: float = field(default_factory=time.monotonic)
    window_id: Optional[int] = None
    display_id: Optional[str] = None
    coordinate_space: str = DESKTOP_PIXELS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region": self.region.to_dict(),
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "backend": self.backend,
            "path": self.path,
            "channels": self.channels,
            "pixels_per_unit_x": self.pixels_per_unit_x,
            "pixels_per_unit_y": self.pixels_per_unit_y,
            "captured_at": self.captured_at,
            "window_id": self.window_id,
            "display_id": self.display_id,
            "coordinate_space": self.coordinate_space,
            "has_image": self.image is not None,
        }


@dataclass
class InteractionEnvironment:
    """Estado del entorno antes de capturar o enviar entradas a una ventana.

    Cada bandera ``True`` es un motivo concreto para NO interactuar. El
    contrato solo informa; nunca intenta eludir la proteccion.
    """

    session_locked: bool = False
    secure_desktop: bool = False
    target_elevated: bool = False
    jarvis_elevated: bool = False
    protected_content: bool = False
    protected_window: bool = False
    overlay_windows: List[int] = field(default_factory=list)
    target_minimized: bool = False
    target_visible: bool = True
    permissions_missing: List[str] = field(default_factory=list)
    unknown_checks: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def blocking_reasons(self) -> List[str]:
        """Motivos concretos que impiden capturar o enviar entradas."""
        reasons: List[str] = []
        if self.session_locked:
            reasons.append("session_locked")
        if self.secure_desktop:
            reasons.append("secure_desktop")
        if self.target_elevated and not self.jarvis_elevated:
            reasons.append("target_elevated")
        if self.protected_content:
            reasons.append("protected_content")
        if self.protected_window:
            reasons.append("protected_window")
        if self.overlay_windows:
            reasons.append("overlay_present")
        if self.target_minimized:
            reasons.append("target_minimized")
        if not self.target_visible:
            reasons.append("target_hidden")
        for perm in self.permissions_missing:
            reasons.append("permission_missing:%s" % perm)
        return reasons

    @property
    def allowed(self) -> bool:
        return not self.blocking_reasons()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocking_reasons": self.blocking_reasons(),
            "session_locked": self.session_locked,
            "secure_desktop": self.secure_desktop,
            "target_elevated": self.target_elevated,
            "jarvis_elevated": self.jarvis_elevated,
            "protected_content": self.protected_content,
            "protected_window": self.protected_window,
            "overlay_windows": list(self.overlay_windows),
            "target_minimized": self.target_minimized,
            "target_visible": self.target_visible,
            "permissions_missing": list(self.permissions_missing),
            "unknown_checks": list(self.unknown_checks),
            "details": dict(self.details),
        }


@dataclass
class WindowDpiInfo:
    """DPI/escala efectiva de una ventana y awareness del proceso."""

    window_id: int
    dpi: Optional[int] = None
    scale_factor: Optional[float] = None
    window_awareness: Optional[str] = None
    process_awareness: Optional[str] = None
    jarvis_awareness: Optional[str] = None
    display_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "dpi": self.dpi,
            "scale_factor": self.scale_factor,
            "window_awareness": self.window_awareness,
            "process_awareness": self.process_awareness,
            "jarvis_awareness": self.jarvis_awareness,
            "display_id": self.display_id,
            "details": dict(self.details),
        }


# Teclas logicas del contrato. ``primary_modifier`` es Ctrl en Windows y Cmd
# en macOS; los adaptadores traducen el resto a su codigo nativo.
LOGICAL_KEYS = frozenset({
    "primary_modifier", "ctrl", "cmd", "alt", "option", "shift", "win",
    "enter", "return", "escape", "tab", "space", "backspace", "delete",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
})

# Acciones de accesibilidad normalizadas (ver src.desktop.accessibility_model).
ACCESSIBILITY_ACTIONS = frozenset({
    "invoke", "toggle", "expand", "collapse", "select", "set_value",
    "scroll", "focus", "show_menu",
})


# ============================================================================
# CONTRATO DEL ADAPTADOR
# ============================================================================


class DesktopPlatformAdapter:
    """Contrato comun. Las implementaciones sobrescriben lo que soportan.

    Todo metodo no implementado devuelve ``NOT_SUPPORTED`` normalizado; ningun
    metodo debe levantar excepciones nativas hacia el consumidor.
    """

    platform_name: str = ""
    desktop_space: str = DESKTOP_PIXELS

    # ------------------------------------------------------------------
    # Utilidades comunes
    # ------------------------------------------------------------------

    def _unsupported(self, operation: str, detail: str = "") -> PlatformResult[Any]:
        return PlatformResult.failure(
            PlatformErrorCode.NOT_SUPPORTED,
            detail or "Operacion no soportada por el adaptador %s" % (self.platform_name or "desconocido"),
            operation=operation,
            platform=self.platform_name,
        )

    def _fail(
        self,
        operation: str,
        code: PlatformErrorCode,
        message: str,
        native_error: Any = "",
        instructions: str = "",
        **details: Any,
    ) -> PlatformResult[Any]:
        return PlatformResult.failure(
            code,
            message,
            operation=operation,
            platform=self.platform_name,
            native_error=native_error,
            instructions=instructions,
            **details,
        )

    # ------------------------------------------------------------------
    # Capacidades y permisos
    # ------------------------------------------------------------------

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        """Estado de cada capacidad en el equipo actual."""
        return {
            cap: CapabilityReport(cap, CapabilityStatus.NO_SOPORTADO, "adaptador base")
            for cap in Capability
        }

    def capability_status(self, capability: Capability) -> CapabilityStatus:
        report = self.capabilities().get(capability)
        return report.status if report else CapabilityStatus.NO_SOPORTADO

    def check_permissions(self) -> List[PermissionStatus]:
        """Estado de los permisos del SO relevantes para JARVIS."""
        return []

    # ------------------------------------------------------------------
    # Monitores
    # ------------------------------------------------------------------

    def enumerate_displays(self) -> PlatformResult[List[DisplayInfo]]:
        """Reenumera los monitores reales (nunca usa datos historicos)."""
        return self._unsupported("enumerate_displays")

    def start_display_change_listener(
        self, callback: Callable[[str], None]
    ) -> PlatformResult[Any]:
        """Suscribe ``callback(motivo)`` a cambios de pantalla del SO.

        Devuelve un manejador opaco para ``stop_display_change_listener``. Si el
        SO no ofrece notificaciones fiables, ``NOT_SUPPORTED`` y el consumidor
        compara el fingerprint de topologia antes de cada accion espacial.
        """
        return self._unsupported("start_display_change_listener")

    def stop_display_change_listener(self, handle: Any) -> PlatformResult[None]:
        return self._unsupported("stop_display_change_listener")

    # ------------------------------------------------------------------
    # Ventanas
    # ------------------------------------------------------------------

    def list_windows(
        self,
        pid: Optional[int] = None,
        app_identity: Optional[str] = None,
        visible_only: bool = True,
    ) -> PlatformResult[List[WindowInfo]]:
        """Ventanas de nivel superior, filtradas por PID o identidad."""
        return self._unsupported("list_windows")

    def get_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        return self._unsupported("get_window")

    def get_foreground_window(self) -> PlatformResult[Optional[WindowInfo]]:
        return self._unsupported("get_foreground_window")

    def window_at_point(self, x: float, y: float) -> PlatformResult[Optional[WindowInfo]]:
        """Ventana de nivel superior bajo un punto del escritorio."""
        return self._unsupported("window_at_point")

    def move_window_to_display(self, window_id: int, display_id: str) -> PlatformResult[WindowInfo]:
        """Mueve la ventana al monitor indicado (sin maximizar)."""
        return self._unsupported("move_window_to_display")

    def maximize_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        """Maximiza la ventana en su monitor actual y devuelve su geometria real.

        En macOS "maximizar" es ajustar el frame a ``visibleFrame`` via AX
        (no pantalla completa nativa, que crea otro Space).
        """
        return self._unsupported("maximize_window")

    def restore_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        return self._unsupported("restore_window")

    def set_window_bounds(self, window_id: int, bounds: Rect) -> PlatformResult[WindowInfo]:
        return self._unsupported("set_window_bounds")

    def activate_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        """Trae la ventana al frente y COMPRUEBA que quedo en primer plano."""
        return self._unsupported("activate_window")

    def is_foreground(self, window_id: int) -> bool:
        result = self.get_foreground_window()
        return bool(result.ok and result.value is not None and result.value.window_id == window_id)

    def get_window_dpi_info(self, window_id: int) -> PlatformResult[WindowDpiInfo]:
        return self._unsupported("get_window_dpi_info")

    def close_window(self, window_id: int) -> PlatformResult[None]:
        """Solicita el cierre ordenado (WM_CLOSE / AXCloseButton). Nunca fuerza."""
        return self._unsupported("close_window")

    # ------------------------------------------------------------------
    # Procesos
    # ------------------------------------------------------------------

    def process_exists(self, pid: int) -> bool:
        try:
            import psutil  # dependencia comun a ambos SO

            return bool(psutil.pid_exists(int(pid)))
        except Exception as exc:
            logger.debug("process_exists(%s): %s", pid, exc)
            return False

    def process_identity(self, pid: int) -> PlatformResult[Dict[str, Any]]:
        """Identidad del proceso (nombre ejecutable o bundle id). Sin rutas en logs."""
        try:
            import psutil

            proc = psutil.Process(int(pid))
            return PlatformResult.success({"pid": int(pid), "name": proc.name()})
        except Exception as exc:
            return self._fail("process_identity", PlatformErrorCode.NOT_FOUND, "proceso no encontrado", exc)

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------

    def capture_display(self, display_id: str) -> PlatformResult[CaptureResult]:
        return self._unsupported("capture_display")

    def capture_region(self, region: Rect) -> PlatformResult[CaptureResult]:
        return self._unsupported("capture_region")

    def capture_window(self, window_id: int) -> PlatformResult[CaptureResult]:
        """Captura el area visible de una ventana ya verificada en primer plano."""
        return self._unsupported("capture_window")

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def get_pointer_position(self) -> PlatformResult[PointerPosition]:
        return self._unsupported("get_pointer_position")

    def move_pointer(self, x: float, y: float) -> PlatformResult[PointerPosition]:
        """Posicionamiento absoluto; devuelve la posicion REAL leida despues."""
        return self._unsupported("move_pointer")

    def click(self, button: str = "left", count: int = 1) -> PlatformResult[None]:
        """Click en la posicion actual del puntero."""
        return self._unsupported("click")

    def scroll(self, amount: int, horizontal: bool = False) -> PlatformResult[None]:
        return self._unsupported("scroll")

    def type_text(self, text: str) -> PlatformResult[None]:
        return self._unsupported("type_text")

    def press_keys(self, keys: Sequence[str]) -> PlatformResult[None]:
        """Pulsa una combinacion de teclas logicas (``LOGICAL_KEYS`` o caracter)."""
        return self._unsupported("press_keys")

    # ------------------------------------------------------------------
    # Accesibilidad
    # ------------------------------------------------------------------

    def get_accessibility_tree(
        self,
        window_id: int,
        pid: Optional[int] = None,
        max_depth: int = 60,
        max_nodes: int = 2000,
    ) -> PlatformResult[Any]:
        """Arbol normalizado (``AccessibilityTree``) de UNA ventana identificada."""
        return self._unsupported("get_accessibility_tree")

    def element_at_point(self, x: float, y: float) -> PlatformResult[Any]:
        """Nodo de accesibilidad normalizado bajo un punto (o ``None``)."""
        return self._unsupported("element_at_point")

    def perform_accessibility_action(
        self,
        window_id: int,
        node_id: str,
        action: str,
        value: Any = None,
    ) -> PlatformResult[None]:
        """Ejecuta una accion de accesibilidad normalizada sobre un nodo.

        El adaptador no decide si la accion es segura: la politica vive en el
        consumidor (exploracion profunda, puertas de calidad).
        """
        return self._unsupported("perform_accessibility_action")

    # ------------------------------------------------------------------
    # Entorno de interaccion
    # ------------------------------------------------------------------

    def check_interaction_environment(self, window_id: int) -> PlatformResult[InteractionEnvironment]:
        """Sesion bloqueada, escritorio seguro, elevacion, contenido protegido,
        overlays y permisos antes de capturar o enviar entradas."""
        return self._unsupported("check_interaction_environment")


# ============================================================================
# SELECCION DEL ADAPTADOR
# ============================================================================


_ADAPTER_LOCK = threading.Lock()
_ADAPTER: Optional[DesktopPlatformAdapter] = None


def _create_adapter_for_platform(platform: str) -> DesktopPlatformAdapter:
    if platform == "win32":
        from src.desktop.platform_windows import WindowsDesktopAdapter

        return WindowsDesktopAdapter()
    if platform == "darwin":
        from src.desktop.platform_macos import MacOSDesktopAdapter

        return MacOSDesktopAdapter()
    raise PlatformNotSupportedError(
        "No hay adaptador de escritorio para el SO %r. Soportados: Windows y macOS." % platform
    )


def get_desktop_platform() -> DesktopPlatformAdapter:
    """Devuelve el adaptador del SO actual (singleton por proceso)."""
    global _ADAPTER
    if _ADAPTER is not None:
        return _ADAPTER
    with _ADAPTER_LOCK:
        if _ADAPTER is None:
            _ADAPTER = _create_adapter_for_platform(sys.platform)
            logger.info("Adaptador de escritorio seleccionado: %s", _ADAPTER.platform_name)
        return _ADAPTER


def create_desktop_platform(platform: Optional[str] = None) -> DesktopPlatformAdapter:
    """Crea un adaptador nuevo para ``platform`` (por defecto ``sys.platform``)."""
    return _create_adapter_for_platform(platform or sys.platform)


def set_desktop_platform(adapter: Optional[DesktopPlatformAdapter]) -> None:
    """Fija (o borra con ``None``) el adaptador del proceso. Uso: tests/inyeccion."""
    global _ADAPTER
    with _ADAPTER_LOCK:
        _ADAPTER = adapter


__all__ = [
    "DESKTOP_PIXELS",
    "DESKTOP_POINTS",
    "PLATFORM_WINDOWS",
    "PLATFORM_MACOS",
    "Capability",
    "CapabilityStatus",
    "CapabilityReport",
    "PermissionKind",
    "PermissionStatus",
    "PlatformErrorCode",
    "PlatformError",
    "PlatformOperationError",
    "PlatformNotSupportedError",
    "PlatformResult",
    "Rect",
    "DisplayInfo",
    "WindowInfo",
    "PointerPosition",
    "CaptureResult",
    "InteractionEnvironment",
    "WindowDpiInfo",
    "LOGICAL_KEYS",
    "ACCESSIBILITY_ACTIONS",
    "DesktopPlatformAdapter",
    "get_desktop_platform",
    "create_desktop_platform",
    "set_desktop_platform",
]
