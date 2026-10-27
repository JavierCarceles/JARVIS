# -*- coding: utf-8 -*-
"""Tests de resolución por alias — unidad 3.2.2.5 (FASE 3.2.2 — Carga).

Objetivo: "Verificar resolución por alias cuando existe en el código real."

Verifica que ``ApplicationManager.get_application`` resuelve aliases
dinámicos almacenados en ``metadata['aliases']`` de las aplicaciones
registradas (provenientes de ``Entity.aliases`` al materializar apps
desde ``data/memory/entities.json``).

Antes de esta unidad, ``get_application`` solo usaba el diccionario
estático hardcodeado de ``_normalize_name``. Los aliases declarados en
``entities.json`` (ej. GitHub -> ["gh", "git"]) no eran resueltos, por
lo que ``get_application("gh")`` devolvía ``None``.

Los tests usan:
- ``ApplicationManager()`` real (carga Chrome/Spotify hardcodeados +
  YouTube/GitHub/Twitch desde data/memory/entities.json).
- ``_make_min_manager()`` aislado (bypass __init__) para round-trip
  controlado con apps dinámicas que tienen aliases en metadata.
"""

import pytest

from src.hands.applications_core import (
    ApplicationManager,
    ApplicationKnowledge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_min_manager():
    """ApplicationManager aislado (bypass __init__) sin persistencia."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _StubMemoryManager:
        def save_entity(self, entity):
            return True

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _StubMemoryManager()
    return manager


def _make_entity_app(name, app_type, aliases=None, **kwargs):
    """Crea un ApplicationKnowledge con metadata que contiene aliases,
    simulando el resultado de _reconstruct_application."""
    metadata = {"entity_id": name.lower()}
    if aliases:
        metadata["aliases"] = list(aliases)
    return ApplicationKnowledge(
        name=name,
        type=app_type,
        metadata=metadata,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Verificación de pre-condición: apps cargadas desde entities tienen aliases en metadata
# ---------------------------------------------------------------------------

class TestEntityAliasesInMetadata:
    """Verifica que las apps cargadas desde entities.json tienen sus
    aliases almacenados en ``metadata['aliases']`` tras __init__."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    def test_github_has_aliases_in_metadata(self, manager):
        app = manager.get_application("GitHub")
        assert app is not None
        assert app.metadata.get("aliases") == ["gh", "git"]

    def test_youtube_has_aliases_in_metadata(self, manager):
        app = manager.get_application("YouTube")
        assert app is not None
        assert app.metadata.get("aliases") == ["yt", "you"]

    def test_twitch_has_aliases_in_metadata(self, manager):
        app = manager.get_application("Twitch")
        assert app is not None
        assert app.metadata.get("aliases") == ["twich", "twitchtv"]

    def test_entity_id_stored_in_metadata(self, manager):
        """``_reconstruct_metadata`` almacena entity_id en metadata."""
        app = manager.get_application("GitHub")
        assert app is not None
        assert app.metadata.get("entity_id") == "github"


# ---------------------------------------------------------------------------
# 2. Resolución por alias: apps cargadas desde entities (GitHub, YouTube, Twitch)
# ---------------------------------------------------------------------------

class TestAliasResolutionEntityLoadedApps:
    """``get_application`` resuelve aliases de apps cargadas desde
    entities.json (data/memory/entities.json)."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    @pytest.mark.parametrize("alias", ["gh", "git", "Gh", "GIT"])
    def test_resolve_github_by_alias(self, manager, alias):
        result = manager.get_application(alias)
        assert result is not None
        assert result.name == "GitHub"

    @pytest.mark.parametrize("alias", ["yt", "you", "YT", "You"])
    def test_resolve_youtube_by_alias(self, manager, alias):
        result = manager.get_application(alias)
        assert result is not None
        assert result.name == "YouTube"

    @pytest.mark.parametrize("alias", ["twich", "twitchtv", "Twich", "TWITCHTV"])
    def test_resolve_twitch_by_alias(self, manager, alias):
        result = manager.get_application(alias)
        assert result is not None
        assert result.name == "Twitch"

    def test_resolve_github_by_alias_returns_same_object_as_name(self, manager):
        """El alias y el nombre canónico devuelven la misma instancia."""
        by_name = manager.get_application("GitHub")
        by_alias = manager.get_application("gh")
        assert by_name is not None
        assert by_alias is not None
        assert by_name is by_alias


# ---------------------------------------------------------------------------
# 3. Coherencia: alias no interfiere con resolución por nombre (no regresión)
# ---------------------------------------------------------------------------

class TestAliasResolutionNoRegression:
    """La resolución por alias no debe romper la resolución existente."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    @pytest.mark.parametrize("query", ["chrome", "Chrome", "CHROME"])
    def test_hardcoded_alias_still_works(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "Chrome"

    def test_static_alias_google_chrome(self, manager):
        """'Google Chrome' sigue resolviendo a Chrome (alias estático)."""
        result = manager.get_application("Google Chrome")
        assert result is not None
        assert result.name == "Chrome"

    @pytest.mark.parametrize("query", ["youtube", "YouTube", "YOUTUBE"])
    def test_canonical_name_still_works(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "YouTube"

    def test_spotify_resolvable_by_name(self, manager):
        result = manager.get_application("Spotify")
        assert result is not None
        assert result.name == "Spotify"


# ---------------------------------------------------------------------------
# 4. Negativo: alias o nombre inexistente devuelve None
# ---------------------------------------------------------------------------

class TestAliasResolutionNotFound:
    """``get_application`` devuelve ``None`` para aliases/nombres inexistentes."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    @pytest.mark.parametrize("alias", ["nonexistent_alias", "xyz", "gh_invalid", "fakeyt"])
    def test_unknown_alias_returns_none(self, manager, alias):
        assert manager.get_application(alias) is None

    def test_none_input_returns_none(self, manager):
        assert manager.get_application(None) is None

    def test_empty_string_returns_none(self, manager):
        assert manager.get_application("") is None


# ---------------------------------------------------------------------------
# 5. Resolución por alias: apps dinámicas (registro con metadata aliases)
# ---------------------------------------------------------------------------

class TestAliasResolutionDynamicRegistration:
    """``get_application`` resuelve aliases de apps registradas dinámicamente
    con ``metadata['aliases']`` establecido explícitamente."""

    def test_alias_resolves_for_dynamically_registered_app(self):
        manager = _make_min_manager()
        app = _make_entity_app(
            "GitHub", "development", aliases=["gh", "git"],
            executable="chrome.exe",
        )
        assert manager.register_application(app) is True
        # Resolución por alias
        result = manager.get_application("gh")
        assert result is not None
        assert result is app
        assert result.name == "GitHub"

    def test_alias_case_insensitive_for_dynamic_app(self):
        manager = _make_min_manager()
        app = _make_entity_app(
            "GitLab", "development", aliases=["gl", "gitlab"],
        )
        manager.register_application(app)
        assert manager.get_application("GL") is app
        assert manager.get_application("gl") is app
        assert manager.get_application("GitLab") is app

    def test_alias_does_not_shadow_existing_app(self):
        """Un alias que coincide con una clave canónica distinta no debe
        devolver la app equivocada. La resolución prioriza el lookup directo."""
        manager = _make_min_manager()
        chrome = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
            metadata={"entity_id": "chrome"},
        )
        manager.register_application(chrome)
        # 'chrome' como alias no existe en el diccionario estático ni en metadata
        # de Chrome (no tiene aliases), por lo que el lookup directo gana.
        result = manager.get_application("chrome")
        assert result is chrome

    def test_dynamically_registered_app_without_aliases_resolves_by_name(self):
        """Una app registrada sin aliases sigue resolviéndose por su nombre."""
        manager = _make_min_manager()
        app = _make_entity_app("TestApp", "utility", aliases=None)
        manager.register_application(app)
        assert manager.get_application("TestApp") is app
        assert manager.get_application("testapp") is app


# ---------------------------------------------------------------------------
# 6. Resolución por alias: método _resolve_alias directamente
# ---------------------------------------------------------------------------

class TestResolveAliasMethod:
    """``_resolve_alias`` retorna la app cuyo metadata['aliases'] contiene
    el nombre normalizado, o ``None`` si no hay coincidencia."""

    def test_resolve_alias_finds_matching_app(self):
        manager = _make_min_manager()
        app = _make_entity_app(
            "GitHub", "development", aliases=["gh", "git"],
        )
        manager.register_application(app)
        assert manager._resolve_alias("gh") is app
        assert manager._resolve_alias("git") is app

    def test_resolve_alias_no_match_returns_none(self):
        manager = _make_min_manager()
        app = _make_entity_app(
            "GitHub", "development", aliases=["gh", "git"],
        )
        manager.register_application(app)
        assert manager._resolve_alias("nonexistent") is None

    def test_resolve_alias_empty_manager_returns_none(self):
        manager = _make_min_manager()
        assert manager._resolve_alias("anything") is None

    def test_resolve_alias_handles_none_metadata(self):
        """Apps con metadata=None o metadata sin 'aliases' no causan error."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="NoMeta", type="utility", executable="nometa",
            metadata=None,
        )
        manager.register_application(app)
        # No raises
        assert manager._resolve_alias("anyname") is None

    def test_resolve_alias_handles_non_dict_metadata(self):
        """metadata que no es dict (p.ej. lista) se ignora gracefully."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="BadMeta", type="utility", executable="badmeta",
            metadata=[1, 2, 3],  # tipo incorrecto
        )
        manager.register_application(app)
        assert manager._resolve_alias("anyname") is None


# ---------------------------------------------------------------------------
# 7. _normalize_name como static method: sin cambios (compatibilidad)
# ---------------------------------------------------------------------------

class TestNormalizeNameBackwardCompat:
    """``_normalize_name`` sigue siendo un ``@staticmethod`` que resuelve
    aliases estáticos hardcodeados. No se modificó su contrato."""

    @pytest.mark.parametrize("alias,canonical", [
        ("Google Chrome", "chrome"),
        ("Mozilla Firefox", "firefox"),
        ("Bloc de Notas", "notepad"),
        ("command prompt", "cmd"),
        ("file explorer", "explorer"),
        ("microsoft paint", "paint"),
    ])
    def test_static_alias_resolves_to_canonical(self, alias, canonical):
        assert ApplicationManager._normalize_name(alias) == canonical

    def test_unknown_name_passes_through(self):
        assert ApplicationManager._normalize_name("CustomApp") == "customapp"

    def test_none_safe(self):
        assert ApplicationManager._normalize_name(None) == ""
