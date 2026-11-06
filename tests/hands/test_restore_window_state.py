"""
Tests for _restore_window_state (3.5.2.3) – verify reusable state without destroying user state.
"""
import unittest
from unittest.mock import patch, MagicMock
import ctypes
import win32con

from src.hands.calibration_manager import CalibrationManager, _WindowStateSnapshot


class TestRestoreWindowState(unittest.TestCase):
    def setUp(self):
        self.manager = CalibrationManager()

    @patch("src.hands.calibration_manager.USER32.SetWindowPlacement")
    @patch("src.hands.calibration_manager.USER32.IsWindow")
    def test_restore_success(self, mock_is_window, mock_set_placement):
        """Valid hwnd and snapshot should return True."""
        hwnd = 12345
        mock_is_window.return_value = True
        mock_set_placement.return_value = True
        snapshot = _WindowStateSnapshot(
            flags=0,
            show_cmd=win32con.SW_SHOWNORMAL,
            min_x=0,
            min_y=0,
            max_x=1920,
            max_y=1080,
            normal_left=0,
            normal_top=0,
            normal_right=1920,
            normal_bottom=1080,
        )
        result = CalibrationManager._restore_window_state(hwnd, snapshot)
        self.assertTrue(result)

    @patch("src.hands.calibration_manager.USER32.SetWindowPlacement")
    @patch("src.hands.calibration_manager.USER32.IsWindow")
    def test_restore_failure_missing_hwnd(self, mock_is_window, mock_set_placement):
        """Missing hwnd should return False."""
        result = CalibrationManager._restore_window_state(None, None)
        self.assertFalse(result)

    @patch("src.hands.calibration_manager.USER32.SetWindowPlacement")
    @patch("src.hands.calibration_manager.USER32.IsWindow")
    def test_restore_failure_invalid_window(self, mock_is_window, mock_set_placement):
        """Invalid window handle should return False."""
        mock_is_window.return_value = False
        result = CalibrationManager._restore_window_state(0, None)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()