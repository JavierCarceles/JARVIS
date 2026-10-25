# -*- coding: utf-8 -*-
"""Tests de ApplicationPreflight (src/hands/application_preflight.py)."""

from dataclasses import is_dataclass
from unittest.mock import patch, MagicMock

import pytest

from src.hands.application_preflight import (
    ApplicationPreflight,
    PreflightResult,
    get_application_preflight,
)


class TestPreflightResult:
    def test_create_full(self):
        result = PreflightResult(
            allowed=True,
            reason="OK",
            executable_path="/app/path",
            requires_elevation=False,
            confidence="high",
            availability="available",
            login_required=True,
            logged_in=True,
            resources_available=True,
            blocked_by=None,
        )
        assert result.allowed is True
        assert result.executable_path == "/app/path"
        assert result.blocked_by is None

    def test_create_defaults(self):
        result = PreflightResult(allowed=False, reason="blocked")
        assert result.requires_elevation is False
        assert result.confidence == "unknown"
        assert result.availability == "unknown"
        assert result.login_required is None
        assert result.blocked_by is None

    def test_to_dict_keys(self):
        result = PreflightResult(allowed=True, reason="ok")
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["reason"] == "ok"
        assert d["executable_path"] is None
        assert d["requires_elevation"] is False
        assert d["confidence"] == "unknown"
        assert "blocked_by" in d

    def test_frozen_dataclass(self):
        result = PreflightResult(allowed=True, reason="ok")
        with pytest.raises(Exception):
            result.allowed = False


class TestApplicationPreflightInit:
    def test_default_init(self):
        pf = ApplicationPreflight()
        assert pf._executable_cache == {}
        assert pf._manifest_cache == {}

    def test_get_application_preflight_singleton(self):
        pf1 = get_application_preflight()
        pf2 = get_application_preflight()
        assert pf1 is pf2


class TestNameBlocking:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_name_blocked_verifier(self):
        assert self.pf._name_is_blocked("Application Verifier") is True

    def test_name_blocked_admin(self):
        assert self.pf._name_is_blocked("Administrator") is True

    def test_name_blocked_registry(self):
        assert self.pf._name_is_blocked("Registry Editor") is True

    def test_name_blocked_services(self):
        assert self.pf._name_is_blocked("Services") is True

    def test_name_not_blocked_normal(self):
        assert self.pf._name_is_blocked("chrome") is False

    def test_name_blocked_empty(self):
        assert self.pf._name_is_blocked("") is True

    def test_app_id_blocked(self):
        assert self.pf._app_id_is_blocked("task_scheduler") is True

    def test_app_id_blocked_registry(self):
        assert self.pf._app_id_is_blocked("registry") is True

    def test_app_id_not_blocked_normal(self):
        assert self.pf._app_id_is_blocked("com.microsoft.chrome") is False


class TestNormalize:
    def test_normalize(self):
        pf = ApplicationPreflight()
        assert pf._normalize("Chrome") == "chrome"
        assert pf._normalize("Google Chrome") == "google_chrome"
        assert pf._normalize("") == ""
        assert pf._normalize(None) == ""

    def test_normalize_special_chars(self):
        pf = ApplicationPreflight()
        assert pf._normalize("My- App!") == "my_app"

    def test_normalized_values(self):
        pf = ApplicationPreflight()
        vals = pf._normalized_values(["Chrome", "Firefox"])
        assert "chrome" in vals
        assert "firefox" in vals

    def test_normalize_unicode(self):
        pf = ApplicationPreflight()
        result = pf._normalize("Aplicación")
        assert "aplicion" in result.lower() or "aplicaci" in result.lower()


class TestOptionalBool:
    def test_true_values(self):
        pf = ApplicationPreflight()
        assert pf._optional_bool(True) is True
        assert pf._optional_bool("true") is True
        assert pf._optional_bool("yes") is True
        assert pf._optional_bool("1") is True
        assert pf._optional_bool("available") is True

    def test_false_values(self):
        pf = ApplicationPreflight()
        assert pf._optional_bool(False) is False
        assert pf._optional_bool("false") is False
        assert pf._optional_bool("no") is False
        assert pf._optional_bool("0") is False
        assert pf._optional_bool("disabled") is False

    def test_none_values(self):
        pf = ApplicationPreflight()
        assert pf._optional_bool(None) is None
        assert pf._optional_bool("unknown") is None
        assert pf._optional_bool(42) is None


class TestResolveResourcesStatus:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_resources_available_bool(self):
        result = self.pf._resolve_resources_status({"resources_available": True})
        assert result is True

    def test_resources_not_available_bool(self):
        result = self.pf._resolve_resources_status({"resources_available": False})
        assert result is False

    def test_resources_dict_all_true(self):
        result = self.pf._resolve_resources_status(
            {"resources": {"cpu": True, "mem": True}}
        )
        assert result is True

    def test_resources_dict_mixed(self):
        result = self.pf._resolve_resources_status(
            {"resources": {"cpu": True, "mem": False}}
        )
        assert result is False

    def test_resources_none(self):
        result = self.pf._resolve_resources_status({"name": "app"})
        assert result is None

    def test_resources_empty_dict(self):
        result = self.pf._resolve_resources_status({"resources": {}})
        assert result is None


class TestCheck:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_check_invalid_application_not_dict(self):
        result = self.pf.check("not a dict")
        assert result["allowed"] is False
        assert result["blocked_by"] == "invalid_application"

    def test_check_empty_name(self):
        result = self.pf.check({"name": ""})
        assert result["allowed"] is False
        assert result["blocked_by"] == "invalid_application"

    def test_check_blocked_name(self):
        result = self.pf.check({"name": "Task Scheduler"})
        assert result["allowed"] is False
        assert result["blocked_by"] == "blocked_name"

    def test_check_blocked_app_id(self):
        result = self.pf.check({"name": "myapp", "app_id": "task_scheduler"})
        assert result["allowed"] is False
        assert result["blocked_by"] == "blocked_app_id"

    def test_check_login_required_not_logged(self):
        result = self.pf.check({"name": "app", "login_required": True, "logged_in": False})
        assert result["allowed"] is False
        assert result["blocked_by"] == "login_required"

    def test_check_login_required_unknown_state(self):
        result = self.pf.check({"name": "app", "login_required": True})
        assert result["allowed"] is False
        assert result["blocked_by"] == "login_unknown"

    def test_check_resources_not_available(self):
        result = self.pf.check({"name": "app", "resources_available": False})
        assert result["allowed"] is False
        assert result["blocked_by"] == "resources_unavailable"

    def test_check_normal_app_passes_preflight(self):
        result = self.pf.check({"name": "chrome"})
        assert result["allowed"] is True

    def test_check_returns_dict(self):
        result = self.pf.check({"name": "app"})
        assert isinstance(result, dict)
        assert "allowed" in result
        assert "reason" in result
        assert "confidence" in result


class TestCheckApplication:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_check_application_returns_preflight_result(self):
        result = self.pf.check_application({"name": "chrome"})
        assert isinstance(result, PreflightResult)
        assert result.allowed is True

    def test_check_application_typed_blocked(self):
        result = self.pf.check_application({"name": "Task Scheduler"})
        assert isinstance(result, PreflightResult)
        assert result.allowed is False
        assert result.blocked_by == "blocked_name"


class TestIsSafeToCalibrate:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_safe_app(self):
        assert self.pf.is_safe_to_calibrate({"name": "chrome"}) is True

    def test_unsafe_blocked_name(self):
        assert self.pf.is_safe_to_calibrate({"name": "Task Scheduler"}) is False

    def test_unsafe_login_required(self):
        assert self.pf.is_safe_to_calibrate(
            {"name": "app", "login_required": True, "logged_in": False}
        ) is False


class TestCheckLoginState:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_authenticated(self):
        result = self.pf.check_login_state({"login_required": True, "logged_in": True})
        assert result["status"] == "authenticated"
        assert result["allowed"] is True

    def test_not_authenticated(self):
        result = self.pf.check_login_state({"login_required": True, "logged_in": False})
        assert result["status"] == "not_authenticated"
        assert result["allowed"] is False

    def test_unknown_login(self):
        result = self.pf.check_login_state({"login_required": True})
        assert result["status"] == "unknown"
        assert result["allowed"] is False

    def test_not_required(self):
        result = self.pf.check_login_state({"login_required": False})
        assert result["status"] == "not_required"
        assert result["allowed"] is True

    def test_unknown_no_login_info(self):
        result = self.pf.check_login_state({"name": "app"})
        assert result["status"] == "unknown"


class TestCheckResources:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_resources_available(self):
        result = self.pf.check_resources({"resources": True})
        assert result["status"] == "available"
        assert result["available"] is True

    def test_resources_unavailable(self):
        result = self.pf.check_resources({"resources": False})
        assert result["status"] == "unavailable"
        assert result["available"] is False

    def test_resources_unknown(self):
        result = self.pf.check_resources({"name": "app"})
        assert result["status"] == "unknown"
        assert result["available"] is None


class TestClearCache:
    def test_clear_cache(self):
        pf = ApplicationPreflight()
        pf._executable_cache["key"] = "value"
        pf._manifest_cache["key"] = {"found": True}
        pf.clear_cache()
        assert pf._executable_cache == {}
        assert pf._manifest_cache == {}


class TestInspectExecutableManifest:
    def setup_method(self, _method=None):
        self.pf = ApplicationPreflight()

    def test_inspect_not_found(self):
        result = self.pf.inspect_executable_manifest("/nonexistent/path.exe")
        assert result["found"] is False

    def test_parse_manifest_xml_valid(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1">
  <trustInfo>
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"""
        result = self.pf._parse_manifest_xml(xml)
        assert result["found"] is True
        assert result["requested_execution_level"] == "asInvoker"
        assert result["ui_access"] is False

    def test_parse_manifest_xml_invalid(self):
        result = self.pf._parse_manifest_xml(b"not xml")
        assert result == {}

    def test_parse_manifest_xml_empty(self):
        result = self.pf._parse_manifest_xml(None)
        assert result == {}
