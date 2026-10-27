# -*- coding: utf-8 -*-
"""Tests de resolucion por nombre — unidad 3.2.2.4 (FASE 3.2.2 — Carga).

Objetivo: "Verificar resolucion por nombre".

Verifica que ``ApplicationManager.get_application`` resuelve aplicaciones
por su nombre de forma case-insensitive, tanto para apps hardcodeadas
(Chrome, Spotify) como para apps cargadas desde entidades
(YouTube, GitHub, Twitch).

Tambien verifica la coherencia del identificador canónico:
``register_application`` y ``_load_custom_applications`` usan
``_normalize_name`` como clave (no ``app.name.lower()``), de modo que
una app cuyo nombre coincide con un alias hardcodeado (ej. "Google
Chrome") se almacena bajo la clave canónica ("chrome") y es resoluble
por su nombre y por el alias. Antes de la correccion de 3.2.2.4,
``register_application`` usaba ``app.name.lower()`` lo que producia una
clave divergente de la que ``get_application`` usa para buscar, rompiendo
la resolucion para nombres con alias.

Los tests usan:
- ``ApplicationManager()`` real (carga Chrome/Spotify + entities de data/memory/entities.json).
- ``_make_min_manager()`` aislado (bypass __init__) con MemoryManager falso para round-trip controlado.
"""

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationCapabilityDef,
    ApplicationKnowledge,
    ApplicationManager,
    ApplicationState,
    UIElement,
)
from src.memory.storage import Entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_min_manager():
    """ApplicationManager aislado (bypass __init__) con MemoryManager falso.

    Evita registrar Chrome/Spotify y evita toda persistencia a entities.json.
    Ideal para testear el round-trip register -> get_application de forma controlada.
    """
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}

    class _CountingMemoryManager:
        def __init__(self):
            self.saved = []
            self.save_calls = 0

        def save_entity(self, entity):
            self.save_calls += 1
            self.saved.append(entity)
            return True

        def get_entities_by_type(self, t):
            return []

    manager.memory_manager = _CountingMemoryManager()
    return manager


# ---------------------------------------------------------------------------
# 1. Resolucion por nombre: apps hardcodeadas (Chrome, Spotify)
# ---------------------------------------------------------------------------

class TestNameResolutionHardcodedApps:
    """``get_application`` resuelve apps hardcodeadas por su nombre,
    case-insensitive, tanto con nombre canónico como con el nombre
    display completo (ej. "Chrome", no "Google Chrome")."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    @pytest.mark.parametrize("query", ["chrome", "Chrome", "CHROME", " Chrome "])
    def test_resolve_chrome_by_name(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "Chrome"
        assert result.type == "browser"

    @pytest.mark.parametrize("query", ["spotify", "Spotify", "SPOTIFY"])
    def test_resolve_spotify_by_name(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "Spotify"
        assert result.type == "media"


# ---------------------------------------------------------------------------
# 2. Resolucion por nombre: apps cargadas desde entities (YouTube, GitHub, Twitch)
# ---------------------------------------------------------------------------

class TestNameResolutionEntityLoadedApps:
    """``get_application`` resuelve apps cargadas desde entities.json
    (data/memory/entities.json) por su nombre, case-insensitive."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    @pytest.mark.parametrize("query", ["youtube", "YouTube", "YOUTUBE"])
    def test_resolve_youtube_by_name(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "YouTube"
        assert result.type == "video_platform"

    @pytest.mark.parametrize("query", ["github", "GitHub", "GITHUB"])
    def test_resolve_github_by_name(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "GitHub"
        assert result.type == "development"

    @pytest.mark.parametrize("query", ["twitch", "Twitch", "TWITCH"])
    def test_resolve_twitch_by_name(self, manager, query):
        result = manager.get_application(query)
        assert result is not None
        assert result.name == "Twitch"
        assert result.type == "streaming"


# ---------------------------------------------------------------------------
# 3. Coherencia de clave: register_application usa _normalize_name
# ---------------------------------------------------------------------------

class TestRegisterApplicationUsesNormalizeName:
    """``register_application`` debe usar ``_normalize_name`` como clave
    para ser consistente con ``get_application``. Antes de 3.2.2.4 usaba
    ``app.name.lower()``, rompiendo la resolucion para nombres con alias."""

    def test_register_alias_name_resolvable_by_name(self):
        """Una app registrada con nombre 'Google Chrome' se almacena bajo
        la clave canónica 'chrome' y es resoluble por 'Google Chrome'
        y por 'chrome'."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="Google Chrome", type="browser", executable="chrome",
        )
        assert manager.register_application(app) is True
        # Resoluble por el nombre completo (alias)
        result1 = manager.get_application("Google Chrome")
        assert result1 is not None
        assert result1 is app
        # Resoluble por la clave canónica
        result2 = manager.get_application("chrome")
        assert result2 is not None
        assert result2 is app

    def test_register_alias_name_stored_under_normalized_key(self):
        """La clave usada en self.applications es _normalize_name(app.name),
        no app.name.lower()."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="Google Chrome", type="browser", executable="chrome",
        )
        manager.register_application(app)
        assert "chrome" in manager.applications
        assert "google chrome" not in manager.applications

    def test_register_alias_name_entity_id_uses_normalized_key(self):
        """El Entity.id derivado usa la clave normalizada."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="Google Chrome", type="browser", executable="chrome",
        )
        manager.register_application(app)
        saved_entity = manager.memory_manager.saved[-1]
        assert saved_entity.id == "app_chrome"

    def test_register_non_alias_name_still_works(self):
        """Nombres sin alias se registran y resuelven igual (lowercase)."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="MyCustomApp", type="utility", executable="mycustomapp",
        )
        assert manager.register_application(app) is True
        assert manager.get_application("MyCustomApp") is not None
        assert manager.get_application("mycustomapp") is not None
        assert manager.applications["mycustomapp"] is app

    def test_register_alias_name_duplicate_detected(self):
        """Registrar 'Google Chrome' cuando Chrome ya está registrado devuelve False."""
        manager = _make_min_manager()
        # Pre-registrar Chrome bajo la clave canónica
        manager.register_application(
            ApplicationKnowledge(name="Chrome", type="browser", executable="chrome")
        )
        # Intentar registrar "Google Chrome" debe detectarse como duplicado
        result = manager.register_application(
            ApplicationKnowledge(name="Google Chrome", type="browser", executable="gc")
        )
        assert result is False
        # Chrome original no se sobreescribe
        existing = manager.get_application("chrome")
        assert existing.executable == "chrome"


# ---------------------------------------------------------------------------
# 4. Round-trip: register -> resolve -> verify
# ---------------------------------------------------------------------------

class TestNameResolutionRoundTrip:
    """Round-trip: register_application almacena bajo la clave normalizada;
    get_application la resuelve de vuelta usando _normalize_name."""

    def test_round_trip_exact_name(self):
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="TestApp", type="utility", executable="testapp",
        )
        manager.register_application(app)
        result = manager.get_application("TestApp")
        assert result is not None
        assert result is app
        assert result.name == "TestApp"

    def test_round_trip_case_insensitive(self):
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="CaseApp", type="utility", executable="caseapp",
        )
        manager.register_application(app)
        assert manager.get_application("CASEAPP") is app
        assert manager.get_application("caseapp") is app
        assert manager.get_application("CaseApp") is app

    def test_round_trip_with_spaces_and_case(self):
        """Normalización: strip + lower + alias resolution."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="Microsoft Edge", type="browser", executable="edge",
        )
        manager.register_application(app)
        # Resoluble por el nombre con espacios y mayúsculas
        assert manager.get_application("  Microsoft Edge  ") is app
        # Resoluble por la clave canónica
        assert manager.get_application("edge") is app
        # No almacenado bajo el nombre sin normalizar
        assert "microsoft edge" not in manager.applications


# ---------------------------------------------------------------------------
# 5. Negativo: apps inexistentes
# ---------------------------------------------------------------------------

class TestNameResolutionNotFound:
    """``get_application`` devuelve None para apps que no existen."""

    @pytest.fixture
    def manager(self):
        return ApplicationManager()

    def test_nonexistent_name(self, manager):
        assert manager.get_application("nonexistent_app_xyz") is None

    def test_nonexistent_case_variants(self, manager):
        assert manager.get_application("NONEXISTENT_APP_XYZ") is None
        assert manager.get_application("NonExistent_App_XyZ") is None


# ---------------------------------------------------------------------------
# 6. Coherencia interna: ApplicationManager + _load_custom_applications
# ---------------------------------------------------------------------------

class TestLoadCustomApplicationsUsesNormalizeName:
    """``_load_custom_applications`` también usa ``_normalize_name`` como clave,
    manteniendo coherencia con ``register_application`` y ``get_application``."""

    def test_entity_with_alias_matching_name_skipped(self):
        """Una entity cuyo nombre normaliza a una app ya registrada se omite
        (no crea duplicado). Chrome + entity 'Google Chrome' -> clave 'chrome'."""
        manager = _make_min_manager()
        manager.register_application(
            ApplicationKnowledge(name="Chrome", type="browser", executable="chrome")
        )

        class _FakeMM:
            def get_entities_by_type(self, t):
                if t == "application":
                    return [Entity.from_dict({
                        "id": "app_google_chrome",
                        "type": "application",
                        "name": "Google Chrome",
                        "properties": {
                            "type": "browser",
                            "executable": "chrome",
                            "url": "https://chrome.google.com",
                            "login_required": False,
                            "capabilities": ["open"],
                            "ui_elements": [],
                            "states": ["closed"],
                        },
                        "aliases": ["google", "gc"],
                        "tags": [],
                        "confidence": 1.0,
                        "created_at": "2024-01-01",
                        "updated_at": "2024-01-01",
                        "metadata": None,
                    })]
                return []

            def save_entity(self, entity):
                pass

        manager.memory_manager = _FakeMM()
        manager._load_custom_applications()
        # Chrome está bajo 'chrome' (normalizado desde "Google Chrome")
        assert "chrome" in manager.applications
        # No hay entrada adicional bajo 'google chrome'
        assert "google chrome" not in manager.applications
        # Sigue resoluble
        assert manager.get_application("google chrome") is manager.applications["chrome"]

    def test_entity_without_alias_loaded_normally(self):
        """Una entity sin coincidencia de alias se carga bajo su clave normalizada."""
        manager = _make_min_manager()

        class _FakeMM:
            def get_entities_by_type(self, t):
                if t == "application":
                    return [Entity.from_dict({
                        "id": "youtube",
                        "type": "application",
                        "name": "YouTube",
                        "properties": {
                            "url": "https://www.youtube.com",
                            "executable": "chrome.exe",
                            "category": "video_platform",
                        },
                        "aliases": ["yt", "you"],
                        "tags": [],
                        "confidence": 1.0,
                        "created_at": "2024-01-01",
                        "updated_at": "2024-01-01",
                        "metadata": None,
                    })]
                return []

            def save_entity(self, entity):
                pass

        manager.memory_manager = _FakeMM()
        manager._load_custom_applications()
        assert "youtube" in manager.applications
        assert manager.applications["youtube"].name == "YouTube"
        assert manager.get_application("youtube") is not None
        assert manager.get_application("YouTube") is not None
