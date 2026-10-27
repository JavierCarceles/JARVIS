# -*- coding: utf-8 -*-
"""Tests de evasion de duplicados en register_application — unidad 3.2.2.3.

Objetivo: "Evitar duplicados al registrar".

Verifica que ``ApplicationManager.register_application`` evita registrar
una aplicación que ya está presente en ``self.applications``, omitiendo
la llamada a ``save_entity`` y devolviendo ``False`` en el segundo
intento. La detección se basa en la clave ``self._normalize_name(app.name)``
(case-insensitive + alias resolution), manteniendo consistencia con
``get_application`` que también usa ``_normalize_name`` y con
``_load_custom_applications`` que ya omite apps ya registradas.

Los tests usan un MemoryManager aislado (mock) que cuenta llamadas a
``save_entity`` para verificar que no se duplica la persistencia.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_min_manager():
    """ApplicationManager aislado (bypass __init__) con memory_manager falso.

    El ``_CountingMemoryManager`` registra cuántas veces se llama a
    ``save_entity`` y almacena las entidades recibidas. No persiste a disco.
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


def _make_app(name="DupApp", app_type="browser", executable="dupapp"):
    """Crea una ApplicationKnowledge mínima para pruebas."""
    return ApplicationKnowledge(
        name=name, type=app_type, executable=executable,
    )


# ---------------------------------------------------------------------------
# 1. Duplicado: segunda llamada devuelve False y no llama a save_entity
# ---------------------------------------------------------------------------

class TestRegisterApplicationDuplicateAvoidance:
    """register_application evita duplicados al registrar."""

    def test_second_registration_returns_false(self):
        """Registrar la misma app dos veces: segunda vez devuelve False."""
        manager = _make_min_manager()
        app = _make_app(name="DupApp")
        assert manager.register_application(app) is True
        assert manager.register_application(app) is False

    def test_duplicate_does_not_call_save_entity(self):
        """La segunda llamada no invoca save_entity (evita escritura duplicada)."""
        manager = _make_min_manager()
        app = _make_app(name="DupApp")
        manager.register_application(app)
        first_calls = manager.memory_manager.save_calls
        manager.register_application(app)
        assert manager.memory_manager.save_calls == first_calls

    def test_duplicate_does_not_overwrite_existing_app(self):
        """La app registrada original no se sobreescribe con una instancia distinta."""
        manager = _make_min_manager()
        app_v1 = _make_app(name="DupApp", executable="dupapp_v1")
        app_v2 = _make_app(name="DupApp", executable="dupapp_v2")
        manager.register_application(app_v1)
        result = manager.register_application(app_v2)
        assert result is False
        existing = manager.get_application("dupapp")
        assert existing is app_v1
        assert existing.executable == "dupapp_v1"

    def test_duplicate_save_entity_called_exactly_once(self):
        """save_entity se llama exactamente una vez tras dos registros del mismo app."""
        manager = _make_min_manager()
        app = _make_app(name="DupApp")
        manager.register_application(app)
        manager.register_application(app)
        assert manager.memory_manager.save_calls == 1

    def test_duplicate_entity_stored_once(self):
        """Solo se almacena una entidad para la app duplicada."""
        manager = _make_min_manager()
        app = _make_app(name="DupApp")
        manager.register_application(app)
        manager.register_application(app)
        assert len(manager.memory_manager.saved) == 1

    def test_duplicate_id_preserved(self):
        """La entidad almacenada conserva el id derivado del nombre."""
        manager = _make_min_manager()
        app = _make_app(name="DupApp")
        manager.register_application(app)
        entity = manager.memory_manager.saved[0]
        assert entity.id == "app_dupapp"


# ---------------------------------------------------------------------------
# 2. Detección de duplicados: normalización por app.name.lower()
# ---------------------------------------------------------------------------

class TestRegisterApplicationDuplicateDetection:
    """La detección de duplicados usa app.name.lower() como clave."""

    def test_case_insensitive_duplicate(self):
        """Mismo nombre con diferente capitalización se detecta como duplicado."""
        manager = _make_min_manager()
        app = _make_app(name="MyApp")
        manager.register_application(app)
        # "MyApp" y "myapp" comparten la clave "myapp"
        dup = _make_app(name="MYAPP", executable="other")
        assert manager.register_application(dup) is False
        assert manager.get_application("myapp") is app

    def test_different_apps_not_duplicates(self):
        """Aplicaciones distintas no se detectan como duplicados."""
        manager = _make_min_manager()
        app1 = _make_app(name="AppAlpha", executable="alpha")
        app2 = _make_app(name="AppBeta", executable="beta")
        assert manager.register_application(app1) is True
        assert manager.register_application(app2) is True
        assert "appalpha" in manager.applications
        assert "appbeta" in manager.applications
        assert manager.memory_manager.save_calls == 2

    def test_spaces_and_case_variants(self):
        """Nombre con espacios/extra se normaliza: solo el nombre lower importa."""
        manager = _make_min_manager()
        app = _make_app(name="TestApp")
        manager.register_application(app)
        # "testapp" like key (exact name lower)
        assert manager.register_application(_make_app(name="TESTAPP")) is False

    def test_app_with_ui_elements_not_duplicated(self):
        """App con ui_elements/states: el duplicado se detecta igualmente."""
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="UiApp", type="browser", executable="uiapp",
            ui_elements=[UIElement(name="btn", type="button",
                                   required_capability=ApplicationCapability.OPEN)],
            states=[ApplicationState.OPEN, ApplicationState.ACTIVE],
        )
        assert manager.register_application(app) is True
        assert manager.register_application(app) is False
        assert manager.memory_manager.save_calls == 1


# ---------------------------------------------------------------------------
# 3. Consistencia con _load_custom_applications
# ---------------------------------------------------------------------------

class TestRegisterDuplicateConsistencyWithLoad:
    """register_application y _load_custom_applications usan la misma clave."""

    def test_load_skips_same_key_as_register(self):
        """Una app registrada no se vuelve a registrar al cargar desde entidades."""
        from src.memory.storage import Entity

        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="Chrome", type="browser", executable="chrome",
        )
        # Simula que Chrome ya está registrado (como lo hace __init__)
        manager.register_application(app)

        # Ahora simula que MemoryManager devuelve una entity para Chrome
        class _EntityBackedMemoryManager:
            def __init__(self):
                self.saved = []
                self.save_calls = 0

            def save_entity(self, entity):
                self.save_calls += 1
                self.saved.append(entity)
                return True

            def get_entities_by_type(self, t):
                if t == "application":
                    return [Entity.from_dict({
                        "id": "app_chrome",
                        "type": "application",
                        "name": "Chrome",
                        "properties": {
                            "type": "browser",
                            "executable": "chrome",
                            "url": None,
                            "login_required": False,
                            "capabilities": ["open"],
                            "ui_elements": [],
                            "states": ["closed"],
                        },
                        "aliases": [],
                        "tags": [],
                        "confidence": 1.0,
                    })]
                return []

        manager.memory_manager = _EntityBackedMemoryManager()
        manager._load_custom_applications()
        # Chrome ya estaba registrado → _load_custom_applications lo omite
        assert len(manager.applications) == 1
        assert "chrome" in manager.applications

    def test_load_registers_different_app(self):
        """Una app distinta NO registrada se carga normalmente."""
        from src.memory.storage import Entity

        manager = _make_min_manager()
        manager.register_application(ApplicationKnowledge(
            name="AppOne", type="browser", executable="one",
        ))

        class _EntityBackedMemoryManager:
            def __init__(self):
                self.saved = []
                self.save_calls = 0

            def save_entity(self, entity):
                self.save_calls += 1
                self.saved.append(entity)
                return True

            def get_entities_by_type(self, t):
                if t == "application":
                    return [Entity.from_dict({
                        "id": "app_apptwo",
                        "type": "application",
                        "name": "AppTwo",
                        "properties": {
                            "type": "browser",
                            "executable": "two",
                            "url": None,
                            "login_required": False,
                            "capabilities": [],
                            "ui_elements": [],
                            "states": ["closed"],
                        },
                        "aliases": [],
                        "tags": [],
                        "confidence": 1.0,
                    })]
                return []

        manager.memory_manager = _EntityBackedMemoryManager()
        manager._load_custom_applications()
        assert "appone" in manager.applications
        assert "apptwo" in manager.applications
        assert len(manager.applications) == 2


# ---------------------------------------------------------------------------
# 4. Integridad: register_application sigue funcionando para apps nuevas
# ---------------------------------------------------------------------------

class TestRegisterApplicationNotBlocked:
    """Verifica que la prevención de duplicados no bloquea registros nuevos."""

    def test_register_new_app_still_true(self):
        manager = _make_min_manager()
        app = ApplicationKnowledge(
            name="NewApp", type="utility", executable="newapp",
        )
        assert manager.register_application(app) is True
        assert "newapp" in manager.applications

    def test_register_after_duplicate_re_registers_different_app(self):
        """Después de un duplicado rechazado, una app nueva se registra OK."""
        manager = _make_min_manager()
        app = _make_app(name="FirstApp")
        manager.register_application(app)
        # Intento de duplicado → rechazado
        assert manager.register_application(_make_app(name="FIRSTAPP")) is False
        # App nueva → registrada
        assert manager.register_application(_make_app(name="SecondApp")) is True
        assert manager.memory_manager.save_calls == 2
        saved_ids = [e.id for e in manager.memory_manager.saved]
        assert "app_firstapp" in saved_ids
        assert "app_secondapp" in saved_ids
        assert len(saved_ids) == 2
