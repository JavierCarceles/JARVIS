# -*- coding: utf-8 -*-
"""
Reproduccion del defecto D-ENTITIES-PERSIST-BUG (unidad 3.8.4.6.2).

Defecto (pendiente desde 3.2.1.3):
- MemoryManager.save_entity convierte la entidad a dict y luego llama a
  JSONStorage.save(entities, ENTITIES) pasando una LISTA DE DICT.
- JSONStorage._process_data_for_save para MemoryType.ENTITIES solo procesa
  instancias de Entity (ignora los dict), por lo que ninguna entidad se
  anade: entities.json queda en [] y la cache solo conserva la ultima
  entidad guardada.

Contrato esperado: tras guardar varias entidades, entities.json debe
contener todas y get_entity debe recuperarlas por id.

Este test DEBE fallar con el codigo actual (defecto presente). La
correccion es competencia de la unidad 3.8.4.6.3; aqui NO se modifica
codigo de produccion ni se tocan ficheros de datos reales (se usa
directorio temporal via tmp_path).
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


class TestDefectoDEntitiesPersistBug:
    """save_entity debe conservar las entidades previas en disco y en cache."""

    def test_save_entity_conserva_entidades_previas_en_disco(self, tmp_path: Path):
        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))

        e1 = _nueva_entidad("ent-uno", "Entidad Uno")
        e2 = _nueva_entidad("ent-dos", "Entidad Dos")

        assert manager.save_entity(e1) is True
        assert manager.save_entity(e2) is True

        entities_json = memoria_dir / "entities.json"
        assert entities_json.exists(), "entities.json debe crearse en el directorio temporal"

        datos = json.loads(entities_json.read_text(encoding="utf-8"))
        ids = {e.get("id") for e in datos if isinstance(e, dict)}

        # Con el defecto D-ENTITIES-PERSIST-BUG, datos == [] y ids == set().
        assert ids == {"ent-uno", "ent-dos"}, (
            f"Defecto D-ENTITIES-PERSIST-BUG: solo se persisten {ids}; "
            "se esperaban ambas entidades"
        )

    def test_get_entity_recupera_todas_las_entidades_guardadas(self, tmp_path: Path):
        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))

        e1 = _nueva_entidad("ent-uno", "Entidad Uno")
        e2 = _nueva_entidad("ent-dos", "Entidad Dos")

        assert manager.save_entity(e1) is True
        assert manager.save_entity(e2) is True

        # Con el defecto, la cache solo conserva la ultima entidad y el disco
        # queda en [], por lo que get_entity devuelve None para cualquiera
        # salvo (quizas) la ultima.
        assert manager.get_entity("ent-uno") is not None, (
            "Defecto D-ENTITIES-PERSIST-BUG: ent-uno no recuperable tras guardarla"
        )
        assert manager.get_entity("ent-dos") is not None, (
            "Defecto D-ENTITIES-PERSIST-BUG: ent-dos no recuperable tras guardarla"
        )
