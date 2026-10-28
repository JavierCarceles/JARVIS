# -*- coding: utf-8 -*-
"""Tests de verificacion del comportamiento ante DATOS INCOMPLETOS
— unidad 3.2.1.4 (FASE 3.2.1 — Fuente de datos).

Verifica el comportamiento REAL (no el esperado) del modelo Application
Knowledge (ApplicationManager) y de las fuentes de datos cuando los
ficheros fuente EXISTEN pero contienen datos parciales, malformados o
mal tipificados.

NOTA 3.2.3.2: Las secciones 3, 4 y 5 se actualizaron para reflejar el cambio
de contrato introducido por la unidad 3.2.3.2 ("Definir resultado ante
aplicacion invalida"): `get_entities_by_type`, `get_entity` y `find_entities`
ahora manejan errores per-item (un entidad invalida se omite individualmente
en lugar de perder todas las entidades del tipo o propagar TypeError). La
sección 6 también se actualizo porque `_load_custom_applications` no es un
stub: procesa entities reales y, con el manejo per-item, omite las apps
invalidas manteniendo las validas.

Resumen de comportamientos verificados:

1. `src/memory/storage.py` — `JSONStorage.load()`:
   - JSON sintacticamente invalido (truncated) → `json.JSONDecodeError`
     capturado → devuelve valor por defecto (`[]` para ENTITIES, `{}` para
     APPLICATIONS).
   - JSON valido pero tipo top-level inesperado (dict en vez de list para
     entities; list en vez de dict para applications) → devuelve el dato
     parseado tal cual, sin validacion de tipo.
   - JSON `null` → `load()` devuelve `None`; `_warm_cache` lo normaliza a `[]`.

2. `src/memory/storage.py` — `Entity.from_dict()`:
   - Campos obligatorios (`id`, `type`, `name`, `properties`) ausentes →
     `TypeError` (el dataclass no provee defaults para ellos).
   - Campos opcionales ausentes (`created_at`, `updated_at`, `aliases`,
     `confidence`, `tags`, `metadata`) → rellenados con defaults.
   - `properties: null` (JSON null → Python None) → no lanza error;
     `entity.properties` queda `None`.
   - `properties` con tipo incorrecto (lista en vez de dict) → no lanza
     error; se almacena sin validacion.

3. `src/memory/storage.py` — `get_entities_by_type()` (actualizado por 3.2.3.2):
   - Cada entity se reconstruye con `Entity.from_dict()` dentro de un
     try/except per-item: una entity invalida (campos obligatorios ausentes)
     se omite individualmente (registro de error) y NO provoca la perdida
     de las demas entities validas del mismo tipo.
   - Items no dict en la lista (string, None, int) → omitidos por el filtro
     `isinstance(entity_data, dict)`.
   - Entity con `properties=None` → cargada sin error, `properties` queda None.

4. `src/memory/storage.py` — `get_entity()` (actualizado por 3.2.3.2):
   - `Entity.from_dict()` para la entity encontrada esta envuelto en
     try/except per-item: si la entity es invalida, se registra el error y
     se devuelve `None` (no se propaga `TypeError`).
   - Si otra entity (no la buscada) es incompleta, `get_entity` no se
     rompe (solo parsea la entity que coincide por ID).

5. `src/memory/storage.py` — `find_entities()` (actualizado por 3.2.3.2):
   - Cada entity se reconstruye con `Entity.from_dict()` dentro de un
     try/except per-item: una entity invalida se omite (registro de error)
     y no propaga `TypeError`; las entities validas que coinciden con la
     query se devuelven normalmente.

6. `src/hands/applications_core.py` — `ApplicationManager.__init__()`:
   - No se rompe con datos incompletos en entities.json; las apps
     hardcodeadas (Chrome, Spotify) permanecen disponibles.
   - `_load_custom_applications()` procesa entities reales invocando
     `get_entities_by_type("application")` y `_reconstruct_application()`
     por entity. Con el cambio de 3.2.3.2, una entity application invalida
     se omite individualmente: las apps validas se cargan y la invalida se
     registra y descarta. `_reconstruct_application` devuelve `None` para
     apps sin nombre usable, omitidas por el bucle.

7. `src/memory/conversation.py` — `DomainMemory.load_domain_knowledge()`:
   - `knowledge/applications.json`: entries incompletos se almacenan tal
     cual (dict raw sin validacion de schema).
   - `knowledge/entities.json`: si una entity carece de campos obligatorios,
     `Entity.from_dict()` lanza `TypeError` durante el bucle de iteracion.
     Las entities validas cargadas ANTES de la entidad incompleta se conservan
     en `self.entities`; la entidad incompleta y las siguientes se pierden.
     La excepcion se captura (try/except externo) y se registra el error
     sin propagar.
"""

import dataclasses
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from src.hands.applications_core import (
    ApplicationCapability,
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
def _write_entities_json(storage_path: Path, entities_list) -> None:
    """Escribe entities.json con el contenido dado en el directorio de datos."""
    (storage_path / "entities.json").write_text(
        json.dumps(entities_list), encoding="utf-8"
    )


def _make_valid_entity(entity_id="valid_app", name="ValidApp"):
    """Construye un dict de entidad completo y valido."""
    return {
        "id": entity_id,
        "type": "application",
        "name": name,
        "properties": {
            "url": "https://example.com",
            "executable": "valid.exe",
            "category": "test",
        },
        "aliases": ["alias1"],
        "tags": ["tag1"],
        "confidence": 1.0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "metadata": None,
    }


# ---------------------------------------------------------------------------
# 1. JSONStorage.load(): JSON sintacticamente invalido
# ---------------------------------------------------------------------------
class TestJsonStorageLoadCorruptedJson:
    """JSONStorage.load() con JSON sintacticamente invalido (truncated)."""

    @pytest.fixture
    def storage(self, tmp_path):
        return JSONStorage(tmp_path)

    def test_load_truncated_json_returns_default(self, storage, tmp_path):
        """JSON truncado → JSONDecodeError capturado → devuelve [] (default)."""
        (tmp_path / "entities.json").write_text(
            '[{"id": "bad", "type": "application", "name": "Bad", "properties": {}', encoding="utf-8"
        )
        result = storage.load(MemoryType.ENTITIES)
        assert result == []

    def test_load_truncated_json_applications_default(self, storage, tmp_path):
        """JSON truncado para applications.json → devuelve {} (default)."""
        (tmp_path / "applications.json").write_text(
            '{"chrome": {"name": "Chrome",', encoding="utf-8"
        )
        result = storage.load(MemoryType.APPLICATIONS)
        assert result == {}

    def test_load_garbage_returns_default(self, storage, tmp_path):
        """Contenido no-JSON (garbage) → JSONDecodeError → default."""
        (tmp_path / "entities.json").write_text("not json at all {{{", encoding="utf-8")
        result = storage.load(MemoryType.ENTITIES)
        assert result == []

    def test_load_partial_json_object_returns_default(self, storage, tmp_path):
        """Un objeto JSON incompleto → JSONDecodeError → default."""
        (tmp_path / "entities.json").write_text('{"incomplete":', encoding="utf-8")
        result = storage.load(MemoryType.ENTITIES)
        assert result == []


# ---------------------------------------------------------------------------
# 2. JSONStorage.load(): JSON valido pero tipo top-level inesperado
# ---------------------------------------------------------------------------
class TestJsonStorageLoadWrongTopLevelType:
    """JSONStorage.load() con JSON valido pero tipo top-level inesperado.

    load() no valida el tipo del dato parseado: solo captura JSONDecodeError
    y Exception general. Si el JSON es valido pero tiene estructura incorrecta
    (p.ej. dict en vez de list para entities), load() devuelve el dato tal cual.
    """

    @pytest.fixture
    def storage(self, tmp_path):
        return JSONStorage(tmp_path)

    def test_load_entities_as_dict_returns_dict(self, storage, tmp_path):
        """entities.json con un dict (no una lista) → load() devuelve el dict."""
        (tmp_path / "entities.json").write_text(
            json.dumps({"unexpected": "top_level_dict"}), encoding="utf-8"
        )
        result = storage.load(MemoryType.ENTITIES)
        assert result == {"unexpected": "top_level_dict"}
        assert isinstance(result, dict)

    def test_load_entities_as_string_returns_string(self, storage, tmp_path):
        """entities.json con un string → load() lo devuelve tal cual."""
        (tmp_path / "entities.json").write_text(json.dumps("a string"), encoding="utf-8")
        result = storage.load(MemoryType.ENTITIES)
        assert result == "a string"

    def test_load_entities_null_returns_none(self, storage, tmp_path):
        """entities.json con `null` → load() devuelve None (no JSONDecodeError)."""
        (tmp_path / "entities.json").write_text("null", encoding="utf-8")
        result = storage.load(MemoryType.ENTITIES)
        assert result is None

    def test_load_applications_as_list_returns_list(self, storage, tmp_path):
        """applications.json con una lista (no un dict) → load() devuelve la lista."""
        (tmp_path / "applications.json").write_text(
            json.dumps(["chrome", "spotify"]), encoding="utf-8"
        )
        result = storage.load(MemoryType.APPLICATIONS)
        assert result == ["chrome", "spotify"]

    def test_warm_cache_normalizes_null_entities_to_list(self, tmp_path):
        """_warm_cache: si load() devuelve None para entities, la cache se
        inicializa con [] (entones `entities_data if entities_data is not None
        else []`)."""
        (tmp_path / "entities.json").write_text("null", encoding="utf-8")
        mm = MemoryManager(tmp_path)
        assert mm.cache["entities"]["data"] == []


# ---------------------------------------------------------------------------
# 3. Entity.from_dict(): campos obligatorios ausentes
# ---------------------------------------------------------------------------
class TestEntityFromDictMissingRequiredFields:
    """Entity.from_dict() con campos obligatorios ausentes.

    El dataclass Entity declara id, type, name y properties como campos
    requeridos (sin default). from_dict() solo rellena defaults para
    created_at, updated_at, aliases, confidence, tags y metadata. Si falta
    cualquiera de los 4 campos requeridos, cls(**data) lanza TypeError.
    """

    def test_missing_id_raises_type_error(self):
        data = _make_valid_entity()
        del data["id"]
        with pytest.raises(TypeError, match="id"):
            Entity.from_dict(data)

    def test_missing_type_raises_type_error(self):
        data = _make_valid_entity()
        del data["type"]
        with pytest.raises(TypeError, match="type"):
            Entity.from_dict(data)

    def test_missing_name_raises_type_error(self):
        data = _make_valid_entity()
        del data["name"]
        with pytest.raises(TypeError, match="name"):
            Entity.from_dict(data)

    def test_missing_properties_raises_type_error(self):
        data = _make_valid_entity()
        del data["properties"]
        with pytest.raises(TypeError, match="properties"):
            Entity.from_dict(data)

    def test_missing_all_required_raises_type_error(self):
        data = {"aliases": [], "tags": [], "confidence": 1.0}
        with pytest.raises(TypeError):
            Entity.from_dict(data)


# ---------------------------------------------------------------------------
# 4. Entity.from_dict(): campos opcionales ausentes → defaults
# ---------------------------------------------------------------------------
class TestEntityFromDictMissingOptionalFields:
    """Entity.from_dict() rellena defaults para campos opcionales ausentes."""

    def test_missing_created_at_filled(self):
        data = _make_valid_entity()
        del data["created_at"]
        e = Entity.from_dict(data)
        assert e.created_at is not None
        assert isinstance(e.created_at, str)

    def test_missing_updated_at_filled(self):
        data = _make_valid_entity()
        del data["updated_at"]
        e = Entity.from_dict(data)
        assert e.updated_at is not None

    def test_missing_aliases_filled_with_empty_list(self):
        data = _make_valid_entity()
        del data["aliases"]
        e = Entity.from_dict(data)
        assert e.aliases == []

    def test_missing_confidence_filled_with_one(self):
        data = _make_valid_entity()
        del data["confidence"]
        e = Entity.from_dict(data)
        assert e.confidence == 1.0

    def test_missing_tags_filled_with_empty_list(self):
        data = _make_valid_entity()
        del data["tags"]
        e = Entity.from_dict(data)
        assert e.tags == []

    def test_missing_metadata_filled_with_none(self):
        data = _make_valid_entity()
        del data["metadata"]
        e = Entity.from_dict(data)
        assert e.metadata is None

    def test_missing_all_optionals_still_constructs(self):
        """Una entity con solo los 4 campos obligatorios se construye OK."""
        data = {
            "id": "minimal",
            "type": "application",
            "name": "Minimal",
            "properties": {},
        }
        e = Entity.from_dict(data)
        assert e.id == "minimal"
        assert e.name == "Minimal"
        assert e.aliases == []
        assert e.tags == []
        assert e.confidence == 1.0
        assert e.metadata is None


# ---------------------------------------------------------------------------
# 5. Entity.from_dict(): properties = null o tipo incorrecto
# ---------------------------------------------------------------------------
class TestEntityFromDictWithNullAndWrongTypeProperties:
    """Entity.from_dict() no valida el tipo de `properties`.

    - `properties: null` (JSON null → Python None) → entity.properties = None.
    - `properties` como lista en vez de dict → entity.properties = lista.
    Ambas se construyen sin error porque el dataclass no valida tipos.
    """

    def test_properties_null_does_not_raise(self):
        data = {
            "id": "null_props",
            "type": "application",
            "name": "NullProps",
            "properties": None,
            "aliases": [],
            "tags": [],
            "confidence": 1.0,
            "created_at": "2024-01-01",
            "updated_at": "2024-01-01",
            "metadata": None,
        }
        e = Entity.from_dict(data)
        assert e.properties is None

    def test_properties_as_list_does_not_raise(self):
        data = {
            "id": "list_props",
            "type": "application",
            "name": "ListProps",
            "properties": ["not", "a", "dict"],
        }
        e = Entity.from_dict(data)
        assert e.properties == ["not", "a", "dict"]
        assert isinstance(e.properties, list)


# ---------------------------------------------------------------------------
# 6. get_entities_by_type(): entity incompleta omitida per-item (3.2.3.2)
# ---------------------------------------------------------------------------
class TestGetEntitiesByTypeWithIncompleteData:
    """get_entities_by_type() con datos incompletos (actualizado por 3.2.3.2).

    Con el manejo per-item introducido en 3.2.3.2, si una entity con `type`
    que coincide carece de un campo obligatorio, `Entity.from_dict()` lanza
    `TypeError` capturado per-item: la entity invalida se omite (registro de
    error) y NO se pierden las entities validas del mismo tipo.
    """

    @pytest.fixture
    def isolated_mm(self, tmp_path):
        _write_entities_json(tmp_path, [_make_valid_entity("valid_app", "ValidApp")])
        return MemoryManager(tmp_path)

    def test_valid_entity_loaded_when_no_incomplete(self, isolated_mm):
        """Sin datos incompletos, la entity valida se carga correctamente."""
        entities = isolated_mm.get_entities_by_type("application")
        assert len(entities) == 1
        assert entities[0].id == "valid_app"

    def test_incomplete_entity_missing_name_skipped_valid_loaded(self, tmp_path):
        """Una entity application que falta `name` se omite per-item (TypeError
        capturado); la entity valida 'ok' se carga correctamente. No se pierden
        las applications validas. (Contrato definido por 3.2.3.2.)"""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {"url": "http://bad.com", "executable": "bad.exe", "category": "test"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        # Sin el campo 'name'
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        # La entity invalida se omite; la valida 'ok' se carga
        assert len(result) == 1
        assert result[0].id == "ok"

    def test_incomplete_entity_missing_properties_skipped_valid_loaded(self, tmp_path):
        """Una entity application que falta `properties` se omite per-item;
        la entity valida 'ok' se carga. No se pierden las applications validas.
        (Contrato definido por 3.2.3.2.)"""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "name": "BadApp",
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        assert len(result) == 1
        assert result[0].id == "ok"

    def test_incomplete_entity_missing_id_skipped_valid_loaded(self, tmp_path):
        """Una entity application que falta `id` se omite per-item;
        la entity valida 'ok' se carga. No se pierden las applications validas.
        (Contrato definido por 3.2.3.2.)"""
        incomplete = {
            "type": "application",
            "name": "BadNoId",
            "properties": {"url": "http://bad.com", "executable": "bad.exe", "category": "test"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        assert len(result) == 1
        assert result[0].id == "ok"

    def test_non_dict_items_skipped_valid_entity_loaded(self, tmp_path):
        """Items no-dict en la lista (string, None, int) son omitidos por el
        filtro isinstance(entity_data, dict); la entity valida se carga."""
        _write_entities_json(tmp_path, [
            "not_a_dict",
            None,
            42,
            _make_valid_entity("ok", "Good"),
        ])
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        assert len(result) == 1
        assert result[0].id == "ok"

    def test_entity_with_properties_none_loaded(self, tmp_path):
        """Una entity con properties=null (JSON null → None) se carga sin error;
        properties queda None."""
        data = _make_valid_entity("null_props_app", "NullPropsApp")
        data["properties"] = None
        _write_entities_json(tmp_path, [data])
        mm = MemoryManager(tmp_path)
        result = mm.get_entities_by_type("application")
        assert len(result) == 1
        assert result[0].properties is None

    def test_incomplete_non_matching_type_does_not_affect(self, tmp_path):
        """Una entity de tipo distinto (streamer) que es incompleta no afecta
        a la carga de entities application validas, porque solo se filtra por
        type antes de llamar from_dict."""
        incomplete_streamer = {
            "id": "bad_streamer",
            "type": "streamer",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [
            _make_valid_entity("ok", "Good"),
            incomplete_streamer,
        ])
        mm = MemoryManager(tmp_path)
        apps = mm.get_entities_by_type("application")
        assert len(apps) == 1
        assert apps[0].id == "ok"


# ---------------------------------------------------------------------------
# 7. get_entity(): entity incompleta devuelve None (manejo per-item, 3.2.3.2)
# ---------------------------------------------------------------------------
class TestGetEntityWithIncompleteData:
    """get_entity() con datos incompletos (actualizado por 3.2.3.2).

    Con el manejo per-item introducido en 3.2.3.2, si la entity con el ID
    buscado carece de campos obligatorios, `Entity.from_dict()` captura el
    `TypeError` y devuelve `None` (no lo propaga al llamador).
    """

    def test_get_entity_incomplete_returns_none(self, tmp_path):
        """get_entity('bad_app') con una entity incompleta (falta name)
        → devuelve None (TypeError capturado per-item, no propagado).
        (Contrato definido por 3.2.3.2.)"""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {"executable": "bad.exe"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [
            _make_valid_entity("ok", "Good"),
            incomplete,
        ])
        mm = MemoryManager(tmp_path)
        result = mm.get_entity("bad_app")
        assert result is None

    def test_get_entity_valid_returns_entity(self, tmp_path):
        """get_entity() sobre una entity completa funciona normalmente."""
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good")])
        mm = MemoryManager(tmp_path)
        entity = mm.get_entity("ok")
        assert entity is not None
        assert entity.id == "ok"
        assert entity.name == "Good"

    def test_get_entity_incomplete_other_does_not_crash(self, tmp_path):
        """Si una entity distinta a la buscada es incompleta, get_entity no
        se rompe (solo parsea la entity que coincide por ID)."""
        incomplete = {
            "id": "bad_other",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [
            _make_valid_entity("target", "Target"),
            incomplete,
        ])
        mm = MemoryManager(tmp_path)
        entity = mm.get_entity("target")
        assert entity is not None
        assert entity.name == "Target"

    def test_get_entity_nonexistent_returns_none(self, tmp_path):
        """get_entity sobre un ID inexistente devuelve None (no lanza)."""
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good")])
        mm = MemoryManager(tmp_path)
        assert mm.get_entity("nonexistent") is None

    def test_get_entity_empty_list_returns_none(self, tmp_path):
        """get_entity con entities.json vacia ([]) devuelve None."""
        _write_entities_json(tmp_path, [])
        mm = MemoryManager(tmp_path)
        assert mm.get_entity("anything") is None


# ---------------------------------------------------------------------------
# 8. find_entities(): entity incompleta omitida per-item (3.2.3.2)
# ---------------------------------------------------------------------------
class TestFindEntitiesWithIncompleteData:
    """find_entities() con datos incompletos (actualizado por 3.2.3.2).

    Con el manejo per-item introducido en 3.2.3.2, cada entity se reconstruye
    con `Entity.from_dict()` dentro de un try/except per-item: una entity
    incompleta se omite (registro de error) y no propaga `TypeError`; las
    entities validas que coinciden con la query se devuelven normalmente.
    """

    def test_find_entities_incomplete_skipped_valid_loaded(self, tmp_path):
        """find_entities() con una entity incompleta (falta name) → la entity
        invalida se omite per-item; la entity valida 'ok' que coincide con la
        query se devuelve. No se propaga TypeError.
        (Contrato definido por 3.2.3.2.)"""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [
            _make_valid_entity("ok", "Good"),
            incomplete,
        ])
        mm = MemoryManager(tmp_path)
        results = mm.find_entities(query="good")
        assert len(results) == 1
        assert results[0].id == "ok"

    def test_find_entities_all_valid_returns_matches(self, tmp_path):
        """find_entities() con entities completas funciona normalmente."""
        _write_entities_json(tmp_path, [
            _make_valid_entity("app1", "AppOne"),
            _make_valid_entity("app2", "AppTwo"),
        ])
        mm = MemoryManager(tmp_path)
        results = mm.find_entities(query="one")
        assert len(results) == 1
        assert results[0].id == "app1"

    def test_find_entities_empty_list_returns_empty(self, tmp_path):
        """find_entities() con entities.json vacia ([]) → []."""
        _write_entities_json(tmp_path, [])
        mm = MemoryManager(tmp_path)
        assert mm.find_entities(query="anything") == []


# ---------------------------------------------------------------------------
# 9. ApplicationManager: init con datos incompletos (actualizado por 3.2.3.2)
# ---------------------------------------------------------------------------
class TestApplicationManagerWithIncompleteData:
    """ApplicationManager.__init__() con datos incompletos en entities.json.

    __init__ llama _initialize_applications() (hardcoded Chrome/Spotify) y
    luego _load_custom_applications() que procesa entities reales. Con el
    manejo per-item de 3.2.3.2, una entity application invalida (falta name)
    se omite individualmente: la app valida 'Good' se carga desde entities
    y la invalida se registra y descarta, sin afectar a Chrome/Spotify.
    """

    @pytest.fixture
    def manager_with_incomplete(self, tmp_path):
        """ApplicationManager con entities.json que contiene una entity
        application incompleta (falta name)."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {"executable": "bad.exe"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [
            _make_valid_entity("ok", "Good"),
            incomplete,
        ])
        mm = MemoryManager(tmp_path)
        with patch(
            "src.hands.applications_core.get_memory_manager",
            return_value=mm,
        ):
            manager = ApplicationManager()
        return manager, mm, tmp_path

    def test_init_does_not_crash(self, manager_with_incomplete):
        manager, _, _ = manager_with_incomplete
        assert manager is not None

    def test_chrome_and_spotify_present(self, manager_with_incomplete):
        """Las apps hardcodeadas siguen presentes pese a datos incompletos."""
        manager, _, _ = manager_with_incomplete
        assert "chrome" in manager.applications
        assert "spotify" in manager.applications

    def test_open_capability_apps_present(self, manager_with_incomplete):
        """get_applications_by_capability(OPEN) devuelve Chrome y Spotify."""
        manager, _, _ = manager_with_incomplete
        open_apps = manager.get_applications_by_capability(ApplicationCapability.OPEN)
        names = {a.name for a in open_apps}
        assert names == {"Chrome", "Spotify"}

    def test_load_custom_applications_returns_none(self, manager_with_incomplete):
        """_load_custom_applications() devuelve None (metodo void), no lanza.
        Procesa entities reales con manejo per-item: omite la invalida."""
        manager, _, _ = manager_with_incomplete
        result = manager._load_custom_applications()
        assert result is None

    def test_valid_custom_app_loaded_invalid_skipped(self, manager_with_incomplete):
        """La app valida 'Good' (entity 'ok') se carga desde entities; la
        entity incompleta (falta name) se omite per-item y no aparece en el
        modelo. Chrome y Spotify permanecen. (Contrato definido por 3.2.3.2.)"""
        manager, _, _ = manager_with_incomplete
        assert set(manager.applications.keys()) == {"chrome", "spotify", "good"}
        # La entity invalida (bad_app, sin name) no se materializa
        assert "bad_app" not in manager.applications
        assert "badapp" not in manager.applications
        # La app valida 'Good' esta disponible
        assert manager.applications["good"].name == "Good"

    def test_repeated_load_no_effect(self, manager_with_incomplete):
        """Llamar _load_custom_applications() explicitamente no anade apps
        duplicadas (solo carga las ya registradas)."""
        manager, _, _ = manager_with_incomplete
        before = set(manager.applications.keys())
        manager._load_custom_applications()
        after = set(manager.applications.keys())
        assert before == after == {"chrome", "spotify", "good"}


# ---------------------------------------------------------------------------
# 10. DomainMemory: aplicaciones incompletas y entities incompletas
# ---------------------------------------------------------------------------
class TestDomainMemoryWithIncompleteData:
    """DomainMemory.load_domain_knowledge() con datos incompletos.

    - knowledge/applications.json: entries incompletos se almacenan tal
      cual (dict raw, sin validacion de schema).
    - knowledge/entities.json: si una entity carece de campos obligatorios,
      StorageEntity.from_dict() lanza TypeError, capturado por el try/except
      de la carga → self.entities queda {}.
    """

    def test_incomplete_app_entry_stored_as_is(self, tmp_path):
        """Aplicación incompleta en knowledge/applications.json se almacena
        tal cual (raw dict, sin validacion)."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        apps_data = {
            "chrome": {"name": "Google Chrome", "executable": "chrome.exe"},  # incompleto
            "broken": {"name": "BrokenApp"},  # muy incompleto
        }
        (knowledge_dir / "applications.json").write_text(
            json.dumps(apps_data), encoding="utf-8"
        )
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert len(dm.applications) == 2
        assert dm.applications["chrome"] == {"name": "Google Chrome", "executable": "chrome.exe"}
        assert dm.applications["broken"] == {"name": "BrokenApp"}
        assert "capabilities" not in dm.applications["chrome"]

    def test_incomplete_entity_loses_subsequent_entities(self, tmp_path):
        """knowledge/entities.json con una entity que falta `name` →
        StorageEntity.from_dict() lanza TypeError, capturado por el try/except
        de load_domain_knowledge. La entity valida CARGADA ANTES de la
        incompleta se conserva en self.entities; la incompleta y las
        siguientes se pierden. Se registra el error pero no se propaga."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        entities_data = [
            _make_valid_entity("ok", "GoodApp"),  # completa, cargada primero
            {
                "id": "bad", "type": "application",  # falta name
                "properties": {},
                "aliases": [], "tags": [], "confidence": 1.0,
                "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
            },
        ]
        (knowledge_dir / "entities.json").write_text(
            json.dumps(entities_data), encoding="utf-8"
        )
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        # La entity "ok" se carga ANTES del error → se conserva
        assert "ok" in dm.entities
        assert dm.entities["ok"].name == "GoodApp"
        # La entity "bad" falla → no se registra
        assert "bad" not in dm.entities

    def test_complete_entities_in_knowledge_load_fine(self, tmp_path):
        """knowledge/entities.json con entities completas se cargan OK."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        entities_data = [_make_valid_entity("ok", "GoodApp")]
        (knowledge_dir / "entities.json").write_text(
            json.dumps(entities_data), encoding="utf-8"
        )
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert "ok" in dm.entities
        assert dm.entities["ok"].name == "GoodApp"

    def test_incomplete_app_entry_does_not_break_applications_load(self, tmp_path):
        """Una entry de aplicación incompleta no rompe la carga de aplicaciones
        (DomainMemory.load_domain_knowledge carga applications como raw dict)."""
        knowledge_dir = tmp_path / "data" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        apps_data = {"incomplete_app": {"name": "Incomplete"}}
        (knowledge_dir / "applications.json").write_text(
            json.dumps(apps_data), encoding="utf-8"
        )
        with patch(
            "src.memory.conversation.get_project_root",
            return_value=tmp_path,
        ):
            from src.memory.conversation import DomainMemory
            dm = DomainMemory()
        assert dm.applications == {"incomplete_app": {"name": "Incomplete"}}


# ---------------------------------------------------------------------------
# 8. Error logging verification (3.2.3.3)
# ---------------------------------------------------------------------------
class TestErrorLoggingDuringLoad:
    """Verifica que los errores de carga se registran con detalle y sin
    ocultar la excepcion (unidad 3.2.3.3).

    - Cargas per-item (entity invalida) → WARNING con id de entity y texto
      de la excepcion.
    - Errores generales (JSONStorage.load/save, save_entity, _warm_cache) →
      ERROR con detalle de la excepcion.
    - No se usan mensajes genericos "Procesando solicitud" en paths de error.
    """

    @pytest.fixture
    def storage(self, tmp_path):
        return JSONStorage(tmp_path)

    @pytest.fixture
    def mm(self, tmp_path):
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good")])
        return MemoryManager(tmp_path)

    # --- JSONStorage.load(): JSONDecodeError → WARNING ---
    def test_load_corrupted_json_logs_warning(self, storage, tmp_path, caplog):
        """JSON truncado → JSONDecodeError capturado → se registra WARNING
        con referencia al archivo y la excepcion."""
        (tmp_path / "entities.json").write_text(
            '[{"id": "bad", "type":', encoding="utf-8"
        )
        caplog.set_level(logging.WARNING)
        storage.load(MemoryType.ENTITIES)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        msg = warnings[0].getMessage()
        assert "entities.json" in msg or "load" in msg.lower()
        # No generic "Procesando solicitud"
        assert "Procesando solicitud" not in msg

    # --- get_entity: entity incompleta → WARNING ---
    def test_get_entity_invalid_logs_warning_with_id_and_exception(self, tmp_path, caplog):
        """get_entity con entity que falta 'name' → WARNING que incluye el
        id de la entity y el texto de la excepcion (TypeError)."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [incomplete])
        mm = MemoryManager(tmp_path)
        caplog.set_level(logging.WARNING)

        result = mm.get_entity("bad_app")
        assert result is None

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        msg = warnings[0].getMessage()
        assert "bad_app" in msg
        assert "name" in msg.lower() or "required" in msg.lower()
        assert "get_entity" in msg

    # --- get_entities_by_type: entity incompleta → WARNING ---
    def test_get_entities_by_type_invalid_logs_warning(self, tmp_path, caplog):
        """get_entities_by_type con entity incompleta → WARNING per-item
        con el id y la excepcion; la entity valida se carga igual."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        mm = MemoryManager(tmp_path)
        caplog.set_level(logging.WARNING)

        result = mm.get_entities_by_type("application")
        assert len(result) == 1
        assert result[0].id == "ok"

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        msg = warnings[0].getMessage()
        assert "bad_app" in msg
        assert "get_entities_by_type" in msg

    # --- find_entities: entity incompleta → WARNING ---
    def test_find_entities_invalid_logs_warning(self, tmp_path, caplog):
        """find_entities con entity incompleta → WARNING per-item con el id
        y la excepcion."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        mm = MemoryManager(tmp_path)
        caplog.set_level(logging.WARNING)

        result = mm.find_entities("Good")
        assert len(result) == 1
        assert result[0].id == "ok"

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        msg = warnings[0].getMessage()
        assert "bad_app" in msg
        assert "find_entities" in msg

    # --- find_entities_by_property: entity incompleta → WARNING ---
    def test_find_entities_by_property_invalid_logs_warning(self, tmp_path, caplog):
        """find_entities_by_property con entity incompleta → WARNING per-item
        con el id y la excepcion."""
        # bad_app is truly invalid (missing 'name') but matches the property
        # filter so from_dict is actually attempted.
        incomplete = {
            "id": "bad_app",
            "type": "application",
            # NOTE: missing 'name' → Entity.from_dict raises TypeError
            "properties": {"executable": "bad.exe"},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(
            tmp_path,
            [_make_valid_entity("ok", "Good"), incomplete],
        )
        mm = MemoryManager(tmp_path)
        caplog.set_level(logging.WARNING)

        result = mm.find_entities_by_property(
            "executable", "bad.exe",
        )
        # bad_app matches the filter but is invalid → omitted (0 results)
        assert len(result) == 0

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        msg = warnings[0].getMessage()
        assert "bad_app" in msg
        assert "find_entities_by_property" in msg

    # --- per-item errors use WARNING, not INFO ---
    def test_per_item_errors_are_not_info_level(self, tmp_path, caplog):
        """Los errores per-item deben ser WARNING, nunca INFO."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [_make_valid_entity("ok", "Good"), incomplete])
        caplog.set_level(logging.DEBUG)
        mm = MemoryManager(tmp_path)
        mm.get_entity("bad_app")

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        # No INFO-level records related to the invalid entity
        relevant_info = [
            r for r in info_records
            if "bad_app" in r.getMessage() or "invalida" in r.getMessage().lower()
        ]
        assert len(relevant_info) == 0

    # --- no generic "Procesando solicitud" in error paths ---
    def test_no_generic_processing_request_in_error_paths(self, tmp_path, caplog):
        """Ningun mensaje de error debe contener el texto generico
        'Procesando solicitud'."""
        incomplete = {
            "id": "bad_app",
            "type": "application",
            "properties": {},
            "aliases": [], "tags": [], "confidence": 1.0,
            "created_at": "2024-01-01", "updated_at": "2024-01-01", "metadata": None,
        }
        _write_entities_json(tmp_path, [incomplete])
        caplog.set_level(logging.WARNING)
        mm = MemoryManager(tmp_path)
        mm.get_entities_by_type("application")

        for record in caplog.records:
            assert "Procesando solicitud" not in record.getMessage()

    # --- save_entity: exception → ERROR with exception text ---
    def test_save_entity_exception_logs_error_with_exception(self, tmp_path, caplog):
        """save_entity con file permission error → ERROR que incluye el
        tipo de excepcion."""
        from src.memory.storage import MemoryType
        mm = MemoryManager(tmp_path)
        caplog.set_level(logging.ERROR)

        with patch.object(
            mm.storage, "save",
            side_effect=OSError("disk full"),
        ):
            result = mm.save_entity(Entity(
                id="test_ent", type="application", name="Test", properties={},
                created_at="2024-01-01T00:00:00", updated_at="2024-01-01T00:00:00",
            ))
            assert result is False

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) >= 1
        msg = errors[0].getMessage()
        assert "disk full" in msg
        assert "save_entity" in msg

    # --- JSONStorage.save: exception → ERROR ---
    def test_json_storage_save_exception_logs_error(self, tmp_path, caplog):
        """JSONStorage.save() con excepcion → ERROR con detalle."""
        storage = JSONStorage(tmp_path)
        caplog.set_level(logging.ERROR)

        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = storage.save([{"id": "x"}], MemoryType.ENTITIES)
            assert result is False

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) >= 1
        msg = errors[0].getMessage()
        assert "permission denied" in msg
        assert "save" in msg.lower()

    # --- _warm_cache: exception → ERROR ---
    def test_warm_cache_exception_logs_error(self, tmp_path, caplog):
        """_warm_cache con excepcion en load() → ERROR con detalle."""
        caplog.set_level(logging.ERROR)
        with patch.object(
            JSONStorage, "load",
            side_effect=OSError("io error during warm cache"),
        ):
            mm = MemoryManager(tmp_path)  # __init__ calls _warm_cache

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) >= 1
        msg = errors[0].getMessage()
        assert "io error during warm cache" in msg
