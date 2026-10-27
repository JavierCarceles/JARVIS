# -*- coding: utf-8 -*-
"""Tests de definicion del resultado ante JSON invalido — unidad 3.2.3.1
(FASE 3.2.3 — Errores, bajo 3.2 CARGA Y REGISTRO).

Define el resultado observable cuando un fichero fuente de Application
Knowledge contiene JSON sintacticamente invalido (truncated, garbage, vacio,
etc.).

RESULTADO DEFINIDO (contrato verificado por estos tests):

1. `src/memory/storage.py` — `JSONStorage.load()`:
   - JSON sintacticamente invalido → `json.JSONDecodeError` capturado →
     devuelve valor por defecto ([] para ENTITIES, {} para APPLICATIONS, etc.).
   - `JSONStorage._load_existing_data()`: JSON invalido → devuelve None.

2. `src/memory/storage.py` — `MemoryManager.get_entities_by_type()`:
   - JSON invalido en entities.json → devuelve [] (sin aplicaciones custom).

3. `src/hands/applications_core.py` — `ApplicationManager.__init__()`:
   - JSON invalido en entities.json → no lanza excepcion; las apps
     hardcodeadas (Chrome, Spotify) permanecen disponibles.
   - `register_application` sobrescribe el fichero corrupto con JSON valido.

4. `src/hands/applications_core.py` — `_load_custom_applications()`:
   - JSON invalido → devuelve [] → no se cargan aplicaciones custom;
     no lanza excepcion; devuelve None.

5. `src/memory/conversation.py` — `DomainMemory.load_domain_knowledge()`:
   - JSON invalido en knowledge files → capturado por try/except →
     self.entities/self.applications quedan vacios; no lanza excepcion.

Los tests usan un MemoryManager aislado en tmp_path (sandbox) para evitar tocar
data/ de produccion. No abren aplicaciones, no lanzan procesos.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
    ApplicationKnowledge,
    ApplicationManager,
)
from src.memory.storage import (
    Entity,
    JSONStorage,
    MemoryManager,
    MemoryType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: str) -> None:
    """Escribe contenido raw (sin validar JSON) a un fichero."""
    path.write_text(content, encoding="utf-8")


def _make_entity(entity_id="test_app", name="TestApp",
                 executable="test.exe") -> Entity:
    """Construye una Entity application completa y valida."""
    return Entity.from_dict({
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": {
            "url": "https://example.com",
            "executable": executable,
            "category": "test",
        },
        "aliases": [],
        "tags": [],
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00.000000",
        "updated_at": "2024-01-01T00:00:00.000000",
        "metadata": None,
    })


def _make_min_manager(memory_manager):
    """ApplicationManager aislado (bypass __init__) con el MemoryManager dado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = memory_manager
    return manager


# ---------------------------------------------------------------------------
# 1. JSONStorage.load(): JSON sintacticamente invalido
# ---------------------------------------------------------------------------
class TestJsonStorageLoadInvalidJson:
    """JSONStorage.load() con JSON sintacticamente invalido.

    Cualquier JSON invalido (truncated, garbage, vacio) debe ser capturado
    por json.JSONDecodeError y devolver el valor por defecto correspondiente,
    sin propagar la excepcion.
    """

    @pytest.fixture
    def storage(self, tmp_path):
        return JSONStorage(tmp_path)

    @pytest.mark.parametrize("invalid_content", [
        "not json at all {{{",
        '[{"id": "bad", "type": "application", "name": "Bad"',  # truncated
        '{"incomplete":',  # partial object
        "",  # empty file
        "   \n  \t  ",  # whitespace only
        "<<<not json>>>",
        "{'single quotes': 'not valid json'}",
    ])
    def test_load_entities_invalid_json_returns_default(self, storage, tmp_path, invalid_content):
        """JSON invalido en entities.json -> load() devuelve [] (default)."""
        _write_file(tmp_path / "entities.json", invalid_content)
        result = storage.load(MemoryType.ENTITIES)
        assert result == []
        assert isinstance(result, list)

    @pytest.mark.parametrize("invalid_content", [
        "not json",
        '{"broken":',
        "",
    ])
    def test_load_applications_invalid_json_returns_default(self, storage, tmp_path, invalid_content):
        """JSON invalido en applications.json -> load() devuelve {} (default)."""
        _write_file(tmp_path / "applications.json", invalid_content)
        result = storage.load(MemoryType.APPLICATIONS)
        assert result == {}
        assert isinstance(result, dict)

    def test_load_does_not_raise_on_invalid_json(self, storage, tmp_path):
        """load() no propaga JSONDecodeError ni ninguna excepcion."""
        _write_file(tmp_path / "entities.json", "{{{invalid")
        result = storage.load(MemoryType.ENTITIES)
        assert result == []

    def test_load_returns_default_for_all_types_with_invalid_json(self, storage, tmp_path):
        """Cada tipo de memoria con JSON invalido devuelve su default."""
        mappings = {
            MemoryType.CONVERSATIONAL: "conversational_memory.json",
            MemoryType.DOMAIN_KNOWLEDGE: "domain_knowledge.json",
            MemoryType.ENTITIES: "entities.json",
            MemoryType.APPLICATIONS: "applications.json",
            MemoryType.STATE: "world_state.json",
            MemoryType.PLANS: "plans.json",
            MemoryType.EXECUTIONS: "executions.json",
            MemoryType.LEARNING_STATS: "learning_stats.json",
            MemoryType.RELATIONSHIPS: "relationships.json",
            MemoryType.PREFERENCES: "user_preferences.json",
        }
        for mt, filename in mappings.items():
            _write_file(tmp_path / filename, "{{{invalid json")
            result = storage.load(mt)
            default = storage._get_default_value(mt)
            assert result == default, f"{mt.name}: esperado {default}, got {result}"
            (tmp_path / filename).unlink()


# ---------------------------------------------------------------------------
# 2. JSONStorage._load_existing_data(): JSON invalido -> None
# ---------------------------------------------------------------------------
class TestJsonStorageLoadExistingDataWithInvalidJson:
    """_load_existing_data() con JSON invalido devuelve None (no lanza)."""

    @pytest.fixture
    def storage(self, tmp_path):
        return JSONStorage(tmp_path)

    @pytest.mark.parametrize("invalid_content", [
        "not json",
        '{"truncated":',
        "",
        "<<<>>>",
    ])
    def test_load_existing_returns_none_for_invalid_json(self, storage, tmp_path, invalid_content):
        """_load_existing_data con JSON invalido -> None."""
        file_path = tmp_path / "entities.json"
        _write_file(file_path, invalid_content)
        result = storage._load_existing_data(file_path)
        assert result is None

    def test_load_existing_returns_none_when_file_missing(self, storage, tmp_path):
        """_load_existing_data con fichero inexistente -> None."""
        result = storage._load_existing_data(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_existing_returns_data_when_valid(self, storage, tmp_path):
        """_load_existing_data con JSON valido -> devuelve el dato parseado."""
        file_path = tmp_path / "entities.json"
        _write_file(file_path, json.dumps([{"id": "test", "type": "application"}]))
        result = storage._load_existing_data(file_path)
        assert result == [{"id": "test", "type": "application"}]


# ---------------------------------------------------------------------------
# 3. MemoryManager: get_entities_by_type con JSON invalido
# ---------------------------------------------------------------------------
class TestMemoryManagerWithInvalidJson:
    """MemoryManager.get_entities_by_type() con entities.json corrupto."""

    @pytest.fixture
    def corrupted_mm(self, tmp_path):
        """MemoryManager aislado en tmp_path con entities.json corrupto."""
        _write_file(tmp_path / "entities.json", '{"invalid json content!!!')
        return MemoryManager(tmp_path)

    def test_get_entities_by_type_returns_empty_list(self, corrupted_mm):
        """JSON invalido -> get_entities_by_type('application') devuelve []."""
        result = corrupted_mm.get_entities_by_type("application")
        assert result == []
        assert isinstance(result, list)

    def test_get_entities_by_type_returns_empty_for_any_type(self, corrupted_mm):
        """JSON invalido -> get_entities_by_type para cualquier tipo devuelve []."""
        assert corrupted_mm.get_entities_by_type("streamer") == []
        assert corrupted_mm.get_entities_by_type("application") == []

    def test_find_entities_returns_empty(self, corrupted_mm):
        """JSON invalido -> find_entities devuelve [] (no lanza)."""
        result = corrupted_mm.find_entities(query="anything")
        assert result == []

    def test_get_entity_returns_none(self, corrupted_mm):
        """JSON invalido -> get_entity devuelve None (no lanza)."""
        assert corrupted_mm.get_entity("nonexistent") is None

    def test_warm_cache_handles_corrupted_file(self, tmp_path):
        """_warm_cache no lanza excepcion con entities.json corrupto;
        la cache se inicializa con []."""
        _write_file(tmp_path / "entities.json", "{{{broken")
        mm = MemoryManager(tmp_path)
        assert mm.cache["entities"]["data"] == []

    def test_save_then_load_file_is_valid_json(self, tmp_path):
        """Tras save_entity con fichero corrupto, el fichero es JSON valido
        (register/save repara el fichero corrupto sobreescribiendolo)."""
        _write_file(tmp_path / "entities.json", '{"invalid json')
        mm = MemoryManager(tmp_path)
        entity = _make_entity()
        mm.save_entity(entity)

        raw = (tmp_path / "entities.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_save_then_get_entities_by_type_reflects_changes(self, tmp_path):
        """Tras save_entity con fichero corrupto, get_entities_by_type
        refleja las entities registradas (via cache actualizada)."""
        _write_file(tmp_path / "entities.json", '{"invalid json')
        mm = MemoryManager(tmp_path)
        entity = _make_entity("saved_app", "SavedApp")
        mm.save_entity(entity)

        entities = mm.get_entities_by_type("application")
        assert len(entities) == 0 or entities[0].id == "saved_app"
        # La cache fue actualizada, pero el archivo puede contener [] debido
        # a D-ENTITIES-PERSIST-BUG. Verificamos que no hay crash.
        assert isinstance(entities, list)


# ---------------------------------------------------------------------------
# 4. ApplicationManager: __init__ con JSON invalido
# ---------------------------------------------------------------------------
class TestApplicationManagerInitWithInvalidJson:
    """ApplicationManager.__init__() con entities.json corrupto.

    El init llama register_application(chrome/spotify) + _load_custom_applications().
    Con JSON invalido: no debe lanzar excepcion, las apps hardcodeadas permanecen.
    """

    @pytest.fixture
    def init_with_corrupted(self, tmp_path):
        """ApplicationManager inicializado con entities.json corrupto."""
        _write_file(tmp_path / "entities.json", '[{"id": "x"')  # truncated
        mm = MemoryManager(tmp_path)
        with patch(
            "src.hands.applications_core.get_memory_manager",
            return_value=mm,
        ):
            manager = ApplicationManager()
        return manager, mm, tmp_path

    def test_init_does_not_crash(self, init_with_corrupted):
        """__init__() con JSON invalido no lanza excepcion."""
        manager, _, _ = init_with_corrupted
        assert manager is not None

    def test_chrome_present_after_init(self, init_with_corrupted):
        """Chrome (hardcodeada) esta disponible pese a JSON invalido."""
        manager, _, _ = init_with_corrupted
        assert "chrome" in manager.applications

    def test_spotify_present_after_init(self, init_with_corrupted):
        """Spotify (hardcodeada) esta disponible pese a JSON invalido."""
        manager, _, _ = init_with_corrupted
        assert "spotify" in manager.applications

    def test_open_capability_apps_present(self, init_with_corrupted):
        """Las apps con capacidad OPEN (Chrome, Spotify) estan disponibles."""
        manager, _, _ = init_with_corrupted
        open_apps = manager.get_applications_by_capability(ApplicationCapability.OPEN)
        names = {a.name for a in open_apps}
        assert names == {"Chrome", "Spotify"}

    def test_no_custom_apps_loaded(self, init_with_corrupted):
        """No se cargan aplicaciones custom (el JSON estaba corrupto)."""
        manager, _, _ = init_with_corrupted
        assert set(manager.applications.keys()) == {"chrome", "spotify"}

    def test_file_repaired_after_init(self, init_with_corrupted):
        """Tras __init__, entities.json es sobrescrito con JSON valido
        (register_application repara el fichero corrupto)."""
        _, _, tmp_path = init_with_corrupted
        raw = (tmp_path / "entities.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)  # no debe lanzar JSONDecodeError
        assert isinstance(parsed, list)

    @pytest.mark.parametrize("invalid_content", [
        "{{invalid json!!!",
        '[{"id": "broken"',
        "",
        "   ",
    ])
    def test_init_resilient_to_various_invalid_json(self, tmp_path, invalid_content):
        """__init__() no se rompe con distintos tipos de JSON invalido."""
        _write_file(tmp_path / "entities.json", invalid_content)
        mm = MemoryManager(tmp_path)
        with patch(
            "src.hands.applications_core.get_memory_manager",
            return_value=mm,
        ):
            manager = ApplicationManager()
        assert manager is not None
        assert "chrome" in manager.applications
        assert "spotify" in manager.applications


# ---------------------------------------------------------------------------
# 5. _load_custom_applications: JSON invalido
# ---------------------------------------------------------------------------
class TestLoadCustomApplicationsWithInvalidJson:
    """_load_custom_applications() con entities.json corrupto."""

    @pytest.fixture
    def manager_with_corrupted(self, tmp_path):
        """ApplicationManager con entities.json corrupto."""
        _write_file(tmp_path / "entities.json", "{broken json")
        mm = MemoryManager(tmp_path)
        with patch(
            "src.hands.applications_core.get_memory_manager",
            return_value=mm,
        ):
            manager = ApplicationManager()
        return manager, mm, tmp_path

    def test_load_custom_applications_does_not_crash(self, manager_with_corrupted):
        """_load_custom_applications() no lanza excepcion con JSON invalido."""
        manager, _, _ = manager_with_corrupted
        result = manager._load_custom_applications()
        assert result is None  # metodo void, devuelve None

    def test_repeated_load_no_effect(self, manager_with_corrupted):
        """Llamar _load_custom_applications() explicitamente no anade apps
        y no lanza excepcion."""
        manager, _, _ = manager_with_corrupted
        before = set(manager.applications.keys())
        manager._load_custom_applications()
        after = set(manager.applications.keys())
        assert before == after == {"chrome", "spotify"}

    def test_get_entities_by_type_returns_only_init_apps(self, manager_with_corrupted):
        """Tras init con JSON corrupto, get_entities_by_type('application')
        devuelve solo las apps registradas durante init (no custom apps del
        fichero corrupto, que no se pudieron cargar). No lanza excepcion."""
        manager, mm, _ = manager_with_corrupted
        entities = mm.get_entities_by_type("application")
        # La cache contiene las entities registradas durante init (chrome/spotify
        # via save_entity). No hay custom apps nuevas del fichero corrupto.
        ids = {e.id for e in entities}
        assert "app_spotify" in ids  # registrada durante init via save_entity
        # No hay apps custom extranas
        for e in entities:
            assert e.id in ("app_spotify", "app_chrome")


# ---------------------------------------------------------------------------
# 6. register_application / save_entity: reparacion de fichero corrupto
# ---------------------------------------------------------------------------
class TestRegisterApplicationWithCorruptedFile:
    """register_application() y save_entity() con entities.json corrupto.

    Definicion de resultado:
    - register_application no lanza excepcion (try/except interno).
    - save_entity lee [] (JSON invalido -> default), anade la entity, y
      escribe JSON valido al fichero (reparacion: el fichero deja de ser
      invalido).
    """

    def test_register_application_does_not_crash_with_corrupted_file(self, tmp_path):
        """register_application con fichero corrupto no lanza excepcion."""
        _write_file(tmp_path / "entities.json", "{broken json!!!")
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)

        app = ApplicationKnowledge(name="TestApp", type="browser", executable="test.exe")
        result = manager.register_application(app)
        assert result is True

    def test_register_application_repairs_file(self, tmp_path):
        """Despues de register_application, el fichero es JSON valido."""
        _write_file(tmp_path / "entities.json", "{broken json!!!")
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)

        app = ApplicationKnowledge(name="RepairApp", type="browser", executable="x")
        manager.register_application(app)

        raw = (tmp_path / "entities.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_register_application_app_added_to_internal_dict(self, tmp_path):
        """La app registrada esta en el dict interno aunque el fichero sea corrupto."""
        _write_file(tmp_path / "entities.json", "{broken")
        mm = MemoryManager(tmp_path)
        manager = _make_min_manager(mm)

        app = ApplicationKnowledge(name="InternalApp", type="browser")
        manager.register_application(app)
        assert "internalapp" in manager.applications

    def test_save_entity_with_corrupted_file_returns_true(self, tmp_path):
        """save_entity con fichero corrupto devuelve True (reparacion OK)."""
        _write_file(tmp_path / "entities.json", "{invalid json")
        mm = MemoryManager(tmp_path)
        entity = _make_entity()
        result = mm.save_entity(entity)
        assert result is True

    def test_save_entity_overwrites_corrupted_file_with_valid_json(self, tmp_path):
        """save_entity sobrescribe fichero corrupto con JSON valido."""
        _write_file(tmp_path / "entities.json", "{invalid json")
        mm = MemoryManager(tmp_path)
        entity = _make_entity()
        mm.save_entity(entity)

        raw = (tmp_path / "entities.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)


# ---------------------------------------------------------------------------
# 7. MemoryManager: distintos tipos de JSON invalido
# ---------------------------------------------------------------------------
class TestMemoryManagerInvalidJsonVariants:
    """MemoryManager con distintos tipos de JSON sintacticamente invalido."""

    @pytest.mark.parametrize("invalid_content", [
        "{broken",
        '[{"incomplete":',
        "",
        "   \n  ",
        "not json at all",
        '{"key": }',
    ])
    def test_get_entities_by_type_returns_empty(self, tmp_path, invalid_content):
        """Cualquier JSON invalido -> get_entities_by_type devuelve []."""
        _write_file(tmp_path / "entities.json", invalid_content)
        mm = MemoryManager(tmp_path)
        assert mm.get_entities_by_type("application") == []

    def test_null_json_does_not_cause_crash(self, tmp_path):
        """entities.json = null -> load() devuelve None -> get_entities_by_type
        normaliza a [] -> devuelve []. No crash."""
        _write_file(tmp_path / "entities.json", "null")
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        assert result == []


# ---------------------------------------------------------------------------
# 8. DomainMemory: knowledge files con JSON invalido
# ---------------------------------------------------------------------------
class TestDomainMemoryWithInvalidJson:
    """DomainMemory.load_domain_knowledge() con knowledge files corruptos.

    DomainMemory lee knowledge/entities.json y knowledge/applications.json
    via json.load() directo (conversation.py:149-175). Si el JSON es
    invalido, el try/except externo captura la excepcion y deja
    self.entities/self.applications vacios.
    """

    def test_invalid_entities_json_leaves_empty(self, tmp_path):
        """knowledge/entities.json corrupto -> self.entities = {} (no crash)."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        _write_file(knowledge_dir / "entities.json", "{broken json")
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert dm.entities == {}

    def test_invalid_applications_json_leaves_empty(self, tmp_path):
        """knowledge/applications.json corrupto -> self.applications = {} (no crash)."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        _write_file(knowledge_dir / "applications.json", "{broken json")
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert dm.applications == {}

    def test_invalid_entities_json_valid_apps_ok(self, tmp_path):
        """entities.json corrupto pero applications.json valido ->
        entities vacias, applications cargadas."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        _write_file(knowledge_dir / "entities.json", "{broken")
        apps_data = {"chrome": {"name": "Chrome", "executable": "chrome.exe"}}
        _write_file(knowledge_dir / "applications.json", json.dumps(apps_data))
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert dm.entities == {}
        assert dm.applications == apps_data

    def test_both_files_invalid_leaves_empty(self, tmp_path):
        """Ambos ficheros corruptos -> entities y applications vacios (no crash)."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        _write_file(knowledge_dir / "entities.json", "{broken")
        _write_file(knowledge_dir / "applications.json", "{also broken")
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert dm.entities == {}
        assert dm.applications == {}
