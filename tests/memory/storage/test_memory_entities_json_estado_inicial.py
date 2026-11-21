# -*- coding: utf-8 -*-
"""
Contrato de la unidad 3.8.4.6.4 (padre 3.8.4.6, FASE 3.8).

Objetivo verificable:
    Un entities.json ausente, vacio o corrupto no se sobrescribe perdiendo
    entidades en silencio. El comportamiento resultante queda definido y
    probado segun el contrato real: REPARACION SIN PERDIDA.

Contrato definido (REPARACION SIN PERDIDA, decidido por el usuario el
2026-11-21; sustituye al RECHAZO original de 3.8.4.6.4 y a la reparacion con
perdida que introdujo 3.8.5.1.4.11.6):
    - Fichero ausente: se permite crear entities.json con la entidad
      (no hay datos previos que perder).
    - Fichero vacio o lista JSON valida (incluida []): no hay datos validos
      que perder; se procede con la operacion normal de fusion.
    - Fichero corrupto (JSON invalido) o contenido no-lista: se guarda una
      copia exacta del original (entities.json.corrupto-<fecha>), se
      recuperan todas las entidades completas que contenga y se escribe una
      lista valida con ellas y la entidad nueva (save_entity retorna True).
    - Si la copia del original no se puede escribir: se RECHAZA la escritura
      (False) y el fichero queda intacto.

Registro 3.2.3.1 documenta que con fichero corrupto register_application
lo dejaba en [] (perdida silenciosa). Este test impide que eso vuelva a
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


def _copias_corruptas(directorio: Path) -> list:
    """Copias del original que save_entity deja junto a entities.json."""
    return sorted(directorio.glob("entities.json.corrupto-*"))


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
        """Fichero con []: no hay datos validos que perder, se anade la entidad."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("[]", encoding="utf-8")

        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        assert _ids_en(entities_json) == {"ent-uno"}
        assert manager.get_entity("ent-uno") is not None

    def test_fichero_corrupto_se_repara_con_copia_del_original(self, tmp_path: Path):
        """Fichero corrupto sin entidades recuperables: copia exacta del
        original y lista valida con la entidad nueva."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("{no es json valido", encoding="utf-8")

        contenido_antes = entities_json.read_bytes()
        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        copias = _copias_corruptas(memoria_dir)
        assert len(copias) == 1
        assert copias[0].read_bytes() == contenido_antes
        assert _ids_en(entities_json) == {"ent-uno"}
        assert manager.get_entity("ent-uno") is not None

    def test_fichero_json_no_lista_se_repara_con_copia_del_original(self, tmp_path: Path):
        """JSON valido pero no-lista (un diccionario que no es entidad): copia
        exacta del original y lista valida con la entidad nueva."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text('{"clave": "valor"}', encoding="utf-8")

        contenido_antes = entities_json.read_bytes()
        manager = MemoryManager(storage_path=str(memoria_dir))

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        copias = _copias_corruptas(memoria_dir)
        assert len(copias) == 1
        assert copias[0].read_bytes() == contenido_antes
        assert _ids_en(entities_json) == {"ent-uno"}

    def test_lista_truncada_conserva_las_entidades_completas(self, tmp_path: Path):
        """Lista cortada a mitad de la tercera entidad: las dos completas se
        conservan con todos sus campos y se anade la nueva."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        previas = [
            {"id": "ent-a", "type": "application", "name": "A",
             "properties": {"ui_elements": [{"name": "Boton", "type": "button"}]},
             "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"},
            {"id": "ent-b", "type": "application", "name": "B", "properties": {},
             "created_at": "2024-01-02T00:00:00", "updated_at": "2024-01-02T00:00:00"},
        ]
        texto = json.dumps(previas, ensure_ascii=False, indent=2)
        truncado = texto[:-2] + ',\n  {"id": "ent-c", "type": "applic'
        entities_json.write_text(truncado, encoding="utf-8")

        manager = MemoryManager(storage_path=str(memoria_dir))
        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is True

        datos = json.loads(entities_json.read_text(encoding="utf-8"))
        por_id = {e["id"]: e for e in datos}
        assert set(por_id) == {"ent-a", "ent-b", "ent-uno"}
        assert por_id["ent-a"] == previas[0]
        assert por_id["ent-b"] == previas[1]
        assert _copias_corruptas(memoria_dir)[0].read_text(encoding="utf-8") == truncado

    def test_sin_copia_del_original_rechaza_sin_tocar_el_fichero(
        self, tmp_path: Path, monkeypatch
    ):
        """Si la copia del original falla, no se escribe nada."""
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        entities_json = memoria_dir / "entities.json"
        entities_json.write_text("{no es json valido", encoding="utf-8")
        contenido_antes = entities_json.read_bytes()

        manager = MemoryManager(storage_path=str(memoria_dir))
        monkeypatch.setattr(
            MemoryManager, "_respaldar_fichero_corrupto", staticmethod(lambda *a, **k: None)
        )

        assert manager.save_entity(_nueva_entidad("ent-uno", "Uno")) is False
        assert entities_json.read_bytes() == contenido_antes
        assert _copias_corruptas(memoria_dir) == []

    def test_no_regresion_lista_valida_preserva_entidades_previas(
        self, tmp_path: Path
    ):
        """Regresion 3.8.4.6.3: fichero valido con entidades previas se
        fusiona sin perder ninguna al anadir una nueva."""
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
