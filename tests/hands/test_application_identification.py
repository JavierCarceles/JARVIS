# -*- coding: utf-8 -*-
"""Tests del contrato minimo 3.1.2.1 — identificacion univoca de una aplicacion.

Verifican el mecanismo ACTUAL de identificacion de ApplicationKnowledge sin
modificar codigo de produccion. El contrato definido en 3.1.2.1 establece que
`ApplicationKnowledge.name` (en forma case-insensitive, lowercased) es el
identificador unico: se usa como clave en `ApplicationManager.applications` y
como base del Entity.id (`app_{name.lower()}`).
"""

from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationCapabilityDef,
    ApplicationCapability,
)
from src.memory.storage import Entity


class TestApplicationNameIsIdentifier:
    """`name` es el campo que identifica inequívocamente una aplicación."""

    def test_name_is_required_no_default(self):
        """ApplicationKnowledge no permite construir sin `name`."""
        with pytest.raises(TypeError):
            ApplicationKnowledge(type="browser")

    def test_name_identifies_in_manager_dict(self):
        """El gestor indexa por `name.lower()`."""
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}

        class FakeMM:
            def save_entity(self, entity):
                pass
        manager.memory_manager = FakeMM()

        app = ApplicationKnowledge(name="MyApp", type="utility", executable="myapp")
        manager.register_application(app)
        assert "myapp" in manager.applications
        assert manager.applications["myapp"] is app

    def test_name_case_insensitive(self):
        """El identificador es case-insensitive: 'MYAPP' resuelve a 'myapp'."""
        manager = ApplicationManager()
        assert manager.get_application("CHROME") is not None
        assert manager.get_application("chrome") is not None
        assert manager.get_application("Chrome") is not None


class TestNormalizeName:
    """`_normalize_name` resuelve aliases a la clave canónica (name.lower())."""

    @pytest.mark.parametrize("alias,canonical", [
        ("Google Chrome", "chrome"),
        ("Mozilla Firefox", "firefox"),
        ("Bloc de Notas", "notepad"),
        ("command prompt", "cmd"),
        ("file explorer", "explorer"),
        ("microsoft paint", "paint"),
    ])
    def test_alias_resolves_to_canonical(self, alias, canonical):
        assert ApplicationManager._normalize_name(alias) == canonical

    def test_unknown_name_passes_through(self):
        """Un nombre sin alias se normaliza a su lowercased directamente."""
        assert ApplicationManager._normalize_name("CustomApp") == "customapp"

    def test_none_safe(self):
        assert ApplicationManager._normalize_name(None) == ""


class TestGetApplicationByAlias:
    """`get_application` resuelve alias mediante `_normalize_name`."""

    def test_resolve_alias_to_app(self):
        manager = ApplicationManager()
        result = manager.get_application("Google Chrome")
        assert result is not None
        assert result.name == "Chrome"

    def test_resolve_canonical_name(self):
        manager = ApplicationManager()
        result = manager.get_application("chrome")
        assert result is not None
        assert result.name == "Chrome"

    def test_unknown_returns_none(self):
        manager = ApplicationManager()
        assert manager.get_application("nonexistent_app_xyz") is None


class TestEntityIdUsesName:
    """El Entity persistido usa `app_{name.lower()}` como id."""

    def test_entity_id_matches_name_lowercased(self):
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}
        saved = {}

        def fake_save_entity(entity):
            saved["entity"] = entity

        fake_mm = type("FakeMM", (), {"save_entity": staticmethod(fake_save_entity)})
        manager.memory_manager = fake_mm()

        app = ApplicationKnowledge(name="TestApp", type="utility", executable="testapp")
        manager.register_application(app)
        assert saved["entity"].id == "app_testapp"
        assert saved["entity"].type == "application"
        assert saved["entity"].name == "TestApp"

    def test_entity_aliases_always_empty(self):
        """`register_application` persiste aliases=[] siempre (no conecta _normalize_name)."""
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}
        saved = {}

        def fake_save_entity(entity):
            saved["entity"] = entity

        class FakeMM:
            def save_entity(self, entity):
                fake_save_entity(entity)
        manager.memory_manager = FakeMM()

        app = ApplicationKnowledge(name="MyBrowser", type="browser", executable="mybrowser")
        manager.register_application(app)
        assert saved["entity"].aliases == []


class TestNameUniquenessBehavior:
    """El nombre lowercased es la única clave; registro duplicado sobrescribe."""

    def test_same_name_overwrites(self):
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}

        class FakeMM:
            def save_entity(self, entity):
                pass
        manager.memory_manager = FakeMM()

        app1 = ApplicationKnowledge(name="DupApp", type="utility", executable="dup1")
        app2 = ApplicationKnowledge(name="dupapp", type="browser", executable="dup2")
        manager.register_application(app1)
        manager.register_application(app2)
        # Ambos se resuelven a la misma clave "dupapp"
        assert len(manager.applications) == 1
        assert manager.applications["dupapp"] is app2
        assert manager.applications["dupapp"].executable == "dup2"

    def test_distinct_names_cohabit(self):
        manager = ApplicationManager.__new__(ApplicationManager)
        manager.applications = {}

        class FakeMM:
            def save_entity(self, entity):
                pass
        manager.memory_manager = FakeMM()

        manager.register_application(ApplicationKnowledge(name="AppA", type="utility", executable="a"))
        manager.register_application(ApplicationKnowledge(name="AppB", type="utility", executable="b"))
        assert len(manager.applications) == 2


class TestNameInKnowledgeOutput:
    """`get_application_knowledge` expone `name` como identificador público."""

    def test_knowledge_exposes_name(self):
        from src.hands.applications_core import get_application_knowledge
        knowledge = get_application_knowledge("chrome")
        assert knowledge["name"] == "Chrome"
        assert knowledge["type"] == "browser"
