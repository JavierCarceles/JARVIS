# -*- coding: utf-8 -*-
"""
Tests de la unidad 3.8.4.7.6 (padre 3.8.4.7, FASE 3.8).

Objetivo verificable:
    Registrar aplicaciones descubiertas y de catalogo (con posibles duplicados
    por nombre normalizado o por alias) y verificar que:

    1. No se crean duplicados: una aplicacion ya registrada (por nombre o alias)
       se conserva y no se reemplaza ni duplica.
    2. entities.json se preserva EXACTAMENTE contra la linea base fijada en
       3.8.4.4.2: data/knowledge/entities.json = 7 entidades / 3231 bytes /
       SHA-256 60635AA8F64FAAD75C2C9635E483769874A60E0A98FD1244F696AC2B62A0DAB7.
       Tras cualquier operacion de registro, el fichero de produccion permanece
       intacto (mismo hash, mismo contenido, mismos 7 ids).

    Trabaja SIEMPRE sobre copias en directorios temporales para operaciones de
    disco. Nunca escribe ni modifica el fichero real de datos del repo.

Contexto:
    - register_discovered_application (applications_core.py) nunca llama a
      save_entity: las descubiertas viven solo en memoria y no alteran
      entities.json (verificado en 3.8.4.7.4).
    - register_application (applications_core.py) llama a save_entity y omite
      duplicados por nombre normalizado (verificado en 3.8.4.6.1).
    - MemoryManager.save_entity (storage.py) hace upsert por id y rechaza
      ficheros corruptos/no-lista (verificado en 3.8.4.6.3 y 3.8.4.6.4).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.hands.applications_core import (
    ApplicationKnowledge,
    ApplicationManager,
)
from src.memory.storage import Entity, MemoryManager
from tests.helpers.entities_state import snapshot_entities_json

TESTS_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = TESTS_DIR.parent
REAL_ENTITIES_JSON = ROOT_DIR / "data" / "knowledge" / "entities.json"

LINEA_BASE_SHA256 = "60635AA8F64FAAD75C2C9635E483769874A60E0A98FD1244F696AC2B62A0DAB7"
LINEA_BASE_BYTES = 3231
LINEA_BASE_ENTIDADES = 7
LINEA_BASE_IDS = {"nissaxter", "shroud", "pokimane", "youtube", "spotify", "github", "twitch"}


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


class _FakeMemoryManager:
    """Memory manager simulado que registra si se llamo a save_entity."""

    def __init__(self) -> None:
        self.saved_entities: list = []

    def save_entity(self, entity: object) -> None:
        self.saved_entities.append(entity)

    def get_entities_by_type(self, _type: str) -> list:
        return []


def _make_manager() -> ApplicationManager:
    """Crea ApplicationManager sin __init__ (evita registrar Chrome/Spotify
    ni cargar entidades de memoria) y con memory_manager falsificado."""
    manager = ApplicationManager.__new__(ApplicationManager)
    manager.applications = {}
    manager.memory_manager = _FakeMemoryManager()
    return manager


class TestLineaBaseConocimientoIntacto:
    """data/knowledge/entities.json permanece exactamente como la linea base
    de 3.8.4.4.2 y no se altera tras operaciones de registro."""

    def test_linea_base_3_8_4_4_2(self) -> None:
        antes = snapshot_entities_json(REAL_ENTITIES_JSON)
        datos = json.loads(antes.contenido.decode("utf-8"))
        assert isinstance(datos, list)
        assert len(datos) == LINEA_BASE_ENTIDADES
        assert antes.size_bytes == LINEA_BASE_BYTES
        # SHA-256 hexadecimal: se compara sin distinguir mayusculas/minusculas
        # porque el registro 3.8.4.4.2 lo escribio en mayusculas y hexdigest()
        # devuelve minusculas; el valor hexadecimal es idéntico.
        assert antes.sha256.lower() == LINEA_BASE_SHA256.lower(), (
            f"hash de linea base no coincide: {antes.sha256} vs {LINEA_BASE_SHA256}"
        )
        ids = {e.get("id") for e in datos if isinstance(e, dict)}
        assert ids == LINEA_BASE_IDS

    def test_produccion_intacta_tras_registro_descubiertas(self) -> None:
        """Registrar descubiertas (nuevas, duplicadas, colision de alias) no
        toca data/knowledge/entities.json: misma hash, mismo contenido."""
        antes = snapshot_entities_json(REAL_ENTITIES_JSON)

        manager = _make_manager()
        # Descubiertas nuevas
        manager.register_discovered_application(name="App Nueva 1", type="utility")
        manager.register_discovered_application(name="App Nueva 2", type="utility")
        # Duplicado por nombre normalizado: se conserva la entrada previa
        duplicado = manager.register_discovered_application(name="App Nueva 1", type="utility")
        assert duplicado is not None
        # Colision por alias: nombre normalizado de descubierta es alias de existente
        manager.register_discovered_application(
            name="App Nueva 3", type="utility", metadata={"aliases": ["app nueva 1"]}
        )

        despues = snapshot_entities_json(REAL_ENTITIES_JSON)
        assert antes.sha256 == despues.sha256, (
            "data/knowledge/entities.json debe permanecer intacto tras registro de descubiertas"
        )
        assert antes.contenido == despues.contenido
        assert antes.size_bytes == despues.size_bytes
        ids_despues = _ids_en(REAL_ENTITIES_JSON)
        assert ids_despues == LINEA_BASE_IDS, (
            "las 7 entidades originales de la linea base deben permanecer"
        )


class TestNoDuplicadosMemoria:
    """register_discovered_application y register_application evitan
    duplicados en memoria (nombre normalizado y alias)."""

    def test_descubierta_duplicada_no_duplica_en_memoria(self) -> None:
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]
        entidades_antes = len(manager.applications)
        saved_antes = len(mm.saved_entities)

        app1 = manager.register_discovered_application(name="NuevaApp", type="utility")
        app2 = manager.register_discovered_application(name="NuevaApp", type="utility")

        assert app1 is app2, "mismo nombre normalizado -> retorna la entrada previa"
        assert len(manager.applications) == entidades_antes + 1, "no se crea duplicado en memoria"
        assert len(mm.saved_entities) == saved_antes, "register_discovered_application no llama a save_entity"

    def test_registro_catalogo_duplicado_no_guarda_dos_veces(self) -> None:
        """register_application omite duplicados por nombre normalizado y no
        llama a save_entity dos veces."""
        manager = _make_manager()
        mm: _FakeMemoryManager = manager.memory_manager  # type: ignore[assignment]
        saved_antes = len(mm.saved_entities)

        app = ApplicationKnowledge(name="Chrome", type="browser", executable="chrome.exe")
        assert manager.register_application(app) is True
        assert len(mm.saved_entities) == saved_antes + 1

        app2 = ApplicationKnowledge(name="chrome", type="browser", executable="chrome.exe")
        assert manager.register_application(app2) is False, "nombre normalizado duplicado -> se omite"
        assert len(mm.saved_entities) == saved_antes + 1, "no se guarda dos veces la misma entidad"

    def test_duplicado_por_alias_no_duplica_en_memoria(self) -> None:
        """Nombre normalizado de descubierta colisiona con alias de app existente."""
        manager = _make_manager()
        existente = ApplicationKnowledge(
            name="MiApp", type="utility", executable="miapp.exe",
            metadata={"aliases": ["miapp_alias", "mi app"]},
        )
        manager.register_application(existente)

        app = manager.register_discovered_application(name="miapp_alias", type="utility")
        assert app is existente, "colision por alias -> conserva la entrada previa"
        assert len(manager.applications) == 1, "no se agrega ninguna entrada nueva"


class TestUpsertSinDuplicadosContraLineaBase:
    """save_entity sobre una COPIA de la linea base: upsert por id sin
    duplicados y las 7 entidades originales se preservan exactamente."""

    def _setup_copia_linea_base(self, tmp_path: Path) -> tuple[Path, MemoryManager]:
        memoria_dir = tmp_path / "memory"
        memoria_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_ENTITIES_JSON, memoria_dir / "entities.json")
        manager = MemoryManager(storage_path=str(memoria_dir))
        return memoria_dir / "entities.json", manager

    def test_guardar_nueva_y_upsert_existente_no_duplica(self, tmp_path: Path) -> None:
        """Entidad nueva se añade; entidad con id existente se actualiza
        (upsert) sin duplicar. Las 7 originales de la linea base se preservan."""
        entities_json, manager = self._setup_copia_linea_base(tmp_path)

        # Estado inicial: 7 entidades de la linea base
        assert _ids_en(entities_json) == LINEA_BASE_IDS

        # Guardar entidad nueva
        e_nueva = Entity(
            id="app_registro_nuevo",
            type="application",
            name="Registro Nuevo",
            properties={},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert manager.save_entity(e_nueva) is True
        assert _ids_en(entities_json) == LINEA_BASE_IDS | {"app_registro_nuevo"}, (
            "se añade una entidad nueva sin tocar las originales"
        )

        # Upsert: guardar entidad con id existente (nissaxter de la linea base)
        e_existente = Entity(
            id="nissaxter",
            type="streamer",
            name="Nissaxter Actualizado",
            properties={"platform": "twitch"},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        assert manager.save_entity(e_existente) is True
        ids_despues = _ids_en(entities_json)
        assert ids_despues == LINEA_BASE_IDS | {"app_registro_nuevo"}, (
            f"upsert por id no debe duplicar: {ids_despues}"
        )
        assert len(ids_despues) == 8, "7 originales + 1 nueva = 8, nunca mas"

    def test_recarga_preserva_linea_base_y_nuevas(self, tmp_path: Path) -> None:
        """Una nueva instancia de MemoryManager lee desde disco: las 7
        entidades de la linea base y la entidad nueva persisten sin duplicar."""
        entities_json, manager = self._setup_copia_linea_base(tmp_path)

        e_nueva = Entity(
            id="app_recarga",
            type="application",
            name="Recarga",
            properties={},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert manager.save_entity(e_nueva) is True

        # Nueva instancia sobre el mismo directorio: lee desde disco.
        manager2 = MemoryManager(storage_path=str(tmp_path / "memory"))
        assert manager2.get_entity("nissaxter") is not None, "linea base recuperada desde disco"
        assert manager2.get_entity("app_recarga") is not None, "entidad nueva recuperada desde disco"
        assert _ids_en(entities_json) == LINEA_BASE_IDS | {"app_recarga"}, (
            "sin duplicados tras recarga"
        )

    def test_produccion_intacta_despues_de_operaciones_disco(self, tmp_path: Path) -> None:
        """Las operaciones sobre copias temporales no modifican el fichero
        real de produccion data/knowledge/entities.json."""
        antes = snapshot_entities_json(REAL_ENTITIES_JSON)

        # Ejecutar operaciones de disco sobre copia temporal
        self._setup_copia_linea_base(tmp_path)

        despues = snapshot_entities_json(REAL_ENTITIES_JSON)
        assert antes.sha256.lower() == despues.sha256.lower() == LINEA_BASE_SHA256.lower(), (
            "el fichero real de produccion permanece intacto"
        )
        assert antes.contenido == despues.contenido
        assert _ids_en(REAL_ENTITIES_JSON) == LINEA_BASE_IDS

