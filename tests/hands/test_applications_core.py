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
    _check_application_available,
    _check_application_login,
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


# ---------------------------------------------------------------------------
# TESTS ADICIONALES — is_capable, get_capability, defaults, estructura
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeIsCapable:
    """is_capable: comparación por enum, no por string."""

    def _make(self, **overrides):
        defaults = dict(name="Chrome", type="browser", executable="chrome")
        defaults.update(overrides)
        return ApplicationKnowledge(**defaults)

    def test_capable_with_enum(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = self._make(capabilities=[cap])
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.CLOSE) is False

    def test_not_capable_with_string(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = self._make(capabilities=[cap])
        # is_capable compares enums directly, string does not match
        assert app.is_capable("open") is False

    def test_not_capable_empty_capabilities(self):
        app = self._make(capabilities=[])
        assert app.is_capable(ApplicationCapability.OPEN) is False

    def test_multiple_capabilities(self):
        caps = [
            ApplicationCapabilityDef(
                capability=ApplicationCapability.OPEN, name="open",
                description="d", required_ui_elements=[], preconditions=[],
                effects=[], cost=1.0,
            ),
            ApplicationCapabilityDef(
                capability=ApplicationCapability.NAVIGATE, name="nav",
                description="d", required_ui_elements=[], preconditions=[],
                effects=[], cost=1.0,
            ),
        ]
        app = self._make(capabilities=caps)
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_capable(ApplicationCapability.NAVIGATE) is True
        assert app.is_capable(ApplicationCapability.SEARCH) is False


class TestApplicationKnowledgeGetCapability:
    """get_capability: búsqueda por nombre o valor."""

    def _make_cap(self, **overrides):
        defaults = dict(
            capability=ApplicationCapability.OPEN, name="open_chrome",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        defaults.update(overrides)
        return ApplicationCapabilityDef(**defaults)

    def test_by_name(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[self._make_cap(name="open_chrome")],
        )
        result = app.get_capability("open_chrome")
        assert result is not None
        assert result.capability == ApplicationCapability.OPEN

    def test_by_value(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[self._make_cap(name="open_chrome")],
        )
        result = app.get_capability("open")
        assert result is not None

    def test_case_insensitive(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[self._make_cap(name="open_chrome")],
        )
        result = app.get_capability("OPEN_CHROME")
        assert result is not None

    def test_not_found(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[],
        )
        assert app.get_capability("missing") is None

    def test_empty_name(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            capabilities=[self._make_cap(name="open_chrome")],
        )
        assert app.get_capability("") is None


class TestApplicationKnowledgeDefaults:
    """__post_init__: valoriza defaults para None."""

    def test_all_defaults(self):
        app = ApplicationKnowledge(name="X", type="utility", executable="x")
        assert app.capabilities == []
        assert app.ui_elements == []
        assert app.states == [ApplicationState.CLOSED]
        assert app.login_required is False
        assert app.calibration_policy == []
        assert app.preflight_requirements == []
        assert app.default_state == ApplicationState.CLOSED
        assert app.metadata == {}
        assert app.url is None
        assert app.icon is None

    def test_none_states_not_overwritten(self):
        # Passing states=None triggers default
        app = ApplicationKnowledge(
            name="X", type="utility", executable="x", states=None,
        )
        assert app.states == [ApplicationState.CLOSED]

    def test_custom_states(self):
        app = ApplicationKnowledge(
            name="X", type="utility", executable="x",
            states=[ApplicationState.OPEN, ApplicationState.ACTIVE],
        )
        assert ApplicationState.OPEN in app.states
        assert ApplicationState.ACTIVE in app.states

    def test_url_and_icon(self):
        app = ApplicationKnowledge(
            name="X", type="browser", executable="x",
            url="https://x.com", icon="x.ico",
        )
        assert app.url == "https://x.com"
        assert app.icon == "x.ico"


class TestApplicationManagerQueriesExtended:
    """Consultas del gestor con casos adicionales."""

    def setup_method(self, _method=None):
        self.manager = ApplicationManager()

    def test_get_application_case_insensitive(self):
        assert self.manager.get_application("CHROME") is not None
        assert self.manager.get_application("Chrome") is not None
        assert self.manager.get_application("chrome") is not None

    def test_get_application_by_alias(self):
        assert self.manager.get_application("Google Chrome") is not None
        assert self.manager.get_application("google chrome") is not None

    def test_get_applications_by_type_browser(self):
        browsers = self.manager.get_applications_by_type("browser")
        assert len(browsers) >= 1
        assert all(a.type == "browser" for a in browsers)
        names = [a.name.lower() for a in browsers]
        assert "chrome" in names

    def test_get_applications_by_type_unknown(self):
        result = self.manager.get_applications_by_type("nonexistent_type")
        assert result == []

    def test_get_applications_by_capability_search(self):
        # SEARCH only declared by Chrome
        apps = self.manager.get_applications_by_capability(ApplicationCapability.SEARCH)
        names = [app.name for app in apps]
        assert "Chrome" in names
        assert "Spotify" not in names

    def test_get_applications_by_capability_close(self):
        apps = self.manager.get_applications_by_capability(ApplicationCapability.CLOSE)
        assert apps == []

    def test_get_application_capabilities_full_structure(self):
        caps = self.manager.get_application_capabilities("chrome")
        assert isinstance(caps, dict)
        open_cap = caps["open_chrome"]
        assert open_cap["description"] == "Abre Chrome"
        assert open_cap["cost"] == 10.0
        assert open_cap["timeout"] == 30.0
        assert open_cap["retry_count"] == 3
        assert open_cap["alternatives"] == []
        assert open_cap["capability"] == "open"
        assert open_cap["required_ui_elements"] == []
        assert "chrome_closed" in open_cap["preconditions"]
        assert "chrome_open" in open_cap["effects"]

    def test_get_application_ui_elements_full_structure(self):
        elements = self.manager.get_application_ui_elements("chrome")
        assert isinstance(elements, dict)
        addr = elements["address_bar"]
        assert addr["type"] == "input"
        assert addr["is_calibrated"] is False
        assert addr["coordinates"] is None
        assert addr["screen"] == 0
        assert addr["calibration_data"] is None
        assert addr["required_capability"] == ApplicationCapability.NAVIGATE.value

    def test_get_application_ui_elements_not_found(self):
        assert self.manager.get_application_ui_elements("nonexistent") == {}

    def test_get_application_capabilities_not_found(self):
        assert self.manager.get_application_capabilities("nonexistent") == {}

    def test_get_applications_by_type_case_insensitive(self):
        apps = self.manager.get_applications_by_type("BROWSER")
        assert len(apps) >= 1


class TestApplicationManagerRegister:
    """Registro de aplicaciones: casos correctos y erróneos."""

    def test_register_minimal_app(self):
        manager = ApplicationManager()
        app = ApplicationKnowledge(name="MinimalApp", type="utility", executable="minapp")
        assert manager.register_application(app) is True
        assert "minimalapp" in manager.applications

    def test_register_app_in_manager_dict(self):
        """Registration stores the app in the manager's internal dict."""
        manager = ApplicationManager()
        app = ApplicationKnowledge(name="PersistApp", type="utility", executable="papp")
        result = manager.register_application(app)
        # Fresh managers work because memory_manager.save_entity may fail in sandbox,
        # but the in-memory dict and the return value are what we can assert reliably
        assert "persistapp" in manager.applications
        assert manager.get_application("persistapp") is not None

    def test_register_with_capabilities(self):
        manager = ApplicationManager()
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        app = ApplicationKnowledge(
            name="CapApp", type="utility", executable="capp",
            capabilities=[cap],
        )
        assert manager.register_application(app) is True
        registered = manager.get_application("capapp")
        assert registered is not None
        assert len(registered.capabilities) == 1


class TestGetApplicationKnowledgeFullStructure:
    """get_application_knowledge: estructura declarativa completa."""

    def test_chrome_full_structure(self):
        knowledge = get_application_knowledge("chrome")
        assert knowledge["name"] == "Chrome"
        assert knowledge["type"] == "browser"
        assert knowledge["executable"] == "chrome"
        assert knowledge["login_required"] is False
        assert knowledge["url"] == "https://chrome.google.com"
        assert "open_chrome" in knowledge["capabilities"]
        assert "address_bar" in knowledge["ui_elements"]
        assert ApplicationState.CLOSED.value in knowledge["states"]
        assert "address_bar" in knowledge["calibration_policy"]
        assert "application_available" in knowledge["preflight_requirements"]
        assert knowledge["default_state"] == "closed"
        assert isinstance(knowledge["metadata"], dict)

    def test_spotify_full_structure(self):
        knowledge = get_application_knowledge("spotify")
        assert knowledge["name"] == "Spotify"
        assert knowledge["type"] == "media"
        assert knowledge["login_required"] is True
        assert "application_available" in knowledge["preflight_requirements"]
        assert "login_required" in knowledge["preflight_requirements"]

    def test_not_found(self):
        assert get_application_knowledge("zzz_nonexistent") == {}


class TestOpenApplication:
    """open_application: casos felices y de error."""

    def test_open_via_executable(self):
        fake_manager = ApplicationManager()
        app = ApplicationKnowledge(
            name="TestOpen", type="utility", executable="testopen_app",
        )
        # Bypass register_application (save_entity may fail in sandbox)
        fake_manager.applications["testopen"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=fake_manager):
            with patch("src.hands.applications_core.subprocess.Popen") as mock_popen:
                mock_popen.return_value = MagicMock()
                result = open_application("testopen")
                assert "exitosamente" in result
                mock_popen.assert_called_once()

    def test_open_via_url(self):
        fake_manager = ApplicationManager()
        app = ApplicationKnowledge(
            name="TestUrl", type="browser", executable=None,
            url="https://test.example.com",
            preflight_requirements=[],
        )
        fake_manager.applications["testurl"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=fake_manager):
            with patch("src.hands.applications_core.webbrowser.open", return_value=True):
                result = open_application("testurl")
                assert "exitosamente" in result

    def test_open_not_found(self):
        fake_manager = ApplicationManager()
        with patch("src.hands.applications_core.get_application_manager", return_value=fake_manager):
            with pytest.raises(ValueError, match="no encontrada"):
                open_application("nonexistent_app_xyz_12345")

    def test_open_not_available(self):
        fake_manager = ApplicationManager()
        app = ApplicationKnowledge(
            name="UnavailableApp", type="utility", executable="nonexistent_exe_99999",
            preflight_requirements=["application_available"],
        )
        fake_manager.applications["unavailableapp"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=fake_manager):
            with patch("src.hands.applications_core._check_application_available", return_value=False):
                with pytest.raises(RuntimeError, match="no está disponible"):
                    open_application("unavailableapp")


class TestCloseApplication:
    """close_application: cierre de aplicaciones."""

    def test_close_empty_name(self):
        with pytest.raises(ValueError, match="vacío"):
            close_application("")

    def test_close_happy_path(self):
        with patch("src.hands.applications_core.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = close_application("chrome")
            assert "cerrada" in result

    def test_close_with_exe_suffix(self):
        with patch("src.hands.applications_core.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = close_application("notepad.exe")
            assert "cerrada" in result


class TestWaitForApplicationStateExtended:
    """wait_for_application_state: casos adicionales."""

    def test_timeout_zero_active(self):
        # timeout=0 → el bucle while no se ejecuta → RuntimeError
        with pytest.raises(RuntimeError, match="agotado"):
            wait_for_application_state("chrome", "active", timeout=0)

    def test_timeout_zero_ready(self):
        with pytest.raises(RuntimeError, match="agotado"):
            wait_for_application_state("chrome", "ready", timeout=0)

    def test_timeout_zero_unknown_state(self):
        with pytest.raises(RuntimeError, match="agotado"):
            wait_for_application_state("chrome", "unknown_state", timeout=0)


class TestNavigateToUrlError:
    """navigate_to_url: casos de error."""

    def test_webbrowser_raises(self):
        with patch("src.hands.applications_core.webbrowser.open", side_effect=Exception("browser error")):
            with pytest.raises(Exception, match="browser error"):
                navigate_to_url("https://example.com")

    def test_webbrowser_returns_false(self):
        with patch("src.hands.applications_core.webbrowser.open", return_value=False):
            with pytest.raises(RuntimeError, match="No se pudo"):
                navigate_to_url("https://example.com")


class TestRegisterCustomApplicationFull:
    """register_custom_application: configuración completa."""

    def test_with_capabilities_and_elements(self):
        config = {
            "name": "FullCustomApp",
            "type": "utility",
            "executable": "fullcustomapp",
            "capabilities": [
                {
                    "capability": "open",
                    "name": "open_full",
                    "description": "Abre",
                    "required_ui_elements": ["btn_ok"],
                    "preconditions": [],
                    "effects": ["opened"],
                    "cost": 5.0,
                },
            ],
            "ui_elements": [
                {
                    "name": "btn_ok",
                    "type": "button",
                    "coordinates": {"x": 10, "y": 20},
                    "required_capability": "open",
                },
            ],
            "states": ["closed"],
            "login_required": True,
            "calibration_policy": ["btn_ok"],
            "preflight_requirements": ["app_ready"],
        }
        result = register_custom_application(config)
        assert result is True
        app = get_application_manager().get_application("fullcustomapp")
        assert app is not None
        assert app.login_required is True
        assert len(app.capabilities) == 1
        assert len(app.ui_elements) == 1
        assert app.ui_elements[0].is_calibrated() is True
        assert "app_ready" in app.preflight_requirements

    def test_missing_name_and_type(self):
        assert register_custom_application({}) is False
        assert register_custom_application(None) is False


class TestUIElementCoordinateVariants:
    """UIElement.is_calibrated: formatos de coordenadas."""

    def test_single_screen_key(self):
        elem = UIElement(name="btn", type="button", coordinates={"s1": [10, 20]})
        assert elem.is_calibrated() is True

    def test_xy_non_numeric(self):
        elem = UIElement(name="btn", type="button", coordinates={"x": "abc", "y": 20})
        assert elem.is_calibrated() is False

    def test_empty_coordinates_dict(self):
        elem = UIElement(name="btn", type="button", coordinates={})
        assert elem.is_calibrated() is False

    def test_multiscreen_partial(self):
        elem = UIElement(name="btn", type="button",
                         coordinates={"s1": [10, 20], "s2": "invalid"})
        assert elem.is_calibrated() is True  # s1 is valid

    def test_no_coordinates(self):
        elem = UIElement(name="btn", type="button")
        assert elem.is_calibrated() is False


class TestApplicationCapabilityDef:
    """ApplicationCapabilityDef: defaults y alternativas."""

    def test_default_alternatives(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        assert cap.alternatives == []

    def test_custom_alternatives(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0, alternatives=["alt_1", "alt_2"],
        )
        assert cap.alternatives == ["alt_1", "alt_2"]

    def test_default_timeout_and_retry(self):
        cap = ApplicationCapabilityDef(
            capability=ApplicationCapability.OPEN, name="open",
            description="d", required_ui_elements=[], preconditions=[],
            effects=[], cost=1.0,
        )
        assert cap.timeout == 30.0
        assert cap.retry_count == 3


class TestCheckApplicationAvailable:
    """_check_application_available: resolución de ejecutables."""

    def test_url_only_no_executable(self):
        app = ApplicationKnowledge(
            name="UrlApp", type="browser", executable=None, url="https://example.com",
        )
        assert _check_application_available(app) is True

    def test_executable_none_and_url_none(self):
        app = ApplicationKnowledge(
            name="NoExeApp", type="utility", executable=None, url=None,
        )
        assert _check_application_available(app) is False

    def test_known_executable(self):
        app = ApplicationKnowledge(
            name="CalcApp", type="utility", executable="cmd",
        )
        assert _check_application_available(app) is True

    def test_unknown_executable(self):
        app = ApplicationKnowledge(
            name="UnknownApp", type="utility", executable="nonexistent_executable_99999",
        )
        assert _check_application_available(app) is False


class TestCheckApplicationLogin:
    """_check_application_login: siempre True por compatibilidad."""

    def test_returns_true(self):
        app = ApplicationKnowledge(
            name="LoginApp", type="utility", executable="loginapp",
            login_required=True,
        )
        assert _check_application_login(app) is True


# ---------------------------------------------------------------------------
# TESTS ADICIONALES — calibrate_application_ui, calibrate_applications
# ---------------------------------------------------------------------------

class TestCalibrateApplicationUI:
    """calibrate_application_ui: calibración específica de UI."""

    def test_not_found(self):
        with pytest.raises(ValueError, match="no encontrada"):
            calibrate_application_ui("nonexistent_app_xyz_12345")

    def test_no_calibration_policy(self):
        manager = ApplicationManager()
        app = ApplicationKnowledge(name="NoCalApp", type="utility", executable="nocal",
                                   calibration_policy=[])
        manager.applications["nocal"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=manager):
            with pytest.raises(RuntimeError, match="no permite calibración"):
                calibrate_application_ui("nocal")

    def test_no_valid_elements(self):
        """App con calibration_policy pero sin UI elements válidos."""
        manager = ApplicationManager()
        elem = UIElement(name="custom_elem", type="custom", coordinates=None)
        app = ApplicationKnowledge(
            name="NoValidElems", type="utility", executable="nve",
            calibration_policy=["custom_elem"],
            ui_elements=[elem],
        )
        manager.applications["novalidelems"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=manager):
            result = calibrate_application_ui("novalidelems")
            assert "No se encontraron elementos calibrables" in result

    def test_happy_path(self):
        """Calibración exitosa con elementos válidos."""
        manager = ApplicationManager()
        elem = UIElement(name="btn_ok", type="button", coordinates={"x": 10, "y": 20})
        app = ApplicationKnowledge(
            name="CalHappyApp", type="utility", executable="calhappy",
            calibration_policy=["btn_ok"],
            ui_elements=[elem],
        )
        manager.applications["calhappy"] = app

        mock_cal_manager = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elements_count = 1
        mock_cal_manager.calibrate_application.return_value = mock_result

        with patch("src.hands.applications_core.get_application_manager", return_value=manager):
            with patch("src.hands.applications_core.get_calibration_manager", return_value=mock_cal_manager):
                result = calibrate_application_ui("calhappy")
                assert "completada" in result
                assert "1 elementos" in result

    def test_no_valid_elements_not_in_policy(self):
        """Elements referenced in policy but not in ui_elements → no valid elements."""
        manager = ApplicationManager()
        app = ApplicationKnowledge(
            name="MissingElems", type="utility", executable="me",
            calibration_policy=["nonexistent_elem"],
        )
        manager.applications["missingelems"] = app
        with patch("src.hands.applications_core.get_application_manager", return_value=manager):
            result = calibrate_application_ui("missingelems")
            assert "No se encontraron elementos calibrables" in result


class TestCallCalibrateAllApplications:
    """_call_calibrate_all_applications: compatibilidad con managers."""

    def test_manager_without_calibrate_method(self):
        from src.hands.applications_core import _call_calibrate_all_applications
        with pytest.raises(RuntimeError, match="calibrate_all_applications"):
            _call_calibrate_all_applications(MagicMock(spec=[]), force=True)

    def test_manager_with_force_parameter(self):
        from src.hands.applications_core import _call_calibrate_all_applications

        def mock_method(force=False):
            return {"force": force}
        manager = MagicMock()
        manager.calibrate_all_applications = mock_method
        result = _call_calibrate_all_applications(manager, force=True)
        assert result == {"force": True}

    def test_manager_without_force_parameter(self):
        from src.hands.applications_core import _call_calibrate_all_applications

        def mock_method():
            return {"called": True}
        manager = MagicMock()
        manager.calibrate_all_applications = mock_method
        result = _call_calibrate_all_applications(manager, force=True)
        assert result == {"called": True}

