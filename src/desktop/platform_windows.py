"""
Adaptador Windows del contrato de plataforma de escritorio.

Implementa ``DesktopPlatformAdapter`` (``src.desktop.platform_contract``) sobre
las APIs reales de Windows, envolviendo el codigo ya existente del proyecto:

* Monitores: ``EnumDisplayMonitors`` + ``GetMonitorInfoW`` (``rcMonitor`` y
  ``rcWork``), ``GetDpiForMonitor`` (DPI efectivo), ``EnumDisplaySettingsW``
  (rotacion y frecuencia) y ``EnumDisplayDevicesW`` con
  ``EDD_GET_DEVICE_INTERFACE_NAME`` (identificador estable del monitor).
* Ventanas: ``EnumWindows``, ``GetWindowRect``, ``GetClientRect`` +
  ``ClientToScreen``, ``DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)``,
  ``IsIconic``/``IsZoomed``/``IsWindowVisible``/``DWMWA_CLOAKED``,
  ``SetWindowPos``/``ShowWindow`` y activacion con verificacion real de
  ``GetForegroundWindow``.
* Captura: ``MssCapture`` de ``src.eyes.capture.screen_capture`` (ruta por
  defecto) y ``DXcamCapture`` opcional, informando siempre el backend efectivo.
* Entrada: ``SetCursorPos`` + lectura real con ``GetCursorPos`` y ``SendInput``
  para botones, rueda y teclado. ``primary_modifier`` es Ctrl.
* Accesibilidad: ``UIAutomationAdapter`` (pywinauto/UIA, COM de respaldo)
  normalizado con ``normalize_uia_tree``; ``element_at_point`` con
  ``UIAElementInfo.from_point``; acciones solo mediante patrones UIA y solo
  cuando se llaman de forma explicita.
* Entorno: escritorio de entrada (sesion bloqueada / escritorio seguro),
  elevacion del objetivo frente a la de JARVIS (``TokenElevation``),
  ``GetWindowDisplayAffinity`` (contenido protegido), ventanas protegidas de
  UAC/credenciales, ventanas superpuestas por encima en el orden Z, ventana
  minimizada u oculta.

Geometria: todas las operaciones se ejecutan con el contexto de DPI del hilo en
Per-Monitor V2 (``SetThreadDpiAwarenessContext``) y se restaura el contexto
previo al terminar, de modo que las coordenadas son pixeles fisicos del
escritorio virtual (``DESKTOP_PIXELS``) sin cambiar la awareness global del
proceso.

Todos los imports nativos (``ctypes.WinDLL``, estructuras Win32, pywinauto,
comtypes, dxcam, winreg) son perezosos y solo se cargan en Windows: el modulo
se importa sin error en macOS, donde todas las operaciones devuelven
``NOT_SUPPORTED`` normalizado.

El adaptador no decide politica: no elige monitores, no valida si una accion
es segura y no protege por si mismo ventanas ajenas. Esa responsabilidad es de
los consumidores (topologia, puertas de calidad, exploracion profunda).
"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.accessibility_model import (
    AccessibilityNode,
    AccessibilityTree,
    normalize_uia_element,
    normalize_uia_tree,
)
from src.desktop.platform_contract import (
    ACCESSIBILITY_ACTIONS,
    DESKTOP_PIXELS,
    PLATFORM_WINDOWS,
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


# ============================================================================
# CONSTANTES WIN32
# ============================================================================

MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF
EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001
MDT_EFFECTIVE_DPI = 0

GA_ROOT = 2
GA_ROOTOWNER = 3
GW_HWNDPREV = 3
GW_OWNER = 4
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

SW_MAXIMIZE = 3
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

LWA_ALPHA = 0x00000002

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SETTINGCHANGE = 0x001A
WM_DISPLAYCHANGE = 0x007E
WM_DPICHANGED = 0x02E0
SPI_SETWORKAREA = 0x002F
SPI_SETLOGICALDPIOVERRIDE = 0x009F

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20
ERROR_ACCESS_DENIED = 5

DESKTOP_SWITCHDESKTOP = 0x0100
UOI_NAME = 2

WDA_NONE = 0x00000000

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

DPI_AWARENESS_NAMES = {
    -1: "invalid",
    0: "unaware",
    1: "system_aware",
    2: "per_monitor_aware",
}

# Rotacion DEVMODEW.dmDisplayOrientation -> grados.
DMDO_DEGREES = {0: 0, 1: 90, 2: 180, 3: 270}

# Botones de raton -> (flag pulsar, flag soltar).
MOUSE_BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Teclas logicas del contrato -> codigo virtual Windows.
# ``primary_modifier`` y ``cmd`` se traducen a Ctrl (equivalente de Cmd en macOS).
VIRTUAL_KEYS: Dict[str, int] = {
    "primary_modifier": 0x11,
    "ctrl": 0x11,
    "cmd": 0x11,
    "alt": 0x12,
    "option": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}
for _i in range(1, 13):
    VIRTUAL_KEYS["f%d" % _i] = 0x70 + (_i - 1)

# Teclas que requieren KEYEVENTF_EXTENDEDKEY.
EXTENDED_VIRTUAL_KEYS = frozenset({
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B,
})

# Ventanas protegidas del sistema (UAC, credenciales, pantalla de bloqueo).
PROTECTED_WINDOW_CLASSES = frozenset({
    "credential dialog xaml host",
    "$$$secure uap dummy window class for interim dialog",
})
PROTECTED_PROCESS_NAMES = frozenset({
    "consent.exe",
    "logonui.exe",
    "lockapp.exe",
    "credentialuibroker.exe",
})

# Fraccion minima del area de la ventana objetivo que debe cubrir otra ventana
# superior para considerarla superpuesta (evita contar bordes de 1 px).
OVERLAY_MIN_AREA_RATIO = 0.01

# Tiempos maximos de espera activa (polling, nunca sleep fijo).
WINDOW_STATE_TIMEOUT = 2.0
FOREGROUND_TIMEOUT = 1.0
POLL_INTERVAL = 0.03

ScrollAmount_SmallDecrement = 1
ScrollAmount_NoAmount = 2
ScrollAmount_SmallIncrement = 4


def _wait_until(predicate: Callable[[], bool], timeout: float, interval: float = POLL_INTERVAL) -> bool:
    """Espera activa con limite: devuelve True en cuanto ``predicate`` se cumple."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        try:
            if predicate():
                return True
        except Exception as exc:
            logger.debug("_wait_until: predicado fallo: %s", exc)
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


# ============================================================================
# CARGA PEREZOSA DE LA API WIN32
# ============================================================================


class _Win32Api:
    """Bibliotecas, estructuras y firmas Win32 del adaptador.

    Usa instancias propias de ``ctypes.WinDLL`` para que declarar ``argtypes`` y
    ``restype`` no altere los punteros compartidos de ``ctypes.windll`` que usan
    otros modulos del proyecto. Solo se construye en Windows.
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        try:
            self.shcore = ctypes.WinDLL("shcore")
        except OSError as exc:
            logger.debug("shcore no disponible: %s", exc)
            self.shcore = None
        try:
            self.dwmapi = ctypes.WinDLL("dwmapi")
        except OSError as exc:
            logger.debug("dwmapi no disponible: %s", exc)
            self.dwmapi = None
        self._define_structures()
        self._declare_functions()

    # ------------------------------------------------------------------
    # Estructuras
    # ------------------------------------------------------------------

    def _define_structures(self) -> None:
        ctypes = self.ctypes
        wt = self.wintypes

        self.RECT = wt.RECT
        self.POINT = wt.POINT
        self.MSG = wt.MSG
        self.ULONG_PTR = ctypes.c_size_t
        self.LRESULT = ctypes.c_ssize_t

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wt.DWORD),
                ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD),
                ("szDevice", wt.WCHAR * 32),
            ]

        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("DeviceName", wt.WCHAR * 32),
                ("DeviceString", wt.WCHAR * 128),
                ("StateFlags", wt.DWORD),
                ("DeviceID", wt.WCHAR * 128),
                ("DeviceKey", wt.WCHAR * 128),
            ]

        class DEVMODEW(ctypes.Structure):
            # Variante de pantalla de la union (dmPosition/dmDisplayOrientation).
            _fields_ = [
                ("dmDeviceName", wt.WCHAR * 32),
                ("dmSpecVersion", wt.WORD),
                ("dmDriverVersion", wt.WORD),
                ("dmSize", wt.WORD),
                ("dmDriverExtra", wt.WORD),
                ("dmFields", wt.DWORD),
                ("dmPositionX", wt.LONG),
                ("dmPositionY", wt.LONG),
                ("dmDisplayOrientation", wt.DWORD),
                ("dmDisplayFixedOutput", wt.DWORD),
                ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short),
                ("dmFormName", wt.WCHAR * 32),
                ("dmLogPixels", wt.WORD),
                ("dmBitsPerPel", wt.DWORD),
                ("dmPelsWidth", wt.DWORD),
                ("dmPelsHeight", wt.DWORD),
                ("dmDisplayFlags", wt.DWORD),
                ("dmDisplayFrequency", wt.DWORD),
                ("dmICMMethod", wt.DWORD),
                ("dmICMIntent", wt.DWORD),
                ("dmMediaType", wt.DWORD),
                ("dmDitherType", wt.DWORD),
                ("dmReserved1", wt.DWORD),
                ("dmReserved2", wt.DWORD),
                ("dmPanningWidth", wt.DWORD),
                ("dmPanningHeight", wt.DWORD),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wt.LONG),
                ("dy", wt.LONG),
                ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wt.WORD),
                ("wScan", wt.WORD),
                ("dwFlags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wt.DWORD),
                ("wParamL", wt.WORD),
                ("wParamH", wt.WORD),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wt.DWORD),
                ("u", _INPUTUNION),
            ]

        self.WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM
        )

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wt.UINT),
                ("style", wt.UINT),
                ("lpfnWndProc", self.WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", wt.HICON),
            ]

        self.MONITORINFOEXW = MONITORINFOEXW
        self.DISPLAY_DEVICEW = DISPLAY_DEVICEW
        self.DEVMODEW = DEVMODEW
        self.MOUSEINPUT = MOUSEINPUT
        self.KEYBDINPUT = KEYBDINPUT
        self.INPUT = INPUT
        self.WNDCLASSEXW = WNDCLASSEXW
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        self.MONITORENUMPROC = ctypes.WINFUNCTYPE(
            wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
        )

    # ------------------------------------------------------------------
    # Firmas
    # ------------------------------------------------------------------

    def _sig(self, dll: Any, name: str, restype: Any, argtypes: Sequence[Any]) -> Any:
        """Declara la firma de ``dll.name``; devuelve None si no existe en este Windows."""
        if dll is None:
            return None
        try:
            fn = getattr(dll, name)
        except AttributeError:
            return None
        fn.restype = restype
        fn.argtypes = list(argtypes)
        return fn

    def _declare_functions(self) -> None:
        ct = self.ctypes
        wt = self.wintypes
        P = ct.POINTER
        u, k, a = self.user32, self.kernel32, self.advapi32
        HWND = wt.HWND

        self.IsWindow = self._sig(u, "IsWindow", wt.BOOL, [HWND])
        self.IsWindowVisible = self._sig(u, "IsWindowVisible", wt.BOOL, [HWND])
        self.IsWindowEnabled = self._sig(u, "IsWindowEnabled", wt.BOOL, [HWND])
        self.IsIconic = self._sig(u, "IsIconic", wt.BOOL, [HWND])
        self.IsZoomed = self._sig(u, "IsZoomed", wt.BOOL, [HWND])
        self.GetWindowRect = self._sig(u, "GetWindowRect", wt.BOOL, [HWND, P(wt.RECT)])
        self.GetClientRect = self._sig(u, "GetClientRect", wt.BOOL, [HWND, P(wt.RECT)])
        self.ClientToScreen = self._sig(u, "ClientToScreen", wt.BOOL, [HWND, P(wt.POINT)])
        self.GetWindowTextLengthW = self._sig(u, "GetWindowTextLengthW", ct.c_int, [HWND])
        self.GetWindowTextW = self._sig(u, "GetWindowTextW", ct.c_int, [HWND, wt.LPWSTR, ct.c_int])
        self.GetClassNameW = self._sig(u, "GetClassNameW", ct.c_int, [HWND, wt.LPWSTR, ct.c_int])
        self.GetWindowThreadProcessId = self._sig(
            u, "GetWindowThreadProcessId", wt.DWORD, [HWND, P(wt.DWORD)]
        )
        self.GetForegroundWindow = self._sig(u, "GetForegroundWindow", HWND, [])
        self.SetForegroundWindow = self._sig(u, "SetForegroundWindow", wt.BOOL, [HWND])
        self.BringWindowToTop = self._sig(u, "BringWindowToTop", wt.BOOL, [HWND])
        self.ShowWindow = self._sig(u, "ShowWindow", wt.BOOL, [HWND, ct.c_int])
        self.SetWindowPos = self._sig(
            u, "SetWindowPos", wt.BOOL,
            [HWND, HWND, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.UINT],
        )
        self.GetWindow = self._sig(u, "GetWindow", HWND, [HWND, wt.UINT])
        self.GetAncestor = self._sig(u, "GetAncestor", HWND, [HWND, wt.UINT])
        self.WindowFromPoint = self._sig(u, "WindowFromPoint", HWND, [wt.POINT])
        self.GetWindowLongW = self._sig(u, "GetWindowLongW", wt.LONG, [HWND, ct.c_int])
        self.GetLayeredWindowAttributes = self._sig(
            u, "GetLayeredWindowAttributes", wt.BOOL,
            [HWND, P(wt.DWORD), P(wt.BYTE), P(wt.DWORD)],
        )
        self.EnumWindows = self._sig(u, "EnumWindows", wt.BOOL, [self.WNDENUMPROC, wt.LPARAM])
        self.EnumDisplayMonitors = self._sig(
            u, "EnumDisplayMonitors", wt.BOOL,
            [wt.HDC, P(wt.RECT), self.MONITORENUMPROC, wt.LPARAM],
        )
        self.GetMonitorInfoW = self._sig(
            u, "GetMonitorInfoW", wt.BOOL, [wt.HMONITOR, P(self.MONITORINFOEXW)]
        )
        self.MonitorFromWindow = self._sig(u, "MonitorFromWindow", wt.HMONITOR, [HWND, wt.DWORD])
        self.MonitorFromPoint = self._sig(u, "MonitorFromPoint", wt.HMONITOR, [wt.POINT, wt.DWORD])
        self.EnumDisplaySettingsW = self._sig(
            u, "EnumDisplaySettingsW", wt.BOOL, [wt.LPCWSTR, wt.DWORD, P(self.DEVMODEW)]
        )
        self.EnumDisplayDevicesW = self._sig(
            u, "EnumDisplayDevicesW", wt.BOOL,
            [wt.LPCWSTR, wt.DWORD, P(self.DISPLAY_DEVICEW), wt.DWORD],
        )
        self.SetCursorPos = self._sig(u, "SetCursorPos", wt.BOOL, [ct.c_int, ct.c_int])
        self.GetCursorPos = self._sig(u, "GetCursorPos", wt.BOOL, [P(wt.POINT)])
        self.SendInput = self._sig(u, "SendInput", wt.UINT, [wt.UINT, P(self.INPUT), ct.c_int])
        self.VkKeyScanW = self._sig(u, "VkKeyScanW", ct.c_short, [wt.WCHAR])
        self.MapVirtualKeyW = self._sig(u, "MapVirtualKeyW", wt.UINT, [wt.UINT, wt.UINT])
        self.GetDpiForWindow = self._sig(u, "GetDpiForWindow", wt.UINT, [HWND])
        self.GetWindowDpiAwarenessContext = self._sig(
            u, "GetWindowDpiAwarenessContext", ct.c_void_p, [HWND]
        )
        self.GetAwarenessFromDpiAwarenessContext = self._sig(
            u, "GetAwarenessFromDpiAwarenessContext", ct.c_int, [ct.c_void_p]
        )
        self.AreDpiAwarenessContextsEqual = self._sig(
            u, "AreDpiAwarenessContextsEqual", wt.BOOL, [ct.c_void_p, ct.c_void_p]
        )
        self.SetThreadDpiAwarenessContext = self._sig(
            u, "SetThreadDpiAwarenessContext", ct.c_void_p, [ct.c_void_p]
        )
        self.GetThreadDpiAwarenessContext = self._sig(
            u, "GetThreadDpiAwarenessContext", ct.c_void_p, []
        )
        self.GetWindowDisplayAffinity = self._sig(
            u, "GetWindowDisplayAffinity", wt.BOOL, [HWND, P(wt.DWORD)]
        )
        self.AttachThreadInput = self._sig(
            u, "AttachThreadInput", wt.BOOL, [wt.DWORD, wt.DWORD, wt.BOOL]
        )
        self.PostMessageW = self._sig(
            u, "PostMessageW", wt.BOOL, [HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        )
        self.OpenInputDesktop = self._sig(
            u, "OpenInputDesktop", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]
        )
        self.GetUserObjectInformationW = self._sig(
            u, "GetUserObjectInformationW", wt.BOOL,
            [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, P(wt.DWORD)],
        )
        self.CloseDesktop = self._sig(u, "CloseDesktop", wt.BOOL, [wt.HANDLE])
        self.RegisterClassExW = self._sig(u, "RegisterClassExW", wt.ATOM, [P(self.WNDCLASSEXW)])
        self.UnregisterClassW = self._sig(u, "UnregisterClassW", wt.BOOL, [wt.LPCWSTR, wt.HINSTANCE])
        self.CreateWindowExW = self._sig(
            u, "CreateWindowExW", HWND,
            [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ct.c_int, ct.c_int,
             ct.c_int, ct.c_int, HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID],
        )
        self.DefWindowProcW = self._sig(
            u, "DefWindowProcW", self.LRESULT, [HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        )
        self.DestroyWindow = self._sig(u, "DestroyWindow", wt.BOOL, [HWND])
        self.GetMessageW = self._sig(u, "GetMessageW", wt.BOOL, [P(wt.MSG), HWND, wt.UINT, wt.UINT])
        self.TranslateMessage = self._sig(u, "TranslateMessage", wt.BOOL, [P(wt.MSG)])
        self.DispatchMessageW = self._sig(u, "DispatchMessageW", self.LRESULT, [P(wt.MSG)])
        self.PostQuitMessage = self._sig(u, "PostQuitMessage", None, [ct.c_int])

        self.GetCurrentThreadId = self._sig(k, "GetCurrentThreadId", wt.DWORD, [])
        self.GetCurrentProcess = self._sig(k, "GetCurrentProcess", wt.HANDLE, [])
        self.OpenProcess = self._sig(k, "OpenProcess", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD])
        self.CloseHandle = self._sig(k, "CloseHandle", wt.BOOL, [wt.HANDLE])
        self.GetModuleHandleW = self._sig(k, "GetModuleHandleW", wt.HMODULE, [wt.LPCWSTR])

        self.OpenProcessToken = self._sig(
            a, "OpenProcessToken", wt.BOOL, [wt.HANDLE, wt.DWORD, P(wt.HANDLE)]
        )
        self.GetTokenInformation = self._sig(
            a, "GetTokenInformation", wt.BOOL,
            [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, P(wt.DWORD)],
        )

        self.GetDpiForMonitor = self._sig(
            self.shcore, "GetDpiForMonitor", ct.c_long,
            [wt.HMONITOR, ct.c_int, P(wt.UINT), P(wt.UINT)],
        )
        self.GetProcessDpiAwareness = self._sig(
            self.shcore, "GetProcessDpiAwareness", ct.c_long, [wt.HANDLE, P(ct.c_int)]
        )
        self.DwmGetWindowAttribute = self._sig(
            self.dwmapi, "DwmGetWindowAttribute", ct.c_long,
            [HWND, wt.DWORD, ct.c_void_p, wt.DWORD],
        )

    # ------------------------------------------------------------------
    # Contexto DPI del hilo
    # ------------------------------------------------------------------

    @contextmanager
    def per_monitor_dpi(self) -> Iterator[None]:
        """Ejecuta el bloque con el hilo en Per-Monitor V2 y restaura el previo.

        Solo cambia el contexto del hilo actual; la awareness global del
        proceso no se modifica (no se cambia despues de crear ventanas).
        """
        previous = None
        setter = self.SetThreadDpiAwarenessContext
        if setter is not None:
            try:
                previous = setter(self.ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
            except Exception as exc:
                logger.debug("SetThreadDpiAwarenessContext fallo: %s", exc)
                previous = None
        try:
            yield
        finally:
            if setter is not None and previous:
                try:
                    setter(self.ctypes.c_void_p(previous))
                except Exception as exc:
                    logger.debug("No se pudo restaurar el contexto DPI del hilo: %s", exc)

    def last_error(self) -> int:
        try:
            return int(self.ctypes.get_last_error())
        except Exception:
            return 0


# ============================================================================
# ESCUCHA DE CAMBIOS DE PANTALLA
# ============================================================================


class _DisplayChangeListener:
    """Ventana oculta de nivel superior en un hilo propio que recibe los
    mensajes de cambio de pantalla y llama ``callback(motivo)``.

    Se usa una ventana oculta de nivel superior (estilo ``WS_POPUP`` sin
    ``WS_VISIBLE``) y no una ventana message-only porque las ventanas
    message-only no reciben mensajes de difusion como ``WM_DISPLAYCHANGE`` o
    ``WM_SETTINGCHANGE``. Motivos: ``display_change``, ``dpi_change``,
    ``work_area_change``, ``scale_change``. El callback se ejecuta en el hilo
    del listener y debe ser rapido.
    """

    _counter = 0
    _counter_lock = threading.Lock()

    def __init__(self, api: _Win32Api, callback: Callable[[str], None]) -> None:
        self._api = api
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._hwnd: Optional[int] = None
        self._error: Optional[str] = None
        self._wndproc_ref: Any = None
        with _DisplayChangeListener._counter_lock:
            _DisplayChangeListener._counter += 1
            self._class_name = "JarvisDisplayChangeListener%d" % _DisplayChangeListener._counter

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive() and self._hwnd)

    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(
            target=self._run, name="jarvis-display-listener", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self.running

    def stop(self, timeout: float = 5.0) -> bool:
        api = self._api
        hwnd = self._hwnd
        if hwnd and api.PostMessageW is not None:
            try:
                api.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception as exc:
                logger.warning("No se pudo cerrar la ventana del listener: %s", exc)
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def _dispatch(self, reason: str) -> None:
        try:
            self._callback(reason)
        except Exception:
            logger.exception("El callback de cambio de pantalla fallo (%s)", reason)

    def _wndproc(self, hwnd: Any, msg: int, wparam: int, lparam: int) -> int:
        api = self._api
        try:
            if msg == WM_DISPLAYCHANGE:
                self._dispatch("display_change")
            elif msg == WM_DPICHANGED:
                self._dispatch("dpi_change")
            elif msg == WM_SETTINGCHANGE:
                if int(wparam or 0) == SPI_SETWORKAREA:
                    self._dispatch("work_area_change")
                elif int(wparam or 0) == SPI_SETLOGICALDPIOVERRIDE:
                    self._dispatch("scale_change")
            elif msg == WM_CLOSE:
                api.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                api.PostQuitMessage(0)
                return 0
        except Exception:
            logger.exception("Error en el procedimiento de ventana del listener")
        return int(api.DefWindowProcW(hwnd, msg, wparam, lparam))

    def _run(self) -> None:
        api = self._api
        ct = api.ctypes
        atom = 0
        hinstance = None
        try:
            if api.SetThreadDpiAwarenessContext is not None:
                api.SetThreadDpiAwarenessContext(
                    ct.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
                )
            hinstance = api.GetModuleHandleW(None)
            self._wndproc_ref = api.WNDPROC(self._wndproc)
            wc = api.WNDCLASSEXW()
            wc.cbSize = ct.sizeof(api.WNDCLASSEXW)
            wc.style = 0
            wc.lpfnWndProc = self._wndproc_ref
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinstance
            wc.hIcon = None
            wc.hCursor = None
            wc.hbrBackground = None
            wc.lpszMenuName = None
            wc.lpszClassName = self._class_name
            wc.hIconSm = None
            atom = api.RegisterClassExW(ct.byref(wc))
            if not atom:
                self._error = "RegisterClassExW fallo (error %s)" % api.last_error()
                return
            hwnd = api.CreateWindowExW(
                WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                self._class_name,
                "JARVIS display listener",
                WS_POPUP,
                0, 0, 0, 0,
                None, None, hinstance, None,
            )
            if not hwnd:
                self._error = "CreateWindowExW fallo (error %s)" % api.last_error()
                return
            self._hwnd = int(hwnd)
            self._ready.set()
            msg = api.MSG()
            while True:
                result = api.GetMessageW(ct.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                api.TranslateMessage(ct.byref(msg))
                api.DispatchMessageW(ct.byref(msg))
        except Exception as exc:
            self._error = str(exc)
            logger.exception("El hilo del listener de pantallas fallo")
        finally:
            self._hwnd = None
            self._ready.set()
            if atom:
                try:
                    api.UnregisterClassW(self._class_name, hinstance)
                except Exception as exc:
                    logger.debug("UnregisterClassW fallo: %s", exc)


# ============================================================================
# ADAPTADOR
# ============================================================================


class WindowsDesktopAdapter(DesktopPlatformAdapter):
    """Implementacion Windows del contrato de plataforma de escritorio.

    Argumentos:
        capture_backend: ``"mss"`` (por defecto, ruta estable existente),
            ``"dxcam"`` (usa DXcam para capturar monitores completos y degrada a
            mss informando el motivo) o ``"auto"`` (igual que ``"dxcam"``).
        capabilities_ttl: segundos durante los que se reutiliza el informe de
            capacidades.
    """

    platform_name = PLATFORM_WINDOWS
    desktop_space = DESKTOP_PIXELS

    def __init__(self, capture_backend: str = "mss", capabilities_ttl: float = 30.0) -> None:
        backend = str(capture_backend or "mss").lower()
        self.capture_backend = backend if backend in ("mss", "dxcam", "auto") else "mss"
        self._api: Optional[_Win32Api] = None
        self._api_error: Optional[str] = None
        self._api_lock = threading.Lock()
        self._uia_adapters: Dict[Tuple[int, int], Any] = {}
        self._uia_lock = threading.Lock()
        self._listeners: Dict[int, _DisplayChangeListener] = {}
        self._capabilities_cache: Optional[Dict[Capability, CapabilityReport]] = None
        self._capabilities_time = 0.0
        self._capabilities_ttl = float(capabilities_ttl)

    # ------------------------------------------------------------------
    # Infraestructura
    # ------------------------------------------------------------------

    def _get_api(self) -> Optional[_Win32Api]:
        if self._api is not None:
            return self._api
        if sys.platform != "win32":
            self._api_error = "el adaptador Windows solo funciona en Windows (SO actual: %s)" % sys.platform
            return None
        with self._api_lock:
            if self._api is None and self._api_error is None:
                try:
                    self._api = _Win32Api()
                except Exception as exc:
                    self._api_error = "no se pudo cargar la API Win32: %s" % exc
                    logger.warning("WindowsDesktopAdapter: %s", self._api_error)
        return self._api

    def _run(self, operation: str, fn: Callable[[_Win32Api], PlatformResult[Any]]) -> PlatformResult[Any]:
        """Ejecuta ``fn(api)`` en contexto Per-Monitor V2 y normaliza errores."""
        api = self._get_api()
        if api is None:
            return self._fail(
                operation,
                PlatformErrorCode.NOT_SUPPORTED,
                self._api_error or "API Win32 no disponible",
            )
        try:
            with api.per_monitor_dpi():
                return fn(api)
        except Exception as exc:
            logger.warning("WindowsDesktopAdapter.%s fallo: %s", operation, exc)
            return self._fail(
                operation,
                PlatformErrorCode.NATIVE_ERROR,
                "Error nativo en %s" % operation,
                native_error=exc,
            )

    # ------------------------------------------------------------------
    # Ayudas Win32 de bajo nivel
    # ------------------------------------------------------------------

    @staticmethod
    def _rect(r: Any) -> Rect:
        return Rect(int(r.left), int(r.top), int(r.right), int(r.bottom))

    def _is_window(self, api: _Win32Api, hwnd: Optional[int]) -> bool:
        if not hwnd:
            return False
        try:
            return bool(api.IsWindow(int(hwnd)))
        except Exception:
            return False

    def _window_pid(self, api: _Win32Api, hwnd: int) -> int:
        pid = api.wintypes.DWORD(0)
        api.GetWindowThreadProcessId(int(hwnd), api.ctypes.byref(pid))
        return int(pid.value)

    def _window_thread(self, api: _Win32Api, hwnd: int) -> int:
        return int(api.GetWindowThreadProcessId(int(hwnd), None) or 0)

    def _window_text(self, api: _Win32Api, hwnd: int) -> str:
        try:
            length = int(api.GetWindowTextLengthW(int(hwnd)))
            if length <= 0:
                return ""
            buf = api.ctypes.create_unicode_buffer(length + 1)
            api.GetWindowTextW(int(hwnd), buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def _class_name(self, api: _Win32Api, hwnd: int) -> str:
        try:
            buf = api.ctypes.create_unicode_buffer(256)
            n = api.GetClassNameW(int(hwnd), buf, 256)
            return buf.value if n > 0 else ""
        except Exception:
            return ""

    def _window_rect(self, api: _Win32Api, hwnd: int) -> Optional[Rect]:
        rect = api.RECT()
        if not api.GetWindowRect(int(hwnd), api.ctypes.byref(rect)):
            return None
        return self._rect(rect)

    def _client_rect(self, api: _Win32Api, hwnd: int) -> Optional[Rect]:
        rect = api.RECT()
        if not api.GetClientRect(int(hwnd), api.ctypes.byref(rect)):
            return None
        origin = api.POINT(0, 0)
        if not api.ClientToScreen(int(hwnd), api.ctypes.byref(origin)):
            return None
        width = int(rect.right) - int(rect.left)
        height = int(rect.bottom) - int(rect.top)
        return Rect(int(origin.x), int(origin.y), int(origin.x) + width, int(origin.y) + height)

    def _frame_rect(self, api: _Win32Api, hwnd: int) -> Optional[Rect]:
        if api.DwmGetWindowAttribute is None:
            return None
        rect = api.RECT()
        hr = api.DwmGetWindowAttribute(
            int(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
            api.ctypes.byref(rect), api.ctypes.sizeof(rect),
        )
        if hr != 0:
            return None
        result = self._rect(rect)
        return result if result.is_valid() else None

    def _is_cloaked(self, api: _Win32Api, hwnd: int) -> bool:
        if api.DwmGetWindowAttribute is None:
            return False
        value = api.wintypes.DWORD(0)
        hr = api.DwmGetWindowAttribute(
            int(hwnd), DWMWA_CLOAKED, api.ctypes.byref(value), api.ctypes.sizeof(value)
        )
        return hr == 0 and int(value.value) != 0

    def _exstyle(self, api: _Win32Api, hwnd: int) -> int:
        try:
            return int(api.GetWindowLongW(int(hwnd), GWL_EXSTYLE)) & 0xFFFFFFFF
        except Exception:
            return 0

    def _root(self, api: _Win32Api, hwnd: Optional[int]) -> Optional[int]:
        if not hwnd:
            return None
        root = api.GetAncestor(int(hwnd), GA_ROOT)
        return int(root) if root else int(hwnd)

    def _foreground(self, api: _Win32Api) -> Optional[int]:
        hwnd = api.GetForegroundWindow()
        return int(hwnd) if hwnd else None

    def _exe_name(self, pid: int, cache: Optional[Dict[int, str]] = None) -> str:
        if cache is not None and pid in cache:
            return cache[pid]
        name = ""
        try:
            import psutil

            name = str(psutil.Process(int(pid)).name() or "")
        except Exception as exc:
            logger.debug("No se pudo leer el nombre del proceso %s: %s", pid, exc)
        if cache is not None:
            cache[pid] = name
        return name

    def _device_identity(self, api: _Win32Api, device_name: str) -> Tuple[str, str]:
        """(display_id estable, nombre amigable) para un dispositivo ``\\\\.\\DISPLAYn``.

        El identificador es la ruta de interfaz del monitor
        (``EDD_GET_DEVICE_INTERFACE_NAME``), estable entre reinicios y orden de
        conexion. Si no esta disponible se usa el nombre de dispositivo.
        """
        try:
            dd = api.DISPLAY_DEVICEW()
            dd.cb = api.ctypes.sizeof(api.DISPLAY_DEVICEW)
            if api.EnumDisplayDevicesW(device_name, 0, api.ctypes.byref(dd), EDD_GET_DEVICE_INTERFACE_NAME):
                device_id = str(dd.DeviceID or "").strip()
                friendly = str(dd.DeviceString or "").strip()
                if device_id:
                    return device_id, friendly
                return device_name, friendly
        except Exception as exc:
            logger.debug("EnumDisplayDevicesW(%s) fallo: %s", device_name, exc)
        return device_name, ""

    def _monitor_dpi(self, api: _Win32Api, hmonitor: int) -> int:
        if api.GetDpiForMonitor is None or not hmonitor:
            return 96
        dpi_x = api.wintypes.UINT(96)
        dpi_y = api.wintypes.UINT(96)
        try:
            hr = api.GetDpiForMonitor(
                int(hmonitor), MDT_EFFECTIVE_DPI,
                api.ctypes.byref(dpi_x), api.ctypes.byref(dpi_y),
            )
            if hr == 0 and int(dpi_x.value) > 0:
                return int(dpi_x.value)
        except Exception as exc:
            logger.debug("GetDpiForMonitor fallo: %s", exc)
        return 96

    def _display_from_hmonitor(self, api: _Win32Api, hmonitor: int) -> Optional[DisplayInfo]:
        info = api.MONITORINFOEXW()
        info.cbSize = api.ctypes.sizeof(api.MONITORINFOEXW)
        if not api.GetMonitorInfoW(int(hmonitor), api.ctypes.byref(info)):
            return None
        bounds = self._rect(info.rcMonitor)
        work = self._rect(info.rcWork)
        if not bounds.is_valid():
            return None
        device_name = str(info.szDevice or "").strip()
        dpi = self._monitor_dpi(api, int(hmonitor))
        rotation = 0
        refresh: Optional[float] = None
        mode_size: Optional[Tuple[int, int]] = None
        try:
            mode = api.DEVMODEW()
            mode.dmSize = api.ctypes.sizeof(api.DEVMODEW)
            if api.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, api.ctypes.byref(mode)):
                rotation = DMDO_DEGREES.get(int(mode.dmDisplayOrientation), 0)
                frequency = int(mode.dmDisplayFrequency)
                # 0 y 1 significan "frecuencia por defecto del hardware".
                refresh = float(frequency) if frequency > 1 else None
                mode_size = (int(mode.dmPelsWidth), int(mode.dmPelsHeight))
        except Exception as exc:
            logger.debug("EnumDisplaySettingsW(%s) fallo: %s", device_name, exc)
        display_id, friendly = self._device_identity(api, device_name)
        return DisplayInfo(
            display_id=display_id,
            name=friendly or device_name,
            bounds=bounds,
            work_area=work,
            pixel_width=int(bounds.width),
            pixel_height=int(bounds.height),
            scale_factor=float(dpi) / 96.0,
            dpi=int(dpi),
            is_primary=bool(int(info.dwFlags) & MONITORINFOF_PRIMARY),
            rotation=rotation,
            refresh_rate=refresh,
            coordinate_space=DESKTOP_PIXELS,
            native_handle=int(hmonitor),
            extra={
                "device_name": device_name,
                "mode_pixels": list(mode_size) if mode_size else None,
            },
        )

    def _display_for_window(
        self,
        api: _Win32Api,
        hwnd: int,
        cache: Optional[Dict[int, Optional[DisplayInfo]]] = None,
    ) -> Optional[DisplayInfo]:
        hmon = api.MonitorFromWindow(int(hwnd), MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        hmon = int(hmon)
        if cache is not None and hmon in cache:
            return cache[hmon]
        display = self._display_from_hmonitor(api, hmon)
        if cache is not None:
            cache[hmon] = display
        return display

    def _display_for_point(self, api: _Win32Api, x: float, y: float) -> Optional[DisplayInfo]:
        hmon = api.MonitorFromPoint(api.POINT(int(round(x)), int(round(y))), MONITOR_DEFAULTTONULL)
        return self._display_from_hmonitor(api, int(hmon)) if hmon else None

    def _all_displays(self, api: _Win32Api) -> List[DisplayInfo]:
        handles: List[int] = []

        def _callback(hmonitor: Any, _hdc: Any, _rect: Any, _lparam: Any) -> bool:
            try:
                handles.append(int(hmonitor or 0))
            except Exception as exc:
                logger.debug("EnumDisplayMonitors callback: %s", exc)
            return True

        proc = api.MONITORENUMPROC(_callback)
        api.EnumDisplayMonitors(None, None, proc, 0)
        displays: List[DisplayInfo] = []
        for hmon in handles:
            if not hmon:
                continue
            display = self._display_from_hmonitor(api, hmon)
            if display is not None:
                displays.append(display)
        displays.sort(key=lambda d: (not d.is_primary, d.bounds.top, d.bounds.left, d.display_id))
        return displays

    def _virtual_desktop(self, api: _Win32Api) -> Optional[Rect]:
        displays = self._all_displays(api)
        if not displays:
            return None
        return Rect(
            min(d.bounds.left for d in displays),
            min(d.bounds.top for d in displays),
            max(d.bounds.right for d in displays),
            max(d.bounds.bottom for d in displays),
        )

    def _window_dpi(self, api: _Win32Api, hwnd: int) -> Optional[int]:
        if api.GetDpiForWindow is None:
            return None
        try:
            value = int(api.GetDpiForWindow(int(hwnd)))
            return value if value > 0 else None
        except Exception:
            return None

    def _context_awareness(self, api: _Win32Api, context: Any) -> Optional[str]:
        if not context or api.GetAwarenessFromDpiAwarenessContext is None:
            return None
        try:
            if api.AreDpiAwarenessContextsEqual is not None and api.AreDpiAwarenessContextsEqual(
                api.ctypes.c_void_p(context),
                api.ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2),
            ):
                return "per_monitor_aware_v2"
            value = int(api.GetAwarenessFromDpiAwarenessContext(api.ctypes.c_void_p(context)))
            return DPI_AWARENESS_NAMES.get(value, "unknown")
        except Exception as exc:
            logger.debug("No se pudo interpretar el contexto DPI: %s", exc)
            return None

    def _window_awareness(self, api: _Win32Api, hwnd: int) -> Optional[str]:
        if api.GetWindowDpiAwarenessContext is None:
            return None
        try:
            return self._context_awareness(api, api.GetWindowDpiAwarenessContext(int(hwnd)))
        except Exception:
            return None

    def _process_awareness(self, api: _Win32Api, pid: Optional[int]) -> Optional[str]:
        """Awareness de un proceso (``None`` = el propio JARVIS)."""
        if api.GetProcessDpiAwareness is None:
            return None
        handle = None
        opened = False
        try:
            if pid is None:
                handle = None
            else:
                handle = api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
                if not handle:
                    return None
                opened = True
            value = api.ctypes.c_int(-1)
            hr = api.GetProcessDpiAwareness(handle, api.ctypes.byref(value))
            if hr != 0:
                return None
            return DPI_AWARENESS_NAMES.get(int(value.value), "unknown")
        except Exception as exc:
            logger.debug("GetProcessDpiAwareness(%s) fallo: %s", pid, exc)
            return None
        finally:
            if opened and handle:
                api.CloseHandle(handle)

    def _token_elevation(self, api: _Win32Api, process_handle: Any) -> Tuple[Optional[bool], int]:
        token = api.wintypes.HANDLE()
        if not api.OpenProcessToken(process_handle, TOKEN_QUERY, api.ctypes.byref(token)):
            return None, api.last_error()
        try:
            elevation = api.wintypes.DWORD(0)
            returned = api.wintypes.DWORD(0)
            if not api.GetTokenInformation(
                token, TOKEN_ELEVATION_CLASS, api.ctypes.byref(elevation),
                api.ctypes.sizeof(elevation), api.ctypes.byref(returned),
            ):
                return None, api.last_error()
            return bool(elevation.value), 0
        finally:
            api.CloseHandle(token)

    def _is_process_elevated(self, api: _Win32Api, pid: Optional[int]) -> Tuple[Optional[bool], str]:
        """Elevacion de un proceso (``pid=None`` = JARVIS).

        Devuelve ``(valor, detalle)``. Si el token no se puede leer por
        ``ERROR_ACCESS_DENIED`` desde un JARVIS no elevado, el objetivo se
        considera probablemente elevado (``True``) para no interactuar con el.
        """
        if pid is None:
            value, error = self._token_elevation(api, api.GetCurrentProcess())
            return value, ("" if value is not None else "token propio ilegible (error %s)" % error)
        handle = api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            error = api.last_error()
            if error == ERROR_ACCESS_DENIED:
                return True, "OpenProcess denegado: proceso probablemente elevado o protegido"
            return None, "OpenProcess fallo (error %s)" % error
        try:
            value, error = self._token_elevation(api, handle)
            if value is None and error == ERROR_ACCESS_DENIED:
                return True, "token del proceso denegado: proceso probablemente elevado"
            if value is None:
                return None, "token ilegible (error %s)" % error
            return value, ""
        finally:
            api.CloseHandle(handle)

    def _window_info(
        self,
        api: _Win32Api,
        hwnd: int,
        foreground: Optional[int] = None,
        exe_cache: Optional[Dict[int, str]] = None,
        display_cache: Optional[Dict[int, Optional[DisplayInfo]]] = None,
    ) -> Optional[WindowInfo]:
        if not self._is_window(api, hwnd):
            return None
        hwnd = int(hwnd)
        pid = self._window_pid(api, hwnd)
        if foreground is None:
            foreground = self._foreground(api)
        exstyle = self._exstyle(api, hwnd)
        cloaked = self._is_cloaked(api, hwnd)
        dpi = self._window_dpi(api, hwnd)
        display = None
        try:
            display = self._display_for_window(api, hwnd, cache=display_cache)
        except Exception as exc:
            logger.debug("No se pudo resolver el monitor de HWND=%s: %s", hwnd, exc)
        owner = api.GetWindow(hwnd, GW_OWNER)
        return WindowInfo(
            window_id=hwnd,
            pid=pid,
            title=self._window_text(api, hwnd),
            app_identity=self._exe_name(pid, exe_cache).lower(),
            bounds=self._window_rect(api, hwnd),
            client_bounds=self._client_rect(api, hwnd),
            frame_bounds=self._frame_rect(api, hwnd),
            is_visible=bool(api.IsWindowVisible(hwnd)) and not cloaked,
            is_minimized=bool(api.IsIconic(hwnd)),
            is_maximized=bool(api.IsZoomed(hwnd)),
            is_foreground=bool(foreground == hwnd),
            display_id=display.display_id if display else None,
            scale_factor=(float(dpi) / 96.0) if dpi else (display.scale_factor if display else None),
            dpi=dpi if dpi else (display.dpi if display else None),
            dpi_awareness=self._window_awareness(api, hwnd),
            coordinate_space=DESKTOP_PIXELS,
            extra={
                "class_name": self._class_name(api, hwnd),
                "is_cloaked": cloaked,
                "is_topmost": bool(exstyle & WS_EX_TOPMOST),
                "is_tool_window": bool(exstyle & WS_EX_TOOLWINDOW),
                "has_owner": bool(owner),
                "owner_window_id": int(owner) if owner else None,
                "is_enabled": bool(api.IsWindowEnabled(hwnd)),
            },
        )

    def _require_window(self, api: _Win32Api, operation: str, window_id: int) -> Tuple[Optional[WindowInfo], Optional[PlatformResult[Any]]]:
        info = self._window_info(api, int(window_id))
        if info is None:
            return None, self._fail(
                operation, PlatformErrorCode.WINDOW_GONE,
                "La ventana %s no existe" % window_id, window_id=int(window_id),
            )
        return info, None

    def _blocked_by_elevation(self, api: _Win32Api, operation: str, info: WindowInfo) -> Optional[PlatformResult[Any]]:
        target, target_detail = self._is_process_elevated(api, info.pid)
        own, _ = self._is_process_elevated(api, None)
        if target and not own:
            return self._fail(
                operation,
                PlatformErrorCode.PROTECTED,
                "La ventana pertenece a un proceso elevado y JARVIS no lo esta; no se intenta eludir UIPI",
                window_id=info.window_id,
                detail=target_detail,
            )
        return None

    # ------------------------------------------------------------------
    # Capacidades y permisos
    # ------------------------------------------------------------------

    @staticmethod
    def _module_available(name: str) -> Tuple[bool, str]:
        try:
            __import__(name)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        now = time.monotonic()
        if self._capabilities_cache is not None and now - self._capabilities_time < self._capabilities_ttl:
            return dict(self._capabilities_cache)
        reports: Dict[Capability, CapabilityReport] = {}
        api = self._get_api()
        launch_detail = (
            "lo gestiona el adaptador de lanzamiento (src.hands.apps.platform_launch), "
            "no el adaptador de escritorio"
        )
        if api is None:
            for cap in Capability:
                reports[cap] = CapabilityReport(
                    cap, CapabilityStatus.NO_SOPORTADO, self._api_error or "API Win32 no disponible"
                )
            return reports

        for cap in (Capability.DISCOVER, Capability.RESOLVE, Capability.PREFLIGHT, Capability.LAUNCH):
            reports[cap] = CapabilityReport(cap, CapabilityStatus.NO_SOPORTADO, launch_detail)

        psutil_ok, psutil_err = self._module_available("psutil")
        reports[Capability.PROCESS_VERIFY] = CapabilityReport(
            Capability.PROCESS_VERIFY,
            CapabilityStatus.DISPONIBLE if psutil_ok else CapabilityStatus.NO_SOPORTADO,
            "" if psutil_ok else "psutil no disponible: %s" % psutil_err,
            backend="psutil",
        )
        for cap in (Capability.WINDOW_VERIFY, Capability.WINDOW_CONTROL, Capability.DISPLAY_ENUM):
            reports[cap] = CapabilityReport(cap, CapabilityStatus.DISPONIBLE, "Win32", backend="win32")

        mss_ok, mss_err = self._module_available("mss")
        dx_ok, _dx_err = self._module_available("dxcam")
        backend = "mss" + ("+dxcam" if dx_ok else "")
        reports[Capability.SCREEN_CAPTURE] = CapabilityReport(
            Capability.SCREEN_CAPTURE,
            CapabilityStatus.DISPONIBLE if mss_ok else CapabilityStatus.NO_SOPORTADO,
            "" if mss_ok else "mss no disponible: %s" % mss_err,
            backend=backend,
        )

        input_status = CapabilityStatus.DISPONIBLE if api.SendInput is not None else CapabilityStatus.NO_SOPORTADO
        reports[Capability.INPUT_CONTROL] = CapabilityReport(
            Capability.INPUT_CONTROL,
            input_status,
            "SetCursorPos/SendInput; UIPI impide enviar entradas a procesos elevados si JARVIS no lo esta",
            backend="sendinput",
        )

        uia_ok, uia_err = self._module_available("pywinauto")
        if not uia_ok:
            com_ok, com_err = self._module_available("comtypes")
            uia_ok = com_ok
            uia_err = uia_err if not com_ok else ""
        reports[Capability.ACCESSIBILITY_TREE] = CapabilityReport(
            Capability.ACCESSIBILITY_TREE,
            CapabilityStatus.DISPONIBLE if uia_ok else CapabilityStatus.NO_SOPORTADO,
            "" if uia_ok else "pywinauto/comtypes no disponibles: %s" % uia_err,
            backend="uia",
        )

        reports[Capability.AUDIO_INPUT] = self._audio_input_report()
        self._capabilities_cache = dict(reports)
        self._capabilities_time = now
        return reports

    def _audio_input_report(self) -> CapabilityReport:
        mic = self._microphone_permission()
        if mic.status == CapabilityStatus.SIN_PERMISO:
            return CapabilityReport(
                Capability.AUDIO_INPUT, CapabilityStatus.SIN_PERMISO, mic.detail, mic.instructions, "sounddevice"
            )
        try:
            import sounddevice  # type: ignore

            devices = sounddevice.query_devices(kind="input")
            if not devices:
                return CapabilityReport(
                    Capability.AUDIO_INPUT, CapabilityStatus.NO_SOPORTADO,
                    "no hay dispositivo de entrada de audio", backend="sounddevice",
                )
            return CapabilityReport(
                Capability.AUDIO_INPUT, CapabilityStatus.DISPONIBLE, mic.detail, backend="sounddevice"
            )
        except Exception as exc:
            return CapabilityReport(
                Capability.AUDIO_INPUT, CapabilityStatus.NO_SOPORTADO,
                "sounddevice o dispositivo no disponible: %s" % exc, backend="sounddevice",
            )

    def _microphone_permission(self) -> PermissionStatus:
        """Consentimiento de microfono de Windows (Configuracion > Privacidad)."""
        instructions = (
            "Abrir Configuracion > Privacidad y seguridad > Microfono y activar "
            "'Acceso al microfono' y 'Permitir que las aplicaciones de escritorio "
            "accedan al microfono'."
        )
        if sys.platform != "win32":
            return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.NO_SOPORTADO, "solo Windows")
        try:
            import winreg  # type: ignore

            base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
            checks = (
                (winreg.HKEY_LOCAL_MACHINE, base, "equipo"),
                (winreg.HKEY_CURRENT_USER, base, "usuario"),
                (winreg.HKEY_CURRENT_USER, base + r"\NonPackaged", "aplicaciones de escritorio"),
            )
            seen = False
            for hive, path, label in checks:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        value, _kind = winreg.QueryValueEx(key, "Value")
                        seen = True
                        if str(value).strip().lower() == "deny":
                            return PermissionStatus(
                                PermissionKind.MICROPHONE, CapabilityStatus.SIN_PERMISO,
                                "microfono denegado para %s" % label, instructions,
                            )
                except OSError:
                    continue
            detail = "consentimiento permitido" if seen else "sin restriccion de consentimiento registrada"
            return PermissionStatus(PermissionKind.MICROPHONE, CapabilityStatus.DISPONIBLE, detail)
        except Exception as exc:
            return PermissionStatus(
                PermissionKind.MICROPHONE, CapabilityStatus.NO_VERIFICADO,
                "no se pudo leer el consentimiento de microfono: %s" % exc, instructions,
            )

    def check_permissions(self) -> List[PermissionStatus]:
        api = self._get_api()
        if api is None:
            return [
                PermissionStatus(kind, CapabilityStatus.NO_SOPORTADO, self._api_error or "")
                for kind in PermissionKind
            ]
        result: List[PermissionStatus] = []
        uia_ok, uia_err = self._module_available("pywinauto")
        result.append(PermissionStatus(
            PermissionKind.ACCESSIBILITY,
            CapabilityStatus.DISPONIBLE if uia_ok else CapabilityStatus.NO_SOPORTADO,
            "UI Automation no requiere permiso en Windows" if uia_ok else "pywinauto no disponible: %s" % uia_err,
        ))
        result.append(PermissionStatus(
            PermissionKind.SCREEN_RECORDING, CapabilityStatus.DISPONIBLE,
            "Windows no exige permiso de captura; el contenido protegido (WDA) se detecta por ventana",
        ))
        result.append(self._microphone_permission())
        result.append(PermissionStatus(
            PermissionKind.AUTOMATION, CapabilityStatus.DISPONIBLE,
            "Windows no exige permiso de automatizacion entre aplicaciones",
        ))
        own, detail = self._is_process_elevated(api, None)
        result.append(PermissionStatus(
            PermissionKind.INPUT_INJECTION, CapabilityStatus.DISPONIBLE,
            "SendInput disponible; UIPI bloquea entradas hacia procesos elevados"
            + ("" if own else " (JARVIS no esta elevado)"),
        ))
        result.append(PermissionStatus(
            PermissionKind.ELEVATION,
            CapabilityStatus.DISPONIBLE if own is not None else CapabilityStatus.NO_VERIFICADO,
            ("JARVIS se ejecuta elevado" if own else "JARVIS se ejecuta sin elevar; no interactua con ventanas elevadas")
            if own is not None else detail,
        ))
        return result

    # ------------------------------------------------------------------
    # Monitores
    # ------------------------------------------------------------------

    def enumerate_displays(self) -> PlatformResult[List[DisplayInfo]]:
        def _impl(api: _Win32Api) -> PlatformResult[List[DisplayInfo]]:
            displays = self._all_displays(api)
            if not displays:
                return self._fail(
                    "enumerate_displays", PlatformErrorCode.NOT_FOUND,
                    "EnumDisplayMonitors no devolvio monitores",
                )
            return PlatformResult.success(displays, count=len(displays))

        return self._run("enumerate_displays", _impl)

    def start_display_change_listener(self, callback: Callable[[str], None]) -> PlatformResult[Any]:
        if not callable(callback):
            return self._fail(
                "start_display_change_listener", PlatformErrorCode.INVALID_ARGUMENT,
                "callback no invocable",
            )
        api = self._get_api()
        if api is None:
            return self._fail(
                "start_display_change_listener", PlatformErrorCode.NOT_SUPPORTED,
                self._api_error or "API Win32 no disponible",
            )
        listener = _DisplayChangeListener(api, callback)
        try:
            started = listener.start()
        except Exception as exc:
            return self._fail(
                "start_display_change_listener", PlatformErrorCode.NATIVE_ERROR,
                "No se pudo iniciar el listener de pantallas", native_error=exc,
            )
        if not started:
            listener.stop(timeout=1.0)
            return self._fail(
                "start_display_change_listener", PlatformErrorCode.NATIVE_ERROR,
                "El listener de pantallas no arranco", native_error=listener.error or "",
            )
        handle = id(listener)
        self._listeners[handle] = listener
        return PlatformResult.success(handle, mechanism="hidden_toplevel_window")

    def stop_display_change_listener(self, handle: Any) -> PlatformResult[None]:
        listener = self._listeners.pop(handle, None)
        if listener is None:
            return self._fail(
                "stop_display_change_listener", PlatformErrorCode.NOT_FOUND,
                "No existe un listener con ese manejador",
            )
        stopped = listener.stop()
        if not stopped:
            return self._fail(
                "stop_display_change_listener", PlatformErrorCode.TIMEOUT,
                "El hilo del listener no termino a tiempo",
            )
        return PlatformResult.success(None)

    # ------------------------------------------------------------------
    # Ventanas
    # ------------------------------------------------------------------

    def list_windows(
        self,
        pid: Optional[int] = None,
        app_identity: Optional[str] = None,
        visible_only: bool = True,
    ) -> PlatformResult[List[WindowInfo]]:
        identity = (app_identity or "").strip().lower()
        if identity and not identity.endswith(".exe"):
            identity_alt = identity + ".exe"
        else:
            identity_alt = identity

        def _impl(api: _Win32Api) -> PlatformResult[List[WindowInfo]]:
            handles: List[int] = []

            def _callback(hwnd: Any, _lparam: Any) -> bool:
                try:
                    if hwnd:
                        handles.append(int(hwnd))
                except Exception as exc:
                    logger.debug("EnumWindows callback: %s", exc)
                return True

            proc = api.WNDENUMPROC(_callback)
            api.EnumWindows(proc, 0)
            foreground = self._foreground(api)
            exe_cache: Dict[int, str] = {}
            display_cache: Dict[int, Optional[DisplayInfo]] = {}
            windows: List[WindowInfo] = []
            for hwnd in handles:
                try:
                    if visible_only and not api.IsWindowVisible(hwnd):
                        continue
                    window_pid = self._window_pid(api, hwnd)
                    if pid is not None and window_pid != int(pid):
                        continue
                    if identity:
                        exe = self._exe_name(window_pid, exe_cache).lower()
                        if exe not in (identity, identity_alt):
                            continue
                    info = self._window_info(
                        api, hwnd, foreground=foreground,
                        exe_cache=exe_cache, display_cache=display_cache,
                    )
                    if info is None:
                        continue
                    if visible_only:
                        if not info.is_visible:
                            continue
                        if info.bounds is None or (not info.bounds.is_valid() and not info.is_minimized):
                            continue
                    windows.append(info)
                except Exception as exc:
                    logger.debug("list_windows: HWND=%s omitida: %s", hwnd, exc)
            return PlatformResult.success(windows, count=len(windows))

        return self._run("list_windows", _impl)

    def get_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, "get_window", window_id)
            if error is not None:
                return error
            return PlatformResult.success(info)

        return self._run("get_window", _impl)

    def get_foreground_window(self) -> PlatformResult[Optional[WindowInfo]]:
        def _impl(api: _Win32Api) -> PlatformResult[Optional[WindowInfo]]:
            hwnd = self._foreground(api)
            if not hwnd:
                return PlatformResult.success(None, reason="sin ventana en primer plano")
            return PlatformResult.success(self._window_info(api, hwnd, foreground=hwnd))

        return self._run("get_foreground_window", _impl)

    def window_at_point(self, x: float, y: float) -> PlatformResult[Optional[WindowInfo]]:
        def _impl(api: _Win32Api) -> PlatformResult[Optional[WindowInfo]]:
            hwnd = api.WindowFromPoint(api.POINT(int(round(x)), int(round(y))))
            if not hwnd:
                return PlatformResult.success(None, reason="ninguna ventana bajo el punto")
            root = self._root(api, int(hwnd))
            return PlatformResult.success(
                self._window_info(api, root) if root else None,
                child_window_id=int(hwnd),
            )

        return self._run("window_at_point", _impl)

    def _restore_if_needed(self, api: _Win32Api, hwnd: int) -> bool:
        if api.IsIconic(hwnd) or api.IsZoomed(hwnd):
            api.ShowWindow(hwnd, SW_RESTORE)
            return _wait_until(
                lambda: not api.IsIconic(hwnd) and not api.IsZoomed(hwnd), WINDOW_STATE_TIMEOUT
            )
        return True

    def move_window_to_display(self, window_id: int, display_id: str) -> PlatformResult[WindowInfo]:
        operation = "move_window_to_display"

        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            blocked = self._blocked_by_elevation(api, operation, info)
            if blocked is not None:
                return blocked
            target = next((d for d in self._all_displays(api) if d.display_id == display_id), None)
            if target is None:
                return self._fail(
                    operation, PlatformErrorCode.NOT_FOUND,
                    "El monitor %s no existe en la topologia actual" % display_id,
                )
            hwnd = int(window_id)
            if info.display_id == target.display_id and not info.is_minimized:
                return PlatformResult.success(info, moved=False)
            if not self._restore_if_needed(api, hwnd):
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "No se pudo restaurar la ventana antes de moverla",
                )
            current = self._window_rect(api, hwnd)
            if current is None:
                return self._fail(operation, PlatformErrorCode.WINDOW_GONE, "La ventana desaparecio")
            work = target.work_area if target.work_area.is_valid() else target.bounds
            width = int(min(current.width, work.width))
            height = int(min(current.height, work.height))
            x = int(work.left + max(0, (work.width - width) // 2))
            y = int(work.top + max(0, (work.height - height) // 2))
            if not api.SetWindowPos(hwnd, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE):
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "SetWindowPos fallo", native_error="error %s" % api.last_error(),
                )

            def _on_target() -> bool:
                display = self._display_for_window(api, hwnd)
                return bool(display is not None and display.display_id == target.display_id)

            if not _wait_until(_on_target, WINDOW_STATE_TIMEOUT):
                current_display = self._display_for_window(api, hwnd)
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana no quedo en el monitor solicitado",
                    expected_display=target.display_id,
                    actual_display=current_display.display_id if current_display else None,
                )
            return PlatformResult.success(self._window_info(api, hwnd), moved=True)

        return self._run(operation, _impl)

    def maximize_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        operation = "maximize_window"

        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            blocked = self._blocked_by_elevation(api, operation, info)
            if blocked is not None:
                return blocked
            hwnd = int(window_id)
            if api.IsIconic(hwnd):
                api.ShowWindow(hwnd, SW_RESTORE)
                _wait_until(lambda: not api.IsIconic(hwnd), WINDOW_STATE_TIMEOUT)
            if not api.IsZoomed(hwnd):
                api.ShowWindow(hwnd, SW_MAXIMIZE)
            if not _wait_until(lambda: bool(api.IsZoomed(hwnd)), WINDOW_STATE_TIMEOUT):
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana no quedo maximizada (puede no admitir maximizar)",
                )
            result = self._window_info(api, hwnd)
            if result is None:
                return self._fail(operation, PlatformErrorCode.WINDOW_GONE, "La ventana desaparecio")
            display = self._display_for_window(api, hwnd)
            matches = None
            if display is not None and result.frame_bounds is not None:
                fb, wa = result.frame_bounds, display.work_area
                matches = (
                    abs(fb.left - wa.left) <= 2 and abs(fb.top - wa.top) <= 2
                    and abs(fb.right - wa.right) <= 2 and abs(fb.bottom - wa.bottom) <= 2
                )
            return PlatformResult.success(
                result,
                frame_matches_work_area=matches,
                display_id=display.display_id if display else None,
            )

        return self._run(operation, _impl)

    def restore_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        operation = "restore_window"

        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            blocked = self._blocked_by_elevation(api, operation, info)
            if blocked is not None:
                return blocked
            hwnd = int(window_id)
            if not self._restore_if_needed(api, hwnd):
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana no quedo restaurada",
                )
            return PlatformResult.success(self._window_info(api, hwnd))

        return self._run(operation, _impl)

    def set_window_bounds(self, window_id: int, bounds: Rect) -> PlatformResult[WindowInfo]:
        operation = "set_window_bounds"
        if bounds is None or not bounds.is_valid():
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Rectangulo invalido")

        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            blocked = self._blocked_by_elevation(api, operation, info)
            if blocked is not None:
                return blocked
            hwnd = int(window_id)
            if not self._restore_if_needed(api, hwnd):
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "No se pudo restaurar la ventana antes de redimensionarla",
                )
            left, top, right, bottom = bounds.to_int_tuple()
            if not api.SetWindowPos(
                hwnd, None, left, top, right - left, bottom - top, SWP_NOZORDER | SWP_NOACTIVATE
            ):
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "SetWindowPos fallo", native_error="error %s" % api.last_error(),
                )

            def _applied() -> bool:
                rect = self._window_rect(api, hwnd)
                return bool(rect is not None and abs(rect.left - left) <= 2 and abs(rect.top - top) <= 2)

            applied = _wait_until(_applied, WINDOW_STATE_TIMEOUT)
            result = self._window_info(api, hwnd)
            if not applied:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana no adopto la posicion solicitada",
                    requested=bounds.to_dict(),
                    actual=result.bounds.to_dict() if result and result.bounds else None,
                )
            return PlatformResult.success(result)

        return self._run(operation, _impl)

    def _try_foreground(self, api: _Win32Api, hwnd: int) -> Tuple[bool, str]:
        """Intenta poner ``hwnd`` en primer plano sin enviar teclado ni raton.

        1. ``SetForegroundWindow``.
        2. Si el bloqueo de primer plano lo impide, se adjunta temporalmente la
           cola de entrada del hilo actual a la del hilo en primer plano
           (``AttachThreadInput``), se repite y se desadjunta siempre.
        No se simulan pulsaciones (por ejemplo Alt), porque irian a otra ventana.
        """
        api.SetForegroundWindow(hwnd)
        if _wait_until(lambda: self._foreground(api) == hwnd, FOREGROUND_TIMEOUT / 2):
            return True, "set_foreground"
        current_thread = int(api.GetCurrentThreadId())
        foreground = self._foreground(api)
        foreground_thread = self._window_thread(api, foreground) if foreground else 0
        attached = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached = bool(api.AttachThreadInput(current_thread, foreground_thread, True))
            api.BringWindowToTop(hwnd)
            api.SetForegroundWindow(hwnd)
        finally:
            if attached:
                api.AttachThreadInput(current_thread, foreground_thread, False)
        if _wait_until(lambda: self._foreground(api) == hwnd, FOREGROUND_TIMEOUT):
            return True, "attach_thread_input"
        return False, "foreground_lock"

    def activate_window(self, window_id: int) -> PlatformResult[WindowInfo]:
        operation = "activate_window"

        def _impl(api: _Win32Api) -> PlatformResult[WindowInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            hwnd = int(window_id)
            if not info.is_visible and not info.is_minimized:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana esta oculta; no se activa",
                )
            if api.IsIconic(hwnd):
                api.ShowWindow(hwnd, SW_RESTORE)
                _wait_until(lambda: not api.IsIconic(hwnd), WINDOW_STATE_TIMEOUT)
            ok, method = self._try_foreground(api, hwnd)
            if not ok:
                foreground = self._foreground(api)
                owned = bool(foreground and api.GetAncestor(foreground, GA_ROOTOWNER) == hwnd)
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana no quedo en primer plano",
                    foreground_window_id=foreground,
                    foreground_is_owned_by_target=owned,
                    method=method,
                )
            return PlatformResult.success(self._window_info(api, hwnd, foreground=hwnd), method=method)

        return self._run(operation, _impl)

    def is_foreground(self, window_id: int) -> bool:
        api = self._get_api()
        if api is None:
            return False
        try:
            return self._foreground(api) == int(window_id)
        except Exception as exc:
            logger.debug("is_foreground(%s): %s", window_id, exc)
            return False

    def get_window_dpi_info(self, window_id: int) -> PlatformResult[WindowDpiInfo]:
        operation = "get_window_dpi_info"

        def _impl(api: _Win32Api) -> PlatformResult[WindowDpiInfo]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            hwnd = int(window_id)
            dpi = self._window_dpi(api, hwnd)
            display = self._display_for_window(api, hwnd)
            thread_context = None
            if api.GetThreadDpiAwarenessContext is not None:
                thread_context = api.GetThreadDpiAwarenessContext()
            return PlatformResult.success(WindowDpiInfo(
                window_id=hwnd,
                dpi=dpi if dpi else (display.dpi if display else None),
                scale_factor=(float(dpi) / 96.0) if dpi else (display.scale_factor if display else None),
                window_awareness=self._window_awareness(api, hwnd),
                process_awareness=self._process_awareness(api, info.pid),
                jarvis_awareness=self._process_awareness(api, None),
                display_id=display.display_id if display else None,
                details={
                    "monitor_dpi": display.dpi if display else None,
                    "adapter_thread_awareness": self._context_awareness(api, thread_context),
                    "get_dpi_for_window_available": api.GetDpiForWindow is not None,
                },
            ))

        return self._run(operation, _impl)

    def close_window(self, window_id: int) -> PlatformResult[None]:
        operation = "close_window"

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            if not api.PostMessageW(int(window_id), WM_CLOSE, 0, 0):
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "PostMessageW(WM_CLOSE) fallo", native_error="error %s" % api.last_error(),
                )
            return PlatformResult.success(None, requested="WM_CLOSE")

        return self._run(operation, _impl)

    # ------------------------------------------------------------------
    # Procesos
    # ------------------------------------------------------------------

    def process_identity(self, pid: int) -> PlatformResult[Dict[str, Any]]:
        base = super().process_identity(pid)
        if not base.ok:
            return base
        identity = dict(base.value or {})
        api = self._get_api()
        if api is not None:
            try:
                elevated, detail = self._is_process_elevated(api, int(pid))
                identity["is_elevated"] = elevated
                if detail:
                    identity["elevation_detail"] = detail
            except Exception as exc:
                logger.debug("process_identity: elevacion de %s no leida: %s", pid, exc)
        identity["name"] = str(identity.get("name", "")).lower()
        return PlatformResult.success(identity)

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------

    def _capture_mss(self, region: Rect) -> Tuple[Any, str]:
        """Captura una region con ``MssCapture`` (frame BGRA) o devuelve el error."""
        from src.eyes.capture.screen_capture import MssCapture

        capture = MssCapture()
        try:
            if not capture.available:
                return None, str(capture.error or "mss no disponible")
            left, top, right, bottom = region.to_int_tuple()
            frame = capture.capture_region(left, top, right - left, bottom - top)
            if frame is None:
                return None, str(capture.error or "mss no devolvio frame")
            return frame, ""
        finally:
            capture.close()

    def _capture_result(
        self,
        region: Rect,
        frame: Any,
        backend: str,
        channels: str,
        window_id: Optional[int] = None,
        display_id: Optional[str] = None,
    ) -> CaptureResult:
        height, width = int(frame.shape[0]), int(frame.shape[1])
        return CaptureResult(
            region=region,
            pixel_width=width,
            pixel_height=height,
            backend=backend,
            image=frame,
            channels=channels,
            pixels_per_unit_x=float(width) / float(region.width) if region.width else 1.0,
            pixels_per_unit_y=float(height) / float(region.height) if region.height else 1.0,
            captured_at=time.monotonic(),
            window_id=window_id,
            display_id=display_id,
            coordinate_space=DESKTOP_PIXELS,
        )

    def _capture_display_dxcam(self, display: DisplayInfo) -> Tuple[Any, str]:
        """Captura un monitor con DXcam si su salida se identifica sin ambiguedad."""
        try:
            from src.eyes.capture.screen_capture import DXcamCapture
        except Exception as exc:
            return None, "DXcamCapture no importable: %s" % exc
        probe = DXcamCapture(output_idx=0)
        if not probe.available:
            return None, str(probe.error or "dxcam no disponible")
        outputs = probe.enumerate_outputs()
        matches = [
            out for out in outputs
            if int(out.get("width", 0)) == int(display.pixel_width)
            and int(out.get("height", 0)) == int(display.pixel_height)
            and bool(out.get("primary")) == bool(display.is_primary)
        ]
        if len(matches) != 1:
            return None, "salida dxcam no identificable sin ambiguedad (%d coincidencias)" % len(matches)
        camera = DXcamCapture(output_idx=int(matches[0]["output_idx"]))
        try:
            if not camera.start():
                return None, str(camera.error or "dxcam no arranco")
            frame = None
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                candidate = camera.grab()
                if candidate is not None and not camera.fallback_active:
                    frame = candidate
                    break
                time.sleep(POLL_INTERVAL)
            if frame is None:
                return None, "dxcam no entrego un frame fresco: %s" % (camera.error or "sin frame")
            return frame, ""
        finally:
            camera.stop()
            camera.release()

    def capture_display(self, display_id: str) -> PlatformResult[CaptureResult]:
        operation = "capture_display"

        def _impl(api: _Win32Api) -> PlatformResult[CaptureResult]:
            display = next((d for d in self._all_displays(api) if d.display_id == display_id), None)
            if display is None:
                return self._fail(
                    operation, PlatformErrorCode.NOT_FOUND,
                    "El monitor %s no existe en la topologia actual" % display_id,
                )
            dxcam_error = ""
            if self.capture_backend in ("dxcam", "auto"):
                frame, dxcam_error = self._capture_display_dxcam(display)
                if frame is not None:
                    return PlatformResult.success(
                        self._capture_result(display.bounds, frame, "dxcam", "RGB", display_id=display.display_id)
                    )
                logger.info("capture_display: DXcam no utilizable, se usa mss: %s", dxcam_error)
            frame, error = self._capture_mss(display.bounds)
            if frame is None:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "No se pudo capturar el monitor", native_error=error,
                    dxcam_error=dxcam_error or None,
                )
            return PlatformResult.success(
                self._capture_result(display.bounds, frame, "mss", "BGRA", display_id=display.display_id),
                dxcam_error=dxcam_error or None,
            )

        return self._run(operation, _impl)

    def capture_region(self, region: Rect) -> PlatformResult[CaptureResult]:
        operation = "capture_region"
        if region is None or not region.is_valid():
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Region invalida")

        def _impl(api: _Win32Api) -> PlatformResult[CaptureResult]:
            desktop = self._virtual_desktop(api)
            if desktop is None or not desktop.contains_rect(region):
                return self._fail(
                    operation, PlatformErrorCode.INVALID_ARGUMENT,
                    "La region queda fuera del escritorio virtual",
                    region=region.to_dict(), desktop=desktop.to_dict() if desktop else None,
                )
            frame, error = self._capture_mss(region)
            if frame is None:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR, "No se pudo capturar la region",
                    native_error=error,
                )
            display = self._display_for_point(api, *region.center)
            return PlatformResult.success(self._capture_result(
                region, frame, "mss", "BGRA",
                display_id=display.display_id if display else None,
            ))

        return self._run(operation, _impl)

    def _occluding_windows(self, api: _Win32Api, info: WindowInfo, area: Rect) -> Tuple[List[int], List[Dict[str, Any]]]:
        """Ventanas por encima de ``info`` en orden Z que cubren parte de ``area``.

        Se ignoran las ventanas del propio proceso objetivo y sus ventanas
        propias, las invisibles, ocultas por DWM, minimizadas, las capas con
        alfa 0 y las capas transparentes al raton (se informan aparte).
        """
        overlays: List[int] = []
        ignored: List[Dict[str, Any]] = []
        hwnd = int(info.window_id)
        current = api.GetWindow(hwnd, GW_HWNDPREV)
        guard = 0
        while current and guard < 1000:
            guard += 1
            other = int(current)
            current = api.GetWindow(other, GW_HWNDPREV)
            try:
                if not api.IsWindowVisible(other) or api.IsIconic(other) or self._is_cloaked(api, other):
                    continue
                if self._window_pid(api, other) == info.pid:
                    continue
                if api.GetAncestor(other, GA_ROOTOWNER) == hwnd:
                    continue
                rect = self._frame_rect(api, other) or self._window_rect(api, other)
                if rect is None:
                    continue
                inter = area.intersection_area(rect)
                if inter <= 0 or inter < OVERLAY_MIN_AREA_RATIO * area.area:
                    continue
                exstyle = self._exstyle(api, other)
                class_name = self._class_name(api, other)
                if exstyle & WS_EX_LAYERED:
                    alpha = api.wintypes.BYTE(255)
                    flags = api.wintypes.DWORD(0)
                    if api.GetLayeredWindowAttributes is not None and api.GetLayeredWindowAttributes(
                        other, None, api.ctypes.byref(alpha), api.ctypes.byref(flags)
                    ):
                        if (int(flags.value) & LWA_ALPHA) and int(alpha.value) == 0:
                            ignored.append({"window_id": other, "class_name": class_name, "reason": "alpha_0"})
                            continue
                    if exstyle & WS_EX_TRANSPARENT:
                        ignored.append({"window_id": other, "class_name": class_name, "reason": "click_through"})
                        continue
                overlays.append(other)
            except Exception as exc:
                logger.debug("_occluding_windows: HWND=%s omitida: %s", other, exc)
        return overlays, ignored

    def capture_window(self, window_id: int) -> PlatformResult[CaptureResult]:
        operation = "capture_window"

        def _impl(api: _Win32Api) -> PlatformResult[CaptureResult]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            if info.is_minimized or not info.is_visible:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana esta minimizada u oculta; no se captura",
                )
            if api.GetWindowDisplayAffinity is not None:
                affinity = api.wintypes.DWORD(0)
                if api.GetWindowDisplayAffinity(int(window_id), api.ctypes.byref(affinity)) and int(affinity.value) != WDA_NONE:
                    return self._fail(
                        operation, PlatformErrorCode.PROTECTED,
                        "La ventana protege su contenido frente a captura (display affinity)",
                        affinity=int(affinity.value),
                    )
            area = info.frame_bounds or info.bounds
            desktop = self._virtual_desktop(api)
            if area is None or desktop is None:
                return self._fail(operation, PlatformErrorCode.NATIVE_ERROR, "Geometria de ventana no disponible")
            visible = area.intersection(desktop)
            if visible is None:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana esta fuera de todos los monitores",
                )
            overlays, _ignored = self._occluding_windows(api, info, visible)
            if overlays:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "La ventana esta cubierta por otras ventanas; activarla antes de capturar",
                    overlay_windows=overlays,
                    is_foreground=info.is_foreground,
                )
            frame, cap_error = self._capture_mss(visible)
            if frame is None:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR, "No se pudo capturar la ventana",
                    native_error=cap_error,
                )
            return PlatformResult.success(
                self._capture_result(
                    visible, frame, "mss", "BGRA",
                    window_id=int(window_id), display_id=info.display_id,
                ),
                clipped=not visible.contains_rect(area) if area else False,
            )

        return self._run(operation, _impl)

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def _pointer(self, api: _Win32Api) -> Optional[PointerPosition]:
        point = api.POINT(0, 0)
        if not api.GetCursorPos(api.ctypes.byref(point)):
            return None
        display = self._display_for_point(api, int(point.x), int(point.y))
        return PointerPosition(
            x=int(point.x), y=int(point.y),
            coordinate_space=DESKTOP_PIXELS,
            display_id=display.display_id if display else None,
        )

    def get_pointer_position(self) -> PlatformResult[PointerPosition]:
        operation = "get_pointer_position"

        def _impl(api: _Win32Api) -> PlatformResult[PointerPosition]:
            position = self._pointer(api)
            if position is None:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "GetCursorPos fallo (posible escritorio seguro o sesion bloqueada)",
                    native_error="error %s" % api.last_error(),
                )
            return PlatformResult.success(position)

        return self._run(operation, _impl)

    def move_pointer(self, x: float, y: float) -> PlatformResult[PointerPosition]:
        operation = "move_pointer"
        try:
            target_x = int(round(float(x)))
            target_y = int(round(float(y)))
        except (TypeError, ValueError):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Coordenadas invalidas")

        def _impl(api: _Win32Api) -> PlatformResult[PointerPosition]:
            if self._display_for_point(api, target_x, target_y) is None:
                return self._fail(
                    operation, PlatformErrorCode.INVALID_ARGUMENT,
                    "El punto no pertenece a ningun monitor",
                    requested=[target_x, target_y],
                )
            if not api.SetCursorPos(target_x, target_y):
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR, "SetCursorPos fallo",
                    native_error="error %s" % api.last_error(),
                )
            position = self._pointer(api)
            if position is None:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "No se pudo leer la posicion real tras mover el puntero",
                )
            return PlatformResult.success(
                position,
                requested=[target_x, target_y],
                error_px=max(abs(position.x - target_x), abs(position.y - target_y)),
            )

        return self._run(operation, _impl)

    def _send_inputs(self, api: _Win32Api, inputs: List[Any]) -> Tuple[bool, int]:
        if not inputs:
            return True, 0
        array_type = api.INPUT * len(inputs)
        array = array_type(*inputs)
        sent = int(api.SendInput(len(inputs), array, api.ctypes.sizeof(api.INPUT)))
        return sent == len(inputs), sent

    def _mouse_input(self, api: _Win32Api, flags: int, data: int = 0) -> Any:
        item = api.INPUT()
        item.type = INPUT_MOUSE
        item.u.mi = api.MOUSEINPUT(0, 0, int(data) & 0xFFFFFFFF, int(flags), 0, 0)
        return item

    def _key_input(self, api: _Win32Api, vk: int, scan: int, flags: int) -> Any:
        item = api.INPUT()
        item.type = INPUT_KEYBOARD
        item.u.ki = api.KEYBDINPUT(int(vk), int(scan), int(flags), 0, 0)
        return item

    def click(self, button: str = "left", count: int = 1) -> PlatformResult[None]:
        operation = "click"
        flags = MOUSE_BUTTON_FLAGS.get(str(button or "").lower())
        if flags is None:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Boton no valido: %s" % button)
        try:
            repeat = int(count)
        except (TypeError, ValueError):
            repeat = 0
        if repeat < 1 or repeat > 3:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "count debe estar entre 1 y 3")

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            down, up = flags
            inputs = []
            for _ in range(repeat):
                inputs.append(self._mouse_input(api, down))
                inputs.append(self._mouse_input(api, up))
            ok, sent = self._send_inputs(api, inputs)
            if not ok:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "SendInput no envio todos los eventos (UIPI o escritorio seguro)",
                    sent=sent, expected=len(inputs), native_error="error %s" % api.last_error(),
                )
            position = self._pointer(api)
            return PlatformResult.success(
                None, button=str(button).lower(), count=repeat,
                position=position.to_dict() if position else None,
            )

        return self._run(operation, _impl)

    def scroll(self, amount: int, horizontal: bool = False) -> PlatformResult[None]:
        operation = "scroll"
        try:
            notches = int(amount)
        except (TypeError, ValueError):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "amount debe ser entero")
        if notches == 0:
            return PlatformResult.success(None, notches=0)

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
            ok, sent = self._send_inputs(api, [self._mouse_input(api, flag, notches * WHEEL_DELTA)])
            if not ok:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR, "SendInput (rueda) fallo",
                    sent=sent, native_error="error %s" % api.last_error(),
                )
            return PlatformResult.success(None, notches=notches, horizontal=bool(horizontal))

        return self._run(operation, _impl)

    def type_text(self, text: str) -> PlatformResult[None]:
        operation = "type_text"
        if not isinstance(text, str):
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "text debe ser str")

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            inputs: List[Any] = []
            for char in text:
                if char == "\r":
                    continue
                if char in ("\n", "\t"):
                    vk = 0x0D if char == "\n" else 0x09
                    inputs.append(self._key_input(api, vk, 0, 0))
                    inputs.append(self._key_input(api, vk, 0, KEYEVENTF_KEYUP))
                    continue
                encoded = char.encode("utf-16-le")
                for i in range(0, len(encoded), 2):
                    unit = encoded[i] | (encoded[i + 1] << 8)
                    inputs.append(self._key_input(api, 0, unit, KEYEVENTF_UNICODE))
                    inputs.append(self._key_input(api, 0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            ok, sent = self._send_inputs(api, inputs)
            if not ok:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "SendInput no envio todo el texto (UIPI o escritorio seguro)",
                    sent=sent, expected=len(inputs),
                )
            return PlatformResult.success(None, characters=len(text))

        return self._run(operation, _impl)

    def _resolve_key(self, api: _Win32Api, key: str) -> Optional[Tuple[int, List[int]]]:
        """(codigo virtual, modificadores implicitos) para una tecla logica o caracter."""
        name = str(key or "").strip()
        lowered = name.lower()
        if lowered in VIRTUAL_KEYS:
            return VIRTUAL_KEYS[lowered], []
        if len(name) == 1:
            if "a" <= lowered <= "z":
                return ord(lowered.upper()), []
            if "0" <= name <= "9":
                return ord(name), []
            scan = int(api.VkKeyScanW(name)) if api.VkKeyScanW is not None else -1
            if scan == -1:
                return None
            vk = scan & 0xFF
            shift_state = (scan >> 8) & 0xFF
            modifiers: List[int] = []
            if shift_state & 1:
                modifiers.append(VIRTUAL_KEYS["shift"])
            if shift_state & 2:
                modifiers.append(VIRTUAL_KEYS["ctrl"])
            if shift_state & 4:
                modifiers.append(VIRTUAL_KEYS["alt"])
            return vk, modifiers
        return None

    def press_keys(self, keys: Sequence[str]) -> PlatformResult[None]:
        operation = "press_keys"
        key_list = [k for k in (keys or []) if str(k or "").strip()]
        if not key_list:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Sin teclas que pulsar")

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            codes: List[int] = []
            for key in key_list:
                resolved = self._resolve_key(api, key)
                if resolved is None:
                    return self._fail(
                        operation, PlatformErrorCode.INVALID_ARGUMENT,
                        "Tecla no soportada: %s" % key,
                    )
                vk, implicit = resolved
                for modifier in implicit + [vk]:
                    if modifier not in codes:
                        codes.append(modifier)
            inputs: List[Any] = []
            for vk in codes:
                flags = KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VIRTUAL_KEYS else 0
                scan = int(api.MapVirtualKeyW(vk, 0)) if api.MapVirtualKeyW is not None else 0
                inputs.append(self._key_input(api, vk, scan, flags))
            for vk in reversed(codes):
                flags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VIRTUAL_KEYS else 0)
                scan = int(api.MapVirtualKeyW(vk, 0)) if api.MapVirtualKeyW is not None else 0
                inputs.append(self._key_input(api, vk, scan, flags))
            ok, sent = self._send_inputs(api, inputs)
            if not ok:
                return self._fail(
                    operation, PlatformErrorCode.NATIVE_ERROR,
                    "SendInput no envio la combinacion (UIPI o escritorio seguro)",
                    sent=sent, expected=len(inputs),
                )
            return PlatformResult.success(None, keys=[str(k) for k in key_list])

        return self._run(operation, _impl)

    # ------------------------------------------------------------------
    # Accesibilidad (UI Automation)
    # ------------------------------------------------------------------

    def _uia_adapter(self, max_depth: int, max_nodes: int) -> Any:
        key = (int(max_depth), int(max_nodes))
        with self._uia_lock:
            adapter = self._uia_adapters.get(key)
            if adapter is None:
                from src.hands.detection.ui_automation_adapter import UIAutomationAdapter

                adapter = UIAutomationAdapter(max_depth=key[0], max_elements=key[1])
                self._uia_adapters[key] = adapter
            return adapter

    def get_accessibility_tree(
        self,
        window_id: int,
        pid: Optional[int] = None,
        max_depth: int = 60,
        max_nodes: int = 2000,
    ) -> PlatformResult[AccessibilityTree]:
        operation = "get_accessibility_tree"

        def _impl(api: _Win32Api) -> PlatformResult[AccessibilityTree]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            if pid is not None and int(pid) != info.pid:
                return self._fail(
                    operation, PlatformErrorCode.INVALID_ARGUMENT,
                    "El PID indicado no corresponde a la ventana",
                    expected_pid=int(pid), window_pid=info.pid,
                )
            adapter = self._uia_adapter(max_depth, max_nodes)
            raw_tree = adapter.enumerate_window(int(window_id), info.pid)
            tree = normalize_uia_tree(raw_tree)
            if raw_tree.error and not tree.nodes:
                code = (
                    PlatformErrorCode.WINDOW_GONE
                    if not self._is_window(api, int(window_id))
                    else PlatformErrorCode.NATIVE_ERROR
                )
                return self._fail(
                    operation, code, "No se pudo leer el arbol UI Automation",
                    native_error=raw_tree.error,
                )
            return PlatformResult.success(
                tree, truncated=tree.truncated, node_count=len(tree.nodes),
                source=str(getattr(raw_tree, "source", "uia")),
            )

        return self._run(operation, _impl)

    def element_at_point(self, x: float, y: float) -> PlatformResult[Optional[AccessibilityNode]]:
        operation = "element_at_point"

        def _impl(api: _Win32Api) -> PlatformResult[Optional[AccessibilityNode]]:
            px, py = int(round(x)), int(round(y))
            hwnd = api.WindowFromPoint(api.POINT(px, py))
            root = self._root(api, int(hwnd)) if hwnd else None
            try:
                from pywinauto.uia_element_info import UIAElementInfo  # type: ignore
            except Exception as exc:
                return self._fail(
                    operation, PlatformErrorCode.DEPENDENCY_MISSING,
                    "pywinauto no disponible", native_error=exc,
                )
            info = UIAElementInfo.from_point(px, py)
            if info is None:
                return PlatformResult.success(None, window_id=root)
            adapter = self._uia_adapter(1, 1)
            element = adapter._element_info_to_dataclass(info, depth=0, parent_handle=0, pid=None)
            node = normalize_uia_element(element, int(root or 0))
            return PlatformResult.success(node, window_id=root)

        return self._run(operation, _impl)

    @staticmethod
    def _runtime_from_node_id(node_id: str) -> Optional[Tuple[int, ...]]:
        if not node_id.startswith("uia:"):
            return None
        body = node_id[4:].split("#", 1)[0]
        try:
            parts = tuple(int(p) for p in body.split("."))
        except ValueError:
            return None
        return parts if parts else None

    def _find_uia_element(self, api: _Win32Api, window_id: int, node_id: str) -> Tuple[Any, str]:
        """Localiza el UIAElementInfo de ``node_id`` dentro de la ventana."""
        from pywinauto.uia_element_info import UIAElementInfo  # type: ignore

        root = UIAElementInfo(int(window_id))
        candidates = [root]
        try:
            candidates.extend(root.descendants())
        except Exception as exc:
            return None, "no se pudieron enumerar los descendientes: %s" % exc
        runtime = self._runtime_from_node_id(node_id)
        if runtime is not None:
            for candidate in candidates:
                try:
                    if tuple(int(v) for v in (candidate.runtime_id or ())) == runtime:
                        return candidate, ""
                except Exception:
                    continue
            return None, "ningun elemento con ese RuntimeId"
        tree_result = self.get_accessibility_tree(window_id)
        if not tree_result.ok or tree_result.value is None:
            return None, "no se pudo releer el arbol para resolver el nodo"
        node = tree_result.value.get(node_id)
        if node is None:
            return None, "el nodo ya no existe en el arbol"
        target_box = node.bbox.to_int_tuple() if node.bbox else None
        for candidate in candidates:
            try:
                rect = candidate.rectangle
                box = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
                if (
                    str(candidate.automation_id or "") == node.identifier
                    and str(candidate.control_type or "") == node.native_role
                    and str(candidate.name or "") == node.name
                    and (target_box is None or box == target_box)
                ):
                    return candidate, ""
            except Exception:
                continue
        return None, "no se encontro un elemento equivalente"

    def perform_accessibility_action(
        self,
        window_id: int,
        node_id: str,
        action: str,
        value: Any = None,
    ) -> PlatformResult[None]:
        operation = "perform_accessibility_action"
        action = str(action or "").strip().lower()
        if action not in ACCESSIBILITY_ACTIONS:
            return self._fail(operation, PlatformErrorCode.INVALID_ARGUMENT, "Accion no valida: %s" % action)

        def _impl(api: _Win32Api) -> PlatformResult[None]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            blocked = self._blocked_by_elevation(api, operation, info)
            if blocked is not None:
                return blocked
            try:
                from pywinauto import uia_defines  # type: ignore
            except Exception as exc:
                return self._fail(
                    operation, PlatformErrorCode.DEPENDENCY_MISSING, "pywinauto no disponible",
                    native_error=exc,
                )
            element_info, reason = self._find_uia_element(api, int(window_id), str(node_id))
            if element_info is None:
                return self._fail(operation, PlatformErrorCode.NOT_FOUND, "Nodo no encontrado: %s" % reason)
            try:
                element_pid = int(element_info.process_id or 0)
            except Exception:
                element_pid = 0
            if element_pid and element_pid != info.pid:
                return self._fail(
                    operation, PlatformErrorCode.VERIFICATION_FAILED,
                    "El elemento pertenece a otro proceso",
                    element_pid=element_pid, window_pid=info.pid,
                )
            element = element_info.element

            def _iface(pattern: str) -> Any:
                return uia_defines.get_elem_interface(element, pattern)

            try:
                if action == "invoke":
                    _iface("Invoke").Invoke()
                elif action == "toggle":
                    _iface("Toggle").Toggle()
                elif action in ("expand", "show_menu"):
                    _iface("ExpandCollapse").Expand()
                elif action == "collapse":
                    _iface("ExpandCollapse").Collapse()
                elif action == "select":
                    _iface("SelectionItem").Select()
                elif action == "set_value":
                    try:
                        _iface("Value").SetValue(str("" if value is None else value))
                    except Exception:
                        _iface("RangeValue").SetValue(float(value))
                elif action == "scroll":
                    if value is None:
                        _iface("ScrollItem").ScrollIntoView()
                    else:
                        steps = int(value)
                        amount = ScrollAmount_SmallIncrement if steps > 0 else ScrollAmount_SmallDecrement
                        pattern = _iface("Scroll")
                        for _ in range(abs(steps)):
                            pattern.Scroll(ScrollAmount_NoAmount, amount)
                elif action == "focus":
                    element.SetFocus()
            except Exception as exc:
                return self._fail(
                    operation, PlatformErrorCode.NOT_SUPPORTED,
                    "El elemento no admite la accion %s" % action, native_error=exc,
                )
            return PlatformResult.success(None, action=action, node_id=str(node_id))

        return self._run(operation, _impl)

    # ------------------------------------------------------------------
    # Entorno de interaccion
    # ------------------------------------------------------------------

    def _input_desktop_state(self, api: _Win32Api) -> Tuple[Optional[str], str]:
        """Nombre del escritorio de entrada (``Default`` en sesion normal)."""
        handle = api.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not handle:
            return None, "OpenInputDesktop denegado (error %s)" % api.last_error()
        try:
            buf = api.ctypes.create_unicode_buffer(256)
            needed = api.wintypes.DWORD(0)
            if not api.GetUserObjectInformationW(
                handle, UOI_NAME, buf, api.ctypes.sizeof(buf), api.ctypes.byref(needed)
            ):
                return None, "GetUserObjectInformationW fallo (error %s)" % api.last_error()
            return str(buf.value or ""), ""
        finally:
            api.CloseDesktop(handle)

    @staticmethod
    def _running_process_names(names: Sequence[str]) -> List[str]:
        wanted = {n.lower() for n in names}
        found: List[str] = []
        try:
            import psutil

            for proc in psutil.process_iter(["name"]):
                name = str(proc.info.get("name") or "").lower()
                if name in wanted and name not in found:
                    found.append(name)
        except Exception as exc:
            logger.debug("No se pudieron listar procesos: %s", exc)
        return found

    def check_interaction_environment(self, window_id: int) -> PlatformResult[InteractionEnvironment]:
        operation = "check_interaction_environment"

        def _impl(api: _Win32Api) -> PlatformResult[InteractionEnvironment]:
            info, error = self._require_window(api, operation, window_id)
            if error is not None:
                return error
            env = InteractionEnvironment()
            details: Dict[str, Any] = {}

            # Sesion bloqueada / escritorio seguro.
            try:
                desktop_name, desktop_detail = self._input_desktop_state(api)
                details["input_desktop"] = desktop_name
                if desktop_name is None:
                    env.session_locked = True
                    details["input_desktop_detail"] = desktop_detail
                elif desktop_name.lower() != "default":
                    running = self._running_process_names(("logonui.exe", "consent.exe", "lockapp.exe"))
                    details["system_processes"] = running
                    if "consent.exe" in running:
                        env.secure_desktop = True
                    else:
                        env.session_locked = True
                        if desktop_name.lower() == "winlogon":
                            env.secure_desktop = True
            except Exception as exc:
                env.unknown_checks.append("input_desktop")
                details["input_desktop_error"] = str(exc)

            # Elevacion del objetivo frente a JARVIS.
            try:
                target, target_detail = self._is_process_elevated(api, info.pid)
                own, own_detail = self._is_process_elevated(api, None)
                env.target_elevated = bool(target)
                env.jarvis_elevated = bool(own)
                if target is None:
                    env.unknown_checks.append("target_elevation")
                if target_detail:
                    details["target_elevation_detail"] = target_detail
                if own_detail:
                    details["jarvis_elevation_detail"] = own_detail
            except Exception as exc:
                env.unknown_checks.append("elevation")
                details["elevation_error"] = str(exc)

            # Contenido protegido frente a captura.
            try:
                if api.GetWindowDisplayAffinity is not None:
                    affinity = api.wintypes.DWORD(0)
                    if api.GetWindowDisplayAffinity(int(window_id), api.ctypes.byref(affinity)):
                        details["display_affinity"] = int(affinity.value)
                        env.protected_content = int(affinity.value) != WDA_NONE
                    else:
                        env.unknown_checks.append("display_affinity")
                else:
                    env.unknown_checks.append("display_affinity")
            except Exception as exc:
                env.unknown_checks.append("display_affinity")
                details["display_affinity_error"] = str(exc)

            # Ventana protegida del sistema (UAC, credenciales, bloqueo).
            class_name = str(info.extra.get("class_name", "")).lower()
            if class_name in PROTECTED_WINDOW_CLASSES or info.app_identity in PROTECTED_PROCESS_NAMES:
                env.protected_window = True
                details["protected_window_reason"] = class_name or info.app_identity

            # Ventanas superpuestas por encima de la objetivo.
            env.target_minimized = bool(info.is_minimized)
            env.target_visible = bool(info.is_visible)
            area = info.frame_bounds or info.bounds
            if area is not None and area.is_valid() and not info.is_minimized:
                try:
                    overlays, ignored = self._occluding_windows(api, info, area)
                    env.overlay_windows = overlays
                    if overlays:
                        details["overlay_classes"] = [self._class_name(api, h) for h in overlays]
                    if ignored:
                        details["ignored_overlays"] = ignored
                except Exception as exc:
                    env.unknown_checks.append("overlays")
                    details["overlays_error"] = str(exc)
            details["is_foreground"] = bool(info.is_foreground)
            env.details = details
            return PlatformResult.success(env, allowed=env.allowed)

        return self._run(operation, _impl)


__all__ = [
    "WindowsDesktopAdapter",
    "VIRTUAL_KEYS",
    "PROTECTED_WINDOW_CLASSES",
    "PROTECTED_PROCESS_NAMES",
    "OVERLAY_MIN_AREA_RATIO",
]
