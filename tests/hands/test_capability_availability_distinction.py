# -*- coding: utf-8 -*-
"""Tests de la distinción entre capability disponible y capability declarada.

Unidad 3.3.2.2: "Distinguir capability disponible de capability simplemente declarada."

Una capacidad **declarada** existe en el modelo de conocimiento (``is_capable``).
Una capacidad **disponible** requiere además que la aplicación esté disponible en
tiempo de ejecución (``is_available`` — ejecutable instalado o URL configurada).
``is_capability_available`` combina ambas condiciones.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
    get_application_knowledge,
    get_application_manager,
    is_application_available,
    is_capability_available,
)
from src.hands.planner.application_integration import (
    ApplicationKnowledgeIntegrator,
)


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


def _make_integrator_with_manager(manager):
    """ApplicationKnowledgeIntegrator con un gestor inyectado."""
    integrator = ApplicationKnowledgeIntegrator.__new__(ApplicationKnowledgeIntegrator)
    integrator.application_manager = manager
    integrator.memory_manager = None
    return integrator


def _make_app_with_executable(
    name="Chrome",
    app_type="browser",
    executable=None,
    url=None,
    capabilities=None,
    **overrides,
) -> ApplicationKnowledge:
    """Crea una ApplicationKnowledge con ejecutable/url controlados."""
    defaults = dict(
        name=name,
        type=app_type,
        executable=executable,
        url=url,
        capabilities=capabilities or [],
        ui_elements=[],
        states=[],
    )
    defaults.update(overrides)
    return ApplicationKnowledge(**defaults)


def _make_open_cap(
    capability: ApplicationCapability = ApplicationCapability.OPEN,
    name="open_app",
) -> ApplicationCapabilityDef:
    return ApplicationCapabilityDef(
        capability=capability,
        name=name,
        description="d",
        required_ui_elements=[],
        preconditions=[],
        effects=[],
        cost=1.0,
    )


# ---------------------------------------------------------------------------
# 1. MODELO: ApplicationKnowledge.is_available()
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeIsAvailable:
    """is_available() distingue disponible de simplemente declarada."""

    def test_available_with_real_executable(self):
        """Una app cuyo ejecutable existe en el PATH está disponible."""
        app = _make_app_with_executable(
            executable="python", url=None
        )
        assert app.is_available() is True

    def test_available_with_absolute_path_executable(self):
        """Un aple ejecutable por ruta absoluta válida está disponible."""
        app = _make_app_with_executable(
            executable=sys.executable, url=None
        )
        assert app.is_available() is True

    def test_not_available_with_fake_executable(self):
        """Un ejecutable inexistente en el PATH no está disponible."""
        app = _make_app_with_executable(
            executable="nonexistent_executable_99999_xyz", url=None
        )
        assert app.is_available() is False

    def test_not_available_without_executable_or_url(self):
        """Sin ejecutable ni URL, la app no está disponible."""
        app = _make_app_with_executable(executable=None, url=None)
        assert app.is_available() is False

    def test_available_with_url_only(self):
        """Sin ejecutable pero con URL, la app está disponible."""
        app = _make_app_with_executable(executable=None, url="https://example.com")
        assert app.is_available() is True

    def test_available_with_empty_executable_and_url(self):
        """Un ejecutable vacío con URL sigue disponible."""
        app = _make_app_with_executable(executable="   ", url="https://example.com")
        assert app.is_available() is True


# ---------------------------------------------------------------------------
# 2. MODELO: ApplicationKnowledge.is_capability_available()
# ---------------------------------------------------------------------------

class TestApplicationKnowledgeIsCapabilityAvailable:
    """is_capability_available distingue declared + available."""

    def test_available_and_declared(self):
        """App disponible + capability declarada → disponible."""
        app = _make_app_with_executable(
            executable="python",
            capabilities=[_make_open_cap()],
        )
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_available() is True
        assert app.is_capability_available(ApplicationCapability.OPEN) is True

    def test_declared_but_not_available(self):
        """App no disponible (ejecutable inexistente) + capability declarada.

        La capability está **declarada** (is_capable True) pero NO
        **disponible** (is_capability_available False).
        """
        app = _make_app_with_executable(
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        assert app.is_capable(ApplicationCapability.OPEN) is True
        assert app.is_available() is False
        assert app.is_capability_available(ApplicationCapability.OPEN) is False

    def test_available_but_not_declared(self):
        """App disponible pero capability no declarada → no disponible."""
        app = _make_app_with_executable(
            executable="python",
            capabilities=[],  # no capabilities declared
        )
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.is_available() is True
        assert app.is_capability_available(ApplicationCapability.OPEN) is False

    def test_not_declared_not_available(self):
        """App sin ejecutable válido y sin capabilities."""
        app = _make_app_with_executable(executable=None, url=None, capabilities=[])
        assert app.is_capable(ApplicationCapability.OPEN) is False
        assert app.is_available() is False
        assert app.is_capability_available(ApplicationCapability.OPEN) is False

    def test_declared_capability_specific(self):
        """is_capability_available respeta la capability específica."""
        app = _make_app_with_executable(
            executable="python",
            capabilities=[_make_open_cap(capability=ApplicationCapability.OPEN)],
        )
        assert app.is_capability_available(ApplicationCapability.OPEN) is True
        assert app.is_capability_available(ApplicationCapability.CLOSE) is False


# ---------------------------------------------------------------------------
# 3. GESTOR: ApplicationManager.is_application_available / is_capability_available
# ---------------------------------------------------------------------------

class TestApplicationManagerAvailability:
    """El gestor delega a is_available / is_capability_available del modelo."""

    def setup_method(self, _method=None):
        self.manager = _make_minimal_manager()

    def test_is_application_available_true(self):
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["availapp"] = app
        assert self.manager.is_application_available("availapp") is True

    def test_is_application_available_false(self):
        app = _make_app_with_executable(
            "UnavailApp", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["unavailapp"] = app
        assert self.manager.is_application_available("unavailapp") is False

    def test_is_application_available_unknown_app(self):
        assert self.manager.is_application_available("nonexistent") is False

    def test_is_capability_available_true(self):
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["availapp"] = app
        assert self.manager.is_capability_available(
            "availapp", ApplicationCapability.OPEN
        ) is True

    def test_is_capability_available_declared_but_not_available(self):
        """El gesto es el punto clave de 3.3.2.2: declarada ≠ disponible."""
        app = _make_app_with_executable(
            "UnavailApp", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["unavailapp"] = app
        # La capacidad está declarada...
        assert self.manager.get_application("unavailapp").is_capable(
            ApplicationCapability.OPEN
        ) is True
        # ...pero no está disponible.
        assert self.manager.is_capability_available(
            "unavailapp", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_not_declared(self):
        app = _make_app_with_executable(
            "AvailNoCap", "utility", executable="python",
            capabilities=[_make_open_cap(capability=ApplicationCapability.SEARCH)],
        )
        self.manager.applications["availnocap"] = app
        assert self.manager.is_capability_available(
            "availnocap", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_unknown_app(self):
        assert self.manager.is_capability_available(
            "nonexistent", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_with_invalid_enum(self):
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["availapp"] = app
        assert self.manager.is_capability_available(
            "availapp", "not_a_real_capability"
        ) is False


# ---------------------------------------------------------------------------
# 4. FUNCIONES MÓDULO (compatibilidad)
# ---------------------------------------------------------------------------

class TestModuleLevelAvailability:
    """Funciones module-level is_application_available / is_capability_available."""

    def test_is_application_available_with_real_app(self):
        """Chrome está hardcodeado con ejecutable 'chrome'."""
        manager = get_application_manager()
        # Chrome has executable="chrome"; its availability depends on the env.
        # We just verify the function runs and returns a bool.
        result = is_application_available("Chrome")
        assert isinstance(result, bool)

    def test_is_application_available_unknown_app(self):
        assert is_application_available("nonexistent_app_xyz_12345") is False

    def test_is_capability_available_with_enum(self):
        result = is_capability_available("Chrome", ApplicationCapability.OPEN)
        assert isinstance(result, bool)

    def test_is_capability_available_with_string(self):
        result = is_capability_available("Chrome", "open")
        assert isinstance(result, bool)

    def test_is_capability_available_unknown_app(self):
        assert is_capability_available(
            "nonexistent_app_xyz_12345", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_invalid_string(self):
        assert is_capability_available("Chrome", "not_a_real_capability") is False


# ---------------------------------------------------------------------------
# 5. INTEGRADOR: ApplicationKnowledgeIntegrator
# ---------------------------------------------------------------------------

class TestIntegratorAvailability:
    """El integrador expone is_application_available / is_capability_available."""

    def setup_method(self, _method=None):
        self.manager = _make_minimal_manager()
        self.integrator = _make_integrator_with_manager(self.manager)

    def test_is_application_available_delegates_to_model(self):
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["availapp"] = app
        assert self.integrator.is_application_available("availapp") is True

    def test_is_application_available_not_available(self):
        app = _make_app_with_executable(
            "UnavailApp", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["unavailapp"] = app
        assert self.integrator.is_application_available("unavailapp") is False

    def test_is_application_available_unknown_app(self):
        assert self.integrator.is_application_available("nonexistent") is False

    def test_is_capability_available_true(self):
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["availapp"] = app
        assert self.integrator.is_capability_available(
            "availapp", ApplicationCapability.OPEN
        ) is True

    def test_is_capability_available_declared_not_available(self):
        """El integrador distingue declared de available."""
        app = _make_app_with_executable(
            "UnavailApp", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        self.manager.applications["unavailapp"] = app
        # declared (is_application_capable) → True
        assert self.integrator.is_application_capable(
            "unavailapp", ApplicationCapability.OPEN
        ) is True
        # available (is_capability_available) → False
        assert self.integrator.is_capability_available(
            "unavailapp", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_not_declared(self):
        app = _make_app_with_executable(
            "AvailNoCap", "utility", executable="python",
            capabilities=[_make_open_cap(capability=ApplicationCapability.SEARCH)],
        )
        self.manager.applications["availnocap"] = app
        assert self.integrator.is_capability_available(
            "availnocap", ApplicationCapability.OPEN
        ) is False

    def test_is_capability_available_unknown_app(self):
        assert self.integrator.is_capability_available(
            "nonexistent", ApplicationCapability.OPEN
        ) is False


# ---------------------------------------------------------------------------
# 6. DISTINCTIÓN CLAVE: declared ≠ available
# ---------------------------------------------------------------------------

class TestDeclaredVsAvailableDistinction:
    """Prueba el contrato central de 3.3.2.2: declarada ≠ disponible."""

    def test_declared_true_available_false(self):
        """App declarada con capability pero ejecutable no instalado.

        is_application_capable → True (declarada)
        is_capability_available → False (no disponible)
        """
        manager = _make_minimal_manager()
        app = _make_app_with_executable(
            "DeclaredOnly", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        manager.applications["declaredonly"] = app
        integrator = _make_integrator_with_manager(manager)

        assert integrator.is_application_capable(
            "declaredonly", ApplicationCapability.OPEN
        ) is True
        assert integrator.is_application_available("declaredonly") is False
        assert integrator.is_capability_available(
            "declaredonly", ApplicationCapability.OPEN
        ) is False

    def test_both_true(self):
        """App disponible y con capability declarada: ambas True."""
        manager = _make_minimal_manager()
        app = _make_app_with_executable(
            "AvailCap", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        manager.applications["availcap"] = app
        integrator = _make_integrator_with_manager(manager)

        assert integrator.is_application_capable(
            "availcap", ApplicationCapability.OPEN
        ) is True
        assert integrator.is_application_available("availcap") is True
        assert integrator.is_capability_available(
            "availcap", ApplicationCapability.OPEN
        ) is True


# ---------------------------------------------------------------------------
# 7. get_application_knowledge incluye la distinción
# ---------------------------------------------------------------------------

class TestGetApplicationKnowledgeIncludesAvailability:
    """get_application_knowledge expone 'available' y 'declared_capabilities'."""

    def test_get_application_knowledge_has_available_key(self):
        manager = _make_minimal_manager()
        app = _make_app_with_executable(
            "AvailApp", "utility", executable="python",
            capabilities=[_make_open_cap()],
        )
        manager.applications["availapp"] = app
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ):
            knowledge = get_application_knowledge("AvailApp")
        assert "available" in knowledge
        assert knowledge["available"] is True

    def test_get_application_knowledge_declared_and_available_distinct(self):
        manager = _make_minimal_manager()
        app = _make_app_with_executable(
            "UnavailApp", "utility",
            executable="nonexistent_executable_99999_xyz",
            capabilities=[_make_open_cap()],
        )
        manager.applications["unavailapp"] = app
        with patch(
            "src.hands.applications_core.get_application_manager",
            return_value=manager,
        ):
            knowledge = get_application_knowledge("UnavailApp")
        assert knowledge["available"] is False
        assert "open" in knowledge["declared_capabilities"]

    def test_get_application_knowledge_unknown_app(self):
        assert get_application_knowledge("nonexistent_app_xyz_12345") == {}
