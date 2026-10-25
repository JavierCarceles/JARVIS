# -*- coding: utf-8 -*-
"""Tests de screen_capture.py (ScreenCapture y get_screen_capture)."""

import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.eyes import screen_capture as sc_module
from src.eyes.screen_capture import ScreenCapture, get_screen_capture


class TestScreenCaptureInit:
    def test_analyzer_is_none(self):
        cap = ScreenCapture()
        assert cap.analyzer is None

    def test_init_does_not_lazy_init(self):
        cap = ScreenCapture()
        assert cap.analyzer is None


class TestScreenCaptureGetAnalyzer:
    def test_lazy_init_success(self):
        cap = ScreenCapture()
        with patch("src.eyes.screen.ScreenAnalyzer") as mock_cls:
            mock_cls.return_value = MagicMock(name="analyzer")
            result = cap._get_analyzer()
            assert result is mock_cls.return_value
            assert cap.analyzer is result

    def test_lazy_init_import_error(self):
        cap = ScreenCapture()
        with patch(
            "src.eyes.screen.ScreenAnalyzer",
            side_effect=ImportError("no module"),
        ):
            result = cap._get_analyzer()
            assert result is None
            assert cap.analyzer is None

    def test_cached_after_first_call(self):
        cap = ScreenCapture()
        cap.analyzer = MagicMock(name="cached")
        result = cap._get_analyzer()
        assert result is cap.analyzer


class TestCaptureMonitor:
    def test_monitor_not_found_returns_none(self):
        cap = ScreenCapture()
        with patch(
            "src.eyes.screen_capture.get_monitor_info", return_value=None
        ):
            assert cap.capture_monitor(99) is None

    @patch("src.eyes.screen_capture.pyautogui")
    @patch("src.eyes.screen_capture.get_monitor_info")
    def test_capture_monitor_success(self, mock_get_info, mock_pyautogui, tmp_path):
        mock_get_info.return_value = MagicMock(
            monitor_id=1, left=0, top=0, width=100, height=100, right=100, bottom=100
        )
        screenshot = MagicMock()
        screenshot.size = (100, 100)
        screenshot.width = 100
        screenshot.height = 100
        save_path = str(tmp_path / "test.png")
        screenshot.save = lambda p: open(p, "wb").close()
        mock_pyautogui.screenshot.return_value = screenshot

        cap = ScreenCapture()
        result = cap.capture_monitor(1, save_path=save_path)
        assert result is not None
        assert os.path.exists(result)

    @patch("src.eyes.screen_capture.pyautogui")
    @patch("src.eyes.screen_capture.get_monitor_info")
    def test_capture_monitor_exception_returns_none(self, mock_get_info, mock_pyautogui):
        mock_get_info.return_value = MagicMock(
            monitor_id=1, left=0, top=0, width=100, height=100, right=100, bottom=100
        )
        mock_pyautogui.screenshot.side_effect = RuntimeError("fail")
        cap = ScreenCapture()
        assert cap.capture_monitor(1) is None


class TestCaptureRegion:
    @patch("src.eyes.screen_capture.ImageGrab")
    def test_capture_region_success(self, mock_imggrab, tmp_path):
        screenshot = MagicMock()
        screenshot.size = (50, 50)
        screenshot.width = 50
        screenshot.height = 50
        save_path = str(tmp_path / "region.png")
        screenshot.save = lambda p: open(p, "wb").close()
        mock_imggrab.grab.return_value = screenshot
        cap = ScreenCapture()
        result = cap.capture_region(0, 0, 50, 50, save_path=save_path)
        assert result is not None
        assert os.path.exists(result)

    @patch("src.eyes.screen_capture.ImageGrab")
    def test_capture_region_exception_returns_none(self, mock_imggrab):
        mock_imggrab.grab.side_effect = RuntimeError("fail")
        cap = ScreenCapture()
        assert cap.capture_region(0, 0, 50, 50) is None


class TestCaptureElement:
    def test_capture_element_not_dict_returns_none(self):
        cap = ScreenCapture()
        assert cap.capture_element("not a dict") is None
        assert cap.capture_element([1, 2, 3]) is None

    @patch("src.eyes.screen_capture.ImageGrab")
    def test_capture_element_valid_coords(self, mock_imggrab):
        screenshot = MagicMock()
        screenshot.size = (10, 10)
        screenshot.width = 10
        screenshot.height = 10
        mock_imggrab.grab.return_value = screenshot
        cap = ScreenCapture()
        result = cap.capture_element({"x": 0, "y": 0, "width": 10, "height": 10})
        assert result is not None


class TestCaptureActiveWindow:
    def test_no_active_window_returns_none(self):
        cap = ScreenCapture()
        try:
            import pygetwindow as gw
            with patch.object(gw, "getActiveWindow", return_value=None):
                assert cap.capture_active_window() is None
        except ImportError:
            pytest.skip("pygetwindow not available")

    @patch("src.eyes.screen_capture.ImageGrab")
    def test_capture_active_window_success(self, mock_imggrab, tmp_path):
        try:
            import pygetwindow as gw
            mock_window = MagicMock()
            mock_window.left = 0
            mock_window.top = 0
            mock_window.width = 200
            mock_window.height = 100
            screenshot = MagicMock()
            screenshot.size = (200, 100)
            screenshot.save = MagicMock()
            mock_imggrab.grab.return_value = screenshot
            cap = ScreenCapture()
            with patch.object(gw, "getActiveWindow", return_value=mock_window):
                result = cap.capture_active_window(save_path=str(tmp_path / "window.png"))
                assert result is not None
        except ImportError:
            pytest.skip("pygetwindow not available")

    def test_capture_active_window_invalid_dims(self):
        cap = ScreenCapture()
        try:
            import pygetwindow as gw
            mock_window = MagicMock()
            mock_window.left = 0
            mock_window.top = 0
            mock_window.width = -1
            mock_window.height = 0
            with patch.object(gw, "getActiveWindow", return_value=mock_window):
                assert cap.capture_active_window() is None
        except ImportError:
            pytest.skip("pygetwindow not available")

    def test_capture_active_window_exception(self):
        cap = ScreenCapture()
        try:
            import pygetwindow as gw
            with patch.object(gw, "getActiveWindow", side_effect=RuntimeError("fail")):
                assert cap.capture_active_window() is None
        except ImportError:
            pytest.skip("pygetwindow not available")


class TestScreenCaptureGetWorldState:
    def test_get_world_state_no_analyzer(self):
        cap = ScreenCapture()
        cap.analyzer = None
        with patch("src.eyes.screen.WorldState") as mock_ws:
            mock_ws.return_value = MagicMock()
            result = cap.get_world_state()
            assert result is not None

    def test_get_world_state_with_analyzer(self):
        cap = ScreenCapture()
        cap.analyzer = MagicMock()
        cap._get_analyzer = MagicMock(return_value=cap.analyzer)
        result = cap.get_world_state()
        cap.analyzer.build_world_state.assert_called_once()


class TestScreenCaptureGetApplicationState:
    def test_get_application_state_no_analyzer(self):
        cap = ScreenCapture()
        cap.analyzer = None
        with patch("src.eyes.screen.ApplicationInfo", return_value=MagicMock()):
            result = cap.get_application_state("chrome")
            assert result is not None

    def test_get_application_state_with_analyzer(self):
        cap = ScreenCapture()
        cap.analyzer = MagicMock()
        cap._get_analyzer = MagicMock(return_value=cap.analyzer)
        result = cap.get_application_state("chrome")
        cap.analyzer.analyze_application_state.assert_called_once_with("chrome")


class TestGetScreenCapture:
    def test_returns_instance(self):
        cap = get_screen_capture()
        assert isinstance(cap, ScreenCapture)

    def test_singleton(self):
        cap1 = get_screen_capture()
        cap2 = get_screen_capture()
        assert cap1 is cap2
