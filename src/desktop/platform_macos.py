"""
Adaptador de escritorio macOS del contrato de plataforma (implementado a ciegas).

Implementa ``DesktopPlatformAdapter`` (``src.desktop.platform_contract``) para
macOS con APIs publicas de Apple via pyobjc:

* Monitores: ``NSScreen`` (frame, visibleFrame, backingScaleFactor,
  localizedName, deviceDescription["NSScreenNumber"]) y Quartz Display Services
  (``CGDisplayBounds``, ``CGDisplayCopyDisplayMode``,
  ``CGDisplayModeGetPixelWidth``, ``CGDisplayRotation``, ``CGDisplayIsMain``,
  ``CGDisplayVendorNumber``/``ModelNumber``/``SerialNumber``,
  ``CGDisplayScreenSize``).
* Ventanas: ``CGWindowListCopyWindowInfo`` (``window_id`` = ``kCGWindowNumber``,
  ``kCGWindowBounds`` en puntos Quartz) y ``AXUIElement`` (posicion, tamano,
  minimizado, ``AXRaise``, boton de cierre).
* Activacion: ``NSRunningApplication.activateWithOptions_`` y el atributo
  ``AXFrontmost`` de la aplicacion; se COMPRUEBA el primer plano real con
  ``NSWorkspace.frontmostApplication`` y el orden de ``CGWindowList``.
* Entrada: ``CGEventCreateMouseEvent``, ``CGEventCreateKeyboardEvent``,
  ``CGEventKeyboardSetUnicodeString``, ``CGEventCreateScrollWheelEvent``,
  ``CGEventPost(kCGHIDEventTap)``; posicion real con
  ``CGEventGetLocation(CGEventCreate(None))``. Coordenadas en puntos; la tecla
  ``primary_modifier`` es Cmd.
* Captura: ``CGWindowListCreateImage`` (o ``mss`` si pyobjc falta). La captura
  Retina devuelve pixeles: ``pixels_per_unit`` se MIDE (ancho de imagen /
  ancho de la region en puntos), nunca se supone.
* Accesibilidad: ``AXUIElementCreateApplication``,
  ``AXUIElementCopyAttributeValue``, ``AXUIElementCopyActionNames``,
  ``AXUIElementIsAttributeSettable``, ``AXUIElementPerformAction``,
  ``AXUIElementSetAttributeValue``, ``AXUIElementCopyElementAtPosition``,
  ``AXValueCreate``/``AXValueGetValue``; arbol normalizado con
  ``normalize_ax_attributes``.
* Permisos: ``AXIsProcessTrusted`` (Accesibilidad, tambien necesario para
  enviar eventos), ``CGPreflightScreenCaptureAccess`` (Grabacion de pantalla) y
  ``AVCaptureDevice.authorizationStatusForMediaType_`` (Microfono, si
  AVFoundation esta instalado). Nunca se eluden: falta de permiso ->
  ``SIN_PERMISO`` / ``PERMISSION_DENIED`` con instrucciones.

Toda llamada a pyobjc vive en ``MacNativeBoundary``, con imports perezosos
dentro de cada metodo, y devuelve datos Python planos (dicts, tuplas, listas,
numeros, ``bytes``) o manejadores opacos de elementos AX que el adaptador nunca
inspecciona. Asi los tests de contrato en Windows pueden sustituir la frontera
por una sintetica (Retina 2x, varios monitores, origen negativo, monitor
vertical, permisos denegados).

Sistemas de coordenadas (errores tipicos contemplados):

* El espacio de escritorio de este adaptador es ``DESKTOP_POINTS``: puntos
  globales de Quartz con origen arriba-izquierda del monitor principal (el de
  la barra de menus, ``NSScreen.screens()[0]``) y ``y`` creciendo hacia abajo.
  Puede haber origenes negativos.
* ``NSScreen`` usa coordenadas Cocoa (origen abajo-izquierda del principal,
  ``y`` hacia arriba). La conversion es ``y_quartz = alto_principal - (y + h)``.
* ``visibleFrame`` excluye barra de menus y Dock: es el ``work_area``.
* "Maximizar" = ajustar el frame de la ventana a ``visibleFrame`` via AX; nunca
  pantalla completa nativa (crea otro Space).
* Los pixeles reales del framebuffer son puntos x ``backingScaleFactor``.
* macOS no tiene "DPI awareness": la entrada CGEvent usa puntos y la captura
  devuelve pixeles. ``DisplayInfo.dpi`` es el DPI logico ``72 x escala``; el
  DPI fisico (si ``CGDisplayScreenSize`` lo da) va en ``extra``.
* Los permisos de Accesibilidad y Grabacion de pantalla se conceden a la app
  anfitriona (Terminal, VS Code o el binario de Python) y exigen reiniciarla.

Estado de verificacion: este modulo se escribio sin poder ejecutarlo contra
pyobjc en un Mac real (regla 3 de la cabecera del roadmap). Mientras
``MACOS_REAL_VERIFICATION`` sea ``False`` los informes de capacidad lo indican.

Cubre (referencia de localizacion en el roadmap): 3.8.6.5.5, 3.8.6.7.3, parte
macOS de 3.8.6.4.6 y de 3.8.6.6.5.

Limitaciones conocidas:

* No hay API publica para obtener el ``CGWindowID`` de un ``AXUIElement``: la
  ventana AX se empareja con la de CGWindowList por PID + geometria (+ titulo).
* ``kCGWindowName`` solo esta disponible con permiso de Grabacion de pantalla;
  sin el, el titulo se toma de AX cuando se consulta una ventana concreta.
* El "area cliente" en macOS se aproxima con el frame de la ventana (incluye
  barra de titulo); ``kCGWindowBounds`` no incluye la sombra.
* ``start_display_change_listener`` no se implementa (sin run loop propio
  verificable): el consumidor compara el fingerprint de topologia antes de
  cada accion espacial.
* El bloqueo de pantalla se lee de ``CGSessionCopyCurrentDictionary``; la clave
  ``CGSSessionScreenIsLocked`` no esta documentada por Apple: si falta, la
  comprobacion queda en ``unknown_checks``.
* Los codigos de tecla son posiciones fisicas ANSI (``kVK_ANSI_*``); con otra
  distribucion de teclado los atajos usan la tecla en esa posicion fisica.
* En macOS 14+ la activacion cooperativa puede negar el primer plano: el
  resultado se verifica y, si no se consigue, se devuelve el fallo.
"""

from __future__ import annotations

import importlib
import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.accessibility_model import (
    AccessibilityNode,
    AccessibilityTree,
    build_tree,
    normalize_ax_attributes,
)
from src.desktop.native_imports import NativeDependencyUnavailable
from src.desktop.platform_contract import (
    ACCESSIBILITY_ACTIONS,
    DESKTOP_POINTS,
    LOGICAL_KEYS,
    PLATFORM_MACOS,
    Capability,
    CapabilityReport,
    CapabilityStatus,
    CaptureResult,
    DesktopPlatformAdapter,
    DisplayInfo,
    InteractionEnvironment,
    PermissionKind,
    PermissionStatus,
    PlatformErrorCode,
    PlatformResult,
    PointerPosition,
    Rect,
    WindowDpiInfo,
    WindowInfo,
)

logger = get_logger(__name__)

# Cambiar a True solo cuando las comprobaciones reales en un Mac esten hechas.
MACOS_REAL_VERIFICATION = False
_UNVERIFIED_NOTE = "macOS: implementado sin verificar en equipo real"

# ---------------------------------------------------------------------------
# Constantes nativas (valores documentados en los headers de Apple)
# ---------------------------------------------------------------------------

# CGWindowListOption (CGWindow.h)
_KCG_LIST_ALL = 0
_KCG_LIST_ON_SCREEN_ONLY = 1
_KCG_LIST_INCLUDING_WINDOW = 8
_KCG_LIST_EXCLUDE_DESKTOP = 16
_KCG_NULL_WINDOW_ID = 0
# CGWindowImageOption (CGWindow.h)
_KCG_IMAGE_DEFAULT = 0
_KCG_IMAGE_BOUNDS_IGNORE_FRAMING = 1
_KCG_IMAGE_BEST_RESOLUTION = 8
# CGWindowSharingType: kCGWindowSharingNone = 0 (contenido no capturable)
_KCG_WINDOW_SHARING_NONE = 0

# CGEventType (CGEventTypes.h)
_KCG_EVENT_LEFT_DOWN = 1
_KCG_EVENT_LEFT_UP = 2
_KCG_EVENT_RIGHT_DOWN = 3
_KCG_EVENT_RIGHT_UP = 4
_KCG_EVENT_MOUSE_MOVED = 5
_KCG_EVENT_OTHER_DOWN = 25
_KCG_EVENT_OTHER_UP = 26
# CGMouseButton
_KCG_BUTTON_LEFT = 0
_KCG_BUTTON_RIGHT = 1
_KCG_BUTTON_CENTER = 2
# CGEventField kCGMouseEventClickState
_KCG_MOUSE_EVENT_CLICK_STATE = 1
# CGEventTapLocation kCGHIDEventTap
_KCG_HID_EVENT_TAP = 0
# CGScrollEventUnit kCGScrollEventUnitLine
_KCG_SCROLL_UNIT_LINE = 1

# CGEventFlags (CGEventTypes.h)
_FLAG_SHIFT = 1 << 17
_FLAG_CONTROL = 1 << 18
_FLAG_OPTION = 1 << 19
_FLAG_COMMAND = 1 << 20

# AXError (AXError.h)
AX_ERROR_SUCCESS = 0
AX_ERROR_FAILURE = -25200
AX_ERROR_ILLEGAL_ARGUMENT = -25201
AX_ERROR_INVALID_UI_ELEMENT = -25202
AX_ERROR_CANNOT_COMPLETE = -25204
AX_ERROR_ATTRIBUTE_UNSUPPORTED = -25205
AX_ERROR_ACTION_UNSUPPORTED = -25206
AX_ERROR_NOT_IMPLEMENTED = -25208
AX_ERROR_API_DISABLED = -25211
AX_ERROR_NO_VALUE = -25212

# NSApplicationActivationOptions
_NS_ACTIVATE_ALL_WINDOWS = 1 << 0
_NS_ACTIVATE_IGNORING_OTHER_APPS = 1 << 1

# AVAuthorizationStatus
_AV_NOT_DETERMINED = 0
_AV_RESTRICTED = 1
_AV_DENIED = 2
_AV_AUTHORIZED = 3

# Codigos de tecla virtuales (HIToolbox/Events.h, kVK_*). Posiciones fisicas ANSI.
_KEYCODES: Dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
    "enter": 0x24, "return": 0x24, "tab": 0x30, "space": 0x31,
    "backspace": 0x33, "escape": 0x35, "delete": 0x75,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
}

# Modificadores logicos -> (codigo de tecla, mascara de flag).
_MODIFIERS: Dict[str, Tuple[int, int]] = {
    "primary_modifier": (0x37, _FLAG_COMMAND),   # Cmd en macOS
    "cmd": (0x37, _FLAG_COMMAND),
    "win": (0x37, _FLAG_COMMAND),                # tecla en la misma posicion fisica
    "ctrl": (0x3B, _FLAG_CONTROL),
    "alt": (0x3A, _FLAG_OPTION),
    "option": (0x3A, _FLAG_OPTION),
    "shift": (0x38, _FLAG_SHIFT),
}

# Atributos AX leidos por elemento (AXAttributeConstants.h).
_AX_ELEMENT_ATTRIBUTES = (
    "AXRole", "AXSubrole", "AXTitle", "AXDescription", "AXIdentifier",
    "AXPosition", "AXSize", "AXEnabled", "AXFocused", "AXHidden",
    "AXExpanded", "AXSelected", "AXDisclosing",
)
# Roles cuyo AXValue puede contener contenido del usuario: nunca se lee.
_AX_PRIVATE_VALUE_ROLES = frozenset({
    "AXTextField", "AXSecureTextField", "AXTextArea", "AXSearchField",
    "AXComboBox", "AXWebArea",
})
# Roles AX que recortan el area visible de sus hijos.
_AX_CLIPPING_ROLES = frozenset({"AXScrollArea"})

# Aplicaciones/ventanas del sistema que protegen credenciales o la sesion.
_PROTECTED_BUNDLES = frozenset({
    "com.apple.loginwindow",
    "com.apple.SecurityAgent",
    "com.apple.LocalAuthentication.UIAgent",
})
_PROTECTED_OWNER_NAMES = frozenset({"loginwindow", "SecurityAgent", "coreautha"})

_INSTR_ACCESSIBILITY = (
    "Abra Ajustes del Sistema > Privacidad y seguridad > Accesibilidad y active "
    "la aplicacion que ejecuta JARVIS (Terminal, VS Code o el binario de Python). "
    "Despues cierre y vuelva a abrir esa aplicacion."
)
_INSTR_SCREEN_RECORDING = (
    "Abra Ajustes del Sistema > Privacidad y seguridad > Grabacion de pantalla "
    "(Grabacion de pantalla y audio del sistema en macOS 15) y active la "
    "aplicacion que ejecuta JARVIS. Despues cierre y vuelva a abrir esa aplicacion."
)
_INSTR_MICROPHONE = (
    "Abra Ajustes del Sistema > Privacidad y seguridad > Microfono y active la "
    "aplicacion que ejecuta JARVIS. Despues cierre y vuelva a abrir esa aplicacion."
)
_INSTR_PYOBJC = (
    "Instale las dependencias macOS de docs/requirements/requirements.txt "
    "(pyobjc-framework-Cocoa, -Quartz, -ApplicationServices) con "
    "docs/requirements/jarvis_requirements.command."
)


def _import(module_name: str) -> Any:
    """Importa un framework pyobjc o levanta NativeDependencyUnavailable."""
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        raise NativeDependencyUnavailable(
            "No se pudo importar %s (pyobjc): %s" % (module_name, exc)
        ) from exc


def _const(module: Any, *names: str, default: Any = None) -> Any:
    """Devuelve la primera constante existente (pyobjc renombra algunas)."""
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    return default


def _rect_tuple(rect: Any) -> Tuple[float, float, float, float]:
    """NSRect/CGRect -> (x, y, w, h) en floats."""
    return (
        float(rect.origin.x),
        float(rect.origin.y),
        float(rect.size.width),
        float(rect.size.height),
    )


# ============================================================================
# FRONTERA NATIVA (UNICO PUNTO QUE TOCA PYOBJC)
# ============================================================================


class MacNativeBoundary:
    """Frontera nativa macOS. Unica clase que llama a pyobjc.

    Cada metodo importa sus frameworks dentro del propio metodo, cita la API de
    Apple usada y devuelve datos Python planos. Los manejadores de elementos AX
    se devuelven como objetos opacos que el adaptador solo reenvia a la
    frontera. Los errores se propagan como excepciones: el adaptador las
    convierte en ``PlatformResult`` normalizados.
    """

    ax_messaging_timeout = 2.0

    # ------------------------------------------------------------------
    # Dependencias
    # ------------------------------------------------------------------

    def dependencies(self) -> Dict[str, Optional[str]]:
        """Nombre de framework -> ``None`` si importa o texto del error."""
        result: Dict[str, Optional[str]] = {}
        for name in ("AppKit", "Quartz", "ApplicationServices", "AVFoundation", "mss"):
            try:
                importlib.import_module(name)
                result[name] = None
            except Exception as exc:
                result[name] = str(exc) or type(exc).__name__
        return result

    # ------------------------------------------------------------------
    # Monitores
    # ------------------------------------------------------------------

    def screens(self) -> List[Dict[str, Any]]:
        """Monitores en el orden de ``NSScreen.screens()`` (el primero es el principal).

        APIs: ``NSScreen.screens``, ``frame``, ``visibleFrame``,
        ``backingScaleFactor``, ``localizedName``, ``deviceDescription``;
        ``CGDisplayBounds``, ``CGDisplayCopyDisplayMode``,
        ``CGDisplayModeGetPixelWidth/Height``, ``CGDisplayModeGetWidth``,
        ``CGDisplayModeGetRefreshRate``, ``CGDisplayRotation``,
        ``CGDisplayIsMain``, ``CGDisplayIsBuiltin``, ``CGDisplayVendorNumber``,
        ``CGDisplayModelNumber``, ``CGDisplaySerialNumber``,
        ``CGDisplayScreenSize``.
        """
        AppKit = _import("AppKit")
        Quartz = _import("Quartz")
        result: List[Dict[str, Any]] = []
        for index, screen in enumerate(AppKit.NSScreen.screens() or []):
            description = screen.deviceDescription()
            display_id = int(description["NSScreenNumber"])
            entry: Dict[str, Any] = {
                "index": index,
                "display_id": display_id,
                "frame": _rect_tuple(screen.frame()),
                "visible_frame": _rect_tuple(screen.visibleFrame()),
                "backing_scale": float(screen.backingScaleFactor()),
                "name": "",
            }
            try:
                entry["name"] = str(screen.localizedName())  # macOS 10.15+
            except Exception:
                entry["name"] = ""
            try:
                entry["quartz_bounds"] = _rect_tuple(Quartz.CGDisplayBounds(display_id))
            except Exception as exc:
                logger.debug("CGDisplayBounds(%s): %s", display_id, exc)
            try:
                mode = Quartz.CGDisplayCopyDisplayMode(display_id)
                if mode is not None:
                    entry["mode_pixel_width"] = int(Quartz.CGDisplayModeGetPixelWidth(mode))
                    entry["mode_pixel_height"] = int(Quartz.CGDisplayModeGetPixelHeight(mode))
                    entry["mode_width"] = int(Quartz.CGDisplayModeGetWidth(mode))
                    entry["mode_height"] = int(Quartz.CGDisplayModeGetHeight(mode))
                    entry["refresh_rate"] = float(Quartz.CGDisplayModeGetRefreshRate(mode))
            except Exception as exc:
                logger.debug("CGDisplayCopyDisplayMode(%s): %s", display_id, exc)
            for key, fn in (
                ("rotation", "CGDisplayRotation"),
                ("is_main", "CGDisplayIsMain"),
                ("is_builtin", "CGDisplayIsBuiltin"),
                ("vendor", "CGDisplayVendorNumber"),
                ("model", "CGDisplayModelNumber"),
                ("serial", "CGDisplaySerialNumber"),
            ):
                try:
                    entry[key] = getattr(Quartz, fn)(display_id)
                except Exception as exc:
                    logger.debug("%s(%s): %s", fn, display_id, exc)
            try:
                size_mm = Quartz.CGDisplayScreenSize(display_id)
                entry["size_mm"] = (float(size_mm.width), float(size_mm.height))
            except Exception as exc:
                logger.debug("CGDisplayScreenSize(%s): %s", display_id, exc)
            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Ventanas (CGWindowList)
    # ------------------------------------------------------------------

    def window_list(self, mode: str = "on_screen", window_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Ventanas en orden de delante hacia atras.

        API: ``CGWindowListCopyWindowInfo`` con ``kCGWindowListOptionOnScreenOnly``
        (``mode="on_screen"``), ``kCGWindowListOptionAll`` (``"all"``) o
        ``kCGWindowListOptionIncludingWindow`` (``"single"``), siempre con
        ``kCGWindowListExcludeDesktopElements`` salvo ``"single"``.
        Claves: ``kCGWindowNumber``, ``kCGWindowOwnerPID``, ``kCGWindowOwnerName``,
        ``kCGWindowName`` (requiere Grabacion de pantalla), ``kCGWindowBounds``,
        ``kCGWindowLayer``, ``kCGWindowAlpha``, ``kCGWindowIsOnscreen``,
        ``kCGWindowSharingState``.
        """
        Quartz = _import("Quartz")
        if mode == "single":
            option = _KCG_LIST_INCLUDING_WINDOW
            relative = int(window_id or 0)
        elif mode == "all":
            option = _KCG_LIST_ALL | _KCG_LIST_EXCLUDE_DESKTOP
            relative = _KCG_NULL_WINDOW_ID
        else:
            option = _KCG_LIST_ON_SCREEN_ONLY | _KCG_LIST_EXCLUDE_DESKTOP
            relative = _KCG_NULL_WINDOW_ID
        raw = Quartz.CGWindowListCopyWindowInfo(option, relative) or []
        result: List[Dict[str, Any]] = []
        for z_index, info in enumerate(raw):
            bounds = info.get("kCGWindowBounds") or {}
            result.append({
                "window_id": int(info.get("kCGWindowNumber", 0) or 0),
                "pid": int(info.get("kCGWindowOwnerPID", 0) or 0),
                "owner_name": str(info.get("kCGWindowOwnerName", "") or ""),
                "title": str(info.get("kCGWindowName", "") or ""),
                "bounds": (
                    float(bounds.get("X", 0.0)),
                    float(bounds.get("Y", 0.0)),
                    float(bounds.get("Width", 0.0)),
                    float(bounds.get("Height", 0.0)),
                ),
                "layer": int(info.get("kCGWindowLayer", 0) or 0),
                "alpha": float(info.get("kCGWindowAlpha", 1.0) if info.get("kCGWindowAlpha") is not None else 1.0),
                "onscreen": bool(info.get("kCGWindowIsOnscreen", False)),
                "sharing_state": int(info.get("kCGWindowSharingState", 1)
                                     if info.get("kCGWindowSharingState") is not None else 1),
                "z_index": z_index,
            })
        return result

    # ------------------------------------------------------------------
    # Aplicaciones (NSRunningApplication / NSWorkspace)
    # ------------------------------------------------------------------

    def running_application(self, pid: int) -> Optional[Dict[str, Any]]:
        """API: ``NSRunningApplication.runningApplicationWithProcessIdentifier_``."""
        AppKit = _import("AppKit")
        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is None:
            return None
        executable_name = ""
        try:
            url = app.executableURL()
            executable_name = str(url.lastPathComponent()) if url is not None else ""
        except Exception:
            executable_name = ""
        return {
            "pid": int(app.processIdentifier()),
            "bundle_id": str(app.bundleIdentifier() or ""),
            "name": str(app.localizedName() or ""),
            "executable_name": executable_name,
            "active": bool(app.isActive()),
            "hidden": bool(app.isHidden()),
            "activation_policy": int(app.activationPolicy()),
            "terminated": bool(app.isTerminated()),
        }

    def frontmost_application(self) -> Optional[Dict[str, Any]]:
        """API: ``NSWorkspace.sharedWorkspace().frontmostApplication()``."""
        AppKit = _import("AppKit")
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return {
            "pid": int(app.processIdentifier()),
            "bundle_id": str(app.bundleIdentifier() or ""),
            "name": str(app.localizedName() or ""),
        }

    def activate_application(self, pid: int) -> bool:
        """API: ``NSRunningApplication.unhide`` + ``activateWithOptions_``."""
        AppKit = _import("AppKit")
        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is None:
            return False
        try:
            if app.isHidden():
                app.unhide()
        except Exception as exc:
            logger.debug("unhide(%s): %s", pid, exc)
        options = _NS_ACTIVATE_ALL_WINDOWS | _NS_ACTIVATE_IGNORING_OTHER_APPS
        return bool(app.activateWithOptions_(options))

    def process_euid(self, pid: int) -> Optional[int]:
        """UID efectivo de un proceso (psutil; sin pyobjc)."""
        try:
            import psutil

            return int(psutil.Process(int(pid)).uids().effective)
        except Exception as exc:
            logger.debug("process_euid(%s): %s", pid, exc)
            return None

    def own_euid(self) -> int:
        return int(os.geteuid())

    # ------------------------------------------------------------------
    # Permisos y sesion
    # ------------------------------------------------------------------

    def ax_is_trusted(self) -> bool:
        """API: ``AXIsProcessTrusted`` (sin mostrar el dialogo del sistema)."""
        AS = _import("ApplicationServices")
        return bool(AS.AXIsProcessTrusted())

    def screen_capture_access(self) -> Optional[bool]:
        """API: ``CGPreflightScreenCaptureAccess`` (macOS 10.15+, no muestra dialogo)."""
        Quartz = _import("Quartz")
        fn = getattr(Quartz, "CGPreflightScreenCaptureAccess", None)
        if fn is None:
            return None
        return bool(fn())

    def microphone_authorization(self) -> Optional[int]:
        """API: ``AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)``."""
        AV = _import("AVFoundation")
        return int(AV.AVCaptureDevice.authorizationStatusForMediaType_(AV.AVMediaTypeAudio))

    def session_info(self) -> Optional[Dict[str, Any]]:
        """API: ``CGSessionCopyCurrentDictionary`` (``kCGSessionOnConsoleKey``).

        La clave ``CGSSessionScreenIsLocked`` no esta documentada por Apple; se
        devuelve solo si aparece en el diccionario.
        """
        Quartz = _import("Quartz")
        info = Quartz.CGSessionCopyCurrentDictionary()
        if info is None:
            return None
        on_console_key = _const(Quartz, "kCGSessionOnConsoleKey", default="kCGSSessionOnConsoleKey")
        result: Dict[str, Any] = {"on_console": bool(info.get(on_console_key, True))}
        if "CGSSessionScreenIsLocked" in info:
            result["screen_locked"] = bool(info.get("CGSSessionScreenIsLocked"))
        return result

    # ------------------------------------------------------------------
    # Accesibilidad (AXUIElement)
    # ------------------------------------------------------------------

    def _ax_copy(self, AS: Any, element: Any, attribute: str) -> Tuple[int, Any]:
        """API: ``AXUIElementCopyAttributeValue``."""
        err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
        return int(err), value

    def _ax_point(self, AS: Any, value: Any) -> Optional[Tuple[float, float]]:
        """API: ``AXValueGetValue(kAXValueCGPointType)``."""
        if value is None:
            return None
        point_type = _const(AS, "kAXValueCGPointType", "kAXValueTypeCGPoint", default=1)
        ok, point = AS.AXValueGetValue(value, point_type, None)
        if not ok:
            return None
        return (float(point.x), float(point.y))

    def _ax_size(self, AS: Any, value: Any) -> Optional[Tuple[float, float]]:
        """API: ``AXValueGetValue(kAXValueCGSizeType)``."""
        if value is None:
            return None
        size_type = _const(AS, "kAXValueCGSizeType", "kAXValueTypeCGSize", default=2)
        ok, size = AS.AXValueGetValue(value, size_type, None)
        if not ok:
            return None
        return (float(size.width), float(size.height))

    def ax_application(self, pid: int) -> Any:
        """API: ``AXUIElementCreateApplication`` + ``AXUIElementSetMessagingTimeout``."""
        AS = _import("ApplicationServices")
        app = AS.AXUIElementCreateApplication(int(pid))
        try:
            AS.AXUIElementSetMessagingTimeout(app, float(self.ax_messaging_timeout))
        except Exception as exc:
            logger.debug("AXUIElementSetMessagingTimeout(%s): %s", pid, exc)
        return app

    def ax_application_windows(self, pid: int) -> List[Dict[str, Any]]:
        """Ventanas AX de una aplicacion (``kAXWindowsAttribute``)."""
        AS = _import("ApplicationServices")
        app = self.ax_application(pid)
        err, windows = self._ax_copy(AS, app, "AXWindows")
        if err != AX_ERROR_SUCCESS or windows is None:
            if err == AX_ERROR_API_DISABLED:
                raise PermissionError("AXWindows: API de accesibilidad deshabilitada (%s)" % err)
            return []
        result: List[Dict[str, Any]] = []
        for window in windows:
            entry: Dict[str, Any] = {"handle": window}
            _, pos = self._ax_copy(AS, window, "AXPosition")
            _, size = self._ax_copy(AS, window, "AXSize")
            entry["position"] = self._ax_point(AS, pos)
            entry["size"] = self._ax_size(AS, size)
            for key, attr in (
                ("title", "AXTitle"), ("minimized", "AXMinimized"), ("main", "AXMain"),
                ("focused", "AXFocused"), ("fullscreen", "AXFullScreen"),
                ("role", "AXRole"), ("subrole", "AXSubrole"),
            ):
                e, value = self._ax_copy(AS, window, attr)
                entry[key] = value if e == AX_ERROR_SUCCESS else None
            entry["title"] = str(entry.get("title") or "")
            for key in ("minimized", "main", "focused", "fullscreen"):
                entry[key] = bool(entry.get(key)) if entry.get(key) is not None else False
            result.append(entry)
        return result

    def ax_attributes(self, element: Any) -> Dict[str, Any]:
        """Atributos planos de un elemento AX para ``normalize_ax_attributes``.

        APIs: ``AXUIElementCopyAttributeValue``, ``AXValueGetValue``,
        ``AXUIElementCopyActionNames``, ``AXUIElementIsAttributeSettable``.
        Nunca lee ``AXValue`` de roles que pueden contener texto del usuario.
        """
        AS = _import("ApplicationServices")
        attrs: Dict[str, Any] = {}
        for name in _AX_ELEMENT_ATTRIBUTES:
            err, value = self._ax_copy(AS, element, name)
            if err == AX_ERROR_API_DISABLED:
                raise PermissionError("AX deshabilitado leyendo %s" % name)
            if err == AX_ERROR_INVALID_UI_ELEMENT:
                raise LookupError("elemento AX invalido")
            if err != AX_ERROR_SUCCESS or value is None:
                continue
            if name == "AXPosition":
                attrs[name] = self._ax_point(AS, value)
            elif name == "AXSize":
                attrs[name] = self._ax_size(AS, value)
            elif isinstance(value, bool) or name in ("AXEnabled", "AXFocused", "AXHidden",
                                                     "AXExpanded", "AXSelected", "AXDisclosing"):
                attrs[name] = bool(value)
            else:
                attrs[name] = str(value)
        role = str(attrs.get("AXRole") or "")
        if role and role not in _AX_PRIVATE_VALUE_ROLES:
            err, value = self._ax_copy(AS, element, "AXValue")
            if err == AX_ERROR_SUCCESS and isinstance(value, (str, int, float, bool)):
                attrs["AXValue"] = value
        try:
            err, names = AS.AXUIElementCopyActionNames(element, None)
            attrs["_actions"] = [str(n) for n in (names or [])] if int(err) == AX_ERROR_SUCCESS else []
        except Exception as exc:
            logger.debug("AXUIElementCopyActionNames: %s", exc)
            attrs["_actions"] = []
        for flag, attribute in (("_value_settable", "AXValue"), ("_focusable", "AXFocused")):
            try:
                err, settable = AS.AXUIElementIsAttributeSettable(element, attribute, None)
                attrs[flag] = bool(settable) if int(err) == AX_ERROR_SUCCESS else False
            except Exception:
                attrs[flag] = False
        if role in _AX_PRIVATE_VALUE_ROLES:
            # Escribir texto en campos del usuario nunca forma parte del contrato
            # de descubrimiento: el dato se conserva, el valor no se lee.
            attrs["_value_private"] = True
        return attrs

    def ax_children(self, element: Any) -> List[Any]:
        """API: ``AXUIElementCopyAttributeValue(kAXChildrenAttribute)``."""
        AS = _import("ApplicationServices")
        err, children = self._ax_copy(AS, element, "AXChildren")
        if err != AX_ERROR_SUCCESS or children is None:
            return []
        return list(children)

    def ax_parent(self, element: Any) -> Optional[Any]:
        """API: ``AXUIElementCopyAttributeValue(kAXParentAttribute)``."""
        AS = _import("ApplicationServices")
        err, parent = self._ax_copy(AS, element, "AXParent")
        if err != AX_ERROR_SUCCESS:
            return None
        return parent

    def ax_attribute_element(self, element: Any, attribute: str) -> Optional[Any]:
        """Elemento referenciado por un atributo (``AXCloseButton``, ``AXWindow``...)."""
        AS = _import("ApplicationServices")
        err, value = self._ax_copy(AS, element, attribute)
        if err != AX_ERROR_SUCCESS:
            return None
        return value

    def ax_equal(self, a: Any, b: Any) -> bool:
        """API: ``CFEqual`` (via igualdad de objetos CF en pyobjc)."""
        CoreFoundation = _import("CoreFoundation")
        try:
            return bool(CoreFoundation.CFEqual(a, b))
        except Exception:
            return a == b

    def ax_element_at_position(self, x: float, y: float) -> Optional[Any]:
        """API: ``AXUIElementCreateSystemWide`` + ``AXUIElementCopyElementAtPosition``."""
        AS = _import("ApplicationServices")
        system = AS.AXUIElementCreateSystemWide()
        err, element = AS.AXUIElementCopyElementAtPosition(system, float(x), float(y), None)
        if int(err) == AX_ERROR_API_DISABLED:
            raise PermissionError("AX deshabilitado en AXUIElementCopyElementAtPosition")
        if int(err) != AX_ERROR_SUCCESS:
            return None
        return element

    def ax_element_pid(self, element: Any) -> Optional[int]:
        """API: ``AXUIElementGetPid``."""
        AS = _import("ApplicationServices")
        err, pid = AS.AXUIElementGetPid(element, None)
        if int(err) != AX_ERROR_SUCCESS:
            return None
        return int(pid)

    def ax_set_position(self, element: Any, x: float, y: float) -> int:
        """API: ``AXValueCreate(kAXValueCGPointType)`` + ``AXUIElementSetAttributeValue(kAXPositionAttribute)``."""
        AS = _import("ApplicationServices")
        Quartz = _import("Quartz")
        point_type = _const(AS, "kAXValueCGPointType", "kAXValueTypeCGPoint", default=1)
        value = AS.AXValueCreate(point_type, Quartz.CGPoint(float(x), float(y)))
        return int(AS.AXUIElementSetAttributeValue(element, "AXPosition", value))

    def ax_set_size(self, element: Any, width: float, height: float) -> int:
        """API: ``AXValueCreate(kAXValueCGSizeType)`` + ``AXUIElementSetAttributeValue(kAXSizeAttribute)``."""
        AS = _import("ApplicationServices")
        Quartz = _import("Quartz")
        size_type = _const(AS, "kAXValueCGSizeType", "kAXValueTypeCGSize", default=2)
        value = AS.AXValueCreate(size_type, Quartz.CGSize(float(width), float(height)))
        return int(AS.AXUIElementSetAttributeValue(element, "AXSize", value))

    def ax_set_bool(self, element: Any, attribute: str, value: bool) -> int:
        """API: ``AXUIElementSetAttributeValue`` con un booleano."""
        AS = _import("ApplicationServices")
        return int(AS.AXUIElementSetAttributeValue(element, attribute, bool(value)))

    def ax_set_value(self, element: Any, value: Any) -> int:
        """API: ``AXUIElementSetAttributeValue(kAXValueAttribute)``."""
        AS = _import("ApplicationServices")
        return int(AS.AXUIElementSetAttributeValue(element, "AXValue", value))

    def ax_perform_action(self, element: Any, action: str) -> int:
        """API: ``AXUIElementPerformAction``."""
        AS = _import("ApplicationServices")
        return int(AS.AXUIElementPerformAction(element, action))

    def ax_set_app_frontmost(self, pid: int) -> int:
        """API: ``AXUIElementSetAttributeValue(app, kAXFrontmostAttribute, True)``."""
        AS = _import("ApplicationServices")
        app = self.ax_application(pid)
        return int(AS.AXUIElementSetAttributeValue(app, "AXFrontmost", True))

    # ------------------------------------------------------------------
    # Eventos de entrada (CGEvent, coordenadas en puntos Quartz)
    # ------------------------------------------------------------------

    def pointer_location(self) -> Tuple[float, float]:
        """API: ``CGEventGetLocation(CGEventCreate(None))`` (Quartz global, puntos)."""
        Quartz = _import("Quartz")
        point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return (float(point.x), float(point.y))

    def post_mouse_move(self, x: float, y: float) -> None:
        """API: ``CGEventCreateMouseEvent(kCGEventMouseMoved)`` + ``CGEventPost``."""
        Quartz = _import("Quartz")
        event = Quartz.CGEventCreateMouseEvent(
            None, _KCG_EVENT_MOUSE_MOVED, Quartz.CGPoint(float(x), float(y)), _KCG_BUTTON_LEFT
        )
        Quartz.CGEventPost(_KCG_HID_EVENT_TAP, event)

    def post_mouse_button(self, x: float, y: float, button: str, down: bool, click_state: int) -> None:
        """API: ``CGEventCreateMouseEvent`` + ``CGEventSetIntegerValueField(kCGMouseEventClickState)`` + ``CGEventPost``."""
        Quartz = _import("Quartz")
        if button == "right":
            event_type = _KCG_EVENT_RIGHT_DOWN if down else _KCG_EVENT_RIGHT_UP
            cg_button = _KCG_BUTTON_RIGHT
        elif button == "middle":
            event_type = _KCG_EVENT_OTHER_DOWN if down else _KCG_EVENT_OTHER_UP
            cg_button = _KCG_BUTTON_CENTER
        else:
            event_type = _KCG_EVENT_LEFT_DOWN if down else _KCG_EVENT_LEFT_UP
            cg_button = _KCG_BUTTON_LEFT
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type, Quartz.CGPoint(float(x), float(y)), cg_button
        )
        Quartz.CGEventSetIntegerValueField(event, _KCG_MOUSE_EVENT_CLICK_STATE, int(click_state))
        Quartz.CGEventPost(_KCG_HID_EVENT_TAP, event)

    def post_scroll(self, amount: int, horizontal: bool) -> None:
        """API: ``CGEventCreateScrollWheelEvent(kCGScrollEventUnitLine)`` + ``CGEventPost``."""
        Quartz = _import("Quartz")
        if horizontal:
            event = Quartz.CGEventCreateScrollWheelEvent(None, _KCG_SCROLL_UNIT_LINE, 2, 0, int(amount))
        else:
            event = Quartz.CGEventCreateScrollWheelEvent(None, _KCG_SCROLL_UNIT_LINE, 1, int(amount))
        Quartz.CGEventPost(_KCG_HID_EVENT_TAP, event)

    def post_key(self, keycode: int, down: bool, flags: int) -> None:
        """API: ``CGEventCreateKeyboardEvent`` + ``CGEventSetFlags`` + ``CGEventPost``."""
        Quartz = _import("Quartz")
        event = Quartz.CGEventCreateKeyboardEvent(None, int(keycode), bool(down))
        Quartz.CGEventSetFlags(event, int(flags))
        Quartz.CGEventPost(_KCG_HID_EVENT_TAP, event)

    def post_unicode(self, text: str) -> None:
        """API: ``CGEventCreateKeyboardEvent`` + ``CGEventKeyboardSetUnicodeString`` + ``CGEventPost``."""
        Quartz = _import("Quartz")
        chunk_size = 20  # limite practico de unidades UTF-16 por evento
        for start in range(0, len(text), chunk_size):
            chunk = text[start:start + chunk_size]
            length = len(chunk.encode("utf-16-le")) // 2
            for down in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
                Quartz.CGEventKeyboardSetUnicodeString(event, length, chunk)
                Quartz.CGEventPost(_KCG_HID_EVENT_TAP, event)

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------

    def capture_image(
        self,
        rect: Optional[Tuple[float, float, float, float]],
        window_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Captura una region (puntos Quartz) o una ventana concreta.

        APIs: ``CGWindowListCreateImage`` (region: ``kCGWindowListOptionOnScreenOnly``;
        ventana: ``kCGWindowListOptionIncludingWindow`` +
        ``kCGWindowImageBoundsIgnoreFraming``, sin sombra), ``CGImageGetWidth``,
        ``CGImageGetHeight``, ``CGImageGetBytesPerRow``,
        ``CGImageGetBitsPerPixel``, ``CGImageGetBitmapInfo``,
        ``CGDataProviderCopyData(CGImageGetDataProvider)``.
        El formato habitual es BGRA (kCGBitmapByteOrder32Little + alfa premultiplicado
        primero). Sin permiso de Grabacion de pantalla la imagen no contiene las
        ventanas de otras aplicaciones: el adaptador comprueba antes el permiso.
        """
        Quartz = _import("Quartz")
        create = getattr(Quartz, "CGWindowListCreateImage", None)
        if create is None:
            return None
        if window_id is not None:
            image = create(
                Quartz.CGRectNull,
                _KCG_LIST_INCLUDING_WINDOW,
                int(window_id),
                _KCG_IMAGE_BOUNDS_IGNORE_FRAMING | _KCG_IMAGE_BEST_RESOLUTION,
            )
        else:
            x, y, w, h = rect or (0.0, 0.0, 0.0, 0.0)
            image = create(
                Quartz.CGRectMake(float(x), float(y), float(w), float(h)),
                _KCG_LIST_ON_SCREEN_ONLY,
                _KCG_NULL_WINDOW_ID,
                _KCG_IMAGE_DEFAULT,
            )
        if image is None:
            return None
        data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
        return {
            "width": int(Quartz.CGImageGetWidth(image)),
            "height": int(Quartz.CGImageGetHeight(image)),
            "bytes_per_row": int(Quartz.CGImageGetBytesPerRow(image)),
            "bits_per_pixel": int(Quartz.CGImageGetBitsPerPixel(image)),
            "bitmap_info": int(Quartz.CGImageGetBitmapInfo(image)),
            "data": bytes(data),
            "channels": "BGRA",
            "backend": "cgwindowlist",
        }

    def capture_with_mss(self, rect: Tuple[float, float, float, float]) -> Optional[Dict[str, Any]]:
        """Alternativa con ``mss`` (usa CGWindowListCreateImage por ctypes, region en puntos)."""
        mss_module = _import("mss")
        x, y, w, h = rect
        with mss_module.mss() as grabber:
            shot = grabber.grab({
                "left": int(round(x)), "top": int(round(y)),
                "width": int(round(w)), "height": int(round(h)),
            })
            width, height = int(shot.width), int(shot.height)
            return {
                "width": width,
                "height": height,
                "bytes_per_row": width * 4,
                "bits_per_pixel": 32,
                "bitmap_info": 0,
                "data": bytes(shot.bgra),
                "channels": "BGRA",
                "backend": "mss",
            }


# ============================================================================
# UTILIDADES DE GEOMETRIA
# ============================================================================


def cocoa_rect_to_quartz(
    rect: Tuple[float, float, float, float], primary_height: float
) -> Rect:
    """Rectangulo Cocoa (origen abajo-izquierda del principal) -> Rect Quartz.

    ``y_quartz = alto_principal - (y_cocoa + alto)``; ``x`` no cambia.
    """
    x, y, w, h = [float(v) for v in rect]
    top = float(primary_height) - (y + h)
    return Rect(x, top, x + w, top + h)


def _rect_from_xywh(value: Optional[Sequence[float]]) -> Optional[Rect]:
    if not value:
        return None
    try:
        x, y, w, h = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return Rect(x, y, x + w, y + h)


def _rect_distance(a: Rect, b: Rect) -> float:
    return (
        abs(a.left - b.left) + abs(a.top - b.top)
        + abs(a.right - b.right) + abs(a.bottom - b.bottom)
    )


# ============================================================================
# ADAPTADOR macOS
# ============================================================================


class MacOSDesktopAdapter(DesktopPlatformAdapter):
    """Implementacion macOS del contrato de escritorio (a ciegas, regla 3).

    Argumentos:
        boundary: frontera nativa (por defecto ``MacNativeBoundary``). Los tests
            de contrato la sustituyen por una sintetica.
        poll_timeout: limite (s) para comprobar efectos asincronos del SO
            (puntero, activacion, geometria); se sondea, no se duerme a ciegas.
        poll_interval: intervalo entre sondeos.
        tree_timeout: limite (s) para recorrer un arbol AX.
        window_match_tolerance: tolerancia (puntos) al emparejar una ventana AX
            con su entrada de CGWindowList.
    """

    platform_name = PLATFORM_MACOS
    desktop_space = DESKTOP_POINTS

    def __init__(
        self,
        boundary: Optional[MacNativeBoundary] = None,
        poll_timeout: float = 1.5,
        poll_interval: float = 0.03,
        tree_timeout: float = 15.0,
        window_match_tolerance: float = 4.0,
    ) -> None:
        self.boundary = boundary if boundary is not None else MacNativeBoundary()
        self.poll_timeout = float(poll_timeout)
        self.poll_interval = float(poll_interval)
        self.tree_timeout = float(tree_timeout)
        self.window_match_tolerance = float(window_match_tolerance)
        # Frame previo a mover/maximizar, por window_id, para restore_window.
        self._saved_frames: Dict[int, Rect] = {}
        # node_id -> manejador AX del ultimo arbol leido de cada ventana.
        self._node_handles: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _dependency_error(self, operation: str, exc: Exception) -> PlatformResult[Any]:
        return self._fail(
            operation,
            PlatformErrorCode.DEPENDENCY_MISSING,
            "Dependencia nativa macOS no disponible",
            native_error=exc,
            instructions=_INSTR_PYOBJC,
        )

    def _native_error(self, operation: str, exc: Exception) -> PlatformResult[Any]:
        if isinstance(exc, NativeDependencyUnavailable):
            return self._dependency_error(operation, exc)
        if isinstance(exc, PermissionError):
            return self._fail(
                operation,
                PlatformErrorCode.PERMISSION_DENIED,
                "Permiso de Accesibilidad no concedido",
                native_error=exc,
                instructions=_INSTR_ACCESSIBILITY,
            )
        logger.warning("macOS %s fallo: %s", operation, exc)
        return self._fail(operation, PlatformErrorCode.NATIVE_ERROR, "Error nativo macOS", native_error=exc)

    def _ax_error(self, operation: str, code: int, what: str) -> PlatformResult[Any]:
        if code == AX_ERROR_API_DISABLED:
            return self._fail(
                operation, PlatformErrorCode.PERMISSION_DENIED,
                "Permiso de Accesibilidad no concedido (%s)" % what,
                native_error="AXError %d" % code, instructions=_INSTR_ACCESSIBILITY,
            )
        if code == AX_ERROR_INVALID_UI_ELEMENT:
            return self._fail(operation, PlatformErrorCode.WINDOW_GONE,
                              "El elemento AX ya no existe (%s)" % what, native_error="AXError %d" % code)
        if code in (AX_ERROR_ACTION_UNSUPPORTED, AX_ERROR_ATTRIBUTE_UNSUPPORTED, AX_ERROR_NOT_IMPLEMENTED):
            return self._fail(operation, PlatformErrorCode.NOT_SUPPORTED,
                              "Operacion AX no soportada por el elemento (%s)" % what,
                              native_error="AXError %d" % code)
        if code == AX_ERROR_CANNOT_COMPLETE:
            return self._fail(operation, PlatformErrorCode.TIMEOUT,
                              "La aplicacion no respondio a AX (%s)" % what, native_error="AXError %d" % code)
        return self._fail(operation, PlatformErrorCode.NATIVE_ERROR,
                          "Fallo AX (%s)" % what, native_error="AXError %d" % code)

    def _poll(self, predicate: Callable[[], bool], timeout: Optional[float] = None) -> bool:
        """Sondea ``predicate`` hasta que sea cierto o venza el limite."""
        deadline = time.monotonic() + (self.poll_timeout if timeout is None else float(timeout))
        while True:
            try:
                if predicate():
                    return True
            except Exception as exc:
                logger.debug("sondeo macOS: %s", exc)
            if time.monotonic() >= deadline:
                return False
            time.sleep(self.poll_interval)

    def _ax_trusted(self) -> Optional[bool]:
        try:
            return self.boundary.ax_is_trusted()
        except NativeDependencyUnavailable:
            return None
        except Exception as exc:
            logger.debug("AXIsProcessTrusted: %s", exc)
            return None

    def _screen_capture_granted(self) -> Optional[bool]:
        try:
            return self.boundary.screen_capture_access()
        except NativeDependencyUnavailable:
            return None
        except Exception as exc:
            logger.debug("CGPreflightScreenCaptureAccess: %s", exc)
            return None

    def _require_accessibility(self, operation: str) -> Optional[PlatformResult[Any]]:
        trusted = self._ax_trusted()
        if trusted is None:
            return self._fail(operation, PlatformErrorCode.DEPENDENCY_MISSING,
                              "No se puede usar AX: pyobjc ApplicationServices no disponible",
                              instructions=_INSTR_PYOBJC)
        if not trusted:
            return self._fail(operation, PlatformErrorCode.PERMISSION_DENIED,
                              "Permiso de Accesibilidad no concedido a la app anfitriona",
                              instructions=_INSTR_ACCESSIBILITY)
        return None

    def _require_screen_capture(self, operation: str) -> Tuple[Optional[PlatformResult[Any]], Optional[bool]]:
        granted = self._screen_capture_granted()
        if granted is False:
            return (
                self._fail(operation, PlatformErrorCode.PERMISSION_DENIED,
                           "Permiso de Grabacion de pantalla no concedido a la app anfitriona",
                           instructions=_INSTR_SCREEN_RECORDING),
                granted,
            )
        return None, granted

    # ------------------------------------------------------------------
    # Capacidades y permisos
    # ------------------------------------------------------------------

    def _note(self, detail: str) -> str:
        if MACOS_REAL_VERIFICATION:
            return detail
        return ("%s (%s)" % (detail, _UNVERIFIED_NOTE)) if detail else _UNVERIFIED_NOTE

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        try:
            deps = self.boundary.dependencies()
        except Exception as exc:
            logger.debug("dependencies(): %s", exc)
            deps = {}
        appkit_ok = deps.get("AppKit", "x") is None
        quartz_ok = deps.get("Quartz", "x") is None
        ax_ok = deps.get("ApplicationServices", "x") is None
        mss_ok = deps.get("mss", "x") is None
        trusted = self._ax_trusted() if ax_ok else None
        capture = self._screen_capture_granted() if quartz_ok else None

        def report(cap: Capability, status: CapabilityStatus, detail: str,
                   instructions: str = "", backend: str = "") -> CapabilityReport:
            return CapabilityReport(cap, status, self._note(detail), instructions, backend)

        missing = CapabilityStatus.NO_SOPORTADO
        reports: Dict[Capability, CapabilityReport] = {}

        for cap in (Capability.DISCOVER, Capability.RESOLVE, Capability.PREFLIGHT, Capability.LAUNCH):
            reports[cap] = report(
                cap, CapabilityStatus.NO_SOPORTADO,
                "La declara el adaptador de lanzamiento macOS (src/hands/apps/launch_macos.py)",
            )

        if appkit_ok and quartz_ok:
            reports[Capability.DISPLAY_ENUM] = report(
                Capability.DISPLAY_ENUM, CapabilityStatus.DISPONIBLE, "NSScreen + CGDisplay", backend="appkit+quartz")
            reports[Capability.WINDOW_VERIFY] = report(
                Capability.WINDOW_VERIFY, CapabilityStatus.DISPONIBLE,
                "CGWindowListCopyWindowInfo (titulos solo con Grabacion de pantalla)", backend="cgwindowlist")
        else:
            for cap in (Capability.DISPLAY_ENUM, Capability.WINDOW_VERIFY):
                reports[cap] = report(cap, missing, "Faltan AppKit/Quartz de pyobjc", _INSTR_PYOBJC)

        reports[Capability.PROCESS_VERIFY] = report(
            Capability.PROCESS_VERIFY,
            CapabilityStatus.DISPONIBLE if appkit_ok else CapabilityStatus.NO_VERIFICADO,
            "NSRunningApplication + psutil" if appkit_ok else "Solo psutil (falta AppKit)",
            "" if appkit_ok else _INSTR_PYOBJC, backend="nsrunningapplication" if appkit_ok else "psutil",
        )

        def ax_based(cap: Capability, detail: str, backend: str) -> CapabilityReport:
            if not ax_ok or not quartz_ok:
                return report(cap, missing, "Faltan ApplicationServices/Quartz de pyobjc", _INSTR_PYOBJC)
            if trusted is False:
                return report(cap, CapabilityStatus.SIN_PERMISO,
                              "Permiso de Accesibilidad no concedido", _INSTR_ACCESSIBILITY, backend)
            if trusted is None:
                return report(cap, CapabilityStatus.NO_VERIFICADO, "No se pudo consultar AXIsProcessTrusted", backend=backend)
            return report(cap, CapabilityStatus.DISPONIBLE, detail, backend=backend)

        reports[Capability.WINDOW_CONTROL] = ax_based(
            Capability.WINDOW_CONTROL, "AXUIElement (posicion/tamano/AXRaise) + NSRunningApplication", "ax")
        reports[Capability.INPUT_CONTROL] = ax_based(
            Capability.INPUT_CONTROL, "CGEventPost en puntos (Cmd = primary_modifier)", "cgevent")
        reports[Capability.ACCESSIBILITY_TREE] = ax_based(
            Capability.ACCESSIBILITY_TREE, "AXUIElement normalizado", "ax")

        if quartz_ok:
            if capture is False:
                reports[Capability.SCREEN_CAPTURE] = report(
                    Capability.SCREEN_CAPTURE, CapabilityStatus.SIN_PERMISO,
                    "Permiso de Grabacion de pantalla no concedido", _INSTR_SCREEN_RECORDING, "cgwindowlist")
            elif capture is None:
                reports[Capability.SCREEN_CAPTURE] = report(
                    Capability.SCREEN_CAPTURE, CapabilityStatus.NO_VERIFICADO,
                    "CGPreflightScreenCaptureAccess no disponible", backend="cgwindowlist")
            else:
                reports[Capability.SCREEN_CAPTURE] = report(
                    Capability.SCREEN_CAPTURE, CapabilityStatus.DISPONIBLE,
                    "CGWindowListCreateImage", backend="cgwindowlist")
        elif mss_ok:
            reports[Capability.SCREEN_CAPTURE] = report(
                Capability.SCREEN_CAPTURE, CapabilityStatus.NO_VERIFICADO,
                "Solo mss: sin pyobjc no se puede comprobar el permiso de Grabacion de pantalla",
                _INSTR_PYOBJC, "mss")
        else:
            reports[Capability.SCREEN_CAPTURE] = report(
                Capability.SCREEN_CAPTURE, missing, "Faltan Quartz y mss", _INSTR_PYOBJC)

        mic = self._microphone_status()
        reports[Capability.AUDIO_INPUT] = report(
            Capability.AUDIO_INPUT, mic.status, mic.detail, mic.instructions, "sounddevice")
        return reports

    def _microphone_status(self) -> PermissionStatus:
        try:
            status = self.boundary.microphone_authorization()
        except NativeDependencyUnavailable:
            return PermissionStatus(
                PermissionKind.MICROPHONE, CapabilityStatus.NO_VERIFICADO,
                "AVFoundation no instalado: el permiso se solicita al primer uso del microfono",
                _INSTR_MICROPHONE)
        except Exception as exc:
            return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.NO_VERIFICADO,
                                    "No se pudo consultar el permiso de microfono: %s" % exc, _INSTR_MICROPHONE)
        if status == _AV_AUTHORIZED:
            return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.DISPONIBLE, "Microfono autorizado")
        if status in (_AV_DENIED, _AV_RESTRICTED):
            return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.SIN_PERMISO,
                                    "Microfono denegado o restringido", _INSTR_MICROPHONE)
        return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.NO_VERIFICADO,
                                "Permiso de microfono aun no solicitado", _INSTR_MICROPHONE)

    def check_permissions(self) -> List[PermissionStatus]:
        result: List[PermissionStatus] = []
        trusted = self._ax_trusted()
        if trusted is None:
            ax = PermissionStatus(PermissionKind.ACCESSIBILITY, CapabilityStatus.NO_VERIFICADO,
                                  "No se pudo consultar AXIsProcessTrusted (pyobjc ausente)", _INSTR_PYOBJC)
        elif trusted:
            ax = PermissionStatus(PermissionKind.ACCESSIBILITY, CapabilityStatus.DISPONIBLE,
                                  "Accesibilidad concedida a la app anfitriona")
        else:
            ax = PermissionStatus(PermissionKind.ACCESSIBILITY, CapabilityStatus.SIN_PERMISO,
                                  "Accesibilidad no concedida a la app anfitriona", _INSTR_ACCESSIBILITY)
        result.append(ax)
        result.append(PermissionStatus(
            PermissionKind.INPUT_INJECTION, ax.status,
            "CGEventPost exige el permiso de Accesibilidad", ax.instructions))
        capture = self._screen_capture_granted()
        if capture is None:
            result.append(PermissionStatus(PermissionKind.SCREEN_RECORDING, CapabilityStatus.NO_VERIFICADO,
                                           "No se pudo consultar CGPreflightScreenCaptureAccess",
                                           _INSTR_SCREEN_RECORDING))
        elif capture:
            result.append(PermissionStatus(PermissionKind.SCREEN_RECORDING, CapabilityStatus.DISPONIBLE,
                                           "Grabacion de pantalla concedida"))
        else:
            result.append(PermissionStatus(PermissionKind.SCREEN_RECORDING, CapabilityStatus.SIN_PERMISO,
                                           "Grabacion de pantalla no concedida", _INSTR_SCREEN_RECORDING))
        result.append(self._microphone_status())
        result.append(PermissionStatus(
            PermissionKind.AUTOMATION, CapabilityStatus.NO_VERIFICADO,
            "JARVIS no usa Apple Events/osascript; permiso no requerido por este adaptador"))
        return result

    # ------------------------------------------------------------------
    # Monitores
    # ------------------------------------------------------------------

    def _display_from_screen(self, entry: Dict[str, Any], primary_height: float, index: int) -> Optional[DisplayInfo]:
        scale = float(entry.get("backing_scale") or 1.0)
        if scale <= 0:
            scale = 1.0
        bounds = _rect_from_xywh(entry.get("quartz_bounds"))
        if bounds is None:
            frame = entry.get("frame")
            if not frame:
                return None
            bounds = cocoa_rect_to_quartz(frame, primary_height)
        visible = entry.get("visible_frame")
        work_area = cocoa_rect_to_quartz(visible, primary_height) if visible else bounds
        # Contener el area util dentro del monitor (proteccion ante datos incoherentes).
        work_area = work_area.intersection(bounds) or bounds
        rotation = int(round(float(entry.get("rotation") or 0.0))) % 360
        display_id = str(int(entry.get("display_id") or 0))
        is_main = entry.get("is_main")
        is_primary = bool(is_main) if is_main is not None else index == 0
        extra: Dict[str, Any] = {
            "backing_scale": scale,
            "screen_index": entry.get("index", index),
            "is_builtin": bool(entry.get("is_builtin")) if entry.get("is_builtin") is not None else None,
        }
        for key in ("vendor", "model", "serial", "mode_pixel_width", "mode_pixel_height",
                    "mode_width", "mode_height"):
            if entry.get(key) is not None:
                extra[key] = entry.get(key)
        if all(entry.get(k) is not None for k in ("vendor", "model", "serial")):
            # Identidad estable entre reinicios (el CGDirectDisplayID puede cambiar).
            extra["stable_key"] = "%s-%s-%s" % (entry["vendor"], entry["model"], entry["serial"])
        pixel_width = int(round(bounds.width * scale))
        pixel_height = int(round(bounds.height * scale))
        size_mm = entry.get("size_mm")
        if size_mm and float(size_mm[0]) > 0:
            native_width = entry.get("mode_pixel_width") or pixel_width
            extra["physical_dpi"] = round(float(native_width) / (float(size_mm[0]) / 25.4), 1)
        refresh = entry.get("refresh_rate")
        return DisplayInfo(
            display_id=display_id,
            name=str(entry.get("name") or "Pantalla %s" % display_id),
            bounds=bounds,
            work_area=work_area,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            scale_factor=scale,
            dpi=int(round(72.0 * scale)),
            is_primary=is_primary,
            rotation=rotation,
            refresh_rate=float(refresh) if refresh else None,
            coordinate_space=DESKTOP_POINTS,
            native_handle=int(entry.get("display_id") or 0),
            extra=extra,
        )

    def enumerate_displays(self) -> PlatformResult[List[DisplayInfo]]:
        operation = "enumerate_displays"
        try:
            screens = self.boundary.screens()
        except Exception as exc:
            return self._native_error(operation, exc)
        if not screens:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND, "NSScreen no devolvio monitores")
        frame0 = screens[0].get("frame") or (0.0, 0.0, 0.0, 0.0)
        primary_height = float(frame0[3])
        displays: List[DisplayInfo] = []
        for index, entry in enumerate(screens):
            display = self._display_from_screen(entry, primary_height, index)
            if display is not None:
                displays.append(display)
        if not displays:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND, "Ningun monitor con geometria valida")
        if not any(d.is_primary for d in displays):
            displays[0].is_primary = True
        displays.sort(key=lambda d: (not d.is_primary, d.bounds.top, d.bounds.left, d.display_id))
        return PlatformResult.success(displays, count=len(displays))

    def start_display_change_listener(self, callback: Callable[[str], None]) -> PlatformResult[Any]:
        return self._unsupported(
            "start_display_change_listener",
            "macOS: sin notificaciones verificables (NSApplicationDidChangeScreenParametersNotification "
            "requiere un run loop propio); comparar el fingerprint de topologia antes de cada accion espacial",
        )

    def stop_display_change_listener(self, handle: Any) -> PlatformResult[None]:
        return self._unsupported("stop_display_change_listener")

    def _displays_or_empty(self) -> List[DisplayInfo]:
        result = self.enumerate_displays()
        return list(result.value or []) if result.ok else []

    @staticmethod
    def _display_for_rect(displays: Sequence[DisplayInfo], rect: Optional[Rect]) -> Optional[DisplayInfo]:
        if rect is None or not displays:
            return None
        best: Optional[DisplayInfo] = None
        best_area = 0.0
        for display in displays:
            area = display.bounds.intersection_area(rect)
            if area > best_area:
                best, best_area = display, area
        if best is None:
            cx, cy = rect.center
            for display in displays:
                if display.bounds.contains_point(cx, cy):
                    return display
        return best

    @staticmethod
    def _display_for_point(displays: Sequence[DisplayInfo], x: float, y: float) -> Optional[DisplayInfo]:
        for display in displays:
            if display.bounds.contains_point(x, y):
                return display
        return None

    # ------------------------------------------------------------------
    # Ventanas
    # ------------------------------------------------------------------

    @staticmethod
    def _is_maximized(bounds: Optional[Rect], display: Optional[DisplayInfo]) -> bool:
        """Frame contenido en el area util y cubriendola salvo un margen (3% o 2 pt).

        Las apps con incrementos de tamano (por ejemplo, terminales por celdas)
        no rellenan exactamente ``visibleFrame``; por eso se admite el margen.
        """
        if bounds is None or display is None:
            return False
        work = display.work_area
        slack = 1.0
        inside = (
            bounds.left >= work.left - slack and bounds.top >= work.top - slack
            and bounds.right <= work.right + slack and bounds.bottom <= work.bottom + slack
        )
        if not inside:
            return False
        tol_w = max(2.0, work.width * 0.03)
        tol_h = max(2.0, work.height * 0.03)
        return bounds.width >= work.width - tol_w and bounds.height >= work.height - tol_h

    def _app_info(self, pid: int) -> Optional[Dict[str, Any]]:
        try:
            return self.boundary.running_application(pid)
        except Exception as exc:
            logger.debug("running_application(%s): %s", pid, exc)
            return None

    def _frontmost_pid(self) -> Optional[int]:
        try:
            front = self.boundary.frontmost_application()
        except Exception as exc:
            logger.debug("frontmost_application: %s", exc)
            return None
        return int(front["pid"]) if front else None

    def _front_window_id_for_pid(self, entries: Sequence[Dict[str, Any]], pid: int) -> Optional[int]:
        for entry in entries:
            if entry.get("pid") == pid and int(entry.get("layer", 0)) == 0 and entry.get("onscreen", True) \
                    and float(entry.get("alpha", 1.0)) > 0:
                return int(entry["window_id"])
        return None

    def _window_info_from_entry(
        self,
        entry: Dict[str, Any],
        displays: Sequence[DisplayInfo],
        frontmost_pid: Optional[int],
        front_window_id: Optional[int],
        app: Optional[Dict[str, Any]] = None,
        ax_window: Optional[Dict[str, Any]] = None,
    ) -> WindowInfo:
        bounds = _rect_from_xywh(entry.get("bounds"))
        display = self._display_for_rect(displays, bounds)
        onscreen = bool(entry.get("onscreen", False))
        hidden_app = bool(app.get("hidden")) if app else False
        minimized = bool(ax_window.get("minimized")) if ax_window else (not onscreen)
        title = str(entry.get("title") or "") or (str(ax_window.get("title") or "") if ax_window else "")
        identity = ""
        if app:
            identity = str(app.get("bundle_id") or app.get("name") or "")
        if not identity:
            identity = str(entry.get("owner_name") or "")
        window_id = int(entry.get("window_id") or 0)
        extra: Dict[str, Any] = {
            "layer": int(entry.get("layer", 0)),
            "alpha": float(entry.get("alpha", 1.0)),
            "z_index": entry.get("z_index"),
            "owner_name": str(entry.get("owner_name") or ""),
            "sharing_state": entry.get("sharing_state"),
            "client_area": "frame_includes_titlebar",
            "minimized_source": "ax" if ax_window else "cg_offscreen",
        }
        if ax_window:
            extra["ax_fullscreen"] = bool(ax_window.get("fullscreen"))
            extra["ax_main"] = bool(ax_window.get("main"))
        return WindowInfo(
            window_id=window_id,
            pid=int(entry.get("pid") or 0),
            title=title,
            app_identity=identity,
            bounds=bounds,
            client_bounds=bounds,
            frame_bounds=bounds,
            is_visible=onscreen and not hidden_app and float(entry.get("alpha", 1.0)) > 0 and not minimized,
            is_minimized=minimized,
            is_maximized=self._is_maximized(bounds, display) and not minimized,
            is_foreground=(
                frontmost_pid is not None and int(entry.get("pid") or 0) == frontmost_pid
                and front_window_id == window_id
            ),
            display_id=display.display_id if display else None,
            scale_factor=display.scale_factor if display else None,
            dpi=display.dpi if display else None,
            dpi_awareness=None,
            coordinate_space=DESKTOP_POINTS,
            extra=extra,
        )

    def list_windows(
        self,
        pid: Optional[int] = None,
        app_identity: Optional[str] = None,
        visible_only: bool = True,
    ) -> PlatformResult[List[WindowInfo]]:
        operation = "list_windows"
        try:
            on_screen = self.boundary.window_list("on_screen")
            entries = on_screen if visible_only else self.boundary.window_list("all")
        except Exception as exc:
            return self._native_error(operation, exc)
        displays = self._displays_or_empty()
        frontmost = self._frontmost_pid()
        front_window = self._front_window_id_for_pid(on_screen, frontmost) if frontmost is not None else None
        identity_l = (app_identity or "").strip().lower()
        apps: Dict[int, Optional[Dict[str, Any]]] = {}
        windows: List[WindowInfo] = []
        for entry in entries:
            if int(entry.get("layer", 0)) != 0:
                continue  # solo ventanas normales de aplicacion
            entry_pid = int(entry.get("pid") or 0)
            if pid is not None and entry_pid != int(pid):
                continue
            if entry_pid not in apps:
                apps[entry_pid] = self._app_info(entry_pid)
            app = apps[entry_pid]
            if identity_l:
                candidates = {str(entry.get("owner_name") or "").lower()}
                if app:
                    candidates.add(str(app.get("bundle_id") or "").lower())
                    candidates.add(str(app.get("name") or "").lower())
                    candidates.add(str(app.get("executable_name") or "").lower())
                if identity_l not in candidates:
                    continue
            info = self._window_info_from_entry(entry, displays, frontmost, front_window, app)
            if visible_only and not info.is_visible:
                continue
            windows.append(info)
        return PlatformResult.success(windows, count=len(windows))

    def _window_entry(self, window_id: int) -> Optional[Dict[str, Any]]:
        entries = self.boundary.window_list("single", window_id=int(window_id))
        for entry in entries:
            if int(entry.get("window_id") or 0) == int(window_id):
                return entry
        return None

    def _match_ax_window(self, pid: int, bounds: Optional[Rect], title: str = "") -> Optional[Dict[str, Any]]:
        """Empareja la ventana CG con su ventana AX por PID + geometria (+ titulo)."""
        windows = self.boundary.ax_application_windows(pid)
        if not windows:
            return None
        best: Optional[Dict[str, Any]] = None
        best_score: Optional[float] = None
        for window in windows:
            rect = None
            if window.get("position") and window.get("size"):
                (x, y), (w, h) = window["position"], window["size"]
                rect = _rect_from_xywh((x, y, w, h))
            if rect is None or bounds is None:
                continue
            score = _rect_distance(rect, bounds)
            if title and str(window.get("title") or "") == title:
                score -= 0.5  # desempate por titulo identico
            if best_score is None or score < best_score:
                best, best_score = window, score
        if best is None or best_score is None or best_score > self.window_match_tolerance * 4:
            if len(windows) == 1 and bounds is None:
                return windows[0]
            return None
        return best

    def get_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        operation = "get_window"
        try:
            entry = self._window_entry(window_id)
        except Exception as exc:
            return self._native_error(operation, exc)
        if entry is None:
            return self._fail(operation, PlatformErrorCode.WINDOW_GONE,
                              "La ventana %s no existe" % window_id, window_id=window_id)
        pid = int(entry.get("pid") or 0)
        displays = self._displays_or_empty()
        frontmost = self._frontmost_pid()
        front_window = None
        if frontmost is not None:
            try:
                front_window = self._front_window_id_for_pid(self.boundary.window_list("on_screen"), frontmost)
            except Exception as exc:
                logger.debug("window_list para primer plano: %s", exc)
        ax_window = None
        if self._ax_trusted():
            try:
                ax_window = self._match_ax_window(pid, _rect_from_xywh(entry.get("bounds")), str(entry.get("title") or ""))
            except Exception as exc:
                logger.debug("_match_ax_window(%s): %s", window_id, exc)
        info = self._window_info_from_entry(entry, displays, frontmost, front_window, self._app_info(pid), ax_window)
        return PlatformResult.success(info)

    def get_foreground_window(self) -> PlatformResult[Optional[WindowInfo]]:
        operation = "get_foreground_window"
        frontmost = self._frontmost_pid()
        if frontmost is None:
            return PlatformResult.success(None, reason="sin aplicacion en primer plano")
        try:
            entries = self.boundary.window_list("on_screen")
        except Exception as exc:
            return self._native_error(operation, exc)
        front_window = self._front_window_id_for_pid(entries, frontmost)
        if front_window is None:
            return PlatformResult.success(None, reason="la aplicacion activa no tiene ventanas visibles",
                                          frontmost_pid=frontmost)
        entry = next(e for e in entries if int(e.get("window_id") or 0) == front_window)
        info = self._window_info_from_entry(
            entry, self._displays_or_empty(), frontmost, front_window, self._app_info(frontmost))
        return PlatformResult.success(info)

    def window_at_point(self, x: float, y: float) -> PlatformResult[Optional[WindowInfo]]:
        """Ventana mas al frente que contiene el punto (incluidas capas superiores)."""
        operation = "window_at_point"
        try:
            entries = self.boundary.window_list("on_screen")
        except Exception as exc:
            return self._native_error(operation, exc)
        frontmost = self._frontmost_pid()
        front_window = self._front_window_id_for_pid(entries, frontmost) if frontmost is not None else None
        for entry in entries:
            if float(entry.get("alpha", 1.0)) <= 0:
                continue
            rect = _rect_from_xywh(entry.get("bounds"))
            if rect is not None and rect.contains_point(float(x), float(y)):
                pid = int(entry.get("pid") or 0)
                info = self._window_info_from_entry(
                    entry, self._displays_or_empty(), frontmost, front_window, self._app_info(pid))
                return PlatformResult.success(info)
        return PlatformResult.success(None)

    def _ax_window_for(self, operation: str, window_id: int) -> Tuple[Optional[PlatformResult[Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Devuelve (error, entrada CG, ventana AX) para operaciones de control."""
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied, None, None
        try:
            entry = self._window_entry(window_id)
        except Exception as exc:
            return self._native_error(operation, exc), None, None
        if entry is None:
            return (self._fail(operation, PlatformErrorCode.WINDOW_GONE,
                               "La ventana %s no existe" % window_id, window_id=window_id), None, None)
        try:
            ax_window = self._match_ax_window(
                int(entry.get("pid") or 0), _rect_from_xywh(entry.get("bounds")), str(entry.get("title") or ""))
        except Exception as exc:
            return self._native_error(operation, exc), entry, None
        if ax_window is None:
            return (self._fail(operation, PlatformErrorCode.NOT_FOUND,
                               "No se encontro la ventana AX correspondiente (PID + geometria)",
                               window_id=window_id), entry, None)
        return None, entry, ax_window

    def _set_frame(self, operation: str, handle: Any, rect: Rect) -> Optional[PlatformResult[Any]]:
        """Posicion, tamano y de nuevo posicion (el tamano puede limitarse por el monitor previo)."""
        for step, call in (
            ("posicion", lambda: self.boundary.ax_set_position(handle, rect.left, rect.top)),
            ("tamano", lambda: self.boundary.ax_set_size(handle, rect.width, rect.height)),
            ("posicion", lambda: self.boundary.ax_set_position(handle, rect.left, rect.top)),
        ):
            try:
                code = int(call())
            except Exception as exc:
                return self._native_error(operation, exc)
            if code != AX_ERROR_SUCCESS:
                return self._ax_error(operation, code, step)
        return None

    def _remember_frame(self, window_id: int, entry: Dict[str, Any]) -> None:
        if window_id not in self._saved_frames:
            rect = _rect_from_xywh(entry.get("bounds"))
            if rect is not None:
                self._saved_frames[window_id] = rect

    def _wait_bounds(self, window_id: int, predicate: Callable[[WindowInfo], bool]) -> Optional[WindowInfo]:
        holder: Dict[str, WindowInfo] = {}

        def check() -> bool:
            result = self.get_window(window_id)
            if not result.ok or result.value is None:
                return False
            holder["info"] = result.value
            return predicate(result.value)

        ok = self._poll(check)
        info = holder.get("info")
        return info

    def move_window_to_display(self, window_id: int, display_id: str) -> PlatformResult[WindowInfo]:
        operation = "move_window_to_display"
        displays = self._displays_or_empty()
        target = next((d for d in displays if d.display_id == str(display_id)), None)
        if target is None:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND,
                              "Monitor %s no encontrado en la topologia actual" % display_id)
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        if ax_window.get("fullscreen"):
            return self._fail(operation, PlatformErrorCode.PROTECTED,
                              "La ventana esta en pantalla completa nativa (otro Space); no se modifica")
        current = _rect_from_xywh(entry.get("bounds"))
        work = target.work_area
        width = min(current.width if current else work.width, work.width)
        height = min(current.height if current else work.height, work.height)
        new_rect = Rect(work.left, work.top, work.left + width, work.top + height)
        self._remember_frame(window_id, entry)
        failed = self._set_frame(operation, ax_window["handle"], new_rect)
        if failed is not None:
            return failed
        info = self._wait_bounds(window_id, lambda w: w.display_id == target.display_id)
        if info is None or info.display_id != target.display_id:
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "La ventana no quedo en el monitor %s" % display_id,
                              actual_display=info.display_id if info else None)
        return PlatformResult.success(info, display_id=target.display_id)

    def maximize_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        """Ajusta el frame a ``visibleFrame`` del monitor actual via AX y lo verifica."""
        operation = "maximize_window"
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        if ax_window.get("fullscreen"):
            return self._fail(operation, PlatformErrorCode.PROTECTED,
                              "La ventana esta en pantalla completa nativa (otro Space); no se sale automaticamente")
        handle = ax_window["handle"]
        if ax_window.get("minimized"):
            try:
                code = int(self.boundary.ax_set_bool(handle, "AXMinimized", False))
            except Exception as exc:
                return self._native_error(operation, exc)
            if code != AX_ERROR_SUCCESS:
                return self._ax_error(operation, code, "AXMinimized")
        displays = self._displays_or_empty()
        display = self._display_for_rect(displays, _rect_from_xywh(entry.get("bounds")))
        if display is None:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND, "No se pudo determinar el monitor de la ventana")
        self._remember_frame(window_id, entry)
        failed = self._set_frame(operation, handle, display.work_area)
        if failed is not None:
            return failed
        info = self._wait_bounds(window_id, lambda w: self._is_maximized(w.bounds, display))
        if info is None or not self._is_maximized(info.bounds, display):
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "La ventana no ocupa el area util del monitor tras ajustar su frame",
                              expected=display.work_area.to_dict(),
                              actual=info.bounds.to_dict() if info and info.bounds else None)
        info.is_maximized = True
        return PlatformResult.success(info, display_id=display.display_id)

    def restore_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        """Desminimiza y, si este adaptador la movio o maximizo, restaura su frame previo."""
        operation = "restore_window"
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        handle = ax_window["handle"]
        if ax_window.get("minimized"):
            try:
                code = int(self.boundary.ax_set_bool(handle, "AXMinimized", False))
            except Exception as exc:
                return self._native_error(operation, exc)
            if code != AX_ERROR_SUCCESS:
                return self._ax_error(operation, code, "AXMinimized")
        saved = self._saved_frames.get(window_id)
        if saved is not None:
            failed = self._set_frame(operation, handle, saved)
            if failed is not None:
                return failed
            self._saved_frames.pop(window_id, None)
        info = self._wait_bounds(
            window_id, lambda w: not w.is_minimized and (saved is None or (w.bounds is not None and _rect_distance(w.bounds, saved) <= 4.0)))
        if info is None:
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED, "No se pudo leer la ventana restaurada")
        return PlatformResult.success(info, restored_frame=saved.to_dict() if saved else None)

    def set_window_bounds(self, window_id: int, bounds: Rect) -> PlatformResult[WindowInfo]:
        operation = "set_window_bounds"
        if not isinstance(bounds, Rect) or not bounds.is_valid():
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Rectangulo invalido")
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        self._remember_frame(window_id, entry)
        failed = self._set_frame(operation, ax_window["handle"], bounds)
        if failed is not None:
            return failed
        info = self._wait_bounds(window_id, lambda w: w.bounds is not None and _rect_distance(w.bounds, bounds) <= 4.0)
        if info is None or info.bounds is None or _rect_distance(info.bounds, bounds) > 4.0:
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "La geometria aplicada no coincide con la pedida",
                              expected=bounds.to_dict(), actual=info.bounds.to_dict() if info and info.bounds else None)
        return PlatformResult.success(info)

    def activate_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        """``activateWithOptions_`` + ``AXFrontmost`` + ``AXRaise``/``AXMain``; verifica el frente."""
        operation = "activate_window"
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        pid = int(entry.get("pid") or 0)
        handle = ax_window["handle"]
        try:
            if ax_window.get("minimized"):
                self.boundary.ax_set_bool(handle, "AXMinimized", False)
            self.boundary.activate_application(pid)
            self.boundary.ax_set_app_frontmost(pid)
            raise_code = int(self.boundary.ax_perform_action(handle, "AXRaise"))
            self.boundary.ax_set_bool(handle, "AXMain", True)
        except Exception as exc:
            return self._native_error(operation, exc)
        if raise_code not in (AX_ERROR_SUCCESS, AX_ERROR_ACTION_UNSUPPORTED):
            return self._ax_error(operation, raise_code, "AXRaise")

        def is_front() -> bool:
            if self._frontmost_pid() != pid:
                return False
            return self._front_window_id_for_pid(self.boundary.window_list("on_screen"), pid) == int(window_id)

        if not self._poll(is_front):
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "La ventana no quedo en primer plano (activacion cooperativa denegada o ventana tapada)",
                              frontmost_pid=self._frontmost_pid())
        result = self.get_window(window_id)
        if not result.ok:
            return result
        result.value.is_foreground = True
        return result

    def is_foreground(self, window_id: int) -> bool:
        result = self.get_foreground_window()
        return bool(result.ok and result.value is not None and result.value.window_id == int(window_id))

    def get_window_dpi_info(self, window_id: int) -> PlatformResult[WindowDpiInfo]:
        operation = "get_window_dpi_info"
        result = self.get_window(window_id)
        if not result.ok:
            return PlatformResult.from_error(result.error)
        window = result.value
        displays = self._displays_or_empty()
        display = next((d for d in displays if d.display_id == window.display_id), None)
        if display is None:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND, "Monitor de la ventana no encontrado")
        info = WindowDpiInfo(
            window_id=int(window_id),
            dpi=display.dpi,
            scale_factor=display.scale_factor,
            window_awareness=None,
            process_awareness=None,
            jarvis_awareness=None,
            display_id=display.display_id,
            details={
                "note": "macOS no tiene DPI awareness: entrada en puntos, captura en pixeles (backingScaleFactor)",
                "physical_dpi": display.extra.get("physical_dpi"),
            },
        )
        return PlatformResult.success(info)

    def close_window(self, window_id: int) -> PlatformResult[None]:
        """Pulsa el boton de cierre AX (``AXCloseButton`` + ``AXPress``). Nunca fuerza."""
        operation = "close_window"
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        try:
            button = self.boundary.ax_attribute_element(ax_window["handle"], "AXCloseButton")
            if button is None:
                return self._fail(operation, PlatformErrorCode.NOT_SUPPORTED, "La ventana no expone AXCloseButton")
            code = int(self.boundary.ax_perform_action(button, "AXPress"))
        except Exception as exc:
            return self._native_error(operation, exc)
        if code != AX_ERROR_SUCCESS:
            return self._ax_error(operation, code, "AXCloseButton")
        self._saved_frames.pop(int(window_id), None)
        self._node_handles.pop(int(window_id), None)
        return PlatformResult.success(None)

    # ------------------------------------------------------------------
    # Procesos
    # ------------------------------------------------------------------

    def process_identity(self, pid: int) -> PlatformResult[Dict[str, Any]]:
        app = self._app_info(pid)
        if app is None:
            return super().process_identity(pid)
        return PlatformResult.success({
            "pid": int(pid),
            "name": app.get("name", ""),
            "bundle_id": app.get("bundle_id", ""),
            "executable_name": app.get("executable_name", ""),
        })

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------

    def _to_capture(
        self,
        raw: Dict[str, Any],
        region: Rect,
        window_id: Optional[int],
        display_id: Optional[str],
        permission_verified: Optional[bool],
    ) -> PlatformResult[CaptureResult]:
        width, height = int(raw.get("width") or 0), int(raw.get("height") or 0)
        if width <= 0 or height <= 0:
            return self._fail("capture", PlatformErrorCode.NATIVE_ERROR, "Captura vacia")
        image = None
        try:
            import numpy as np

            row = int(raw.get("bytes_per_row") or width * 4)
            buffer = np.frombuffer(raw["data"], dtype=np.uint8)
            if buffer.size < row * height:
                return self._fail("capture", PlatformErrorCode.NATIVE_ERROR, "Buffer de captura incompleto")
            image = buffer[: row * height].reshape(height, row)[:, : width * 4].reshape(height, width, 4).copy()
        except Exception as exc:
            logger.warning("No se pudo convertir la captura a numpy: %s", exc)
        capture = CaptureResult(
            region=region,
            pixel_width=width,
            pixel_height=height,
            backend=str(raw.get("backend") or "cgwindowlist"),
            image=image,
            channels=str(raw.get("channels") or "BGRA"),
            # Escala medida (pixeles / puntos), nunca supuesta.
            pixels_per_unit_x=width / region.width if region.width > 0 else 1.0,
            pixels_per_unit_y=height / region.height if region.height > 0 else 1.0,
            captured_at=time.monotonic(),
            window_id=window_id,
            display_id=display_id,
            coordinate_space=DESKTOP_POINTS,
        )
        details: Dict[str, Any] = {}
        if permission_verified is None:
            details["warning"] = "permiso de Grabacion de pantalla no comprobable: las ventanas ajenas podrian faltar"
        return PlatformResult.success(capture, **details)

    def _capture_rect(self, operation: str, region: Rect, display_id: Optional[str]) -> PlatformResult[CaptureResult]:
        denied, granted = self._require_screen_capture(operation)
        if denied is not None:
            return denied
        xywh = (region.left, region.top, region.width, region.height)
        raw = None
        try:
            raw = self.boundary.capture_image(xywh)
        except NativeDependencyUnavailable as exc:
            logger.debug("CGWindowListCreateImage no disponible: %s", exc)
        except Exception as exc:
            logger.warning("CGWindowListCreateImage fallo: %s", exc)
        if raw is None:
            try:
                raw = self.boundary.capture_with_mss(xywh)
            except Exception as exc:
                return self._native_error(operation, exc)
        if raw is None:
            return self._fail(operation, PlatformErrorCode.NATIVE_ERROR, "No se obtuvo imagen de captura")
        return self._to_capture(raw, region, None, display_id, granted)

    def capture_display(self, display_id: str) -> PlatformResult[CaptureResult]:
        operation = "capture_display"
        display = next((d for d in self._displays_or_empty() if d.display_id == str(display_id)), None)
        if display is None:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND, "Monitor %s no encontrado" % display_id)
        return self._capture_rect(operation, display.bounds, display.display_id)

    def capture_region(self, region: Rect) -> PlatformResult[CaptureResult]:
        operation = "capture_region"
        if not isinstance(region, Rect) or not region.is_valid():
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Region invalida")
        display = self._display_for_rect(self._displays_or_empty(), region)
        return self._capture_rect(operation, region, display.display_id if display else None)

    def capture_window(self, window_id: int) -> PlatformResult[CaptureResult]:
        """Captura solo la ventana indicada (``kCGWindowListOptionIncludingWindow``, sin sombra)."""
        operation = "capture_window"
        denied, granted = self._require_screen_capture(operation)
        if denied is not None:
            return denied
        result = self.get_window(window_id)
        if not result.ok:
            return PlatformResult.from_error(result.error)
        window = result.value
        if window.is_minimized or not window.is_visible or window.bounds is None:
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "La ventana esta minimizada u oculta; no se captura", window_id=window_id)
        if window.extra.get("sharing_state") == _KCG_WINDOW_SHARING_NONE:
            return self._fail(operation, PlatformErrorCode.PROTECTED,
                              "La ventana declara contenido no capturable (kCGWindowSharingNone)")
        raw = None
        try:
            raw = self.boundary.capture_image(None, window_id=int(window_id))
        except NativeDependencyUnavailable as exc:
            logger.debug("CGWindowListCreateImage no disponible: %s", exc)
        except Exception as exc:
            logger.warning("Captura de ventana fallo: %s", exc)
        if raw is None:
            # Alternativa: region de la ventana con mss (solo si esta en primer plano).
            if not window.is_foreground:
                return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                                  "Sin captura por ventana; la region solo es valida en primer plano")
            try:
                b = window.bounds
                raw = self.boundary.capture_with_mss((b.left, b.top, b.width, b.height))
            except Exception as exc:
                return self._native_error(operation, exc)
        if raw is None:
            return self._fail(operation, PlatformErrorCode.NATIVE_ERROR, "No se obtuvo imagen de la ventana")
        captured = self._to_capture(raw, window.bounds, int(window_id), window.display_id, granted)
        if captured.ok:
            captured.details["foreground"] = window.is_foreground
        return captured

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def get_pointer_position(self) -> PlatformResult[PointerPosition]:
        operation = "get_pointer_position"
        try:
            x, y = self.boundary.pointer_location()
        except Exception as exc:
            return self._native_error(operation, exc)
        display = self._display_for_point(self._displays_or_empty(), x, y)
        return PlatformResult.success(PointerPosition(
            x=float(x), y=float(y), coordinate_space=DESKTOP_POINTS,
            display_id=display.display_id if display else None))

    def move_pointer(self, x: float, y: float) -> PlatformResult[PointerPosition]:
        operation = "move_pointer"
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Coordenadas no numericas")
        displays = self._displays_or_empty()
        if displays and self._display_for_point(displays, fx, fy) is None:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT,
                              "El punto (%.1f, %.1f) no esta en ningun monitor (puntos Quartz)" % (fx, fy))
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        try:
            self.boundary.post_mouse_move(fx, fy)
        except Exception as exc:
            return self._native_error(operation, exc)
        holder: Dict[str, Tuple[float, float]] = {}

        def arrived() -> bool:
            holder["pos"] = self.boundary.pointer_location()
            return abs(holder["pos"][0] - fx) <= 0.5 and abs(holder["pos"][1] - fy) <= 0.5

        self._poll(arrived)
        if "pos" not in holder:
            return self._fail(operation, PlatformErrorCode.NATIVE_ERROR, "No se pudo leer la posicion del puntero")
        ax, ay = holder["pos"]
        display = self._display_for_point(displays, ax, ay)
        return PlatformResult.success(
            PointerPosition(ax, ay, DESKTOP_POINTS, display.display_id if display else None),
            requested={"x": fx, "y": fy}, delta={"x": ax - fx, "y": ay - fy},
        )

    def click(self, button: str = "left", count: int = 1) -> PlatformResult[None]:
        operation = "click"
        button = str(button or "left").lower()
        if button not in ("left", "right", "middle"):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Boton no valido: %s" % button)
        if int(count) < 1 or int(count) > 3:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Numero de clicks fuera de rango")
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        try:
            x, y = self.boundary.pointer_location()
            for click_state in range(1, int(count) + 1):
                self.boundary.post_mouse_button(x, y, button, True, click_state)
                self.boundary.post_mouse_button(x, y, button, False, click_state)
        except Exception as exc:
            return self._native_error(operation, exc)
        return PlatformResult.success(None, x=x, y=y, button=button, count=int(count))

    def scroll(self, amount: int, horizontal: bool = False) -> PlatformResult[None]:
        operation = "scroll"
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        try:
            self.boundary.post_scroll(int(amount), bool(horizontal))
        except Exception as exc:
            return self._native_error(operation, exc)
        return PlatformResult.success(None)

    def type_text(self, text: str) -> PlatformResult[None]:
        operation = "type_text"
        if not isinstance(text, str):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "El texto debe ser str")
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        try:
            self.boundary.post_unicode(text)
        except Exception as exc:
            return self._native_error(operation, exc)
        return PlatformResult.success(None, length=len(text))

    @staticmethod
    def _resolve_keys(keys: Sequence[str]) -> Tuple[List[Tuple[int, int]], List[int], List[str]]:
        """Devuelve (modificadores, teclas, desconocidas)."""
        modifiers: List[Tuple[int, int]] = []
        normal: List[int] = []
        unknown: List[str] = []
        for key in keys:
            name = str(key)
            lower = name.lower()
            if lower in _MODIFIERS:
                modifiers.append(_MODIFIERS[lower])
            elif lower in _KEYCODES:
                normal.append(_KEYCODES[lower])
            else:
                unknown.append(name)
        return modifiers, normal, unknown

    def press_keys(self, keys: Sequence[str]) -> PlatformResult[None]:
        operation = "press_keys"
        if isinstance(keys, str):
            keys = [keys]
        keys = list(keys or [])
        if not keys:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Sin teclas")
        modifiers, normal, unknown = self._resolve_keys(keys)
        if unknown:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT,
                              "Teclas no soportadas: %s" % ", ".join(unknown),
                              logical_keys=sorted(LOGICAL_KEYS))
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        flags = 0
        pressed: List[Tuple[int, int]] = []
        try:
            for code, mask in modifiers:
                flags |= mask
                self.boundary.post_key(code, True, flags)
                pressed.append((code, mask))
            for code in normal:
                self.boundary.post_key(code, True, flags)
                self.boundary.post_key(code, False, flags)
        except Exception as exc:
            return self._native_error(operation, exc)
        finally:
            for code, mask in reversed(pressed):
                flags &= ~mask
                try:
                    self.boundary.post_key(code, False, flags)
                except Exception as exc:
                    logger.warning("No se pudo soltar el modificador %s: %s", code, exc)
        return PlatformResult.success(None, keys=keys)

    # ------------------------------------------------------------------
    # Accesibilidad
    # ------------------------------------------------------------------

    def get_accessibility_tree(
        self,
        window_id: int,
        pid: Optional[int] = None,
        max_depth: int = 60,
        max_nodes: int = 2000,
    ) -> PlatformResult[AccessibilityTree]:
        operation = "get_accessibility_tree"
        start = time.monotonic()
        error, entry, ax_window = self._ax_window_for(operation, window_id)
        if error is not None:
            return error
        entry_pid = int(entry.get("pid") or 0)
        if pid is not None and int(pid) != entry_pid:
            return self._fail(operation, PlatformErrorCode.VERIFICATION_FAILED,
                              "El PID indicado no es el propietario de la ventana",
                              expected_pid=int(pid), window_pid=entry_pid)
        displays = [d.bounds for d in self._displays_or_empty()]
        window_rect = _rect_from_xywh(entry.get("bounds"))
        deadline = start + self.tree_timeout
        nodes: List[AccessibilityNode] = []
        handles: Dict[str, Any] = {}
        truncated = False
        read_errors = 0
        # (manejador, profundidad, ruta, id del padre, rectangulo de recorte)
        stack: List[Tuple[Any, int, str, Optional[str], Optional[Rect]]] = [
            (ax_window["handle"], 0, "0", None, window_rect)
        ]
        while stack:
            if len(nodes) >= int(max_nodes) or time.monotonic() > deadline:
                truncated = True
                break
            handle, depth, path, parent_id, clip = stack.pop()
            try:
                attrs = self.boundary.ax_attributes(handle)
            except PermissionError as exc:
                return self._native_error(operation, exc)
            except Exception as exc:
                read_errors += 1
                logger.debug("ax_attributes(%s): %s", path, exc)
                continue
            box = None
            pos, size = attrs.get("AXPosition"), attrs.get("AXSize")
            if pos and size:
                box = _rect_from_xywh((pos[0], pos[1], size[0], size[1]))
            on_any_display = box is not None and any(r.intersection(box) for r in displays) if displays else box is not None
            inside_clip = box is not None and (clip is None or clip.intersection(box) is not None)
            attrs["_onscreen"] = bool(on_any_display and inside_clip)
            node = normalize_ax_attributes(
                attrs, int(window_id), entry_pid, parent_id, depth, path, native_ref=handle)
            nodes.append(node)
            handles[node.node_id] = handle
            try:
                children = self.boundary.ax_children(handle)
            except Exception as exc:
                read_errors += 1
                logger.debug("ax_children(%s): %s", path, exc)
                children = []
            if not children:
                continue
            if depth >= int(max_depth):
                truncated = True
                continue
            child_clip = clip
            if str(attrs.get("AXRole") or "") in _AX_CLIPPING_ROLES and box is not None:
                child_clip = (clip.intersection(box) if clip is not None else box) or box
            for index in range(len(children) - 1, -1, -1):
                stack.append((children[index], depth + 1, "%s.%d" % (path, index), node.node_id, child_clip))
        self._node_handles[int(window_id)] = handles
        tree = build_tree(
            window_id=int(window_id),
            pid=entry_pid,
            source="ax",
            nodes=nodes,
            truncated=truncated,
            error=None,
            coordinate_space=DESKTOP_POINTS,
            elapsed_seconds=time.monotonic() - start,
        )
        return PlatformResult.success(tree, read_errors=read_errors, node_count=len(nodes))

    def _element_path(self, element: Any, window_handle: Any) -> Optional[str]:
        """Ruta de indices desde la ventana AX hasta el elemento (como en el arbol)."""
        indices: List[int] = []
        current = element
        for _ in range(200):
            if self.boundary.ax_equal(current, window_handle):
                return ".".join(["0"] + [str(i) for i in reversed(indices)])
            parent = self.boundary.ax_parent(current)
            if parent is None:
                return None
            siblings = self.boundary.ax_children(parent)
            index = next((i for i, s in enumerate(siblings) if self.boundary.ax_equal(s, current)), None)
            if index is None:
                return None
            indices.append(index)
            current = parent
        return None

    def element_at_point(self, x: float, y: float) -> PlatformResult[Optional[AccessibilityNode]]:
        operation = "element_at_point"
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        try:
            element = self.boundary.ax_element_at_position(float(x), float(y))
        except Exception as exc:
            return self._native_error(operation, exc)
        if element is None:
            return PlatformResult.success(None)
        try:
            attrs = self.boundary.ax_attributes(element)
            pid = self.boundary.ax_element_pid(element)
            ax_window = self.boundary.ax_attribute_element(element, "AXWindow")
        except Exception as exc:
            return self._native_error(operation, exc)
        window_id: Optional[int] = None
        path: Optional[str] = None
        if ax_window is not None:
            try:
                win_attrs = self.boundary.ax_attributes(ax_window)
                pos, size = win_attrs.get("AXPosition"), win_attrs.get("AXSize")
                win_rect = _rect_from_xywh((pos[0], pos[1], size[0], size[1])) if pos and size else None
                if win_rect is not None and pid:
                    for entry in self.boundary.window_list("on_screen"):
                        rect = _rect_from_xywh(entry.get("bounds"))
                        if int(entry.get("pid") or 0) == int(pid) and rect is not None \
                                and _rect_distance(rect, win_rect) <= self.window_match_tolerance:
                            window_id = int(entry["window_id"])
                            break
                path = self._element_path(element, ax_window)
            except Exception as exc:
                logger.debug("element_at_point: ventana AX: %s", exc)
        if window_id is None:
            under = self.window_at_point(x, y)
            if under.ok and under.value is not None:
                window_id = under.value.window_id
        attrs["_onscreen"] = True
        node = normalize_ax_attributes(
            attrs, int(window_id or 0), pid, None, path.count(".") if path else 0,
            path or "point:%.1f,%.1f" % (float(x), float(y)), native_ref=element)
        return PlatformResult.success(node, window_id=window_id, path_resolved=path is not None)

    # Accion normalizada -> (acciones AX en orden de preferencia, atributo alternativo, valor).
    _ACTION_PLAN: Dict[str, Tuple[Tuple[str, ...], Optional[str], Any]] = {
        "invoke": (("AXPress", "AXConfirm"), None, None),
        "toggle": (("AXPress",), None, None),
        "show_menu": (("AXShowMenu",), None, None),
        "expand": (("AXShowMenu",), "AXExpanded", True),
        "collapse": (("AXCancel",), "AXExpanded", False),
        "select": (("AXPick",), "AXSelected", True),
        "scroll": (("AXScrollToVisible",), None, None),
        "focus": (("AXRaise",), "AXFocused", True),
        "set_value": ((), "AXValue", None),
    }

    def perform_accessibility_action(
        self,
        window_id: int,
        node_id: str,
        action: str,
        value: Any = None,
    ) -> PlatformResult[None]:
        operation = "perform_accessibility_action"
        if action not in ACCESSIBILITY_ACTIONS or action not in self._ACTION_PLAN:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Accion no valida: %s" % action)
        if action == "set_value" and value is None:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "set_value requiere un valor")
        denied = self._require_accessibility(operation)
        if denied is not None:
            return denied
        handles = self._node_handles.get(int(window_id)) or {}
        handle = handles.get(node_id)
        if handle is None:
            refreshed = self.get_accessibility_tree(window_id)
            if not refreshed.ok:
                return PlatformResult.from_error(refreshed.error)
            handle = (self._node_handles.get(int(window_id)) or {}).get(node_id)
        if handle is None:
            return self._fail(operation, PlatformErrorCode.NOT_FOUND,
                              "Nodo %s no encontrado en el arbol actual de la ventana" % node_id)
        try:
            native_actions = list(self.boundary.ax_attributes(handle).get("_actions") or [])
        except Exception as exc:
            return self._native_error(operation, exc)
        ax_actions, attribute, attr_value = self._ACTION_PLAN[action]
        try:
            for ax_action in ax_actions:
                if ax_action in native_actions:
                    code = int(self.boundary.ax_perform_action(handle, ax_action))
                    if code != AX_ERROR_SUCCESS:
                        return self._ax_error(operation, code, ax_action)
                    return PlatformResult.success(None, native_action=ax_action)
            if attribute is not None:
                if action == "set_value":
                    code = int(self.boundary.ax_set_value(handle, value))
                else:
                    code = int(self.boundary.ax_set_bool(handle, attribute, bool(attr_value)))
                if code != AX_ERROR_SUCCESS:
                    return self._ax_error(operation, code, attribute)
                return PlatformResult.success(None, native_attribute=attribute)
        except Exception as exc:
            return self._native_error(operation, exc)
        return self._fail(operation, PlatformErrorCode.NOT_SUPPORTED,
                          "El elemento no ofrece una accion AX para %s" % action,
                          native_actions=native_actions)

    # ------------------------------------------------------------------
    # Entorno de interaccion
    # ------------------------------------------------------------------

    def check_interaction_environment(self, window_id: int) -> PlatformResult[InteractionEnvironment]:
        operation = "check_interaction_environment"
        env = InteractionEnvironment()
        # Sesion (CGSessionCopyCurrentDictionary).
        try:
            session = self.boundary.session_info()
        except Exception as exc:
            logger.debug("session_info: %s", exc)
            session = None
        if session is None:
            env.unknown_checks.append("session_locked")
        else:
            if not session.get("on_console", True):
                env.session_locked = True
                env.details["session"] = "sesion no activa en consola (cambio rapido de usuario)"
            if "screen_locked" in session:
                env.session_locked = env.session_locked or bool(session["screen_locked"])
            else:
                env.unknown_checks.append("screen_locked")
        # Ventana de login/autorizacion en primer plano = escritorio seguro.
        try:
            front = self.boundary.frontmost_application()
        except Exception as exc:
            logger.debug("frontmost_application: %s", exc)
            front = None
        if front is None:
            env.unknown_checks.append("secure_desktop")
        elif str(front.get("bundle_id") or "") in _PROTECTED_BUNDLES:
            env.secure_desktop = True
        # Ventana objetivo.
        try:
            on_screen = self.boundary.window_list("on_screen")
            entry = self._window_entry(window_id)
        except Exception as exc:
            return self._native_error(operation, exc)
        if entry is None:
            return self._fail(operation, PlatformErrorCode.WINDOW_GONE, "La ventana %s no existe" % window_id)
        pid = int(entry.get("pid") or 0)
        app = self._app_info(pid)
        bounds = _rect_from_xywh(entry.get("bounds"))
        onscreen = bool(entry.get("onscreen", False))
        env.target_visible = onscreen and not (app and app.get("hidden")) and float(entry.get("alpha", 1.0)) > 0
        env.target_minimized = not onscreen
        if self._ax_trusted():
            try:
                ax_window = self._match_ax_window(pid, bounds, str(entry.get("title") or ""))
                if ax_window is not None:
                    env.target_minimized = bool(ax_window.get("minimized"))
            except Exception as exc:
                logger.debug("AX de la ventana objetivo: %s", exc)
        if entry.get("sharing_state") == _KCG_WINDOW_SHARING_NONE:
            env.protected_content = True
        owner = str(entry.get("owner_name") or "")
        bundle = str(app.get("bundle_id") or "") if app else ""
        if owner in _PROTECTED_OWNER_NAMES or bundle in _PROTECTED_BUNDLES:
            env.protected_window = True
        # Elevacion: proceso objetivo de root frente a JARVIS sin root.
        target_euid = self.boundary.process_euid(pid)
        own_euid = self.boundary.own_euid()
        env.jarvis_elevated = own_euid == 0
        if target_euid is None:
            env.unknown_checks.append("target_elevated")
        else:
            env.target_elevated = target_euid == 0
        # Overlays: ventanas de capa superior delante del objetivo que lo intersectan.
        target_index = next((i for i, e in enumerate(on_screen)
                             if int(e.get("window_id") or 0) == int(window_id)), None)
        occluding: List[int] = []
        if bounds is not None and target_index is not None:
            target_layer = int(entry.get("layer", 0))
            for other in on_screen[:target_index]:
                if int(other.get("pid") or 0) == pid or float(other.get("alpha", 1.0)) <= 0:
                    continue
                other_rect = _rect_from_xywh(other.get("bounds"))
                if other_rect is None or other_rect.intersection_area(bounds) < 1.0:
                    continue
                if int(other.get("layer", 0)) > target_layer:
                    env.overlay_windows.append(int(other.get("window_id") or 0))
                else:
                    occluding.append(int(other.get("window_id") or 0))
        env.details["occluding_windows"] = occluding
        # Permisos.
        trusted = self._ax_trusted()
        if trusted is False:
            env.permissions_missing.append(PermissionKind.ACCESSIBILITY.value)
        elif trusted is None:
            env.unknown_checks.append("accessibility_permission")
        capture = self._screen_capture_granted()
        if capture is False:
            env.permissions_missing.append(PermissionKind.SCREEN_RECORDING.value)
        elif capture is None:
            env.unknown_checks.append("screen_recording_permission")
        env.details["window_id"] = int(window_id)
        env.details["pid"] = pid
        return PlatformResult.success(env)


__all__ = [
    "MACOS_REAL_VERIFICATION",
    "MacNativeBoundary",
    "MacOSDesktopAdapter",
    "cocoa_rect_to_quartz",
]
