import sys
import os
import ctypes
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USER32 = ctypes.windll.user32

# Buscar ventana de VS Code por PID 26964
target_pid = 26964

def enum_callback(hwnd, lParam):
    pid = wintypes.DWORD()
    USER32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    if pid.value == target_pid:
        rect = wintypes.RECT()
        USER32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        length = USER32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        buff = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(wintypes.HWND(hwnd), buff, length + 1)
        is_iconic = USER32.IsIconic(wintypes.HWND(hwnd))
        is_zoomed = USER32.IsZoomed(wintypes.HWND(hwnd))
        print(f"VS Code ventana: hwnd={hwnd}")
        print(f"  rect: left={rect.left} top={rect.top} right={rect.right} bottom={rect.bottom}")
        print(f"  size: {rect.right-rect.left}x{rect.bottom-rect.top}")
        print(f"  minimizado={is_iconic} maximizado={is_zoomed}")
        print(f"  titulo='{buff.value}'")
        # Determinar monitor
        if rect.left >= 3840:
            print(f"  MONITOR: DISPLAY2 (secundaria)")
        else:
            print(f"  MONITOR: DISPLAY1 (primaria)")
    return True

ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
USER32.EnumWindows(ENUMPROC(enum_callback), 0)

# También verificar estado de maximizacion de todas las ventanas de Code
print("\n--- Todas las ventanas con 'Code' en el titulo ---")
def enum_callback2(hwnd, lParam):
    length = USER32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if length == 0:
        return True
    buff = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(wintypes.HWND(hwnd), buff, length + 1)
    title = buff.value
    if "Code" in title or "code" in title.lower():
        pid = wintypes.DWORD()
        USER32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        rect = wintypes.RECT()
        USER32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        is_zoomed = USER32.IsZoomed(wintypes.HWND(hwnd))
        monitor = "DISPLAY2" if rect.left >= 3840 else "DISPLAY1"
        print(f"  hwnd={hwnd} pid={pid.value} monitor={monitor} maximizado={is_zoomed} rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) titulo='{title[:50]}'")
    return True

USER32.EnumWindows(ENUMPROC(enum_callback2), 0)
