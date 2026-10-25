# -*- coding: utf-8 -*-
"""Tests de screen.py (ApplicationState, ApplicationInfo, WorldState, ScreenAnalyzer, utilidades)."""

from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from src.eyes.screen import (
    ApplicationInfo,
    ApplicationState,
    WorldState,
    ScreenAnalyzer,
    _get_available_monitor_numbers,
    _get_monitor_number,
)


class TestApplicationState:
    def test_values(self):
        assert ApplicationState.CLOSED.value == "closed"
        assert ApplicationState.OPEN.value == "open"
        assert ApplicationState.ACTIVE.value == "active"
        assert ApplicationState.MINIMIZED.value == "minimized"
        assert ApplicationState.MAXIMIZED.value == "maximized"

    def test_from_string(self):
        assert ApplicationState("closed") == ApplicationState.CLOSED
        assert ApplicationState("active") == ApplicationState.ACTIVE


class TestApplicationInfoInit:
    def test_defaults(self):
        info = ApplicationInfo(name="app", state=ApplicationState.CLOSED)
        assert info.name == "app"
        assert info.state == ApplicationState.CLOSED
        assert info.window_title is None
        assert info.window_class is None
        assert info.monitor == 1
        assert info.position == (0, 0)
        assert info.size == (0, 0)
        assert info.visible_elements == []

    def test_visible_elements_none_becomes_list(self):
        info = ApplicationInfo(name="app", state=ApplicationState.OPEN, visible_elements=None)
        assert info.visible_elements == []

    def test_custom_values(self):
        info = ApplicationInfo(
            name="chrome",
            state=ApplicationState.ACTIVE,
            window_title="Google",
            window_class="Chrome_Widget",
            monitor=2,
            position=(100, 200),
            size=(800, 600),
            visible_elements=["tab", "url_bar"],
        )
        assert info.name == "chrome"
        assert info.state == ApplicationState.ACTIVE
        assert info.window_title == "Google"
        assert info.window_class == "Chrome_Widget"
        assert info.monitor == 2
        assert info.position == (100, 200)
        assert info.size == (800, 600)
        assert info.visible_elements == ["tab", "url_bar"]


class TestApplicationInfoSerialization:
    def test_to_dict(self):
        info = ApplicationInfo(
            name="chrome",
            state=ApplicationState.ACTIVE,
            window_title="Google",
            window_class="Chrome_Widget",
            monitor=2,
            position=(100, 200),
            size=(800, 600),
            visible_elements=["tab"],
        )
        d = info.to_dict()
        assert d["name"] == "chrome"
        assert d["state"] == "active"
        assert d["window_title"] == "Google"
        assert d["window_class"] == "Chrome_Widget"
        assert d["monitor"] == 2
        assert d["position"] == (100, 200)
        assert d["size"] == (800, 600)
        assert d["visible_elements"] == ["tab"]

    def test_from_dict_roundtrip(self):
        original = ApplicationInfo(
            name="firefox",
            state=ApplicationState.MAXIMIZED,
            window_title="Mozilla",
            monitor=1,
            visible_elements=["url_bar", "tab"],
        )
        restored = ApplicationInfo.from_dict(original.to_dict())
        assert restored.name == "firefox"
        assert restored.state == ApplicationState.MAXIMIZED
        assert restored.window_title == "Mozilla"
        assert restored.monitor == 1
        assert restored.visible_elements == ["url_bar", "tab"]

    def test_from_dict_with_valid_state(self):
        data = {
            "name": "app", "state": "open",
            "window_title": "T", "window_class": "WC",
            "monitor": 3, "position": [10, 20], "size": [100, 200],
            "visible_elements": ["a", "b"],
        }
        info = ApplicationInfo.from_dict(data)
        assert info.state == ApplicationState.OPEN
        assert info.position == (10, 20)
        assert info.size == (100, 200)
        assert info.monitor == 3

    def test_from_dict_invalid_state_defaults_closed(self):
        info = ApplicationInfo.from_dict({"name": "app", "state": "weird"})
        assert info.state == ApplicationState.CLOSED

    def test_from_dict_missing_state_defaults_closed(self):
        info = ApplicationInfo.from_dict({"name": "app"})
        assert info.state == ApplicationState.CLOSED

    def test_from_dict_none_position_size(self):
        """position=None triggers TypeError → defaults to (0,0).
        size='abc' triggers ValueError on int() → crashes."""
        info = ApplicationInfo.from_dict({"name": "app", "position": None, "size": None})
        assert info.position == (0, 0)
        assert info.size == (0, 0)

    def test_from_dict_missing_position_size(self):
        info = ApplicationInfo.from_dict({"name": "app"})
        assert info.position == (0, 0)
        assert info.size == (0, 0)

    def test_from_dict_invalid_position_size(self):
        """position=[1] → len 1 → fallback (0,0).
        size=[1, 2, 3, 4, 5] → [:2] → (1,2) which has len 2 → passes through."""
        info = ApplicationInfo.from_dict({"name": "app", "position": [1], "size": [1, 2, 3, 4, 5]})
        assert info.position == (0, 0)
        assert info.size == (1, 2)

    def test_from_dict_invalid_monitor_raises(self):
        """int('abc') raises ValueError that is NOT caught by from_dict."""
        with pytest.raises(ValueError):
            ApplicationInfo.from_dict({"name": "app", "monitor": "abc"})

    def test_from_dict_negative_monitor_clamped(self):
        info = ApplicationInfo.from_dict({"name": "app", "monitor": -5})
        assert info.monitor == 1

    def test_from_dict_none_input(self):
        info = ApplicationInfo.from_dict(None)
        assert info.name == "unknown"
        assert info.state == ApplicationState.CLOSED

    def test_from_dict_empty_dict(self):
        info = ApplicationInfo.from_dict({})
        assert info.name == "unknown"
        assert info.state == ApplicationState.CLOSED


class TestWorldState:
    def test_defaults(self):
        ws = WorldState(timestamp=12345.0, applications={})
        assert ws.timestamp == 12345.0
        assert ws.applications == {}
        assert ws.focused_application is None
        assert ws.active_monitor == 1
        assert ws.available_monitors == [1]
        assert ws.calibrated_elements == {}
        assert ws.known_urls == {}
        assert ws.system_resources == {}

    def test_to_dict(self):
        info = ApplicationInfo(name="app", state=ApplicationState.OPEN)
        ws = WorldState(timestamp=100.0, applications={"app": info})
        d = ws.to_dict()
        assert d["timestamp"] == 100.0
        assert d["focused_application"] is None
        assert d["active_monitor"] == 1
        assert isinstance(d["available_monitors"], list)
        assert "app" in d["applications"]
        assert isinstance(d["applications"]["app"], dict)

    def test_from_dict_roundtrip(self):
        original = WorldState(
            timestamp=200.0,
            applications={},
            focused_application="chrome",
            active_monitor=2,
            available_monitors=[1, 2],
            calibrated_elements={"btn": {"x": 10}},
            known_urls={"twitch": "https://twitch.tv"},
            system_resources={"cpu": 50},
        )
        restored = WorldState.from_dict(original.to_dict())
        assert restored.timestamp == 200.0
        assert restored.focused_application == "chrome"
        assert restored.active_monitor == 2
        assert restored.available_monitors == [1, 2]  # both are valid digit strings

    def test_from_dict_none_input(self):
        ws = WorldState.from_dict(None)
        assert ws.timestamp is not None
        assert ws.applications == {}

    def test_from_dict_app_info_conversion(self):
        data = {
            "timestamp": 100.0,
            "applications": {"chrome": {"name": "chrome", "state": "active"}},
        }
        ws = WorldState.from_dict(data)
        assert "chrome" in ws.applications
        assert isinstance(ws.applications["chrome"], ApplicationInfo)

    def test_from_dict_non_dict_app_data(self):
        data = {"timestamp": 100.0, "applications": {"chrome": "not_a_dict"}}
        ws = WorldState.from_dict(data)
        assert "chrome" in ws.applications
        assert ws.applications["chrome"].state == ApplicationState.CLOSED

    def test_from_dict_invalid_available_monitors(self):
        data = {"timestamp": 100.0, "applications": {}, "available_monitors": ["abc", None]}
        ws = WorldState.from_dict(data)
        assert ws.available_monitors == [1]  # fallback

    def test_from_dict_active_monitor_max_1(self):
        data = {"timestamp": 100.0, "applications": {}, "active_monitor": -1}
        ws = WorldState.from_dict(data)
        assert ws.active_monitor == 1

    def test_from_dict_active_monitor_string(self):
        data = {"timestamp": 100.0, "applications": {}, "active_monitor": "abc"}
        ws = WorldState.from_dict(data)
        assert ws.active_monitor == 1


class TestGetMonitorNumber:
    def test_none_monitor(self):
        assert _get_monitor_number(None) is None

    def test_monitor_id(self):
        mock = MagicMock()
        mock.monitor_id = 3
        assert _get_monitor_number(mock) == 3

    def test_fallback_to_index(self):
        mock = MagicMock()
        del mock.monitor_id
        mock.index = 0
        assert _get_monitor_number(mock) == 1

    def test_no_valid_attrs(self):
        mock = MagicMock()
        del mock.monitor_id
        mock.index = None
        assert _get_monitor_number(mock) is None

    def test_screen_number_fallback(self):
        mock = MagicMock()
        del mock.monitor_id
        mock.index = None
        mock.screen_number = 5
        assert _get_monitor_number(mock) == 5


class TestGetAvailableMonitorNumbers:
    def test_returns_list(self):
        result = _get_available_monitor_numbers()
        assert isinstance(result, list)
        assert len(result) >= 1

    @patch("src.eyes.screen.get_screen_manager")
    def test_with_mocked_manager(self, mock_get_sm):
        mock_sm = MagicMock()
        mock_sm.monitors = [MagicMock(monitor_id=1, index=None)]
        mock_get_sm.return_value = mock_sm
        result = _get_available_monitor_numbers()
        assert 1 in result

    @patch("src.eyes.screen.get_screen_manager")
    def test_manager_raises_returns_fallback(self, mock_get_sm):
        mock_get_sm.side_effect = RuntimeError("fail")
        result = _get_available_monitor_numbers()
        assert result == [1]


class TestScreenAnalyzer:
    def test_init(self):
        analyzer = ScreenAnalyzer()
        assert analyzer.memory_manager is not None
        assert analyzer._vision is None

    def test_get_vision_lazy_init(self):
        analyzer = ScreenAnalyzer()
        with patch("src.eyes.vision.Vision") as mock_vision_cls:
            mock_vision_cls.return_value = MagicMock()
            result = analyzer._get_vision()
            assert result is mock_vision_cls.return_value
            assert analyzer._vision is result

    def test_get_vision_caches(self):
        analyzer = ScreenAnalyzer()
        analyzer._vision = MagicMock(name="cached")
        result = analyzer._get_vision()
        assert result is analyzer._vision

    def test_get_vision_import_error(self):
        analyzer = ScreenAnalyzer()
        with patch("src.eyes.vision.Vision", side_effect=Exception("import fail")):
            result = analyzer._get_vision()
            assert result is None
            assert analyzer._vision is None

    def test_analyze_application_state_empty_name(self):
        analyzer = ScreenAnalyzer()
        result = analyzer.analyze_application_state("")
        assert isinstance(result, ApplicationInfo)
        assert result.state == ApplicationState.CLOSED

    def test_analyze_application_state_none_name(self):
        analyzer = ScreenAnalyzer()
        result = analyzer.analyze_application_state(None)
        assert isinstance(result, ApplicationInfo)
        assert result.name == ""
        assert result.state == ApplicationState.CLOSED

    def test_analyze_application_state_vision_available(self):
        analyzer = ScreenAnalyzer()
        analyzer._vision = MagicMock()
        mock_info = ApplicationInfo(name="chrome", state=ApplicationState.ACTIVE)
        analyzer._vision.detect_application_state.return_value = mock_info
        result = analyzer.analyze_application_state("chrome")
        assert result.state == ApplicationState.ACTIVE

    def test_analyze_application_state_vision_returns_dict(self):
        analyzer = ScreenAnalyzer()
        analyzer._vision = MagicMock()
        analyzer._vision.detect_application_state.return_value = {
            "name": "chrome", "state": "active", "window_title": "Google"
        }
        result = analyzer.analyze_application_state("chrome")
        assert result.state == ApplicationState.ACTIVE

    def test_analyze_application_state_vision_exception_falls_back(self):
        analyzer = ScreenAnalyzer()
        analyzer._vision = MagicMock()
        analyzer._vision.detect_application_state.side_effect = RuntimeError("fail")
        result = analyzer.analyze_application_state("chrome")
        assert isinstance(result, ApplicationInfo)

    def test_analyze_application_state_no_vision_fallback(self):
        analyzer = ScreenAnalyzer()
        analyzer._vision = None
        result = analyzer.analyze_application_state("chrome")
        assert isinstance(result, ApplicationInfo)

    def test_get_known_applications(self):
        analyzer = ScreenAnalyzer()
        with patch.object(analyzer, "memory_manager") as mock_mm:
            mock_mm.get_entities_by_type.return_value = []
            apps = analyzer._get_known_applications()
            assert "chrome" in apps
            assert "edge" in apps
            assert "firefox" in apps

    def test_detect_focused_application_no_window(self):
        analyzer = ScreenAnalyzer()
        try:
            import pygetwindow as gw
            with patch.object(gw, "getActiveWindow", return_value=None):
                result = analyzer._detect_focused_application({})
                assert result is None
        except ImportError:
            pytest.skip("pygetwindow not available")

    def test_get_active_monitor_exception(self):
        analyzer = ScreenAnalyzer()
        with patch("src.eyes.screen.get_screen_manager") as mock_sm:
            mock_sm.side_effect = RuntimeError("fail")
            result = analyzer._get_active_monitor()
            assert result == 1

    def test_get_calibrated_elements_no_data(self):
        analyzer = ScreenAnalyzer()
        with patch.object(analyzer, "memory_manager") as mock_mm:
            mock_mm.storage.load.return_value = None
            result = analyzer._get_calibrated_elements()
            assert result == {}

    def test_get_known_urls_empty(self):
        analyzer = ScreenAnalyzer()
        with patch.object(analyzer, "memory_manager") as mock_mm:
            mock_mm.get_entities_by_type.return_value = []
            result = analyzer._get_known_urls()
            assert result == {}

    def test_get_system_resources_exception(self):
        analyzer = ScreenAnalyzer()
        with patch.dict("sys.modules", {"psutil": None}):
            result = analyzer._get_system_resources()
            assert result == {}
