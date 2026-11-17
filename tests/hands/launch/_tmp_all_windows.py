import sys
import os
import ctypes
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USER32 = ctypes.windll.user32

def enum_callback(hwnd, lParam):
    if not USER32.IsWindowVisible(wintypes.HWND(hwnd)):
        return True
    pid = wintypes.DWORD()
    USER32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    rect = wintypes.RECT()
    USER32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    length = USER32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    buff = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(wintypes.HWND(hwnd), buff, length + 1)
    title = buff.value
    is_zoomed = USER32.IsZoomed(wintypes.HWND(hwnd))
    monitor = "DISPLAY2" if rect.left >= 3840 else "DISPLAY1"
    print(f"  hwnd={hwnd} pid={pid.value} monitor={monitor} maximizado={is_zoomed} rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) size={rect.right-rect.left}x{rect.bottom-rect.top} titulo='{title[:50]}'")
    return True

ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
print("Ventanas visibles en el sistema:")
USER32.EnumWindows(ENUMPROC(enum_callback), 0)
