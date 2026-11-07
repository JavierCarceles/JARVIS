# -*- coding: utf-8 -*-
"""
Contrato de la unidad 3.8.4.6.4 (padre 3.8.4.6, FASE 3.8).

Objetivo verificable:
    Un entities.json ausente, vacio o corrupto no se sobrescribe perdiendo
    entidades en silencio. El comportamiento resultante queda definido y
    probado segun el contrato real: RECHAZO.

Contrato definido (RECHAZO):
    - Fichero ausente: se permite crear entities.json con la entidad
      (no hay datos previos que perder).
    - Fichero vacio o lista JSON valida (incluida []): no hay datos validos
      que perder; se procede con la operacion normal de fusion.
    - Fichero corrupto (JSON invalido) o contenido no-lista: se RECHAZA la
      escritura (save_entity retorna False), se registra en el log y el
      fichero original se deja intacto; no se sobrescribe y no se pierden
      datos silenciosamente.

Registro 3.2.3.1 documenta que con fichero corrupto register_application
lo dejaba en [] (pérdida silenciosa). Este test impide que eso vuelva a
suceder.

Trabaja SIEMPRE sobre copias en directorios temporales (tmp_path). Nunca
escribe ni modifica el fichero real de datos del repo.
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


class TestContratoRechazoEstadoInicialEntitiesJson:
    """save_entity no sobrescribe silenciosamente entities.json cuando el
    estado inicial del fichero es ausente, vacio o corrupto."""

    def test_crea_fichero_cuando_no_existe(self, tmp_path: Path):
        """Fichero ausente: se crea entities.json con la entidad."""
        memoria_dir = tmp_path / "memory"
        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        entities_json = memoria_dir / "entities.json"
        assert entities_json.exists()
        assert _ids_en(entities_json) == {"ent-uno"}
        assert manager.get_entity("ent-uno") is not None

    def test_sobre_fichero_vacio_no_pierde_datos(self, tmp_path: Path):
        """Fichero vacio (contenido vacio): se procede y se escribe la entidad."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("", encoding="utf-8")

        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        assert _ids_en(entities_json) == {"ent-uno"}
        assert manager.get_entity("ent-uno") is not None

    def test_sobre_lista_vacia_preserva_y_anade(self, tmp_path: Path):
        """Fichero con []: no hay datos validos que perder, se añade la entidad."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("[]", encoding="utf-8")

        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        assert _ids_en(entities_json) == {"ent-uno"}
        assert manager.get_entity("ent-uno") is not None

    def test_rechaza_fichero_corrupto_sin_sobreescribir(self, tmp_path: Path):
        """Fichero corrupto (JSON invalido): se rechaza, retorna False y el
        fichero queda intacto (no se pierde nada silenciosamente)."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("{no es json valido", encoding="utf-8")

        contenido_antes = entities_json.read_bytes()
        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is False

        # El fichero original se deja intacto: no se sobrescribe.
        assert entities_json.read_bytes() == contenido_antes
        assert _ids_en(entities_json) == {"__CORRUPT__"}
        # Nada se persiste.
        assert manager.get_entity("ent-uno") is None

    def test_rechaza_fichero_json_no_lista_sin_sobreescribir(self, tmp_path: Path):
        """Fichero con JSON valido pero no-lista (p.ej. un diccionario): se
        rechaza y el fichero queda intacto."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text('{"clave": "valor"}', encoding="utf-8")

        contenido_antes = entities_json.read_bytes()
        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is False

        assert entities_json.read_bytes() == contenido_antes
        assert _ids_en(entities_json) == {"__NOT_A_LIST__"}
        assert manager.get_entity("ent-uno") is None

    def test_no_regresion_lista_valida_preserva_entidades_previas(
        self, tmp_path: Path
    ):
        """Regresion 3.8.4.6.3: fichero valido con entidades previas se
        fusiona sin perder ninguna al añadir una nueva."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entidades_previas = [
            {"id": "ent-a", "type": "application", "name": "A",
             "properties": {}, "created_at": "2024-01-01T00:00:00",
             "updated_at": "2024-01-01T00:00:00"},
            {"id": "ent-b", "type": "application", "name": "B",
             "properties": {}, "created_at": "2024-01-01T00:00:00",
             "updated_at": "2024-01-01T00:00:00"},
        ]
        entities_json.write_text(
            json.dumps(entidades_previas, ensure_ascii=False), encoding="utf-8"
        )

        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-c", "C")) is True

        ids = _ids_en(entities_json)
        assert ids == {"ent-a", "ent-b", "ent-c"}, (
            f"Regresion: se esperaban ent-a, ent-b, ent-c; se obtuvieron {ids}"
        )
        assert manager.get_entity("ent-a") is not None
        assert manager.get_entity("ent-b") is not None
        assert manager.get_entity("ent-c") is not None
