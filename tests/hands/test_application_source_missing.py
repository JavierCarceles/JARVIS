# -*- coding: utf-8 -*-
"""Tests de verificacion del comportamiento cuando la fuente no existe
— unidad 3.2.1.3 (FASE 3.2.1 — Fuente de datos).

Verifica el comportamiento REAL (no el esperado) del modelo Application
Knowledge (ApplicationManager) y de sus fuentes de datos cuando los
ficheros fuente no existen en el sistema de archivos:

1. `src/memory/storage.py` — `JSONStorage.load()` devuelve valores por
   defecto (`[]`, `{}`) cuando el fichero no existe, sin lanzar excepcion.
2. `src/memory/storage.py` — `MemoryManager.get_entities_by_type()` devuelve
   `[]` cuando `data/memory/entities.json` no existe; `get_entity()` devuelve
   `None`.
3. `src/hands/applications_core.py` — `ApplicationManager.__init__()` no se
   rompe cuando la fuente (entities.json) no existe; las apps hardcodeadas
   (Chrome, Spotify) permanecen disponibles.
4. `src/hands/applications_core.py` — `_load_custom_applications()` (stub,
   aplicaciones_core.py:510) no lanza excepciones cuando las entidades
   no existen.
5. `src/memory/conversation.py` — `DomainMemory` con `knowledge/applications.json`
   ausente deja `self.applications` como `{}`.

No modifica codigo de produccion. Los tests de runtime usan un MemoryManager
aislado en tmp_path (sin ficheros de datos) para reproducir la condicion
de "fuente no existe" de forma segura.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationManager,
)
from src.memory.storage import (
    JSONStorage,
    MemoryManager,
    MemoryType,
)


# ---------------------------------------------------------------------------
# 1. JSONStorage: comportamiento cuando el fichero no existe
# ---------------------------------------------------------------------------
class TestJsonStorageLoadWhenFileMissing:
    """JSONStorage.load() devuelve valores por defecto cuando el fichero no existe."""

    @pytest.fixture
    def empty_storage(self, tmp_path):
        return JSONStorage(tmp_path)

    def test_load_entities_returns_empty_list_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.ENTITIES)
        assert result == []
        assert isinstance(result, list)

    def test_load_applications_returns_empty_dict_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.APPLICATIONS)
        assert result == {}
        assert isinstance(result, dict)

    def test_load_conversational_returns_empty_list_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.CONVERSATIONAL)
        assert result == []

    def test_load_state_returns_empty_dict_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.STATE)
        assert result == {}

    def test_load_plans_returns_empty_list_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.PLANS)
        assert result == []

    def test_load_executions_returns_empty_list_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.EXECUTIONS)
        assert result == []

    def test_load_relationships_returns_empty_dict_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.RELATIONSHIPS)
        assert result == {}

    def test_load_preferences_returns_empty_dict_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.PREFERENCES)
        assert result == {}

    def test_load_learning_stats_returns_empty_dict_when_missing(self, empty_storage):
        result = empty_storage.load(MemoryType.LEARNING_STATS)
        assert result == {}

    def test_load_all_memory_types_without_exception(self, empty_storage):
        """Cargar todos los tipos de memoria: ningun tipo lanza excepcion
        cuando ningun fichero existe."""
        for mt in MemoryType:
            result = empty_storage.load(mt)
            assert result is not None

    def test_exists_returns_false_for_all_types_when_missing(self, empty_storage):
        for mt in MemoryType:
            assert empty_storage.exists(mt) is False

    def test_load_does_not_create_file(self, empty_storage, tmp_path):
        """La lectura (load) no crea el fichero entities.json."""
        _ = empty_storage.load(MemoryType.ENTITIES)
        assert not (tmp_path / "entities.json").exists()

    def test_load_returns_same_as_get_default_value(self, empty_storage):
        """El valor devuelto coincide con _get_default_value para cada tipo."""
        for mt in MemoryType:
            result = empty_storage.load(mt)
            default = empty_storage._get_default_value(mt)
            assert result == default


# ---------------------------------------------------------------------------
# 2. MemoryManager: comportamiento cuando entities.json no existe
# ---------------------------------------------------------------------------
class TestMemoryManagerWhenSourceMissing:
    """MemoryManager aislado en tmp_path (sin entities.json)."""

    @pytest.fixture
    def isolated_mm(self, tmp_path):
        return MemoryManager(tmp_path)

    def test_get_entities_by_type_returns_empty_list(self, isolated_mm):
        result = isolated_mm.get_entities_by_type("application")
        assert result == []
        assert isinstance(result, list)

    def test_get_entities_by_type_any_type_returns_empty(self, isolated_mm):
        result = isolated_mm.get_entities_by_type("any_type")
        assert result == []

    def test_get_entity_returns_none_when_missing(self, isolated_mm):
        result = isolated_mm.get_entity("nonexistent")
        assert result is None

    def test_find_entities_returns_empty_when_missing(self, isolated_mm):
        result = isolated_mm.find_entities(query="anything")
        assert result == []

    def test_warm_cache_handles_missing_files(self, isolated_mm):
        """_warm_cache (llamado en __init__) no lanza excepcion cuando
        los ficheros de datos no existen. La cache se inicializa con []"""
        assert isolated_mm.cache is not None
        assert "entities" in isolated_mm.cache

    def test_entities_file_not_created_on_read(self, isolated_mm, tmp_path):
        """La lectura de get_entities_by_type no crea entities.json."""
        assert not (tmp_path / "entities.json").exists()
        _ = isolated_mm.get_entities_by_type("application")
        assert not (tmp_path / "entities.json").exists()


# ---------------------------------------------------------------------------
# 3. ApplicationManager: init y _load_custom_applications sin fuente
# ---------------------------------------------------------------------------
class TestApplicationManagerWhenSourceMissing:
    """Verifica el comportamiento de ApplicationManager cuando la fuente
    (entities.json) no existe, usando un MemoryManager aislado en tmp_path.

    Se inyecta el MemoryManager aislado mediante patch de
    `get_memory_manager` en `src.hands.applications_core`, de modo que
    `ApplicationManager.__init__()` use el tmp_path en lugar del singleton.
    """

    @pytest.fixture
    def isolated_manager(self, tmp_path):
        """ApplicationManager inicializado con un MemoryManager aislado
        (tmp_path sin ficheros de datos)."""
        mm = MemoryManager(tmp_path)
        with patch(
            "src.hands.applications_core.get_memory_manager",
            return_value=mm,
        ):
            manager = ApplicationManager()
        return manager, mm, tmp_path

    def test_init_does_not_crash(self, isolated_manager):
        """ApplicationManager.__init__() no lanza excepcion cuando la fuente
        no existe (entities.json ausente)."""
        manager, _, _ = isolated_manager
        assert manager is not None

    def test_chrome_and_spotify_present_after_init(self, isolated_manager):
        """Las apps hardcodeadas (Chrome, Spotify) estan presentes aunque
        la fuente no exista."""
        manager, _, _ = isolated_manager
        assert "chrome" in manager.applications
        assert "spotify" in manager.applications

    def test_open_capability_apps_present(self, isolated_manager):
        """get_applications_by_capability(OPEN) devuelve Chrome y Spotify
        aun cuando la fuente no existe."""
        manager, _, _ = isolated_manager
        open_apps = manager.get_applications_by_capability(ApplicationCapability.OPEN)
        names = {a.name for a in open_apps}
        assert names == {"Chrome", "Spotify"}

    def test_only_hardcoded_apps_in_model(self, isolated_manager):
        """Sin fuente, solo Chrome y Spotify (hardcoded en _initialize_applications)
        estan en el modelo. _load_custom_applications (stub) no materializa
        entidades."""
        manager, _, _ = isolated_manager
        assert set(manager.applications.keys()) == {"chrome", "spotify"}

    def test_load_custom_applications_returns_none(self, isolated_manager):
        """_load_custom_applications() (aplicaciones_core.py:510) devuelve
        None y no lanza excepcion cuando las entidades no existen."""
        manager, _, _ = isolated_manager
        result = manager._load_custom_applications()
        assert result is None

    def test_repeated_load_custom_applications_no_effect(self, isolated_manager):
        """Llamar _load_custom_applications() explicitamente no anade apps
        al modelo y no lanza excepcion."""
        manager, _, _ = isolated_manager
        before = set(manager.applications.keys())
        manager._load_custom_applications()
        after = set(manager.applications.keys())
        assert before == after == {"chrome", "spotify"}

    def test_get_application_by_name_works(self, isolated_manager):
        """Las apps hardcodeadas son resolubles por nombre aun sin fuente."""
        manager, _, _ = isolated_manager
        chrome = manager.get_application("chrome")
        assert chrome is not None
        assert chrome.name == "Chrome"
        spotify = manager.get_application("spotify")
        assert spotify is not None
        assert spotify.name == "Spotify"

    def test_get_application_unknown_returns_none(self, isolated_manager):
        """Una app no registrada devuelve None."""
        manager, _, _ = isolated_manager
        assert manager.get_application("nonexistent_app") is None

    def test_source_file_created_after_init(self, isolated_manager):
        """Despues de __init__(), register_application persiste entities.json
        en el directorio de datos (crea el fichero). La fuente no existia
        antes del init pero se crea durante el init."""
        manager, mm, tmp_path = isolated_manager
        entities_path = tmp_path / "entities.json"
        assert entities_path.exists(), (
            "register_application crea entities.json durante init"
        )

    def test_source_file_content_after_init(self, isolated_manager):
        """Caracterizacion del contenido real del fichero tras init sin fuente.

        entities.json se crea con `[]` (vacia) debido a un hallazgo preexistente
        (D-ENTITIES-PERSIST-BUG): save_entity pasa dicts a _process_data_for_save
        que solo procesa instancias de Entity. Este test documenta el
        comportamiento actual, no asume que el bug debe corregirse aqui."""
        manager, mm, tmp_path = isolated_manager
        entities_path = tmp_path / "entities.json"
        content = json.loads(entities_path.read_text(encoding="utf-8"))
        assert content == []


# ---------------------------------------------------------------------------
# 4. DomainMemory: comportamiento cuando knowledge/applications.json no existe
# ---------------------------------------------------------------------------
class TestDomainMemoryWhenSourceMissing:
    """DomainMemory con get_project_root apuntando a tmp_path (sin ficheros
    de conocimiento). Verifica que knowledge/applications.json ausente deja
    self.applications como {}."""

    @pytest.fixture
    def isolated_domain_memory(self, tmp_path):
        """DomainMemory inicializado con get_project_root parcheado para
        apuntar a tmp_path (sin ficheros de datos de conocimiento)."""
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        return dm

    def test_applications_remains_empty_dict(self, isolated_domain_memory):
        """knowledge/applications.json ausente: self.applications = {}."""
        assert isolated_domain_memory.applications == {}

    def test_entities_remains_empty_dict(self, isolated_domain_memory):
        """knowledge/entities.json ausente: self.entities = {}."""
        assert isolated_domain_memory.entities == {}

    def test_capabilities_remains_empty_dict(self, isolated_domain_memory):
        """knowledge/capabilities.json ausente: self.capabilities = {}."""
        assert isolated_domain_memory.capabilities == {}
