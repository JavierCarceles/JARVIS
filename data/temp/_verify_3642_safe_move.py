# Temporary verification for 3.6.4.2 (movimiento seguro) - no real window movement
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from unittest.mock import MagicMock, patch
from src.utils.screen_manager import ScreenManager, MonitorInfo

def test_screen_manager_safe_move():
    sm = ScreenManager.__new__(ScreenManager)
    sm.chrome_config = MagicMock(maximized=False)
    # MonitorInfo is a simple container in this codebase; build a minimal compatible object.
    monitor = MagicMock(left=1920, top=0, right=3840, bottom=1080, width=1920, height=1080, monitor_id=2, is_primary=False, handle=2)
    fake_win = MagicMock()
    fake_win.restore = MagicMock()

    # invalid monitor
    sm.get_monitor = MagicMock(return_value=None)
    assert sm.move_window_to_monitor("X", 99) is False
    print("invalid monitor -> False: OK")

    # no windows found
    sm.get_monitor = MagicMock(return_value=monitor)
    with patch("src.utils.screen_manager.gw.getWindowsWithTitle", return_value=[]):
        assert sm.move_window_to_monitor("Nope", 2) is False
    print("no window -> False: OK")

    # normal move + verify on correct monitor
    sm.get_monitor_for_window = MagicMock(return_value=monitor)
    with patch("src.utils.screen_manager.gw.getWindowsWithTitle", return_value=[fake_win]):
        with patch("src.utils.screen_manager.time.sleep"):
            res = sm.move_window_to_monitor("App", 2)
    assert res is True
    fake_win.moveTo.assert_called_with(1920, 0)
    print("move ok + moveTo(target coords): OK")

    # move but lands on wrong monitor
    other = MagicMock(left=0, top=0, right=1920, bottom=1080, width=1920, height=1080, monitor_id=1, is_primary=True, handle=1)
    sm.get_monitor_for_window = MagicMock(return_value=other)
    with patch("src.utils.screen_manager.gw.getWindowsWithTitle", return_value=[fake_win]):
        with patch("src.utils.screen_manager.time.sleep"):
            res = sm.move_window_to_monitor("App", 2)
    assert res is False
    print("wrong monitor after move -> False: OK")

    # exception safety
    with patch("src.utils.screen_manager.gw.getWindowsWithTitle", side_effect=RuntimeError("boom")):
        assert sm.move_window_to_monitor("App", 2) is False
    print("exception -> False: OK")

def test_calibration_manager_safe_move():
    from src.hands.calibration_manager import CalibrationManager
    with patch.object(CalibrationManager, "__init__", lambda self: None):
        cm = CalibrationManager()
    cm.screen_manager = MagicMock()
    cm._get_window_handle = MagicMock(return_value=None)
    cm._win32_is_gui_window = MagicMock(return_value=False)
    monitor = MagicMock(left=100, top=50, monitor_id=2)
    with patch("src.hands.calibration_manager.get_monitor_info", return_value=None):
        assert cm.move_window_to_monitor(MagicMock(), 9) is False
    print("CalibrationManager invalid monitor -> False: OK")
    with patch("src.hands.calibration_manager.get_monitor_info", return_value=monitor):
        assert cm.move_window_to_monitor(None, 2) is False
    print("CalibrationManager None window -> False: OK")
    # invalid hwnd/gui guard
    with patch("src.hands.calibration_manager.get_monitor_info", return_value=monitor):
        assert cm.move_window_to_monitor(MagicMock(), 2) is False
    print("CalibrationManager invalid hwnd/gui -> False: OK")

def test_verify_target_monitor_exists():
    from src.hands.applications_core import verify_target_monitor
    print("verify_target_monitor exists:", callable(verify_target_monitor))

if __name__ == "__main__":
    test_screen_manager_safe_move()
    test_calibration_manager_safe_move()
    test_verify_target_monitor_exists()
    print("ALL CHECKS PASSED")
