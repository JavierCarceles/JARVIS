import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hands.calibration.calibration_manager import get_calibration_manager

cal = get_calibration_manager()
windows = cal._get_windows()
print("total ventanas:", len(windows))
for w in windows:
    hwnd = cal._get_window_handle(w)
    title = ""
    try:
        import ctypes
        from ctypes import wintypes
        USER32 = ctypes.windll.user32
        length = USER32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        buff = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(wintypes.HWND(hwnd), buff, length + 1)
        title = buff.value
    except Exception:
        title = "<error>"
    pid = cal._get_window_process_id(w)
    visible = cal._win32_is_visible(hwnd) if hasattr(cal, "_win32_is_visible") else "?"
    print(f"  hwnd={hwnd} pid={pid} visible={visible} title='{title[:60]}'")
