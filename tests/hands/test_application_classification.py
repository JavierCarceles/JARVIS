# -*- coding: utf-8 -*-
"""Tests de la unidad 3.8.1.3: distinguir aplicación instalada, en ejecución,
registrada en ApplicationManager y disponible para automatización.

`classify_application()` devuelve una `ApplicationClassification` con cuatro
ejes independientes (installed, running, registered, automatable) para un
nombre de aplicación dado. Es una operación de inspección de lectura sola:
no lanza, instala ni modifica ninguna aplicación.

Los tests usan ApplicationManager mínimo (sin registrar Chrome/Spotify) y
mockean las dependencias de sistema (_is_process_running, ApplicationPreflight)
para evitar efectos secundarios.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationClassification,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    classify_application,
    get_application_manager,
)
from src.hands.application_preflight import PreflightResult


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_minimal_manager():
    """ApplicationManager sin __init__ (evita registrar Chrome/Spotify)."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _FakeMemoryManager:
        def __init__(self):
            self.saved = []

        def save_entity(self, entity):
            self.saved.append(entity)

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _FakeMemoryManager()
    return manager


def _make_app(
    name="TestApp",
    app_type="utility",
    executable=None,
    url=None,
    capabilities=None,
    login_required=False,
    states=None,
    **overrides,
) -> ApplicationKnowledge:
    """Crea una ApplicationKnowledge con campos controlados."""
    defaults = dict(
        name=name,
        type=app_type,
        executable=executable,
        url=url,
        capabilities=capabilities or [],
        ui_elements=[],
        states=states or [ApplicationState.CLOSED],
        login_required=login_required,
        metadata={},
    )
    defaults.update(overrides)
    return ApplicationKnowledge(**defaults)


def _make_open_cap(capability=ApplicationCapability.OPEN, name="open_app"):
    return ApplicationCapabilityDef(
        capability=capability,
        name=name,
        description="d",
        required_ui_elements=[],
        preconditions=[],
        effects=[],
        cost=1.0,
    )


def _patch_manager(manager):
    """Parchea get_application_manager para devolver el manager dado."""
    return patch(
        "src.hands.applications_core.get_application_manager",
        return_value=manager,
    )


# ---------------------------------------------------------------------------
# 1. ApplicationClassification dataclass
# ---------------------------------------------------------------------------

class TestApplicationClassificationDataclass:
    """La dataclass almacena los cuatro ejes y detalles."""

    def test_fields_defaults(self):
        cls = ApplicationClassification(
            app_name="Foo",
            installed=True,
            running=False,
            registered=True,
            automatable=False,
            details={},
        )
        assert cls.app_name == "Foo"
        assert cls.installed is True
        assert cls.running is False
        assert cls.registered is True
        assert cls.automatable is False
        assert cls.details == {}


# ---------------------------------------------------------------------------
# 2. classify_application: registered axis
# ---------------------------------------------------------------------------

class TestClassifyRegistered:
    """Eje registered: la app está en ApplicationManager."""

    def test_registered_true(self):
        manager = _make_minimal_manager()
        app = _make_app("RegisteredApp", executable="regapp.exe")
        manager.applications["registeredapp"] = app
        with _patch_manager(manager):
            result = classify_application("RegisteredApp")
        assert result.registered is True

    def test_registered_false_unknown_app(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("UnknownAppXyz")
        assert result.registered is False

    def test_registered_case_insensitive(self):
        manager = _make_minimal_manager()
        app = _make_app("MyApp", executable="myapp.exe")
        manager.applications["myapp"] = app
        with _patch_manager(manager):
            result = classify_application("MYAPP")
        assert result.registered is True


# ---------------------------------------------------------------------------
# 3. classify_application: installed axis
# ---------------------------------------------------------------------------

class TestClassifyInstalled:
    """Eje installed: ejecutable en disco o URL."""

    def test_installed_true_real_executable(self):
        manager = _make_minimal_manager()
        app = _make_app("InstApp", executable="python")
        manager.applications["instapp"] = app
        with _patch_manager(manager):
            result = classify_application("InstApp")
        assert result.installed is True

    def test_installed_true_url_only(self):
        manager = _make_minimal_manager()
        app = _make_app("UrlApp", executable=None, url="https://example.com")
        manager.applications["urlapp"] = app
        with _patch_manager(manager):
            result = classify_application("UrlApp")
        assert result.installed is True

    def test_installed_false_no_executable_no_url(self):
        manager = _make_minimal_manager()
        app = _make_app("NoInstApp", executable=None, url=None)
        manager.applications["noinstapp"] = app
        with _patch_manager(manager):
            result = classify_application("NoInstApp")
        assert result.installed is False

    def test_installed_false_unknown_app(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("UnknownAppXyz")
        assert result.installed is False


# ---------------------------------------------------------------------------
# 4. classify_application: running axis
# ---------------------------------------------------------------------------

class TestClassifyRunning:
    """Eje running: proceso activo en el sistema."""

    def test_running_true_via_executable(self):
        manager = _make_minimal_manager()
        app = _make_app("RunApp", executable="chrome.exe")
        manager.applications["runapp"] = app
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=True
        ) as m:
            result = classify_application("RunApp")
        assert result.running is True
        m.assert_called_once_with("chrome.exe")

    def test_running_false_no_process(self):
        manager = _make_minimal_manager()
        app = _make_app("NoRunApp", executable="notepad.exe")
        manager.applications["norunapp"] = app
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=False
        ):
            result = classify_application("NoRunApp")
        assert result.running is False

    def test_running_false_unknown_app_no_executable(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=True
        ) as m:
            result = classify_application("UnknownAppXyz")
        assert result.running is False
        m.assert_not_called()


# ---------------------------------------------------------------------------
# 5. classify_application: automatable axis
# ---------------------------------------------------------------------------

class TestClassifyAutomatable:
    """Eje automatable: preflight aprobado y disponible."""

    def test_automatable_true(self):
        manager = _make_minimal_manager()
        app = _make_app("AutoApp", executable="python")
        manager.applications["autoapp"] = app
        preflight_result = PreflightResult(
            allowed=True,
            reason="ok",
            executable_path="python",
            confidence="high",
            availability="available",
            login_required=False,
            logged_in=True,
            resources_available=True,
        )
        with _patch_manager(manager), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(check=MagicMock(return_value=preflight_result)),
        ):
            result = classify_application("AutoApp")
        assert result.automatable is True

    def test_automatable_false_preflight_blocked(self):
        manager = _make_minimal_manager()
        app = _make_app("BlockedApp", executable="python")
        manager.applications["blockedapp"] = app
        preflight_result = PreflightResult(
            allowed=False,
            reason="blocked by admin policy",
            confidence="high",
            availability="unknown",
        )
        with _patch_manager(manager), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(check=MagicMock(return_value=preflight_result)),
        ):
            result = classify_application("BlockedApp")
        assert result.automatable is False

    def test_automatable_false_confidence_unknown(self):
        manager = _make_minimal_manager()
        app = _make_app("UncertainApp", executable="python")
        manager.applications["uncertainapp"] = app
        preflight_result = PreflightResult(
            allowed=True,
            reason="unknown",
            confidence="unknown",
            availability="unknown",
        )
        with _patch_manager(manager), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(check=MagicMock(return_value=preflight_result)),
        ):
            result = classify_application("UncertainApp")
        assert result.automatable is False

    def test_automatable_false_not_installed(self):
        manager = _make_minimal_manager()
        app = _make_app("NotInstApp", executable="nonexistent_xyz.exe")
        manager.applications["notinstapp"] = app
        preflight_result = PreflightResult(
            allowed=True,
            reason="ok",
            confidence="high",
            availability="available",
        )
        with _patch_manager(manager), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(check=MagicMock(return_value=preflight_result)),
        ):
            result = classify_application("NotInstApp")
        assert result.automatable is False


# ---------------------------------------------------------------------------
# 6. classify_application: four axes combined
# ---------------------------------------------------------------------------

class TestClassifyCombined:
    """Combinaciones de los cuatro ejes."""

    def test_all_true(self):
        manager = _make_minimal_manager()
        app = _make_app("AllApp", executable="python")
        manager.applications["allapp"] = app
        preflight_result = PreflightResult(
            allowed=True,
            reason="ok",
            confidence="high",
            availability="available",
        )
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=True
        ), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(check=MagicMock(return_value=preflight_result)),
        ):
            result = classify_application("AllApp")
        assert result.installed is True
        assert result.running is True
        assert result.registered is True
        assert result.automatable is True

    def test_installed_not_registered_not_running_not_automatable(self):
        manager = _make_minimal_manager()
        # App no registrada: manager vacío
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=False
        ):
            result = classify_application("python")
        assert result.installed is False  # no app → is_available no se evalúa
        assert result.running is False
        assert result.registered is False
        assert result.automatable is False

    def test_registered_but_not_installed_not_running(self):
        manager = _make_minimal_manager()
        app = _make_app("GhostApp", executable="nonexistent_ghost_xyz.exe")
        manager.applications["ghostapp"] = app
        with _patch_manager(manager), patch(
            "src.hands.applications_core._is_process_running", return_value=False
        ), patch(
            "src.hands.applications_core.get_application_preflight",
            return_value=MagicMock(
                check=MagicMock(
                    return_value=PreflightResult(
                        allowed=False,
                        reason="not installed",
                        confidence="unknown",
                    )
                )
            ),
        ):
            result = classify_application("GhostApp")
        assert result.registered is True
        assert result.installed is False
        assert result.running is False
        assert result.automatable is False


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------

class TestClassifyEdgeCases:
    """Casos borde: nombre vacío, None, excepciones."""

    def test_empty_name(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("")
        assert result.app_name == ""
        assert result.registered is False
        assert result.installed is False
        assert result.running is False
        assert result.automatable is False

    def test_whitespace_name(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("   ")
        assert result.app_name == ""
        assert result.registered is False

    def test_preflight_exception_does_not_crash(self):
        manager = _make_minimal_manager()
        app = _make_app("CrashApp", executable="python")
        manager.applications["crashapp"] = app
        with _patch_manager(manager), patch(
            "src.hands.applications_core.get_application_preflight",
            side_effect=RuntimeError("preflight boom"),
        ):
            result = classify_application("CrashApp")
        assert result.installed is True
        assert result.automatable is False  # fallback: installed but no preflight


# ---------------------------------------------------------------------------
# 8. Details dict
# ---------------------------------------------------------------------------

class TestClassifyDetails:
    """El diccionario details contiene información útil de depuración."""

    def test_details_contains_executable_and_type(self):
        manager = _make_minimal_manager()
        app = _make_app("DetailApp", executable="detail.exe", app_type="browser")
        manager.applications["detailapp"] = app
        with _patch_manager(manager):
            result = classify_application("DetailApp")
        assert result.details["executable"] == "detail.exe"
        assert result.details["type"] == "browser"
        assert result.details["app_name"] == "DetailApp"
        assert "normalized_name" in result.details


# ---------------------------------------------------------------------------
# 9. classify_application: unknown axis (unidad 3.8.2.5)
# ---------------------------------------------------------------------------

class TestClassifyUnknown:
    """Eje unknown: la app no se conoce ni es resoluble sobre apps registradas."""

    def test_unknown_true_for_unregistered_app(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("UnknownAppXyz")
        assert result.unknown is True
        assert result.registered is False

    def test_unknown_false_for_registered_app(self):
        manager = _make_minimal_manager()
        app = _make_app("KnownApp")  # sin executable ni url: installed=False, no preflight
        manager.applications["knownapp"] = app
        with _patch_manager(manager):
            result = classify_application("KnownApp")
        assert result.unknown is False
        assert result.registered is True

    def test_unknown_true_for_empty_name(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("")
        assert result.unknown is True
        assert result.app_name == ""


# ---------------------------------------------------------------------------
# 10. classify_application: localizable axis (unidad 3.8.2.5)
# ---------------------------------------------------------------------------

def _patch_preflight(allowed=True, confidence="high"):
    """Mockea get_application_preflight para evitar llamadas reales al sistema."""
    result = PreflightResult(
        allowed=allowed,
        reason="ok",
        confidence=confidence,
        availability="available",
    )
    return patch(
        "src.hands.applications_core.get_application_preflight",
        return_value=MagicMock(check=MagicMock(return_value=result)),
    )


class TestClassifyLocalizable:
    """Eje localizable: instalada y se determina un ejecutable/local concreto."""

    def test_localizable_true_when_executable_in_path(self):
        manager = _make_minimal_manager()
        app = _make_app("PathApp", executable="python")
        manager.applications["pathapp"] = app
        with _patch_manager(manager), _patch_preflight():
            result = classify_application("PathApp")
        assert result.installed is True
        assert result.localizable is True

    def test_localizable_false_when_executable_not_found(self):
        manager = _make_minimal_manager()
        app = _make_app("GhostApp", executable="nonexistent_ghost_xyz.exe")
        manager.applications["ghostapp"] = app
        with _patch_manager(manager):
            result = classify_application("GhostApp")
        assert result.installed is False
        assert result.localizable is False

    def test_localizable_false_for_url_only_app(self):
        # installed (se puede lanzar por URL) pero sin ejecutable local localizable.
        manager = _make_minimal_manager()
        app = _make_app("UrlApp", executable=None, url="https://example.com")
        manager.applications["urlapp"] = app
        with _patch_manager(manager), _patch_preflight():
            result = classify_application("UrlApp")
        assert result.installed is True
        assert result.localizable is False

    def test_localizable_true_when_absolute_existing_path(self, tmp_path):
        executable = tmp_path / "miapp.exe"
        executable.write_text("dummy")
        manager = _make_minimal_manager()
        app = _make_app("LocalApp", executable=str(executable))
        manager.applications["localapp"] = app
        with _patch_manager(manager), _patch_preflight():
            result = classify_application("LocalApp")
        assert result.installed is True
        assert result.localizable is True

    def test_localizable_false_for_unknown_app(self):
        manager = _make_minimal_manager()
        with _patch_manager(manager):
            result = classify_application("UnknownAppXyz")
        assert result.localizable is False
        assert result.unknown is True
