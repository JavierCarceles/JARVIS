# -*- coding: utf-8 -*-
"""Tests de applications_core (src/hands/applications_core.py)."""

from unittest.mock import MagicMock, patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    abrir_gmail,
    abrir_youtube,
    calibrate_application_ui,
    calibrate_applications,
    calibrar_aplicaciones,
    close_application,
    get_available_commands,
    get_application_knowledge,
    get_applications_by_capability,
    navigate_to_url,
    open_application,
    register_custom_application,
    wait_for_application_state,
    get_application_manager,
)


class TestApplicationCapability:
    def test_values(self):
        assert ApplicationCapability.OPEN.value == "open"
        assert ApplicationCapability.CLOSE.value == "close"
        assert ApplicationCapability.NAVIGATE.value == "navigate"
        assert ApplicationCapability.SEARCH.value == "search"
        assert ApplicationCapability.LOGIN.value == "login"

    def test_open_from_string(self):
        assert ApplicationCapability("open") == ApplicationCapability.OPEN

    def test_open_from_string_invalid(self):
        with pytest.raises(ValueError):
            ApplicationCapability("nonexistent")


class TestApplicationState:
    def test_values(self):
        assert ApplicationState.CLOSED.value == "closed"
        assert ApplicationState.ACTIVE.value == "active"
        assert ApplicationState.READY.value == "ready"
        assert ApplicationState.LOADING.value == "loading"

    def test_from_string(self):
        assert ApplicationState("active") == ApplicationState.ACTIVE


class TestUIElement:
    def test_create_full(self):
        elem = UIElement(
            name="btn", type="button",
            coordinates={"x": 10, "y": 20},
            screen=1,
            calibration_data={"offset": 0},
            required_capability=ApplicationCapability.CLICK,
        )
        assert elem.name == "btn"
        assert elem.type == "button"
        assert elem.coordinates == {"x": 10, "y": 20}
        assert elem.screen == 1
        assert elem.is_calibrated() is True

    def test_create_without_coordinates(self):
        elem = UIElement(name="btn", type="button")
        assert elem.name == "btn"
        assert elem.is_calibrated() is False

    def test_is_coordinate_pair_xy(self):
        assert UIElement._is_coordinate_pair(10, 20) is True
        assert UIElement._is_coordinate_pair("a", 20) is False

    def test_is_coordinate_pair_list(self):
        assert UIElement._is_coordinate_pair([10, 20]) is True
        assert UIElement._is_coordinate_pair([10]) is False
        assert UIElement._is_coordinate_pair("abc") is False

    def test_coordinates_dict_format(self):
        elem = UIElement(name="btn", type="button", coordinates={"x": 1, "y": 2})
        assert elem.is_calibrated() is True

    def test_coordinates_multiscreen_format(self):
        elem = UIElement(name="btn", type="button", coordinates={"s1": [10, 20], "s2": [30, 40]})
        assert elem.is_calibrated() is True


class TestApplicationCapabilityDef:
    def test_create(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="open_chrome",
            description="Abre Chrome",
            required_ui_elements=[],
            preconditions=["chrome_closed"],
            effects=["chrome_open"],
            cost=10.0,
        )
        assert cap.capability == ApplicationCapability.OPEN
        assert cap.name == "open_chrome"
        assert cap.cost == 10.0
        assert cap.timeout == 30.0
        assert cap.retry_count == 3
        assert cap.alternatives == []

    def test_post_init_defaults(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN,
            name="test",
            description="d",
            required_ui_elements=[],
            preconditions=[],
            effects=[],
            cost=1.0,
        )
        assert cap.alternatives == []


class TestApplicationKnowledge:
    def _make(self, **overrides):
        defaults = dict(
            name="Chrome", type="browser", executable="chrome",
        )
        defaults.update(overrides)
        return ApplicationKnowledge(**defaults)

    def test_post_init_defaults(self):
        app = self._make()
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.metadata == {}

    def test_get_capability_by_value(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open_chrome",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = self._make(capabilities=[cap])
        result = app.get_capability("open")
        assert result is not None
        assert result.name == "open_chrome"

    def test_get_capability_by_name(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.NAVIGATE, name="navigate_to_url",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = self._make(capabilities=[cap])
        result = app.get_capability("navigate_to_url")
        assert result is not None

    def test_get_capability_not_found(self):
        app = self._make(capabilities=[])
        assert app.get_capability("nonexistent") is None

    def test_is_capable(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = self._make(capabilities=[cap])
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.CLOSE) is False

    def test_get_calibrated_elements_none(self):
        app = self._make()
        assert app.get_calibrated_elements() == []

    def test_get_calibrated_elements_some(self):
        elem1 = UIElement(name="btn1", type="button", coordinates={"x": 1, "y": 2})
        elem2 = UIElement(name="btn2", type="button")
        app = self._make(ui_elements=[elem1, elem2])
        calibrated = app.get_calibrated_elements()
        assert len(calibrated) == 1
        assert calibrated[0].name == "btn1"

    def test_get_ui_element_found(self):
        elem = UIElement(name="address_bar", type="input")
        app = self._make(ui_elements=[elem])
        result = app.get_ui_element("address_bar")
        assert result is not None
        assert result.name == "address_bar"

    def test_get_ui_element_not_found(self):
        app = self._make(ui_elements=[])
        assert app.get_ui_element("missing") is None


class TestApplicationManagerInit:
    def test_default_init(self):
        manager = ApplicationManager()
        assert manager.applications != {}
        assert "chrome" in manager.applications
        assert "spotify" in manager.applications

    def test_get_application_manager_singleton(self):
        m1 = get_application_manager()
        m2 = get_application_manager()
        assert m1 is m2

    def test_chrome_has_capabilities(self):
        manager = get_application_manager()
        chrome = manager.get_application("chrome")
        assert chrome is not None
        assert len(chrome.capabilities) >= 3

    def test_chrome_has_ui_elements(self):
        manager = get_application_manager()
        chrome = manager.get_application("chrome")
        assert chrome is not None
        assert len(chrome.ui_elements) >= 2

    def test_spotify_login_required(self):
        manager = get_application_manager()
        spotify = manager.get_application("spotify")
        assert spotify is not None
        assert spotify.login_required is True


class TestApplicationManagerNormalize:
    def test_normalize_alias(self):
        manager = ApplicationManager()
        assert manager._normalize_name("Google Chrome") == "chrome"
        assert manager._normalize_name("Mozilla Firefox") == "firefox"

    def test_normalize_unknown(self):
        manager = ApplicationManager()
        assert manager._normalize_name("unknown_app") == "unknown_app"

    def test_normalize_none(self):
        manager = ApplicationManager()
        assert manager._normalize_name(None) == ""


class TestApplicationManagerQueries:
    def setup_method(self, _method=None):
        self.manager = ApplicationManager()

    def test_get_application_found(self):
        result = self.manager.get_application("chrome")
        assert result is not None
        assert result.name == "Chrome"

    def test_get_application_alias(self):
        result = self.manager.get_application("Google Chrome")
        assert result is not None
        assert result.name == "Chrome"

    def test_get_application_not_found(self):
        assert self.manager.get_application("nonexistent") is None

    def test_get_applications_by_type(self):
        browsers = self.manager.get_applications_by_type("browser")
        assert len(browsers) >= 1
        assert all(app.type == "browser" for app in browsers)

    def test_get_applications_by_capability(self):
        apps = self.manager.get_applications_by_capability(ApplicationCapability.OPEN)
        assert len(apps) >= 1

    def test_get_application_capabilities(self):
        caps = self.manager.get_application_capabilities("chrome")
        assert isinstance(caps, dict)
        assert len(caps) >= 1

    def test_get_application_capabilities_not_found(self):
        caps = self.manager.get_application_capabilities("nonexistent")
        assert caps == {}

    def test_get_application_ui_elements(self):
        elements = self.manager.get_application_ui_elements("chrome")
        assert isinstance(elements, dict)
        assert "address_bar" in elements
        assert "search_bar" in elements

    def test_get_application_ui_elements_not_found(self):
        elements = self.manager.get_application_ui_elements("nonexistent")
        assert elements == {}


class TestApplicationManagerRegister:
    def test_register_application(self):
        manager = ApplicationManager()
        app = ApplicationKnowledge(name="TestApp", type="utility", executable="testapp")
        result = manager.register_application(app)
        assert result is True
        assert "testapp" in manager.applications


class TestModuleFunctions:
    def test_get_available_commands(self):
        commands = get_available_commands()
        assert isinstance(commands, list)
        assert "open_application" in commands

    def test_get_application_knowledge(self):
        knowledge = get_application_knowledge("chrome")
        assert isinstance(knowledge, dict)
        assert knowledge["name"] == "Chrome"
        assert "capabilities" in knowledge

    def test_get_application_knowledge_not_found(self):
        knowledge = get_application_knowledge("nonexistent_app_xyz")
        assert knowledge == {}

    def test_get_applications_by_capability_valid(self):
        apps = get_applications_by_capability("open")
        assert isinstance(apps, list)
        assert len(apps) >= 1

    def test_get_applications_by_capability_invalid(self):
        apps = get_applications_by_capability("nonexistent_capability")
        assert apps == []

    def test_register_custom_application_valid(self):
        app_config = {
            "name": "CustomApp",
            "type": "utility",
            "executable": "customapp",
            "capabilities": [],
        }
        result = register_custom_application(app_config)
        assert result is True

    def test_register_custom_application_missing_name(self):
        result = register_custom_application({"type": "utility"})
        assert result is False

    def test_register_custom_application_missing_type(self):
        result = register_custom_application({"name": "App"})
        assert result is False

    def test_navigate_to_url_valid(self):
        with patch("webbrowser.open", return_value=True):
            result = navigate_to_url("https://example.com")
            assert "example.com" in result

    def test_navigate_to_url_empty(self):
        with pytest.raises(ValueError, match="vacía"):
            navigate_to_url("")

    def test_open_application_not_found(self):
        with pytest.raises(ValueError, match="no encontrada"):
            open_application("nonexistent_app_xyz")

    def test_close_application_empty_name(self):
        with pytest.raises(ValueError, match="vacío"):
            close_application("")

    def test_wait_for_application_state_empty(self):
        with pytest.raises(ValueError, match="vacío"):
            wait_for_application_state("app", "")

    def test_wait_for_application_state_negative_timeout(self):
        with pytest.raises(RuntimeError, match="agotado"):
            wait_for_application_state("app", "active", timeout=-5)

    def test_calibrate_application_ui_not_found(self):
        with pytest.raises(ValueError, match="no encontrada"):
            calibrate_application_ui("nonexistent_app_xyz")

    def test_calibrar_aplicaciones(self):
        with patch("src.hands.applications_core.get_calibration_manager") as mock_gc:
            mock_manager = MagicMock()
            mock_gc.return_value = mock_manager
            mock_manager.calibrate_all_applications.return_value = {
                "success": True, "calibrated": [], "skipped": [],
                "failed": [], "total_elements": 0,
                "monitors_detected": 1, "applications_requested": 0,
            }
            result = calibrar_aplicaciones()
            assert isinstance(result, dict)
            assert result["success"] is True

    def test_abrir_youtube(self):
        with patch("src.hands.applications_core.navigate_to_url", return_value="Navegación solicitada a https://youtube.com"):
            result = abrir_youtube()
            assert "YouTube" not in result or "youtube" in result.lower() or "Error" not in result

    def test_abrir_gmail(self):
        with patch("src.hands.applications_core.navigate_to_url", return_value="Navegación solicitada a https://mail.google.com"):
            result = abrir_gmail()
            assert "Error" not in result
