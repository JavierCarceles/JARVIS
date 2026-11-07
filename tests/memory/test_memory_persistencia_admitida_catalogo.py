# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.4.7.5 (padre 3.8.4.7, FASE 3.8).

Objetivo verificable:
    La persistencia de entidades esta ADMITIDA (funciona realmente en disco)
    tras el arreglo del defecto D-ENTITIES-PERSIST-BUG en 3.8.4.6.3:

    - Guardar entidades con save_entity, crear un NUEVO MemoryManager sobre el
      mismo directorio temporal (simula reinicio del sistema) y verificar que
      las entidades se recuperan desde disco (no solo desde la cache).
    - El registro explicito de catalogo (varias save_entity) persiste: todas
      las entidades quedan en entities.json y son recuperables por id tras
      recarga.
    - Actualizar una entidad existente (upsert por id) no duplica y persiste
      tras recarga.
    - Trabaja SIEMPRE sobre copias en directorios temporales (tmp_path). Nunca
      escribe ni modifica el fichero real de datos del repo.

Contexto:
    Las pruebas de 3.8.4.6.2 (defecto corregido con una misma instancia) y
    3.8.4.6.4 (rechazo de archivos corruptos/vacios) ya cubren el arreglo del
    defecto y el contrato de rechazo. Esta unidad cubre la persistencia
    admitida tras recarga (nueva instancia de MemoryManager) y el registro
    explicito de catalogo, sobre copias temporales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory.storage import Entity, MemoryManager


def _nueva_entidad(entity_id: str, nombre: str) -> Entity:
    return Entity(
        id=entity_id,
        type="application",
        name=nombre,
        properties={},
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )


def _ids_en(path: Path) -> set:
    """Devuelve los ids de entidad contenido en un fichero entities.json."""
    if not path.exists():
        return set()
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {"__CORRUPT__"}
    if not isinstance(datos, list):
        return {"__NOT_A_LIST__"}
    return {e.get("id") for e in datos if isinstance(e, dict)}


class TestPersistenciaAdmitidaTrasRecarga:
    """save_entity persiste en disco y sobrevive a una nueva instancia
    de MemoryManager (simula reinicio del sistema)."""

    def test_nueva_instancia_recupera_entidades_desde_disco(self, tmp_path: Path):
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)

        manager1 = MemoryManager(storage_path=str(memoria_dir))
        e1 = _nueva_entidad("cat-uno", "Catalogo Uno")
        e2 = _nueva_entidad("cat-dos", "Catalogo Dos")
        assert manager1.save_entity(e1) is True
        assert manager1.save_entity(e2) is True

        # Nueva instancia sobre el mismo directorio: lee desde disco, no de cache.
        manager2 = MemoryManager(storage_path=str(memoria_dir))

        recuperada_uno = manager2.get_entity("cat-uno")
        recuperada_dos = manager2.get_entity("cat-dos")
        assert recuperada_uno is not None, "cat-uno debe recuperarse desde disco tras recarga"
        assert recuperada_dos is not None, "cat-dos debe recuperarse desde disco tras recarga"
        assert recuperada_uno.name == "Catalogo Uno"
        assert recuperada_dos.name == "Catalogo Dos"

        entities_json = memoria_dir / "entities.json"
        assert _ids_en(entities_json) == {"cat-uno", "cat-dos"}

    def test_persistencia_admitida_sobre_copia_temporal_no_toca_produccion(
        self, tmp_path: Path
    ):
        """La operacion completa (guardar, recargar, verificar) ocurre en un
        directorio temporal y el entities.json real queda intacto."""
        from tests.helpers.entities_state import snapshot_entities_json

        _TESTS_DIR = Path(__file__).resolve().parents[1]
        _ROOT_DIR = _TESTS_DIR.parent
        REAL_ENTITIES_JSON = _ROOT_DIR / "data" / "knowledge" / "entities.json"

        antes = snapshot_entities_json(REAL_ENTITIES_JSON)

        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))
        assert manager.save_entity(_nueva_entidad("tmp-solo-temporal", "Solo Temporal")) is True

        despues = snapshot_entities_json(REAL_ENTITIES_JSON)
        assert antes.sha256 == despues.sha256, (
            "el entities.json real no debe modificarse por pruebas temporales"
        )


class TestRegistroExplicitoDeCatalogo:
    """Varias save_entity (registro explicito de catalogo) persisten completo
    tras recarga en una nueva instancia de MemoryManager."""

    def test_registro_explicito_de_catalogo_persiste_todas_tras_recarga(
        self, tmp_path: Path
    ):
        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))

        entidades = [
            _nueva_entidad("cat-a", "Catalogo A"),
            _nueva_entidad("cat-b", "Catalogo B"),
            _nueva_entidad("cat-c", "Catalogo C"),
        ]
        for ent in entidades:
            assert manager.save_entity(ent) is True

        # Recarga en nueva instancia: el catalogo registrado persiste completo.
        manager2 = MemoryManager(storage_path=str(memoria_dir))
        for ent in entidades:
            recuperada = manager2.get_entity(ent.id)
            assert recuperada is not None, f"{ent.id} no recuperable tras recarga"
            assert recuperada.name == ent.name
            assert recuperada.type == ent.type

        entities_json = memoria_dir / "entities.json"
        assert _ids_en(entities_json) == {"cat-a", "cat-b", "cat-c"}


class TestActualizacionDeEntidadExistente:
    """Actualizar una entidad existente (mismo id) no duplica y persiste."""

    def test_actualizar_entidad_no_duplica_y_persiste(self, tmp_path: Path):
        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))

        e = _nueva_entidad("cat-upd", "Original")
        assert manager.save_entity(e) is True

        # Actualizar la misma entidad (mismo id, nombre y propiedades distintos).
        e_actualizada = Entity(
            id="cat-upd",
            type="application",
            name="Actualizado",
            properties={"version": 2},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        assert manager.save_entity(e_actualizada) is True

        entities_json = memoria_dir / "entities.json"
        datos = json.loads(entities_json.read_text(encoding="utf-8"))
        ids = [d.get("id") for d in datos if isinstance(d, dict)]
        assert ids.count("cat-upd") == 1, "no debe duplicarse la entidad al actualizar"

        # Recarga: la entidad actualizada persiste con el nuevo nombre y props.
        manager2 = MemoryManager(storage_path=str(memoria_dir))
        recuperada = manager2.get_entity("cat-upd")
        assert recuperada is not None
        assert recuperada.name == "Actualizado"
        assert recuperada.properties == {"version": 2}
